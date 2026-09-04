# Quickstart: Validating the Video Subtitle Generator

This is a runnable validation guide, not implementation documentation.
It's meant for whoever validates the feature once built (see the `qa`
subagent's Evidence-Based Validation responsibility) to confirm each
requirement against real command output. Command details are defined in
[contracts/cli.md](contracts/cli.md); data shapes are in
[data-model.md](data-model.md).

## Prerequisites

- Python 3.11+ and the project installed (`pip install -e .` from the
  repo root, once packaging exists).
- An `ffmpeg` binary on `PATH` (research.md — Audio extraction).
- A short sample video with clear spoken English audio, e.g.
  `samples/hello.mp4` (a few seconds to a couple of minutes is enough for
  the scenarios below; a ~10-minute clip is needed for the SC-002 timing
  check).

## Scenario 1 — Basic transcription (FR-001, FR-002, FR-003, FR-006 / User Story 1)

```bash
whisperflow transcribe samples/hello.mp4 --no-review
```

**Expected**: Exit code `0`. A `hello.srt` file appears next to the input
video, containing subtitle blocks whose text matches what's spoken in the
sample, in the video's original language, with start/end timestamps that
line up with the audio when played back with the video.

## Scenario 2 — Progress feedback (FR-011)

```bash
whisperflow transcribe samples/hello.mp4 --no-review
```

**Expected**: While the command runs, stderr shows stage announcements
(`Extracting audio…`, `Transcribing…`, `Writing subtitles…`) and a
progress percentage during the `Transcribing…` stage — the terminal is
never silent for more than a few seconds at a time.

## Scenario 3 — Review and edit before finalizing (FR-009, FR-010 / User Story 2)

```bash
whisperflow transcribe samples/hello.mp4 --review --editor "code --wait"
```

**Expected**: The command pauses after generating a draft `.srt`, opens
it in the given editor, and waits. Edit the text of one subtitle line,
save, and close. **Then**: the finalized `hello.srt` contains the edited
text for that line, not the originally generated text.

## Scenario 4 — No detectable speech (FR-008)

```bash
whisperflow transcribe samples/silence.mp4 --no-review
```

(`samples/silence.mp4` — a video with a silent or music-only audio
track.)

**Expected**: Exit code `0` (this is success, not an error — see
data-model.md). Stderr clearly states no speech was detected. The
resulting `.srt` file exists and contains zero subtitle blocks, not a
crash or a garbled file.

## Scenario 5 — Unsupported input (FR-007)

```bash
whisperflow transcribe README.md
```

**Expected**: Exit code `1`. A single clear error line on stderr
identifying the file as an unsupported/invalid video — no partial or
corrupt `.srt` file is left behind.

## Scenario 6 — Video exceeding the maximum length (FR-007, Clarifications)

```bash
whisperflow transcribe samples/three-hour-video.mp4
```

**Expected**: Exit code `1`. Error message states the video exceeds the
2-hour maximum, with the actual detected duration.

## Scenario 7 — Local-only processing (FR-004)

Run Scenario 1 with outbound network access blocked (e.g. via a firewall
rule or a network namespace with no route).

**Expected**: Identical success and output to Scenario 1 — no failure is
attributable to a blocked network call, confirming no transcription
traffic ever leaves the machine.

## Scenario 8 — Timing targets (SC-002, SC-006)

Run Scenario 1 against a ~10-minute sample video and time the command
(e.g. `time whisperflow transcribe samples/ten-minutes.mp4 --no-review`).

**Expected**: Completes in ≤5 minutes (SC-002) on the reference test
machine. For SC-006, the same check against a video near the 2-hour
maximum should complete in roughly ≤1 hour, preserving the ~2x-real-time
ratio.
