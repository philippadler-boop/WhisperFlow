"""Unit tests for T005 (`SubtitleLine`/`SubtitleFile` and `.srt` composition).

Covers data-model.md's SubtitleLine/SubtitleFile entities and FR-006 ("write
the generated subtitles to a subtitle file in a standard subtitle format").
"""

from __future__ import annotations

from pathlib import Path

import pytest
import srt

from subtitles.models import SubtitleFile, SubtitleLine


class TestSubtitleLine:
    def test_defaults_to_not_edited(self) -> None:
        line = SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.5, text="Hello")
        assert line.edited is False

    @pytest.mark.parametrize(
        ("index", "start", "end"),
        [
            (0, 0.0, 1.0),  # index must be 1-based
            (1, -1.0, 1.0),  # start must be >= 0
            (1, 2.0, 1.0),  # end must be >= start
        ],
    )
    def test_rejects_invalid_timings(self, index: int, start: float, end: float) -> None:
        with pytest.raises(ValueError):
            SubtitleLine(index=index, start_seconds=start, end_seconds=end, text="x")

    def test_to_srt_subtitle_round_trips_fields(self) -> None:
        line = SubtitleLine(index=3, start_seconds=1.0, end_seconds=2.5, text="Hi there")
        sub = line.to_srt_subtitle()
        assert isinstance(sub, srt.Subtitle)
        assert sub.index == 3
        assert sub.content == "Hi there"
        assert sub.start.total_seconds() == 1.0
        assert sub.end.total_seconds() == 2.5

    def test_with_text_sets_edited_flag_on_change(self) -> None:
        original = SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Generated")
        edited = original.with_text("Corrected")

        assert edited.text == "Corrected"
        assert edited.edited is True
        # Original is untouched (FR-010: edits produce a new value).
        assert original.text == "Generated"
        assert original.edited is False
        # Timings are not user-editable in v1 -- unchanged by the edit.
        assert edited.start_seconds == original.start_seconds
        assert edited.end_seconds == original.end_seconds

    def test_with_text_unchanged_does_not_set_edited(self) -> None:
        line = SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Same")
        result = line.with_text("Same")

        assert result.edited is False
        assert result is line  # re-saving unchanged text is a no-op


class TestSubtitleFile:
    def test_format_defaults_to_srt(self) -> None:
        subtitle_file = SubtitleFile()
        assert subtitle_file.format == "srt"

    def test_rejects_non_srt_format(self) -> None:
        with pytest.raises(ValueError):
            SubtitleFile(format="vtt")

    def test_compose_empty_lines_is_empty_string(self) -> None:
        # FR-008: "no detectable speech" is a valid, successful outcome,
        # not an error -- an empty SubtitleFile composes cleanly.
        subtitle_file = SubtitleFile(lines=[])
        assert subtitle_file.compose() == ""

    def test_compose_produces_valid_srt_text(self) -> None:
        lines = [
            SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="First line"),
            SubtitleLine(index=2, start_seconds=1.5, end_seconds=3.0, text="Second line"),
        ]
        subtitle_file = SubtitleFile(lines=lines)
        composed = subtitle_file.compose()

        assert "00:00:00,000 --> 00:00:01,000" in composed
        assert "First line" in composed
        assert "00:00:01,500 --> 00:00:03,000" in composed
        assert "Second line" in composed

        # Round-trips through the srt library's own parser.
        parsed = list(srt.parse(composed))
        assert [s.content for s in parsed] == ["First line", "Second line"]
        assert [s.index for s in parsed] == [1, 2]

    def test_compose_preserves_given_index_without_reindexing(self) -> None:
        # data-model.md: SubtitleFile.lines is "Ordered by index" -- an
        # edited file (User Story 2) should keep the indices it was
        # generated with rather than being silently renumbered.
        lines = [
            SubtitleLine(index=5, start_seconds=0.0, end_seconds=1.0, text="Only line"),
        ]
        subtitle_file = SubtitleFile(lines=lines)
        parsed = list(srt.parse(subtitle_file.compose()))
        assert parsed[0].index == 5

    def test_write_creates_parent_dirs_and_returns_path(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "out.srt"
        lines = [SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hello")]
        subtitle_file = SubtitleFile(lines=lines, output_path=target)

        result = subtitle_file.write()

        assert result == target
        assert target.is_file()
        assert "Hello" in target.read_text(encoding="utf-8")

    def test_write_without_output_path_raises(self) -> None:
        subtitle_file = SubtitleFile()
        with pytest.raises(ValueError):
            subtitle_file.write()

    def test_write_accepts_explicit_path_override(self, tmp_path: Path) -> None:
        default_target = tmp_path / "default.srt"
        override_target = tmp_path / "override.srt"
        subtitle_file = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="X")],
            output_path=default_target,
        )

        result = subtitle_file.write(override_target)

        assert result == override_target
        assert override_target.is_file()
        assert not default_target.exists()
