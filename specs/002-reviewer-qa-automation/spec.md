# Feature Specification: Automate `reviewer` and `qa` via GitHub Actions

**Feature Branch**: `002-reviewer-qa-automation` *(not yet cut — see Process
Note at the end of this document)*

**Created**: 2026-09-17

**Status**: Draft — proposal stage, not approved for implementation.
Every requirement below is a proposal pending human sign-off at the
Requirements Gate; nothing here authorizes the Architect or Developer to
proceed.

**Input**: User description: "extend automation to also run `reviewer` and
`qa` themselves via GitHub Actions... so the whole task lifecycle
(implement → review → fix → qa → ready-to-merge) runs without a human
driving each step." (from `docs/ideas/reviewer-qa-automation.md`)

This document collapses the concept brief and requirements spec into one
lightweight artifact, per the Analyst's standard process for anything
smaller than a multi-week feature.

## Current State (for accurate framing — not a proposal)

As implemented today (`.claude/agents/*.md`, `CLAUDE.md`'s Subagents
section, `.github/workflows/claude-dev-agent.yml`):

- `developer` runs unattended via `claude-dev-agent.yml`, triggered by
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
- `claude-dev-agent.yml`'s own header comment states this arrangement
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
that `claude-dev-agent.yml` already automates still stalls waiting for a
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
  diff in an Actions context, or the exact automation-mode tool allowlist
  for `qa`'s Bash access — those are Architect-phase design decisions that
  depend on requirements this document leaves open (see Open Questions).
- **Not** setting a specific cost/latency budget or threshold — the idea
  note explicitly defers this to future scoping, not to a decision made in
  this spec.
- **Not** automating `analyst` or `architect`; this proposal is scoped to
  `reviewer` and `qa` only, matching the idea note.

## Open Questions / [NEEDS CLARIFICATION]

These are carried forward from `docs/ideas/reviewer-qa-automation.md`
because they are genuinely open tradeoffs for the project owner to decide,
not implementation details the Architect can resolve unilaterally. Several
of the requirements below are intentionally written as constraints that
hold *regardless* of how these are answered, rather than presupposing an
answer.

1. **[NEEDS CLARIFICATION — safety-property replacement]** What replaces
   the human-in-the-loop gate that manual `reviewer` invocation currently
   provides? Candidates include: relying solely on the existing human
   merge gate (already a hard rule); adding a new explicit gate (e.g. a
   required human "approved for automation" signal per PR or per repo);
   or something else. Not deciding this and shipping automated `reviewer`
   anyway would silently remove a documented safety property.
2. **[NEEDS CLARIFICATION — qa Bash containment]** Is CI's existing
   `ci.yml` `test`-job sandboxing sufficient containment for `qa`'s
   broader Bash use (installing dependencies, running real
   transcriptions, sometimes downloading models), or does automated `qa`
   need a narrower, automation-mode-specific tool allowlist than its
   current interactive one?
3. **[NEEDS CLARIFICATION — round-cap correctness under automated review]**
   Does `MAX_AUTO_FIX_ROUNDS`, as currently computed (counting
   `CHANGES_REQUESTED` reviews on the PR), still correctly bound a fully
   automated review→fix loop, or does an automated reviewer posting
   reviews faster/more reliably than a human require a different
   mechanism (e.g. a wall-clock cap, or counting automated `qa` commits
   toward the same cap)?
