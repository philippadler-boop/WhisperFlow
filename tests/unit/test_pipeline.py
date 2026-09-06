"""Unit tests for pipeline orchestration (T013, spec FR-008, FR-011).

Covers `run_pipeline()`'s happy path (probe -> extract -> transcribe ->
write, each stage announced on stderr via T006's `ProgressReporter`), the
FR-008 "no detectable speech" stderr notice for an empty transcript,
temporary-audio-file cleanup, and that every domain error a stage raises
(`lib.errors.WhisperFlowError` and its subclasses) propagates unmodified
rather than being caught/reported here -- reporting is T014's job, once,
at the CLI's top level.

Each stage function (`probe_video`, `extract_audio`, `transcribe_audio`,
`write_subtitles`) is monkeypatched at its `cli.pipeline`-local name, the
same pattern `tests/unit/test_extract.py`/`test_transcribe.py` use for
their own single external seam (there, `subprocess.run`/`WhisperModel`).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

import cli.pipeline as pipeline_module
from audio.extract import AudioTrack
from audio.video_probe import Video
from lib.errors import (
    FfmpegNotFoundError,
    ModelLoadError,
    TranscriptionError,
    UnsupportedVideoFormatError,
)
from subtitles.models import SubtitleFile
from transcription.transcribe import Transcript, TranscriptSegment


def _video(tmp_path: Path, duration_seconds: float = 10.0) -> Video:
    return Video(
        path=tmp_path / "clip.mp4",
        container_format="mp4",
        duration_seconds=duration_seconds,
        has_audio_track=True,
    )


def _audio_track(tmp_path: Path, video: Video) -> AudioTrack:
    wav_path = tmp_path / "extracted.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")
    return AudioTrack(source_video=video, extracted_path=wav_path)


def _transcript(video: Video, segments: list[TranscriptSegment] | None = None) -> Transcript:
    return Transcript(source_video=video, language="en", segments=segments or [])


class TestRunPipelineHappyPath:
    def test_runs_all_stages_and_returns_written_subtitle_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)
        transcript = _transcript(
            video,
            [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="Hello")],
        )
        output_path = tmp_path / "out.srt"
        write_calls: list[tuple[Transcript, Path]] = []

        def _fake_write_subtitles(transcript_arg, output_path_arg):
            write_calls.append((transcript_arg, Path(output_path_arg)))
            subtitle_file = SubtitleFile(source_video=video, output_path=Path(output_path_arg))
            subtitle_file.write()
            return subtitle_file

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)
        monkeypatch.setattr(
            pipeline_module, "transcribe_audio", lambda track, **kwargs: transcript
        )
        monkeypatch.setattr(pipeline_module, "write_subtitles", _fake_write_subtitles)

        stream = io.StringIO()
        result = pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=output_path,
            model_size="base",
            stream=stream,
        )

        assert result.output_path == output_path
        assert write_calls == [(transcript, output_path)]
        output = stream.getvalue()
        assert "Extracting audio…" in output
        assert "Transcribing…" in output
        assert "Writing subtitles…" in output
        assert "Done." in output

    def test_reports_progress_via_on_segment_callback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path, duration_seconds=100.0)
        audio_track = _audio_track(tmp_path, video)
        segment = TranscriptSegment(start_seconds=0.0, end_seconds=50.0, text="Halfway")

        def _fake_transcribe_audio(track, *, model_size, on_segment=None):
            if on_segment is not None:
                on_segment(segment)
            return _transcript(video, [segment])

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)
        monkeypatch.setattr(pipeline_module, "transcribe_audio", _fake_transcribe_audio)
        monkeypatch.setattr(
            pipeline_module,
            "write_subtitles",
            lambda transcript, output_path: SubtitleFile(
                source_video=video, output_path=Path(output_path)
            ),
        )

        stream = io.StringIO()
        pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=tmp_path / "out.srt",
            model_size="base",
            stream=stream,
        )

        assert "50.0%" in stream.getvalue()

    def test_no_speech_detected_prints_clear_stderr_notice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)
        transcript = _transcript(video, segments=[])

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)
        monkeypatch.setattr(
            pipeline_module, "transcribe_audio", lambda track, **kwargs: transcript
        )
        monkeypatch.setattr(
            pipeline_module,
            "write_subtitles",
            lambda transcript_arg, output_path: SubtitleFile(
                source_video=video, output_path=Path(output_path)
            ),
        )

        stream = io.StringIO()
        pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=tmp_path / "out.srt",
            model_size="base",
            stream=stream,
        )

        assert pipeline_module.NO_SPEECH_DETECTED_MESSAGE in stream.getvalue()

    def test_no_speech_notice_absent_when_speech_detected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)
        transcript = _transcript(
            video, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="Hi")]
        )

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)
        monkeypatch.setattr(
            pipeline_module, "transcribe_audio", lambda track, **kwargs: transcript
        )
        monkeypatch.setattr(
            pipeline_module,
            "write_subtitles",
            lambda transcript_arg, output_path: SubtitleFile(
                source_video=video, output_path=Path(output_path)
            ),
        )

        stream = io.StringIO()
        pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=tmp_path / "out.srt",
            model_size="base",
            stream=stream,
        )

        assert pipeline_module.NO_SPEECH_DETECTED_MESSAGE not in stream.getvalue()

    def test_cleans_up_temporary_audio_file_after_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)
        transcript = _transcript(video, segments=[])

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)
        monkeypatch.setattr(
            pipeline_module, "transcribe_audio", lambda track, **kwargs: transcript
        )
        monkeypatch.setattr(
            pipeline_module,
            "write_subtitles",
            lambda transcript_arg, output_path: SubtitleFile(
                source_video=video, output_path=Path(output_path)
            ),
        )

        assert audio_track.extracted_path.exists()
        pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=tmp_path / "out.srt",
            model_size="base",
            stream=io.StringIO(),
        )

        assert not audio_track.extracted_path.exists()


class TestRunPipelinePropagatesDomainErrors:
    def test_unsupported_format_from_probing_propagates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _raise(path):
            raise UnsupportedVideoFormatError(path, detected_format="avi")

        monkeypatch.setattr(pipeline_module, "probe_video", _raise)

        with pytest.raises(UnsupportedVideoFormatError):
            pipeline_module.run_pipeline(
                video_path=tmp_path / "clip.avi",
                output_path=tmp_path / "out.srt",
                model_size="base",
                stream=io.StringIO(),
            )

    def test_missing_ffmpeg_from_extraction_propagates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)

        def _raise(v):
            raise FfmpegNotFoundError("ffmpeg")

        monkeypatch.setattr(pipeline_module, "extract_audio", _raise)

        with pytest.raises(FfmpegNotFoundError):
            pipeline_module.run_pipeline(
                video_path=video.path,
                output_path=tmp_path / "out.srt",
                model_size="base",
                stream=io.StringIO(),
            )

    def test_model_load_error_from_transcription_propagates_and_still_cleans_up(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)
        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)

        def _raise(track, **kwargs):
            raise ModelLoadError("base", reason="boom")

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _raise)

        with pytest.raises(ModelLoadError):
            pipeline_module.run_pipeline(
                video_path=video.path,
                output_path=tmp_path / "out.srt",
                model_size="base",
                stream=io.StringIO(),
            )

        assert not audio_track.extracted_path.exists()

    def test_transcription_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)
        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)

        def _raise(track, **kwargs):
            raise TranscriptionError(track.extracted_path, reason="boom")

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _raise)

        with pytest.raises(TranscriptionError):
            pipeline_module.run_pipeline(
                video_path=video.path,
                output_path=tmp_path / "out.srt",
                model_size="base",
                stream=io.StringIO(),
            )
