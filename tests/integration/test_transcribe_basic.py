"""Integration test: quickstart.md Scenario 1 (T015, User Story 1).

Covers spec FR-001 (accept a video file), FR-002 (transcribe spoken audio),
FR-003 (subtitles in the video's own spoken language, no translation), and
FR-006 (write a standard-format `.srt` file) end to end via the real CLI:

    whisperflow transcribe <video> --no-review

**Expected** (quickstart.md Scenario 1): exit code 0; a `.srt` file appears
next to the input video containing subtitle blocks whose text matches what
was spoken, in the video's original language, with start/end timestamps that
line up with the audio.

The test exercises the real pipeline, including the tiny model and timing
assertions, so a regression to the old unimplemented placeholder fails here.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import srt
from typer.testing import CliRunner

from cli.main import app

# Known real-transcription shape for tests/fixtures/clear_speech.mp4, captured
# from an actual (mocked-nothing) `faster-whisper` "tiny" run against this
# exact fixture (see docs/validation/T011.md): a single segment,
# start=0.000 end=3.200. The tiny model's exact lexical output can vary by
# platform and runtime, so the assertion below checks stable fixture-specific
# words rather than a brittle full transcript equality.
_KNOWN_SEGMENT_START_SECONDS = 0.0
_KNOWN_SEGMENT_END_SECONDS = 3.2
_KNOWN_SEGMENT_TIMINGS = (
    (_KNOWN_SEGMENT_START_SECONDS, _KNOWN_SEGMENT_END_SECONDS),
)
_STABLE_SPOKEN_WORDS = (
    "hello",
    "test",
    "generator",
)


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

    result = cli_runner.invoke(
        app, ["transcribe", str(video_path), "--model", "tiny", "--no-review"]
    )

    assert result.exit_code == 0, result.output
    assert expected_srt_path.is_file(), "expected .srt file was not created"

    subtitles = list(srt.parse(expected_srt_path.read_text(encoding="utf-8")))
    # The fixture's known ground truth (see docs/validation/T011.md) is a
    # single segment spanning 0.000-3.200s. Assert the exact block count so a
    # result split into multiple blocks (or otherwise not matching the
    # recorded segment shape) fails here, rather than only checking the
    # first start and last end -- which would also pass e.g. two blocks at
    # 0.0-0.1 and 2.8-3.2.
    assert len(subtitles) == 1, (
        f"expected exactly 1 subtitle block matching the fixture's known "
        f"single segment, got {len(subtitles)}"
    )

    # Text matches what's spoken in the fixture, in the original language
    # (no translation -- FR-003). Exact tiny-model wording is intentionally
    # not required because decoding can vary across platforms and runtimes.
    joined_text = " ".join(subtitle.content for subtitle in subtitles).lower()
    actual_words = tuple(re.findall(r"[a-z]+(?:-[a-z]+)?", joined_text))
    assert len(actual_words) >= len(_STABLE_SPOKEN_WORDS), (
        f"expected a non-trivial transcription, got {actual_words!r} "
        f"from {joined_text!r}"
    )
    missing_words = set(_STABLE_SPOKEN_WORDS).difference(actual_words)
    assert not missing_words, (
        f"expected fixture-specific words {_STABLE_SPOKEN_WORDS!r}, "
        f"missing {sorted(missing_words)!r} from {joined_text!r}"
    )

    # Timing lines up with the audio: the single block's start/end must each
    # match the known real-transcription ground truth for this fixture
    # (not just "the first start and last end fall somewhere within the
    # whole clip duration", which wouldn't catch e.g. a result split into
    # blocks at 0.0-0.1 and 2.8-3.2 -- neither of which matches the recorded
    # single 0.0-3.2 segment despite passing a first-start/last-end-only
    # check).
    actual_timings = tuple(
        (
            subtitle.start.total_seconds(),
            subtitle.end.total_seconds(),
        )
        for subtitle in subtitles
    )
    for (actual_start, actual_end), (expected_start, expected_end) in zip(
        actual_timings, _KNOWN_SEGMENT_TIMINGS, strict=True
    ):
        assert actual_end >= actual_start, "subtitle block's end must be >= its start"
        assert actual_start == pytest.approx(expected_start, abs=0.3)
        assert actual_end == pytest.approx(expected_end, abs=0.3)
