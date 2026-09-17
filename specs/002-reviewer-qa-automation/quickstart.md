# Quickstart: Validating Automated `reviewer`/`qa`

This is a runnable validation guide, not implementation documentation —
for whoever validates this feature once built (`qa`'s Evidence-Based
Validation responsibility, Constitution Principle V) to confirm each
success criterion against real workflow runs, not self-reports. Trigger
details are defined in [contracts/automation-triggers.md](contracts/automation-triggers.md);
state/event shapes are in [data-model.md](data-model.md).

## Prerequisites

- `ANTHROPIC_API_KEY_REVIEWER` and `ANTHROPIC_API_KEY_QA` exist as repo
  secrets (confirmed present 2026-09-17; re-verify with
  `gh secret list --repo <owner>/<repo>` before relying on this).
- The extended `claude-dev-agent.yml` (this feature's implementation) is
  merged to `main` and active.
- A throwaway issue/PR available for smoke testing before any real work
  is routed through this feature (FR-009 requires this before real use).

## Scenario 1 — Tool-restriction smoke test for automated `reviewer` (FR-002, SC-002)

```bash
# Open a throwaway PR with an obvious, trivial finding for reviewer to catch,
# then let automated reviewer run against it (via the workflow's own trigger,
# not a manual local invocation).
```

**Expected**: The workflow's automation-mode `reviewer` invocation reports
zero unexpected tool grants — confirmed by an invocation-based check (the
agent actually attempting a disallowed tool, e.g. `Write` or `Bash`, and
the result being a literal denial: `permission_denials_count` matching
expectation and/or an explicit `Error: No such tool available`), not by
reading `reviewer`'s own description of what it believes it can do.
**Do not proceed to Scenario 2 or beyond until this passes** — SC-002
explicitly gates further real use on it.

## Scenario 2 — Full automated lifecycle on a throwaway issue (SC-001)

```bash
gh issue edit <throwaway-issue> --add-label claude-dev
```

**Expected**: Without any human running a local `reviewer` or `qa`
session:
1. `developer`'s existing automation opens a PR (unchanged behavior).
2. Automated `reviewer` posts an actual GitHub PR review (`APPROVE` or
   `CHANGES_REQUESTED`) — verify via `gh pr view <PR> --json reviews`,
   not by reading a workflow log.
3. If `CHANGES_REQUESTED`: automated `developer` pushes a fix commit to
   the same branch (existing path), automated `reviewer` re-reviews, and
   this repeats up to `MAX_AUTO_FIX_ROUNDS` (5) times.
4. On the first `APPROVE` verdict matching the PR's current HEAD commit,
   automated `qa` runs and commits a `docs/validation/*.md` report onto
   the *same* PR branch (verify via `git log <branch>` showing the report
   commit, and confirm it's on the existing PR, not a new one — `gh pr
   list --head <branch>` should show exactly one PR).
5. A human is the only one who performs the final merge.

## Scenario 3 — Stale-approval rejection (FR-007, data-model.md `PRReviewEvent`)

```bash
# On a throwaway PR: get an automated APPROVE, then push one more trivial
# commit to the same branch WITHOUT triggering a new review cycle first.
```

**Expected**: Automated `qa` does **not** run off the now-stale approval
(the approval's `commit_id` no longer matches `pull_request.head.sha`).
Confirm by checking that no new `docs/validation/*.md` commit appears on
the branch, and that the workflow run history shows either no dispatch or
an explicit skip, not a silent no-op that could be mistaken for "already
validated."

## Scenario 4 — Round cap hands back to a human (FR-008)

```bash
# On a throwaway PR: post 5 CHANGES_REQUESTED reviews in a row (scripted,
# mirroring how this repo's own pipeline testing has done this before).
```

**Expected**: After the 5th `CHANGES_REQUESTED` review, the workflow
stops dispatching `developer`/`reviewer` automatically and either fails
visibly or posts a PR comment saying so (FR-013) — it does not attempt a
6th round.

## Scenario 5 — No auto-merge under any outcome (FR-011, SC-004)

```bash
# Across Scenarios 2 and 4 above, inspect the PR's merge state throughout.
```

**Expected**: At no point does the PR merge itself — `gh pr view <PR>
--json state,mergedAt` shows `state: OPEN` (or, after a human merges it
manually, `MERGED` with a merge actor that is a human account, never
`claude[bot]`/`github-actions[bot]`) for every automated run observed.

## Scenario 6 — Cost/latency measurement (FR-009, SC-003)

```bash
# After Scenario 2 completes once on a throwaway issue:
```

**Expected**: `ANTHROPIC_API_KEY_REVIEWER` and `ANTHROPIC_API_KEY_QA`'s
own usage (checked via the Anthropic Console, not estimated) shows a
real, attributable cost and the workflow run history shows a real
wall-clock duration for the added `reviewer`/`qa` steps. This number,
together with the run count from Scenario 2, is what the project owner
uses to make an explicit accept/reject call before this feature is
enabled for real (non-throwaway) `claude-dev`-labeled issues by default —
record that decision (accept/reject, and any conditions) in
`docs/validation/` alongside the measurement itself.
