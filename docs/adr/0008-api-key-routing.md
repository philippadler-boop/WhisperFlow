# 0008: Routing Dedicated API Keys to Their Own Automation-Mode Invocation

> **Status**: Accepted — approved at the Design Gate (Principle II) on
> 2026-09-17. Merging PR #133 was the approval action, per Constitution
> Principle IV ("It merges to `main` via PR once the plan is approved —
> that merge is the approval action").

## Context

Per Resolved Decision 5 / FR-009, two new Anthropic API keys —
`ANTHROPIC_API_KEY_REVIEWER` and `ANTHROPIC_API_KEY_QA` — are already
provisioned as GitHub Actions repo secrets, distinct from the existing
`ANTHROPIC_API_KEY_DEV`, specifically so each role's actual API spend can
be read directly from that key's own usage rather than estimated or
commingled. `data-model.md`'s `SecretBinding` entity makes this a hard
validation rule: each automation-mode `claude-code-action` invocation
"MUST reference only its own role's secret" and `reviewer`'s job step
"MUST NOT fall back to `ANTHROPIC_API_KEY_DEV` (even accidentally, e.g.
via a YAML anchor/default that isn't overridden per-job)."

The existing `developer` invocation already establishes the base pattern:
`anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_DEV }}` as a literal
value on the `with:` block of its `claude-code-action` step. This feature
adds two more such invocations (one for `reviewer`, one for `qa`), each
needing its own key wired to its own step without disturbing that
guarantee.

## Decision

Each of the three automation-mode `claude-code-action` invocations
(`developer`, `reviewer`, `qa`) is its own independent step in its own
job, with a literal, hardcoded `anthropic_api_key: ${{ secrets.<ROLE_KEY>
}}` reference:

- `developer` (existing, unchanged): `secrets.ANTHROPIC_API_KEY_DEV`
- `reviewer` (new, `reviewer-agent` job): `secrets.ANTHROPIC_API_KEY_REVIEWER`
- `qa` (new, `qa-agent` job): `secrets.ANTHROPIC_API_KEY_QA`

No shared variable, no YAML anchor/alias, no computed/dynamic secret-name
lookup, and no `||` fallback expression of any kind is used to select
which secret a given step references. Each step's `anthropic_api_key:`
line is self-contained and independently readable in isolation.

## Alternatives Considered

- **A reusable composite action or YAML anchor, parameterized by
  role/secret name** — rejected: this is exactly the kind of indirection
  `SecretBinding`'s validation rule warns against (an anchor/default not
  correctly overridden per-job could silently fall back to the wrong
  key), for negligible benefit given there are only three invocations
  total in this file. Explicit duplication of a one-line `with:` field
  three times is safer here than the DRY alternative.
- **A single job matrix** (`strategy: matrix: role: [reviewer, qa]`)
  selecting the secret dynamically via a computed expression like
  `secrets[format('ANTHROPIC_API_KEY_{0}', matrix.role)]` — rejected:
  GitHub Actions' `secrets` context does not reliably support this kind of
  dynamic lookup in all contexts, and even where it does, it reintroduces
  the same indirection this rule exists to avoid, in exchange for saving a
  few lines of straightforward, auditable duplication.

## Consequences

- Each role's spend is cleanly separable in Anthropic's own per-key
  usage/billing views, directly satisfying FR-009's "measured, not
  estimated" requirement with no additional cost-instrumentation code in
  this repo.
- A reviewer of this workflow file (human or `reviewer` itself, if this
  file were ever in scope for review) can verify the no-fallback guarantee
  by inspecting each job's `claude-code-action` step in isolation, without
  tracing through a shared anchor or composite-action definition elsewhere
  in the repository.
- Adding a fourth automated role in the future (out of this feature's
  scope) would repeat this same explicit, per-step pattern rather than
  reusing shared plumbing that does not yet exist — an intentional
  trade-off of a small amount of repetition for legibility and auditability
  at the current scale (three roles).
- This ADR does not by itself address *which token authenticates GitHub
  API calls* (as opposed to the underlying model call) for `reviewer`'s
  or `qa`'s job — that is a separate concern, covered by ADR 0007 for
  `reviewer`'s review-posting step and left to `qa`'s existing
  documented push-to-branch behavior (`qa.md`) for its validation-report
  commit.
