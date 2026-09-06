"""Integration tests: quickstart.md Scenarios 5-6 (T018, FR-007).

Covers the real CLI's input validation end to end:

    whisperflow transcribe <input> --no-review

Both invalid inputs must fail before extraction or model loading, with a
single clear error line on stderr and no subtitle output.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app


def _create_overlong_video(path: Path) -> None:
    """Create a tiny, valid MP4 whose duration is just over two hours."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:r=1",
            "-t",
            "7201",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_unsupported_input_fails_with_clear_error(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """`whisperflow transcribe README.md` (Scenario 5)."""
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not installed")

    input_path = tmp_path / "README.md"
    input_path.write_text("This is not a video.\n", encoding="utf-8")
    output_path = tmp_path / "README.srt"

    result = cli_runner.invoke(
        app,
        [
            "transcribe",
            str(input_path),
            "--output",
            str(output_path),
            "--no-review",
        ],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    error_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(error_lines) == 1
    assert error_lines[0].startswith("Error: ")
    assert "supported video format" in error_lines[0].lower()
    assert "video" in error_lines[0].lower()
    assert not output_path.exists()


def test_overlong_video_fails_with_clear_error(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """`whisperflow transcribe <over-2-hour video>` (Scenario 6)."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")

    encoder_result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if encoder_result.returncode != 0 or not any(
        "libx264" in line.split() for line in encoder_result.stdout.splitlines()
    ):
        pytest.skip("ffmpeg libx264 encoder not available")

    input_path = tmp_path / "overlong.mp4"
    output_path = tmp_path / "overlong.srt"
    _create_overlong_video(input_path)

    result = cli_runner.invoke(
        app,
        [
            "transcribe",
            str(input_path),
            "--output",
            str(output_path),
            "--no-review",
        ],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    error_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(error_lines) == 1
    assert error_lines[0].startswith("Error: ")
    assert "maximum" in error_lines[0].lower()
    assert "2 hours" in error_lines[0].lower()
    assert "2:00:01" in error_lines[0]
    assert not output_path.exists()