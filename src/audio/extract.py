"""Audio extraction via `ffmpeg` subprocess (T010).

Implements data-model.md's `AudioTrack` entity by shelling out to an
`ffmpeg` binary (research.md's "Audio extraction" decision; ADR 0002) to
pull a mono, 16kHz WAV file out of a `Video` that video probing (T009,
`src/audio/video_probe.py`) has already validated -- container format
supported and duration within the 2-hour cap (spec FR-007). Because
probing already ran first, this module only needs to guard against two
failure modes of its own: the `ffmpeg` binary being missing from `PATH`,
and `ffmpeg` itself failing while it runs (e.g. a stream ffprobe could
read but ffmpeg can't decode, or a video with no audio stream to extract
at all).

The mono/16kHz shape is fixed, not configurable, because it matches
exactly what `faster-whisper`/CTranslate2 (ADR 0001) expects as input --
if that ASR engine choice ever changes, this module's output shape should
be re-reviewed alongside it (ADR 0002's Consequences).

`extract_audio()` is the single entry point: it runs `ffmpeg`, writes the
resulting WAV to a caller-supplied path or an auto-generated temporary
one, and returns an `AudioTrack`. It raises the shared `FfmpegNotFoundError`
(also raised by T009's probing) if the binary isn't on `PATH`, and the new
`AudioExtractionError` for any other `ffmpeg` failure, rather than letting
a raw `subprocess`/`OSError` leak to the caller.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from audio.video_probe import Video
from lib.errors import AudioExtractionError, FfmpegNotFoundError

#: The `ffmpeg` binary extraction shells out to (the sibling of T009's
#: `ffprobe`, from the same distribution; research.md's Audio extraction
#: decision covers both).
FFMPEG_EXECUTABLE = "ffmpeg"

#: Fixed output shape `faster-whisper`/CTranslate2 (ADR 0001) expects --
#: data-model.md: AudioTrack.sample_rate_hz is "Fixed at 16000 for the ASR
#: engine".
SAMPLE_RATE_HZ = 16000

#: Mono audio, per data-model.md ("The mono, 16kHz audio extracted from
#: Video").
AUDIO_CHANNELS = 1


@dataclass(frozen=True)
class AudioTrack:
    """The mono, 16kHz audio extracted from a `Video` (data-model.md — AudioTrack)."""

    source_video: Video
    extracted_path: Path
    sample_rate_hz: int = SAMPLE_RATE_HZ


def extract_audio(video: Video, output_path: Path | str | None = None) -> AudioTrack:
    """Extract `video`'s spoken audio to a mono, 16kHz WAV file.

    Args:
        video: An already-probed, already-validated `Video` (T009's
            `probe_video()`).
        output_path: Where to write the extracted WAV file. If `None`
            (the default), a fresh temporary `.wav` file is created and
            its path returned as `AudioTrack.extracted_path` --
            data-model.md describes this as a "Temporary WAV file,
            removed after the run", which the caller (the T013 pipeline)
            is responsible for cleaning up once transcription has
            consumed it.

    Returns:
        An `AudioTrack` referencing `video`, the path the WAV file was
        written to, and the fixed `SAMPLE_RATE_HZ`.

    Raises:
        FfmpegNotFoundError: `ffmpeg` is not on `PATH` (contracts/cli.md).
        AudioExtractionError: `ffmpeg` ran but exited non-zero (e.g. a
            corrupt stream, or a video with no audio stream to extract),
            or exited zero without actually writing a non-empty output
            file. This also covers a caller-supplied `output_path` that
            already existed (with content) before the call and that
            `ffmpeg` left untouched -- an existence/size check alone can't
            tell that apart from a genuine write, so the pre-call state of
            that path is snapshotted below and compared afterwards.
    """
    if shutil.which(FFMPEG_EXECUTABLE) is None:
        raise FfmpegNotFoundError(FFMPEG_EXECUTABLE)

    owns_output_file = output_path is None
    resolved_output = _new_temp_wav_path() if owns_output_file else Path(output_path)

    # Snapshot the output path's state *before* invoking ffmpeg. For an
    # owned (auto-generated) path this is always "exists, empty" --
    # `_new_temp_wav_path()` just created it via `mkstemp`. For a
    # caller-supplied path it may already exist with real content (the
    # caller reusing a path across calls, say), which is exactly the case
    # an exists()/size-only check after the fact can't distinguish from a
    # genuine ffmpeg write -- ffmpeg exiting 0 without touching a
    # pre-existing non-empty file would otherwise look identical to
    # success.
    pre_run_stat = resolved_output.stat() if resolved_output.exists() else None

    try:
        result = subprocess.run(
            [
                FFMPEG_EXECUTABLE,
                "-y",
                "-i",
                str(video.path),
                "-vn",
                "-ac",
                str(AUDIO_CHANNELS),
                "-ar",
                str(SAMPLE_RATE_HZ),
                "-f",
                "wav",
                str(resolved_output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # Race: shutil.which() found it, but it's gone (or unexecutable) by
        # the time subprocess actually tries to run it (mirrors T009's
        # identical guard around ffprobe). Don't leak the empty temp file
        # `_new_temp_wav_path()` created before we ever got here.
        _cleanup_owned_file(resolved_output, owns_output_file)
        raise FfmpegNotFoundError(FFMPEG_EXECUTABLE) from exc

    if result.returncode != 0:
        # Don't leak a partial/empty temp file for a run the caller never
        # gets a usable AudioTrack for.
        _cleanup_owned_file(resolved_output, owns_output_file)
        raise AudioExtractionError(video.path, stderr=result.stderr)

    post_run_stat = resolved_output.stat() if resolved_output.exists() else None

    if post_run_stat is None or post_run_stat.st_size == 0:
        # Belt-and-braces: ffmpeg exited 0 but didn't actually write (a
        # non-empty) output file. Fail clearly here rather than returning
        # an AudioTrack pointing at a missing/stale file and pushing a
        # confusing failure downstream into transcription (FR-007).
        _cleanup_owned_file(resolved_output, owns_output_file)
        raise AudioExtractionError(
            video.path,
            stderr="ffmpeg exited successfully but produced no output audio file",
        )

    if _looks_unmodified(pre_run_stat, post_run_stat):
        # ffmpeg exited 0 and *a* non-empty file sits at resolved_output --
        # but it's the same file (same size, same mtime) that was already
        # there before this call ran. That only happens for a
        # caller-supplied output_path pointing at a pre-existing,
        # non-empty file: an auto-generated path always starts out empty
        # (mkstemp), so any non-empty result there necessarily means
        # ffmpeg wrote it. Don't return an AudioTrack pointing at stale
        # bytes ffmpeg never touched.
        _cleanup_owned_file(resolved_output, owns_output_file)
        raise AudioExtractionError(
            video.path,
            stderr=(
                "ffmpeg exited successfully but did not modify the "
                "pre-existing output file"
            ),
        )

    return AudioTrack(
        source_video=video,
        extracted_path=resolved_output,
        sample_rate_hz=SAMPLE_RATE_HZ,
    )


def _looks_unmodified(pre_run_stat: os.stat_result | None, post_run_stat: os.stat_result) -> bool:
    """Whether `post_run_stat` shows no evidence ffmpeg actually wrote the file.

    Only meaningful when the path already existed (with content) before
    ffmpeg ran: `pre_run_stat` is `None` for a path that didn't exist yet,
    which is never "unmodified" -- any file appearing there is new.
    Compares both size and mtime (not size alone) since an ffmpeg run
    that rewrites a file with content of the same length would otherwise
    look untouched.
    """
    if pre_run_stat is None or pre_run_stat.st_size == 0:
        return False
    return (
        post_run_stat.st_size == pre_run_stat.st_size
        and post_run_stat.st_mtime_ns == pre_run_stat.st_mtime_ns
    )


def _cleanup_owned_file(path: Path, owns_file: bool) -> None:
    """Delete `path` if (and only if) this call created it itself.

    A caller-supplied `output_path` is the caller's own file to manage --
    extraction only ever deletes temp files it created via
    `_new_temp_wav_path()`, never a path the caller passed in.
    """
    if owns_file:
        path.unlink(missing_ok=True)


def _new_temp_wav_path() -> Path:
    """Create and return the path to a fresh, empty temporary `.wav` file.

    Uses `tempfile.mkstemp` (rather than `NamedTemporaryFile`) so the file
    is created but not held open -- `ffmpeg` (a separate process) needs to
    open and write it itself, which isn't possible while this process
    holds an exclusive handle on some platforms (notably Windows).
    """
    fd, name = tempfile.mkstemp(suffix=".wav", prefix="whisperflow_")
    os.close(fd)
    return Path(name)
