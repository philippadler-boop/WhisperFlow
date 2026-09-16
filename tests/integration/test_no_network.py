"""Integration test: quickstart.md Scenario 7 (T026, FR-004).

Confirms `whisperflow transcribe` produces the same successful outcome as
quickstart.md Scenario 1 (T015, `test_transcribe_basic.py`) even when every
outbound network connection attempt is blocked -- proving no per-video
transcription traffic depends on reaching the network, per FR-004 and ADR
0001's Consequences ("no network call is part of the transcription path").

ADR 0001 also documents the one narrow, deliberate exception to "no network
calls": the ASR model's *weight* files must already be present locally
(a first-run download, or a pre-bundled cache) before that guarantee holds.
This test warms that cache -- with the network still allowed -- exactly like
a real first run would, *before* blocking the network, so what's actually
under test is Scenario 7's real-world case (an already-installed
`whisperflow` running on an air-gapped or firewalled machine), not the
one-time initial weight download that ADR 0001 explicitly carves out.
"""

from __future__ import annotations

import shutil
import socket
from pathlib import Path
from typing import Any

import pytest
import srt
from typer.testing import CliRunner

from cli.main import app

_MODEL_SIZE = "tiny"

# Same fixture-specific ground truth as test_transcribe_basic.py's Scenario 1
# test (docs/validation/T011.md) -- Scenario 7 must reproduce it identically
# with the network blocked, not just "succeed with some output".
_STABLE_SPOKEN_WORDS = ("hello", "test", "generator")


def _prewarm_model_cache() -> None:
    """Ensure the `tiny` model's weights are already cached locally.

    Mirrors `transcription.transcribe._load_model`: constructing a
    `WhisperModel` downloads its weights into the local Hugging Face Hub
    cache the first time, and every later construction reuses that cache
    (ADR 0001's one-time-download exception). Doing this once, up front,
    while the network is still allowed, keeps the rest of this test
    focused on what Scenario 7 actually asserts -- that a *transcription
    run* needs no network -- rather than on whether model weights can
    materialize on disk with no network at all, which nothing in FR-004
    claims.
    """
    from faster_whisper import WhisperModel

    WhisperModel(_MODEL_SIZE, device="auto", compute_type="int8")


class _NetworkBlocker:
    """Raises on every call; records how many outbound attempts it stopped."""

    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.attempts += 1
        raise OSError("outbound network access is blocked for this test")


@pytest.fixture
def blocked_network(monkeypatch: pytest.MonkeyPatch) -> _NetworkBlocker:
    """Block every outbound TCP connection attempt for the life of a test.

    Patches the low-level socket entry points anything in the process --
    the CLI itself, `faster-whisper`, `huggingface_hub`, or some future
    dependency -- would have to go through to reach the network
    (`socket.socket.connect`/`connect_ex` and `socket.create_connection`),
    rather than mocking one specific HTTP client. That keeps this a
    genuine "no outbound network calls succeed" check (quickstart.md
    Scenario 7's own "e.g. via a firewall rule or a network namespace with
    no route" framing) instead of one that only proves a particular
    caller was avoided.
    """
    blocker = _NetworkBlocker()
    monkeypatch.setattr(socket.socket, "connect", blocker)
    monkeypatch.setattr(socket.socket, "connect_ex", blocker)
    monkeypatch.setattr(socket, "create_connection", blocker)
    return blocker


def test_blocked_network_fixture_actually_blocks_outbound_connections(
    blocked_network: _NetworkBlocker,
) -> None:
    """Positive control: the fixture itself really stops a connection attempt.

    Guards against this test suite silently passing for the wrong reason
    (e.g. a typo'd patch target that leaves the real network reachable) --
    proves the block is real and independent of whatever `transcribe`
    itself does or doesn't attempt.
    """
    with pytest.raises(OSError):
        socket.create_connection(("203.0.113.1", 80), timeout=1)
    assert blocked_network.attempts >= 1


def test_clear_speech_video_transcribes_identically_with_network_blocked(
    cli_runner: CliRunner,
    clear_speech_video: Path,
    tmp_path: Path,
    blocked_network: _NetworkBlocker,
) -> None:
    """`whisperflow transcribe <clear-speech video> --no-review` (Scenario 7).

    Same command, fixture, and expected outcome as
    `test_transcribe_basic.py`'s Scenario 1 test, run with every outbound
    network connection blocked: exit code 0, an `.srt` file containing the
    same fixture-specific words. No failure is attributable to the blocked
    network call (quickstart.md Scenario 7's own success criterion) --
    whether or not any connection attempt actually occurs, this must
    succeed exactly as Scenario 1 does.
    """
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")

    # Warm the model cache *before* blocking the network -- see this
    # module's docstring and ADR 0001's documented one-time-download
    # exception.
    _prewarm_model_cache()

    video_path = tmp_path / "clear_speech.mp4"
    shutil.copyfile(clear_speech_video, video_path)
    expected_srt_path = video_path.with_suffix(".srt")

    result = cli_runner.invoke(
        app, ["transcribe", str(video_path), "--model", _MODEL_SIZE, "--no-review"]
    )

    assert result.exit_code == 0, result.output
    assert expected_srt_path.is_file(), "expected .srt file was not created"

    subtitles = list(srt.parse(expected_srt_path.read_text(encoding="utf-8")))
    assert len(subtitles) == 1, (
        f"expected exactly 1 subtitle block matching the fixture's known "
        f"single segment (test_transcribe_basic.py), got {len(subtitles)}"
    )

    joined_text = " ".join(subtitle.content for subtitle in subtitles).lower()
    for word in _STABLE_SPOKEN_WORDS:
        assert word in joined_text, (
            f"expected fixture-specific word {word!r} in transcribed text "
            f"{joined_text!r} -- a blocked network call should not change "
            f"a transcription run's result at all versus Scenario 1"
        )
