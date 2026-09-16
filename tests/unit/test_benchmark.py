"""Unit tests for the T025 benchmark helper (`scripts/benchmark.py`).

`scripts/` isn't part of the installed `whisperflow` package (it's a
standalone helper, not shipped with the CLI), so it isn't importable via a
normal `import benchmark` the way `src/`'s packages are once the project is
installed. This file adds `scripts/` to `sys.path` itself, the same
bootstrap trick `benchmark.py` uses for `src/` (see its own
`_bootstrap_src_path()`), so it can be imported and unit-tested directly.

Every external seam (`cli.pipeline.run_pipeline`) is monkeypatched at its
`benchmark`-module-local name, mirroring `tests/unit/test_pipeline.py`'s own
pattern of isolating a module's one real dependency behind a mockable name
-- no real `ffmpeg`/`faster-whisper` call happens in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark  # noqa: E402
from audio.video_probe import Video  # noqa: E402
from subtitles.models import SubtitleFile, SubtitleLine  # noqa: E402


def _video(tmp_path: Path, duration_seconds: float = 10.0) -> Video:
    return Video(
        path=tmp_path / "clip.mp4",
        container_format="mp4",
        duration_seconds=duration_seconds,
        has_audio_track=True,
    )


def _line(index: int, start: float, end: float, text: str) -> SubtitleLine:
    return SubtitleLine(index=index, start_seconds=start, end_seconds=end, text=text)


# ---------------------------------------------------------------------------
# word_error_rate / transcript_accuracy
# ---------------------------------------------------------------------------


class TestWordErrorRateAndAccuracy:
    def test_identical_text_is_zero_error_full_accuracy(self):
        assert benchmark.word_error_rate("Hello there.", "Hello there.") == 0.0
        assert benchmark.transcript_accuracy("Hello there.", "Hello there.") == 1.0

    def test_case_and_punctuation_differences_are_ignored(self):
        assert benchmark.word_error_rate("Hello, THERE!", "hello there") == 0.0

    def test_one_substituted_word_out_of_four(self):
        # "quick" -> "slow": 1 substitution / 4 reference words.
        wer = benchmark.word_error_rate("the quick brown fox", "the slow brown fox")
        assert wer == pytest.approx(0.25)
        assert benchmark.transcript_accuracy(
            "the quick brown fox", "the slow brown fox"
        ) == pytest.approx(0.75)

    def test_completely_wrong_hypothesis_has_full_error(self):
        wer = benchmark.word_error_rate("hello world", "goodbye moon")
        assert wer == pytest.approx(1.0)

    def test_extra_inserted_words_can_exceed_full_error_but_accuracy_clamps_to_zero(self):
        wer = benchmark.word_error_rate("hi", "hi there world how are you")
        assert wer > 1.0
        assert benchmark.transcript_accuracy("hi", "hi there world how are you") == 0.0

    def test_empty_reference_and_empty_hypothesis_is_zero_error(self):
        assert benchmark.word_error_rate("", "") == 0.0

    def test_empty_reference_with_nonempty_hypothesis_is_full_error(self):
        assert benchmark.word_error_rate("", "unexpected words") == 1.0

    def test_empty_hypothesis_with_nonempty_reference_is_full_error(self):
        assert benchmark.word_error_rate("some reference text", "") == 1.0


# ---------------------------------------------------------------------------
# subtitle_timing_sync_ratio
# ---------------------------------------------------------------------------


class TestSubtitleTimingSyncRatio:
    def test_empty_subtitle_file_is_vacuously_in_sync(self, tmp_path: Path):
        subtitle_file = SubtitleFile(source_video=_video(tmp_path), lines=[])
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file) == 1.0

    def test_line_with_ample_duration_is_in_sync(self, tmp_path: Path):
        # 4 characters over 2 seconds = 2 chars/sec, well under the default cap.
        line = _line(1, 0.0, 2.0, "text")
        subtitle_file = SubtitleFile(source_video=_video(tmp_path), lines=[line])
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file) == 1.0

    def test_line_crammed_faster_than_max_reading_speed_is_out_of_sync(self, tmp_path: Path):
        # 100 characters in 1 second = 100 chars/sec, far above any plausible
        # reading speed.
        line = _line(1, 0.0, 1.0, "x" * 100)
        subtitle_file = SubtitleFile(source_video=_video(tmp_path), lines=[line])
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file) == 0.0

    def test_mixed_lines_report_the_correct_fraction(self, tmp_path: Path):
        good_line = _line(1, 0.0, 2.0, "short")
        bad_line = _line(2, 2.0, 3.0, "x" * 100)
        subtitle_file = SubtitleFile(source_video=_video(tmp_path), lines=[good_line, bad_line])
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file) == pytest.approx(0.5)

    def test_custom_max_reading_cps_threshold_is_honored(self, tmp_path: Path):
        # 10 characters in 1 second = 10 chars/sec: in sync under a generous
        # cap, out of sync under a strict one.
        line = _line(1, 0.0, 1.0, "x" * 10)
        subtitle_file = SubtitleFile(source_video=_video(tmp_path), lines=[line])
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file, max_reading_cps=20.0) == 1.0
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file, max_reading_cps=5.0) == 0.0

    def test_empty_text_line_is_trivially_in_sync(self, tmp_path: Path):
        line = _line(1, 0.0, 0.0, "")
        subtitle_file = SubtitleFile(source_video=_video(tmp_path), lines=[line])
        assert benchmark.subtitle_timing_sync_ratio(subtitle_file) == 1.0


# ---------------------------------------------------------------------------
# load_corpus
# ---------------------------------------------------------------------------


class TestLoadCorpus:
    def test_loads_inline_reference_text(self, tmp_path: Path):
        (tmp_path / "video1.mp4").write_bytes(b"")
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "video1.mp4", "reference_text": "hello world"}]),
            encoding="utf-8",
        )

        entries = benchmark.load_corpus(manifest)

        assert len(entries) == 1
        assert entries[0].video_path == tmp_path / "video1.mp4"
        assert entries[0].reference_text == "hello world"
        assert entries[0].label == "video1.mp4"

    def test_loads_reference_text_from_file_relative_to_manifest(self, tmp_path: Path):
        (tmp_path / "video1.mp4").write_bytes(b"")
        (tmp_path / "video1.txt").write_text("reference from file", encoding="utf-8")
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "video1.mp4", "reference_text_path": "video1.txt"}]),
            encoding="utf-8",
        )

        entries = benchmark.load_corpus(manifest)

        assert entries[0].reference_text == "reference from file"

    def test_honors_explicit_label(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps(
                [{"video": "video1.mp4", "reference_text": "hi", "label": "Sample One"}]
            ),
            encoding="utf-8",
        )

        entries = benchmark.load_corpus(manifest)

        assert entries[0].label == "Sample One"

    def test_absolute_video_path_is_not_rejoined_to_manifest_dir(self, tmp_path: Path):
        absolute_video = tmp_path / "elsewhere" / "video1.mp4"
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": str(absolute_video), "reference_text": "hi"}]),
            encoding="utf-8",
        )

        entries = benchmark.load_corpus(manifest)

        assert entries[0].video_path == absolute_video

    def test_non_list_manifest_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

        with pytest.raises(ValueError, match="must be a JSON list"):
            benchmark.load_corpus(manifest)

    def test_entry_missing_video_key_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(json.dumps([{"reference_text": "hi"}]), encoding="utf-8")

        with pytest.raises(ValueError, match="missing the required 'video' key"):
            benchmark.load_corpus(manifest)

    def test_entry_missing_reference_text_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(json.dumps([{"video": "video1.mp4"}]), encoding="utf-8")

        with pytest.raises(ValueError, match="reference_text"):
            benchmark.load_corpus(manifest)

    def test_non_string_video_value_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": 123, "reference_text": "hi"}]), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="'video' value that isn't a string"):
            benchmark.load_corpus(manifest)

    def test_non_string_reference_text_value_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "video1.mp4", "reference_text": ["not", "a", "string"]}]),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="'reference_text' value that isn't a string"):
            benchmark.load_corpus(manifest)

    def test_non_string_reference_text_path_value_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "video1.mp4", "reference_text_path": 42}]),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="'reference_text_path' value that isn't a string"):
            benchmark.load_corpus(manifest)

    def test_non_string_label_value_raises_value_error(self, tmp_path: Path):
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps(
                [{"video": "video1.mp4", "reference_text": "hi", "label": {"nested": True}}]
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="'label' value that isn't a string"):
            benchmark.load_corpus(manifest)


# ---------------------------------------------------------------------------
# time_transcription
# ---------------------------------------------------------------------------


class TestTimeTranscription:
    def test_runs_pipeline_and_reports_duration_and_elapsed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path, duration_seconds=120.0)
        subtitle_file = SubtitleFile(source_video=video, output_path=tmp_path / "out.srt")
        captured_kwargs: dict = {}

        def _fake_run_pipeline(**kwargs):
            captured_kwargs.update(kwargs)
            return subtitle_file

        monkeypatch.setattr(benchmark, "run_pipeline", _fake_run_pipeline)

        result = benchmark.time_transcription(
            video.path, output_path=tmp_path / "out.srt", model_size="tiny"
        )

        assert captured_kwargs["video_path"] == video.path
        assert captured_kwargs["output_path"] == tmp_path / "out.srt"
        assert captured_kwargs["model_size"] == "tiny"
        assert result.video_duration_seconds == 120.0
        assert result.elapsed_seconds >= 0.0
        assert result.model_size == "tiny"

    def test_default_output_path_matches_cli_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        captured_kwargs: dict = {}

        def _fake_run_pipeline(**kwargs):
            captured_kwargs.update(kwargs)
            return SubtitleFile(source_video=video)

        monkeypatch.setattr(benchmark, "run_pipeline", _fake_run_pipeline)

        benchmark.time_transcription(video.path)

        assert captured_kwargs["output_path"] == video.path.with_suffix(".srt")

    def test_realtime_ratio_is_elapsed_over_duration(self, tmp_path: Path):
        result = benchmark.TimingResult(
            video_path=tmp_path / "v.mp4",
            output_path=tmp_path / "v.srt",
            model_size="base",
            video_duration_seconds=100.0,
            elapsed_seconds=25.0,
        )
        assert result.realtime_ratio == pytest.approx(0.25)

    def test_realtime_ratio_is_nan_for_zero_duration(self, tmp_path: Path):
        result = benchmark.TimingResult(
            video_path=tmp_path / "v.mp4",
            output_path=tmp_path / "v.srt",
            model_size="base",
            video_duration_seconds=0.0,
            elapsed_seconds=1.0,
        )
        assert result.realtime_ratio != result.realtime_ratio  # nan


class TestScSc006Note:
    def test_within_target_when_elapsed_is_half_duration_or_less(self):
        note = benchmark.sc002_sc006_note(duration_seconds=600.0, elapsed_seconds=290.0)
        assert "within target" in note

    def test_outside_target_when_elapsed_exceeds_half_duration(self):
        note = benchmark.sc002_sc006_note(duration_seconds=600.0, elapsed_seconds=400.0)
        assert "OUTSIDE target" in note

    def test_unknown_duration_is_reported_as_unevaluated(self):
        note = benchmark.sc002_sc006_note(duration_seconds=float("nan"), elapsed_seconds=10.0)
        assert "could not be evaluated" in note


# ---------------------------------------------------------------------------
# sc003_note / sc004_note (T028)
# ---------------------------------------------------------------------------


class TestSc003Note:
    def test_meets_target_at_exactly_the_threshold(self):
        note = benchmark.sc003_note(0.90)
        assert "SC-003" in note
        assert "meets target" in note

    def test_meets_target_above_the_threshold(self):
        note = benchmark.sc003_note(0.95)
        assert "meets target" in note

    def test_misses_target_below_the_threshold(self):
        note = benchmark.sc003_note(0.89)
        assert "MISSES target" in note

    def test_custom_min_accuracy_is_honored(self):
        assert "meets target" in benchmark.sc003_note(0.80, min_accuracy=0.75)
        assert "MISSES target" in benchmark.sc003_note(0.80, min_accuracy=0.85)

    def test_nan_accuracy_is_reported_as_unevaluated(self):
        note = benchmark.sc003_note(float("nan"))
        assert "could not be evaluated" in note


class TestSc004Note:
    def test_meets_target_at_exactly_the_threshold(self):
        note = benchmark.sc004_note(0.95)
        assert "SC-004" in note
        assert "meets target" in note

    def test_misses_target_below_the_threshold(self):
        note = benchmark.sc004_note(0.94)
        assert "MISSES target" in note

    def test_custom_min_sync_ratio_is_honored(self):
        assert "meets target" in benchmark.sc004_note(0.80, min_sync_ratio=0.75)
        assert "MISSES target" in benchmark.sc004_note(0.80, min_sync_ratio=0.85)

    def test_nan_sync_ratio_is_reported_as_unevaluated(self):
        note = benchmark.sc004_note(float("nan"))
        assert "could not be evaluated" in note


# ---------------------------------------------------------------------------
# run_corpus_benchmark
# ---------------------------------------------------------------------------


class TestRunCorpusBenchmark:
    def test_scores_each_entry_and_aggregates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video_a = _video(tmp_path / "a")
        video_b = _video(tmp_path / "b")
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()

        entries = [
            benchmark.CorpusEntry(
                label="a", video_path=tmp_path / "a" / "a.mp4", reference_text="hello world"
            ),
            benchmark.CorpusEntry(
                label="b", video_path=tmp_path / "b" / "b.mp4", reference_text="goodbye moon"
            ),
        ]

        outputs = {
            entries[0].video_path: SubtitleFile(
                source_video=video_a,
                lines=[_line(1, 0.0, 5.0, "hello world")],
            ),
            entries[1].video_path: SubtitleFile(
                source_video=video_b,
                # Wrong text (full WER) but well-timed (in sync).
                lines=[_line(1, 0.0, 5.0, "totally different")],
            ),
        }

        def _fake_run_pipeline(*, video_path, output_path, model_size, stream=None):
            return outputs[Path(video_path)]

        monkeypatch.setattr(benchmark, "run_pipeline", _fake_run_pipeline)

        result = benchmark.run_corpus_benchmark(entries)

        assert len(result.entries) == 2
        assert result.entries[0].label == "a"
        assert result.entries[0].accuracy == 1.0
        assert result.entries[1].accuracy == 0.0
        # Unweighted average across the two entries.
        assert result.overall_accuracy == pytest.approx(0.5)
        # Both lines were well-timed -> full sync ratio pooled across the corpus.
        assert result.overall_sync_ratio == 1.0

    def test_empty_corpus_reports_nan_accuracy_and_full_sync(self):
        result = benchmark.run_corpus_benchmark([])
        assert result.entries == []
        assert result.overall_accuracy != result.overall_accuracy  # nan
        assert result.overall_sync_ratio == 1.0

    def test_writes_each_entry_to_its_own_temp_output_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        entries = [
            benchmark.CorpusEntry(
                label="only", video_path=tmp_path / "only.mp4", reference_text="hi"
            )
        ]
        seen_output_paths: list[Path] = []

        def _fake_run_pipeline(*, video_path, output_path, model_size, stream=None):
            seen_output_paths.append(Path(output_path))
            assert not Path(output_path).parent.samefile(tmp_path)
            return SubtitleFile(source_video=video, lines=[])

        monkeypatch.setattr(benchmark, "run_pipeline", _fake_run_pipeline)

        benchmark.run_corpus_benchmark(entries)

        assert len(seen_output_paths) == 1
        assert seen_output_paths[0].suffix == ".srt"

    def test_propagates_domain_errors_from_run_pipeline(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        from lib.errors import ModelLoadError

        entries = [
            benchmark.CorpusEntry(
                label="broken", video_path=tmp_path / "broken.mp4", reference_text="hi"
            )
        ]

        def _raise(**kwargs):
            raise ModelLoadError("tiny", reason="boom")

        monkeypatch.setattr(benchmark, "run_pipeline", _raise)

        with pytest.raises(ModelLoadError):
            benchmark.run_corpus_benchmark(entries)


# ---------------------------------------------------------------------------
# CLI (`main`)
# ---------------------------------------------------------------------------


class TestMainCli:
    def test_time_subcommand_prints_report_and_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        video = _video(tmp_path, duration_seconds=60.0)
        subtitle_file = SubtitleFile(source_video=video, output_path=tmp_path / "clip.srt")
        monkeypatch.setattr(benchmark, "run_pipeline", lambda **kwargs: subtitle_file)

        exit_code = benchmark.main(["time", str(video.path)])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Video duration: 60.0s" in out
        assert "SC-002/SC-006 target" in out

    def test_corpus_subcommand_prints_report_and_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        video = _video(tmp_path)
        (tmp_path / "clip.mp4").write_bytes(b"")
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "clip.mp4", "reference_text": "hello world"}]),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            benchmark,
            "run_pipeline",
            lambda **kwargs: SubtitleFile(
                source_video=video, lines=[_line(1, 0.0, 5.0, "hello world")]
            ),
        )

        exit_code = benchmark.main(["corpus", str(manifest)])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Overall transcript accuracy: 100.0%" in out
        assert "Overall subtitle timing-sync: 100.0%" in out
        assert "SC-003 target" in out
        assert "SC-004 target" in out
        assert "meets target" in out

    def test_whisperflow_error_is_reported_as_single_stderr_line_with_exit_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        from lib.errors import UnsupportedVideoFormatError

        def _raise(**kwargs):
            raise UnsupportedVideoFormatError(tmp_path / "bad.mp4", detected_format="avi")

        monkeypatch.setattr(benchmark, "run_pipeline", _raise)

        exit_code = benchmark.main(["time", str(tmp_path / "bad.mp4")])

        assert exit_code == 1
        err = capsys.readouterr().err
        assert err.strip().startswith("Error: ")

    def test_missing_manifest_file_is_reported_with_exit_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        exit_code = benchmark.main(["corpus", str(tmp_path / "does-not-exist.json")])

        assert exit_code == 1
        err = capsys.readouterr().err
        assert "Error:" in err

    def test_no_subcommand_exits_nonzero_via_argparse(self):
        with pytest.raises(SystemExit):
            benchmark.main([])

    def test_corpus_strict_returns_zero_when_targets_are_met(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        video = _video(tmp_path)
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "clip.mp4", "reference_text": "hello world"}]),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            benchmark,
            "run_pipeline",
            lambda **kwargs: SubtitleFile(
                source_video=video, lines=[_line(1, 0.0, 5.0, "hello world")]
            ),
        )

        exit_code = benchmark.main(["corpus", str(manifest), "--strict"])

        assert exit_code == 0

    def test_corpus_strict_returns_nonzero_when_accuracy_target_is_missed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        video = _video(tmp_path)
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "clip.mp4", "reference_text": "hello world"}]),
            encoding="utf-8",
        )
        # Completely wrong hypothesis -> 0% accuracy, well below any threshold.
        monkeypatch.setattr(
            benchmark,
            "run_pipeline",
            lambda **kwargs: SubtitleFile(
                source_video=video, lines=[_line(1, 0.0, 5.0, "totally different text")]
            ),
        )

        exit_code = benchmark.main(["corpus", str(manifest), "--strict"])

        assert exit_code == 2
        out = capsys.readouterr().out
        assert "MISSES target" in out

    def test_corpus_without_strict_returns_zero_even_when_targets_are_missed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        video = _video(tmp_path)
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "clip.mp4", "reference_text": "hello world"}]),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            benchmark,
            "run_pipeline",
            lambda **kwargs: SubtitleFile(
                source_video=video, lines=[_line(1, 0.0, 5.0, "totally different text")]
            ),
        )

        exit_code = benchmark.main(["corpus", str(manifest)])

        assert exit_code == 0

    def test_corpus_custom_min_accuracy_and_min_sync_ratio_are_honored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        video = _video(tmp_path)
        manifest = tmp_path / "corpus.json"
        manifest.write_text(
            json.dumps([{"video": "clip.mp4", "reference_text": "hello world"}]),
            encoding="utf-8",
        )
        # 1 substitution out of 2 reference words -> 50% accuracy.
        monkeypatch.setattr(
            benchmark,
            "run_pipeline",
            lambda **kwargs: SubtitleFile(
                source_video=video, lines=[_line(1, 0.0, 5.0, "hello there")]
            ),
        )

        exit_code = benchmark.main(
            ["corpus", str(manifest), "--strict", "--min-accuracy", "0.4"]
        )

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "meets target" in out


# ---------------------------------------------------------------------------
# _print_corpus_report (T028)
# ---------------------------------------------------------------------------


class TestPrintCorpusReport:
    def test_returns_true_when_both_targets_met(self):
        import io

        result = benchmark.CorpusBenchmarkResult(
            entries=[
                benchmark.CorpusEntryResult(
                    label="a", accuracy=1.0, sync_ratio=1.0, line_count=1, in_sync_count=1
                )
            ]
        )
        out = io.StringIO()
        assert benchmark._print_corpus_report(result, out) is True

    def test_returns_false_when_accuracy_target_missed(self):
        import io

        result = benchmark.CorpusBenchmarkResult(
            entries=[
                benchmark.CorpusEntryResult(
                    label="a", accuracy=0.5, sync_ratio=1.0, line_count=1, in_sync_count=1
                )
            ]
        )
        out = io.StringIO()
        assert benchmark._print_corpus_report(result, out) is False

    def test_returns_false_for_empty_corpus_even_though_ratios_are_vacuous(self):
        import io

        result = benchmark.CorpusBenchmarkResult(entries=[])
        out = io.StringIO()
        # overall_accuracy is nan for an empty corpus -- never counted as "met".
        assert benchmark._print_corpus_report(result, out) is False
