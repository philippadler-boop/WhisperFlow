"""Integration tests for the T025 benchmark helper (`scripts/benchmark.py`).

Unlike `tests/unit/test_benchmark.py` (which monkeypatches `run_pipeline`
entirely), these tests exercise the real `transcribe` pipeline end to end --
real `ffmpeg` audio extraction, a real `faster-whisper` "tiny" model run --
against `tests/fixtures/clear_speech.mp4`, the same fixture and known-ground
-truth transcript `tests/integration/test_transcribe_basic.py` (T015) already
established (see `docs/validation/T011.md`: a single segment, 0.000-3.200s,
text "Hello, this is a test on the whisper flow sub-title generator."). This
is the genuine, no-mocks path the benchmark script is meant for -- a smoke
test that it actually drives real transcription, not just that its pure
scoring math is correct.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark  # noqa: E402

# Known ground truth for tests/fixtures/clear_speech.mp4 (docs/validation/T011.md).
_KNOWN_REFERENCE_TEXT = "Hello, this is a test on the whisper flow sub-title generator."


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")


class TestTimeTranscriptionRealFixture:
    def test_times_a_real_transcription_run_and_reports_duration(
        self, clear_speech_video: Path, tmp_path: Path
    ) -> None:
        _require_ffmpeg()
        video_path = tmp_path / "clear_speech.mp4"
        shutil.copyfile(clear_speech_video, video_path)

        result = benchmark.time_transcription(video_path, model_size="tiny")

        assert result.output_path == video_path.with_suffix(".srt")
        assert result.output_path.is_file()
        assert result.elapsed_seconds > 0.0
        # The fixture's known duration is ~3.2s of audio, plus a little
        # trailing silence -- a few seconds either way, well above zero.
        assert result.video_duration_seconds > 0.0
        assert result.realtime_ratio > 0.0


class TestRunCorpusBenchmarkRealFixture:
    def test_scores_real_transcription_against_known_reference_text(
        self, clear_speech_video: Path, tmp_path: Path
    ) -> None:
        _require_ffmpeg()
        video_path = tmp_path / "clear_speech.mp4"
        shutil.copyfile(clear_speech_video, video_path)

        entries = [
            benchmark.CorpusEntry(
                label="clear_speech",
                video_path=video_path,
                reference_text=_KNOWN_REFERENCE_TEXT,
            )
        ]

        result = benchmark.run_corpus_benchmark(entries, model_size="tiny")

        assert len(result.entries) == 1
        entry_result = result.entries[0]
        # The tiny model's exact lexical output can vary by platform/runtime
        # (see test_transcribe_basic.py's own comment on this fixture), so
        # this doesn't require a perfect WER match -- just a high-accuracy
        # transcription of a short, clearly-spoken sentence, well above
        # chance and consistent with SC-003's 90% anchor.
        assert entry_result.accuracy >= 0.7, (
            f"expected high accuracy against known reference text, got "
            f"{entry_result.accuracy:.1%}"
        )
        assert entry_result.line_count >= 1
        # A single ~3.2s line of normal-length spoken text is well within
        # any plausible reading speed -- expect it scored fully in sync.
        assert entry_result.sync_ratio == 1.0
        assert result.overall_accuracy == entry_result.accuracy
        assert result.overall_sync_ratio == 1.0

    def test_load_corpus_and_run_corpus_benchmark_from_a_real_manifest_file(
        self, clear_speech_video: Path, tmp_path: Path
    ) -> None:
        _require_ffmpeg()
        video_path = tmp_path / "clear_speech.mp4"
        shutil.copyfile(clear_speech_video, video_path)
        manifest_path = tmp_path / "corpus.json"
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "video": "clear_speech.mp4",
                        "reference_text": _KNOWN_REFERENCE_TEXT,
                        "label": "clear_speech",
                    }
                ]
            ),
            encoding="utf-8",
        )

        entries = benchmark.load_corpus(manifest_path)
        result = benchmark.run_corpus_benchmark(entries, model_size="tiny")

        assert result.entries[0].label == "clear_speech"
        assert result.overall_accuracy >= 0.7


class TestMainCliRealFixture:
    def test_time_subcommand_end_to_end(
        self, clear_speech_video: Path, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _require_ffmpeg()
        video_path = tmp_path / "clear_speech.mp4"
        shutil.copyfile(clear_speech_video, video_path)

        exit_code = benchmark.main(["time", str(video_path), "--model", "tiny"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Elapsed:" in out
        assert "SC-002/SC-006 target" in out
        assert video_path.with_suffix(".srt").is_file()
