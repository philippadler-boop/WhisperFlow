"""Unit tests for the `whisperflow transcribe` CLI (T007, T014).

Exercises argument/option parsing and defaulting (T007), per
contracts/cli.md. A full contract test (asserting the entire `--help`
surface matches contracts/cli.md verbatim) is T008's responsibility.

T014's own behavior -- dispatching the `--no-review` path to T013's real
`cli.pipeline.run_pipeline`, `--review` still raising `NotImplementedError`
(T020/T021 aren't done yet), and reporting any `lib.errors.WhisperFlowError`
raised by the pipeline as a single `Error: ...` stderr line with exit code
1 (spec FR-007) -- is covered by the `TestRunPipelineDispatch` and
`TestErrorReporting` classes below.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import cli.main as main_module
from cli.main import ModelSize, _default_editor, _default_output_path, app
from lib.errors import (
    FfmpegNotFoundError,
    MaxDurationExceededError,
    UnsupportedVideoFormatError,
)

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


def test_transcribe_review_still_not_implemented(cli_runner: CliRunner) -> None:
    """`--review` (the default) has no implementation yet (T020/T021)."""
    result = cli_runner.invoke(app, ["transcribe", "video.mp4"])
    assert result.exit_code == 1
    assert isinstance(result.exception, NotImplementedError)


class TestRunPipelineDispatch:
    """T014: `--no-review` dispatches to `cli.pipeline.run_pipeline`."""

    def test_no_review_calls_pipeline_run_pipeline(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            main_module.pipeline,
            "run_pipeline",
            lambda **kwargs: captured.update(kwargs),
        )

        result = cli_runner.invoke(
            app,
            ["transcribe", "video.mp4", "--no-review", "--output", "out.srt", "--model", "small"],
        )

        assert result.exit_code == 0, result.output
        assert captured["video_path"] == Path("video.mp4")
        assert captured["output_path"] == Path("out.srt")
        assert captured["model_size"] == "small"

    def test_review_flag_does_not_reach_pipeline(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = False

        def _fake_run_pipeline(**kwargs):
            nonlocal called
            called = True

        monkeypatch.setattr(main_module.pipeline, "run_pipeline", _fake_run_pipeline)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--review"])

        assert result.exit_code == 1
        assert isinstance(result.exception, NotImplementedError)
        assert called is False


class TestErrorReporting:
    """T014: pipeline `WhisperFlowError`s become a single stderr line, exit 1."""

    def test_unsupported_format_reported_clearly(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(**kwargs):
            raise UnsupportedVideoFormatError("video.avi", detected_format="avi")

        monkeypatch.setattr(main_module.pipeline, "run_pipeline", _raise)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        assert result.exit_code == 1
        assert result.exception is None or not isinstance(result.exception, NotImplementedError)
        assert "Error: unsupported video format 'avi'" in result.output

    def test_oversized_video_reported_clearly(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(**kwargs):
            raise MaxDurationExceededError(8000.0)

        monkeypatch.setattr(main_module.pipeline, "run_pipeline", _raise)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        assert result.exit_code == 1
        assert "Error: video exceeds maximum supported length" in result.output

    def test_missing_ffmpeg_reported_clearly(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(**kwargs):
            raise FfmpegNotFoundError("ffmpeg")

        monkeypatch.setattr(main_module.pipeline, "run_pipeline", _raise)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        assert result.exit_code == 1
        assert "Error: required 'ffmpeg' binary was not found on PATH" in result.output

    def test_error_message_is_a_single_line(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(**kwargs):
            raise FfmpegNotFoundError("ffmpeg")

        monkeypatch.setattr(main_module.pipeline, "run_pipeline", _raise)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        error_lines = [line for line in result.output.splitlines() if line.startswith("Error:")]
        assert len(error_lines) == 1
