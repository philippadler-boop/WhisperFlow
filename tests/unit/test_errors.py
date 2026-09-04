"""Unit tests for domain error types (T004, spec FR-007).

These test the error types in isolation: that each is a `WhisperFlowError`
(so a single `except WhisperFlowError` at the CLI boundary in T014 catches
all of them), that each produces a clear, human-readable message per
FR-007, and that useful attributes are exposed for callers that want the
raw values.
"""

from __future__ import annotations

import pytest

from lib.errors import (
    MAX_DURATION_SECONDS,
    SUPPORTED_VIDEO_FORMATS,
    FfmpegNotFoundError,
    MaxDurationExceededError,
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
        assert "/videos/clip.avi" in message
        for fmt in SUPPORTED_VIDEO_FORMATS:
            assert fmt in message

    def test_message_without_detected_format(self):
        err = UnsupportedVideoFormatError("/videos/mystery.bin")
        message = str(err)
        assert "/videos/mystery.bin" in message
        assert "mp4" in message

    def test_exposes_path_and_detected_format_attributes(self):
        err = UnsupportedVideoFormatError("/videos/clip.avi", detected_format="avi")
        assert str(err.path) == "/videos/clip.avi"
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
        assert "2:14:03" in message
        assert "2:00:00" in message

    def test_default_max_duration_is_two_hours(self):
        assert MAX_DURATION_SECONDS == 7200.0

    def test_exposes_duration_attributes(self):
        err = MaxDurationExceededError(duration_seconds=8000.0)
        assert err.duration_seconds == 8000.0
        assert err.max_duration_seconds == MAX_DURATION_SECONDS

    def test_custom_max_duration_is_respected(self):
        err = MaxDurationExceededError(duration_seconds=100.0, max_duration_seconds=60.0)
        assert err.max_duration_seconds == 60.0
        assert "0:01:00" in str(err)
        assert "0:01:40" in str(err)

    def test_rejects_duration_within_the_limit(self):
        with pytest.raises(ValueError):
            MaxDurationExceededError(duration_seconds=100.0, max_duration_seconds=7200.0)

    def test_raisable_and_catchable(self):
        with pytest.raises(MaxDurationExceededError):
            raise MaxDurationExceededError(duration_seconds=10000.0)


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


def test_all_domain_errors_are_catchable_via_common_base():
    errors = [
        UnsupportedVideoFormatError("clip.avi", detected_format="avi"),
        MaxDurationExceededError(duration_seconds=10000.0),
        FfmpegNotFoundError(),
    ]
    for error in errors:
        with pytest.raises(WhisperFlowError):
            raise error
