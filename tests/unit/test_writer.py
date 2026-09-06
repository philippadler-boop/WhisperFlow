"""Unit tests for T012 (`Transcript` -> `SubtitleFile` conversion and `.srt` writing).

Covers data-model.md's SubtitleLine "initially derived 1:1 from a
TranscriptSegment" rule and spec FR-003/FR-006 -- `src/subtitles/writer.py`
bridges T011's `Transcript`/`TranscriptSegment` to T005's
`SubtitleFile`/`SubtitleLine` and writes the composed result to disk.
"""

from __future__ import annotations

from pathlib import Path

import srt

from audio.video_probe import Video
from subtitles.models import SubtitleFile
from subtitles.writer import transcript_to_subtitle_file, write_subtitles
from transcription.transcribe import Transcript, TranscriptSegment


def _video(tmp_path: Path) -> Video:
    return Video(
        path=tmp_path / "clip.mp4",
        container_format="mp4",
        duration_seconds=10.0,
        has_audio_track=True,
    )


class TestTranscriptToSubtitleFile:
    def test_converts_segments_to_1_based_indexed_lines(self, tmp_path: Path) -> None:
        video = _video(tmp_path)
        transcript = Transcript(
            source_video=video,
            language="en",
            segments=[
                TranscriptSegment(start_seconds=0.0, end_seconds=1.5, text="Hello there."),
                TranscriptSegment(start_seconds=1.5, end_seconds=3.2, text="How are you?"),
            ],
        )

        subtitle_file = transcript_to_subtitle_file(transcript)

        assert isinstance(subtitle_file, SubtitleFile)
        assert subtitle_file.source_video is video
        assert subtitle_file.format == "srt"
        assert [line.index for line in subtitle_file.lines] == [1, 2]
        assert [line.text for line in subtitle_file.lines] == ["Hello there.", "How are you?"]
        assert subtitle_file.lines[0].start_seconds == 0.0
        assert subtitle_file.lines[0].end_seconds == 1.5
        assert subtitle_file.lines[1].start_seconds == 1.5
        assert subtitle_file.lines[1].end_seconds == 3.2

    def test_lines_default_to_not_edited(self, tmp_path: Path) -> None:
        transcript = Transcript(
            source_video=_video(tmp_path),
            language="en",
            segments=[TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="Hi")],
        )

        subtitle_file = transcript_to_subtitle_file(transcript)

        assert subtitle_file.lines[0].edited is False

    def test_empty_segments_produces_empty_lines(self, tmp_path: Path) -> None:
        # FR-008: "no detectable speech" is a valid, successful outcome --
        # an empty Transcript converts cleanly to an empty SubtitleFile,
        # not an error.
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])

        subtitle_file = transcript_to_subtitle_file(transcript)

        assert subtitle_file.lines == []
        assert subtitle_file.compose() == ""

    def test_output_path_not_set_by_default(self, tmp_path: Path) -> None:
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])

        subtitle_file = transcript_to_subtitle_file(transcript)

        assert subtitle_file.output_path is None

    def test_output_path_is_recorded_but_not_written(self, tmp_path: Path) -> None:
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])
        target = tmp_path / "out.srt"

        subtitle_file = transcript_to_subtitle_file(transcript, output_path=target)

        assert subtitle_file.output_path == target
        assert not target.exists()

    def test_output_path_accepts_str(self, tmp_path: Path) -> None:
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])
        target = tmp_path / "out.srt"

        subtitle_file = transcript_to_subtitle_file(transcript, output_path=str(target))

        assert subtitle_file.output_path == target


class TestWriteSubtitles:
    def test_writes_composed_srt_to_output_path(self, tmp_path: Path) -> None:
        video = _video(tmp_path)
        transcript = Transcript(
            source_video=video,
            language="en",
            segments=[
                TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="First line"),
                TranscriptSegment(start_seconds=1.5, end_seconds=3.0, text="Second line"),
            ],
        )
        target = tmp_path / "out.srt"

        subtitle_file = write_subtitles(transcript, target)

        assert subtitle_file.output_path == target
        assert target.is_file()
        composed = target.read_text(encoding="utf-8")
        parsed = list(srt.parse(composed))
        assert [s.content for s in parsed] == ["First line", "Second line"]
        assert [s.index for s in parsed] == [1, 2]

    def test_writes_empty_file_for_no_speech_transcript(self, tmp_path: Path) -> None:
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])
        target = tmp_path / "out.srt"

        subtitle_file = write_subtitles(transcript, target)

        assert target.is_file()
        assert target.read_text(encoding="utf-8") == ""
        assert subtitle_file.lines == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])
        target = tmp_path / "nested" / "dir" / "out.srt"

        write_subtitles(transcript, target)

        assert target.is_file()

    def test_accepts_str_output_path(self, tmp_path: Path) -> None:
        transcript = Transcript(source_video=_video(tmp_path), language="en", segments=[])
        target = tmp_path / "out.srt"

        subtitle_file = write_subtitles(transcript, str(target))

        assert subtitle_file.output_path == target
        assert target.is_file()

    def test_returned_subtitle_file_matches_written_content(self, tmp_path: Path) -> None:
        transcript = Transcript(
            source_video=_video(tmp_path),
            language="en",
            segments=[TranscriptSegment(start_seconds=0.0, end_seconds=2.0, text="Only line")],
        )
        target = tmp_path / "out.srt"

        subtitle_file = write_subtitles(transcript, target)

        assert subtitle_file.compose() == target.read_text(encoding="utf-8")
