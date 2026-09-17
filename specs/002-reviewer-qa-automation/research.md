# Phase 0 Research: Automate `reviewer` and `qa` via GitHub Actions

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

All five items originally marked `[NEEDS CLARIFICATION]` in spec.md were
resolved directly by the project owner during the Requirements Gate
conversation (see spec.md's "Resolved Decisions" section) rather than by
dispatching research agents — they were judgment calls about acceptable
risk/tradeoffs for *this* project, not facts to look up. They are
restated here in Spec Kit's own Decision/Rationale/Alternatives format so
this document is self-contained for whoever reads Phase 0 without also
opening spec.md, and so `architect` has one place to pull technical
grounding from.

## 1. Safety-property replacement

- **Decision**: No new human-approval gate is introduced. The existing
  Merge/Release gate (Constitution Principle II) remains the sole human
  checkpoint for this lifecycle.
- **Rationale**: The project owner explicitly chose full automation —
  `developer → reviewer → qa` runs to completion (an APPROVE verdict and
  green CI, or the round cap) with no human action beyond the final merge
  decision. This is a conscious, recorded tradeoff, not a silent removal
  of `claude-agents-pipeline.yml`'s documented "not a fully closed loop" safety
  property — the safety property is deliberately being closed, with the
  owner's explicit sign-off.
- **Alternatives considered**: (a) an additional "approved for
  automation" gate per PR/repo — rejected as unneeded ceremony once the
  owner decided full automation was acceptable; (b) partial automation
  (automate only `qa`, keep `reviewer` manual) — rejected in favor of
  closing the whole loop, since the review-driven fix cycle is exactly
  what still stalls today.

## 2. `qa` Bash containment in CI

- **Decision**: Automated `qa` runs under the same GitHub Actions runner
  isolation `ci.yml`'s `test` job already relies on. No new,
  automation-mode-specific tool allowlist or sandbox is introduced.
- **Rationale**: `qa`'s Bash use in automation (installing dependencies,
  running real transcriptions, sometimes downloading models) is
  equivalent in kind to what `ci.yml`'s `test` job already does
  unattended on every PR. Treating it identically avoids inventing a
  second containment model to maintain.
- **Alternatives considered**: A narrower automation-mode-specific
  allowlist (e.g. blocking network-adjacent commands beyond what
  transcription itself needs) — rejected as unnecessary extra
  engineering given `ci.yml`'s existing sandboxing already runs
  comparable unattended Bash today without incident.

## 3. Round-cap correctness under automated review

- **Decision**: `MAX_AUTO_FIX_ROUNDS` keeps its existing counting
  mechanism (total `CHANGES_REQUESTED` reviews on the PR, via `gh api`).
  Its default value is raised from **3 to 5**.
- **Rationale**: A `CHANGES_REQUESTED` review is a review regardless of
  whether a human or an automated `reviewer` posted it — the counting
  logic itself needs no change. The cap is raised because full automation
  (Decision 1) means more review→fix cycles may legitimately be needed to
  reach a clean approve without a human ever intervening mid-loop to
  nudge things along, as a human previously could.
- **Alternatives considered**: A wall-clock cap in addition to the review
  count — rejected as unneeded complexity; the review-count cap already
  bounds the loop to a finite, observable number of cycles regardless of
  how fast automation runs them. Lowering the cap — rejected; a *lower*
  cap would make sense if automation were expected to churn on trivial,
  fixable findings, but this repo's own review sessions (T020–T029) show
  genuine, substantive findings are common and often need 1–2 fix rounds
  each — a cap of 3 was already occasionally tight for a human-paced
  loop, and would be tighter still without a human able to intervene.

## 4. `qa` trigger timing

- **Decision**: Automated `qa` is triggered exclusively by automated
  `reviewer` posting an `APPROVE` PR review for the PR's *current* HEAD
  commit — never by a `CHANGES_REQUESTED` review, and never by a
  time-based or commit-quiescence heuristic.
- **Rationale**: This directly resolves the concern already on record as
  bugs.md item #3 / issue #132 (qa validated PR #85 mid-review, before 4
  more fix commits landed). An `APPROVE` verdict is an unambiguous,
  single-event signal that no more fix rounds are expected — no need to
  infer "settled" from the absence of activity over some time window,
  which would be both slower (waiting out the window) and less certain
  (a slow human/agent could still push a commit after the window closes).
- **Alternatives considered**: "Zero new commits since the last review"
  (any verdict, not just APPROVE) — rejected as strictly weaker than
  gating on APPROVE specifically: a CHANGES_REQUESTED review with no
  follow-up commit yet doesn't mean review has settled, it likely means
  the fix is still in flight. A quiet-period timer — rejected per
  Rationale above (slower and not actually more certain).
