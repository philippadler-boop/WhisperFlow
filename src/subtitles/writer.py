"""Transcript -> `SubtitleFile` conversion and `.srt` file writing (T012).

Bridges T011's ASR output (`transcription.transcribe.Transcript`, an
ordered list of `TranscriptSegment`s) to T005's subtitle domain model
(`subtitles.models.SubtitleFile`/`SubtitleLine`), and writes the composed
result to disk -- the last step of User Story 1's pipeline before an
optional review (User Story 2). Concretely: FR-003 ("generate subtitles in
the same language as the video's spoken audio") is satisfied upstream by
T011 (no translation happens here, this module is purely a 1:1 structural
conversion), and FR-006 ("write the generated subtitles to a subtitle file
in a standard subtitle format") is satisfied by delegating composition and
writing to `SubtitleFile` itself.

`transcript_to_subtitle_file()` and `write_subtitles()` are the two entry
points:

- `transcript_to_subtitle_file()` builds the `SubtitleFile` in memory only
  (no disk I/O) -- useful for callers (or tests) that want to inspect or
  further edit the result before writing, e.g. User Story 2's review step,
  which writes the *draft* itself but needs to re-derive `SubtitleLine`
  identity/timings the same way.
- `write_subtitles()` does the same conversion and then writes it to
  `output_path` in one call, returning the written `SubtitleFile` --
  the entry point T013's pipeline orchestration uses.

A `Transcript` with an empty `segments` list (FR-008's "no detectable
speech" outcome, already validated as successful by T011) converts to a
`SubtitleFile` with an empty `lines` list, which `SubtitleFile.compose()`
already renders as an empty string rather than an error -- this module
adds no special-casing of its own for that outcome.
"""

from __future__ import annotations

from pathlib import Path

from subtitles.models import SubtitleFile, SubtitleLine
from transcription.transcribe import Transcript


def transcript_to_subtitle_file(
    transcript: Transcript,
    *,
    output_path: Path | str | None = None,
) -> SubtitleFile:
    """Convert `transcript` into a fresh, unwritten `SubtitleFile`.

    Each `TranscriptSegment` becomes exactly one `SubtitleLine`, in order,
    1-based-indexed by its position in `transcript.segments`
    (data-model.md: SubtitleLine "initially derived 1:1 from a
    TranscriptSegment"; SubtitleFile.lines "Ordered by index"). Every
    produced line has `edited=False` -- these are freshly generated lines,
    not yet subject to any User Story 2 review edit.

    Args:
        transcript: The time-coded ASR output to convert (T011).
        output_path: Recorded on the returned `SubtitleFile` as its
            `output_path` (data-model.md), but nothing is written to disk
            here -- see `write_subtitles()` for the write-through entry
            point.

    Returns:
        A `SubtitleFile` referencing `transcript.source_video`, with one
        `SubtitleLine` per `TranscriptSegment` (empty `lines` when
        `transcript.segments` is empty -- FR-008's valid "no detectable
        speech" outcome).
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
        output_path=Path(output_path) if output_path is not None else None,
    )


def write_subtitles(transcript: Transcript, output_path: Path | str) -> SubtitleFile:
    """Convert `transcript` to a `SubtitleFile` and write it to `output_path`.

    The single entry point T013's pipeline orchestration uses to turn a
    finished `Transcript` into the `.srt` file on disk (spec FR-006).

    Args:
        transcript: The time-coded ASR output to convert (T011).
        output_path: Where to write the composed `.srt` text. Parent
            directories are created as needed (`SubtitleFile.write`).

    Returns:
        The `SubtitleFile` that was written, with `output_path` set to the
        resolved `Path` it was written to -- callers don't need to track
        the path separately.
    """
    subtitle_file = transcript_to_subtitle_file(transcript, output_path=output_path)
    subtitle_file.write()
    return subtitle_file
