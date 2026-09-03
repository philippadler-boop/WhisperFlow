# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

WhisperFlow — a tool that takes a video and generates subtitles in a chosen
language. It's the pilot project for the AI dev pipeline described in
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
- Concept brief + requirements spec — via GitHub Spec Kit once it's
  installed; follow Spec Kit's own layout rather than inventing a parallel
  one.
- `docs/architecture.md` — architect-owned architecture doc.
- `docs/adr/` — one ADR per non-trivial architectural decision, structured
  as Context / Decision / Alternatives Considered / Consequences.
- `docs/validation/` — qa-owned; one validation report per task/PR, mapping
  each requirement to the evidence that closes it.
- Review reports aren't files: the `reviewer` subagent returns its report
  as text, and whoever invoked it posts that as the actual PR review.

## Working conventions

- Branch-per-task: one feature branch per GitHub Issue, never commit
  directly to `main` (branch-protected, PR required).
- Every PR references the `REQ-`/issue ID it implements. This becomes a
  required CI check later, but treat it as a hard rule from the first PR
  on, not something that starts mattering once the check exists.
- Human approval gates at exactly two points: Requirements/Design sign-off,
  and Merge/Release. Everything else proceeds without blocking.
