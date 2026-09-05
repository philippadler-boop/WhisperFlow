"""Video probing via `ffprobe` (T009).

Implements data-model.md's `Video` entity -- `container_format`,
`duration_seconds`, `has_audio_track` -- by shelling out to `ffprobe`,
which ships alongside the `ffmpeg` binary research.md's "Audio extraction"
decision already commits to using (T010 uses `ffmpeg` itself to extract
audio; this module uses its sibling `ffprobe` to inspect the container
first). Probing runs before extraction/transcription so FR-007's
format/duration validation happens up front, without paying for a full
audio decode first.

`probe_video()` is the single entry point: it runs `ffprobe`, resolves
`container_format`/`duration_seconds`/`has_audio_track`, and raises the
domain errors from `lib/errors.py` for every FR-007 failure mode
(unsupported/undetectable format, oversized video, missing `ffprobe`)
rather than letting a raw `subprocess`/JSON exception leak to the caller.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.errors import (
    MAX_DURATION_SECONDS,
    SUPPORTED_VIDEO_FORMATS,
    FfmpegNotFoundError,
    MaxDurationExceededError,
    UnsupportedVideoFormatError,
)

#: The `ffprobe` binary probing shells out to (part of the `ffmpeg`
#: distribution; research.md's Audio extraction decision covers both).
FFPROBE_EXECUTABLE = "ffprobe"

#: ffprobe's demuxer names (`format.format_name`, a comma-separated list of
#: short names ffprobe recognizes a container as) grouped by the
#: `SUPPORTED_VIDEO_FORMATS` token(s) they correspond to. ffprobe shares a
#: single demuxer between MP4 and QuickTime .mov files
#: (`"mov,mp4,m4a,3gp,3g2,mj2"`), so `format_name` alone can't distinguish
#: "mp4" from "mov" -- `_detect_container_format` resolves that ambiguity
#: using the input file's own extension (data-model.md: "Detected from the
#: file"), cross-checked against these tokens so a file with a
#: supported-looking extension but a container ffprobe doesn't actually
#: recognize as such is still rejected.
_FORMAT_NAME_TOKENS: dict[str, frozenset[str]] = {
    "mp4": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "mov": frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}),
    "mkv": frozenset({"matroska", "webm"}),
}


@dataclass(frozen=True)
class Video:
    """The user-supplied input media file (data-model.md -- Video)."""

    path: Path
    container_format: str
    duration_seconds: float
    has_audio_track: bool


def probe_video(path: Path | str) -> Video:
    """Probe `path` via `ffprobe` and return a validated `Video`.

    Applies data-model.md's Video validation rules before returning, so a
    caller only ever gets back a `Video` that's already known to be a
    supported, in-range input:

    Raises:
        FfmpegNotFoundError: `ffprobe` is not on `PATH` (contracts/cli.md).
        UnsupportedVideoFormatError: the file can't be probed at all, or
            its container format isn't one of `SUPPORTED_VIDEO_FORMATS`
            (spec FR-007; data-model.md Video validation rules).
        MaxDurationExceededError: the probed duration exceeds
            `MAX_DURATION_SECONDS` (spec FR-007; data-model.md Video
            validation rules).
    """
    video_path = Path(path)
    probe_data = _run_ffprobe(video_path)

    container_format = _detect_container_format(video_path, probe_data)
    if container_format is None or container_format not in SUPPORTED_VIDEO_FORMATS:
        raise UnsupportedVideoFormatError(video_path, detected_format=container_format)

    duration_seconds = _detect_duration_seconds(probe_data)
    if duration_seconds is None:
        # container_format is already validated at this point -- passing it
        # here would produce a self-contradictory "unsupported format 'mp4'"
        # message about a format that *is* supported. The real failure is an
        # undetectable duration field, not the container format.
        raise UnsupportedVideoFormatError(video_path, detected_format=None)
    if duration_seconds > MAX_DURATION_SECONDS:
        raise MaxDurationExceededError(duration_seconds)

    return Video(
        path=video_path,
        container_format=container_format,
        duration_seconds=duration_seconds,
        has_audio_track=_has_audio_stream(probe_data),
    )


def _run_ffprobe(video_path: Path) -> dict[str, Any]:
    """Run `ffprobe` against `video_path` and return its parsed JSON report.

    Any failure to get back a usable report (missing binary, non-zero exit,
    empty/unparseable output -- e.g. a non-media file) is treated as "not a
    supported video" (`UnsupportedVideoFormatError`) rather than crashing,
    per FR-007.
    """
    if shutil.which(FFPROBE_EXECUTABLE) is None:
        raise FfmpegNotFoundError(FFPROBE_EXECUTABLE)

    try:
        result = subprocess.run(
            [
                FFPROBE_EXECUTABLE,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # Race: shutil.which() found it, but it's gone (or unexecutable) by
        # the time subprocess actually tries to run it.
        raise FfmpegNotFoundError(FFPROBE_EXECUTABLE) from exc

    if result.returncode != 0 or not result.stdout.strip():
        raise UnsupportedVideoFormatError(video_path)

    try:
        probe_data: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UnsupportedVideoFormatError(video_path) from exc

    return probe_data


def _detect_container_format(video_path: Path, probe_data: dict[str, Any]) -> str | None:
    """Resolve one of `SUPPORTED_VIDEO_FORMATS`, or `None`/other if not one.

    ffprobe's own `format_name` tokens are the source of truth for *whether*
    the file is one of the supported container families (data-model.md:
    "Detected from the file") -- the file's extension is only used to
    disambiguate *which* supported format it is when ffprobe's tokens are
    ambiguous between more than one (e.g. MP4 vs QuickTime .mov share a
    single demuxer, `"mov,mp4,m4a,3gp,3g2,mj2"`). A file extension that
    disagrees with what ffprobe actually detected never overrides that
    detection -- e.g. an AVI file renamed to `.mp4` is still reported (and
    rejected) as AVI, not silently accepted as MP4.

    The same shared demuxers also cover *unsupported* sibling formats
    (`.webm` alongside `.mkv`'s matroska demuxer; `.m4a`/`.3gp`/`.3g2`/
    `.mj2` alongside `.mp4`/`.mov`'s demuxer) that ffprobe's tokens alone
    can't distinguish from a genuinely supported one. When the extension
    identifies one of those unsupported siblings, it is never guessed into
    a supported label -- see the `family_tokens` check below.

    Returns ffprobe's own best guess at the real format (its `format_name`
    tokens' first entry, or the file extension as a last resort) when it
    doesn't match any supported family, so callers can still report *what*
    was actually detected in an error message.
    """
    format_name = probe_data.get("format", {}).get("format_name", "")
    tokens = {token.strip().lower() for token in format_name.split(",") if token.strip()}

    matched_supported = {
        supported_format
        for supported_format, known_tokens in _FORMAT_NAME_TOKENS.items()
        if tokens & known_tokens
    }
    if matched_supported:
        extension = video_path.suffix.lower().lstrip(".")
        if extension in matched_supported:
            return extension
        family_tokens: set[str] = set().union(
            *(_FORMAT_NAME_TOKENS[supported_format] for supported_format in matched_supported)
        )
        if extension in family_tokens:
            # The extension identifies a specific sibling within this
            # shared demuxer family that ffprobe's own tokens can't tell
            # apart from a supported one -- e.g. a real .webm file reports
            # the same "matroska,webm" format_name as a real .mkv file, and
            # a real .m4a/.3gp/.3g2/.mj2 file reports the same tokens as
            # mp4/mov. That sibling isn't itself one of
            # SUPPORTED_VIDEO_FORMATS, so return it as-is rather than
            # guessing a supported label -- it's expected to fail the
            # caller's SUPPORTED_VIDEO_FORMATS check.
            return extension
        if len(matched_supported) == 1:
            # No extension-based signal either way (the extension is
            # unrelated to this family entirely, e.g. a real .mkv file
            # renamed to .mp4) -- trust ffprobe's own token detection,
            # since it unambiguously identifies exactly one supported
            # family (data-model.md: container_format is "detected from
            # the file", not the extension).
            return next(iter(matched_supported))
        # Genuinely ambiguous within a shared demuxer (e.g. mp4 vs mov) and
        # the extension gives no signal to resolve it either way -- don't
        # guess. The extension is still surfaced for the caller's error
        # message, but only if it can't itself be mistaken for a *different*
        # supported format -- e.g. a file named "clip.mkv" whose real
        # container is mp4/mov-family (format_name
        # "mov,mp4,m4a,3gp,3g2,mj2") must not come back as "mkv" here, since
        # that would pass the caller's `in SUPPORTED_VIDEO_FORMATS` check
        # despite ffprobe never reporting anything matroska-related.
        return extension if extension and extension not in SUPPORTED_VIDEO_FORMATS else None

    primary_token = format_name.split(",")[0].strip().lower()
    if primary_token:
        # A genuine (if unrecognized) ffprobe token, e.g. "avi" -- safe to
        # return as-is for the caller's error message: since it didn't
        # intersect any _FORMAT_NAME_TOKENS family above, it can't collide
        # with a SUPPORTED_VIDEO_FORMATS value (every token that maps to one
        # is enumerated there).
        return primary_token

    # format_name was missing or empty -- ffprobe gave zero corroboration,
    # genuine or otherwise, about the container. Falling back to the file
    # extension here unconditionally would repeat the exact defect class
    # just fixed above (an ambiguous/absent ffprobe signal letting the
    # extension alone confer a SUPPORTED_VIDEO_FORMATS value, e.g. a
    # `clip.mp4` with unreadable/empty format_name being silently accepted
    # as "mp4"). Use the same guard as the ambiguous-match branch: the
    # extension may still be surfaced as an informative label for the
    # rejection message, but never when doing so would let it pass the
    # caller's `in SUPPORTED_VIDEO_FORMATS` check on its own.
    extension = video_path.suffix.lower().lstrip(".")
    return extension if extension and extension not in SUPPORTED_VIDEO_FORMATS else None


def _detect_duration_seconds(probe_data: dict[str, Any]) -> float | None:
    """Extract `format.duration` as a float, or `None` if missing/invalid."""
    raw_duration = probe_data.get("format", {}).get("duration")
    if raw_duration is None:
        return None
    try:
        return float(raw_duration)
    except (TypeError, ValueError):
        return None


def _has_audio_stream(probe_data: dict[str, Any]) -> bool:
    """True if `probe_data` reports at least one audio stream.

    This reflects the container's own stream table -- whether an audio
    track exists at all -- not whether it carries detectable speech.
    Distinguishing "silent/no-speech audio" from "no audio track" is
    FR-008's job downstream once transcription runs (data-model.md: `False`
    here "triggers the FR-008 'no detectable speech' report" only in the
    stronger case where there's no audio track to even attempt
    transcribing).
    """
    return any(stream.get("codec_type") == "audio" for stream in probe_data.get("streams", []))
