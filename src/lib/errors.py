"""Domain error types for WhisperFlow (spec FR-007; data-model.md validation rules).

FR-007 requires the system to "clearly report an error, rather than
silently failing" for an unsupported input format or an over-length video;
contracts/cli.md additionally requires a missing `ffmpeg` binary to be
reported the same way (exit code 1, a single human-readable line on
stderr). These three exception types are the shared vocabulary later
tasks (T009 video probing, T010 audio extraction, T014 CLI wiring) raise
and catch so that expected, user-facing failures are handled uniformly and
distinctly from unexpected bugs.

Each type's `str(err)` is a complete, human-readable message suitable for
printing directly as `Error: {err}` -- callers should not need to build
their own message from the exception's attributes, though the attributes
are exposed for callers that want the raw values (e.g. for logging).
"""

from __future__ import annotations

from pathlib import Path

#: Supported input video container formats (spec.md Assumptions).
SUPPORTED_VIDEO_FORMATS: tuple[str, ...] = ("mp4", "mov", "mkv")

#: Maximum supported video length in seconds (2 hours; spec Clarifications,
#: data-model.md Video validation rules).
MAX_DURATION_SECONDS: float = 7200.0


def _format_hms(total_seconds: float) -> str:
    """Format a duration in seconds as ``H:MM:SS``.

    Matches the style of contracts/cli.md's example error message for the
    *actual/offending* duration (``got 2:14:03``). Negative input is
    clamped to zero.
    """
    total_seconds = max(0, int(round(total_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _format_duration_human(total_seconds: float) -> str:
    """Format a duration in seconds as a rounded, human-friendly phrase.

    Matches the style of contracts/cli.md's example error message for the
    *configured maximum* duration (``maximum supported length of 2
    hours``) -- unlike `_format_hms`, whole-hour values are rendered as a
    plain "N hour(s)" phrase rather than ``2:00:00``.

    The contract's own example only ever shows a whole-hour maximum, but a
    future config could set a non-whole-hour max (e.g. 90 minutes), so
    non-whole-hour values are decomposed into hours/minutes/seconds and
    only the non-zero components are joined (e.g. "1 hour 30 minutes",
    "45 seconds") to keep the phrasing natural rather than falling back to
    `H:MM:SS`. Negative input is clamped to zero.
    """
    total_seconds = max(0, int(round(total_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    def _pluralize(value: int, unit: str) -> str:
        return f"{value} {unit}{'' if value == 1 else 's'}"

    parts = [
        _pluralize(value, unit)
        for value, unit in ((hours, "hour"), (minutes, "minute"), (seconds, "second"))
        if value
    ]
    return " ".join(parts) if parts else "0 seconds"


class WhisperFlowError(Exception):
    """Base class for domain errors that map to CLI exit code 1.

    `src/cli/main.py` (T014) catches this type at the top level to print a
    single ``Error: ...`` line to stderr and exit non-zero, per
    contracts/cli.md, rather than letting the traceback of an unrelated bug
    leak to the user.
    """


class UnsupportedVideoFormatError(WhisperFlowError):
    """The input file is not a supported video container format (FR-007).

    Raised by video probing (T009) when the input file's container format
    cannot be determined, or is determined but is not one of
    `SUPPORTED_VIDEO_FORMATS` (spec.md Assumptions: e.g. MP4, MOV, MKV).
    """

    def __init__(self, path: str | Path, detected_format: str | None = None) -> None:
        self.path = Path(path)
        self.detected_format = detected_format
        supported = ", ".join(SUPPORTED_VIDEO_FORMATS)
        if detected_format:
            message = (
                f"unsupported video format '{detected_format}' for "
                f"'{self.path}' (supported formats: {supported})"
            )
        else:
            message = (
                f"could not determine a supported video format for "
                f"'{self.path}' (supported formats: {supported})"
            )
        super().__init__(message)


class MaxDurationExceededError(WhisperFlowError):
    """The input video exceeds the maximum supported length (FR-007).

    Raised by video probing (T009) when `duration_seconds` is greater than
    `MAX_DURATION_SECONDS` (2 hours; data-model.md Video validation rules).
    """

    def __init__(
        self,
        duration_seconds: float,
        max_duration_seconds: float = MAX_DURATION_SECONDS,
    ) -> None:
        if duration_seconds <= max_duration_seconds:
            raise ValueError(
                "MaxDurationExceededError requires duration_seconds > "
                "max_duration_seconds "
                f"(got duration_seconds={duration_seconds!r}, "
                f"max_duration_seconds={max_duration_seconds!r})"
            )
        self.duration_seconds = duration_seconds
        self.max_duration_seconds = max_duration_seconds
        message = (
            "video exceeds maximum supported length of "
            f"{_format_duration_human(max_duration_seconds)} "
            f"(got {_format_hms(duration_seconds)})"
        )
        super().__init__(message)


class AudioExtractionError(WhisperFlowError):
    """`ffmpeg` ran but failed to extract audio from the input video.

    Raised by audio extraction (T010, `src/audio/extract.py`) when the
    `ffmpeg` binary itself exits non-zero while demuxing/re-encoding a
    video that video probing (T009) already accepted as a supported
    container -- e.g. a corrupt/truncated stream, or a video with no
    audio stream at all to extract. Distinct from `FfmpegNotFoundError`
    (the binary itself is missing from `PATH`) and from
    `UnsupportedVideoFormatError` (the container format itself is
    rejected up front by probing, before extraction is ever attempted).
    Maps to CLI exit code 1 per contracts/cli.md's "ASR model failed to
    load"-adjacent fatal-error bucket.
    """

    def __init__(self, path: str | Path, stderr: str = "") -> None:
        self.path = Path(path)
        self.stderr = stderr.strip()
        # ffmpeg's stderr is typically many lines of build/codec banner
        # noise followed by the actual failure reason on the last
        # non-empty line -- surface just that line rather than dumping the
        # whole banner into a single-line CLI error message.
        detail_line = self.stderr.splitlines()[-1] if self.stderr else ""
        detail = f": {detail_line}" if detail_line else ""
        message = f"failed to extract audio from '{self.path}'{detail}"
        super().__init__(message)


class FfmpegNotFoundError(WhisperFlowError):
    """The required `ffmpeg` binary was not found on `PATH` (contracts/cli.md).

    Raised by audio extraction/probing (T009, T010) before shelling out to
    `ffmpeg`, so the failure is reported as a clear domain error rather
    than a raw `FileNotFoundError` from `subprocess`.
    """

    def __init__(self, executable: str = "ffmpeg") -> None:
        self.executable = executable
        message = (
            f"required '{executable}' binary was not found on PATH "
            "(install ffmpeg and ensure it is on PATH)"
        )
        super().__init__(message)
