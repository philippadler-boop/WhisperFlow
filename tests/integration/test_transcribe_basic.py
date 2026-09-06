"""Integration test: quickstart.md Scenario 1 (T015, User Story 1).

Covers spec FR-001 (accept a video file), FR-002 (transcribe spoken audio),
FR-003 (subtitles in the video's own spoken language, no translation), and
FR-006 (write a standard-format `.srt` file) end to end via the real CLI:

    whisperflow transcribe <video> --no-review

**Expected** (quickstart.md Scenario 1): exit code 0; a `.srt` file appears
next to the input video containing subtitle blocks whose text matches what
was spoken, in the video's original language, with start/end timestamps that
line up with the audio.

Blocked on T012/T013/T014 (issues #12, #13, #14): `src/subtitles/writer.py`,
`src/cli/pipeline.py`, and their wiring into `src/cli/main.py` aren't merged
into `main` yet, so `whisperflow transcribe` still raises `NotImplementedError`
for any real invocation (see
``tests/unit/test_cli_main.py::test_transcribe_calls_not_yet_implemented_pipeline``).
This test is written now against the intended end-to-end behavior. Rather
than a blanket `xfail(strict=False)` on the whole test (which would also
swallow assertion failures, model-load failures, and malformed output once
T012-T014 land), the test runs the CLI invocation first and only calls
`pytest.xfail(...)` if the *specific*, currently-known `NotImplementedError`
is what came back; any other outcome -- including a wrong/broken
implementation once the pipeline is wired up -- fails the test normally.
Once T012/T013/T014 land, this test should simply start passing and the
`NotImplementedError` special-case below can be deleted in a follow-up.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import srt
from typer.testing import CliRunner

from cli.main import app

# Known real-transcription ground truth for tests/fixtures/clear_speech.mp4,
# captured from an actual (mocked-nothing) `faster-whisper` "tiny" run against
# this exact fixture (see docs/validation/T011.md): a single segment,
# start=0.000 end=3.200, text "Hello, this is a test on the whisper flow
# sub-title generator." Used below with reasonable tolerance so the timing
# assertions actually discriminate a correctly time-synced result from, e.g.,
# a single dummy subtitle block spanning the whole ~3.49s clip.
_KNOWN_SEGMENT_START_SECONDS = 0.0
_KNOWN_SEGMENT_END_SECONDS = 3.2
_KNOWN_SPOKEN_WORDS = ("hello", "test", "whisper")


def test_clear_speech_video_produces_correct_time_synced_srt(
    cli_runner: CliRunner, clear_speech_video: Path, tmp_path: Path
) -> None:
    """`whisperflow transcribe <clear-speech video> --no-review` (Scenario 1)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")

    # Copy the fixture into an isolated tmp dir: the default output path is
    # `<video_basename>.srt` *next to the input video* (FR-006), and this
    # keeps that write out of the repo's tests/fixtures/ directory.
    video_path = tmp_path / "clear_speech.mp4"
    shutil.copyfile(clear_speech_video, video_path)
    expected_srt_path = video_path.with_suffix(".srt")

    result = cli_runner.invoke(app, ["transcribe", str(video_path), "--no-review"])

    if isinstance(result.exception, NotImplementedError):
        pytest.xfail(
            "blocked on #12/#13/#14: whisperflow transcribe's pipeline "
            "(src/subtitles/writer.py, src/cli/pipeline.py, and its CLI "
            "wiring into src/cli/main.py) isn't implemented/merged yet -- "
            "transcribe currently raises NotImplementedError for any real "
            "invocation"
        )

    assert result.exit_code == 0, result.output
    assert expected_srt_path.is_file(), "expected .srt file was not created"

    subtitles = list(srt.parse(expected_srt_path.read_text(encoding="utf-8")))
    assert len(subtitles) >= 1, "expected at least one subtitle block"

    # Text matches what's spoken in the fixture, in the original language
    # (no translation -- FR-003).
    joined_text = " ".join(subtitle.content for subtitle in subtitles).lower()
    for word in _KNOWN_SPOKEN_WORDS:
        assert word in joined_text, f"expected spoken word {word!r} in {joined_text!r}"

    # Timings line up with the audio: ordered, each block's end >= its
    # start, and the overall span matches the known real-transcription
    # ground truth for this fixture (not just "somewhere within the whole
    # clip duration", which wouldn't catch e.g. a single dummy subtitle
    # spanning the entire ~3.49s video).
    starts = [subtitle.start.total_seconds() for subtitle in subtitles]
    ends = [subtitle.end.total_seconds() for subtitle in subtitles]
    assert starts == sorted(starts), "subtitle blocks must be time-ordered"
    assert all(
        end >= start for start, end in zip(starts, ends, strict=True)
    ), "each subtitle block's end must be >= its start"
    assert starts[0] == pytest.approx(_KNOWN_SEGMENT_START_SECONDS, abs=0.3)
    assert ends[-1] == pytest.approx(_KNOWN_SEGMENT_END_SECONDS, abs=0.3)
