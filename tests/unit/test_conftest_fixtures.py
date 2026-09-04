"""Unit tests for the shared fixtures in tests/conftest.py (T003).

These assert the fixtures themselves are usable -- a real CliRunner, and
sample video files that actually exist and contain the audio
characteristics (present vs. silent) the fixture names promise -- not
any application behavior (there is none to exercise yet).
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from typer.testing import CliRunner


def test_cli_runner_is_typer_cli_runner(cli_runner: CliRunner) -> None:
    assert isinstance(cli_runner, CliRunner)


def test_clear_speech_video_fixture_exists(clear_speech_video: Path) -> None:
    assert clear_speech_video.is_file()
    assert clear_speech_video.suffix == ".mp4"
    assert clear_speech_video.stat().st_size > 0


def test_silence_video_fixture_exists(silence_video: Path) -> None:
    assert silence_video.is_file()
    assert silence_video.suffix == ".mp4"
    assert silence_video.stat().st_size > 0


def test_fixture_videos_are_small(
    clear_speech_video: Path, silence_video: Path
) -> None:
    # Keep the repo lightweight: both sample clips should be a few
    # seconds long and well under a megabyte.
    max_bytes = 1_000_000
    assert clear_speech_video.stat().st_size < max_bytes
    assert silence_video.stat().st_size < max_bytes


def _extract_audio_to_wav(video_path: Path, wav_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav_path),
        ],
        check=True,
    )


def _max_abs_amplitude(wav_path: Path) -> int:
    with wave.open(str(wav_path), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
    if not frames:
        return 0
    sample_width = 2  # 16-bit PCM
    samples = [
        int.from_bytes(frames[i : i + sample_width], "little", signed=True)
        for i in range(0, len(frames) - len(frames) % sample_width, sample_width)
    ]
    return max(abs(s) for s in samples)


def test_clear_speech_video_has_nonsilent_audio(
    clear_speech_video: Path, tmp_path: Path
) -> None:
    wav_path = tmp_path / "clear_speech.wav"
    _extract_audio_to_wav(clear_speech_video, wav_path)
    assert _max_abs_amplitude(wav_path) > 1000


def test_silence_video_has_silent_audio(
    silence_video: Path, tmp_path: Path
) -> None:
    wav_path = tmp_path / "silence.wav"
    _extract_audio_to_wav(silence_video, wav_path)
    assert _max_abs_amplitude(wav_path) == 0
