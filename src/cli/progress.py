"""`ProcessingJob` stage model and stderr progress reporter (T006).

Implements data-model.md's `ProcessingJob` entity -- the in-memory-only
state machine a single `whisperflow transcribe` invocation moves through
-- plus a `ProgressReporter` that announces stage transitions and
`Transcribing`-stage percentage progress on stderr, per FR-011 and
contracts/cli.md's "Progress contract".

Nothing here is persisted: per data-model.md's Rules, a `ProcessingJob`
lives only in process memory, so an interrupted run always starts a fresh
job at `ExtractingAudio` rather than resuming (Out of Scope: Resumable
processing).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import TextIO


class Stage(StrEnum):
    """The stages a `ProcessingJob` can be in (data-model.md — ProcessingJob)."""

    EXTRACTING_AUDIO = "ExtractingAudio"
    TRANSCRIBING = "Transcribing"
    WRITING_SUBTITLES = "WritingSubtitles"
    AWAITING_REVIEW = "AwaitingReview"
    DONE = "Done"
    FAILED = "Failed"


#: Terminal stages: no further transitions are possible once reached.
_TERMINAL_STAGES = (Stage.DONE, Stage.FAILED)

#: Valid forward transitions out of each non-terminal stage
#: (data-model.md: `ExtractingAudio` -> `Transcribing` -> `WritingSubtitles`
#: -> `AwaitingReview` (if the interactive review step runs) -> `Done`).
#: `Failed` is reachable from any non-terminal stage and is handled
#: separately by `ProcessingJob.fail()` / `ProgressReporter.report_failure()`
#: rather than listed here.
_ALLOWED_TRANSITIONS: dict[Stage, tuple[Stage, ...]] = {
    Stage.EXTRACTING_AUDIO: (Stage.TRANSCRIBING,),
    Stage.TRANSCRIBING: (Stage.WRITING_SUBTITLES,),
    Stage.WRITING_SUBTITLES: (Stage.AWAITING_REVIEW, Stage.DONE),
    Stage.AWAITING_REVIEW: (Stage.DONE,),
    Stage.DONE: (),
    Stage.FAILED: (),
}

#: One-line stderr announcements for each stage transition, per
#: contracts/cli.md's Progress contract (`"Extracting audio…"`,
#: `"Transcribing…"`, `"Writing subtitles…"`).
STAGE_MESSAGES: dict[Stage, str] = {
    Stage.EXTRACTING_AUDIO: "Extracting audio…",
    Stage.TRANSCRIBING: "Transcribing…",
    Stage.WRITING_SUBTITLES: "Writing subtitles…",
    Stage.AWAITING_REVIEW: "Awaiting review…",
    Stage.DONE: "Done.",
    Stage.FAILED: "Failed.",
}


class InvalidStageTransitionError(RuntimeError):
    """Raised when a `ProcessingJob` is moved to a stage it cannot reach from its current one."""


@dataclass
class ProcessingJob:
    """Runtime state for one `whisperflow transcribe` invocation.

    Held only in process memory (data-model.md — ProcessingJob: "State is
    held only in process memory; nothing is written to disk that would let
    a future run resume mid-job").
    """

    video_duration_seconds: float
    stage: Stage = Stage.EXTRACTING_AUDIO
    current_segment_end_seconds: float = 0.0
    error: str | None = None

    def advance(self, stage: Stage) -> None:
        """Move to `stage`, validating it's reachable from the current stage.

        Re-announcing the current stage (`stage == self.stage`) is a no-op
        rather than an error, so the initial stage can be announced without
        a separate "advance into the starting stage" special case.
        """
        if stage == self.stage:
            return
        allowed = _ALLOWED_TRANSITIONS.get(self.stage, ())
        if stage not in allowed:
            raise InvalidStageTransitionError(
                f"cannot advance from {self.stage.value!r} to {stage.value!r}"
            )
        self.stage = stage

    def fail(self, error: str) -> None:
        """Move to `Failed` from any non-terminal stage, recording `error`.

        Surfaces the FR-007/FR-008 error messages (data-model.md).
        """
        if self.stage in _TERMINAL_STAGES:
            raise InvalidStageTransitionError(
                f"cannot fail a job already in a terminal stage ({self.stage.value!r})"
            )
        self.stage = Stage.FAILED
        self.error = error

    def update_progress(self, current_segment_end_seconds: float) -> None:
        """Record how far transcription has progressed through the video."""
        self.current_segment_end_seconds = current_segment_end_seconds

    @property
    def is_terminal(self) -> bool:
        """True once the job has reached `Done` or `Failed`."""
        return self.stage in _TERMINAL_STAGES

    @property
    def percent_complete(self) -> float:
        """Percentage complete while in the `Transcribing` stage.

        Derived from `current_segment_end_seconds / video_duration_seconds`
        (data-model.md — ProcessingJob Rules), since `Transcribing` is the
        longest-running stage. Always `0.0` outside of `Transcribing`, and
        clamped to the `[0, 100]` range.
        """
        if self.stage != Stage.TRANSCRIBING or self.video_duration_seconds <= 0:
            return 0.0
        fraction = self.current_segment_end_seconds / self.video_duration_seconds
        return max(0.0, min(100.0, fraction * 100.0))


class ProgressReporter:
    """Reports a `ProcessingJob`'s stage/percentage progress to stderr (FR-011).

    Per contracts/cli.md's Progress contract: stage transitions are each
    announced with a single line, and while in `Transcribing` a completion
    percentage is shown -- refreshed in place with `\\r` so the terminal
    isn't flooded with one line per ASR segment. Machine-readable output
    (the `.srt` file) is never written here, only to `--output` elsewhere
    in the pipeline, so stdout stays clean.
    """

    def __init__(self, job: ProcessingJob, stream: TextIO = sys.stderr) -> None:
        self._job = job
        self._stream = stream
        self._percent_line_open = False

    @property
    def job(self) -> ProcessingJob:
        return self._job

    def announce_stage(self, stage: Stage) -> None:
        """Advance the job to `stage` and print its one-line stderr announcement."""
        if stage == Stage.FAILED:
            raise ValueError("use report_failure() to transition to Failed")
        self._close_percent_line()
        self._job.advance(stage)
        print(STAGE_MESSAGES[stage], file=self._stream, flush=True)

    def report_progress(self, current_segment_end_seconds: float) -> None:
        """Update transcription progress and refresh the percentage line.

        Only meaningful while the job is in `Transcribing`; the job itself
        clamps `percent_complete` to `0.0` in other stages.
        """
        self._job.update_progress(current_segment_end_seconds)
        percent = self._job.percent_complete
        print(f"\rTranscribing… {percent:5.1f}%", end="", file=self._stream, flush=True)
        self._percent_line_open = True

    def report_failure(self, error: str) -> None:
        """Move the job to `Failed` and print its stderr error line (FR-007)."""
        self._close_percent_line()
        self._job.fail(error)
        print(f"Error: {error}", file=self._stream, flush=True)

    def report_notice(self, message: str) -> None:
        """Print a stderr notice that is neither a stage transition nor a failure.

        Used by the T013 pipeline for FR-008's "no detectable speech" case:
        the job is not failing (it still reaches `Done` exactly as any
        other successful run would) and no stage transition is happening,
        but the user still needs an explicit, clearly-stated heads-up that
        the resulting `.srt` file has zero subtitle lines by design, not
        because of a bug.
        """
        self._close_percent_line()
        print(message, file=self._stream, flush=True)

    def _close_percent_line(self) -> None:
        if self._percent_line_open:
            print(file=self._stream, flush=True)
            self._percent_line_open = False
