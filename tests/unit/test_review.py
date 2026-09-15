"""Unit tests for T020's `--review` flow (`src/cli/review.py`).

Covers spec FR-009 (review generated subtitle text before finalizing),
FR-010 (edits to individual lines are reflected in the exported file), and
data-model.md's `SubtitleLine.edited` rule -- exercised without a real
editor binary or real stdin by injecting `run_editor`/`confirm`.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from cli.review import (
    FALLBACK_PROMPT_TEMPLATE,
    EditorInvocationError,
    review_subtitle_file,
)
from subtitles.models import SubtitleFile, SubtitleLine


def _subtitle_file(tmp_path: Path, lines: list[SubtitleLine]) -> SubtitleFile:
    return SubtitleFile(lines=lines, output_path=tmp_path / "draft.srt")


def _two_line_subtitle_file(tmp_path: Path) -> SubtitleFile:
    return _subtitle_file(
        tmp_path,
        [
            SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hello there."),
            SubtitleLine(index=2, start_seconds=1.0, end_seconds=2.0, text="How are you?"),
        ],
    )


class TestReviewSubtitleFileRequiresOutputPath:
    def test_raises_when_output_path_missing(self) -> None:
        subtitle_file = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hi")]
        )

        with pytest.raises(ValueError, match="output_path"):
            review_subtitle_file(subtitle_file, editor="true")


class TestReviewSubtitleFileWritesDraft:
    def test_writes_draft_before_invoking_editor(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)
        seen_content_at_invocation = {}

        def fake_run_editor(editor: str, path: Path) -> None:
            seen_content_at_invocation["editor"] = editor
            seen_content_at_invocation["content"] = path.read_text(encoding="utf-8")

        review_subtitle_file(
            subtitle_file, editor="my-editor --flag", run_editor=fake_run_editor
        )

        assert subtitle_file.output_path.is_file()
        assert seen_content_at_invocation["editor"] == "my-editor --flag"
        assert "Hello there." in seen_content_at_invocation["content"]
        assert "How are you?" in seen_content_at_invocation["content"]


class TestReviewSubtitleFileEditedFlag:
    def test_edited_text_marks_only_that_line_as_edited(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def fake_run_editor(editor: str, path: Path) -> None:
            content = path.read_text(encoding="utf-8")
            path.write_text(content.replace("Hello there.", "Hi everyone."), encoding="utf-8")

        result = review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

        assert [line.text for line in result.lines] == ["Hi everyone.", "How are you?"]
        assert result.lines[0].edited is True
        assert result.lines[1].edited is False

    def test_no_changes_leaves_edited_false(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def fake_run_editor(editor: str, path: Path) -> None:
            pass  # user opens the editor, changes nothing, closes it

        result = review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

        assert [line.text for line in result.lines] == ["Hello there.", "How are you?"]
        assert all(line.edited is False for line in result.lines)

    def test_resaving_an_already_edited_line_unchanged_keeps_edited_true(
        self, tmp_path: Path
    ) -> None:
        subtitle_file = _subtitle_file(
            tmp_path,
            [
                SubtitleLine(
                    index=1,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    text="Already fixed.",
                    edited=True,
                )
            ],
        )

        def fake_run_editor(editor: str, path: Path) -> None:
            pass  # re-saved with no further change

        result = review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

        assert result.lines[0].text == "Already fixed."
        assert result.lines[0].edited is True

    def test_line_added_in_editor_has_no_generated_counterpart_and_is_edited(
        self, tmp_path: Path
    ) -> None:
        subtitle_file = _subtitle_file(
            tmp_path,
            [SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Only line")],
        )

        def fake_run_editor(editor: str, path: Path) -> None:
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nOnly line\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\nBrand new line\n\n",
                encoding="utf-8",
            )

        result = review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

        assert [line.text for line in result.lines] == ["Only line", "Brand new line"]
        assert result.lines[0].edited is False
        assert result.lines[1].edited is True
        assert result.lines[1].start_seconds == 1.0
        assert result.lines[1].end_seconds == 2.0

    def test_line_removed_in_editor_is_absent_from_result(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def fake_run_editor(editor: str, path: Path) -> None:
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello there.\n\n", encoding="utf-8"
            )

        result = review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

        assert [line.text for line in result.lines] == ["Hello there."]

    def test_returned_subtitle_file_preserves_metadata(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def fake_run_editor(editor: str, path: Path) -> None:
            pass

        result = review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

        assert result.output_path == subtitle_file.output_path
        assert result.format == subtitle_file.format
        assert result is not subtitle_file


class TestReviewSubtitleFileFallbackPrompt:
    def test_no_editor_prints_fallback_prompt_and_waits_for_confirm(
        self, tmp_path: Path
    ) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)
        stream = io.StringIO()
        confirm_calls = []

        result = review_subtitle_file(
            subtitle_file,
            editor=None,
            stream=stream,
            confirm=lambda: confirm_calls.append(True),
        )

        assert confirm_calls == [True]
        assert FALLBACK_PROMPT_TEMPLATE.format(path=subtitle_file.output_path) in stream.getvalue()
        assert [line.text for line in result.lines] == ["Hello there.", "How are you?"]

    def test_no_editor_reflects_manual_edit_made_before_confirming(
        self, tmp_path: Path
    ) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def manual_edit_then_confirm() -> None:
            content = subtitle_file.output_path.read_text(encoding="utf-8")
            subtitle_file.output_path.write_text(
                content.replace("How are you?", "How's it going?"), encoding="utf-8"
            )

        result = review_subtitle_file(
            subtitle_file,
            editor=None,
            stream=io.StringIO(),
            confirm=manual_edit_then_confirm,
        )

        assert [line.text for line in result.lines] == ["Hello there.", "How's it going?"]
        assert result.lines[1].edited is True


class TestReviewSubtitleFileEditorInvocationError:
    def test_editor_nonzero_exit_raises_editor_invocation_error(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        with pytest.raises(EditorInvocationError, match="false"):
            review_subtitle_file(subtitle_file, editor="false")

    def test_editor_not_found_raises_editor_invocation_error(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        with pytest.raises(EditorInvocationError, match="not-a-real-editor-binary"):
            review_subtitle_file(subtitle_file, editor="not-a-real-editor-binary")

    def test_editor_invocation_error_is_a_whisperflow_error(self) -> None:
        from lib.errors import WhisperFlowError

        assert issubclass(EditorInvocationError, WhisperFlowError)
