"""Unit tests for T020's `--review` flow (`src/cli/review.py`).

Covers spec FR-009 (review generated subtitle text before finalizing),
FR-010 (edits to individual lines are reflected in the exported file), and
data-model.md's `SubtitleLine.edited` rule -- exercised without a real
editor binary or real stdin by injecting `run_editor`/`confirm`.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from cli.review import (
    FALLBACK_PROMPT_TEMPLATE,
    EditorInvocationError,
    _run_editor_subprocess,
    _split_editor_command,
    review_subtitle_file,
)
from lib.errors import DraftParseError, WhisperFlowError
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
        # A portable non-zero-exit "editor": a real Python interpreter
        # invoked with a multi-word --editor value, rather than relying on
        # a `false` binary being on PATH (not guaranteed, e.g. on Windows).
        # This also exercises shlex.split's multi-word-command path end to
        # end, since `editor` here is more than one token.
        editor = f"{sys.executable} -c \"import sys; sys.exit(1)\""

        with pytest.raises(EditorInvocationError, match="exited with status 1"):
            review_subtitle_file(subtitle_file, editor=editor)

    def test_editor_not_found_raises_editor_invocation_error(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        with pytest.raises(EditorInvocationError, match="not-a-real-editor-binary"):
            review_subtitle_file(subtitle_file, editor="not-a-real-editor-binary")

    def test_editor_invocation_error_is_a_whisperflow_error(self) -> None:
        assert issubclass(EditorInvocationError, WhisperFlowError)


class TestRunEditorSubprocessShlexSplitting:
    def test_windows_style_backslash_path_is_not_mangled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A Windows editor path's backslashes must survive splitting.

        `shlex.split` in its default POSIX mode treats a bare, unquoted
        backslash as an escape character, which would corrupt an editor
        value like ``C:\\Editors\\Notepad2\\notepad2.exe`` (no spaces
        requiring quoting, the common case for a bare `--editor`/`$EDITOR`
        path) into a bogus argv[0] with the backslashes silently dropped.
        `_run_editor_subprocess` must split in non-POSIX mode on Windows so
        the path reaches `subprocess.run` unchanged.
        """
        seen_commands = []

        class _FakeCompletedProcess:
            returncode = 0

        def fake_run(command, **kwargs):
            seen_commands.append(command)
            return _FakeCompletedProcess()

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr("cli.review.subprocess.run", fake_run)

        editor = r"C:\Editors\Notepad2\notepad2.exe"
        draft_path = tmp_path / "draft.srt"

        _run_editor_subprocess(editor, draft_path)

        assert seen_commands == [[editor, str(draft_path)]]

    def test_windows_style_quoted_path_with_space_is_split_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A quoted Windows editor path containing a space keeps its quotes stripped.

        `shlex.split(..., posix=False)` (needed so backslashes survive,
        per the sibling test above) does not consume the quote characters
        it uses to find token boundaries the way POSIX mode does. Without
        stripping them back off, a legitimately quoted path like
        `'"C:\\Program Files\\Notepad++\\notepad++.exe" --multiInst'`
        would reach `subprocess.run` with the quote characters still
        embedded in argv[0], which is wrong on every platform.
        """
        seen_commands = []

        class _FakeCompletedProcess:
            returncode = 0

        def fake_run(command, **kwargs):
            seen_commands.append(command)
            return _FakeCompletedProcess()

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr("cli.review.subprocess.run", fake_run)

        editor = '"C:\\Program Files\\Notepad++\\notepad++.exe" --multiInst'
        draft_path = tmp_path / "draft.srt"

        _run_editor_subprocess(editor, draft_path)

        assert seen_commands == [
            [
                "C:\\Program Files\\Notepad++\\notepad++.exe",
                "--multiInst",
                str(draft_path),
            ]
        ]

    def test_split_editor_command_strips_matching_quotes_on_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")

        assert _split_editor_command('"code" --wait') == ["code", "--wait"]

    def test_split_editor_command_uses_posix_rules_off_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "linux")

        assert _split_editor_command('"code" --wait') == ["code", "--wait"]


class TestReReadWithEditsDraftParseError:
    def test_malformed_draft_raises_draft_parse_error(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def fake_run_editor(editor: str, path: Path) -> None:
            path.write_text("this is not valid .srt content at all", encoding="utf-8")

        with pytest.raises(DraftParseError):
            review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

    def test_invalid_timestamp_raises_draft_parse_error(self, tmp_path: Path) -> None:
        subtitle_file = _two_line_subtitle_file(tmp_path)

        def fake_run_editor(editor: str, path: Path) -> None:
            # A newly *added* block (index 3, no original counterpart) with
            # its end timestamp before its start -- SubtitleLine.__post_init__
            # raises ValueError for this when constructing the new line,
            # which must be wrapped rather than escaping raw from
            # review_subtitle_file. (An invalid timestamp on an *existing*
            # index wouldn't reach validation at all: with_text() only ever
            # replaces text, never start/end.)
            path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello there.\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\nHow are you?\n\n"
                "3\n00:00:05,000 --> 00:00:01,000\nBad timing\n\n",
                encoding="utf-8",
            )

        with pytest.raises(DraftParseError):
            review_subtitle_file(subtitle_file, editor="fake", run_editor=fake_run_editor)

    def test_draft_parse_error_is_a_whisperflow_error(self) -> None:
        assert issubclass(DraftParseError, WhisperFlowError)
