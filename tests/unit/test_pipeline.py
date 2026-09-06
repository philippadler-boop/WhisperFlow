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
    AudioExtractionError,
    FfmpegNotFoundError,
    ModelLoadError,
    TranscriptionError,
    UnsupportedVideoFormatError,
)
from subtitles.models import SubtitleFile
from transcription.transcribe import Transcript, TranscriptSegment


def _video(
    tmp_path: Path, duration_seconds: float = 10.0, has_audio_track: bool = True
) -> Video:
    return Video(
        path=tmp_path / "clip.mp4",
        container_format="mp4",
        duration_seconds=duration_seconds,
        has_audio_track=has_audio_track,
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


class TestRunPipelineNoAudioTrack:
    """FR-008's stronger case: `Video.has_audio_track is False`.

    Distinct from the "no detectable speech" tests above (which fake an
    empty transcript from a video that *does* have an audio track) --
    here there is no audio track at all, so `extract_audio()`/
    `transcribe_audio()` must never even be called: `extract_audio()` has
    nothing to map to its output for a video like this and would only
    ever raise `AudioExtractionError`, turning FR-008's documented
    successful outcome into a fatal, exit-code-1 error (P1 review).
    """

    def test_skips_extraction_and_transcription_and_exits_successfully(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path, has_audio_track=False)
        output_path = tmp_path / "out.srt"
        extract_calls: list[Video] = []
        transcribe_calls: list[object] = []

        def _fake_extract_audio(v):
            extract_calls.append(v)
            raise AssertionError("extract_audio must not be called when has_audio_track is False")

        def _fake_transcribe_audio(track, **kwargs):
            transcribe_calls.append(track)
            raise AssertionError(
                "transcribe_audio must not be called when has_audio_track is False"
            )

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", _fake_extract_audio)
        monkeypatch.setattr(pipeline_module, "transcribe_audio", _fake_transcribe_audio)

        stream = io.StringIO()
        result = pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=output_path,
            model_size="base",
            stream=stream,
        )

        assert extract_calls == []
        assert transcribe_calls == []
        assert result.output_path == output_path
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == ""
        output = stream.getvalue()
        assert pipeline_module.NO_SPEECH_DETECTED_MESSAGE in output
        assert "Done." in output
        # P2 review: the job silently advanced through ExtractingAudio and
        # Transcribing without announcing either -- a valid, no-audio-track
        # video must still announce every stage it passes through, same as
        # every other run, even though there is no actual work to do in them.
        assert "Extracting audio…" in output
        assert "Transcribing…" in output
        assert "Writing subtitles…" in output

    def test_no_audio_track_writes_empty_srt_regardless_of_writer_stub(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path, has_audio_track=False)
        write_calls: list[tuple[object, Path]] = []

        def _fake_write_subtitles(transcript_arg, output_path_arg):
            write_calls.append((transcript_arg, Path(output_path_arg)))
            subtitle_file = SubtitleFile(source_video=video, output_path=Path(output_path_arg))
            subtitle_file.write()
            return subtitle_file

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "write_subtitles", _fake_write_subtitles)

        result = pipeline_module.run_pipeline(
            video_path=video.path,
            output_path=tmp_path / "out.srt",
            model_size="base",
            stream=io.StringIO(),
        )

        assert len(write_calls) == 1
        transcript_arg, _ = write_calls[0]
        assert transcript_arg.segments == []
        assert result.output_path == tmp_path / "out.srt"


class TestRunPipelineCleanupFailure:
    """P2 review: temp-audio cleanup must be best-effort, never leaking a
    raw `OSError` or masking a more important exception already
    propagating.
    """

    def test_cleanup_failure_after_successful_transcription_raises_domain_error(
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
        write_called = False

        def _fake_write_subtitles(transcript_arg, output_path_arg):
            nonlocal write_called
            write_called = True
            return SubtitleFile(source_video=video, output_path=Path(output_path_arg))

        monkeypatch.setattr(pipeline_module, "write_subtitles", _fake_write_subtitles)

        def _raise_permission_error(self, missing_ok=False):
            raise PermissionError("[Errno 13] Permission denied")

        monkeypatch.setattr(Path, "unlink", _raise_permission_error)

        with pytest.raises(AudioExtractionError):
            pipeline_module.run_pipeline(
                video_path=video.path,
                output_path=tmp_path / "out.srt",
                model_size="base",
                stream=io.StringIO(),
            )

        # A cleanup failure after a fully successful transcription is this
        # run's *only* failure -- it must still be reported, not silently
        # swallowed -- but must not prevent the (already-successful) write
        # stage from having run.
        assert write_called is True

    def test_cleanup_failure_during_failed_transcription_does_not_mask_primary_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        video = _video(tmp_path)
        audio_track = _audio_track(tmp_path, video)

        monkeypatch.setattr(pipeline_module, "probe_video", lambda path: video)
        monkeypatch.setattr(pipeline_module, "extract_audio", lambda v: audio_track)

        def _raise_transcription_error(track, **kwargs):
            raise TranscriptionError(track.extracted_path, reason="boom")

        monkeypatch.setattr(pipeline_module, "transcribe_audio", _raise_transcription_error)

        def _raise_permission_error(self, missing_ok=False):
            raise PermissionError("[Errno 13] Permission denied")

        monkeypatch.setattr(Path, "unlink", _raise_permission_error)

        # The primary TranscriptionError must win -- a simultaneous cleanup
        # failure must not replace it with an AudioExtractionError/raw
        # PermissionError instead.
        with pytest.raises(TranscriptionError, match="boom"):
            pipeline_module.run_pipeline(
                video_path=video.path,
                output_path=tmp_path / "out.srt",
                model_size="base",
                stream=io.StringIO(),
            )

    def test_temp_audio_cleaned_up_when_write_subtitles_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """P2 review: `write_subtitles()` ran outside the temp-audio cleanup
        block entirely -- an unwritable output directory, a full disk, or
        any other writer failure left the extracted temporary WAV behind,
        violating `AudioTrack.extracted_path`'s "removed after the run"
        contract. Writing is now handled under the same unified cleanup as
        transcription: the temp file must still be removed, and the
        original writer exception must still be the one that propagates.
        """
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

        def _raise_os_error(transcript_arg, output_path_arg):
            raise OSError("[Errno 28] No space left on device")

        monkeypatch.setattr(pipeline_module, "write_subtitles", _raise_os_error)

        assert audio_track.extracted_path.exists()
        with pytest.raises(OSError, match="No space left on device"):
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
