"""`faster-whisper`-based transcription (T011).

Implements data-model.md's `Transcript`/`TranscriptSegment` entities by
running the already-extracted, mono/16kHz `AudioTrack` (T010,
`src/audio/extract.py`) through `faster-whisper` (ADR 0001; research.md's
"Local ASR engine" decision) -- CPU inference with int8 quantization by
default, a GPU used automatically when one is available (`device="auto"`).

`transcribe_audio()` is the single entry point: it loads the
`faster_whisper.WhisperModel` for the requested model size, runs it against
`AudioTrack.extracted_path`, and returns a `Transcript` -- the auto-detected
source language (spec FR-002: "the video's original (source) language") and
an ordered list of `TranscriptSegment`s. All transcription happens
in-process via this locally-loaded model; no video/audio content is ever
transmitted anywhere, satisfying FR-004 by construction (ADR 0001's
Consequences notes that only the one-time model *weight* download, not
per-video transcription traffic, touches the network).

A video with no detectable speech is not a special case here:
`faster-whisper` itself simply yields zero segments for silent/non-speech
audio, which `transcribe_audio()` returns as a `Transcript` with an empty
`segments` list -- a valid, successful outcome per data-model.md's
Transcript validation rules. Surfacing that to the user as a clear "no
speech detected" notice (FR-008) is the T013 pipeline's job, not this
module's.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from faster_whisper import WhisperModel

from audio.extract import AudioTrack
from audio.video_probe import Video
from lib.errors import ModelLoadError, TranscriptionError

#: Default `faster-whisper` model size (contracts/cli.md's `--model` default).
DEFAULT_MODEL_SIZE = "base"

#: `device="auto"` lets CTranslate2 pick a GPU automatically when one is
#: available; `compute_type="int8"` is the CPU-quantization default --
#: both per ADR 0001 / research.md's "Local ASR engine" decision.
DEVICE = "auto"
COMPUTE_TYPE = "int8"


class _TranscribingModel(Protocol):
    """The subset of `faster_whisper.WhisperModel`'s interface this module uses.

    Lets callers (and tests) inject a lightweight fake via
    `transcribe_audio(..., model=...)` without needing a real model
    download -- mirrors `src/audio/extract.py`'s pattern of isolating the
    one external call (there, `subprocess.run`; here, `WhisperModel.transcribe`)
    behind a narrow, mockable seam.
    """

    def transcribe(self, audio: str) -> tuple[Iterable[Any], Any]: ...


@dataclass(frozen=True)
class TranscriptSegment:
    """One ASR-produced unit of timed text (data-model.md -- TranscriptSegment)."""

    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class Transcript:
    """The full time-coded transcript of a `Video` (data-model.md -- Transcript)."""

    source_video: Video
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)


def transcribe_audio(
    audio_track: AudioTrack,
    *,
    model_size: str = DEFAULT_MODEL_SIZE,
    model: _TranscribingModel | None = None,
    on_segment: Callable[[TranscriptSegment], None] | None = None,
) -> Transcript:
    """Transcribe `audio_track` into a time-coded `Transcript`.

    Args:
        audio_track: An already-extracted mono/16kHz `AudioTrack` (T010).
        model_size: `faster-whisper` model size (contracts/cli.md's
            `--model`: tiny/base/small/medium/large). Ignored when `model`
            is given.
        model: A pre-constructed ASR engine (anything satisfying
            `_TranscribingModel`'s `.transcribe()` interface), for callers
            (and tests) that want to reuse or inject a model rather than
            having this function build one from `model_size`. When `None`
            (the default), a fresh `faster_whisper.WhisperModel` is built
            per ADR 0001 (CPU int8 by default, GPU auto-used when
            available).
        on_segment: Optional callback invoked once per `TranscriptSegment`,
            in order, as it's produced -- `faster-whisper` decodes and
            yields segments incrementally rather than all at once, so this
            lets a caller (T013's pipeline) drive FR-011 progress
            reporting without waiting for the whole video to finish.

    Returns:
        A `Transcript` referencing `audio_track.source_video`, the
        auto-detected source language (spec FR-002), and the ordered list
        of `TranscriptSegment`s -- an empty list is a valid, successful
        "no detectable speech" outcome (FR-008; data-model.md).

    Raises:
        ModelLoadError: `model` is `None` and constructing the
            `WhisperModel` for `model_size` failed (contracts/cli.md's
            "ASR model failed to load").
        TranscriptionError: the model loaded (or was given) but decoding
            `audio_track.extracted_path` failed, never a raw exception
            from the underlying library.
    """
    engine = model if model is not None else _load_model(model_size)

    try:
        raw_segments, info = engine.transcribe(str(audio_track.extracted_path))
    except Exception as exc:
        raise TranscriptionError(audio_track.extracted_path, reason=str(exc)) from exc

    segments: list[TranscriptSegment] = []
    try:
        for raw_segment in raw_segments:
            segment = TranscriptSegment(
                start_seconds=raw_segment.start,
                end_seconds=raw_segment.end,
                text=raw_segment.text.strip(),
            )
            segments.append(segment)
            if on_segment is not None:
                on_segment(segment)
    except Exception as exc:
        # A generator failing partway through iteration (e.g. an internal
        # CTranslate2 decoding error) is just as much a transcription
        # failure as engine.transcribe() itself raising synchronously
        # above -- must not leak a raw exception from the underlying
        # library either.
        raise TranscriptionError(audio_track.extracted_path, reason=str(exc)) from exc

    return Transcript(
        source_video=audio_track.source_video,
        language=info.language,
        segments=segments,
    )


def _load_model(model_size: str) -> WhisperModel:
    """Construct a `WhisperModel` for `model_size`, raising `ModelLoadError` on failure."""
    try:
        return WhisperModel(model_size, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception as exc:
        raise ModelLoadError(model_size, reason=str(exc)) from exc
