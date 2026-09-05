"""Unit tests for `faster-whisper`-based transcription (T011, spec FR-002, FR-004).

Covers `transcribe_audio()`'s happy path (segment/language mapping via an
injected fake model, so most cases don't depend on a real model download),
the empty-segments "no detectable speech" outcome (FR-008; data-model.md),
its two failure modes (`ModelLoadError`, `TranscriptionError` -- both for
the initial `.transcribe()` call and for a failure partway through
iterating segments), the `on_segment` progress-callback hook, and a couple
of end-to-end sanity checks against the real `faster-whisper` "tiny" model
and fixture videos.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from audio.extract import extract_audio
from audio.video_probe import Video
from lib.errors import ModelLoadError, TranscriptionError
from transcription.transcribe import (
    COMPUTE_TYPE,
    DEVICE,
    Transcript,
    TranscriptSegment,
    transcribe_audio,
)


def _video(tmp_path: Path, name: str = "clip.mp4") -> Video:
    video_path = tmp_path / name
    video_path.touch()
    return Video(
        path=video_path,
        container_format="mp4",
        duration_seconds=12.5,
        has_audio_track=True,
    )


def _audio_track(tmp_path: Path, video: Video | None = None):
    from audio.extract import AudioTrack

    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")
    return AudioTrack(source_video=video or _video(tmp_path), extracted_path=wav_path)


class _FakeInfo:
    def __init__(self, language: str = "en") -> None:
        self.language = language


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class _FakeModel:
    """Stand-in for `faster_whisper.WhisperModel` used by the mocked tests."""

    def __init__(
        self,
        segments: list[_FakeSegment],
        language: str = "en",
        raise_on_call: Exception | None = None,
        raise_mid_iteration: Exception | None = None,
    ) -> None:
        self._segments = segments
        self._language = language
        self._raise_on_call = raise_on_call
        self._raise_mid_iteration = raise_mid_iteration
        self.calls: list[str] = []

    def transcribe(self, audio: str):
        self.calls.append(audio)
        if self._raise_on_call is not None:
            raise self._raise_on_call
        return self._segment_iterator(), _FakeInfo(self._language)

    def _segment_iterator(self):
        yield from self._segments
        if self._raise_mid_iteration is not None:
            raise self._raise_mid_iteration


class TestTranscribeAudioMocked:
    def test_returns_transcript_with_expected_fields(self, tmp_path: Path):
        video = _video(tmp_path)
        track = _audio_track(tmp_path, video)
        fake_model = _FakeModel(
            [
                _FakeSegment(0.0, 1.5, " Hello there. "),
                _FakeSegment(1.5, 3.2, "How are you?"),
            ],
            language="en",
        )

        transcript = transcribe_audio(track, model=fake_model)

        assert isinstance(transcript, Transcript)
        assert transcript.source_video is video
        assert transcript.language == "en"
        assert transcript.segments == [
            TranscriptSegment(start_seconds=0.0, end_seconds=1.5, text="Hello there."),
            TranscriptSegment(start_seconds=1.5, end_seconds=3.2, text="How are you?"),
        ]
        assert fake_model.calls == [str(track.extracted_path)]

    def test_strips_surrounding_whitespace_from_segment_text(self, tmp_path: Path):
        track = _audio_track(tmp_path)
        fake_model = _FakeModel([_FakeSegment(0.0, 1.0, "   padded text   ")])

        transcript = transcribe_audio(track, model=fake_model)

        assert transcript.segments[0].text == "padded text"

    def test_empty_segments_is_a_valid_successful_transcript(self, tmp_path: Path):
        # data-model.md: an empty segments list represents "no detectable
        # speech" (FR-008) and is a valid, successful outcome -- not an
        # error -- distinct from a failed run.
        track = _audio_track(tmp_path)
        fake_model = _FakeModel([], language="en")

        transcript = transcribe_audio(track, model=fake_model)

        assert transcript.segments == []
        assert transcript.language == "en"

    def test_segments_are_ordered_by_start_seconds(self, tmp_path: Path):
        track = _audio_track(tmp_path)
        fake_model = _FakeModel(
            [
                _FakeSegment(0.0, 1.0, "first"),
                _FakeSegment(1.0, 2.0, "second"),
                _FakeSegment(2.0, 3.0, "third"),
            ]
        )

        transcript = transcribe_audio(track, model=fake_model)

        assert [segment.text for segment in transcript.segments] == ["first", "second", "third"]
        starts = [segment.start_seconds for segment in transcript.segments]
        assert starts == sorted(starts)

    def test_on_segment_callback_invoked_once_per_segment_in_order(self, tmp_path: Path):
        track = _audio_track(tmp_path)
        fake_model = _FakeModel(
            [
                _FakeSegment(0.0, 1.0, "first"),
                _FakeSegment(1.0, 2.0, "second"),
            ]
        )
        observed: list[TranscriptSegment] = []

        transcript = transcribe_audio(track, model=fake_model, on_segment=observed.append)

        assert observed == transcript.segments

    def test_on_segment_is_optional(self, tmp_path: Path):
        track = _audio_track(tmp_path)
        fake_model = _FakeModel([_FakeSegment(0.0, 1.0, "hello")])

        # Must not raise just because no callback was supplied.
        transcript = transcribe_audio(track, model=fake_model)
        assert len(transcript.segments) == 1

    def test_transcribe_call_failure_raises_transcription_error(self, tmp_path: Path):
        track = _audio_track(tmp_path)
        fake_model = _FakeModel([], raise_on_call=RuntimeError("decoder exploded"))

        with pytest.raises(TranscriptionError) as exc_info:
            transcribe_audio(track, model=fake_model)

        assert str(track.extracted_path) in str(exc_info.value)
        assert "decoder exploded" in str(exc_info.value)
        assert not isinstance(exc_info.value, RuntimeError)

    def test_mid_iteration_failure_raises_transcription_error(self, tmp_path: Path):
        track = _audio_track(tmp_path)
        fake_model = _FakeModel(
            [_FakeSegment(0.0, 1.0, "partial")],
            raise_mid_iteration=RuntimeError("stream cut off"),
        )

        with pytest.raises(TranscriptionError) as exc_info:
            transcribe_audio(track, model=fake_model)

        assert "stream cut off" in str(exc_info.value)

    def test_iterator_creation_failure_raises_transcription_error(self, tmp_path: Path):
        track = _audio_track(tmp_path)

        class _BrokenIterable:
            def __iter__(self):
                raise RuntimeError("iterator setup failed")

        class _BrokenIteratorModel:
            def transcribe(self, audio: str):
                return _BrokenIterable(), _FakeInfo()

        with pytest.raises(TranscriptionError) as exc_info:
            transcribe_audio(track, model=_BrokenIteratorModel())

        assert "iterator setup failed" in str(exc_info.value)

    def test_on_segment_callback_failure_propagates_unwrapped(self, tmp_path: Path):
        # `on_segment` is caller-supplied (T013's own progress-reporting
        # code, not part of faster-whisper) -- a bug there must not be
        # misattributed to the ASR engine as a TranscriptionError.
        track = _audio_track(tmp_path)
        fake_model = _FakeModel([_FakeSegment(0.0, 1.0, "hello")])

        def _bad_callback(segment: TranscriptSegment) -> None:
            raise ValueError("callback bug")

        with pytest.raises(ValueError, match="callback bug"):
            transcribe_audio(track, model=fake_model, on_segment=_bad_callback)

    def test_injected_model_bypasses_whispermodel_construction(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        def _boom(*args, **kwargs):
            raise AssertionError("WhisperModel should not be constructed when model= is given")

        monkeypatch.setattr("transcription.transcribe.WhisperModel", _boom)
        track = _audio_track(tmp_path)
        fake_model = _FakeModel([_FakeSegment(0.0, 1.0, "hi")])

        transcript = transcribe_audio(track, model=fake_model)

        assert transcript.segments[0].text == "hi"

    def test_default_builds_whispermodel_with_expected_args(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        captured: dict[str, object] = {}

        class _CapturingFakeModel(_FakeModel):
            def __init__(self, model_size_or_path, **kwargs):
                captured["model_size_or_path"] = model_size_or_path
                captured.update(kwargs)
                super().__init__([_FakeSegment(0.0, 1.0, "hi")])

        monkeypatch.setattr("transcription.transcribe.WhisperModel", _CapturingFakeModel)
        track = _audio_track(tmp_path)

        transcribe_audio(track, model_size="small")

        assert captured["model_size_or_path"] == "small"
        assert captured["device"] == DEVICE == "auto"
        assert captured["compute_type"] == COMPUTE_TYPE == "int8"

    def test_default_model_size_is_base(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        captured: dict[str, object] = {}

        class _CapturingFakeModel(_FakeModel):
            def __init__(self, model_size_or_path, **kwargs):
                captured["model_size_or_path"] = model_size_or_path
                super().__init__([])

        monkeypatch.setattr("transcription.transcribe.WhisperModel", _CapturingFakeModel)
        track = _audio_track(tmp_path)

        transcribe_audio(track)

        assert captured["model_size_or_path"] == "base"

    def test_model_construction_failure_raises_model_load_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        def _raise(*args, **kwargs):
            raise OSError("corrupt model cache")

        monkeypatch.setattr("transcription.transcribe.WhisperModel", _raise)
        track = _audio_track(tmp_path)

        with pytest.raises(ModelLoadError) as exc_info:
            transcribe_audio(track, model_size="medium")

        assert "medium" in str(exc_info.value)
        assert "corrupt model cache" in str(exc_info.value)
        assert not isinstance(exc_info.value, OSError)

    def test_model_load_error_distinct_from_transcription_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        def _raise(*args, **kwargs):
            raise ValueError("bad model size")

        monkeypatch.setattr("transcription.transcribe.WhisperModel", _raise)
        track = _audio_track(tmp_path)

        with pytest.raises(ModelLoadError):
            transcribe_audio(track)


class TestTranscribeAudioRealFasterWhisper:
    """End-to-end sanity checks against the real `faster-whisper` "tiny" model.

    Skipped if the model can't be loaded at all (e.g. no network available
    on a machine's first run, before any model weights are cached) --
    mirrors `TestExtractAudioRealFfmpeg`'s ffmpeg-availability skip in
    `tests/unit/test_extract.py`.
    """

    @pytest.fixture
    def tiny_model(self):
        from faster_whisper import WhisperModel

        try:
            return WhisperModel("tiny", device="cpu", compute_type="int8")
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"faster-whisper 'tiny' model unavailable: {exc}")

    def test_clear_speech_fixture_produces_matching_transcript(
        self, clear_speech_video: Path, tiny_model, tmp_path: Path
    ):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not installed")

        video = Video(
            path=clear_speech_video,
            container_format="mp4",
            duration_seconds=3.49,
            has_audio_track=True,
        )
        track = extract_audio(video, output_path=tmp_path / "audio.wav")

        transcript = transcribe_audio(track, model=tiny_model)

        assert transcript.source_video is video
        assert transcript.language == "en"
        assert len(transcript.segments) >= 1
        joined_text = " ".join(segment.text for segment in transcript.segments).lower()
        assert "test" in joined_text
        assert transcript.segments[0].start_seconds == pytest.approx(0.0, abs=0.5)
        assert transcript.segments[-1].end_seconds <= video.duration_seconds + 0.5

    def test_silence_fixture_produces_empty_segments(
        self, silence_video: Path, tiny_model, tmp_path: Path
    ):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not installed")

        video = Video(
            path=silence_video,
            container_format="mp4",
            duration_seconds=3.0,
            has_audio_track=True,
        )
        track = extract_audio(video, output_path=tmp_path / "audio.wav")

        transcript = transcribe_audio(track, model=tiny_model)

        assert transcript.segments == []
