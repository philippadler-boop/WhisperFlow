"""Unit tests for the `whisperflow transcribe` CLI (T007, T014, T021).

Exercises argument/option parsing and defaulting (T007), per
contracts/cli.md. A full contract test (asserting the entire `--help`
surface matches contracts/cli.md verbatim) is T008's responsibility.

T014/T021's own behavior -- dispatching `--no-review` straight to T013's
real `cli.pipeline.run_pipeline`, dispatching `--review` (the default) to
that same pipeline *and then* T020's `cli.review.review_subtitle_file`
review step, writing back its finalized result, and reporting any
`lib.errors.WhisperFlowError` raised by either step as a single
`Error: ...` stderr line with exit code 1 (spec FR-007) -- is covered by
the `TestRunPipelineDispatch` and `TestErrorReporting` classes below.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import cli.main as main_module
from cli.main import BANNER, ModelSize, _default_editor, _default_output_path, app
from cli.review import EditorInvocationError
from lib.errors import (
    FfmpegNotFoundError,
    MaxDurationExceededError,
    SubtitleWriteError,
    UnsupportedVideoFormatError,
)
from subtitles.models import SubtitleFile, SubtitleLine

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI/Rich formatting codes so substring checks are reliable."""
    return _ANSI_RE.sub("", text)


def test_transcribe_is_a_required_subcommand(cli_runner: CliRunner) -> None:
    """`whisperflow transcribe ...`, not `whisperflow ...` (contracts/cli.md)."""
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "transcribe" in result.output


