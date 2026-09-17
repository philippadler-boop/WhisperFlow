# Contract: Automated `reviewer`/`qa` Trigger Wiring and Tool Guarantees

**Feature**: [../spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md)

This is the external-facing contract for `.github/workflows/claude-dev-agent.yml`'s
extension — analogous in role to `specs/001-video-subtitle-generator/contracts/cli.md`
for the CLI feature. It documents what a PR author/reviewer can observe and
rely on from this workflow, independent of its internal implementation.
`architect`'s ADRs record *how* this contract is satisfied; this document
records *what* must hold true regardless of implementation.

## Trigger contract

| Event | Condition | Action | FR |
|---|---|---|---|
| `issues` | `types: [labeled]`, label `== claude-dev` | Dispatch `developer` automation-mode (existing, unchanged) | — |
| `pull_request_review` | `types: [submitted]`, `review.state == 'changes_requested'` | Dispatch `developer` automation-mode fix round (existing, unchanged), **then** dispatch automated `reviewer` against the resulting commit (new) | FR-002, FR-003, FR-004 |
| `pull_request_review` | `types: [submitted]`, `review.state == 'approved'`, `review.commit_id == pull_request.head.sha`, review posted by the automated `reviewer` actor (see data-model.md `AutomationActor`) | Dispatch automated `qa` (new) | FR-005, FR-006, FR-007 |
| Round cap reached | `RoundCounter >= MAX_AUTO_FIX_ROUNDS` (now 5) | Stop automatic dispatch, hand back to a human (existing mechanism, new constant) | FR-008 |

**Guarantee**: no trigger condition in this table, alone or in
combination, causes a PR to merge or a release to publish. Merge/Release
remains a separate, human-only action in every case (FR-011).

## Tool-grant contract (per automation-mode invocation)

| Role | `--allowedTools` MUST equal | MUST NOT include |
|---|---|---|
| `developer` | `Bash,Edit,Write,Read,Grep,Glob` (existing, unchanged) | — |
| `reviewer` (new automation-mode) | `Read,Grep,Glob` | `Write`, `Edit`, `Bash`, `git`, `gh` |
| `qa` (new automation-mode) | Exactly `qa.md`'s documented interactive `tools:` line | Any tool beyond that line |

**Guarantee**: this table MUST be verified, before any real (non-throwaway)
use, by an invocation-based smoke test per FR-002/FR-010 — the agent
actually attempting a disallowed tool call and the workflow/agent
reporting a literal denial (e.g. `permission_denials_count` and/or
`Error: No such tool available`), not a self-report of what tools it
believes it has. A passing smoke test is evidence; a self-description is
not (Constitution Principle V).

## Diff-supply contract (for automated `reviewer`)

Since `reviewer` has no `Bash`/`git`/`gh` in any mode, the workflow itself
— not the `reviewer` agent — is responsible for making a PR's diff and
current file contents available to `reviewer`'s `Read`/`Grep`/`Glob`
tools and/or its prompt text. The concrete mechanism (which step fetches
the diff, whether it's embedded in the prompt vs. relies solely on a
checked-out branch) is an Architect-phase decision (see
`docs/adr/0005-reviewer-diff-supply-mechanism.md` once approved) — this
contract only fixes the *outcome*: after the workflow's setup steps run,
`reviewer` MUST be able to produce a verdict grounded in the PR's actual
current diff and (if needed) surrounding file context, without itself
executing any `git`/`gh`/`Bash` command.

## Review-posting contract (for automated `reviewer`)

`reviewer`'s verdict (approve, or request-changes with specific points)
MUST be posted as an actual GitHub PR review via a `gh pr review`
invocation the *workflow* performs (using `reviewer`'s returned text as
input), not something `reviewer` posts itself. The posted review MUST use
the same `--approve` / `--request-changes --body-file <content>` semantics
a human invoker of `reviewer` uses today, so that this feature's own new
`approved` trigger path (and the existing `changes_requested` path) fire
correctly off a real GitHub review object — not a comment, not a workflow
log line.

## QA report contract (for automated `qa`)

Automated `qa`'s validation report MUST be committed onto the same branch
as the PR under review (Constitution Principle IV/V) — never a second
branch or PR. If the target branch/PR is missing or already merged by the
time automated `qa` runs, the workflow MUST fail visibly (a failed run
and/or a posted PR comment), not silently open a new branch/PR to route
around it (FR-006, FR-013).

## Non-goals of this contract (explicitly out of scope)

- Does not define a new API, CLI flag, or user-facing WhisperFlow product
  surface — this is a repository pipeline-internal contract.
- Does not specify the exact GitHub Actions job/step YAML structure — that
  belongs to `architect`'s ADRs and the eventual `tasks.md` breakdown.
- Does not change `.claude/agents/reviewer.md` or `.claude/agents/qa.md`'s
  own documented `tools:`/responsibilities (FR-012) — this contract
  describes automation-mode *invocation* of those unchanged agent
  definitions, not a redefinition of the roles themselves.
