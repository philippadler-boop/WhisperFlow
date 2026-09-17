# 0006: Posting Automated `reviewer`'s Verdict as a Real GitHub PR Review

> **Status**: Proposed — pending human approval at the Design Gate
> (Principle II). Not yet binding until sign-off.

## Context

`reviewer.md` states plainly: "Your report is text you return, not a file
you write. Whoever invoked you is responsible for posting it as the
actual PR review." `reviewer` has no `Write`, `Edit`, `Bash`, `git`, or
`gh` tool in any mode (FR-002/FR-012), so it cannot post anything itself.
FR-004 requires the *workflow* to post `reviewer`'s verdict (approve, or
request-changes with specific points) as a real GitHub PR review — using
the same `--approve` / `--request-changes --body-file <content>` semantics
a human invoker already uses today (per research.md's note) — specifically
so `claude-dev-agent.yml`'s existing `pull_request_review`/
`changes_requested` trigger, and this feature's new `approved` trigger
(ADR 0007, data-model.md `PRReviewEvent`), fire off a genuine review
object rather than a comment or a workflow log line.

This requires converting `reviewer`'s free-text response into a
machine-actionable decision (approve vs. request-changes) plus a body, and
running the corresponding `gh pr review` command from a workflow step —
not from anything `reviewer` itself does.

## Decision

- `reviewer`'s automation-mode prompt (built the same way `developer`'s
  per-trigger prompt is already built — a dedicated `Build prompt` step,
  not a change to `reviewer.md` itself, preserving FR-012) explicitly
  requires the response to begin with a single, fixed, literal
  machine-readable verdict line as the first line of its returned text:
  either exactly `VERDICT: APPROVE` or exactly `VERDICT: REQUEST_CHANGES`,
  followed by the human-readable report (approval rationale, or specific
  actionable points) on subsequent lines, exactly as `reviewer.md`'s
  existing Responsibilities section already asks for.
- A step following the `claude-code-action` invocation captures that
  returned text (the exact field/output `claude-code-action` exposes for
  the agent's final response is not yet confirmed against the action's
  documented outputs — see Consequences), parses the first line, and:
  - if it is exactly `VERDICT: APPROVE`, runs `gh pr review <PR_NUMBER>
    --approve` (with an optional `--body` carrying the approval
    rationale);
  - if it is exactly `VERDICT: REQUEST_CHANGES`, writes the remaining
    report text to a file and runs `gh pr review <PR_NUMBER>
    --request-changes --body-file <file>`;
  - if the first line matches neither literal string, the workflow fails
    visibly (FR-013) rather than guessing at intent from free text.
- The body text is passed via `--body-file`, not `--body`, for the same
  reason issue titles and review bodies elsewhere in this workflow are
  passed via `env:`/`$VAR` rather than spliced into command text —
  avoiding shell-argument-length and quoting/injection risk for
  arbitrarily long, attacker-influenced (in the sense that `reviewer`'s
  own output is model-generated from attacker-influenced diff content —
  see ADR 0005) text.
- *Which* GitHub identity/token this `gh pr review` step authenticates as
  is deliberately left to ADR 0007, not fixed here — that choice affects
  both review-posting and the `approved`-trigger's actor-identification
  problem, so it is decided as one question in ADR 0007 rather than
  independently here.

## Alternatives Considered

- **Free-text/keyword classification of reviewer's natural-language
  response** (e.g. searching for "approve" vs. "request changes" anywhere
  in the text) — rejected as fragile: a review discussing "I would
  normally request changes here but..." or referencing the words
  incidentally could be misclassified. A required literal verdict line as
  the first line of the response is unambiguous to parse while still
  leaving the rest of the response as free-form, human-readable prose.
- **Have `reviewer` write a structured file itself** (e.g. JSON or a
  fixed-format markdown file) instead of returning text — rejected
  outright: `reviewer` has no `Write` tool in any mode, and granting one
  for this purpose would violate FR-002/FR-012.
- **Post via `gh pr comment` instead of `gh pr review`** — rejected:
  FR-004 explicitly requires a real review object so the existing
  `changes_requested` trigger and this feature's new `approved` trigger
  continue to fire correctly. A plain comment has no `state` or
  `commit_id` field and does not fire a `pull_request_review` event at
  all, so it cannot satisfy `data-model.md`'s `PRReviewEvent` contract.

## Consequences

- `reviewer.md` itself is unchanged (FR-012); the verdict-line requirement
  lives entirely in the automation-mode prompt text the workflow builds,
  the same place `developer`'s trigger-specific instructions already
  live — not in the interactive-mode agent definition.
- The exact mechanism for extracting `claude-code-action`'s final agent
  response as a usable step output/value is **not yet confirmed** against
  the action's actual documented outputs (unlike `--agent`/`--allowedTools`
  /`--model`, which this repo has already smoke-tested by invocation).
  This MUST be confirmed by an invocation-based smoke test against a
  throwaway PR — observing the literal captured text and literal `gh pr
  review` result, not a self-report of what the action is believed to
  expose — before this mechanism is trusted for real work, per
  Constitution Principle V and CLAUDE.md's "test by invocation, not
  self-report" lesson.
- `gh pr review` always posts against the PR's *current* HEAD at the
  moment the command runs, not a SHA the caller specifies. If the PR's
  head moved between the diff-fetch step (ADR 0005) and this posting step
  (e.g. a human pushed a manual commit in between), the posted review
  could end up associated with a newer commit than `reviewer` actually
  saw. Mitigation: re-check `pull_request.head.sha` immediately before
  posting and abort (failing visibly per FR-013) if it no longer matches
  the SHA the diff was fetched against, rather than posting a review that
  silently appears to cover a commit it never actually reviewed.
- A malformed or missing verdict line is treated as a hard failure
  (FR-013), not a default-to-request-changes or default-to-approve
  fallback — a wrong default in either direction would be worse than
  visibly stopping and requiring a human to look.
