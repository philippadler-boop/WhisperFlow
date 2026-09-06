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
This test is written now against the intended end-to-end behavior and marked
`xfail(strict=False)` so it doesn't block CI while those tasks land; it's
expected to flip to XPASS once they do, at which point the marker below
should be removed (and, per `strict=False`, an XPASS is not itself a failure
in the meantime).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import srt
from typer.testing import CliRunner

from cli.main import app

pytestmark = pytest.mark.xfail(
    reason=(
        "blocked on #12/#13/#14: whisperflow transcribe's pipeline "
        "(src/subtitles/writer.py, src/cli/pipeline.py, and its CLI wiring "
        "into src/cli/main.py) isn't implemented/merged yet -- transcribe "
        "currently raises NotImplementedError for any real invocation"
    ),
    strict=False,
)

# Known properties of tests/fixtures/clear_speech.mp4 (see
# tests/unit/test_transcribe.py's own real-model sanity check, which this
# mirrors at the CLI/integration level rather than the transcription-module
# level).
_KNOWN_DURATION_SECONDS = 3.49
_KNOWN_SPOKEN_WORD = "test"


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

    assert result.exit_code == 0, result.output
    assert expected_srt_path.is_file(), "expected .srt file was not created"

    subtitles = list(srt.parse(expected_srt_path.read_text(encoding="utf-8")))
    assert len(subtitles) >= 1, "expected at least one subtitle block"

    # Text matches what's spoken in the fixture, in the original language
    # (no translation -- FR-003).
    joined_text = " ".join(subtitle.content for subtitle in subtitles).lower()
    assert _KNOWN_SPOKEN_WORD in joined_text

    # Timings line up with the audio: ordered, each block's end >= its
    # start, and within the fixture's known ~3.49s duration.
    starts = [subtitle.start.total_seconds() for subtitle in subtitles]
    ends = [subtitle.end.total_seconds() for subtitle in subtitles]
    assert starts == sorted(starts), "subtitle blocks must be time-ordered"
    assert all(
        end >= start for start, end in zip(starts, ends, strict=True)
    ), "each subtitle block's end must be >= its start"
    assert starts[0] == pytest.approx(0.0, abs=0.5)
    assert ends[-1] <= _KNOWN_DURATION_SECONDS + 0.5
