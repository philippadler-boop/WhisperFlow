---

description: "Task list template for feature implementation"
---

# Tasks: Video Subtitle Generator

**Input**: Design documents from `/specs/001-video-subtitle-generator/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md), [quickstart.md](quickstart.md)

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and testing of each story. Every task references the FR-xxx/SC-xxx it satisfies, per this project's constitution (Principle III — Requirement Traceability); carry the same IDs into the PR that closes each task.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- Paths below are repo-root-relative, per plan.md's Project Structure (single project: `src/`, `tests/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project structure per plan.md: `src/cli/`, `src/audio/`, `src/transcription/`, `src/subtitles/`, `src/lib/`, `tests/contract/`, `tests/integration/`, `tests/unit/`, `tests/fixtures/`, `scripts/` (each `src/`/`tests/` subdirectory with `__init__.py`)
- [x] T002 Initialize `pyproject.toml` at repo root: project metadata, Python 3.11+ requirement, runtime dependencies (`faster-whisper`, `srt`, `typer`, `rich`), dev dependency (`pytest`), `ruff` lint config, and `pytest` config (testpaths) — per plan.md Technical Context and research.md
- [x] T003 [P] Add `tests/conftest.py` with shared fixtures (a `typer.testing.CliRunner` fixture, and paths to small fixture videos under `tests/fixtures/` — a clear-speech clip and a silent/no-speech clip, per quickstart.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infrastructure and shared entities that both user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Implement domain error types `UnsupportedVideoFormatError`, `MaxDurationExceededError`, `FfmpegNotFoundError` in `src/lib/errors.py` (spec FR-007; data-model.md validation rules)
- [x] T005 [P] Implement `SubtitleLine` and `SubtitleFile` data classes plus `.srt` composition (via the `srt` library) in `src/subtitles/models.py` — shared by US1 (creates) and US2 (edits) (data-model.md — SubtitleLine/SubtitleFile; spec FR-006)
- [x] T006 [P] Implement the `ProcessingJob` stage model (`ExtractingAudio` → `Transcribing` → `WritingSubtitles` → `AwaitingReview` → `Done`/`Failed`) and a stderr stage/percentage progress reporter in `src/cli/progress.py` (data-model.md — ProcessingJob; spec FR-011)
- [x] T007 [P] Implement the `whisperflow transcribe VIDEO_PATH` CLI skeleton — argument and all options (`--output`, `--model`, `--review/--no-review`, `--editor`) parsed per contracts/cli.md, wired to a not-yet-implemented pipeline call — in `src/cli/main.py` (spec FR-005)
- [x] T008 Contract test asserting the CLI's argument/option surface, defaults, and `--help` output match contracts/cli.md in `tests/contract/test_cli_contract.py` (depends on T007)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Transcribe a video into subtitles (Priority: P1) 🎯 MVP

**Goal**: Given a video file, produce a time-synced `.srt` subtitle file in the video's original spoken language, with progress feedback and clear errors for bad/oversized input (spec User Story 1; FR-001–FR-004, FR-006–FR-008, FR-011)

**Independent Test**: Run `whisperflow transcribe` against a short sample video with clear speech and verify the produced `.srt` text matches the spoken words and its timings line up with the audio (quickstart.md Scenario 1)

### Implementation for User Story 1

- [x] T009 [P] [US1] Implement video probing (`container_format`, `duration_seconds`, `has_audio_track` via `ffmpeg`) in `src/audio/video_probe.py` (data-model.md — Video; spec FR-001, FR-007)
- [x] T010 [P] [US1] Implement audio extraction (ffmpeg subprocess → mono 16kHz WAV) in `src/audio/extract.py` (data-model.md — AudioTrack; spec FR-001; research.md — Audio extraction)
- [x] T011 [US1] Implement `faster-whisper`-based transcription producing a time-coded `Transcript`/`TranscriptSegment` list in `src/transcription/transcribe.py` (depends on T010) (data-model.md — Transcript; spec FR-002, FR-004; research.md — Local ASR engine)
- [x] T012 [US1] Implement transcript-segments → initial `SubtitleLine`/`SubtitleFile` conversion and `.srt` file writing in `src/subtitles/writer.py` (depends on T005, T011) (spec FR-003, FR-006)
- [x] T013 [US1] Implement pipeline orchestration (probe → extract → transcribe → write), wiring per-stage progress via T006 and handling the zero-speech-detected case as a successful run with a clear stderr notice in `src/cli/pipeline.py` (depends on T009, T010, T011, T012, T006) (spec FR-008, FR-011)
- [x] T014 [US1] Wire the `--no-review` command path to the pipeline, with clear stderr error reporting (via T004's error types) for unsupported format, oversized video, or missing `ffmpeg` in `src/cli/main.py` (depends on T004, T007, T013) (spec FR-005, FR-007)
- [x] T015 [P] [US1] Integration test: clear-speech sample video → correct, time-synced `.srt` (quickstart.md Scenario 1) in `tests/integration/test_transcribe_basic.py`
- [x] T016 [P] [US1] Integration test: stage/progress lines appear on stderr during processing (quickstart.md Scenario 2) in `tests/integration/test_progress.py`
- [x] T017 [P] [US1] Integration test: silent/no-speech sample video → exit 0, empty `.srt`, clear stderr notice (quickstart.md Scenario 4) in `tests/integration/test_no_speech.py`
- [x] T018 [P] [US1] Integration test: unsupported input file and over-2-hour video → exit 1 with a clear error message (quickstart.md Scenarios 5–6) in `tests/integration/test_input_errors.py`
- [x] T019 [P] [US1] Unit tests for video probing and audio extraction edge cases (bad format, missing audio track) in `tests/unit/test_audio.py`

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP

---

## Phase 4: User Story 2 - Review and correct generated subtitles (Priority: P2)

**Goal**: After a draft `.srt` is generated, let the user open it in an editor, correct lines, and have those edits reflected in the finalized file (spec User Story 2; FR-009, FR-010)

**Independent Test**: Run with `--review`, edit the text of one line in the opened editor, and confirm the finalized `.srt` contains the edited text rather than the originally generated text (quickstart.md Scenario 3)

### Implementation for User Story 2

- [x] T020 [US2] Implement the `--review` flow — write the draft `.srt`, invoke `$EDITOR`/`--editor`, wait for confirmation, re-read the file and mark changed lines' `edited` flag — in `src/cli/review.py` (depends on T005, T007) (data-model.md — SubtitleLine.edited; spec FR-009, FR-010)
- [x] T021 [US2] Wire `--review`/`--no-review` branching into the CLI command, defaulting to `--review` per contracts/cli.md, in `src/cli/main.py` (depends on T014, T020) (spec FR-005)
- [x] T022 [P] [US2] Integration test: `--review` with a simulated editor that changes one line → finalized `.srt` reflects the edit (quickstart.md Scenario 3) in `tests/integration/test_review.py`
- [x] T023 [P] [US2] Unit tests for the review/edit logic (`edited` flag set only on changed lines, unchanged lines untouched) in `tests/unit/test_review.py`

**Checkpoint**: User Stories 1 and 2 both work independently

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that span both user stories

- [x] T024 [P] Document the `transcribe` command's usage (arguments, options, examples from contracts/cli.md) in `README.md`
- [ ] T025 [P] Add a benchmark helper (`scripts/benchmark.py`) that times a `transcribe` run against a given video and prints elapsed time (SC-002/SC-006, quickstart.md Scenario 8), and, given a small labeled reference corpus (sample videos + their known-correct transcript text), reports rough transcript-accuracy and subtitle-timing-sync percentages against that corpus. Note: SC-003 ("judged by a reviewing user") and SC-004 ("perceived by a viewer") are spec.md's own human-judgment criteria, not automatable pass/fail checks — this script gives `qa` a concrete number to anchor that judgment against, it does not replace it (Principle V, validation reports are `qa`-owned).
- [ ] T026 [P] Integration test confirming no outbound network calls occur during `transcribe` (quickstart.md Scenario 7) in `tests/integration/test_no_network.py`
- [ ] T027 [P] Lint/type-check cleanup pass across `src/` and `tests/` (`ruff check --fix`)
- [ ] T028 Extend the benchmark helper (depends on T025, same file) to measure transcription accuracy and subtitle-sync percentage against a small labeled sample corpus, giving QA concrete data points for SC-003 (≥90% accuracy) and SC-004 (≥95% sync) in `scripts/benchmark.py`
- [ ] T029 If T025/T028's benchmark shows the SC-002/SC-006 timing target is missed on reference hardware, adjust the default `--model` size (or document a minimum-hardware note) in `src/cli/main.py` and `contracts/cli.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS both user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion — no dependency on US2
- **User Story 2 (Phase 4)**: Depends on Foundational completion; also builds on US1's CLI skeleton and pipeline (T007, T014) since review sits between "draft written" and "finalized," but is independently testable once US1 exists
- **Polish (Phase 5)**: Depends on both user stories being complete

### Within Each User Story

- Models/entities before services (e.g., T005 before T012; T009/T010 before T011)
- Services before CLI wiring (e.g., T013 before T014)
- Implementation before its integration/unit tests

### Parallel Opportunities

- Setup: T003 can run alongside T002 (different files)
- Foundational: T004, T005, T006, T007 touch different files and can run in parallel; T008 must follow T007
- User Story 1: T009 and T010 can run in parallel (different files, no shared dependency); T015–T019 (all test files) can run in parallel once T009–T014 are done
- User Story 2: T022 and T023 can run in parallel once T020–T021 are done
- Polish: T024, T026, T027 touch different files and can run in parallel; T025 must precede T028 (same file); T029 depends on T025/T028's results

---

## Parallel Example: User Story 1

```bash
# Launch the two independent extraction-side modules together:
Task: "Implement video probing in src/audio/video_probe.py"
Task: "Implement audio extraction in src/audio/extract.py"

# Once T009-T014 are done, launch all US1 tests together:
Task: "Integration test: basic transcription in tests/integration/test_transcribe_basic.py"
Task: "Integration test: progress reporting in tests/integration/test_progress.py"
Task: "Integration test: no-speech video in tests/integration/test_no_speech.py"
Task: "Integration test: input errors in tests/integration/test_input_errors.py"
Task: "Unit tests: audio module in tests/unit/test_audio.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks both stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1, 2, 4, 5, 6 against real sample videos
5. This is a usable v1 slice even before review/edit (US2) exists — translation, GUI, and resume-from-checkpoint remain out of scope per spec.md

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add User Story 1 → validate independently → MVP
3. Add User Story 2 → validate independently (quickstart.md Scenario 3)
4. Polish (README, benchmark script, no-network check, lint) → hand off to `reviewer`/`qa` per constitution

---

## Notes

- Per this project's constitution (Principle III), every PR implementing a task MUST reference its FR-xxx/issue ID — carry the IDs already annotated on each task above into the PR title/body.
- Per Principle IV, this feature's Specify/Clarify/Plan/Tasks/Analyze artifacts were committed directly to `main` -- a documented, one-time exception (see constitution.md Principle IV; the feature-branch requirement wasn't written down yet when this work happened). Each implementation task (or small group of related tasks) below is implemented on its own feature branch cut directly from `main`, and PR'd back to `main`. Never committed directly to `main`. Every feature after this one must create a real feature branch before Specify -- see constitution.md Principle IV.
- Per Principle I, no task here includes writing `docs/validation/` reports — that is the `qa` subagent's independent responsibility once a PR is reviewed and approved.
- [P] tasks touch different files with no unfinished-task dependency between them
- Verify each user story's independent test (quickstart.md) passes before moving to the next story
