# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

WhisperFlow — a tool that takes a video and generates subtitles. v1 is
transcription-only (captions in the video's own spoken language);
translation into a chosen target language is deferred as a fast-follow
(see `specs/001-video-subtitle-generator/spec.md`). It's the pilot project
for the AI dev pipeline described in
`../ai-dev-pipeline` (a separate, planning-only repo): the first project run
end-to-end through that pipeline's lifecycle. This repo holds the actual
project artifacts (specs, ADRs, code, `.claude/agents/`); the reasoning
behind why the pipeline is shaped the way it is stays in `../ai-dev-pipeline`
and isn't required reading to work in this repo day to day.

## Subagents

Five roles live in `.claude/agents/`: `analyst`, `architect`, `developer`,
`reviewer`, `qa`. Each has its own restricted tool allowlist — see the
individual files for exact scope and responsibilities. Two constraints are
load-bearing and shouldn't be loosened without a good reason:

- `reviewer` has no `Write`/`Edit` — a reviewer that can fix what it's
  reviewing isn't an independent review.
- No subagent merges its own work. Merge to `main` and publishing a release
  are always a human action.

## Where things live

- `docs/ideas/` — raw, human-authored idea notes.
- `specs/<feature>/` — GitHub Spec Kit's own layout: `spec.md`
  (requirements), `research.md`/`data-model.md`/`contracts/`/`quickstart.md`
  (`/speckit.plan` output), `tasks.md` (`/speckit.tasks` output). No
  separate hand-authored architecture doc — `plan.md` and its companions
  are the design record.
- `docs/adr/` — one ADR per non-trivial architectural decision surfaced
  during the Plan phase, structured as Context / Decision / Alternatives
  Considered / Consequences. A companion to `plan.md`, not a replacement.
- `docs/validation/` — qa-owned; one validation report per task/PR, mapping
  each requirement to the evidence that closes it.
- Review reports aren't files: the `reviewer` subagent returns its report
  as text, and whoever invoked it posts that as the actual PR review.

## Working conventions

- Branch-per-task: one feature branch per GitHub Issue, cut from `main`,
  never commit directly to `main` (branch-protected, PR required). Spec
  Kit's planning phases (`/speckit.specify` through `/speckit.analyze`,
  plus `architect`'s ADRs) also use a real feature branch, merged to
  `main` via PR at Design Gate approval -- not `main` directly. See
  constitution.md Principle IV (video-subtitle-generator is a documented
  one-time exception; every feature after it must have a branch).
- Every PR references the `FR-`/issue ID it implements. This becomes a
  required CI check later, but treat it as a hard rule from the first PR
  on, not something that starts mattering once the check exists.
- Human approval gates at exactly two points: Requirements/Design sign-off,
  and Merge/Release. Everything else proceeds without blocking.
