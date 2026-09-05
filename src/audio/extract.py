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

`ffmpeg` is always pointed at a fresh, auto-generated temp path (never at a
caller-supplied `output_path` directly) -- see `extract_audio()`'s
docstring for why: it avoids having to infer "did ffmpeg actually write
this?" from filesystem metadata, which a prior revision of this module
attempted (comparing size/mtime before and after the run) and which PR #85
review found could misclassify a genuine same-content retry as a no-op on
coarse-mtime-granularity filesystems (FAT32/exFAT's ~2s ticks).
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
            consumed it. If given, `ffmpeg` still writes to an internal
            temp file first; once that write is confirmed to have
            succeeded, the temp file is moved onto `output_path`,
            overwriting anything already there.

    Returns:
        An `AudioTrack` referencing `video`, the path the WAV file was
        written to, and the fixed `SAMPLE_RATE_HZ`.

    Raises:
        FfmpegNotFoundError: `ffmpeg` is not on `PATH` (contracts/cli.md).
        AudioExtractionError: `ffmpeg` ran but exited non-zero (e.g. a
            corrupt stream, or a video with no audio stream to extract),
            or exited zero without actually writing a non-empty output
            file.
    """
    if shutil.which(FFMPEG_EXECUTABLE) is None:
        raise FfmpegNotFoundError(FFMPEG_EXECUTABLE)

    # ffmpeg always writes to a fresh, auto-generated temp path -- never
    # directly to a caller-supplied output_path, even when one is given.
    # This is what lets "did ffmpeg actually write output?" be answered
    # structurally (does the temp file it exclusively owns exist and have
    # content?) instead of by comparing filesystem metadata of a path that
    # might have pre-existing content of its own. A prior revision wrote
    # straight to output_path and inferred success by snapshotting
    # size/mtime before and after the run; that broke on a genuine retry
    # against the same output_path, since ffmpeg is deterministic and a
    # fast re-run can produce a byte-identical file whose mtime quantizes
    # to the same tick as the stale one on coarse-granularity filesystems
    # (FAT32/exFAT's ~2s resolution), making a real success indistinguishable
    # from a no-op (PR #85 review).
    temp_output = _new_temp_wav_path()

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
                str(temp_output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # Race: shutil.which() found it, but it's gone (or unexecutable) by
        # the time subprocess actually tries to run it (mirrors T009's
        # identical guard around ffprobe). Don't leak the empty temp file
        # `_new_temp_wav_path()` created before we ever got here. The
        # caller's output_path (if any) was never touched, so there's
        # nothing to restore there.
        temp_output.unlink(missing_ok=True)
        raise FfmpegNotFoundError(FFMPEG_EXECUTABLE) from exc

    if result.returncode != 0:
        # Don't leak a partial/empty temp file for a run the caller never
        # gets a usable AudioTrack for. Same as above, output_path is
        # untouched.
        temp_output.unlink(missing_ok=True)
        raise AudioExtractionError(video.path, stderr=result.stderr)

    if not temp_output.exists() or temp_output.stat().st_size == 0:
        # Belt-and-braces: ffmpeg exited 0 but didn't actually write (a
        # non-empty) output file. Fail clearly here rather than moving a
        # missing/empty file onto output_path and pushing a confusing
        # failure downstream into transcription (FR-007). Because ffmpeg
        # only ever writes to temp_output, this check alone is sufficient
        # -- there is no pre-existing content at temp_output to confuse it
        # with, unlike when ffmpeg wrote directly to a caller-supplied path.
        temp_output.unlink(missing_ok=True)
        raise AudioExtractionError(
            video.path,
            stderr="ffmpeg exited successfully but produced no output audio file",
        )

    if output_path is None:
        resolved_output = temp_output
    else:
        # ffmpeg is confirmed to have succeeded and written non-empty
        # content to temp_output -- only now do we touch the caller's
        # path, replacing whatever (if anything) was already there.
        # shutil.move (rather than Path.replace/os.replace) handles the
        # temp directory and output_path living on different filesystems
        # or drives, and still overwrites an existing destination file on
        # every platform this project targets (it falls back to a
        # copy+unlink when a same-filesystem rename isn't possible or
        # would fail because the destination already exists).
        resolved_output = Path(output_path)
        shutil.move(str(temp_output), str(resolved_output))

    return AudioTrack(
        source_video=video,
        extracted_path=resolved_output,
        sample_rate_hz=SAMPLE_RATE_HZ,
    )


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
