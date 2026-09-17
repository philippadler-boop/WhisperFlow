# 0005: Diff-Supply Mechanism for Automated `reviewer`

> **Status**: Proposed — pending human approval at the Design Gate
> (Principle II). Not yet binding until sign-off.

## Context

`reviewer.md`'s `tools:` line is `Read, Grep, Glob` only — no `Bash`,
`git`, or `gh`, in any mode (FR-002, FR-012; this feature must not loosen
that allowlist). FR-003 therefore requires the GitHub Actions workflow
itself, not the `reviewer` agent, to obtain a PR's diff and current file
content and make it available to `reviewer`'s prompt/tool context.
`contracts/automation-triggers.md`'s "Diff-supply contract" fixes the
*outcome* (`reviewer` must be able to produce a verdict grounded in the
PR's actual current diff and, if needed, surrounding file context, without
itself executing `git`/`gh`/`Bash`) but explicitly defers the *mechanism*
to this ADR.

`reviewer.md` itself already documents the two options a human invoker
uses today: paste diff text (`git diff main...<branch>` / `gh pr diff
<PR>`) directly into the prompt, or check out the PR branch so
`Read`/`Grep`/`Glob` can inspect real files. Automation mode needs to
choose between (or combine) these without a human doing either step by
hand.

`claude-dev-agent.yml`'s existing "Build prompt for this trigger" step
already establishes the safe pattern for getting attacker-controlled
webhook text into a prompt: pass it through `env:`, reference it as
`"$VAR"` inside a heredoc that is written to `GITHUB_OUTPUT`, and never
splice it via `${{ }}` directly into `run:` script text — because `${{ }}`
substitution happens at the YAML level, before bash parses the script,
so hostile content spliced that way becomes script source, not data. A PR
diff is exactly as attacker-controlled as an issue title or review body
(anyone who can push to the PR branch controls it), so the same discipline
applies here.

## Decision

Combine both mechanisms rather than choosing one exclusively:

1. **Checkout**: a `Checkout repository` step in the `reviewer-agent` job
   checks out the PR's own head branch at its current `head.sha` (not
   `main`, and not a bare `fetch-depth: 1` of the default branch), so
   `reviewer`'s `Read`/`Grep`/`Glob` calls resolve against the PR's actual
   current file tree — needed for the context `reviewer.md` already
   expects beyond the diff hunks themselves (the architecture doc, the
   task spec, related files the diff didn't touch).
2. **Diff text embedded in the prompt**: a dedicated `Fetch PR diff` step
   runs `gh pr diff <PR_NUMBER>` (an API-based call; it does not require
   local git history beyond the checkout already done) and writes the
   output to `GITHUB_OUTPUT` as a multiline value, following the exact
   `env:`-then-`"$VAR"`-inside-heredoc pattern the "Build prompt for this
   trigger" step already uses — with a **randomly generated** heredoc
   delimiter (e.g. a `uuidgen`-style token), not a fixed string, since a
   diff's contents are large and attacker-influenced enough that a fixed
   delimiter risks accidental collision in a way a short issue title does
   not.
3. The `reviewer-agent` job's prompt-building step embeds that diff text
   verbatim into the prompt passed to `reviewer`'s `claude-code-action`
   invocation (via the `prompt:` `with:`-field, i.e. `${{
   steps.build_prompt.outputs.prompt }}` — a YAML-level substitution into
   an action input, not a `run:` shell splice, matching how `developer`'s
   existing prompt already flows), and instructs `reviewer` to use its
   `Read`/`Grep`/`Glob` tools against the checked-out working tree only
   for context beyond the diff, never to re-derive the diff itself (it has
   no tool capable of doing so reliably).

## Alternatives Considered

- **Diff text only, no checkout**: `reviewer` would receive the diff in
  its prompt but have no working tree to `Read`/`Grep`/`Glob` at all.
  Rejected — `reviewer.md` explicitly expects to consult the architecture
  doc and spec alongside the diff, and grants `Read`/`Grep`/`Glob`
  specifically for that; a diff-only prompt would leave those tools
  pointed at nothing, silently defeating the reason they're granted.
- **Checkout only, no diff text embedded**: rely on `reviewer` using
  `Read`/`Grep`/`Glob` to reconstruct "what changed" itself, e.g. by
  checking out both `main` and the PR branch into separate directories and
  comparing files pairwise. Rejected — `reviewer` has no `git diff`
  capability and no tool that performs a structural diff; reconstructing
  changed-line context this way would require reading entire files
  pairwise with no tool support, is far more token- and tool-call-
  expensive than handing over the diff text directly, and is exactly the
  workaround a human invoker already avoids today by pasting diff output
  into the prompt per `reviewer.md`'s own documented practice.
- **A composite/reusable diff-fetch action instead of an inline step** —
  deferred as unnecessary; there is exactly one place this mechanism is
  needed in this workflow, so inlining it keeps the injection-safety
  reasoning (delimiter randomization, `env:`-then-`$VAR`) visible in one
  place rather than hidden in a separate action definition.

## Consequences

- Prompt size scales with diff size. A very large diff could approach
  `claude-code-action`'s prompt-length limits; this ADR does not solve
  that structurally — it relies on the existing branch-per-task convention
  (CLAUDE.md Working Conventions) keeping individual PR diffs small in
  practice, and flags this as a known limitation rather than a solved
  problem.
- The diff text is attacker-controlled to the same degree as issue titles
  and review bodies already are. The `Fetch PR diff` step MUST follow the
  existing `env:`-then-`"$VAR"`-in-heredoc pattern with a **randomized**
  delimiter; it MUST NOT splice `gh pr diff` output into a `run:` script
  body via `${{ }}` under any circumstance, consistent with the
  prompt-injection-safety rationale already documented in
  `claude-dev-agent.yml` and established after PR #79 / issue #75.
- The checkout step must target the PR's `head.sha` (not just its branch
  name), to avoid a race where the branch moves between the triggering
  event and the checkout step actually running — the same stale-commit
  discipline `data-model.md`'s `PRReviewEvent` validation rule requires
  for the `approved` trigger path applies equally here, so `reviewer`
  never reviews a diff that no longer matches the commit the rest of the
  workflow reasons about.
- If the `Fetch PR diff` step fails or returns empty (e.g. the PR was
  closed between event and checkout), the workflow MUST fail visibly per
  FR-013 rather than invoking `reviewer` with an empty or missing diff and
  letting it guess.
- This mechanism is new, unexercised machinery in the same category
  `claude-dev-agent.yml`'s own header comment already flags for other
  parts of this file ("smoke-test... with a throwaway PR... before
  trusting it on real work") — it should be exercised end-to-end against
  a throwaway PR before being relied on for real work, per FR-009/SC-003.
