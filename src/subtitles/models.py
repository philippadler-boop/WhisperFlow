"""Subtitle domain models and `.srt` composition (T005).

Defines `SubtitleLine` and `SubtitleFile` per data-model.md's
SubtitleLine/SubtitleFile entities (spec FR-006), and composes them to
`.srt`-formatted text via the `srt` library. Shared by User Story 1
(`src/subtitles/writer.py` builds a `SubtitleFile` fresh from a
`Transcript`) and User Story 2 (`src/cli/review.py` edits an existing
`SubtitleFile`'s line text) -- neither of those exist yet as of this task,
so this module has no dependency on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import srt


@dataclass
class SubtitleLine:
    """One caption line in the output `.srt` file (data-model.md).

    Initially derived 1:1 from a `TranscriptSegment` but independently
    editable: FR-010 allows a user edit to overwrite `text` only --
    timings are not user-editable in v1.
    """

    index: int
    start_seconds: float
    end_seconds: float
    text: str
    edited: bool = False

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError(f"SubtitleLine.index must be 1-based (>= 1), got {self.index}")
        if self.start_seconds < 0:
            raise ValueError(
                f"SubtitleLine.start_seconds must be >= 0, got {self.start_seconds}"
            )
        if self.end_seconds < self.start_seconds:
            raise ValueError(
                "SubtitleLine.end_seconds must be >= start_seconds "
                f"(start={self.start_seconds}, end={self.end_seconds})"
            )

    def to_srt_subtitle(self) -> srt.Subtitle:
        """Convert to the `srt` library's `Subtitle` type for composition."""
        return srt.Subtitle(
            index=self.index,
            start=timedelta(seconds=self.start_seconds),
            end=timedelta(seconds=self.end_seconds),
            content=self.text,
        )

    def with_text(self, text: str) -> SubtitleLine:
        """Return a copy with `text` replaced (FR-010).

        Sets `edited` when `text` actually differs from the current value,
        so review tooling (FR-009) can distinguish generated vs. corrected
        lines (data-model.md -- SubtitleLine.edited) without falsely
        flagging a line that was merely re-saved unchanged.
        """
        if text == self.text:
            return self
        return replace(self, text=text, edited=True)


@dataclass
class SubtitleFile:
    """The final output artifact: an ordered set of `SubtitleLine`s composed
    to a `.srt` file (data-model.md; spec FR-006).
    """

    source_video: Any = None
    format: str = "srt"
    lines: list[SubtitleLine] = field(default_factory=list)
    output_path: Path | None = None

    def __post_init__(self) -> None:
        if self.format != "srt":
            raise ValueError(f"SubtitleFile.format must be 'srt' in v1, got {self.format!r}")

    def compose(self) -> str:
        """Render `lines` to `.srt`-formatted text.

        An empty `lines` list (FR-008's "no detectable speech" case)
        composes to an empty string rather than an error -- that outcome
        is a valid, successful run (data-model.md -- Transcript validation
        rules), not a failure.

        Lines are composed in `lines` order using each line's own `index`
        (data-model.md: "Ordered by index"); indices are not
        auto-renumbered from start time, so an edited `SubtitleFile`
        (User Story 2) keeps the index it was generated with.
        """
        subtitles = (line.to_srt_subtitle() for line in self.lines)
        return srt.compose(subtitles, reindex=False)

    def write(self, path: Path | None = None) -> Path:
        """Compose `lines` and write the result to `output_path` (or `path`).

        Creates parent directories as needed. Returns the path written to.
        """
        target = Path(path) if path is not None else self.output_path
        if target is None:
            raise ValueError("SubtitleFile.write requires an output_path (none set)")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.compose(), encoding="utf-8")
        return target
