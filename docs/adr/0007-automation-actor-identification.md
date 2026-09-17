# 0007: Distinguishing Automated `reviewer`'s APPROVE from a Human's Manual Approval

> **Status**: Proposed — pending human approval at the Design Gate
> (Principle II). Not yet binding until sign-off.

## Context

FR-007 requires automated `qa` to be triggered **exclusively** by
automated `reviewer` posting an `APPROVE` review for the PR's current HEAD
commit — never by a human's own, ordinary manual approval of the same PR
through GitHub's UI, and never by a time-based heuristic. `data-model.md`
flags this explicitly as an open implementation question (`AutomationActor`):
GitHub's `pull_request_review` payload's `review.commit_id ==
pull_request.head.sha` check alone (already required by Resolved Decision
4) tells the workflow the approval is *current*, but not *whose* approval
it is — a human approving the PR for their own reasons must not
accidentally dispatch `qa` as if the automated loop had produced that
approval.

`data-model.md` explicitly declines to assume an answer and asks
`architect` to ground this in evidence rather than assumption
(Constitution Principle V). The one directly relevant fact already on
record in this repo (research.md, `claude-dev-agent.yml`'s own comments)
is: `developer`'s automation-mode commits show `claude[bot]` as
author/committer, *because* `github_token` is deliberately omitted from
its `claude-code-action` invocation — omitting it makes the action
authenticate as the Claude GitHub App instead of the default
`GITHUB_TOKEN`. This matters for a second, independent reason beyond
identity: `claude-dev-agent.yml` records omitting `github_token`
specifically because "GitHub does not trigger downstream workflows (CI,
traceability) on commits pushed with the default `GITHUB_TOKEN`" — a
well-documented GitHub Actions restriction that events performed using the
default `GITHUB_TOKEN` do not create new workflow runs (to prevent
recursive triggering), with `workflow_dispatch`/`repository_dispatch` as
the only exceptions. This restriction is not specific to `push`/`pull_request`
— it applies to API actions performed with that token generally, which
plausibly includes a `gh pr review` call (ADR 0006) submitting a review.
If true, posting `reviewer`'s APPROVE using the default `github.token`
would not only make the review's actor identity ambiguous — it could mean
the resulting `pull_request_review`/`approved` event never fires a new
workflow run at all, structurally breaking FR-007 regardless of how the
actor check is written.

## Decision

1. **Token**: the `gh pr review` step that posts `reviewer`'s verdict
   (ADR 0006) MUST authenticate using a token other than the default
   `${{ github.token }}` — reusing the same non-default-identity mechanism
   already established for `developer` (an identity that is not subject
   to the "`GITHUB_TOKEN`-authored events don't cascade" restriction),
   rather than inventing a different mechanism. Concretely: `reviewer-agent`'s
   job posts the review using the Claude GitHub App's own installation
   identity — the same identity `developer`'s invocation already
   authenticates as when `github_token` is omitted — obtained via
   whichever mechanism `claude-code-action` exposes for reuse by a
   subsequent plain `gh` step in the same job (to be confirmed against the
   action's actual documented outputs; see Consequences). If no such reuse
   path exists, the fallback is a dedicated GitHub App/bot token minted
   via a step like `actions/create-github-app-token`, using credentials
   distinct from the default `GITHUB_TOKEN` and from the two new Anthropic
   API key secrets (which authenticate model calls, not GitHub API calls,
   and are the wrong credential type for this purpose).
2. **Actor check**: once posted by that non-default identity,
   `review.user.login` reads as the App's bot login (e.g. `claude[bot]`,
   mirroring `developer`'s already-observed commit-author identity) and
   `review.user.type == "Bot"`. The `qa-agent` job's trigger condition
   requires **both**: `review.user.login == '<confirmed bot login>'`
   **and** `review.user.type == 'Bot'`, in addition to the existing
   `review.commit_id == pull_request.head.sha` check. A human's manual
   approval always carries their own personal login and `type == "User"`,
   so it structurally cannot satisfy this condition and will not dispatch
   `qa` — the human remains free to approve a PR through GitHub's normal
   UI for their own purposes without side effects.
3. The exact literal bot login string used in the condition is treated as
   a fact to confirm empirically (an invocation-based check against a
   throwaway PR), not assumed from `claude[bot]` by analogy alone — see
   Consequences.

## Alternatives Considered

- **Match on review body content** (require a fixed marker string in the
  body, check the body instead of actor identity) — rejected: a human
  could type the same marker by coincidence or imitation, and this
  conflates "what the review says" with "who/what posted it," when GitHub
  already exposes an authoritative actor-identity field for exactly this
  purpose.
- **Trust `review.user.type == 'Bot'` alone**, without checking a specific
  login — rejected as too broad: this repo could plausibly gain other bot
  actors in the future (a linter bot, a dependency bot posting
  review-like activity); a generic "any bot" check would incorrectly treat
  an unrelated bot's approval as this automation's own signal.
- **Accept the default `github.token` for posting and assume the
  `approved` event still cascades correctly** — rejected without a test:
  this would repeat exactly the self-report-instead-of-invocation-test
  mistake CLAUDE.md's Operational Lessons already warn against, and
  contradicts this repo's own existing, evidence-based rationale for why
  `developer`'s pushes avoid the default token in the first place.

## Consequences

- This ADR's token choice is the single highest-risk unverified assumption
  in this feature's design: whether a `GITHUB_TOKEN`-authenticated `gh pr
  review` call actually fails to trigger a new `pull_request_review`
  workflow run in this specific repo/GitHub configuration MUST be
  confirmed by an actual invocation-based smoke test (post a throwaway
  APPROVE review and observe whether a new workflow run fires) before this
  feature is trusted for real work — per Constitution Principle V and
  CLAUDE.md's "test by invocation, not self-report" lesson. If the test
  shows the default token *does* cascade correctly in this repo (contrary
  to the general documented restriction), this ADR's non-default-token
  requirement should be revisited rather than kept as unnecessary
  complexity.
- The exact plumbing for obtaining a reusable non-default token for a
  plain `gh` step separate from an agent's own `claude-code-action`
  invocation is not yet confirmed. If no reuse path exists and a dedicated
  GitHub App/PAT must be provisioned, that constitutes new Manual Setup
  beyond what spec.md's "Manual Setup Required" section anticipated (which
  covered only the two Anthropic API keys) — this must be raised back to
  the project owner explicitly, not added silently as an implementation
  detail.
- The literal bot login string used in the `qa-agent` trigger condition
  (e.g. `claude[bot]`) must itself be confirmed empirically before being
  hardcoded, per `data-model.md`'s own flagged open question — an
  incorrect guess here would silently make `qa` never dispatch (a visible,
  fail-safe failure mode per FR-013) rather than dispatch incorrectly, but
  should still be caught by the same smoke test rather than discovered on
  real work.
- This same actor-identification mechanism becomes load-bearing for a
  second trigger path beyond the one FR-007 names directly — see ADR 0009,
  which uses the equivalent `sender.login`/`sender.type` check to scope a
  new `pull_request: opened`/`synchronize`-based trigger for dispatching
  `reviewer` itself. Getting this check right in one place and reusing it
  consistently reduces the chance of the two trigger paths disagreeing
  about what counts as "our own automation."
- A human's ordinary manual approval, comment, or request-changes review
  on an automation-managed PR remains fully unaffected by this ADR — it
  simply does not match the actor check, so `qa` is not dispatched, but
  nothing else about normal PR review behavior changes.
