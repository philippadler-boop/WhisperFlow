"""Unit tests for the `ProcessingJob` stage model and `ProgressReporter` (T006).

Covers data-model.md's `ProcessingJob` entity (stage transitions, the
`Failed` state reachable from any non-terminal stage, and the
`percent_complete` derivation while `Transcribing`) and the stderr
stage/percentage announcements required by FR-011 / contracts/cli.md's
Progress contract.
"""

from __future__ import annotations

import io

import pytest

from cli.progress import (
    InvalidStageTransitionError,
    ProcessingJob,
    ProgressReporter,
    Stage,
)


class TestProcessingJobTransitions:
    def test_starts_in_extracting_audio(self):
        job = ProcessingJob(video_duration_seconds=100.0)
        assert job.stage is Stage.EXTRACTING_AUDIO
        assert not job.is_terminal

    def test_happy_path_without_review(self):
        job = ProcessingJob(video_duration_seconds=100.0)
        job.advance(Stage.TRANSCRIBING)
        job.advance(Stage.WRITING_SUBTITLES)
        job.advance(Stage.DONE)
        assert job.stage is Stage.DONE
        assert job.is_terminal

    def test_happy_path_with_review(self):
        job = ProcessingJob(video_duration_seconds=100.0)
        job.advance(Stage.TRANSCRIBING)
        job.advance(Stage.WRITING_SUBTITLES)
        job.advance(Stage.AWAITING_REVIEW)
        job.advance(Stage.DONE)
        assert job.stage is Stage.DONE

    def test_reannouncing_current_stage_is_a_noop(self):
        job = ProcessingJob(video_duration_seconds=100.0)
        job.advance(Stage.EXTRACTING_AUDIO)
        assert job.stage is Stage.EXTRACTING_AUDIO

    @pytest.mark.parametrize(
        "from_stage,to_stage",
        [
            (Stage.EXTRACTING_AUDIO, Stage.WRITING_SUBTITLES),
            (Stage.EXTRACTING_AUDIO, Stage.DONE),
            (Stage.TRANSCRIBING, Stage.EXTRACTING_AUDIO),
            (Stage.TRANSCRIBING, Stage.AWAITING_REVIEW),
            (Stage.WRITING_SUBTITLES, Stage.TRANSCRIBING),
            (Stage.AWAITING_REVIEW, Stage.TRANSCRIBING),
        ],
    )
    def test_rejects_invalid_transitions(self, from_stage, to_stage):
        job = ProcessingJob(video_duration_seconds=100.0, stage=from_stage)
        with pytest.raises(InvalidStageTransitionError):
            job.advance(to_stage)

    @pytest.mark.parametrize(
        "from_stage",
        [
            Stage.EXTRACTING_AUDIO,
            Stage.TRANSCRIBING,
            Stage.WRITING_SUBTITLES,
            Stage.AWAITING_REVIEW,
        ],
    )
    def test_fail_reachable_from_any_non_terminal_stage(self, from_stage):
        job = ProcessingJob(video_duration_seconds=100.0, stage=from_stage)
        job.fail("boom")
        assert job.stage is Stage.FAILED
        assert job.error == "boom"
        assert job.is_terminal

    @pytest.mark.parametrize("terminal_stage", [Stage.DONE, Stage.FAILED])
    def test_fail_rejected_from_terminal_stages(self, terminal_stage):
        job = ProcessingJob(video_duration_seconds=100.0, stage=terminal_stage)
        with pytest.raises(InvalidStageTransitionError):
            job.fail("boom")

    def test_no_transitions_out_of_done(self):
        job = ProcessingJob(video_duration_seconds=100.0, stage=Stage.DONE)
        with pytest.raises(InvalidStageTransitionError):
            job.advance(Stage.EXTRACTING_AUDIO)


