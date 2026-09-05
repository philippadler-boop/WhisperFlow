"""Unit tests for the `whisperflow transcribe` CLI skeleton (T007).

Exercises argument/option parsing, defaulting, and the not-yet-implemented
pipeline hookup, per contracts/cli.md. A full contract test (asserting the
entire `--help` surface matches contracts/cli.md verbatim) is T008's
responsibility; these tests cover the behavior this task actually adds.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cli.main import ModelSize, _default_editor, _default_output_path, app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI/Rich formatting codes so substring checks are reliable."""
    return _ANSI_RE.sub("", text)


def test_transcribe_is_a_required_subcommand(cli_runner: CliRunner) -> None:
    """`whisperflow transcribe ...`, not `whisperflow ...` (contracts/cli.md)."""
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "transcribe" in result.output


def test_transcribe_help_documents_all_contract_options(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "--help"])
    assert result.exit_code == 0
    output = _plain(result.output)
    for option in ("--output", "-o", "--model", "--review", "--no-review", "--editor"):
        assert option in output


def test_video_path_argument_is_required(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "Error" in result.output


def test_default_model_is_base(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    result = cli_runner.invoke(app, ["transcribe", "video.mp4"])
    assert result.exit_code == 0
    assert captured_pipeline_call["model"] == ModelSize.BASE


def test_model_option_accepts_all_contract_sizes(
    cli_runner: CliRunner, captured_pipeline_call: dict[str, Any]
) -> None:
    for size in ("tiny", "base", "small", "medium", "large"):
        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--model", size])
        assert result.exit_code == 0, result.output
        assert captured_pipeline_call["model"] == ModelSize(size)


def test_model_option_rejects_unknown_size(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--model", "huge"])
    assert result.exit_code != 0


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


def test_output_option_short_and_long_form(
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


def test_default_output_path_helper() -> None:
    assert _default_output_path(Path("clip.mp4")) == Path("clip.srt")
    assert _default_output_path(Path("dir/clip.mov")) == Path("dir/clip.srt")


def test_default_editor_prefers_editor_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITOR", "nano")
    monkeypatch.setenv("VISUAL", "vim")
    assert _default_editor() == "nano"


def test_default_editor_falls_back_to_visual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setenv("VISUAL", "vim")
    assert _default_editor() == "vim"


def test_default_editor_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    assert _default_editor() is None


def test_editor_option_overrides_env(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    captured_pipeline_call: dict[str, Any],
) -> None:
    monkeypatch.setenv("EDITOR", "nano")
    result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--editor", "code --wait"])
    assert result.exit_code == 0
    assert captured_pipeline_call["editor"] == "code --wait"


def test_transcribe_calls_not_yet_implemented_pipeline(cli_runner: CliRunner) -> None:
    """Skeleton wiring: real invocation surfaces NotImplementedError for now."""
    result = cli_runner.invoke(app, ["transcribe", "video.mp4"])
    assert result.exit_code == 1
    assert isinstance(result.exception, NotImplementedError)
