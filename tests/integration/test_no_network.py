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
one-time initial weight download that ADR 0001 explicitly carves out. That
ordering (cache warmed, *then* network blocked) is enforced structurally via
the `blocked_network` fixture depending on `warm_model_cache`, not by the
order in which a test body happens to call things -- see `blocked_network`'s
docstring.
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
# with the network blocked, not just "succeed with some output". Kept in
# sync with test_transcribe_basic.py's `_STABLE_SPOKEN_WORDS` /
# `_KNOWN_SEGMENT_TIMINGS`: a single segment spanning 0.000-3.200s.
_STABLE_SPOKEN_WORDS = ("hello", "test", "generator")
_KNOWN_SEGMENT_START_SECONDS = 0.0
_KNOWN_SEGMENT_END_SECONDS = 3.2
_KNOWN_SEGMENT_TIMINGS = (
    (_KNOWN_SEGMENT_START_SECONDS, _KNOWN_SEGMENT_END_SECONDS),
)


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


@pytest.fixture(scope="session")
def warm_model_cache() -> None:
    """Ensure the `tiny` model's weights are cached locally, network allowed.

    Session-scoped so this (potentially network-using) download happens at
    most once per test run. Declared as a dependency of `blocked_network`
    below rather than called from inside a test body: pytest completes a
    fixture's own setup before running the setup of anything that depends
    on it, so making `blocked_network` require `warm_model_cache` makes
    "cache warmed, then network blocked" a structural fact of pytest's
    fixture dependency graph -- true regardless of test collection order,
    module ordering, or a random-order plugin -- rather than an artifact of
    where a line happens to sit inside a test function's body.
    """
    _prewarm_model_cache()


@pytest.fixture
def blocked_network(
    monkeypatch: pytest.MonkeyPatch, warm_model_cache: None
) -> _NetworkBlocker:
    """Block every outbound connection attempt for the life of a test.

    Depends on `warm_model_cache` (see its docstring) so the model cache is
    always populated *before* this fixture patches anything -- constructing
    a `WhisperModel` after this fixture runs would otherwise itself hit the
    now-blocked network and error out rather than exercising Scenario 7.

    Patches the low-level socket entry points anything in the process --
    the CLI itself, `faster-whisper`, `huggingface_hub`, or some future
    dependency -- would have to go through to reach the network
    (`socket.socket.connect`/`connect_ex`, `socket.create_connection`, and
    `socket.getaddrinfo` for DNS resolution), rather than mocking one
    specific HTTP client. That keeps this a genuine "no outbound network
    calls succeed" check (quickstart.md Scenario 7's own "e.g. via a
    firewall rule or a network namespace with no route" framing) instead of
    one that only proves a particular caller was avoided.
    """
    blocker = _NetworkBlocker()
    monkeypatch.setattr(socket.socket, "connect", blocker)
    monkeypatch.setattr(socket.socket, "connect_ex", blocker)
    monkeypatch.setattr(socket, "create_connection", blocker)
    monkeypatch.setattr(socket, "getaddrinfo", blocker)
    return blocker


def test_blocked_network_fixture_actually_blocks_outbound_connections(
    blocked_network: _NetworkBlocker,
) -> None:
    """Positive control: the fixture itself really stops a connection attempt.

    Guards against this test suite silently passing for the wrong reason
    (e.g. a typo'd patch target that leaves the real network reachable) --
    proves the block is real and independent of whatever `transcribe`
    itself does or doesn't attempt. Exercises all three patched entry
    points individually, since library code may construct a raw socket and
    call `.connect()`/`.connect_ex()` directly rather than going through
    `socket.create_connection`.
    """
    with pytest.raises(OSError):
        socket.create_connection(("203.0.113.1", 80), timeout=1)

    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError):
            raw_socket.connect(("203.0.113.1", 80))
        with pytest.raises(OSError):
            raw_socket.connect_ex(("203.0.113.1", 80))
    finally:
        raw_socket.close()

    assert blocked_network.attempts >= 3


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
    same fixture-specific words *and* the same segment timing. No failure
    is attributable to the blocked network call (quickstart.md Scenario 7's
    own success criterion) -- whether or not any connection attempt
    actually occurs, this must succeed exactly as Scenario 1 does.

    The model cache is warmed with the network still allowed by the
    `blocked_network` fixture's `warm_model_cache` dependency (see that
    fixture's docstring) before this body ever runs.
    """
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")

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

    # Timing must match Scenario 1's recorded ground truth too, not just
    # word presence -- otherwise this test only partially verifies "produces
    # the same successful outcome ... identically" (this module's own
    # docstring, quickstart.md Scenario 7).
    actual_timings = tuple(
        (subtitle.start.total_seconds(), subtitle.end.total_seconds())
        for subtitle in subtitles
    )
    for (actual_start, actual_end), (expected_start, expected_end) in zip(
        actual_timings, _KNOWN_SEGMENT_TIMINGS, strict=True
    ):
        assert actual_end >= actual_start, "subtitle block's end must be >= its start"
        assert actual_start == pytest.approx(expected_start, abs=0.3)
        assert actual_end == pytest.approx(expected_end, abs=0.3)
