# 0004: CLI Framework and Progress Display

> **Status**: Accepted — approved at the Design Gate (Principle II).
> Feature 001 (video-subtitle-generator) predates the branch-per-planning-
> phase process (Constitution Principle IV's documented one-time
> exception); this ADR was committed directly to `main` on 2026-09-04 as
> part of that grandfathered flow, and its decision was implicitly
> ratified by the feature's full implementation and release (T001-T029,
> all merged).

## Context

FR-005 requires subtitle generation to be exposed through a command-line
interface for v1 (a GUI is explicitly out of scope). FR-011 requires the
CLI to show ongoing progress (e.g. percent complete or elapsed time)
while a video is processing, rather than appearing unresponsive —
important given SC-002/SC-006's multi-minute-to-multi-hour processing
times. `contracts/cli.md` (Phase 1 output) defines the CLI's
argument/exit-code/output-format contract, which needs to stay easy to
keep in sync with the implementation as the tool evolves. FR-009/FR-010
also require an interactive review/edit flow for generated subtitle
lines before output is treated as final.

## Decision

Use `typer` for the command-line interface (argument/option parsing,
`--help` generation, subcommands), and `rich` for the progress indicator
required by FR-011, driven by `faster-whisper`'s segment-by-segment
transcription output.

## Alternatives Considered

- **stdlib `argparse` + manual `\r`-based progress printing**: Zero extra
  dependencies, but requires materially more hand-written code to
  reproduce the same argument-parsing ergonomics and progress display,
  with no first-class `--help` generation; rejected as higher
  maintenance cost for equivalent behavior.
- **`click` directly**: `typer` is a thin layer over `click` with the
  same underlying ecosystem and compatibility; `click`'s decorator style
  is more verbose than `typer`'s type-hint-driven style for this CLI's
  argument set, so `typer` was preferred for readability.

## Consequences

- Adds two dependencies (`typer`, `rich`) scoped to `src/cli/` (Project
  Structure); both are widely used, actively maintained libraries with
  no known cross-platform gaps for the Windows/macOS/Linux target
  (Technical Context: Target Platform).
- `typer`'s auto-generated `--help` output becomes part of what
  `contracts/cli.md` describes and what `tests/contract/` verifies —
  contract tests should assert against actual CLI output rather than
  hand-duplicating it, so the two don't drift.
- FR-011's progress percentage is derived from
  `current_segment_end_seconds / video.duration_seconds` during the
  `Transcribing` state (data-model.md: ProcessingJob); `rich`'s
  determinate progress bar consumes that ratio directly, so the ASR
  engine's segment callback is the sole driver of progress updates — if
  `faster-whisper`'s segment emission is bursty or infrequent for a given
  video, the progress bar's perceived smoothness depends on that
  cadence, not on `rich` itself.
- The interactive review/edit flow (FR-009/FR-010) is expected to be
  built on the same `typer`/`rich` stack (e.g. `rich` prompts/tables) for
  consistency with the progress display, though the exact review-flow UX
  is a `/speckit-tasks`/implementation-level detail, not fixed by this
  ADR.
