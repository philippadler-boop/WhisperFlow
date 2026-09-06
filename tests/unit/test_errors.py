"""Unit tests for domain error types (T004, spec FR-007).

These test the error types in isolation: that each is a `WhisperFlowError`
(so a single `except WhisperFlowError` at the CLI boundary in T014 catches
all of them), that each produces a clear, human-readable message per
FR-007, and that useful attributes are exposed for callers that want the
raw values.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.errors import (
    MAX_DURATION_SECONDS,
    SUPPORTED_VIDEO_FORMATS,
    AudioExtractionError,
    FfmpegNotFoundError,
    MaxDurationExceededError,
    ModelLoadError,
    SubtitleWriteError,
    TranscriptionError,
    UnsupportedVideoFormatError,
    WhisperFlowError,
)


class TestWhisperFlowError:
    def test_is_an_exception(self):
        assert issubclass(WhisperFlowError, Exception)


class TestUnsupportedVideoFormatError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(UnsupportedVideoFormatError, WhisperFlowError)

    def test_message_includes_path_and_detected_format(self):
        err = UnsupportedVideoFormatError("/videos/clip.avi", detected_format="avi")
        message = str(err)
        assert "avi" in message
        # Compare via Path/str(Path(...)) rather than a literal "/"-separated
        # string, since pathlib normalizes separators to "\\" in str() on
        # Windows.
        assert str(Path("/videos/clip.avi")) in message
        for fmt in SUPPORTED_VIDEO_FORMATS:
            assert fmt in message

    def test_message_without_detected_format(self):
        err = UnsupportedVideoFormatError("/videos/mystery.bin")
        message = str(err)
        assert str(Path("/videos/mystery.bin")) in message
        assert "mp4" in message

    def test_exposes_path_and_detected_format_attributes(self):
        err = UnsupportedVideoFormatError("/videos/clip.avi", detected_format="avi")
        # Compare as Path objects (not strings) so this passes regardless of
        # the platform's path separator -- pathlib normalizes "/" to "\\" in
        # str() on Windows, which a literal string comparison wouldn't survive.
        assert err.path == Path("/videos/clip.avi")
        assert err.detected_format == "avi"

    def test_raisable_and_catchable(self):
        with pytest.raises(UnsupportedVideoFormatError):
            raise UnsupportedVideoFormatError("clip.avi", detected_format="avi")


class TestMaxDurationExceededError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(MaxDurationExceededError, WhisperFlowError)

    def test_message_reports_max_and_actual_duration(self):
        # 2:14:03 = 2 * 3600 + 14 * 60 + 3
        err = MaxDurationExceededError(duration_seconds=2 * 3600 + 14 * 60 + 3)
        message = str(err)
        # Actual/offending duration is precise H:MM:SS...
        assert "2:14:03" in message
        # ...but the configured maximum is a rounded human phrase, per
        # contracts/cli.md's example ("maximum supported length of 2 hours").
        assert "2 hours" in message
        assert "2:00:00" not in message

    def test_message_matches_contract_example_exactly(self):
        # Pins contracts/cli.md's literal example end-to-end so a future
        # change to either formatter can't silently drift from the contract:
        # "video exceeds maximum supported length of 2 hours (got 2:14:03)"
        err = MaxDurationExceededError(duration_seconds=2 * 3600 + 14 * 60 + 3)
        assert str(err) == (
            "video exceeds maximum supported length of 2 hours (got 2:14:03)"
        )

    def test_default_max_duration_is_two_hours(self):
        assert MAX_DURATION_SECONDS == 7200.0

    def test_exposes_duration_attributes(self):
        err = MaxDurationExceededError(duration_seconds=8000.0)
        assert err.duration_seconds == 8000.0
        assert err.max_duration_seconds == MAX_DURATION_SECONDS

    def test_custom_max_duration_is_respected(self):
        err = MaxDurationExceededError(duration_seconds=100.0, max_duration_seconds=60.0)
        assert err.max_duration_seconds == 60.0
        # Max duration (60s = 1 minute, not a whole hour) still renders as a
        # human phrase, not H:MM:SS.
        assert "1 minute" in str(err)
        # Actual/offending duration stays precise H:MM:SS.
        assert "0:01:40" in str(err)

    def test_custom_max_duration_handles_non_whole_hours(self):
        # A hypothetical 90-minute max should read naturally, not fall back
        # to H:MM:SS just because it isn't a whole number of hours.
        err = MaxDurationExceededError(duration_seconds=6000.0, max_duration_seconds=5400.0)
        assert "1 hour 30 minutes" in str(err)

    def test_rejects_duration_within_the_limit(self):
        with pytest.raises(ValueError):
            MaxDurationExceededError(duration_seconds=100.0, max_duration_seconds=7200.0)

    def test_raisable_and_catchable(self):
        with pytest.raises(MaxDurationExceededError):
            raise MaxDurationExceededError(duration_seconds=10000.0)


class TestAudioExtractionError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(AudioExtractionError, WhisperFlowError)

    def test_message_includes_path_and_last_stderr_line(self):
        err = AudioExtractionError(
            "/videos/clip.mp4",
            stderr="ffmpeg version banner...\nmore banner\nUnknown encoder 'pcm'\n",
        )
        message = str(err)
        assert str(Path("/videos/clip.mp4")) in message
        assert "Unknown encoder 'pcm'" in message
        # Only the last (most relevant) stderr line is surfaced, not the
        # whole multi-line banner.
        assert "banner" not in message

    def test_message_without_stderr(self):
        err = AudioExtractionError("/videos/clip.mp4")
        message = str(err)
        assert str(Path("/videos/clip.mp4")) in message
        assert message == f"failed to extract audio from '{Path('/videos/clip.mp4')}'"

    def test_exposes_path_and_stderr_attributes(self):
        err = AudioExtractionError("/videos/clip.mp4", stderr="  boom  \n")
        assert err.path == Path("/videos/clip.mp4")
        assert err.stderr == "boom"

    def test_raisable_and_catchable(self):
        with pytest.raises(AudioExtractionError):
            raise AudioExtractionError("clip.mp4", stderr="boom")


class TestFfmpegNotFoundError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(FfmpegNotFoundError, WhisperFlowError)

    def test_message_mentions_ffmpeg_and_path(self):
        err = FfmpegNotFoundError()
        message = str(err)
        assert "ffmpeg" in message
        assert "PATH" in message

    def test_custom_executable_name_is_reflected(self):
        err = FfmpegNotFoundError(executable="ffprobe")
        assert err.executable == "ffprobe"
        assert "ffprobe" in str(err)

    def test_raisable_and_catchable(self):
        with pytest.raises(FfmpegNotFoundError):
            raise FfmpegNotFoundError()


class TestModelLoadError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(ModelLoadError, WhisperFlowError)

    def test_message_mentions_model_size(self):
        err = ModelLoadError("medium")
        assert "medium" in str(err)
        assert err.model_size == "medium"

    def test_message_includes_reason_when_given(self):
        err = ModelLoadError("small", reason="corrupt cache")
        assert "corrupt cache" in str(err)
        assert err.reason == "corrupt cache"

    def test_message_omits_reason_when_not_given(self):
        err = ModelLoadError("tiny")
        assert err.reason == ""
        assert str(err) == "failed to load ASR model 'tiny'"

    def test_raisable_and_catchable(self):
        with pytest.raises(ModelLoadError):
            raise ModelLoadError("base", reason="boom")


class TestTranscriptionError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(TranscriptionError, WhisperFlowError)

    def test_message_mentions_path(self):
        err = TranscriptionError("audio.wav")
        assert "audio.wav" in str(err)
        assert err.path == Path("audio.wav")

    def test_message_includes_reason_when_given(self):
        err = TranscriptionError("audio.wav", reason="decoder exploded")
        assert "decoder exploded" in str(err)
        assert err.reason == "decoder exploded"

    def test_raisable_and_catchable(self):
        with pytest.raises(TranscriptionError):
            raise TranscriptionError("audio.wav", reason="boom")


class TestSubtitleWriteError:
    def test_is_a_whisperflow_error(self):
        assert issubclass(SubtitleWriteError, WhisperFlowError)

    def test_message_mentions_path(self):
        err = SubtitleWriteError("/out/subs.srt")
        assert str(Path("/out/subs.srt")) in str(err)
        assert err.path == Path("/out/subs.srt")

    def test_message_includes_reason_when_given(self):
        err = SubtitleWriteError("/out/subs.srt", reason="Permission denied")
        assert "Permission denied" in str(err)
        assert err.reason == "Permission denied"

    def test_message_omits_reason_when_not_given(self):
        err = SubtitleWriteError("/out/subs.srt")
        assert err.reason == ""
        assert str(err) == f"failed to write subtitle file to '{Path('/out/subs.srt')}'"

    def test_raisable_and_catchable(self):
        with pytest.raises(SubtitleWriteError):
            raise SubtitleWriteError("subs.srt", reason="boom")


def test_all_domain_errors_are_catchable_via_common_base():
    errors = [
        UnsupportedVideoFormatError("clip.avi", detected_format="avi"),
        MaxDurationExceededError(duration_seconds=10000.0),
        FfmpegNotFoundError(),
        AudioExtractionError("clip.mp4", stderr="boom"),
        ModelLoadError("base", reason="boom"),
        TranscriptionError("audio.wav", reason="boom"),
        SubtitleWriteError("subs.srt", reason="boom"),
    ]
    for error in errors:
        with pytest.raises(WhisperFlowError):
            raise error
