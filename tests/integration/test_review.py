"""Integration test: quickstart.md Scenario 3 (T022, FR-009, FR-010, User Story 2).

Covers the real CLI's `--review` flow end to end, with a *simulated*
editor rather than a real interactive one:

    whisperflow transcribe <video> --review --editor <simulated editor>

**Expected** (quickstart.md Scenario 3): the command pauses after
generating a draft `.srt`, opens it in the given editor, and waits. Once
the (simulated) editor changes the text of one subtitle line, saves, and
exits, the finalized `.srt` left on disk reflects the edited text for that
line -- not the originally generated text.

Unlike `tests/unit/test_review.py` (which exercises `review_subtitle_file`
directly with an injected `run_editor` callable), this test drives the
real `whisperflow transcribe` CLI end to end: real video probing, real
audio extraction, a real (tiny-model) transcription, a real subprocess
"editor" that edits the draft file on disk, and a real re-write of the
finalized file -- so a regression anywhere in that chain (e.g. T021's CLI
wiring writing the pre-edit draft back out instead of the reviewed result)
fails here even though every individual stage's own unit/integration tests
still pass.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import srt
from typer.testing import CliRunner

from cli.main import app

#: Replaces the first subtitle block's text, regardless of the real
#: (platform/runtime-dependent) tiny-model transcription it started as --
#: matching quickstart.md Scenario 3's "Edit the text of one subtitle
#: line, save, and close."
_EDITED_TEXT = "Reviewed and corrected text."


def _write_simulated_editor_script(path: Path) -> None:
    """A small standalone script that plays the part of `--editor`.

    Simulates a user opening the draft `.srt` in their editor, changing
    the text of exactly the first subtitle block, saving, and closing --
    without depending on a real interactive editor binary being installed
    (e.g. `code --wait`, per quickstart.md's own example command).
    `cli.review.review_subtitle_file`'s default `run_editor` invokes
    whatever `--editor` names as a subprocess and blocks until it exits
    (`src/cli/review.py`'s `_run_editor_subprocess`), so a script that
    edits its `sys.argv[1]` path and exits 0 is indistinguishable, from
    that code's point of view, from a real blocking editor.
    """
    path.write_text(
        "import sys\n"
        "import srt\n"
        "path = sys.argv[1]\n"
        "with open(path, encoding='utf-8') as f:\n"
        "    subtitles = list(srt.parse(f.read()))\n"
        f"subtitles[0].content = {_EDITED_TEXT!r}\n"
        "with open(path, 'w', encoding='utf-8') as f:\n"
        "    f.write(srt.compose(subtitles, reindex=False))\n",
        encoding="utf-8",
    )


def test_review_with_simulated_editor_reflects_edit_in_finalized_srt(
    cli_runner: CliRunner, clear_speech_video: Path, tmp_path: Path
) -> None:
    """`whisperflow transcribe <video> --review --editor <script>` (Scenario 3)."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")

    video_path = tmp_path / "clear_speech.mp4"
    shutil.copyfile(clear_speech_video, video_path)
    expected_srt_path = video_path.with_suffix(".srt")

    editor_script = tmp_path / "simulated_editor.py"
    _write_simulated_editor_script(editor_script)
    # Quote each token: on Windows (and potentially in other environments)
    # `sys.executable`/`tmp_path` may contain spaces, which a bare
    # space-joined command would mis-tokenize. Quoting here also exercises
    # the quoted-path/quote-stripping branch in `_split_editor_command`
    # that production `--editor` values with spaces rely on.
    editor_command = f'"{sys.executable}" "{editor_script}"'

    result = cli_runner.invoke(
        app,
        [
            "transcribe",
            str(video_path),
            "--model",
            "tiny",
            "--review",
            "--editor",
            editor_command,
        ],
    )

    assert result.exit_code == 0, result.output
    assert expected_srt_path.is_file(), "expected finalized .srt file was not created"

    subtitles = list(srt.parse(expected_srt_path.read_text(encoding="utf-8")))
    assert len(subtitles) == 1, (
        f"expected exactly 1 subtitle block matching the fixture's known "
        f"single segment, got {len(subtitles)}"
    )

    # The finalized file reflects the simulated editor's change, not the
    # originally generated transcription text.
    assert subtitles[0].content == _EDITED_TEXT

    # Timing is untouched by the review step (FR-010: only text is
    # user-editable in v1) -- matches the fixture's known ground truth
    # (see tests/integration/test_transcribe_basic.py).
    assert subtitles[0].start.total_seconds() == pytest.approx(0.0, abs=0.3)
    assert subtitles[0].end.total_seconds() == pytest.approx(3.2, abs=0.3)
