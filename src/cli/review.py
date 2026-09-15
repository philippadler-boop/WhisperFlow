"""Interactive `--review` flow: draft, edit, re-read (T020).

Implements User Story 2's review step (spec FR-009, FR-010): write the
freshly generated `SubtitleFile` to disk as a draft `.srt`, open it in the
user's editor (`$EDITOR`/`$VISUAL`, or `--editor`), block until the user
confirms they're done editing, then re-read the file from disk and fold
any text changes back into the in-memory `SubtitleFile` -- setting
`SubtitleLine.edited` on exactly the lines whose text actually changed
(data-model.md -- SubtitleLine.edited), and leaving every other line's
`edited` flag untouched.

This module only implements the review step itself. Wiring it into the
`whisperflow transcribe` command's `--review`/`--no-review` branching (and
deciding what happens with the *returned* `SubtitleFile` -- e.g. whether
it needs to be written again) is T021's job, in `src/cli/main.py`.

Two ways of "waiting for confirmation" are supported, matching
contracts/cli.md's `--editor` row:

- An editor command is configured (`--editor`, or `$EDITOR`/`$VISUAL`):
  it is launched with the draft file's path appended, and this function
  blocks until that process exits. A blocking editor invocation (e.g.
  `code --wait`) is itself the confirmation.
- No editor is configured: a built-in fallback prompt is printed telling
  the user where the draft file is, and this function blocks on an
  explicit confirmation (pressing Enter) instead of launching anything.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TextIO

import srt

from lib.errors import DraftParseError, WhisperFlowError
from subtitles.models import SubtitleFile, SubtitleLine

#: Printed instead of launching an editor when none is configured
#: (contracts/cli.md's `--editor` row: "else a built-in fallback prompt").
FALLBACK_PROMPT_TEMPLATE = (
    "No editor configured (set $EDITOR/$VISUAL or pass --editor). "
    "Edit the draft subtitle file at '{path}' now, save it, then press "
    "Enter here to continue…"
)


class EditorInvocationError(WhisperFlowError):
    """The configured `--editor`/`$EDITOR` command could not be run, or failed.

    Raised when the editor command can't be found/started at all (e.g. a
    typo'd `--editor` value), or when it runs but exits with a non-zero
    status -- both are treated as the user *not* having successfully
    confirmed their edits, so review cannot proceed to finalizing the
    subtitle file. Maps to CLI exit code 1 like every other
    `WhisperFlowError` (contracts/cli.md's Exit codes section).
    """

    def __init__(self, editor: str, reason: str = "") -> None:
        self.editor = editor
        self.reason = reason.strip()
        detail = f": {self.reason}" if self.reason else ""
        message = f"failed to open editor '{editor}'{detail}"
        super().__init__(message)


def review_subtitle_file(
    subtitle_file: SubtitleFile,
    *,
    editor: str | None,
    stream: TextIO | None = None,
    confirm: Callable[[], None] | None = None,
    run_editor: Callable[[str, Path], None] | None = None,
) -> SubtitleFile:
    """Run the FR-009/FR-010 review step on `subtitle_file` and return the result.

    Args:
        subtitle_file: The freshly generated (unwritten or already-written)
            `SubtitleFile` to review. Must have `output_path` set -- that's
            where the draft is written and re-read from.
        editor: The editor command to invoke (contracts/cli.md's
            `--editor`, already resolved from `$EDITOR`/`$VISUAL` by the
            caller), or `None` to use the built-in fallback prompt instead
            of launching anything.
        stream: Where the fallback prompt (when `editor` is `None`) is
            printed. Defaults to `sys.stderr`, matching every other
            user-facing announcement in this codebase (contracts/cli.md's
            Progress contract); overridable for tests.
        confirm: Called to block on the user's confirmation when `editor`
            is `None`. Defaults to the builtin `input`; overridable for
            tests so they don't block on real stdin.
        run_editor: Called as `run_editor(editor, draft_path)` to launch
            the configured editor and block until it exits. Defaults to
            `_run_editor_subprocess`; overridable for tests so they don't
            need a real editor binary on `PATH`.

    Returns:
        A new `SubtitleFile` (same `output_path`/`format`/`source_video`)
        whose `lines` reflect whatever was on disk after the user finished
        editing: lines whose text changed have `edited=True`; lines whose
        text is unchanged keep their prior `edited` value; lines added by
        the user that don't correspond to any originally generated line
        are included as new, `edited=True` lines (there is no "generated"
        value to compare them against, so they cannot be "unchanged").
        Lines the user removed from the draft are simply absent from the
        result.

    Raises:
        ValueError: `subtitle_file.output_path` is not set.
        EditorInvocationError: the configured editor could not be started,
            or exited with a non-zero status.
        DraftParseError: the draft file could not be parsed back in after
            editing -- e.g. it was left malformed, or a new/edited block
            has an invalid timestamp (end before start).
    """
    if stream is None:
        stream = sys.stderr
    if confirm is None:
        confirm = input
    if run_editor is None:
        run_editor = _run_editor_subprocess
    if subtitle_file.output_path is None:
        raise ValueError("review_subtitle_file requires subtitle_file.output_path to be set")

    draft_path = subtitle_file.write()

    if editor:
        run_editor(editor, draft_path)
    else:
        print(FALLBACK_PROMPT_TEMPLATE.format(path=draft_path), file=stream, flush=True)
        confirm()

    return _reread_with_edits(subtitle_file, draft_path)


def _run_editor_subprocess(editor: str, path: Path) -> None:
    """Launch `editor` against `path` and block until it exits (default `run_editor`).

    `editor` is split shell-style (`shlex.split`) so multi-word commands
    from `--editor`/`$EDITOR` (e.g. `"code --wait"`, per contracts/cli.md's
    Scenario 3) work the same as a bare editor name, and the draft path is
    appended as the final argument.

    `shlex.split` is run in non-POSIX mode on Windows (`posix=False`):
    POSIX quoting treats a bare, unquoted backslash as an escape
    character, which would silently corrupt an ordinary Windows path like
    ``--editor C:\\Editors\\Notepad2\\notepad2.exe`` (this project targets
    Windows -- see the ADRs and MSI packaging work) into a bogus argv[0]
    with the backslashes dropped. Non-POSIX splitting leaves backslashes
    alone.
    """
    command = [*shlex.split(editor, posix=(sys.platform != "win32")), str(path)]
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        raise EditorInvocationError(editor, reason=str(exc)) from exc
    if result.returncode != 0:
        raise EditorInvocationError(editor, reason=f"exited with status {result.returncode}")


def _reread_with_edits(subtitle_file: SubtitleFile, draft_path: Path) -> SubtitleFile:
    """Re-read `draft_path` and fold any text changes back into `subtitle_file`.

    Matches re-read subtitle blocks back to `subtitle_file.lines` by
    `index` (data-model.md: `SubtitleLine.index` is "1-based line number in
    the .srt file", preserved by `SubtitleFile.compose()`'s `reindex=False`
    -- see `src/subtitles/models.py`), rather than by position, so a
    reordering or a deletion elsewhere in the file doesn't misattribute an
    edit to the wrong line. `subtitle_file.lines` is assumed not to contain
    duplicate indices to begin with; a duplicate introduced by a careless
    edit is not detected here and would silently collapse onto one output
    line via `originals_by_index`.

    Any failure to parse the edited file back into subtitle blocks --
    malformed `.srt` content (`srt.parse` raises `srt.SRTParseError`/
    `TimestampParseError`), or a new/edited block with an invalid
    timestamp (`SubtitleLine.__post_init__` raises `ValueError` when
    `end_seconds < start_seconds`) -- is caught here and re-raised as
    `DraftParseError`, matching this codebase's convention of never
    letting a library's raw exception escape a subprocess/library boundary
    (see e.g. `src/audio/video_probe.py`, `src/audio/extract.py`).

    Raises:
        DraftParseError: `draft_path`'s content could not be parsed back
            into valid subtitle blocks.
    """
    content = draft_path.read_text(encoding="utf-8")
    try:
        parsed = list(srt.parse(content))
    except (srt.SRTParseError, srt.TimestampParseError) as exc:
        raise DraftParseError(draft_path, reason=str(exc)) from exc
    originals_by_index = {line.index: line for line in subtitle_file.lines}

    new_lines: list[SubtitleLine] = []
    try:
        for entry in parsed:
            original = originals_by_index.get(entry.index)
            if original is not None:
                # with_text() only sets `edited=True` when the text
                # actually differs (subtitles/models.py), so a re-save
                # with no real change leaves `edited` at its prior value
                # instead of always flipping it true.
                new_lines.append(original.with_text(entry.content))
            else:
                # A line the user added that has no originally generated
                # counterpart to compare against -- there is no
                # "unedited" value it could have, so it's edited by
                # definition.
                new_lines.append(
                    SubtitleLine(
                        index=entry.index,
                        start_seconds=entry.start.total_seconds(),
                        end_seconds=entry.end.total_seconds(),
                        text=entry.content,
                        edited=True,
                    )
                )
    except ValueError as exc:
        raise DraftParseError(draft_path, reason=str(exc)) from exc

    return replace(subtitle_file, lines=new_lines)
