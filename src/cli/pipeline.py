"""Pipeline orchestration: probe -> extract -> transcribe -> write (T013).

Wires video probing (T009, `src/audio/video_probe.py`), audio extraction
(T010, `src/audio/extract.py`), `faster-whisper` transcription (T011,
`src/transcription/transcribe.py`), and `.srt` writing (T012,
`src/subtitles/writer.py`) into the single ordered pipeline described by
spec User Story 1, driving per-stage progress reporting via T006's
`ProcessingJob`/`ProgressReporter` (FR-011) along the way.

`run_pipeline()` is the single entry point. It only takes a job through
`ExtractingAudio` -> `Transcribing` -> `WritingSubtitles`
(contracts/cli.md's Progress contract lists exactly these three stage
announcements) -- the `--review`/`--no-review` branching that decides
whether the job then moves to `AwaitingReview` or straight to `Done` is
T014/T021's job (CLI wiring), not this module's, since this module has no
knowledge of the `--review` flag at all.

Zero detectable speech (FR-008) is handled as a first-class *successful*
outcome, not an error, in two different ways depending on *why* there's no
speech:

- The video has an audio track, but `faster-whisper` simply produces no
  segments for it (silence, music-only, etc.) -- extraction and
  transcription both run as normal; `transcribe_audio()` already returns
  this as a `Transcript` with empty `segments` (T011).
- The video has no audio track at all (`Video.has_audio_track` is
  `False`) -- there's nothing for `ffmpeg`/`faster-whisper` to even
  attempt, so extraction and transcription are skipped entirely in favor
  of an empty `Transcript`, per `src/audio/video_probe.py`'s own
  documented contract for that field ("`False` here triggers the FR-008
  'no detectable speech' report").

Either way, a `.srt` file with zero subtitle blocks is still written (per
contracts/cli.md's Output contract) and a clear notice is printed to
stderr via `ProgressReporter.report_notice()` -- the run still exits 0.

Every other failure mode (`WhisperFlowError` and its subclasses, raised by
probing/extraction/transcription for FR-007's unsupported-format/
oversized-video/missing-ffmpeg/model-load cases) is reported to stderr via
`ProgressReporter.report_failure()` (which also moves the job to `Failed`)
and then re-raised, so the caller (T014) only has to decide the process
exit code -- it doesn't need to print its own duplicate error line. An
`OSError` from `SubtitleFile.write()` (T012) -- e.g. a non-writable output
directory or a full disk -- is translated into `lib.errors.SubtitleWriteError`
before it can reach that same handler, so output-write failures are
reported identically rather than escaping as a raw traceback.

`run_pipeline()` never itself advances the job past `WritingSubtitles` on a
successful run -- as noted above, only T014/T021 knows whether `--review`
means the next stop is `AwaitingReview` or `Done`. To make that handoff
possible, the same `ProgressReporter` used throughout the run (wrapping the
same `ProcessingJob`) is returned on `PipelineResult.reporter`, so T014 can
complete the job's state machine (e.g.
`result.reporter.announce_stage(Stage.DONE)`) instead of being left with no
reference to it at all.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from audio.extract import AudioTrack, extract_audio
from audio.video_probe import probe_video
from cli.progress import ProcessingJob, ProgressReporter, Stage
from lib.errors import SubtitleWriteError, WhisperFlowError
from subtitles.models import SubtitleFile
from subtitles.writer import write_subtitle_file
from transcription.transcribe import DEFAULT_MODEL_SIZE, Transcript, transcribe_audio


@dataclass(frozen=True)
class PipelineResult:
    """The outcome of one `run_pipeline()` call.

    Bundles the written `SubtitleFile` together with the `Transcript` it
    was derived from, so a caller (T014) can both locate the output file
    and inspect whether any speech was actually detected without having to
    re-derive that from the file on disk. Also carries the `ProgressReporter`
    (and, through it, the `ProcessingJob`) this run advanced, so T014 can
    move the same job on to `AwaitingReview`/`Done` once it decides which
    applies -- without this, the job would be stranded at `WritingSubtitles`
    forever on every successful run.
    """

    subtitle_file: SubtitleFile
    transcript: Transcript
    reporter: ProgressReporter

    @property
    def has_speech(self) -> bool:
        """`True` unless this run hit FR-008's "no detectable speech" case."""
        return bool(self.transcript.segments)