4. **[NEEDS CLARIFICATION — qa trigger timing]** If `qa` is triggered
   automatically, what condition establishes that "review has genuinely
   settled" before `qa` runs — e.g. does the workflow need to wait for "a
   review cycle produced zero new commits for one full round," or some
   other condition? (This directly guards the concern already on record as
   bugs.md item #3: qa running before review has actually settled.)
5. **[NEEDS CLARIFICATION — cost/latency budget]** What is the actual
   per-task increase in agent API spend and turnaround time from adding
   two more automated invocations (reviewer, qa) per fix round, and is
   that increase acceptable? No target or threshold currently exists; this
   needs real measurement, not an estimate, before a go/no-go decision.

## Requirements

Numbered for independent traceability; each is intended to be specific
enough for `qa` to check against a running/observable workflow rather than
by reading source alone.

- **FR-001**: This feature MUST NOT be enabled for real (non-throwaway)
  issues/PRs until Open Question 1 (safety-property replacement) has an
  explicit, documented answer approved by the project owner — either "the
  existing Merge/Release human gate is sufficient" or a specific
  additional gate, but not left undecided.
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
  `claude-dev-agent.yml`'s existing `pull_request_review` /
  `changes_requested` trigger continues to fire correctly without
  modification.
- **FR-005**: When `qa` runs in automation mode, its Bash access MUST be
  constrained by an explicit, documented containment mechanism (see Open
  Question 2) rather than silently inheriting its full interactive Bash
  capability unmodified into a CI runner.
- **FR-006**: Automated `qa` MUST commit its validation report to the same
  branch as the PR being validated (per the existing one-PR-per-task
  convention in CLAUDE.md and `.claude/agents/qa.md`) and MUST NOT open a
  second branch or PR to do so. If the target branch/PR no longer exists
  or is already merged, the workflow MUST fail visibly (e.g. a failed run
  and/or a posted comment) rather than silently opening a new branch/PR to
  route around it.
- **FR-007**: Automated `qa` MUST NOT be triggered against a PR until the
  condition established in answer to Open Question 4 (review has
  genuinely settled) is met. Until that condition is defined and approved,
  automated `qa` MUST NOT be enabled for real work.
- **FR-008**: If `reviewer` becomes automated, `MAX_AUTO_FIX_ROUNDS` (or
  its replacement per Open Question 3) MUST still cap the total number of
  automatic review→fix cycles on a given PR at a finite, configurable
  number, and reaching that cap MUST stop further automatic dispatch and
  hand back to a human (mirroring `claude-dev-agent.yml`'s existing
  "Stop and hand back" behavior), regardless of whether the cap's
  underlying counting mechanism changes.
- **FR-009**: Before automated `reviewer` and/or `qa` are enabled for real
  work (as opposed to a throwaway smoke-test issue/PR), this feature MUST
  produce a documented measurement of the actual per-task increase in API
  cost and turnaround/latency versus today's developer-only automation
  (Open Question 5), sufficient for the project owner to make an
  accept/reject decision on the increase.
- **FR-010**: Any new automation-mode workflow (or modification to
  `claude-dev-agent.yml`) introduced by this feature MUST grant tools
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

## Success Criteria

- **SC-001**: At least one real (non-throwaway) issue completes the full
  lifecycle — `claude-dev` label → `developer` PR → automated `reviewer`
  verdict → (fix round(s) if needed) → automated `qa` validation report —
  with no human running a local `reviewer` or `qa` session, while a human
  still performs the final merge.
- **SC-002**: FR-002's tool-restriction smoke test for automated
  `reviewer` passes (zero unexpected tool grants) before automated
  `reviewer` is used on any real work.
- **SC-003**: FR-009's documented cost/latency measurement exists, and the
  project owner has made an explicit accept/reject call on the increase,
  before automated `reviewer`/`qa` is enabled for `claude-dev`-labeled
  issues by default (as opposed to opt-in smoke testing only).
- **SC-004**: Reviewing at least one real automated run confirms neither
  the Requirements/Design gate nor the Merge/Release gate was bypassed or
  weakened (e.g. no auto-merge occurred; no PR merged without an
  independent review verdict recorded).
- **SC-005**: All five Open Questions above have an explicit, recorded
  answer (not a default/implicit one) before this feature exits the
  Requirements Gate.

## Assumptions

- This feature reuses the existing `claude-code-action` + automation-mode
  (`prompt` input) + `--allowedTools` pattern already proven for
  `developer` in `claude-dev-agent.yml`, rather than introducing a
  different automation mechanism — no evidence in the idea note suggests
  otherwise.
- "Automated" here means GitHub-Actions-triggered, unattended execution of
  the existing `reviewer`/`qa` subagent definitions (`.claude/agents/`) —
  not a rewrite of their responsibilities or prompts.
- The idea note's five open-question categories are treated as an
  exhaustive starting list for this spec's Open Questions, but the
  Architect or a later Analyst pass may surface additional ones once a
  concrete design is attempted.

## Process Note (not a requirement — procedural, for whoever picks this up)

Per `CLAUDE.md`'s Working Conventions, Spec Kit planning phases (including
this Analyst pass) are expected to happen on a real feature branch, merged
via PR at Design Gate approval — not authored directly on `main`. This
document was authored by the `analyst` subagent, which has no git/Bash
tools and cannot cut a branch or commit itself; whoever takes this spec
forward (moves it toward Architect/Design) is responsible for putting it
on a `002-reviewer-qa-automation` branch and opening a PR, consistent with
how `001-video-subtitle-generator` is documented as a one-time exception
and every feature after it is not.