class TestPercentComplete:
    def test_zero_outside_transcribing(self):
        job = ProcessingJob(video_duration_seconds=100.0, stage=Stage.EXTRACTING_AUDIO)
        job.update_progress(50.0)
        assert job.percent_complete == 0.0

    def test_derived_from_segment_end_over_duration(self):
        job = ProcessingJob(video_duration_seconds=200.0, stage=Stage.TRANSCRIBING)
        job.update_progress(50.0)
        assert job.percent_complete == pytest.approx(25.0)

    def test_clamped_to_100(self):
        job = ProcessingJob(video_duration_seconds=100.0, stage=Stage.TRANSCRIBING)
        job.update_progress(150.0)
        assert job.percent_complete == 100.0

    def test_clamped_to_0_for_negative_progress(self):
        job = ProcessingJob(video_duration_seconds=100.0, stage=Stage.TRANSCRIBING)
        job.update_progress(-10.0)
        assert job.percent_complete == 0.0

    def test_zero_duration_does_not_divide_by_zero(self):
        job = ProcessingJob(video_duration_seconds=0.0, stage=Stage.TRANSCRIBING)
        job.update_progress(10.0)
        assert job.percent_complete == 0.0


class TestProgressReporter:
    def _make(self, duration=100.0):
        job = ProcessingJob(video_duration_seconds=duration)
        stream = io.StringIO()
        reporter = ProgressReporter(job, stream=stream)
        return job, stream, reporter

    def test_announce_stage_advances_job_and_writes_message(self):
        job, stream, reporter = self._make()
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        assert job.stage is Stage.EXTRACTING_AUDIO
        assert "Extracting audio…" in stream.getvalue()

    def test_full_run_announces_each_stage_once(self):
        job, stream, reporter = self._make()
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.report_progress(50.0)
        reporter.announce_stage(Stage.WRITING_SUBTITLES)
        reporter.announce_stage(Stage.DONE)

        output = stream.getvalue()
        assert "Extracting audio…" in output
        assert "Transcribing…" in output
        assert "Writing subtitles…" in output
        assert "Done." in output
        assert job.stage is Stage.DONE

    def test_report_progress_writes_percentage(self):
        job, stream, reporter = self._make(duration=100.0)
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.report_progress(25.0)
        assert "25.0%" in stream.getvalue()

    def test_report_progress_updates_in_place_with_carriage_return(self):
        job, stream, reporter = self._make(duration=100.0)
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.report_progress(10.0)
        reporter.report_progress(20.0)
        output = stream.getvalue()
        # Two in-place-refreshed percentage updates, not two separate lines.
        assert output.count("\r") == 2
        # One newline per stage announcement ("Extracting audio…",
        # "Transcribing…"), none from the two progress refreshes.
        assert output.count("\n") == 2

    def test_announce_stage_closes_open_percent_line_first(self):
        job, stream, reporter = self._make(duration=100.0)
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.report_progress(50.0)
        reporter.announce_stage(Stage.WRITING_SUBTITLES)
        lines = stream.getvalue().splitlines()
        assert any(line.strip() == "Writing subtitles…" for line in lines)

    def test_announce_stage_rejects_failed(self):
        _, _, reporter = self._make()
        with pytest.raises(ValueError):
            reporter.announce_stage(Stage.FAILED)

    def test_report_failure_transitions_job_and_writes_error(self):
        job, stream, reporter = self._make()
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.report_failure("ffmpeg not found")
        assert job.stage is Stage.FAILED
        assert job.error == "ffmpeg not found"
        assert "Error: ffmpeg not found" in stream.getvalue()

    def test_report_failure_closes_open_percent_line_first(self):
        job, stream, reporter = self._make(duration=100.0)
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.report_progress(50.0)
        reporter.report_failure("model failed to load")
        lines = stream.getvalue().splitlines()
        assert any(line.strip() == "Error: model failed to load" for line in lines)

    def test_report_notice_writes_message_without_changing_stage(self):
        job, stream, reporter = self._make()
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.report_notice("No speech detected in 'clip.mp4'.")
        assert job.stage is Stage.EXTRACTING_AUDIO
        assert not job.is_terminal
        assert "No speech detected in 'clip.mp4'." in stream.getvalue()

    def test_report_notice_closes_open_percent_line_first(self):
        job, stream, reporter = self._make(duration=100.0)
        reporter.announce_stage(Stage.EXTRACTING_AUDIO)
        reporter.announce_stage(Stage.TRANSCRIBING)
        reporter.report_progress(50.0)
        reporter.report_notice("No speech detected.")
        lines = stream.getvalue().splitlines()
        assert any(line.strip() == "No speech detected." for line in lines)
