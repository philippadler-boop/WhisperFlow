# Idea: Move `reviewer` and `qa` into GitHub Actions

**Captured:** 2026-09-06 (raw note in `docs/usr_tasks/improvements.md`, moved here 2026-09-17)

Currently `reviewer` and `qa` are deliberately manually-invoked local
sessions (per the M8 scope decision — see `CLAUDE.md`'s Subagents section
and `claude-dev-agent.yml`'s own header comment): a human runs `reviewer`
against a PR's diff and decides whether to post a request-changes review;
a human runs `qa` after review settles and it commits its own validation
report onto the PR's branch. Only the initial `developer` implementation
pass, and now review-driven fix rounds, run unattended via
`claude-dev-agent.yml`.

The idea: extend automation to also run `reviewer` and `qa` themselves via
GitHub Actions, rather than as manually-invoked local sessions, so the
whole task lifecycle (implement → review → fix → qa → ready-to-merge) runs
without a human driving each step.

This is intentionally just the raw idea, not yet a concept brief or
requirements spec. Known open questions to resolve during Concept/
Requirements (not answered here on purpose):

- What replaces the human-in-the-loop gate this removes? `claude-dev-agent.yml`'s own
  header comment states the current design "does not create a fully
  closed, unsupervised review loop" specifically because `reviewer` is
  still manually invoked — automating it removes that safety property.
  Is a different gate (e.g. still requiring human merge approval, which
  is already a hard rule) sufficient, or does something else need to
  take its place?
- `reviewer` currently has no `Write`/`Edit`/`Bash`/`git`/`gh` tools by
  design ("a reviewer that can fix what it's reviewing isn't an
  independent review" — `CLAUDE.md`). Whoever invokes it locally supplies
  the diff manually. In an Actions context, what supplies the diff, and
  does the tool-restriction guarantee still hold when the invocation
  itself is automated (e.g. can the workflow's own permissions leak
  additional capability into the agent's context)?
- `qa` has `Bash` access and actually runs the software (installs
  dependencies, runs real transcriptions, sometimes downloads models).
  Running this in CI needs it secured similarly to how `ci.yml`'s own
  `test` job is sandboxed today — is that containment sufficient for
  `qa`'s broader Bash use, or does `qa` need a narrower automation-mode
  tool allowlist than its current interactive one?
- Round-cap interaction: `claude-dev-agent.yml` already has a
  `MAX_AUTO_FIX_ROUNDS` safety net for the case where request-changes
  reviews get posted faster than a human is watching. If `reviewer`
  itself becomes automated, does the round cap still bound the loop
  correctly, or does a fully automated review→fix→review cycle need a
  different safety mechanism (e.g. a maximum wall-clock time, or the cap
  needs to also account for automated qa's own commits)?
- Does `qa`'s validation report still get committed onto the same PR
  branch (current one-PR-per-task convention), and if `qa` runs
  automatically after every reviewer approval, does that change how the
  bugs.md item #3 concern (qa running before review has genuinely
  settled) needs to be guarded against — e.g. does the workflow need to
  explicitly wait for a "review cycle produced zero new commits for one
  full round" condition before triggering `qa`?
- Cost/latency: this presumably increases the automated API spend per
  task (two more agent invocations per fix round) and changes turnaround
  time expectations — worth scoping the actual increase before deciding.
