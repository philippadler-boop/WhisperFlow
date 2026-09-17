# Feature Specification: Automate `reviewer` and `qa` via GitHub Actions

**Feature Branch**: `002-reviewer-qa-automation` (PR #133)

**Created**: 2026-09-17

**Status**: Requirements Gate approved (2026-09-17) — see "Resolved
Decisions" below. All five Open Questions have explicit project-owner
answers; the requirements and success criteria have been updated to
reflect them. This authorizes the Architect to proceed to Design/Plan.

**Input**: User description: "extend automation to also run `reviewer` and
`qa` themselves via GitHub Actions... so the whole task lifecycle
(implement → review → fix → qa → ready-to-merge) runs without a human
driving each step." (from `docs/ideas/reviewer-qa-automation.md`)

This document collapses the concept brief and requirements spec into one
lightweight artifact, per the Analyst's standard process for anything
smaller than a multi-week feature.

## Current State (for accurate framing — not a proposal)

As implemented today (`.claude/agents/*.md`, `CLAUDE.md`'s Subagents
section, `.github/workflows/claude-agents-pipeline.yml`):

- `developer` runs unattended via `claude-agents-pipeline.yml`, triggered by
  either (a) an issue getting the `claude-dev` label (implement a fresh
  task, open a new PR), or (b) a `pull_request_review` event with
  `state: changes_requested` (push a fix commit to the existing PR's
  branch). A `MAX_AUTO_FIX_ROUNDS` cap (default 3) stops the second path
  and hands back to a human once that many `CHANGES_REQUESTED` reviews
  have accumulated on a PR.
- `reviewer` and `qa` are deliberately **manually-invoked local sessions**
  — a human runs `reviewer` against a PR's diff (pasting `git diff
  main...<branch>` or `gh pr diff <PR>`, since `reviewer` has no
  Bash/git/gh tools by design) and decides whether to post a
  request-changes review; a human runs `qa` after review settles, and
  `qa` commits its own validation report onto the PR's branch.
- `claude-agents-pipeline.yml`'s own header comment states this arrangement
  "does not create a fully closed, unsupervised review loop," specifically
  *because* `reviewer` is still manually invoked — the round cap is
  characterized as a safety net for that manual path being scripted/piped
  faster than a human is really watching, not as a substitute for the
  human decision itself.
- Two human-approval gates exist project-wide and are explicitly meant to
  be the *only* two: Requirements/Design sign-off, and Merge/Release.
  Everything else is meant to proceed without blocking — but "everything
  else" today still includes reviewer's request-changes/approve decision
  and qa's validation, both currently human-driven in practice even though
  not formally listed as approval gates.

## Problem

Only the `developer` step of the task lifecycle (implement → review → fix
→ qa → ready-to-merge) runs unattended. `reviewer` and `qa` each require a
human to start a local session, which means the review-triggered fix loop
that `claude-agents-pipeline.yml` already automates still stalls waiting for a
human to run `reviewer` again after each fix, and waiting for a human to
run `qa` after that. The idea is to extend the existing unattended-agent
pattern (GitHub Actions + `claude-code-action`, automation mode,
`--allowedTools` mirroring the subagent's own tool list) to `reviewer` and
`qa` as well, so the lifecycle can run end-to-end without a human driving
each intermediate step — while the two existing human-approval gates
(Requirements/Design sign-off, Merge/Release) remain exactly as they are
today.

## Stakeholders / Target Users

This is a change to the project's own AI-dev-pipeline process, not to
WhisperFlow the product. The "user" of this feature is whoever operates
this repo's pipeline (currently its owner) — the person who today has to
be present to run `reviewer` and `qa` locally, and who bears the
consequences (cost, latency, and any correctness/safety regression) if
those roles are automated instead.

## Non-Goals (explicit)

- **Not** removing or altering either of the two existing human-approval
  gates (Requirements/Design sign-off; Merge/Release). Both remain hard
  rules regardless of what this feature decides.
- **Not** loosening `reviewer`'s no-Write/Edit/Bash/git/gh tool
  restriction, or the "no subagent merges its own work" rule — both are
  documented in CLAUDE.md as load-bearing and out of scope to weaken here.
- **Not** deciding the concrete mechanism for supplying `reviewer` a PR
  diff in an Actions context — that remains an Architect-phase design
  decision (FR-003); the containment/trigger-timing/cap-value questions
  that used to be open are now resolved (see "Resolved Decisions").
- **Not** setting a specific cost/latency budget or threshold — the idea
  note explicitly defers this to future scoping, not to a decision made in
  this spec.
- **Not** automating `analyst` or `architect`; this proposal is scoped to
  `reviewer` and `qa` only, matching the idea note.

## Resolved Decisions (Requirements Gate — approved 2026-09-17)

The five Open Questions below were put to the project owner directly and
each has an explicit answer. This section is kept as a permanent record of
what was asked and decided, rather than deleted, so the reasoning survives
even after the requirements below are updated to match.

1. **Safety-property replacement — DECIDED: full automation, no new gate.**
   The existing Merge/Release human gate is the only safety property that
   remains. A labeled issue runs the entire `developer → reviewer → qa`
   cycle unattended, repeating automatically until `reviewer` has no more
   findings (an APPROVE verdict) and CI is green — a human is not expected
   to run `reviewer` or `qa` locally, or to approve anything mid-cycle. The
   human's only remaining checkpoint is the final merge.
2. **qa Bash containment — DECIDED: reuse existing CI sandboxing.** No new
   containment mechanism is introduced. Automated `qa` runs with the same
   GitHub Actions runner isolation `ci.yml`'s `test` job already relies on;
   its Bash use (installing deps, real transcriptions, model downloads) is
   treated as equivalent in kind to what `test` already does.
3. **Round-cap correctness — DECIDED: keep counting reviews, raise the cap
   to 5.** `MAX_AUTO_FIX_ROUNDS`'s existing mechanism (counting
   `CHANGES_REQUESTED` reviews on the PR) is kept as-is — a review is a
   review regardless of who/what posted it. The default cap is raised from
   3 to **5**, since full automation (decision 1) means more cycles may be
   needed to reach a clean approve without a human ever intervening
   mid-loop.
4. **qa trigger timing — DECIDED: trigger only on an APPROVE verdict.**
   Automated `qa` is triggered exclusively by automated `reviewer` posting
   an actual `APPROVE` PR review — never on a `CHANGES_REQUESTED` review,
   and never on a bare passage of time or commit-quiescence heuristic. This
   directly resolves the concern on record as bugs.md item #3 / issue #132
   (qa running before review has actually settled): an APPROVE verdict is
   an unambiguous signal that no more fix rounds are expected.
5. **Cost/latency budget — DECIDED: measure via dedicated API keys before
   enabling for real work.** Rather than reusing `ANTHROPIC_API_KEY_DEV`
   for the new automated `reviewer`/`qa` invocations, two new dedicated
   GitHub Actions secrets are provisioned — `ANTHROPIC_API_KEY_REVIEWER`
   and `ANTHROPIC_API_KEY_QA` — mirroring how `ANTHROPIC_API_KEY_DEV`
   already isolates `developer`'s spend. This lets actual per-role API cost
   be measured directly from each key's own usage, not estimated or
   commingled with `developer`'s spend. See "Manual Setup Required" below
   — this is a manual, human action (creating Anthropic API keys and
   registering them as repo secrets), not something the Architect or an
   agent can provision itself.

## Requirements

Numbered for independent traceability; each is intended to be specific
enough for `qa` to check against a running/observable workflow rather than
by reading source alone.

- **FR-001**: Per Resolved Decision 1, no new human-approval gate is
  introduced by this feature. The existing Merge/Release gate is the sole
  remaining human checkpoint; a labeled issue's `developer → reviewer →
  qa` cycle MUST be able to run to completion (an APPROVE verdict and
  green CI, or exhaustion of the round cap per FR-008) without any human
  action beyond the final merge decision.
- **FR-002**: When `reviewer` runs in automation mode, its
  `claude-code-action` invocation MUST grant it no tools beyond its
  documented interactive allowlist (`Read, Grep, Glob` per
  `.claude/agents/reviewer.md`) — specifically it MUST NOT receive
  `Write`, `Edit`, `Bash`, `git`, or `gh`, regardless of the invoking
  workflow's own token permissions. This MUST be confirmed by an
  invocation-based smoke test (the agent actually attempting a
  disallowed tool call and the result being a literal denial, not a
  self-report) before being trusted on real work — the same discipline
  CLAUDE.md's Operational Lessons already require for `developer`'s
  automation.
- **FR-003**: Since `reviewer` has no Bash/git/gh tool access in any mode,
  the GitHub Actions workflow itself (not the `reviewer` agent) MUST be
  the component that obtains the PR diff and supplies it into `reviewer`'s
  prompt/context. The specific mechanism (diff text embedded in the
  prompt vs. branch checked out for `Read`/`Grep`/`Glob`) is left to the
  Architect phase, but whichever mechanism is chosen MUST NOT satisfy this
  requirement by granting `reviewer` new tools.
- **FR-004**: Automated `reviewer`'s verdict (approve, or request-changes
  with specific, actionable points) MUST be posted as an actual GitHub PR
  review via the workflow's own API call (not by the agent directly,
  which has no `gh`/`git`), using the same approve/request-changes
  semantics a human reviewer uses today, so that
  `claude-agents-pipeline.yml`'s existing `pull_request_review` /
  `changes_requested` trigger continues to fire correctly without
  modification.
- **FR-005**: Per Resolved Decision 2, when `qa` runs in automation mode,
  its Bash access runs under the same GitHub Actions runner isolation
  `ci.yml`'s `test` job already relies on — no additional, narrower
  containment mechanism is required beyond that existing sandboxing.
- **FR-006**: Automated `qa` MUST commit its validation report to the same
  branch as the PR being validated (per the existing one-PR-per-task
  convention in CLAUDE.md and `.claude/agents/qa.md`) and MUST NOT open a
  second branch or PR to do so. If the target branch/PR no longer exists
  or is already merged, the workflow MUST fail visibly (e.g. a failed run
  and/or a posted comment) rather than silently opening a new branch/PR to
  route around it.
- **FR-007**: Per Resolved Decision 4, automated `qa` MUST be triggered
  exclusively by automated `reviewer` posting an `APPROVE` PR review for
  that PR's current commit — never by a `CHANGES_REQUESTED` review, and
  never by a time-based or commit-quiescence heuristic. If `qa` cannot
  determine that the most recent review event on the PR was an `APPROVE`
  matching the current HEAD commit, it MUST NOT run.
- **FR-008**: Per Resolved Decision 3, `MAX_AUTO_FIX_ROUNDS` keeps its
  existing counting mechanism (total `CHANGES_REQUESTED` reviews on the
  PR) and its default value MUST be raised from 3 to **5** as part of this
  feature. Reaching the cap MUST still stop further automatic dispatch and
  hand back to a human, mirroring `claude-agents-pipeline.yml`'s existing "Stop
  and hand back" behavior.
- **FR-009**: Per Resolved Decision 5, automated `reviewer` and `qa`
  invocations MUST authenticate using two new dedicated Anthropic API
  keys — `ANTHROPIC_API_KEY_REVIEWER` and `ANTHROPIC_API_KEY_QA` —
  provisioned as GitHub Actions secrets, distinct from
  `ANTHROPIC_API_KEY_DEV`. Before this feature is enabled for real
  (non-throwaway) work, at least one full automated cycle MUST be run
  against a throwaway issue/PR and its per-key API cost and wall-clock
  turnaround time recorded, so the project owner can make an
  accept/reject call on the actual, measured increase — not an estimate.
- **FR-010**: Any new automation-mode workflow (or modification to
  `claude-agents-pipeline.yml`) introduced by this feature MUST grant tools
  explicitly via `--allowedTools` (or an equivalent `settings.permissions`
  block) mirroring the invoked subagent's own declared `tools:`
  frontmatter exactly, per the existing "automation-mode grants zero tool
  access by default" operational lesson — verified by an invocation-based
  smoke test showing `permission_denials_count: 0` for tools the subagent
  is supposed to have, and a genuine denial for any tool it is not
  supposed to have.
- **FR-011**: No workflow introduced or modified by this feature may merge
  a PR or publish a release automatically, under any reviewer/qa outcome
  (including a clean approve-then-pass sequence). The Merge/Release human
  gate is unaffected by this feature.
- **FR-012**: This feature MUST NOT modify `.claude/agents/reviewer.md`'s
  `tools:` line or `.claude/agents/qa.md`'s validation-report-only-artifact
  rule as a side effect of adding automation — those interactive-mode
  contracts stay exactly as documented today; automation mode only adds a
  workflow around invoking them, per FR-002/FR-005's containment
  requirements.
- **FR-013**: If an automated `reviewer` or `qa` run fails, errors, or
  cannot obtain an input it needs (e.g. cannot fetch a diff, cannot
  determine which branch to check out, hits the round cap), the workflow
  MUST surface this visibly — a failed workflow run and/or a posted PR
  comment — rather than completing with exit success and no observable
  output. (This mirrors the M2/M8 lesson on record: a silently-successful
  run with `permission_denials_count: 20` was only caught because
  `show_full_output` was already enabled for inspection.)
- **FR-014**: This feature MUST NOT be considered ready for the Architect
  to design against until the two new API keys in FR-009 have actually
  been created and registered as repo secrets — see "Manual Setup
  Required" below. This is a manual, human action outside any agent's
  tool access.

## Success Criteria

- **SC-001**: At least one real (non-throwaway) issue completes the full
  lifecycle — `claude-dev` label → `developer` PR → automated `reviewer`
  verdict → (fix round(s) if needed) → automated `qa` validation report —
  with no human running a local `reviewer` or `qa` session, while a human
  still performs the final merge.
- **SC-002**: FR-002's tool-restriction smoke test for automated
  `reviewer` passes (zero unexpected tool grants) before automated
  `reviewer` is used on any real work.
- **SC-003**: FR-009's throwaway-issue cost/latency measurement (using the
  dedicated `ANTHROPIC_API_KEY_REVIEWER`/`ANTHROPIC_API_KEY_QA` keys)
  exists, and the project owner has made an explicit accept/reject call on
  the measured increase, before automated `reviewer`/`qa` is enabled for
  `claude-dev`-labeled issues by default.
- **SC-004**: Reviewing at least one real automated run confirms the
  Merge/Release gate was not bypassed or weakened (no auto-merge occurred;
  no PR merged without an independent, automated APPROVE review recorded
  from `reviewer` and a validation report recorded from `qa`).
- **SC-005**: ~~All five Open Questions above have an explicit, recorded
  answer~~ — **met 2026-09-17**; see "Resolved Decisions" above.

## Assumptions

- This feature reuses the existing `claude-code-action` + automation-mode
  (`prompt` input) + `--allowedTools` pattern already proven for
  `developer` in `claude-agents-pipeline.yml`, rather than introducing a
  different automation mechanism — no evidence in the idea note suggests
  otherwise.
- "Automated" here means GitHub-Actions-triggered, unattended execution of
  the existing `reviewer`/`qa` subagent definitions (`.claude/agents/`) —
  not a rewrite of their responsibilities or prompts.
- The idea note's five open-question categories were treated as an
  exhaustive starting list for this spec's now-resolved decisions, but the
  Architect or a later Analyst pass may surface additional open questions
  once a concrete design is attempted.

## Manual Setup Required (not automatable — see FR-009/FR-014)

Before the Architect can treat this feature as buildable, the project
owner must:

1. Create two new Anthropic API keys, dedicated to this feature and
   distinct from the existing `developer` key — one for `reviewer`, one
   for `qa`.
2. Register them as GitHub Actions repo secrets named
   `ANTHROPIC_API_KEY_REVIEWER` and `ANTHROPIC_API_KEY_QA`, mirroring how
   `ANTHROPIC_API_KEY_DEV` is already configured for `developer` in
   `claude-agents-pipeline.yml`.

This is a manual, human action — no agent in this pipeline (analyst,
architect, developer, reviewer, qa) has the access needed to create
Anthropic API keys or GitHub repo secrets itself. Until both secrets
exist, the Architect's design can proceed on paper, but no automated
`reviewer`/`qa` workflow can actually be exercised, even as a throwaway
smoke test.

## Process Note (not a requirement — procedural, historical record)

Per `CLAUDE.md`'s Working Conventions, Spec Kit planning phases (including
this Analyst pass) happen on a real feature branch, merged via PR at
Design Gate approval — not authored directly on `main`. This document was
originally authored by the `analyst` subagent, which has no git/Bash
tools and could not cut a branch or commit itself; the orchestrating
session subsequently created the `002-reviewer-qa-automation` branch,
committed this document, and opened PR #133, consistent with how
`001-video-subtitle-generator` is documented as a one-time exception and
every feature after it is not.