def test_root_help_includes_colored_banner(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "███████" in result.output
    assert "Local video-to-subtitle transcription" in result.output
    output = _plain(result.output)
    for line in BANNER.strip().splitlines():
        assert line.strip() in output


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


class TestRunPipelineDispatch:
    """T014/T021: `--no-review`/`--review` dispatch to `cli.pipeline.run_pipeline`,
    and `--review` additionally to `cli.review.review_subtitle_file`.
    """

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

    def test_no_review_does_not_invoke_review_step(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        subtitle_file = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hi")],
            output_path=tmp_path / "out.srt",
        )
        monkeypatch.setattr(main_module.pipeline, "run_pipeline", lambda **kwargs: subtitle_file)
        called = False

        def _fake_review(*args, **kwargs):
            nonlocal called
            called = True
            return subtitle_file

        monkeypatch.setattr(main_module, "review_subtitle_file", _fake_review)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        assert result.exit_code == 0, result.output
        assert called is False

    def test_review_calls_pipeline_then_review_step(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        draft = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hi")],
            output_path=tmp_path / "out.srt",
        )
        pipeline_captured: dict[str, Any] = {}
        monkeypatch.setattr(
            main_module.pipeline,
            "run_pipeline",
            lambda **kwargs: (pipeline_captured.update(kwargs), draft)[1],
        )

        review_captured: dict[str, Any] = {}

        def _fake_review(subtitle_file, *, editor, **kwargs):
            review_captured["subtitle_file"] = subtitle_file
            review_captured["editor"] = editor
            return subtitle_file

        monkeypatch.setattr(main_module, "review_subtitle_file", _fake_review)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--review", "--editor", "true"])

        assert result.exit_code == 0, result.output
        assert pipeline_captured["video_path"] == Path("video.mp4")
        assert review_captured["subtitle_file"] is draft
        assert review_captured["editor"] == "true"

    def test_review_writes_back_finalized_subtitle_file(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "out.srt"
        draft = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hi")],
            output_path=output_path,
        )
        monkeypatch.setattr(main_module.pipeline, "run_pipeline", lambda **kwargs: draft)

        edited = SubtitleFile(
            lines=[
                SubtitleLine(
                    index=1, start_seconds=0.0, end_seconds=1.0, text="Edited!", edited=True
                )
            ],
            output_path=output_path,
        )
        monkeypatch.setattr(
            main_module, "review_subtitle_file", lambda subtitle_file, **kwargs: edited
        )

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--review"])

        assert result.exit_code == 0, result.output
        assert "Edited!" in output_path.read_text(encoding="utf-8")


class TestErrorReporting:
    """T014/T021: pipeline/review `WhisperFlowError`s become a single
    stderr line, exit 1."""

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

    def test_subtitle_write_failure_is_reported_once(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _raise(**kwargs):
            raise SubtitleWriteError(tmp_path / "out.srt", reason="Permission denied")

        monkeypatch.setattr(main_module.pipeline, "run_pipeline", _raise)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        assert result.exit_code == 1
        error_lines = [line for line in result.output.splitlines() if line.startswith("Error:")]
        assert error_lines == [
            f"Error: failed to write subtitle file to '{tmp_path / 'out.srt'}': Permission denied"
        ]

    def test_review_write_back_failure_is_reported_once(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A failed write-back of the reviewed/finalized `SubtitleFile`
        (T021's `subtitle_file.write()` call after `review_subtitle_file`
        returns) must be reported the same way T013's own initial write
        failure is (`SubtitleWriteError` -> single `Error: ...` line, exit
        code 1) rather than propagating as a raw, unhandled `OSError`."""
        output_path = tmp_path / "out.srt"
        draft = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hi")],
            output_path=output_path,
        )
        monkeypatch.setattr(main_module.pipeline, "run_pipeline", lambda **kwargs: draft)

        edited = SubtitleFile(
            lines=[
                SubtitleLine(
                    index=1, start_seconds=0.0, end_seconds=1.0, text="Edited!", edited=True
                )
            ],
            output_path=output_path,
        )
        monkeypatch.setattr(
            main_module, "review_subtitle_file", lambda subtitle_file, **kwargs: edited
        )

        def _raise_oserror(self) -> None:
            raise OSError("Permission denied")

        monkeypatch.setattr(SubtitleFile, "write", _raise_oserror)

        result = cli_runner.invoke(
            app, ["transcribe", "video.mp4", "--review", "--output", str(output_path)]
        )

        assert result.exit_code == 1
        error_lines = [line for line in result.output.splitlines() if line.startswith("Error:")]
        assert error_lines == [
            f"Error: failed to write subtitle file to '{output_path}': Permission denied"
        ]

    def test_review_step_error_reported_clearly(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A `--review`-step failure (e.g. the configured editor couldn't be
        launched) is reported through the same single-line, exit-code-1
        path as any pipeline-stage `WhisperFlowError` (T021)."""
        draft = SubtitleFile(
            lines=[SubtitleLine(index=1, start_seconds=0.0, end_seconds=1.0, text="Hi")],
            output_path=tmp_path / "out.srt",
        )
        monkeypatch.setattr(main_module.pipeline, "run_pipeline", lambda **kwargs: draft)

        def _raise_editor_error(subtitle_file, **kwargs):
            raise EditorInvocationError("bogus-editor", reason="No such file or directory")

        monkeypatch.setattr(main_module, "review_subtitle_file", _raise_editor_error)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--review"])

        assert result.exit_code == 1
        error_lines = [line for line in result.output.splitlines() if line.startswith("Error:")]
        assert error_lines == [
            "Error: failed to open editor 'bogus-editor': No such file or directory"
        ]

    def test_ffprobe_launch_failure_reported_clearly_not_as_raw_error(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A present-but-unlaunchable `ffprobe` (P3 review) must still be a
        single clear `Error: ...` line, exit code 1 -- exercised through the
        real CLI -> `cli.pipeline.run_pipeline` -> `probe_video` path, with
        nothing mocked below `subprocess.run`/`shutil.which` themselves, so
        this can't pass by coincidence of a higher-level mock swallowing the
        real translation logic under test.
        """
        monkeypatch.setattr("shutil.which", lambda executable: f"/usr/bin/{executable}")

        def _raise_permission_error(*args, **kwargs):
            raise PermissionError("[Errno 13] Permission denied: 'ffprobe'")

        monkeypatch.setattr(subprocess, "run", _raise_permission_error)

        result = cli_runner.invoke(app, ["transcribe", "video.mp4", "--no-review"])

        assert result.exit_code == 1
        assert result.exception is None or not isinstance(result.exception, NotImplementedError)
        error_lines = [line for line in result.output.splitlines() if line.startswith("Error:")]
        assert len(error_lines) == 1
        # Must not be misreported as FfmpegNotFoundError -- ffprobe *is* on
        # PATH here, it just couldn't be launched, so "install ffmpeg" would
        # be an actively wrong remediation.
        assert "install ffmpeg" not in error_lines[0].lower()
