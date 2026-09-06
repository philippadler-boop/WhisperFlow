"""Pipeline orchestration: probe -> extract -> transcribe -> write (T013).

Wires together every prior User Story 1 stage into the single, ordered
sequence contracts/cli.md's Progress contract describes: probing the input
video (T009), extracting its audio (T010), transcribing that audio (T011),
and writing the result to a `.srt` file (T012) -- announcing each stage
transition on stderr via T006's `ProgressReporter` as it goes (FR-011).

`run_pipeline()` is the single entry point T014's CLI wiring (`src/cli/
main.py`) calls for the `--no-review` path. It deliberately does *not*
catch or report any of the domain errors (`lib.errors.WhisperFlowError`
subclasses) raised by the stages it calls -- probing an unsupported format
or an over-length video, a missing `ffmpeg`/`ffprobe` binary, or a failed
ASR model load/transcription all propagate straight out of this function.
Reporting them (a single ``Error: ...`` line on stderr, exit code 1) is
`src/cli/main.py`'s job, once, at the top level -- see contracts/cli.md's
Exit codes section. This mirrors `src/audio/extract.py`/`src/transcription/
transcribe.py`'s own pattern of raising a narrow set of typed errors rather
than reporting them itself.

A video with no detectable speech (FR-008) is not an error: `transcribe_
audio()` already returns that as a `Transcript` with an empty `segments`
list, which converts and writes cleanly to an empty `.srt` file (T012).
This module's only added behavior for that case is printing a clear,
one-line stderr notice (`NO_SPEECH_DETECTED_MESSAGE`) so a `--no-review`
run doesn't silently produce an empty file with no explanation, distinct
from `ProgressReporter`'s own stage-transition lines.

A video with no audio track *at all* (`Video.has_audio_track is False`) is
FR-008's stronger case (data-model.md: `has_audio_track` "False triggers
the FR-008 'no detectable speech' report"), and is handled separately,
*before* extraction/transcription are ever attempted: `extract_audio()`
has nothing to map to its output for such a video and would only ever
raise `AudioExtractionError` (see `src/audio/extract.py`'s own
`test_no_audio_track_video_surfaces_as_extraction_error`, which documents
that as this pipeline's concern, not extraction's) -- which would
incorrectly turn a documented-successful outcome into a fatal, exit-code-1
error. `run_pipeline()` instead skips straight to writing an empty
subtitle file in that case.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from audio.extract import extract_audio
from audio.video_probe import probe_video
from cli.progress import ProcessingJob, ProgressReporter, Stage
from lib.errors import AudioExtractionError
from subtitles.models import SubtitleFile
from subtitles.writer import write_subtitles
from transcription.transcribe import Transcript, transcribe_audio

#: FR-008's "no detectable speech" stderr notice -- a `.srt` file with zero
#: subtitle blocks is a valid, successful outcome (contracts/cli.md's
#: Output contract), but printing nothing would look indistinguishable
#: from a silent failure.
NO_SPEECH_DETECTED_MESSAGE = (
    "No speech detected in the input video -- wrote an empty subtitle file."
)


def run_pipeline(
    *,
    video_path: Path | str,
    output_path: Path | str,
    model_size: str,
    stream: TextIO | None = None,
) -> SubtitleFile:
    """Run the full probe -> extract -> transcribe -> write sequence.

    Args:
        video_path: Path to the input video file (FR-001).
        output_path: Where to write the resulting `.srt` file (FR-006).
        model_size: `faster-whisper` model size (contracts/cli.md's
            `--model`).
        stream: Where stage/progress announcements (T006) and the
            FR-008 no-speech notice are written. Defaults to `sys.stderr`
            per contracts/cli.md's Progress contract; overridable for
            tests.

    Returns:
        The `SubtitleFile` that was written to `output_path`.

    Raises:
        lib.errors.WhisperFlowError: any of its subclasses, propagated
            unmodified from probing, extraction, or transcription --
            `UnsupportedVideoFormatError`/`MaxDurationExceededError`
            (probing), `FfmpegNotFoundError` (probing or extraction),
            `AudioExtractionError` (extraction, or a failure to clean up
            the extracted temporary WAV file once transcription has
            otherwise succeeded), or `ModelLoadError`/`TranscriptionError`
            (transcription). Never caught or reported here -- see this
            module's docstring.
    """
    if stream is None:
        stream = sys.stderr

    resolved_video_path = Path(video_path)
    resolved_output_path = Path(output_path)

    # Probing determines the video's duration, which ProcessingJob needs up
    # front (its percent_complete derivation divides by it) -- so it runs
    # before the job/reporter even exist. Any of its FR-007 errors
    # (unsupported format, oversized video, missing ffprobe) therefore
    # propagate with no stage line ever printed, which is correct: nothing
    # has started processing yet.
    video = probe_video(resolved_video_path)

    job = ProcessingJob(video_duration_seconds=video.duration_seconds)
    reporter = ProgressReporter(job, stream=stream)

    if not video.has_audio_track:
        # FR-008's stronger case: there is no audio track at all to even
        # attempt extracting/transcribing (data-model.md: `has_audio_track`
        # "False triggers the FR-008 'no detectable speech' report").
        # extract_audio() has nothing to map to its output for a video like
        # this and would only ever raise AudioExtractionError -- turning a
        # documented-successful outcome into a fatal error -- so skip
        # extraction/transcription entirely and write straight to an empty
        # subtitle file. Every stage the job passes through -- including
        # the ones with nothing to actually do -- is announced via the
        # reporter itself (rather than advancing `job` directly), so
        # stderr's stage announcements stay complete and consistent with
        # every other run instead of silently skipping straight to
        # "Writing subtitles…" (P2 review).
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.announce_stage(Stage.WRITING_SUBTITLES)
        empty_transcript = Transcript(source_video=video, language="", segments=[])
        subtitle_file = write_subtitles(empty_transcript, resolved_output_path)
        print(NO_SPEECH_DETECTED_MESSAGE, file=stream, flush=True)
        reporter.announce_stage(Stage.DONE)
        return subtitle_file

    reporter.announce_stage(Stage.EXTRACTING_AUDIO)
    audio_track = extract_audio(video)
    temp_audio_path = Path(audio_track.extracted_path)

    # Transcribing and writing are handled under one unified cleanup block:
    # a failure from *either* stage (ModelLoadError/TranscriptionError, or a
    # writer failure such as an unwritable directory/full disk) is already
    # propagating and takes priority -- clean up the temporary WAV
    # best-effort, but never let a cleanup failure replace or mask the
    # primary exception with a raw OSError/traceback, and never leave the
    # temp file behind regardless of which stage failed (P2 review).
    try:
        reporter.announce_stage(Stage.TRANSCRIBING)
        transcript = transcribe_audio(
            audio_track,
            model_size=model_size,
            on_segment=lambda segment: reporter.report_progress(segment.end_seconds),
        )
        reporter.announce_stage(Stage.WRITING_SUBTITLES)
        subtitle_file = write_subtitles(transcript, resolved_output_path)
    except BaseException:
        _cleanup_temp_audio(temp_audio_path)
        raise

    # Only attempted once the transcript is safely on disk: a temp-file
    # cleanup failure at this point is this run's only failure, but it
    # must not cost the user an otherwise-fully-produced, already-written
    # .srt file -- write it, print the FR-008 notice if applicable, and
    # only *then* surface the cleanup failure (P2 review).
    cleanup_error = _cleanup_temp_audio(temp_audio_path)

    if not transcript.segments:
        print(NO_SPEECH_DETECTED_MESSAGE, file=stream, flush=True)

    if cleanup_error is not None:
        # Reported through the CLI's normal WhisperFlowError path
        # (contracts/cli.md's Exit codes section), not silently swallowed
        # -- but note Stage.DONE is deliberately never announced below in
        # this case, since the run did not fully succeed.
        raise cleanup_error

    reporter.announce_stage(Stage.DONE)
    return subtitle_file


def _cleanup_temp_audio(path: Path) -> AudioExtractionError | None:
    """Best-effort removal of the pipeline's own temporary WAV file.

    data-model.md: the extracted WAV is a "Temporary WAV file, removed
    after the run" -- `extract_audio()` always writes to a fresh
    auto-generated temp path here (no `output_path` passed through), so
    this pipeline owns cleaning it up, whether transcription succeeded or
    raised.

    A failure to remove it (e.g. a permission/lock error) must never leak
    a raw `OSError`: doing so could otherwise replace an in-flight
    `ModelLoadError`/`TranscriptionError` with an unrelated traceback, or
    turn an otherwise-successful run into an unhandled crash instead of a
    clean `WhisperFlowError` (P2 review). Returns the domain error to
    raise instead of the cleanup `OSError`, or `None` on success, so the
    caller can decide whether raising it would mask a more important
    exception already propagating.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        return AudioExtractionError(path, stderr=f"failed to remove temporary file: {exc}")
    return None
