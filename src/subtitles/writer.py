"""Transcript -> SubtitleFile conversion and `.srt` writing (T012).

Converts an already-produced `Transcript` (T011,
`src/transcription/transcribe.py`) into a `SubtitleFile` (T005,
`src/subtitles/models.py`) by mapping each `TranscriptSegment` 1:1 onto a
freshly generated `SubtitleLine` (data-model.md — SubtitleLine: "Initially
derived 1:1 from a TranscriptSegment"), then composing and writing it out
as `.srt` (spec FR-003, FR-006).

An empty `Transcript.segments` list (FR-008's "no detectable speech" case)
converts to a `SubtitleFile` with zero lines, which `SubtitleFile.compose()`
already renders as an empty string rather than an error (T005) -- so this
module needs no special case of its own for it. Surfacing that outcome to
the user as a clear stderr notice is the T013 pipeline's job, not this
module's.

`write_subtitle_file()` is the entry point most callers need: build the
`SubtitleFile` and write it to `output_path` in one call.
`build_subtitle_file()` is exposed separately for callers that need the
in-memory `SubtitleFile` before (or without) it being written -- e.g. User
Story 2's `--review` flow (T020), which writes a draft, lets the user edit
it, then re-reads and re-writes it with `edited` flags set.
"""

from __future__ import annotations

from pathlib import Path

from subtitles.models import SubtitleFile, SubtitleLine
from transcription.transcribe import Transcript


def build_subtitle_file(transcript: Transcript, output_path: Path | str) -> SubtitleFile:
    """Convert `transcript` into an initial, not-yet-written `SubtitleFile`.

    Each `TranscriptSegment` becomes one `SubtitleLine`, in the same order,
    with a 1-based `index` matching its position in `transcript.segments`
    (data-model.md — SubtitleLine.index: "1-based line number in the .srt
    file"). No line splitting/merging happens here -- v1's subtitle lines
    are exactly the ASR engine's own segment boundaries (spec FR-003).

    Args:
        transcript: An already-produced `Transcript` (T011). An empty
            `segments` list is valid (FR-008) and produces a `SubtitleFile`
            with an empty `lines` list.
        output_path: Where the returned `SubtitleFile` will be written if
            `.write()` is later called on it with no explicit path.

    Returns:
        A `SubtitleFile` referencing `transcript.source_video`, with
        `format="srt"` (data-model.md's only supported v1 format) and
        `lines` derived 1:1 from `transcript.segments`.
    """
    lines = [
        SubtitleLine(
            index=index,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=segment.text,
        )
        for index, segment in enumerate(transcript.segments, start=1)
    ]
    return SubtitleFile(
        source_video=transcript.source_video,
        lines=lines,
        output_path=Path(output_path),
    )


def write_subtitle_file(transcript: Transcript, output_path: Path | str) -> SubtitleFile:
    """Build a `SubtitleFile` from `transcript` and write it to `output_path`.

    Args:
        transcript: An already-produced `Transcript` (T011).
        output_path: Where to write the composed `.srt` text (spec FR-006).
            Parent directories are created as needed (`SubtitleFile.write`).

    Returns:
        The written `SubtitleFile`, ready for User Story 2's optional
        review step (FR-009, FR-010) to read back and re-write with edits.
    """
    subtitle_file = build_subtitle_file(transcript, output_path)
    subtitle_file.write()
    return subtitle_file
