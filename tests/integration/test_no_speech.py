"""Integration test: quickstart.md Scenario 4 (T017, FR-008, FR-011).

Covers the real CLI's successful no-speech behavior end to end:

    whisperflow transcribe <silent video> --no-review

The command must produce an empty subtitle file and explain the outcome on
stderr instead of treating the absence of speech as a processing failure.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import srt
from typer.testing import CliRunner

from cli.main import app
from cli.pipeline import NO_SPEECH_DETECTED_MESSAGE


def test_silent_video_succeeds_with_empty_srt_and_stderr_notice(
    cli_runner: CliRunner, silence_video: Path, tmp_path: Path
) -> None:
    """`whisperflow transcribe <silent video> --no-review` (Scenario 4)."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")

    video_path = tmp_path / "silence.mp4"
    shutil.copyfile(silence_video, video_path)
    expected_srt_path = video_path.with_suffix(".srt")

    result = cli_runner.invoke(
        app, ["transcribe", str(video_path), "--model", "tiny", "--no-review"]
    )

    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert expected_srt_path.is_file(), "expected .srt file was not created"
    assert list(srt.parse(expected_srt_path.read_text(encoding="utf-8"))) == []
    assert NO_SPEECH_DETECTED_MESSAGE in result.stderr