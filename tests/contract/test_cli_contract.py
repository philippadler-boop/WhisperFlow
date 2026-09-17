"""Contract test: `whisperflow transcribe`'s CLI surface vs. contracts/cli.md (T008).

`tests/unit/test_cli_main.py` (T007) covers the behavior the CLI skeleton
adds (defaulting/plumbing into `_run_pipeline`). This file is the
independent contract check: it reads `specs/001-video-subtitle-generator/
contracts/cli.md` as the source of truth and asserts the *actual* `--help`
text, argument, and option surface -- names, short forms, choice sets, and
documented defaults -- match it, line item by line item. If `cli.md` and
`src/cli/main.py` ever drift, this file is the one that should fail.

Each test's docstring/comment cites the exact contract row/paragraph it
verifies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from cli.main import ModelSize, app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BOX_CHARS_RE = re.compile(r"[│╭╮╰╯─┃┏┓┗┛┌┐└┘━]")
_WS_RE = re.compile(r"\s+")

# Rich (Typer's `--help` renderer) wraps text -- and, at narrow widths, even
# mid-token -- to fit the detected terminal width. Pytest runs with no real
# tty, so force a wide `COLUMNS` for every `--help` invocation below to keep
# multi-word contract phrases and enum literals like
# `<tiny|base|small|medium|large>` intact on one line, regardless of the
# width of whatever terminal happens to run the test suite.
_WIDE_TERMINAL_ENV = {"COLUMNS": "220"}


def _normalize(text: str) -> str:
    """Strip ANSI/Rich color codes and box-drawing borders, then collapse
    whitespace (including line wraps) to single spaces.

    Rich wraps `--help` output in bordered panels and word-wraps long help
    strings across multiple lines; normalizing this way lets us assert on
    the exact contract sentences as contiguous substrings regardless of
    terminal width or panel decoration.
    """
    no_ansi = _ANSI_RE.sub("", text)
    no_box = _BOX_CHARS_RE.sub(" ", no_ansi)
    return _WS_RE.sub(" ", no_box).strip()


# --- Command: "whisperflow transcribe VIDEO_PATH [OPTIONS]" -----------------
# contracts/cli.md: "WhisperFlow v1 exposes exactly one user-facing command
# (FR-005)."


def test_top_level_help_exposes_only_transcribe_command(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"], env=_WIDE_TERMINAL_ENV)
    assert result.exit_code == 0
    output = _normalize(result.output)
    assert "transcribe" in output
    # No other subcommands are part of the v1 contract.
    for stray in ("translate", "review", "config"):
        assert stray not in output


def test_video_path_is_not_a_top_level_shortcut(cli_runner: CliRunner) -> None:
    """`whisperflow VIDEO_PATH` must fail -- only `whisperflow transcribe
    VIDEO_PATH` is the contract's command shape, not a Typer
    single-command auto-flattened shortcut."""
    result = cli_runner.invoke(app, ["video.mp4"])
    assert result.exit_code != 0
    assert "no such command" in result.output.lower()


def test_transcribe_help_usage_line_matches_contract_shape(cli_runner: CliRunner) -> None:
    """Usage: whisperflow transcribe [OPTIONS] VIDEO_PATH"""
    result = cli_runner.invoke(app, ["transcribe", "--help"], env=_WIDE_TERMINAL_ENV)
    assert result.exit_code == 0
    output = _normalize(result.output)
    assert "Usage: whisperflow transcribe [OPTIONS]" in output
    assert "video_path" in output.lower()


# --- Arguments ---------------------------------------------------------------
# | `VIDEO_PATH` | Yes | Path to the input video file (FR-001) |


def test_help_documents_video_path_as_required(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "--help"], env=_WIDE_TERMINAL_ENV)
    output = _normalize(result.output)
    assert "Path to the input video file (FR-001)." in output
    assert "[required]" in output


def test_video_path_argument_is_required(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "Error" in result.output


# --- Options -------------------------------------------------------------
# | `--output`, `-o PATH` | `<video_basename>.srt` next to the input video |
# Where to write the `.srt` file (FR-006)


def test_help_documents_output_option_and_default(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "--help"], env=_WIDE_TERMINAL_ENV)
    output = _normalize(result.output)
    assert "--output" in output
    assert "-o" in output
    assert "Where to write the .srt file (FR-006)." in output
    assert "Defaults to <video_basename>.srt next to the input video." in output


def test_output_option_long_and_short_form_both_work(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    for flag in ("--output", "-o"):
        result = cli_runner.invoke(app, ["transcribe", "video.mp4", flag, "out.srt"])
        assert result.exit_code == 0, result.output
        assert captured_pipeline_call["output_path"] == Path("out.srt")


def test_output_defaults_to_video_basename_next_to_input(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(app, ["transcribe", "some/dir/video.mp4"])
    assert result.exit_code == 0
    assert captured_pipeline_call["output_path"] == Path("some/dir/video.srt")


# | `--model {tiny,base,small,medium,large}` | `base` | faster-whisper
# model size ... |


def test_help_documents_model_option_choices_and_default(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "--help"], env=_WIDE_TERMINAL_ENV)
    output = _normalize(result.output)
    assert "--model" in output
    assert "<tiny|base|small|medium|large>" in output
    assert (
        "faster-whisper model size — smaller is faster, larger is more accurate "
        "(research.md)." in output
    )
    assert "[default: base]" in output


def test_model_option_accepts_all_contract_sizes(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    for size in ("tiny", "base", "small", "medium", "large"):
        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--model", size])
        assert result.exit_code == 0, result.output
        assert captured_pipeline_call["model"] == ModelSize(size)


def test_model_option_rejects_choice_outside_contract_set(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--model", "huge"])
    assert result.exit_code != 0


def test_default_model_is_base(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    """T029 investigated changing this default after short-clip
    benchmarking looked borderline on CPU-only reference hardware, but
    that evidence conflicted with a real, much-longer benchmark run and
    left SC-003's accuracy cost unmeasured -- see contracts/cli.md's
    minimum-hardware note. `base` remains the default; `tiny` is
    recommended only for constrained/CPU-only hardware.
    """
    result = cli_runner.invoke(app, ["transcribe", "video.mp4"])
    assert result.exit_code == 0
    assert captured_pipeline_call["model"] == ModelSize.BASE


# | `--review / --no-review` | `--review` | With `--review`, ... |


def test_help_documents_review_option_and_default(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "--help"], env=_WIDE_TERMINAL_ENV)
    output = _normalize(result.output)
    assert "--review" in output
    assert "--no-review" in output
    assert (
        "With --review, after generating a draft .srt the command "
        "opens it in $EDITOR (or --editor) and waits for confirmation before "
        "finalizing (FR-009, FR-010, User Story 2)." in output
    )
    assert "--no-review finalizes immediately — for scripting/automation." in output
    assert "[default: review]" in output


def test_review_defaults_to_true(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(app, ["transcribe", "video.mp4"])
    assert result.exit_code == 0
    assert captured_pipeline_call["review"] is True


def test_no_review_flag_disables_review(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])
    assert result.exit_code == 0
    assert captured_pipeline_call["review"] is False


# | `--editor CMD` | value of `$EDITOR`/`$VISUAL`, else a built-in fallback
# prompt | Overrides which editor `--review` opens |


def test_help_documents_editor_option_and_default(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "--help"], env=_WIDE_TERMINAL_ENV)
    output = _normalize(result.output)
    assert "--editor" in output
    assert (
        "Overrides which editor --review opens. Defaults to $EDITOR/$VISUAL, "
        "else a built-in fallback prompt." in output
    )


def test_editor_defaults_to_environment_precedence(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(
        app, ["transcribe", "video.mp4"], env={"EDITOR": "nano", "VISUAL": "vim"}
    )
    assert result.exit_code == 0
    assert captured_pipeline_call["editor"] == "nano"


def test_editor_option_overrides_environment(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(
        app,
        ["transcribe", "video.mp4", "--editor", "code --wait"],
        env={"EDITOR": "nano"},
    )
    assert result.exit_code == 0
    assert captured_pipeline_call["editor"] == "code --wait"


def test_editor_defaults_to_none_when_no_env_set(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(
        app, ["transcribe", "video.mp4"], env={"EDITOR": "", "VISUAL": ""}
    )
    assert result.exit_code == 0
    assert captured_pipeline_call["editor"] is None
