"""Unit tests for video probing (T009, spec FR-001/FR-007).

Covers data-model.md's `Video` entity (`container_format`,
`duration_seconds`, `has_audio_track`) and its validation rules, plus the
FR-007 error paths `probe_video()` must raise instead of crashing: an
unsupported/undetectable format, an oversized video, and a missing
`ffprobe` binary.

Most edge cases (format/duration/audio-stream resolution) drive
`probe_video()` through a mocked `subprocess.run` so they don't depend on
having real sample media for every combination; a couple of tests run
against the real fixture videos end to end to confirm the real `ffprobe`
invocation and JSON parsing actually work.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from audio.video_probe import Video, probe_video
from lib.errors import (
    MAX_DURATION_SECONDS,
    FfmpegNotFoundError,
    MaxDurationExceededError,
    UnsupportedVideoFormatError,
)


def _ffprobe_result(
    *,
    format_name: str = "mov,mp4,m4a,3gp,3g2,mj2",
    duration: str | None = "12.5",
    has_video_stream: bool = True,
    has_audio_stream: bool = True,
    returncode: int = 0,
) -> subprocess.CompletedProcess:
    streams = []
    if has_video_stream:
        streams.append({"codec_type": "video", "codec_name": "h264"})
    if has_audio_stream:
        streams.append({"codec_type": "audio", "codec_name": "aac"})

    format_section: dict[str, object] = {"format_name": format_name}
    if duration is not None:
        format_section["duration"] = duration

    payload = {"streams": streams, "format": format_section}
    stdout = "" if returncode != 0 else json.dumps(payload)
    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=""
    )


@pytest.fixture(autouse=True)
def _ffprobe_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """By default, pretend `ffprobe` is present on `PATH`.

    Individual tests that exercise the "missing ffprobe" path override
    this via their own `monkeypatch.setattr("shutil.which", ...)`.
    """
    monkeypatch.setattr("shutil.which", lambda executable: f"/usr/bin/{executable}")


class TestProbeVideoMocked:
    def test_returns_video_with_expected_fields(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(duration="42.75"),
        )

        video = probe_video(video_path)

        assert isinstance(video, Video)
        assert video.path == video_path
        assert video.container_format == "mp4"
        assert video.duration_seconds == pytest.approx(42.75)
        assert video.has_audio_track is True

    def test_mov_extension_resolves_to_mov_not_mp4(self, monkeypatch, tmp_path: Path):
        # ffprobe reports the same shared demuxer tokens for both; the
        # extension disambiguates which supported format it actually is.
        video_path = tmp_path / "clip.mov"
        video_path.touch()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ffprobe_result())

        video = probe_video(video_path)

        assert video.container_format == "mov"

    def test_mkv_extension_and_matroska_demuxer(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mkv"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(format_name="matroska,webm"),
        )

        video = probe_video(video_path)

        assert video.container_format == "mkv"

    def test_no_audio_track_is_reported_false(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(has_audio_stream=False),
        )

        video = probe_video(video_path)

        assert video.has_audio_track is False

    def test_actual_container_wins_over_a_mismatched_extension(self, monkeypatch, tmp_path: Path):
        # Named .mp4, but ffprobe says it's really a Matroska file -- since
        # Matroska *is* a supported format, it's accepted and correctly
        # reported as "mkv", not silently trusted as "mp4" from the
        # extension alone (data-model.md: container_format is "Detected
        # from the file").
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(format_name="matroska,webm"),
        )

        video = probe_video(video_path)

        assert video.container_format == "mkv"

    def test_unrecognized_container_is_rejected_even_with_supported_extension(
        self, monkeypatch, tmp_path: Path
    ):
        # Named .mp4, but ffprobe says it's really an AVI file -- an
        # extension that merely *looks* supported must not override what
        # ffprobe actually detected.
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(format_name="avi"),
        )

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.detected_format == "avi"

    def test_ffprobe_failure_raises_unsupported_format(self, monkeypatch, tmp_path: Path):
        # e.g. a non-media file such as README.md (quickstart.md Scenario 5).
        not_a_video = tmp_path / "README.md"
        not_a_video.write_text("just some text\n")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ffprobe_result(returncode=1))

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(not_a_video)
        assert exc_info.value.detected_format is None

    def test_unparseable_ffprobe_output_raises_unsupported_format(
        self, monkeypatch, tmp_path: Path
    ):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                args=["ffprobe"], returncode=0, stdout="not json", stderr=""
            ),
        )

        with pytest.raises(UnsupportedVideoFormatError):
            probe_video(video_path)

    def test_missing_duration_raises_unsupported_format(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(duration=None),
        )

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(video_path)
        # The container format is already validated as supported (mp4) by
        # this point -- the real failure is an undetectable duration, so
        # detected_format must not echo back the (valid) container format,
        # which would produce a self-contradictory "unsupported format
        # 'mp4'" message.
        assert exc_info.value.detected_format is None

    def test_webm_extension_and_matroska_demuxer_is_rejected(self, monkeypatch, tmp_path: Path):
        # A real .webm file reports the same "matroska,webm" format_name as
        # a real .mkv file -- ffprobe's tokens alone can't tell them apart.
        # webm isn't in SUPPORTED_VIDEO_FORMATS, so it must not be guessed
        # into "mkv" just because they share a demuxer.
        video_path = tmp_path / "clip.webm"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(format_name="matroska,webm"),
        )

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.detected_format == "webm"

    def test_3gp_extension_and_shared_mp4_demuxer_is_rejected(self, monkeypatch, tmp_path: Path):
        # A real .3gp file reports the same shared demuxer tokens as
        # mp4/mov ("mov,mp4,m4a,3gp,3g2,mj2"). 3gp isn't in
        # SUPPORTED_VIDEO_FORMATS, so it must not be guessed into "mov" (or
        # "mp4") just because they share a demuxer.
        video_path = tmp_path / "clip.3gp"
        video_path.touch()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ffprobe_result())

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.detected_format == "3gp"

    def test_mkv_extension_with_mp4_mov_family_container_is_rejected(
        self, monkeypatch, tmp_path: Path
    ):
        # A file named .mkv but whose real container is mp4/mov-family
        # (ffprobe reports the shared "mov,mp4,m4a,3gp,3g2,mj2" demuxer
        # tokens, with no matroska-related token at all) must not be
        # accepted as "mkv" just because "mkv" happens to itself be a
        # SUPPORTED_VIDEO_FORMATS entry -- the extension can disambiguate
        # *within* a family ffprobe already matched, but must never be
        # returned unchecked when it collides with an entirely different
        # supported format ffprobe never actually detected.
        video_path = tmp_path / "clip.mkv"
        video_path.touch()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ffprobe_result())

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.detected_format is None

    @pytest.mark.parametrize("extension", ["m4a", "3g2", "mj2"])
    def test_mp4_mov_family_siblings_are_rejected(
        self, monkeypatch, tmp_path: Path, extension: str
    ):
        # Same shared demuxer as the .3gp case above -- these sibling
        # extensions aren't in SUPPORTED_VIDEO_FORMATS either, so they must
        # not be guessed into "mp4"/"mov" just because they share a demuxer.
        video_path = tmp_path / f"clip.{extension}"
        video_path.touch()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ffprobe_result())

        with pytest.raises(UnsupportedVideoFormatError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.detected_format == extension

    def test_oversized_video_raises_max_duration_exceeded(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        over_limit = MAX_DURATION_SECONDS + 1
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(duration=str(over_limit)),
        )

        with pytest.raises(MaxDurationExceededError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.duration_seconds == pytest.approx(over_limit)

    def test_duration_exactly_at_max_is_accepted(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _ffprobe_result(duration=str(MAX_DURATION_SECONDS)),
        )

        video = probe_video(video_path)

        assert video.duration_seconds == pytest.approx(MAX_DURATION_SECONDS)

    def test_missing_ffprobe_binary_raises_ffmpeg_not_found(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr("shutil.which", lambda executable: None)

        with pytest.raises(FfmpegNotFoundError) as exc_info:
            probe_video(video_path)
        assert exc_info.value.executable == "ffprobe"

    def test_ffprobe_disappearing_at_call_time_raises_ffmpeg_not_found(
        self, monkeypatch, tmp_path: Path
    ):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()

        def _raise_file_not_found(*args, **kwargs):
            raise FileNotFoundError("ffprobe")

        monkeypatch.setattr(subprocess, "run", _raise_file_not_found)

        with pytest.raises(FfmpegNotFoundError):
            probe_video(video_path)

    def test_accepts_str_path_as_well_as_path_object(self, monkeypatch, tmp_path: Path):
        video_path = tmp_path / "clip.mp4"
        video_path.touch()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ffprobe_result())

        video = probe_video(str(video_path))

        assert video.path == video_path


class TestProbeVideoRealFfprobe:
    """End-to-end sanity checks against the real `ffprobe` binary.

    Skipped if `ffprobe` isn't installed, matching CI's dedicated
    "Install ffmpeg" step (`.github/workflows/ci.yml`) rather than failing
    a developer's machine that hasn't installed it.
    """

    def test_clear_speech_fixture(self, clear_speech_video: Path):
        pytest.importorskip("shutil")
        import shutil

        if shutil.which("ffprobe") is None:
            pytest.skip("ffprobe not installed")

        video = probe_video(clear_speech_video)

        assert video.container_format == "mp4"
        assert video.has_audio_track is True
        assert video.duration_seconds > 0

    def test_silence_fixture_still_has_an_audio_track(self, silence_video: Path):
        # silence.mp4 has a (silent) audio *stream* -- has_audio_track is
        # about stream presence, not detectable speech (FR-008 is a
        # downstream, transcription-time concern; see data-model.md).
        import shutil

        if shutil.which("ffprobe") is None:
            pytest.skip("ffprobe not installed")

        video = probe_video(silence_video)

        assert video.container_format == "mp4"
        assert video.has_audio_track is True
        assert video.duration_seconds > 0
