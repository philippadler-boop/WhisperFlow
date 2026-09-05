"""Shared pytest fixtures for the WhisperFlow test suite (T003).

Provides:
- ``cli_runner``: a ``typer.testing.CliRunner`` for invoking the
  ``whisperflow`` CLI in-process (contracts/cli.md).
- ``captured_pipeline_call``: stubs ``cli.main._run_pipeline`` and captures
  the resolved kwargs it receives, so CLI parsing/defaulting tests
  (``tests/unit/test_cli_main.py``, ``tests/contract/test_cli_contract.py``)
  can drive the real Typer ``app`` end to end without hitting the
  not-yet-implemented pipeline.
- ``clear_speech_video`` / ``silence_video``: paths to small sample videos
  under ``tests/fixtures/`` used by quickstart.md's validation scenarios
  and by contract/integration/unit tests -- a short clip with clear
  spoken audio (Scenario 1/2) and a short clip with a silent/no-speech
  audio track (Scenario 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def cli_runner() -> CliRunner:
    """A Typer CLI test runner for invoking `whisperflow` in-process."""
    return CliRunner()


@pytest.fixture
def captured_pipeline_call(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub `_run_pipeline` and capture the resolved kwargs it receives.

    Lets CLI tests drive the real Typer `app`/parsing/defaulting code path
    end to end without hitting the not-yet-implemented pipeline.
    """
    import cli.main as main_module

    captured: dict[str, Any] = {}
    monkeypatch.setattr(main_module, "_run_pipeline", lambda **kwargs: captured.update(kwargs))
    return captured


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
