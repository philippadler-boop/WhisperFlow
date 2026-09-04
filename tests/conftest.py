"""Shared pytest fixtures for the WhisperFlow test suite (T003).

Provides:
- ``cli_runner``: a ``typer.testing.CliRunner`` for invoking the
  ``whisperflow`` CLI in-process (contracts/cli.md).
- ``clear_speech_video`` / ``silence_video``: paths to small sample videos
  under ``tests/fixtures/`` used by quickstart.md's validation scenarios
  and by contract/integration/unit tests -- a short clip with clear
  spoken audio (Scenario 1/2) and a short clip with a silent/no-speech
  audio track (Scenario 4).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def cli_runner() -> CliRunner:
    """A Typer CLI test runner for invoking `whisperflow` in-process."""
    return CliRunner()


@pytest.fixture
def clear_speech_video() -> Path:
    """Path to a short sample video with clear, intelligible spoken audio.

    Used by quickstart.md Scenarios 1 ("Basic transcription") and 2
    ("Progress feedback").
    """
    path = FIXTURES_DIR / "clear_speech.mp4"
    assert path.is_file(), f"missing fixture video: {path}"
    return path


@pytest.fixture
def silence_video() -> Path:
    """Path to a short sample video with a silent/no-speech audio track.

    Used by quickstart.md Scenario 4 ("No detectable speech").
    """
    path = FIXTURES_DIR / "silence.mp4"
    assert path.is_file(), f"missing fixture video: {path}"
    return path
