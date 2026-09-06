"""Unit tests for pipeline orchestration (T013, spec FR-008, FR-011).

Covers `run_pipeline()`'s happy path (probe -> extract -> transcribe ->
write, with per-stage stderr announcements and Transcribing-stage
percentage progress via T006), both flavors of FR-008's "no detectable
speech" case (an audio track that simply has no speech in it, and no
audio track at all), propagation of each stage's `WhisperFlowError`
subclasses (with a matching `Error: ...` stderr line and a `Failed` job),
cleanup of the pipeline's own temporary extracted-audio file, that the
returned `PipelineResult.reporter` lets a caller advance a successful run's
job to a terminal stage, and that an output-write `OSError` is translated
into `SubtitleWriteError` (reported and re-raised like any other failure,
with temp-audio cleanup still happening).

All of `probe_video`, `extract_audio`, and `transcribe_audio` are
monkeypatched at `cli.pipeline`'s own module level -- this module cares
about *orchestration*, not re-testing those units' own internals (already
covered by `tests/unit/test_video_probe.py`, `tests/unit/test_extract.py`,
`tests/unit/test_transcribe.py`).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

import cli.pipeline as pipeline_module
from audio.extract import AudioTrack
from audio.video_probe import Video
from cli.pipeline import PipelineResult, run_pipeline
from cli.progress import Stage
from lib.errors import (
    AudioExtractionError,
    FfmpegNotFoundError,
    ModelLoadError,
    SubtitleWriteError,
    TranscriptionError,
    UnsupportedVideoFormatError,
)
from transcription.transcribe import Transcript, TranscriptSegment


def _video(tmp_path: Path, *, has_audio_track: bool = True, duration: float = 10.0) -> Video:
    video_path = tmp_path / "clip.mp4"
    video_path.touch()
    return Video(
        path=video_path,
        container_format="mp4",
        duration_seconds=duration,
        has_audio_track=has_audio_track,
    )


def _patch_probe(monkeypatch: pytest.MonkeyPatch, video: Video) -> None:
    monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)


def _patch_extract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, video: Video) -> Path:
    wav_path = tmp_path / "extracted.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")

    def _extract(v):
        return AudioTrack(source_video=v, extracted_path=wav_path)

    monkeypatch.setattr(pipeline_module, "extract_audio", _extract)
    return wav_path


def _patch_transcribe(
    monkeypatch: pytest.MonkeyPatch,
    segments: list[TranscriptSegment],
    *,
    language: str = "en",
) -> None:
    def _transcribe(audio_track, *, model_size, on_segment=None):
        for segment in segments:
            if on_segment is not None:
                on_segment(segment)
        return Transcript(
            source_video=audio_track.source_video, language=language, segments=segments
        )

    monkeypatch.setattr(pipeline_module, "transcribe_audio", _transcribe)


class TestRunPipelineHappyPath:
    def test_returns_pipeline_result_with_written_subtitle_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(
            monkeypatch, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )
        output_path = tmp_path / "out.srt"

        result = run_pipeline(
            video.path, output_path, progress_stream=io.StringIO()
        )

        assert isinstance(result, PipelineResult)
        assert result.has_speech is True
        assert output_path.is_file()
        assert "hi" in output_path.read_text(encoding="utf-8")
        assert result.subtitle_file.output_path == output_path

    def test_announces_expected_stages_in_order(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(
            monkeypatch, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )
        stream = io.StringIO()

        run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        output = stream.getvalue()
        assert output.index("Extracting audio…") < output.index("Transcribing…")
        assert output.index("Transcribing…") < output.index("Writing subtitles…")

    def test_reports_transcribing_progress_via_on_segment(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path, duration=10.0)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(
            monkeypatch,
            [
                TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="half"),
            ],
        )
        stream = io.StringIO()

        run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "50.0%" in stream.getvalue()

    def test_passes_model_size_through_to_transcribe_audio(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        captured: dict[str, object] = {}

        def _transcribe(audio_track, *, model_size, on_segment=None):
            captured["model_size"] = model_size
            return Transcript(source_video=audio_track.source_video, language="en", segments=[])

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _transcribe)

        run_pipeline(
            video.path,
            tmp_path / "out.srt",
            model_size="small",
            progress_stream=io.StringIO(),
        )

        assert captured["model_size"] == "small"

    def test_cleans_up_temporary_extracted_audio_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        wav_path = _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(monkeypatch, [])

        run_pipeline(video.path, tmp_path / "out.srt", progress_stream=io.StringIO())

        assert not wav_path.exists()

    def test_returned_reporter_can_complete_the_job_to_a_terminal_stage(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        # run_pipeline() itself only ever takes the job as far as
        # WritingSubtitles (the --review/--no-review branching into
        # AwaitingReview/Done is T014/T021's call, not this module's) --
        # but the caller must actually be able to reach one of those
        # terminal stages using what run_pipeline() gives back, or every
        # successful run would leave its job stranded forever.
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(
            monkeypatch, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )

        result = run_pipeline(
            video.path, tmp_path / "out.srt", progress_stream=io.StringIO()
        )

        assert result.reporter.job.stage == Stage.WRITING_SUBTITLES
        assert result.reporter.job.is_terminal is False

        result.reporter.announce_stage(Stage.DONE)

        assert result.reporter.job.stage == Stage.DONE
        assert result.reporter.job.is_terminal is True


class TestRunPipelineNoSpeechDetected:
    def test_audio_track_with_zero_segments_is_a_successful_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path, has_audio_track=True)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(monkeypatch, [])
        output_path = tmp_path / "out.srt"
        stream = io.StringIO()

        result = run_pipeline(video.path, output_path, progress_stream=stream)

        assert result.has_speech is False
        assert output_path.is_file()
        assert output_path.read_text(encoding="utf-8") == ""
        assert "No speech detected" in stream.getvalue()

    def test_no_audio_track_at_all_skips_extraction_and_transcription(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path, has_audio_track=False)
        _patch_probe(monkeypatch, video)

        def _boom_extract(v):
            raise AssertionError("extract_audio should not be called when has_audio_track=False")

        def _boom_transcribe(*args, **kwargs):
            raise AssertionError(
                "transcribe_audio should not be called when has_audio_track=False"
            )

        monkeypatch.setattr(pipeline_module, "extract_audio", _boom_extract)
        monkeypatch.setattr(pipeline_module, "transcribe_audio", _boom_transcribe)
        output_path = tmp_path / "out.srt"
        stream = io.StringIO()

        result = run_pipeline(video.path, output_path, progress_stream=stream)

        assert result.has_speech is False
        assert output_path.read_text(encoding="utf-8") == ""
        assert "No speech detected" in stream.getvalue()

    def test_no_speech_case_still_exits_successfully_not_via_report_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path, has_audio_track=False)
        _patch_probe(monkeypatch, video)
        stream = io.StringIO()

        run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" not in stream.getvalue()


class TestRunPipelineFailureModes:
    def test_unsupported_format_reports_failure_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video_path = tmp_path / "clip.avi"
        video_path.touch()

        def _probe(path):
            raise UnsupportedVideoFormatError(path, detected_format="avi")

        monkeypatch.setattr(pipeline_module, "probe_video", _probe)
        stream = io.StringIO()

        with pytest.raises(UnsupportedVideoFormatError):
            run_pipeline(video_path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" in stream.getvalue()
        assert "unsupported video format" in stream.getvalue()

    def test_ffmpeg_not_found_during_extraction_reports_failure_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)

        def _extract(v):
            raise FfmpegNotFoundError("ffmpeg")

        monkeypatch.setattr(pipeline_module, "extract_audio", _extract)
        stream = io.StringIO()

        with pytest.raises(FfmpegNotFoundError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" in stream.getvalue()

    def test_audio_extraction_error_reports_failure_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)

        def _extract(v):
            raise AudioExtractionError(video.path, stderr="boom")

        monkeypatch.setattr(pipeline_module, "extract_audio", _extract)
        stream = io.StringIO()

        with pytest.raises(AudioExtractionError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" in stream.getvalue()

    def test_model_load_error_reports_failure_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)

        def _transcribe(audio_track, *, model_size, on_segment=None):
            raise ModelLoadError(model_size, reason="corrupt cache")

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _transcribe)
        stream = io.StringIO()

        with pytest.raises(ModelLoadError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" in stream.getvalue()

    def test_transcription_error_reports_failure_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)

        def _transcribe(audio_track, *, model_size, on_segment=None):
            raise TranscriptionError(audio_track.extracted_path, reason="decode failed")

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _transcribe)
        stream = io.StringIO()

        with pytest.raises(TranscriptionError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" in stream.getvalue()

    def test_no_output_file_left_behind_when_probing_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        def _probe(path):
            raise UnsupportedVideoFormatError(path, detected_format="avi")

        monkeypatch.setattr(pipeline_module, "probe_video", _probe)
        output_path = tmp_path / "out.srt"

        with pytest.raises(UnsupportedVideoFormatError):
            run_pipeline(
                tmp_path / "clip.avi", output_path, progress_stream=io.StringIO()
            )

        assert not output_path.exists()

    def test_cleans_up_temporary_extracted_audio_file_on_transcription_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        wav_path = _patch_extract(monkeypatch, tmp_path, video)

        def _transcribe(audio_track, *, model_size, on_segment=None):
            raise TranscriptionError(audio_track.extracted_path, reason="decode failed")

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _transcribe)

        with pytest.raises(TranscriptionError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=io.StringIO())

        assert not wav_path.exists()

    def test_output_write_failure_is_reported_as_subtitle_write_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(
            monkeypatch, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )

        def _boom_write(transcript, output_path):
            raise PermissionError("Permission denied")

        monkeypatch.setattr(pipeline_module, "write_subtitles", _boom_write)
        stream = io.StringIO()

        with pytest.raises(SubtitleWriteError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=stream)

        assert "Error:" in stream.getvalue()
        assert "Permission denied" in stream.getvalue()

    def test_output_write_failure_still_cleans_up_temporary_extracted_audio_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        _patch_probe(monkeypatch, video)
        wav_path = _patch_extract(monkeypatch, tmp_path, video)
        _patch_transcribe(
            monkeypatch, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )

        def _boom_write(transcript, output_path):
            raise OSError("disk full")

        monkeypatch.setattr(pipeline_module, "write_subtitles", _boom_write)

        with pytest.raises(SubtitleWriteError):
            run_pipeline(video.path, tmp_path / "out.srt", progress_stream=io.StringIO())

        assert not wav_path.exists()
