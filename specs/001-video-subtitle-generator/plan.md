# Implementation Plan: Video Subtitle Generator

**Branch**: `001-video-subtitle-generator` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-video-subtitle-generator/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

A local, CLI-only tool that takes a video file, extracts its audio, and
transcribes speech into a time-synchronized `.srt` subtitle file in the
video's original spoken language (FR-001–FR-003), using a local
Whisper-family ASR model so no video/audio content ever leaves the user's
machine (FR-004). The CLI reports progress during processing (FR-011),
and lets the user review and edit subtitle lines before the file is
considered final (FR-009, FR-010). Translation, a GUI, and
resume-from-checkpoint are explicitly out of scope for v1.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `faster-whisper` (local ASR), `ffmpeg` (external
binary, invoked via subprocess, for audio extraction/probing), `srt`
(compose `.srt` output), `typer` (CLI), `rich` (progress display)

**Storage**: N/A — files only (input video, temporary extracted audio,
output `.srt`); no database or persistent service state

**Testing**: `pytest`

**Target Platform**: Cross-platform CLI (Windows, macOS, Linux); primary
development on Windows, must not assume Unix-only tooling

**Project Type**: Single project — command-line tool

**Performance Goals**: SC-002/SC-006 require at least ~2x real-time
transcription throughput (a 10-minute video completes in ≤5 minutes, and
this ratio holds up to the 2-hour maximum, i.e. ~1 hour for the longest
supported video) on typical consumer hardware, CPU-only

**Constraints**: FR-004 — no network calls for transcription/audio
processing; requires an `ffmpeg` binary available on the host; input
video length capped at 2 hours (spec Clarifications); no checkpoint/resume,
so an interrupted run always restarts from the beginning (Out of Scope)

**Scale/Scope**: Single user, single machine, one video processed per CLI
invocation; no concurrency or multi-tenant requirements for v1

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

This project's constitution ([constitution.md](../../.specify/memory/constitution.md))
is process/governance-focused (subagent separation, approval gates,
traceability, branching, evidence-based validation) rather than
technology-prescriptive, so there are no framework/pattern gates to check
against this plan's tech stack. Relevant gates:

| Gate | Status | Notes |
|---|---|---|
| Two Human Approval Gates (Principle II) | **Pending** | This plan is a Requirements/Design-gate artifact — it requires human sign-off before `/speckit-tasks` output is implemented, not before the planning artifacts themselves are generated. |
| Requirement Traceability (Principle III) | PASS | Every design decision below traces to an FR-xxx/SC-xxx in [spec.md](spec.md); `/speckit-tasks` will carry the same IDs into task and PR references. |
| Branch-per-Task, Protected Main (Principle IV) | PASS (deferred) | This plan lives on `001-video-subtitle-generator`; the developer subagent creates a task-scoped branch per Principle IV once `/speckit-tasks` produces the breakdown — no code lands on this branch directly. |
| Evidence-Based Validation (Principle V) | PASS | [quickstart.md](quickstart.md) defines runnable scenarios QA can execute later to produce requirement → evidence mappings. |
| Subagent Separation of Powers (Principle I) | N/A | No architectural decision here grants merge authority or write/edit tools to a role the constitution restricts. |

No violations requiring justification — Complexity Tracking is empty.

**Post-Phase 1 re-check**: The Phase 1 artifacts (data-model.md,
contracts/cli.md, quickstart.md) introduce no new dependency, merge
authority, or process change beyond what's assessed above — gate
statuses are unchanged after design.

## Project Structure

### Documentation (this feature)

```text
specs/001-video-subtitle-generator/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── cli/                 # Typer entrypoint: argument parsing, progress display (FR-005, FR-011)
├── audio/               # ffmpeg-based audio extraction/probing from the input video (FR-001)
├── transcription/       # faster-whisper wrapper producing a time-coded Transcript (FR-002, FR-004)
├── subtitles/           # Transcript -> SubtitleFile composition (srt lib), review/edit support (FR-006, FR-009, FR-010)
└── lib/                 # Shared types (Video, Transcript, SubtitleFile, etc.) and error/reporting helpers (FR-007, FR-008)

tests/
├── contract/            # CLI argument/exit-code/output-format contract tests (see contracts/cli.md)
├── integration/         # End-to-end: sample video in -> .srt file out
└── unit/                # Per-module unit tests (audio extraction, transcript segmentation, srt composition)
```

**Structure Decision**: Single project (Option 1) — WhisperFlow is a
standalone CLI tool with no frontend/backend split, so a plain `src/` +
`tests/` layout applies. Modules are split by pipeline stage (audio →
transcription → subtitles) rather than by technical layer, matching how
the functional requirements are independently testable per stage.

## Complexity Tracking

No Constitution Check violations — this section is intentionally empty.