- **Design implication for Phase 1 / architect**: the workflow's
  `pull_request_review` trigger (already present in `claude-agents-pipeline.yml`
  for the `changes_requested` path) needs a companion condition path for
  `state == 'approved'` that (a) confirms the review's `commit_id` matches
  the PR's current `head.sha` (an approval on a stale commit, superseded
  by a later push, must not fire `qa`), and (b) confirms the review was
  posted by the automated `reviewer` job itself, not by a human's own
  manual approval of an otherwise-unrelated PR — see data-model.md's
  `ReviewEvent` entity and contracts/automation-triggers.md.

## 5. Cost/latency budget

- **Decision**: Automated `reviewer` and `qa` authenticate with two new,
  dedicated Anthropic API keys — `ANTHROPIC_API_KEY_REVIEWER` and
  `ANTHROPIC_API_KEY_QA` — provisioned as GitHub Actions repo secrets
  (confirmed present as of 2026-09-17). At least one full automated cycle
  against a throwaway issue/PR must have its per-key cost and wall-clock
  turnaround recorded before this feature is enabled for real
  (non-throwaway) work.
- **Rationale**: Reusing `ANTHROPIC_API_KEY_DEV` would commingle
  `reviewer`/`qa`'s spend with `developer`'s existing spend, making it
  impossible to answer "what did adding this cost" from billing data
  alone. Dedicated keys make the measurement in FR-009 directly readable
  from each key's own usage — no separate cost-instrumentation code
  needed.
- **Alternatives considered**: Estimating the cost from token-count math
  ahead of time — rejected per FR-009's own "real measurement, not an
  estimate" requirement, and because the tradeoff (SC-003) explicitly
  needs a project-owner accept/reject call on an *actual* number, which
  an estimate cannot responsibly substitute for.

## Additional technical grounding for Phase 1

Beyond the five resolved decisions above, Phase 1 (data-model.md,
contracts/) needs the following facts about the existing automation this
feature extends, gathered from `.github/workflows/claude-agents-pipeline.yml`,
`.github/workflows/ci.yml`, and `.claude/agents/{reviewer,qa}.md`:

- `claude-agents-pipeline.yml` already uses `anthropics/claude-code-action@v1`
  with `--agent <role> --model sonnet --allowedTools "<comma list>"` for
  `developer`'s automation-mode invocation, and deliberately omits
  `github_token` so the Claude GitHub App's own token (not the default
  `GITHUB_TOKEN`) authenticates any `git`/`gh` actions the *action itself*
  performs on Claude's behalf (e.g. opening the PR) — separate from
  whatever API key authenticates the underlying model call. This same
  pattern (agent name, model, allowedTools, no github_token) is the
  starting point for `reviewer`'s and `qa`'s automation-mode invocations;
  only the `--allowedTools` list and the `anthropic_api_key` secret
  reference change per role.
- `reviewer.md`'s `tools:` line is `Read, Grep, Glob` — no `Write`,
  `Edit`, `Bash`, `git`, or `gh`. This is the exact allowlist FR-002
  requires the automation-mode invocation to mirror.
- `qa.md`'s `tools:` line includes `Bash` (needed to actually run the
  software) alongside `Read`/`Grep`/`Glob`/`Write` (the last restricted
  in practice to `docs/validation/*.md` by convention, not by tool
  permission — `qa.md` documents this as a behavioral rule for the agent
  to follow, not a mechanical restriction the workflow enforces).
- The existing `MAX_AUTO_FIX_ROUNDS` round-cap check (`gh api` +
  `CHANGES_REQUESTED` count) already exists in `claude-agents-pipeline.yml` and
  needs only its cap-value constant changed (Decision 3), not new logic.
- `claude-agents-pipeline.yml`'s existing prompt-injection-safety pattern
  (attacker-controlled `${{ github.event.* }}` text routed through `env:`
  then `$VAR` shell expansion, never spliced directly into `run:` script
  text) applies equally to any new attacker-controlled text this feature
  introduces into a prompt — most notably the PR diff text itself
  (`gh pr diff` output), which is exactly as attacker-controlled as an
  issue title or review body (anyone who can push to the PR branch
  controls it).
- `gh pr review <PR> --approve` / `--request-changes --body-file <file>`
  are the existing commands this session has used all along to post a
  human-invoked `reviewer`'s verdict; the automated equivalent is the
  same commands run by the workflow itself (not by the `reviewer` agent,
  which has no `gh`), using the agent's returned verdict text as input.
