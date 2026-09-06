"""Integration test: quickstart.md Scenario 2 (T016, FR-011).

Covers the real CLI's progress feedback contract end to end:

    whisperflow transcribe <video> --no-review

**Expected** (quickstart.md Scenario 2): while the command runs, stderr
shows stage announcements (`Extracting audio…`, `Transcribing…`,
`Writing subtitles…`) and an in-flight transcription percentage.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import app


def test_transcribe_reports_stage_and_progress_lines_on_stderr(
    cli_runner: CliRunner, clear_speech_video: Path, tmp_path: Path
) -> None:
    """`whisperflow transcribe <clear-speech video> --no-review` (Scenario 2)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")

    video_path = tmp_path / "clear_speech.mp4"
    shutil.copyfile(clear_speech_video, video_path)

    result = cli_runner.invoke(
        app, ["transcribe", str(video_path), "--model", "tiny", "--no-review"]
    )

    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert "Extracting audio…" in result.stderr
    assert "Transcribing…" in result.stderr
    assert "Writing subtitles…" in result.stderr
    assert re.search(r"\rTranscribing…\s+\d+\.\d%", result.stderr) is not None
