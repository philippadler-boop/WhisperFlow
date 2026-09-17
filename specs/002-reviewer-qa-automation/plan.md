# Implementation Plan: Automate `reviewer` and `qa` via GitHub Actions

**Branch**: `002-reviewer-qa-automation` | **Date**: 2026-09-17 | **Spec**: [spec.md](spec.md) (PR #133, Requirements Gate approved)

**Input**: Feature specification from `/specs/002-reviewer-qa-automation/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Extend `.github/workflows/claude-dev-agent.yml`'s existing unattended
`developer` automation so that `reviewer` and `qa` also run via GitHub
Actions instead of as manually-invoked local sessions, closing the loop so
a `claude-dev`-labeled issue runs `developer → reviewer → (fix rounds) →
qa` to completion with no human action beyond the final Merge/Release
decision (Principle II). Per spec.md's Resolved Decisions: no new
human-approval gate is introduced; `qa` reuses `ci.yml`'s existing runner
sandboxing as-is; `MAX_AUTO_FIX_ROUNDS` is raised from 3 to 5; automated
`qa` is triggered exclusively by an automated `reviewer` `APPROVE` verdict
matching current HEAD; and cost/latency is measured via two new dedicated
Anthropic API key secrets (`ANTHROPIC_API_KEY_REVIEWER`,
`ANTHROPIC_API_KEY_QA`, already provisioned) before real use.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow syntax) + POSIX shell
steps — no new application language; this feature only extends
`.github/workflows/claude-dev-agent.yml` and does not touch WhisperFlow's
Python source under `src/`/`tests/`.

**Primary Dependencies**: `anthropics/claude-code-action@v1` (already used
by `claude-dev-agent.yml` for `developer`; this feature adds two more
invocations of it, one per subagent), the `gh` CLI (already available on
GitHub-hosted runners) for the workflow's own diff-fetch and PR-review-post
steps, GitHub's `pull_request_review` webhook event.

**Storage**: N/A (no persistent state beyond what already exists — PR
review history and commit history on GitHub, which the workflow reads via
`gh api`/`gh pr` rather than maintaining its own store).

**Testing**: Invocation-based smoke tests against a throwaway issue/PR
(per FR-002/FR-009/FR-010 — an agent actually attempting a disallowed tool
call and observing a literal denial, not a self-report), the same
discipline `claude-dev-agent.yml`'s own header comments already document
for `developer`'s automation-mode tool grants.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners, matching
`ci.yml`'s existing `test` job per Resolved Decision 2 — no new runner
image or containment layer).

**Project Type**: CI/CD pipeline automation (a workflow-YAML feature, not
a library/CLI/web-service addition to the WhisperFlow product itself — see
spec.md's Stakeholders section: the "user" of this feature is whoever
operates this repo's pipeline, not a WhisperFlow end user).

**Performance Goals**: No fixed target — FR-009 requires *measuring* the
actual per-task API-cost and wall-clock-turnaround increase from adding
two more automated invocations per fix round, then getting an explicit
project-owner accept/reject call on the measured number (not an a priori
budget).

**Constraints**: `reviewer`'s automation-mode invocation MUST NOT receive
tools beyond `Read, Grep, Glob` (FR-002/FR-012); `qa`'s automation-mode
invocation MUST NOT receive tools beyond its documented interactive
allowlist (FR-005/FR-012); no workflow introduced or modified by this
feature may merge a PR or publish a release under any outcome (FR-011);
automated `qa` MUST commit its report onto the same PR branch, never a
second branch/PR (FR-006, Constitution Principle IV/V).

**Scale/Scope**: Single repository (`philippadler-boop/WhisperFlow`)'s own
pipeline; scoped to `reviewer` and `qa` only (spec.md Non-Goals explicitly
excludes automating `analyst`/`architect`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Subagent Separation of Powers)** — PASS. This feature's
  entire design is organized around *preserving* `reviewer`'s
  no-Write/Edit tool restriction and the "no subagent merges its own work"
  rule under automation (FR-002, FR-011, FR-012); it does not loosen
  either. `qa`'s existing `Bash`/validation-report-only-artifact contract
  (`.claude/agents/qa.md`) is likewise left unmodified (FR-012) — only a
  workflow is added around invoking it, not a change to what it's allowed
  to do.
- **Principle II (Two Human Approval Gates)** — PASS, with an explicit,
  approved tradeoff. Resolved Decision 1 keeps the Merge/Release gate as
  the *only* remaining human checkpoint for this lifecycle (no new gate
  added); this was a deliberate project-owner choice made directly at the
  Requirements Gate (spec.md "Resolved Decisions"), not a silent removal
  of a documented safety property. The Requirements/Design gate itself is
  unaffected — this very document is part of satisfying it.
- **Principle III (Requirement Traceability)** — PASS. spec.md's 14 FRs
  are numbered and testable; this plan and its Phase 0/1 outputs reference
  them by ID throughout, and every PR implementing this feature's tasks
  will reference the relevant FR-ID/issue per the existing convention.
- **Principle IV (Branch-per-Task, Protected Main)** — PASS, once the
  process gap identified during this planning session is corrected (see
  "Process Correction" below): this feature's own Spec Kit planning
  artifacts (this plan, research.md, data-model.md, contracts/,
  quickstart.md) are committed to the `002-reviewer-qa-automation` branch
  and merged via PR (#133), not authored on `main`, satisfying the
  branch-for-planning-phases requirement this principle added after the
  D1 finding on feature 001.
- **Principle V (Evidence-Based Validation)** — PASS, and this feature
  materially strengthens it going forward: FR-009's mandatory
  throwaway-issue measurement before real use, and FR-002's
  invocation-based (not self-reported) tool-restriction smoke test, are
  both direct applications of "a green CI run is not, by itself, evidence
  that a requirement is met."

No violations requiring justification in Complexity Tracking.

### Process Correction (recorded here per Principle IV/analyst.md gap, not a spec change)

This feature's `spec.md` was originally written directly by the `analyst`
subagent's `Write` tool into `specs/002-reviewer-qa-automation/spec.md`,
bypassing `/speckit.specify` entirely — so `.specify/feature.json` was
never updated (it still pointed at `specs/001-video-subtitle-generator`)
and no `checklists/requirements.md` was generated. This was caught when
`/speckit.plan`'s own setup script resolved the wrong feature. Per the
Constitution's Documentation & Artifact Structure section ("Spec Kit's
native chain... not a parallel structure invented for this repo"),
`analyst`'s Write output is meant to feed `/speckit.specify`, not replace
its Outline step. Since spec.md's content had already gone through direct
Requirements Gate review and approval (the "Resolved Decisions" section,
answered by the project owner in conversation), it was not discarded and
redone from scratch; instead, `.specify/feature.json` was corrected to
point at the right feature directory (the officially-supported override
mechanism per `common.ps1`'s own documented priority order), and this Plan
phase proceeds from the existing, approved spec.md. `analyst.md` and/or
`CLAUDE.md` should be updated separately (tracked as a follow-up, not part
of this feature's own scope) so a future analyst-authored idea doesn't
land directly under `specs/<feature>/` again.

## Project Structure

### Documentation (this feature)

```text
specs/002-reviewer-qa-automation/
├── spec.md              # Requirements Gate approved (Analyst + Resolved Decisions)
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This feature is CI/CD pipeline automation, not a WhisperFlow application
feature — there is no `src/`/`tests/` code to add. The only repository
files this feature touches are:

```text
.github/workflows/
└── claude-dev-agent.yml   # Extended: two new automation-mode invocations
                            # (reviewer, qa) and their trigger wiring, added
                            # alongside the existing developer automation —
                            # not a new workflow file, per the Assumptions
                            # section of spec.md (reuses the same
                            # claude-code-action + automation-mode pattern)

docs/adr/
└── 000X-*.md               # One ADR per significant technical decision
                            # this plan's Phase 1 design surfaces (diff-
                            # supply mechanism, review-posting mechanism,
                            # qa trigger wiring, API key routing) —
                            # written by `architect` after this plan.md
                            # is complete, per architect.md's own process
```

No changes to `src/cli/`, `src/audio/`, `src/transcription/`,
`src/subtitles/`, `src/lib/`, or any `tests/` directory — this feature
does not touch the WhisperFlow product itself (spec.md Stakeholders /
Non-Goals).

**Structure Decision**: Single-file extension of the existing
`claude-dev-agent.yml` workflow (not a new workflow file), consistent with
spec.md's Assumptions ("reuses the existing `claude-code-action` +
automation-mode + `--allowedTools` pattern already proven for `developer`
... rather than introducing a different automation mechanism"). Design
decisions for *how* that extension is structured (new jobs vs. new steps
in existing jobs, diff-supply mechanism, review-posting mechanism) are
worked out in Phase 1 below and recorded as ADRs by `architect`.

## Complexity Tracking

*No violations — Constitution Check above passed without exceptions. This
section is intentionally empty; not filled per the template's own
instruction ("Fill ONLY if Constitution Check has violations that must be
justified").*

## Post-Design Constitution Re-Check

*Per this skill's own workflow: re-evaluate after Phase 1 design.*

research.md, data-model.md, contracts/automation-triggers.md, and
quickstart.md (Phase 0/1 outputs, above) introduce no new violations of
any Core Principle beyond what the pre-design Constitution Check already
assessed:

- The `AutomationActor` open question in data-model.md (how to
  distinguish the automated `reviewer`'s own APPROVE from an unrelated
  human approval) is flagged as needing an invocation-based empirical
  check before `architect` relies on an assumed actor identity — this is
  itself an application of Principle V, not a gap in it.
- contracts/automation-triggers.md's tool-grant and diff-supply/
  review-posting/QA-report contracts restate FR-002/FR-003/FR-004/FR-005/
  FR-006/FR-011/FR-012 as externally-observable guarantees; they do not
  loosen any of them.
- No new source code, dependency, or project structure was introduced
  beyond extending one existing workflow file — Complexity Tracking
  remains empty.

**Result**: PASS. This feature is ready for `architect` to write ADRs
against plan.md/research.md/data-model.md per its own documented process.
