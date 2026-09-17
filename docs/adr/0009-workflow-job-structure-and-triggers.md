# 0009: Job Structure for Automated `reviewer`/`qa` and the Round-Cap Raise

> **Status**: Proposed — pending human approval at the Design Gate
> (Principle II). Not yet binding until sign-off.

## Context

`plan.md`'s Structure Decision fixes that this feature extends the single
existing `.github/workflows/claude-dev-agent.yml` file rather than adding
a new workflow file. Within that constraint, this ADR decides how the two
new automation-mode invocations (`reviewer`, `qa`) are wired structurally
— new jobs vs. new steps in the existing `dev-agent` job — and how the new
`approved`-review trigger path (FR-007) and the raised
`MAX_AUTO_FIX_ROUNDS` cap (FR-008, Resolved Decision 3) fit alongside the
existing `changes_requested` path.

A gap surfaces in `contracts/automation-triggers.md`'s trigger table: it
names a trigger for *re*-reviewing after a fix round
(`pull_request_review`/`changes_requested` → fix → re-review) and for `qa`
(`pull_request_review`/`approved`), but not for the *first* review right
after `developer` opens a brand-new PR from the `issues`/`labeled` path —
`data-model.md`'s state-transition diagram shows this step
("PR opened → reviewer invoked automatically") but the contract table
doesn't name an event for it. Resolving this gap is part of this ADR's
scope, since it directly determines the job graph.

Two relevant facts from `claude-dev-agent.yml`'s own existing rationale
apply here: (1) `developer`'s PR-opening and fix-round pushes are
authenticated as the Claude GitHub App (via omitting `github_token`)
specifically so they *do* trigger downstream events (unlike the default
`GITHUB_TOKEN`) — opening a PR fires `pull_request`/`opened`, and pushing
a new commit to an existing PR branch fires `pull_request`/`synchronize`;
(2) the existing round-cap mechanism (`MAX_AUTO_FIX_ROUNDS`) already stops
`developer` from pushing a fix commit once the cap is reached, rather than
pushing and then separately blocking a later step.

## Decision

- **Three jobs, one workflow file**: `dev-agent` (existing, unchanged
  identity and both its existing trigger paths), plus two new jobs,
  `reviewer-agent` and `qa-agent`, each independently gated by its own
  `if:` condition, granted only its own role's tools/secret/permissions
  (ADR 0005/0006/0007/0008), rather than appending more steps to the
  existing `dev-agent` job. This mirrors `ci.yml`'s own existing pattern
  of separate `build`/`lint`/`test` jobs rather than one monolithic job.
- **`reviewer-agent`'s trigger — closes the "first review" gap above**:
  `on: pull_request: types: [opened, synchronize]`, scoped by `if:
  github.event.sender.login == '<confirmed automation bot login>' &&
  github.event.sender.type == 'Bot'` (the same actor-identification
  approach as ADR 0007, applied to `sender` rather than `review.user`
  since the relevant actor for a `pull_request` event is whoever performed
  the push/open, not the PR's original author field). This single trigger
  definition uniformly covers both:
  - the very first review, right after `developer`'s `issues`/`labeled`
    run opens a new PR (fires `opened`), and
  - every re-review after a fix-round push (fires `synchronize`),
  without needing a `needs:`-chained job dependency inside the same
  workflow run, and without needing to plumb the PR number developer
  chose back out of its own job as a manual step — GitHub supplies both
  natively in the `pull_request` event payload.
- **Round-cap enforcement falls out for free**: once `dev-agent`'s
  existing "Stop and hand back" step decides the cap is reached, it
  already skips pushing a further fix commit — so no `synchronize` event
  fires, and `reviewer-agent` is never separately dispatched past the cap.
  This ADR does not duplicate a round-cap check inside `reviewer-agent`'s
  own trigger condition.
- **`qa-agent`'s trigger** (per FR-007/data-model.md, unchanged from the
  contract): `on: pull_request_review: types: [submitted]`, scoped by
  `if: github.event.review.state == 'approved' &&
  github.event.review.commit_id == github.event.pull_request.head.sha &&
  <actor check from ADR 0007>`. This is necessarily its own independent
  workflow run, not chained via `needs:` to `reviewer-agent`, because the
  approval that triggers it was posted by a *previous*, already-completed
  workflow run — there is no single run in which both "post the APPROVE"
  and "dispatch qa" can be job-graph siblings.
- **`MAX_AUTO_FIX_ROUNDS`**: a one-line `env:` constant change, `3` → `5`
  (Resolved Decision 3) — no change to the existing counting query or
  "Stop and hand back" mechanism, which remain solely inside `dev-agent`.

## Alternatives Considered

- **Append reviewer/qa as more steps inside the existing `dev-agent`
  job**, rather than new jobs — rejected: mixes three roles' very
  different tool grants, secrets, and permissions blocks into one job's
  linear step list, making it harder to audit which steps run under which
  condition and forcing every step's `if:` to account for all three
  roles' trigger logic at once. Separate jobs keep each role's
  gating/tools/secret self-contained.
- **Chain `reviewer-agent` to `dev-agent` via `needs:` within the same run
  for the fix-round path**, instead of relying on the `pull_request`/
  `synchronize` event as a fresh trigger — considered first, then
  rejected once the event-based design was worked out: the event-based
  approach uniformly covers both the first review and every re-review
  with one trigger definition, needs no extra step to discover the PR
  number/branch `developer` chose, and gets round-cap enforcement for
  free (a `needs:`-chained approach would require duplicating the
  round-cap check inside the second job instead).
- **A time/quiescence-based trigger for the first review** (e.g. "no
  activity for N minutes after a PR opens") — rejected per research.md's
  Decision 4 rationale, which already rejected this style of heuristic for
  `qa`'s trigger for the same reasons (slower, less certain than an actual
  event).

## Consequences

- The `pull_request: types: [opened, synchronize]` trigger is new surface
  area this workflow did not previously watch (previously only `issues`
  and `pull_request_review`). It MUST be scoped tightly by the
  `sender.login`/`sender.type` actor check or it would fire `reviewer` on
  every PR in the repository, including ones with nothing to do with this
  automation — this actor check is now load-bearing for two independent
  jobs (`reviewer-agent`'s dispatch and, via ADR 0007, `qa-agent`'s
  dispatch), so the empirical confirmation ADR 0007 already flags as
  required blocks both, not just one.
- Because `reviewer-agent` now also fires on `pull_request`/`synchronize`,
  a human's own manual commit pushed directly to an automation-managed PR
  branch will not trigger an automatic re-review (the `sender` won't match
  the automation actor) — this is intentional and protective, not a gap:
  a human choosing to intervene manually on a specific PR can still invoke
  `reviewer` locally as before; this feature's automatic triggers only
  continue the loop for the automation's own pushes.
- `MAX_AUTO_FIX_ROUNDS`'s raise to 5 has no interaction with this job
  structure beyond the one `env:` value — the counting query and
  "Stop and hand back" step remain exactly where they are today, inside
  `dev-agent`.
- This is new, unexercised trigger machinery in the same category
  `claude-dev-agent.yml`'s own header comment already flags for the
  existing `changes_requested` path ("UNVERIFIED... smoke-test all of
  this with a throwaway PR... before trusting it on real work"). The full
  three-job chain (PR opened → `reviewer-agent` fires → APPROVE posted →
  `qa-agent` fires) should be exercised end-to-end against a throwaway
  issue/PR, per FR-009/SC-001/SC-003, before being enabled for real work —
  this is also the natural point at which ADR 0007's token/actor-identity
  assumptions get their required empirical confirmation.
