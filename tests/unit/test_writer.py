"""Unit tests for transcript-to-`.srt` conversion and writing (T012, spec FR-003, FR-006).

Covers `build_subtitle_file()`'s 1:1 `TranscriptSegment` -> `SubtitleLine`
mapping (including the empty-segments "no detectable speech" case,
FR-008), and `write_subtitle_file()`'s end-to-end build-then-write
behavior against a real filesystem path.
"""

from __future__ import annotations

from pathlib import Path

from audio.video_probe import Video
from subtitles.models import SubtitleFile
from subtitles.writer import build_subtitle_file, write_subtitle_file
from transcription.transcribe import Transcript, TranscriptSegment


def _video(tmp_path: Path, name: str = "clip.mp4") -> Video:
    video_path = tmp_path / name
    video_path.touch()
    return Video(
        path=video_path,
        container_format="mp4",
        duration_seconds=12.5,
        has_audio_track=True,
    )


def _transcript(
    video: Video, segments: list[TranscriptSegment], language: str = "en"
) -> Transcript:
    return Transcript(source_video=video, language=language, segments=segments)


class TestBuildSubtitleFile:
    def test_maps_segments_to_lines_1_to_1_in_order(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(
            video,
            [
                TranscriptSegment(start_seconds=0.0, end_seconds=1.5, text="Hello there."),
                TranscriptSegment(start_seconds=1.5, end_seconds=3.2, text="How are you?"),
            ],
        )

        subtitle_file = build_subtitle_file(transcript, tmp_path / "out.srt")

        assert isinstance(subtitle_file, SubtitleFile)
        assert subtitle_file.source_video is video
        assert subtitle_file.format == "srt"
        assert subtitle_file.output_path == tmp_path / "out.srt"
        assert [line.index for line in subtitle_file.lines] == [1, 2]
        assert [line.text for line in subtitle_file.lines] == ["Hello there.", "How are you?"]
        assert subtitle_file.lines[0].start_seconds == 0.0
        assert subtitle_file.lines[0].end_seconds == 1.5
        assert subtitle_file.lines[1].start_seconds == 1.5
        assert subtitle_file.lines[1].end_seconds == 3.2

    def test_lines_start_unedited(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(
            video, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )

        subtitle_file = build_subtitle_file(transcript, tmp_path / "out.srt")

        assert subtitle_file.lines[0].edited is False

    def test_empty_segments_produces_empty_lines(self, tmp_path: Path):
        # data-model.md / FR-008: an empty transcript is a valid, successful
        # outcome, not an error -- it must convert cleanly to zero lines.
        video = _video(tmp_path)
        transcript = _transcript(video, [])

        subtitle_file = build_subtitle_file(transcript, tmp_path / "out.srt")

        assert subtitle_file.lines == []
        assert subtitle_file.compose() == ""

    def test_does_not_write_to_disk(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(
            video, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )
        output_path = tmp_path / "out.srt"

        build_subtitle_file(transcript, output_path)

        assert not output_path.exists()


class TestWriteSubtitleFile:
    def test_writes_composed_srt_to_output_path(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(
            video,
            [
                TranscriptSegment(start_seconds=0.0, end_seconds=1.5, text="Hello there."),
            ],
        )
        output_path = tmp_path / "out.srt"

        subtitle_file = write_subtitle_file(transcript, output_path)

        assert output_path.is_file()
        contents = output_path.read_text(encoding="utf-8")
        assert "Hello there." in contents
        assert "1" in contents.splitlines()[0]
        assert subtitle_file.output_path == output_path

    def test_empty_transcript_writes_empty_file(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(video, [])
        output_path = tmp_path / "out.srt"

        write_subtitle_file(transcript, output_path)

        assert output_path.is_file()
        assert output_path.read_text(encoding="utf-8") == ""

    def test_creates_parent_directories(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(
            video, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )
        output_path = tmp_path / "nested" / "dir" / "out.srt"

        write_subtitle_file(transcript, output_path)

        assert output_path.is_file()

    def test_returns_the_written_subtitle_file(self, tmp_path: Path):
        video = _video(tmp_path)
        transcript = _transcript(
            video, [TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hi")]
        )

        subtitle_file = write_subtitle_file(transcript, tmp_path / "out.srt")

        assert len(subtitle_file.lines) == 1
        assert subtitle_file.lines[0].text == "hi"
