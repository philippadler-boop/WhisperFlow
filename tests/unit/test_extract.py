"""Unit tests for audio extraction (T010, spec FR-001; data-model.md — AudioTrack).

Covers `extract_audio()`'s happy path (mono/16kHz WAV extraction via a
mocked `subprocess.run`, so most cases don't depend on a real `ffmpeg`
install), its two failure modes (`FfmpegNotFoundError`,
`AudioExtractionError`), temp-file lifecycle (auto-generated vs.
caller-supplied output path, cleanup on failure), and a couple of
end-to-end sanity checks against the real `ffmpeg` binary and fixture
videos.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest

from audio.extract import (
    AUDIO_CHANNELS,
    SAMPLE_RATE_HZ,
    AudioTrack,
    extract_audio,
)
from audio.video_probe import Video
from lib.errors import AudioExtractionError, FfmpegNotFoundError


def _video(tmp_path: Path, name: str = "clip.mp4", has_audio_track: bool = True) -> Video:
    video_path = tmp_path / name
    video_path.touch()
    return Video(
        path=video_path,
        container_format="mp4",
        duration_seconds=12.5,
        has_audio_track=has_audio_track,
    )


def _fake_ffmpeg_run(*, returncode: int = 0, stderr: str = "", write_output: bool = True):
    """Build a `subprocess.run` stand-in that mimics `ffmpeg`'s side effect.

    Real `ffmpeg` writes its output file as a side effect of the process
    call, not something `subprocess.run`'s return value carries -- the
    fake reproduces that by writing (or not) to the output path it's
    invoked with, exactly like the code under test expects.
    """

    def _run(args, **kwargs):
        if write_output:
            output_path = Path(args[-1])
            output_path.write_bytes(b"RIFF....WAVEfmt ")
        return subprocess.CompletedProcess(
            args=args, returncode=returncode, stdout="", stderr=stderr
        )

    return _run


class TestExtractAudioMocked:
    @pytest.fixture(autouse=True)
    def _ffmpeg_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """By default, pretend `ffmpeg` is present on `PATH`.

        Tests exercising the "missing ffmpeg" path override this
        themselves. Scoped to this class only (rather than
        module-level-autouse) so it can't shadow
        `TestExtractAudioRealFfmpeg`'s own real `shutil.which("ffmpeg")`
        skip-check below.
        """
        monkeypatch.setattr("shutil.which", lambda executable: f"/usr/bin/{executable}")

    def test_returns_audio_track_with_expected_fields(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        monkeypatch.setattr(subprocess, "run", _fake_ffmpeg_run())

        track = extract_audio(video)

        assert isinstance(track, AudioTrack)
        assert track.source_video == video
        assert track.sample_rate_hz == SAMPLE_RATE_HZ == 16000
        assert track.extracted_path.exists()
        assert track.extracted_path.suffix == ".wav"

        track.extracted_path.unlink()

    def test_uses_caller_supplied_output_path(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        desired_output = tmp_path / "audio.wav"
        monkeypatch.setattr(subprocess, "run", _fake_ffmpeg_run())

        track = extract_audio(video, output_path=desired_output)

        assert track.extracted_path == desired_output
        assert desired_output.exists()

    def test_accepts_str_output_path(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        desired_output = tmp_path / "audio.wav"
        monkeypatch.setattr(subprocess, "run", _fake_ffmpeg_run())

        track = extract_audio(video, output_path=str(desired_output))

        assert track.extracted_path == desired_output

    def test_ffmpeg_command_requests_mono_16khz_wav(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        captured_args: list[str] = []

        def _run(args, **kwargs):
            captured_args.extend(args)
            Path(args[-1]).write_bytes(b"RIFF....WAVEfmt ")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)

        extract_audio(video)

        assert captured_args[0] == "ffmpeg"
        assert str(video.path) in captured_args
        assert "-vn" in captured_args
        assert "-ac" in captured_args
        assert captured_args[captured_args.index("-ac") + 1] == str(AUDIO_CHANNELS)
        assert "-ar" in captured_args
        assert captured_args[captured_args.index("-ar") + 1] == str(SAMPLE_RATE_HZ)
        assert "-f" in captured_args
        assert captured_args[captured_args.index("-f") + 1] == "wav"
        assert "-y" in captured_args

    def test_ffmpeg_failure_raises_audio_extraction_error(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake_ffmpeg_run(returncode=1, stderr="Unknown encoder 'pcm'\n"),
        )

        with pytest.raises(AudioExtractionError) as exc_info:
            extract_audio(video)
        assert str(video.path) in str(exc_info.value)
        assert "Unknown encoder" in str(exc_info.value)

    def test_ffmpeg_failure_cleans_up_owned_temp_file(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        created_paths: list[Path] = []

        def _run(args, **kwargs):
            output_path = Path(args[-1])
            created_paths.append(output_path)
            # ffmpeg can leave a partial/empty file behind even on failure.
            output_path.write_bytes(b"")
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr(subprocess, "run", _run)

        with pytest.raises(AudioExtractionError):
            extract_audio(video)

        assert created_paths, "ffmpeg mock was never invoked"
        assert not created_paths[0].exists()

    def test_ffmpeg_failure_does_not_delete_caller_supplied_output(
        self, monkeypatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        desired_output = tmp_path / "audio.wav"
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake_ffmpeg_run(returncode=1, stderr="boom", write_output=True),
        )

        with pytest.raises(AudioExtractionError):
            extract_audio(video, output_path=desired_output)

        # A caller-supplied path is the caller's own file to manage --
        # extraction only deletes files it created itself.
        assert desired_output.exists()

    def test_missing_ffmpeg_binary_raises_ffmpeg_not_found(self, monkeypatch, tmp_path: Path):
        video = _video(tmp_path)
        monkeypatch.setattr("shutil.which", lambda executable: None)

        with pytest.raises(FfmpegNotFoundError) as exc_info:
            extract_audio(video)
        assert exc_info.value.executable == "ffmpeg"

    def test_ffmpeg_disappearing_at_call_time_raises_ffmpeg_not_found(
        self, monkeypatch, tmp_path: Path
    ):
        video = _video(tmp_path)

        def _raise_file_not_found(*args, **kwargs):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(subprocess, "run", _raise_file_not_found)

        with pytest.raises(FfmpegNotFoundError):
            extract_audio(video)

    def test_ffmpeg_disappearing_at_call_time_cleans_up_owned_temp_file(
        self, monkeypatch, tmp_path: Path
    ):
        # `resolved_output = _new_temp_wav_path()` creates an empty file on
        # disk (via mkstemp) *before* subprocess.run ever runs -- if ffmpeg
        # disappears mid-call (the same race the test above exercises),
        # that owned temp file must not be left behind in the OS temp
        # directory.
        video = _video(tmp_path)
        created_paths: list[Path] = []

        import audio.extract as extract_module

        original_new_temp_wav_path = extract_module._new_temp_wav_path

        def _capturing_new_temp_wav_path() -> Path:
            path = original_new_temp_wav_path()
            created_paths.append(path)
            return path

        monkeypatch.setattr(extract_module, "_new_temp_wav_path", _capturing_new_temp_wav_path)

        def _raise_file_not_found(*args, **kwargs):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(subprocess, "run", _raise_file_not_found)

        with pytest.raises(FfmpegNotFoundError):
            extract_audio(video)

        assert created_paths, "temp path was never created"
        assert not created_paths[0].exists()

    def test_ffmpeg_success_without_writing_output_raises_extraction_error(
        self, monkeypatch, tmp_path: Path
    ):
        # If ffmpeg ever exits 0 without writing an output file, extraction
        # must fail clearly here rather than returning an AudioTrack that
        # points at a missing file (FR-007).
        video = _video(tmp_path)
        monkeypatch.setattr(subprocess, "run", _fake_ffmpeg_run(returncode=0, write_output=False))

        with pytest.raises(AudioExtractionError):
            extract_audio(video)

    def test_ffmpeg_success_with_empty_output_raises_extraction_error(
        self, monkeypatch, tmp_path: Path
    ):
        # An output file that exists but is zero-length is just as unusable
        # as a missing one.
        video = _video(tmp_path)

        def _run(args, **kwargs):
            Path(args[-1]).write_bytes(b"")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)

        with pytest.raises(AudioExtractionError):
            extract_audio(video)

    def test_ffmpeg_success_without_writing_output_cleans_up_owned_temp_file(
        self, monkeypatch, tmp_path: Path
    ):
        video = _video(tmp_path)
        created_paths: list[Path] = []

        def _run(args, **kwargs):
            created_paths.append(Path(args[-1]))
            # Deliberately does not write to the output path, unlike real
            # ffmpeg -- simulates ffmpeg exiting 0 without producing output.
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", _run)

        with pytest.raises(AudioExtractionError):
            extract_audio(video)

        assert created_paths, "ffmpeg mock was never invoked"
        assert not created_paths[0].exists()

    def test_ffmpeg_success_leaving_preexisting_output_untouched_raises_extraction_error(
        self, monkeypatch, tmp_path: Path
    ):
        # Residual gap found during PR #85 validation: a caller-supplied
        # output_path that already exists with non-empty content, where
        # ffmpeg exits 0 without actually touching it, must still raise --
        # not silently return an AudioTrack pointing at the stale bytes.
        # The exists()/non-empty check alone can't catch this because the
        # pre-existing file already satisfies both conditions before
        # ffmpeg ever runs.
        video = _video(tmp_path)
        desired_output = tmp_path / "audio.wav"
        original_content = b"PRE-EXISTING-AUDIO-BYTES"
        desired_output.write_bytes(original_content)

        monkeypatch.setattr(subprocess, "run", _fake_ffmpeg_run(returncode=0, write_output=False))

        with pytest.raises(AudioExtractionError):
            extract_audio(video, output_path=desired_output)

        # A caller-supplied path is the caller's own file to manage --
        # raising an error must not delete or modify it.
        assert desired_output.exists()
        assert desired_output.read_bytes() == original_content

    def test_no_audio_track_video_surfaces_as_extraction_error(
        self, monkeypatch, tmp_path: Path
    ):
        # A video with no audio stream at all is exactly the case ffmpeg
        # itself fails on (nothing to map to the output) -- this module
        # doesn't special-case has_audio_track itself (that's a pipeline
        # concern, data-model.md/FR-008), it just surfaces ffmpeg's own
        # non-zero exit as AudioExtractionError like any other failure.
        video = _video(tmp_path, has_audio_track=False)
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake_ffmpeg_run(
                returncode=1,
                stderr="Output file does not contain any stream\n",
                write_output=False,
            ),
        )

        with pytest.raises(AudioExtractionError):
            extract_audio(video)


class TestExtractAudioRealFfmpeg:
    """End-to-end sanity checks against the real `ffmpeg` binary.

    Skipped if `ffmpeg` isn't installed, matching CI's dedicated "Install
    ffmpeg" step (`.github/workflows/ci.yml`) rather than failing a
    developer's machine that hasn't installed it.
    """

    def test_clear_speech_fixture_produces_mono_16khz_wav(self, clear_speech_video: Path):
        import shutil

        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not installed")

        video = Video(
            path=clear_speech_video,
            container_format="mp4",
            duration_seconds=3.49,
            has_audio_track=True,
        )

        track = extract_audio(video)
        try:
            assert track.extracted_path.exists()
            with wave.open(str(track.extracted_path), "rb") as wav_file:
                assert wav_file.getframerate() == SAMPLE_RATE_HZ
                assert wav_file.getnchannels() == AUDIO_CHANNELS
                assert wav_file.getnframes() > 0
        finally:
            track.extracted_path.unlink(missing_ok=True)

    def test_silence_fixture_still_produces_a_wav_file(self, silence_video: Path):
        # silence.mp4 has a silent audio *stream* (not zero streams), so
        # extraction succeeds and produces a real (if silent) WAV file --
        # distinguishing "no detectable speech" from "extraction failed"
        # is a downstream (transcription-time, FR-008) concern, not this
        # module's.
        import shutil

        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not installed")

        video = Video(
            path=silence_video,
            container_format="mp4",
            duration_seconds=3.0,
            has_audio_track=True,
        )

        track = extract_audio(video)
        try:
            assert track.extracted_path.exists()
            with wave.open(str(track.extracted_path), "rb") as wav_file:
                assert wav_file.getframerate() == SAMPLE_RATE_HZ
                assert wav_file.getnchannels() == AUDIO_CHANNELS
        finally:
            track.extracted_path.unlink(missing_ok=True)
