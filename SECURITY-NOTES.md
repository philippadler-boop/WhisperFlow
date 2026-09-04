# Security notes

Sets up the baseline `../ai-dev-pipeline/implementation-plan.md` M6 and
decision 7 call for: accepting broader unattended-agent autonomy (decision
3) means the credential/sandboxing posture has to be tightened now, not
deferred until something goes wrong. This document is the evidence trail
M6 asks for -- what's denied, what's not yet enabled and why, and what
token scope any automation uses.

## Threat model, briefly

Per `../ai-dev-pipeline/assessment.md` Section 12: a documented real-world
attack chain against a Claude-Code-driven GitHub Action ran issue text ->
agent treats it as an instruction -> agent exfiltrates CI secrets ->
attacker pushes malicious code. The baseline below assumes any text in
this repo that didn't come from you directly (an issue body, a PR
description, a code comment in a dependency) could be adversarial, and is
sized for that, not for a purely cooperative environment.

## What's denied (`.claude/settings.json`)

Committed, shared, applies to every Claude Code session -- interactive or
unattended -- working in this repo, on every platform:

```json
"deny": [
  "Read(~/.ssh/**)",
  "Read(~/.aws/**)",
  "Read(~/.gnupg/**)",
  "Read(~/.config/gh/**)",
  "Read(~/.netrc)",
  "Read(~/.docker/config.json)",
  "Read(~/.npmrc)",
  "Read(.env)",
  "Read(**/.env)",
  "Read(**/.env.*)"
]
```

A `Read` deny rule also blocks `Edit`/`Write` on the same path (Claude
Code >= v2.1.228), so this list doesn't need a matching `Edit` entry per
path. None of this is because WhisperFlow itself holds secrets -- it
doesn't, and per FR-004 (no network calls) it never needs API keys or
`.env` files of its own. This exists purely so that a session working in
this repo -- especially an unattended one that also reads untrusted PR/
issue text -- structurally cannot read the credentials sitting elsewhere
on the machine it's running on, whether or not anything ever tries to get
it to.

This deny list is a floor, not the whole ladder. It's enforced by Claude
Code's own permission layer, which does *not* stop an arbitrary script
run via Bash from opening one of these files itself (a Python/Node
process reading `~/.ssh/id_rsa` directly bypasses a `Read()` deny rule --
only OS-level sandboxing, below, closes that gap).

## Sandbox mode: available, not enabled yet

Claude Code has a stricter, OS-enforced Bash sandbox
(`sandbox.enabled: true` in settings, macOS/Linux/WSL2 only -- not native
Windows) that isolates what Bash subprocesses can read/write at the OS
level, closing the gap above, plus `sandbox.credentials.files` /
`sandbox.credentials.envVars` to deny or mask specific credential files
and environment variables from Bash subprocesses specifically.

Deliberately not turned on in the committed config yet: it restricts Bash
writes to the working directory + session temp + explicitly added
directories, which risks friction on ordinary interactive work, and does
nothing at all on native Windows. Per assessment.md Section 12 ("sandboxing
is a ladder, not a switch"), the right point to step up to it is when
running something less trusted than your own interactive session --
in particular, if M8's unattended work is ever run locally (via WSL2)
rather than inside GitHub Actions' own per-run VM isolation (see below).
Revisit then, rather than enabling it pre-emptively today.

**Caveat on this section:** the exact mechanics of Claude Code's
`sandbox.credentials.envVars` masking and of `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`
(the documented fallback for scrubbing env vars from Bash subprocesses on
platforms the sandbox doesn't cover, e.g. native Windows) weren't fully
confirmed against Claude Code's own docs when this was written -- verify
current behavior at https://code.claude.com/docs/en/sandboxing and
https://code.claude.com/docs/en/env-vars before relying on either as a
hard guarantee, rather than trusting this file's summary of them.

## Environment variables

No `.env` file or long-lived secret is checked into this repo, and none is
needed for WhisperFlow itself (local-only tool, no network calls). The
one credential that matters here is whatever GitHub token `gh`/Claude Code
has access to in your interactive shell -- covered below, not by an
in-repo scrub list, since there's nothing repo-specific to scrub yet.

## GitHub token scope

Interactive work (you running `gh` commands yourself, approving each
merge) uses your own personal `gh auth login` session -- that's fine,
since a human is the one deciding what each command does.

**Original plan (M6), superseded by what M8 actually implemented (see
below):** a fine-grained PAT scoped to this repo only --

1. GitHub -> Settings -> Developer settings -> Fine-grained personal
   access tokens -> Generate new token.
2. Repository access: **Only select repositories** -> WhisperFlow. Never
   "All repositories."
3. Permissions: Contents (read/write), Pull requests (read/write), Issues
   (read/write). Nothing else -- no Administration, no organization
   permissions.
4. Store the token value in a password manager or as a GitHub Actions
   secret scoped to this repo (Settings -> Secrets and variables ->
   Actions) -- never in this repo's files, never in `CLAUDE.md`, never
   pasted into a Claude Code session's context.

**What M8 actually uses (2026-09-04, deliberate deviation, logged in
ai-dev-pipeline's decisions.md):** the Claude Code GitHub Action, which
authenticates as the shared **Claude GitHub App** rather than a
repo-scoped fine-grained PAT. Installed via the officially guided
`/install-github-app` flow. This app's permission set is broader than the
plan above -- Actions, Checks, Contents, Discussions, Issues, Pull
requests, Repository hooks, and Workflows, all read-write -- because the
app is shared across every Claude GitHub feature (this action, Code
Review, web auto-fix), not scoped to just this one use case. The
alternative that would have matched the original plan exactly -- a custom
GitHub App requesting only Contents+Issues+PRs -- was considered and
rejected as disproportionate manual setup (registering an app, generating
and storing a private key, extra workflow wiring) for a solo hobby
account where decision 3 already accepts "broader autonomy is
acceptable" as the starting posture.

Separately, the credential authenticating the action itself is a
`CLAUDE_CODE_OAUTH_TOKEN` (generated via `claude setup-token`, stored as a
GitHub Actions secret on this repo), drawing from the existing Claude
subscription's usage allowance rather than a separate API key -- one
billing surface instead of two, not a security-relevant choice on its
own.

## Container boundary for unattended work

M8's unattended agent runs inside GitHub Actions' own per-run VM, which is
already a fresh, isolated environment per decision 7 / assessment.md item
8 -- no separate devcontainer is needed for that path. A devcontainer
would only become necessary if unattended work is ever run locally
instead (e.g. via a long-running local process rather than GitHub
Actions) -- not planned currently; revisit if that changes.

## Third-party Actions

Already covered by M5: every third-party Action referenced in
`.github/workflows/*.yml` is pinned to a commit SHA (not a floating tag),
kept current via Dependabot's `github-actions` ecosystem entry in
`.github/dependabot.yml`.