def run_pipeline(
    video_path: Path | str,
    output_path: Path | str,
    *,
    model_size: str = DEFAULT_MODEL_SIZE,
    progress_stream: TextIO = sys.stderr,
) -> PipelineResult:
    """Run the full probe -> extract -> transcribe -> write pipeline.

    Args:
        video_path: Path to the input video file (spec FR-001).
        output_path: Where to write the resulting `.srt` file (spec FR-006).
        model_size: `faster-whisper` model size (contracts/cli.md's
            `--model`: tiny/base/small/medium/large).
        progress_stream: Where per-stage/percentage progress and notices
            are written (FR-011); defaults to `sys.stderr` per
            contracts/cli.md's Progress contract. Tests pass an in-memory
            stream (e.g. `io.StringIO()`) to assert on it without
            capturing real stderr.

    Returns:
        A `PipelineResult` wrapping the written `SubtitleFile`, the
        `Transcript` it came from -- `PipelineResult.has_speech` is
        `False` exactly when FR-008's "no detectable speech" case applied
        -- and the `ProgressReporter` (job still at `WritingSubtitles`)
        this run used, so the caller can advance it the rest of the way.

    Raises:
        WhisperFlowError (or one of its subclasses from `lib/errors.py`):
            any FR-007 failure -- unsupported/undetectable video format,
            video exceeds the 2-hour maximum, `ffmpeg`/model not found or
            failing, transcription failing partway through, or the output
            `.srt` file failing to write (`SubtitleWriteError`). Before
            re-raising, the failure is reported to `progress_stream` via
            `ProgressReporter.report_failure()`.
    """
    resolved_video_path = Path(video_path)
    resolved_output_path = Path(output_path)

    # The real video duration isn't known until probing succeeds; a
    # placeholder of 0.0 is harmless in the meantime since
    # ProcessingJob.percent_complete is only ever consulted once the job
    # has reached Transcribing, by which point it's been refreshed below.
    reporter = ProgressReporter(
        ProcessingJob(video_duration_seconds=0.0), stream=progress_stream
    )

    audio_track: AudioTrack | None = None
    try:
        video = probe_video(resolved_video_path)
        reporter.job.video_duration_seconds = video.duration_seconds

        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        if video.has_audio_track:
            audio_track = extract_audio(video)
            reporter.announce_stage(Stage.TRANSCRIBING)
            transcript = transcribe_audio(
                audio_track,
                model_size=model_size,
                on_segment=lambda segment: reporter.report_progress(segment.end_seconds),
            )
        else:
            # No audio track at all -- FR-008's "no detectable speech" case
            # applies before there's anything for ffmpeg/faster-whisper to
            # even attempt (src/audio/video_probe.py's documented contract
            # for has_audio_track). Still announce Transcribing so stderr's
            # stage sequence is uniform regardless of which branch ran.
            reporter.announce_stage(Stage.TRANSCRIBING)
            transcript = Transcript(source_video=video, language="", segments=[])

        reporter.announce_stage(Stage.WRITING_SUBTITLES)
        try:
            subtitle_file = write_subtitle_file(transcript, resolved_output_path)
        except OSError as exc:
            raise SubtitleWriteError(resolved_output_path, reason=str(exc)) from exc

        if not transcript.segments:
            reporter.report_notice(
                f"No speech detected in '{resolved_video_path}' -- wrote an "
                f"empty subtitle file to '{subtitle_file.output_path}'."
            )

        return PipelineResult(
            subtitle_file=subtitle_file, transcript=transcript, reporter=reporter
        )
    except WhisperFlowError as exc:
        reporter.report_failure(str(exc))
        raise
    finally:
        # AudioTrack.extracted_path is always this pipeline's own private
        # temp file (extract_audio() is never given an output_path here) --
        # data-model.md: "Temporary WAV file, removed after the run".
        # Cleaned up on every exit (success or failure) once it exists.
        if audio_track is not None:
            audio_track.extracted_path.unlink(missing_ok=True)
