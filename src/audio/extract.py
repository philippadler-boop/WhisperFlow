"""Audio extraction via `ffmpeg` subprocess (T010).

Implements data-model.md's `AudioTrack` entity by shelling out to an
`ffmpeg` binary (research.md's "Audio extraction" decision; ADR 0002) to
pull a mono, 16kHz WAV file out of a `Video` that video probing (T009,
`src/audio/video_probe.py`) has already validated -- container format
supported and duration within the 2-hour cap (spec FR-007). Because
probing already ran first, this module only needs to guard against two
failure modes of its own: the `ffmpeg` binary being missing from (or
present on but unable to be launched from) `PATH`, and `ffmpeg` itself
failing while it runs (e.g. a stream ffprobe could read but ffmpeg can't
decode, or a video with no audio stream to extract at all).

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
        FfmpegNotFoundError: `ffmpeg` is not on `PATH` (contracts/cli.md),
            including the race where `shutil.which()` found it but it's
            gone by the time `subprocess.run()` actually tries to launch
            it.
        AudioExtractionError: `ffmpeg` ran but exited non-zero (e.g. a
            corrupt stream, or a video with no audio stream to extract),
            or exited zero without actually writing a non-empty output
            file, or `ffmpeg` is on `PATH` but could not be launched for a
            reason other than being missing (e.g. `PermissionError` on a
            blocked/non-executable binary, or a corrupt/wrong-architecture
            binary), or (when `output_path` is given) the confirmed-good
            temp file could not be moved onto it (disk full, a
            permission/lock error, or an unrecoverable cross-device
            move) -- never a raw `OSError`/`shutil.Error` (PR #85
            review).
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
        # Race: shutil.which() found it, but it's gone by the time
        # subprocess actually tries to run it (mirrors T009's identical
        # guard around ffprobe). Don't leak the empty temp file
        # `_new_temp_wav_path()` created before we ever got here. The
        # caller's output_path (if any) was never touched, so there's
        # nothing to restore there.
        temp_output.unlink(missing_ok=True)
        raise FfmpegNotFoundError(FFMPEG_EXECUTABLE) from exc
    except OSError as exc:
        # Every other OSError subclass subprocess.run can raise for a
        # binary that IS present on PATH but can't actually be launched --
        # PermissionError (blocked/non-executable), NotADirectoryError (a
        # PATH component collision), or a corrupt/wrong-architecture binary
        # (surfaces as a plain OSError, e.g. "Exec format error"). Deliberately
        # *not* folded into FfmpegNotFoundError above: that error's message
        # ("install ffmpeg and ensure it is on PATH") would be actively
        # wrong here -- ffmpeg *is* on PATH, it just couldn't be started --
        # so this is reported as AudioExtractionError instead, same as any
        # other extraction failure (PR #85 review: this except clause was
        # previously narrowed to FileNotFoundError only, so every other
        # OSError subclass escaped raw, contradicting this function's own
        # documented "never a raw OSError" contract). Same cleanup as every
        # other failure exit: never leak temp_output.
        temp_output.unlink(missing_ok=True)
        raise AudioExtractionError(
            video.path,
            stderr=f"failed to run '{FFMPEG_EXECUTABLE}': {exc}",
        ) from exc

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
        resolved_output = Path(output_path)
        try:
            _finalize_output(temp_output, resolved_output)
        except OSError as exc:
            # PR #85 review: a failure here (disk full, a permission/lock
            # error, a genuinely cross-device move that even the fallback
            # below can't complete) must not leak a raw OSError/
            # shutil.Error -- that breaks this function's documented
            # Raises: contract -- and must not leave temp_output behind:
            # every other exit point in this function already cleans it
            # up, and this was the one path that didn't.
            temp_output.unlink(missing_ok=True)
            raise AudioExtractionError(
                video.path,
                stderr=f"failed to move extracted audio to '{resolved_output}': {exc}",
            ) from exc

    return AudioTrack(
        source_video=video,
        extracted_path=resolved_output,
        sample_rate_hz=SAMPLE_RATE_HZ,
    )


def _finalize_output(temp_output: Path, resolved_output: Path) -> None:
    """Move `temp_output` onto `resolved_output`, replacing it if present.

    Prefers `os.replace` over `shutil.move` (which `extract_audio` used
    previously). `shutil.move` attempts `os.rename` first, and `os.rename`
    *never* overwrites an existing destination on Windows -- so whenever
    `resolved_output` already exists, `shutil.move` unconditionally falls
    back to a `copy2`-based copy+unlink, even when both paths are on the
    same volume. That fallback's `copy2` opens `resolved_output` with
    `'wb'`, truncating it immediately, before any new bytes are written --
    if the copy is then interrupted (disk full, a permission/lock error),
    the caller's previously-good file is left corrupted/truncated rather
    than untouched (PR #85 review). `os.replace`, unlike `os.rename`,
    overwrites atomically on *both* platforms as long as source and
    destination share a filesystem, which is the overwhelmingly common
    case here -- so preferring it removes the truncation risk entirely for
    that case, with no fallback needed.

    Only falls back to a copy when `os.replace` raises `OSError` (e.g. a
    genuine cross-device/cross-drive move) -- and even then, copies into a
    *fresh* temp file created in `resolved_output`'s own directory (so it's
    guaranteed to share its filesystem), rather than opening
    `resolved_output` itself for writing. The concluding step is still an
    atomic same-filesystem `os.replace`, not a truncating in-place copy, so
    a pre-existing `resolved_output` is never at risk of being left
    partially overwritten. (Python's stdlib has no atomic *cross*-filesystem
    replace; a copy of some kind is unavoidable in that case. This narrows
    the truncation risk to "the fallback's own fresh staging file", which
    carries no data worth protecting, rather than the caller's file.)

    Consumes `temp_output` on success (it no longer exists afterwards,
    mirroring `shutil.move`'s contract). Never partially consumes it on
    failure -- raises with `temp_output` still present, left for the
    caller to clean up.
    """
    try:
        os.replace(temp_output, resolved_output)
        return
    except OSError:
        pass  # Fall through to the staged-copy fallback below.

    staged = _new_temp_wav_path(directory=resolved_output.parent)
    try:
        shutil.copy2(temp_output, staged)
        os.replace(staged, resolved_output)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    temp_output.unlink(missing_ok=True)


def _new_temp_wav_path(directory: Path | str | None = None) -> Path:
    """Create and return the path to a fresh, empty temporary `.wav` file.

    Uses `tempfile.mkstemp` (rather than `NamedTemporaryFile`) so the file
    is created but not held open -- `ffmpeg` (a separate process) needs to
    open and write it itself, which isn't possible while this process
    holds an exclusive handle on some platforms (notably Windows).

    Args:
        directory: If given, create the file inside this directory instead
            of the platform's default temp directory. Used by
            `_finalize_output`'s cross-filesystem fallback to stage a copy
            in the same directory as the final destination, guaranteeing
            the concluding `os.replace` is same-filesystem (and therefore
            atomic, and therefore non-truncating) even when the
            ffmpeg-owned temp file itself isn't.
    """
    fd, name = tempfile.mkstemp(suffix=".wav", prefix="whisperflow_", dir=directory)
    os.close(fd)
    return Path(name)
