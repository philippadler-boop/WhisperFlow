# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

WhisperFlow — a tool that takes a video and generates subtitles. v1 is
transcription-only (captions in the video's own spoken language);
translation into a chosen target language is deferred as a fast-follow
(see `specs/001-video-subtitle-generator/spec.md`). It's the pilot project
for the AI dev pipeline described in
`../ai-dev-pipeline` (a separate, planning-only repo): the first project run
end-to-end through that pipeline's lifecycle. This repo holds the actual
project artifacts (specs, ADRs, code, `.claude/agents/`); the reasoning
behind why the pipeline is shaped the way it is stays in `../ai-dev-pipeline`
and isn't required reading to work in this repo day to day.

## Subagents

Five roles live in `.claude/agents/`: `analyst`, `architect`, `developer`,
`reviewer`, `qa`. Each has its own restricted tool allowlist — see the
individual files for exact scope and responsibilities. Two constraints are
load-bearing and shouldn't be loosened without a good reason:

- `reviewer` has no `Write`/`Edit` — a reviewer that can fix what it's
  reviewing isn't an independent review.
- No subagent merges its own work. Merge to `main` and publishing a release
  are always a human action.

`reviewer` also has no Bash/git/gh — it cannot fetch a PR diff on its own.
Whoever invokes it must supply the diff (paste `git diff main...<branch>` or
`gh pr diff <PR>` into the prompt) or have the PR branch checked out locally
first. This was undocumented through M7 and had to be worked around live
during a retroactive review; see `reviewer.md` for the current instruction.

## Where things live

- `docs/ideas/` — raw, human-authored idea notes.
- `specs/<feature>/` — GitHub Spec Kit's own layout: `spec.md`
  (requirements), `research.md`/`data-model.md`/`contracts/`/`quickstart.md`
  (`/speckit.plan` output), `tasks.md` (`/speckit.tasks` output). No
  separate hand-authored architecture doc — `plan.md` and its companions
  are the design record.
- `docs/adr/` — one ADR per non-trivial architectural decision surfaced
  during the Plan phase, structured as Context / Decision / Alternatives
  Considered / Consequences. A companion to `plan.md`, not a replacement.
- `docs/validation/` — qa-owned; one validation report per task/PR, mapping
  each requirement to the evidence that closes it.
- Review reports aren't files: the `reviewer` subagent returns its report
  as text, and whoever invoked it posts that as the actual PR review.

## Security baseline

See `SECURITY-NOTES.md` for the full picture: what's denied in
`.claude/settings.json` (credential paths no session in this repo can
read, regardless of platform or whether the session is interactive or
unattended), why Claude Code's stricter Bash sandbox isn't enabled yet,
the GitHub token scope any future unattended automation (M8) must use,
and why GitHub Actions' own per-run VM isolation is accepted as the
container boundary for that unattended work rather than a devcontainer.

## Operational lessons

- **Automation-mode `claude-code-action` runs grant zero tool access by
  default** — unlike an interactive session, a `prompt`-driven workflow run
  gets no shell/file/GitHub tools until `claude_args` passes `--allowedTools`
  (or a `settings` permissions block). Discovered the hard way in M8 via a
  silently-successful smoke test with `permission_denials_count: 20`. Any new
  automation-mode workflow needs this from the start — see
  `.github/workflows/claude-dev-agent.yml` for the working pattern (its
  `--allowedTools` list mirrors the invoked subagent's own `tools:` line
  exactly, so unattended runs get no more access than the subagent has
  interactively).
- **When smoke-testing a subagent's tool boundary, test by invocation, not
  self-report.** "List your tools" can describe injected MCP-server context
  as if it were a real capability; asking the subagent to actually call a
  tool and reporting the literal result (success or `Error: No such tool
  available`) is the only test that can't be fooled that way (M2).

## Working conventions

- Branch-per-task: one feature branch per GitHub Issue, cut from `main`,
  never commit directly to `main` (branch-protected, PR required). Spec
  Kit's planning phases (`/speckit.specify` through `/speckit.analyze`,
  plus `architect`'s ADRs) also use a real feature branch, merged to
  `main` via PR at Design Gate approval -- not `main` directly. See
  constitution.md Principle IV (video-subtitle-generator is a documented
  one-time exception; every feature after it must have a branch). One
  branch means one PR per task: `qa`'s validation report is committed onto
  that same branch (updating the existing PR), not pushed to a second
  branch/PR opened after the fact -- see constitution.md Principle IV/V
  and `qa.md`.
- Every PR references the `FR-`/issue ID it implements. This becomes a
  required CI check later, but treat it as a hard rule from the first PR
  on, not something that starts mattering once the check exists.
- Every PR **body** must additionally contain a literal, correctly-formed
  GitHub closing-keyword line -- `Closes #N` or `Fixes #N` (or any of
  GitHub's other recognized keywords: `close`, `closed`, `fix`, `fixed`,
  `resolve`, `resolves`, `resolved`), with the keyword immediately followed
  by `#N` and no other words in between. A title-only reference is not
  enough: `traceability.yml` only checks the title (see that workflow's own
  comment for why), and GitHub only auto-closes an issue from keywords it
  finds in the PR body or a commit message, never the title. This bug class
  bit three PRs in a row (#1, #5, #8 -- see #74): "closes issue #1" (wrong
  phrasing, word between keyword and `#N`), "Refs #5" (not a recognized
  keyword), and a title-only reference with no body mention at all. All
  three passed every existing gate and merged cleanly, but left their issue
  open. A non-blocking CI check for this is tracked separately (#75).
- Human approval gates at exactly two points: Requirements/Design sign-off,
  and Merge/Release. Everything else proceeds without blocking.
