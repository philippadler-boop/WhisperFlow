<!--
Sync Impact Report
- Version change: (unratified template) → 1.0.0
- Rationale: initial ratification. The prior file was the unfilled
  constitution-template scaffold (all placeholder tokens); this is the
  first time project-specific principles are recorded here.
- Modified principles: n/a (all five are new)
- Added sections:
  - Core Principles: I. Subagent Separation of Powers, II. Two Human
    Approval Gates, III. Requirement Traceability, IV. Branch-per-Task /
    Protected Main, V. Evidence-Based Validation
  - Documentation & Artifact Structure
  - Development Workflow
  - Governance
- Removed sections: none
- Templates checked for alignment:
  - .specify/templates/plan-template.md — references "Constitution Check"
    generically ("[Gates determined based on constitution file]"); no
    edit needed, gates below are consistent with it.
  - .specify/templates/spec-template.md, tasks-template.md,
    checklist-template.md — no constitution-specific references found.
- Deferred TODOs: none. This command's own scope is limited to the
  constitution; content derived from CLAUDE.md, .claude/agents/*, and
  README.md is treated as authoritative source for these principles per
  the scope guard (no application files were touched).
-->

# WhisperFlow Constitution

## Core Principles

### I. Subagent Separation of Powers
Five roles — `analyst`, `architect`, `developer`, `reviewer`, `qa` — each
operate under the restricted tool allowlist defined for them in
`.claude/agents/`, and MUST NOT be granted tools beyond that allowlist. The
`reviewer` subagent MUST NOT have `Write` or `Edit` tools. No subagent may
merge its own work: merging to `main` and publishing a release are always a
human action, never delegated to any subagent, regardless of how routine
the change appears.

Rationale: independence between the role that writes code and the role
that judges it is what makes review meaningful. A reviewer that can fix
what it's reviewing is checking its own blind spots, not someone else's.

### II. Two Human Approval Gates
Human approval is required at exactly two points: **Requirements/Design
sign-off** (before an approved requirements spec or architecture doc is
acted upon) and **Merge/Release** (before a PR merges to `main` or a
release is published). Every other step — analysis, design drafting,
implementation, review, QA — proceeds without blocking on human approval.

Rationale: gating every step produces rubber-stamp fatigue and stalls the
pipeline without improving outcomes. Concentrating human judgment at the
two points where a mistake is costliest — locking in the wrong
requirements, or shipping the wrong code — keeps a human in control
without making them a bottleneck on everything in between.

### III. Requirement Traceability
Requirements are written as a numbered, testable list (`REQ-001`,
`REQ-002`, ...). Every task in the architect's breakdown MUST reference
the `REQ-xxx` ID(s) it satisfies. Every PR MUST reference the `REQ-`/issue
ID it implements, in its title or body. This is a hard rule starting with
the first PR — it does not wait until a CI check exists to enforce it;
once such a check exists, it becomes a required check, not a new
obligation.

Rationale: traceability adopted "once we get around to it" never actually
gets adopted. Treating it as load-bearing from day one is cheaper than
retrofitting it, and it's the only thing that lets `reviewer` and `qa`
confirm a PR does what it claims rather than just that it looks
plausible.

### IV. Branch-per-Task, Protected Main
One feature branch per GitHub Issue. Nobody — human or subagent — commits
directly to `main`; `main` is branch-protected and every change lands via
PR.

Rationale: keeps each unit of work independently reviewable and
revertible, and is what makes the Merge/Release gate (Principle II)
enforceable in practice rather than only in policy.

### V. Evidence-Based Validation
`qa` confirms a requirement is satisfied by actually running the software
(or the relevant build/test) and observing real output, mapping each
`REQ-xxx` to the concrete evidence that closes it. A green CI run is not,
by itself, evidence that a requirement is met — it confirms tests passed,
not that the right thing was built. Each validation report lives under
`docs/validation/`, one per task/PR, structured as requirement → evidence
→ pass/fail.

Rationale: CI verifies what was written against the tests that were
written; it cannot verify that what was asked for actually exists.
Closing that gap requires someone to independently exercise the behavior
the requirement describes.

## Documentation & Artifact Structure

- `docs/ideas/` holds raw, human-authored idea notes — the starting point
  before any Spec Kit artifact exists.
- Concept briefs and requirements specs are produced via GitHub Spec Kit,
  following Spec Kit's own layout rather than a parallel one invented for
  this repo.
- `docs/architecture.md` is the architect-owned architecture doc, updated
  in place as the design evolves.
- `docs/adr/` holds one Architecture Decision Record per non-trivial
  architectural decision, each structured as **Context** / **Decision** /
  **Alternatives Considered** / **Consequences**.
- `docs/validation/` holds `qa`'s validation reports, one per task/PR
  (Principle V).
- Review reports are not files: `reviewer` returns its report as text, and
  whoever invoked it is responsible for posting that as the actual PR
  review.

## Development Workflow

WhisperFlow is the pilot project for the AI dev pipeline described in the
sibling `ai-dev-pipeline` repo, and follows its lifecycle: Idea → Concept →
Requirements → Architecture → Implementation → Test → Review → Validation
→ Release → Maintenance. The Requirements/Design gate (Principle II) sits
between Requirements/Architecture and Implementation; the Merge/Release
gate sits between Validation and Release. The reasoning behind why the
pipeline is shaped this way lives in `ai-dev-pipeline` and is not required
reading for day-to-day work here — this constitution and `CLAUDE.md` are
the operative documents for that.

## Governance

This constitution supersedes any other stated practice for this
repository where the two conflict. `CLAUDE.md` carries supplementary
day-to-day guidance and MUST NOT contradict this constitution; where they
diverge, this constitution wins and `CLAUDE.md` should be updated to
match.

Amendments are made by running `/speckit-constitution` again and updating
this file directly. Each amendment MUST update the Sync Impact Report at
the top of this file and bump **Version** per semantic versioning: MAJOR
for backward-incompatible principle removal or redefinition, MINOR for a
new principle or materially expanded guidance, PATCH for clarification,
wording, or typo fixes that change no rule.

Every PR and every `reviewer` review MUST verify compliance with the
principles above. Any deviation from a principle MUST be justified
explicitly in the PR description, not introduced silently.

**Version**: 1.0.0 | **Ratified**: 2026-09-03 | **Last Amended**: 2026-09-03
