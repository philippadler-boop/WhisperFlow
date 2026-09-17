# Phase 1 Data Model: Automate `reviewer` and `qa` via GitHub Actions

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

This feature has no application data model (no database, no new Python
classes) — its "entities" are the GitHub-native objects and workflow
state this feature's automation reads, writes, or reasons about. Each is
documented here with the fields this feature actually depends on
(existing GitHub Actions/API concepts, not new schema), validation rules
this feature imposes, and relevant state transitions, per the template's
own guidance ("Entity name, fields, relationships... adapted to the
project type").

## PRReviewEvent

A GitHub `pull_request_review` webhook payload — the trigger event both
the existing `changes_requested` path and this feature's new `approved`
path key off.

**Fields this feature depends on**:
- `review.state`: `"approved"` | `"changes_requested"` | `"commented"`
  (lowercase, per GitHub's webhook payload convention — already confirmed
  observed lowercase in this repo's own testing of the existing
  `changes_requested` trigger).
- `review.commit_id`: the SHA the review was posted against.
- `review.user.login` / `review.user.type`: identifies who/what posted
  the review — needed to distinguish an automated `reviewer`'s own
  APPROVE from a human's manual approval of an unrelated PR (see
  Validation Rules below).
- `pull_request.head.sha`: the PR's *current* HEAD commit, for comparison
  against `review.commit_id`.
- `pull_request.number`, `pull_request.head.ref`: identify which PR/branch
  `qa` (and, on the existing path, `developer`'s fix-round dispatch)
  should check out.

**Validation rules this feature imposes** (FR-007):
- Automated `qa` MUST NOT be dispatched unless `review.state == "approved"`
  **and** `review.commit_id == pull_request.head.sha` at the time the
  workflow evaluates the trigger. A stale approval (superseded by a later
  push) MUST NOT fire `qa` — this is the concrete mechanism behind
  Resolved Decision 4's "matching current HEAD commit" requirement.
- The workflow MUST be able to establish that the `approved` review came
  from the automated `reviewer` job's own invocation, not an unrelated
  human approval — see `AutomationActor` below for how this is
  distinguished.

**State transitions relevant to this feature**:
```
PR opened (developer's automation-mode run)
  -> reviewer invoked automatically (new: automation-mode)
     -> APPROVE  --------------------------> qa invoked automatically (new)
     -> CHANGES_REQUESTED -> developer fix round (existing path)
                              -> reviewer invoked automatically again
                                 (repeats, bounded by RoundCounter below)
```

## RoundCounter

The existing count of `CHANGES_REQUESTED` reviews on a PR, computed live
by `claude-agents-pipeline.yml`'s existing `gh api` + `jq` query — not a stored
entity, a derived value re-computed on every trigger.

**Fields**: an integer count of `PullRequestReview` objects with
`state == "CHANGES_REQUESTED"` for the PR (GraphQL/REST casing differs
from the webhook payload's lowercase `review.state` — the existing query
already accounts for this; unchanged by this feature).

**Validation rule this feature imposes** (FR-008, Resolved Decision 3):
- The existing cap comparison (`count >= MAX_AUTO_FIX_ROUNDS`) is
  unchanged in *mechanism*; only the constant `MAX_AUTO_FIX_ROUNDS`
  changes, from `3` to `5`.
- Reaching the cap MUST stop further automatic `developer`/`reviewer`
  dispatch and hand back to a human, exactly as today — this feature does
  not change what happens *at* the cap, only the count of rounds allowed
  before it's reached.

## AutomationActor

Not a GitHub API object — a design concept this feature introduces to
answer "was this review/commit posted by our own automation, or by
something else (a human, a different bot, Dependabot, GitHub Copilot)."
Needed because `AutomationActor` identity is how `PRReviewEvent`'s
validation rule ("came from the automated `reviewer` job") is actually
checked, and how `qa`'s automation-mode commit is distinguished from
`developer`'s fix-round commits when reasoning about `RoundCounter`.

**Fields**:
- The GitHub identity a `claude-code-action` invocation authenticates and
  commits/reviews as (this repo's existing `developer` automation already
  establishes this precedent — its commits show `claude[bot]` as
  author/committer, distinct from the `github-actions[bot]` identity
  associated with the runner's own default `GITHUB_TOKEN`; this feature's
  `reviewer`/`qa` invocations are expected to follow the same identity
  pattern per research.md's "no `github_token`" note, but the exact
  actor login for a *review* rather than a *commit* is a Phase-1-adjacent
  fact `architect` should confirm empirically before relying on it, per
  Constitution Principle V — do not assume without an invocation-based
  check).
- Which of the two new dedicated secrets (`ANTHROPIC_API_KEY_REVIEWER`,
  `ANTHROPIC_API_KEY_QA`) authenticated a given automation-mode
  invocation's underlying model call — this is a workflow-YAML-level
  fact (which `env:`/`with:` block a given job step uses), not something
  read back from the GitHub API after the fact.

**Validation rule this feature imposes** (FR-004 implies this
indirectly): the workflow's own `pull_request_review`-on-`approved`
trigger condition MUST be able to distinguish "our automated `reviewer`
approved this" from "a human approved this PR directly" — otherwise a
human's ordinary manual approval of a PR (which this feature does not
intend to prevent) would incorrectly auto-dispatch `qa` as if the
automated loop had produced that approval. The exact mechanism (actor
login check, a marker in the review body, a separate event type) is an
Architect-phase decision informed by whichever `AutomationActor` identity
`reviewer`'s automation-mode invocation actually authenticates as —
tracked as an open implementation question for `architect`'s ADR, not
resolved here.

## SecretBinding

The mapping from subagent role to which GitHub Actions secret
authenticates its automation-mode invocation.

| Role | Secret (existing/new) | Introduced by |
|---|---|---|
| `developer` | `ANTHROPIC_API_KEY_DEV` | M8 (existing) |
| `reviewer` | `ANTHROPIC_API_KEY_REVIEWER` (new) | This feature (FR-009) |
| `qa` | `ANTHROPIC_API_KEY_QA` (new) | This feature (FR-009) |

**Validation rule**: each automation-mode `claude-code-action` invocation
in the extended `claude-agents-pipeline.yml` MUST reference only its own role's
secret — `reviewer`'s job step MUST NOT fall back to
`ANTHROPIC_API_KEY_DEV` (even accidentally, e.g. via a YAML anchor/default
that isn't overridden per-job), since that would silently defeat FR-009's
per-role cost measurement.
