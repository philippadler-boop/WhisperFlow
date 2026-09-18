---

description: "Task list template for feature implementation"
---

# Tasks: Automate `reviewer` and `qa` via GitHub Actions

**Input**: Design documents from `/specs/002-reviewer-qa-automation/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/automation-triggers.md](contracts/automation-triggers.md), [quickstart.md](quickstart.md), ADRs [0005](../../docs/adr/0005-reviewer-diff-supply-mechanism.md)–[0009](../../docs/adr/0009-workflow-job-structure-and-triggers.md) (Design Gate approved)

**Note on organization**: this feature's `spec.md` was written in the Analyst's collapsed concept-brief/requirements format (not `/speckit.specify`'s product-feature template), so it has no `User Story P1/P2/P3` sections to organize phases around. Phases below are instead organized around the five approved ADRs' natural build/dependency order — each phase is an independently demonstrable increment against `quickstart.md`'s scenarios, playing the same role a user story would. Every task references the FR-xxx it satisfies, per Constitution Principle III; carry the same IDs into the PR that closes each task.

**Single-file caveat**: almost every implementation task here edits the same file, `.github/workflows/claude-agents-pipeline.yml` — unlike a typical multi-file feature, most tasks are NOT parallelizable with each other even when they touch logically distinct concerns, because they conflict on that one file. `[P]` is only used where tasks genuinely touch different files.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which phase/ADR-cluster this task belongs to (US1–US5, mapped below)
- Paths are repo-root-relative

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm prerequisites this feature depends on are actually in place before any workflow edit begins.

- [x] T101 Confirm `ANTHROPIC_API_KEY_REVIEWER` and `ANTHROPIC_API_KEY_QA` exist as repo secrets (`gh secret list`) — already provisioned per spec.md's Manual Setup Required, but re-verify at implementation start since they were created in a prior session (FR-009, FR-014)
- [x] T102 [P] Confirm the automated bot identity `developer`'s existing automation-mode invocation authenticates as, by inspecting a real recent `developer`-authored commit (`git log --format='%an <%ae>'` on a `claude-dev`-labeled PR branch) — this is the empirical fact ADR 0007's actor-check and ADR 0009's `sender` check both depend on; record the confirmed login string in a code comment at the point it's used in T108/T112 rather than assuming `claude[bot]` by analogy alone (ADR 0007 Consequences)

**Checkpoint**: Prerequisites confirmed — workflow editing can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Scaffolding every later phase depends on — the two new jobs must exist with correct tool/secret grants before any trigger logic or step content can be added to them.

**⚠️ CRITICAL**: No later phase's tasks can be verified end-to-end until this phase is complete.

- [x] T103 Add the `reviewer-agent` job skeleton to `.github/workflows/claude-agents-pipeline.yml`: no `github_token` input (mirroring `dev-agent`'s existing omission), `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_REVIEWER }}` per ADR 0008, `--agent reviewer --model sonnet --allowedTools "Read,Grep,Glob"` per FR-002/contracts/automation-triggers.md's tool-grant table — trigger condition left as `if: false` placeholder for now, wired for real in Phase 3 (ADR 0008, ADR 0009)
- [x] T104 Add the `qa-agent` job skeleton to `.github/workflows/claude-agents-pipeline.yml`: no `github_token` input, `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_QA }}` per ADR 0008, `--agent qa --model sonnet --allowedTools "<qa.md's exact tools: line>"` per FR-005/FR-012 (read `.claude/agents/qa.md` to get the exact list — do not paraphrase it) — trigger condition left as `if: false` placeholder for now, wired for real in Phase 5 (ADR 0008, ADR 0009)
- [x] T105 Update the `MAX_AUTO_FIX_ROUNDS` environment constant in `.github/workflows/claude-agents-pipeline.yml` from `3` to `5` (Resolved Decision 3, FR-008) — no other change to the existing counting query or "Stop and hand back" step, both of which remain solely inside `dev-agent` (ADR 0009)

**Checkpoint**: Both new jobs exist in the workflow file with correct, isolated tool/secret grants and no live trigger yet — safe to merge without behavior change, since both are gated `if: false`

---

## Phase 3: Automated `reviewer` dispatch and diff supply (US1 — FR-002, FR-003, FR-010)

**Goal**: `reviewer-agent` actually fires on a real PR event and can see that PR's diff and files, without yet posting anything back.

**Independent Test**: Open a throwaway PR; confirm (via workflow run logs only, no posted review yet) that `reviewer-agent` fires on `pull_request: opened`, checks out the PR's head branch at its current SHA, fetches the diff via `gh pr diff`, and the resulting prompt sent to `claude-code-action` visibly contains that diff text (quickstart.md Scenario 1, partial — tool-restriction check only, not yet the full lifecycle).

### Implementation for US1

- [x] T106 [US1] Replace `reviewer-agent`'s `if: false` placeholder (T103) with the real trigger condition: `on: pull_request: types: [opened, synchronize]`, scoped by `if: github.event.sender.login == '<bot login from T102>' && github.event.sender.type == 'Bot'` in `.github/workflows/claude-agents-pipeline.yml` (ADR 0009, FR-007's actor-identification principle applied to `sender`)
- [x] T107 [US1] Add a `Checkout PR head` step to `reviewer-agent`, checking out `github.event.pull_request.head.sha` (not `main`, not a bare default-branch checkout) in `.github/workflows/claude-agents-pipeline.yml` (ADR 0005 Decision 1)
- [x] T108 [US1] Add a `Fetch PR diff` step to `reviewer-agent`: run `gh pr diff <PR_NUMBER>`, write the output to `GITHUB_OUTPUT` via a randomly generated (not fixed) heredoc delimiter, following the exact `env:`-then-`"$VAR"` pattern the existing "Build prompt for this trigger" step already uses for attacker-controlled text, in `.github/workflows/claude-agents-pipeline.yml` (ADR 0005 Decision 2, Consequences — injection-safety requirement)
- [x] T109 [US1] Extend `reviewer-agent`'s prompt-building step to embed the fetched diff text into `reviewer`'s prompt (via the `prompt:` `with:`-field YAML substitution, never a `run:` shell splice) and instruct `reviewer` to use `Read`/`Grep`/`Glob` against the checked-out tree only for context beyond the diff, never to attempt re-deriving the diff itself, in `.github/workflows/claude-agents-pipeline.yml` (ADR 0005 Decision 3)
- [x] T110 [US1] Make the `Fetch PR diff` step (T108) fail the job visibly (non-zero exit, no fallback) if the diff fetch fails or returns empty, per FR-013 and ADR 0005 Consequences, in `.github/workflows/claude-agents-pipeline.yml`

**Checkpoint**: `reviewer-agent` fires correctly and can see real PR content — safe to smoke-test in isolation before adding verdict-posting

---

## Phase 4: Automated `reviewer` verdict posting (US2 — FR-004, FR-007, FR-011)

**Goal**: `reviewer-agent`'s output becomes a real, correctly-attributed GitHub PR review.

**Independent Test**: On the same throwaway PR from Phase 3, confirm `reviewer-agent` posts an actual `gh pr review` (approve or request-changes, matching `reviewer`'s actual verdict) authenticated as the automation's own bot identity — verify via `gh pr view <PR> --json reviews` showing `user.login`/`user.type` matching T102's confirmed identity, not a human account and not the default `github-actions[bot]` (quickstart.md Scenario 1 continued; Scenario 5's no-auto-merge guarantee also applies from here on).

### Implementation for US2

- [x] T111 [US2] Add the required `VERDICT: APPROVE` / `VERDICT: REQUEST_CHANGES` machine-readable first-line instruction to `reviewer-agent`'s prompt-building step (not to `.claude/agents/reviewer.md` itself, preserving FR-012) in `.github/workflows/claude-agents-pipeline.yml` (ADR 0006 Decision, bullet 1)
- [x] T112 [US2] Add a step obtaining the non-default GitHub identity needed to post the review — reuse whichever mechanism `claude-code-action` exposes for a subsequent plain `gh` step to authenticate as the same Claude GitHub App identity `dev-agent` already uses (confirm this reuse path exists first; if it does not, fall back to `actions/create-github-app-token` with dedicated credentials, and flag this back to the project owner as new Manual Setup beyond spec.md's original scope per ADR 0007 Consequences) in `.github/workflows/claude-agents-pipeline.yml` (ADR 0007 Decision 1)
- [ ] T113 [US2] Add a step that captures `claude-code-action`'s final response text as a step output (confirm the exact output field against the action's actual documented outputs — this is explicitly unconfirmed per ADR 0006 Consequences, do not assume a field name without checking), parses its first line, and dispatches to `gh pr review <PR_NUMBER> --approve` or `--request-changes --body-file <file>` (body written via a temp file, never `--body` directly, per ADR 0006 Decision bullet 3) using the identity from T112, in `.github/workflows/claude-agents-pipeline.yml` (ADR 0006 Decision bullet 2)
- [ ] T114 [US2] Make the verdict-dispatch step (T113) fail the job visibly per FR-013 if the first line matches neither literal verdict string exactly — no default-to-approve or default-to-request-changes fallback in either direction, in `.github/workflows/claude-agents-pipeline.yml` (ADR 0006 Decision bullet 2, Consequences)
- [ ] T115 [US2] Before posting (T113), re-check `github.event.pull_request.head.sha` against the SHA the diff was fetched against in T108 and abort visibly (FR-013) if they no longer match, rather than posting a review that silently appears to cover a commit it never actually reviewed, in `.github/workflows/claude-agents-pipeline.yml` (ADR 0006 Consequences)

**Checkpoint**: `reviewer-agent` produces a real, correctly-attributed review end to end — Phase 3+4 together satisfy SC-002's tool-restriction smoke test prerequisite once run against a throwaway PR

---

## Phase 5: Automated `qa` dispatch on APPROVE (US3 — FR-005, FR-006, FR-007)

**Goal**: An automated APPROVE (and only an automated APPROVE, matching current HEAD) triggers `qa-agent`, which validates and commits its report onto the same PR branch.

**Independent Test**: On the same throwaway PR, once `reviewer-agent` posts APPROVE (Phase 4), confirm `qa-agent` fires exactly once, does not fire on a `CHANGES_REQUESTED` review or a stale-commit APPROVE (quickstart.md Scenario 3), and does not fire on a human's own manual approval of an unrelated PR; confirm its validation report lands as a commit on the *same* PR branch, never a new branch/PR (quickstart.md Scenario 2 continued).

### Implementation for US3

- [ ] T116 [US3] Replace `qa-agent`'s `if: false` placeholder (T104) with the real trigger condition: `on: pull_request_review: types: [submitted]`, `if: github.event.review.state == 'approved' && github.event.review.commit_id == github.event.pull_request.head.sha && github.event.review.user.login == '<bot login from T102/T112>' && github.event.review.user.type == 'Bot'` in `.github/workflows/claude-agents-pipeline.yml` (ADR 0009 Decision, `qa-agent`'s trigger; data-model.md `PRReviewEvent` validation rule)
- [ ] T117 [US3] Add a `Checkout PR branch` step to `qa-agent` (the PR's own branch, needed since `qa` must commit its report there) in `.github/workflows/claude-agents-pipeline.yml` (FR-006, mirrors `qa.md`'s existing documented one-PR-per-task convention)
- [ ] T118 [US3] Wire `qa-agent`'s `claude-code-action` invocation with the automation-mode prompt instructing `qa` to validate per its existing responsibilities and commit a `docs/validation/*.md` report onto the checked-out branch, in `.github/workflows/claude-agents-pipeline.yml` (FR-005, FR-012 — `qa.md` itself unchanged)
- [ ] T119 [US3] Make `qa-agent` fail visibly (FR-013) if the target branch/PR no longer exists or is already merged by the time it runs, rather than silently opening a new branch/PR to route around it, in `.github/workflows/claude-agents-pipeline.yml` (FR-006, Constitution Principle IV/V)

**Checkpoint**: Full `developer → reviewer → qa` lifecycle runs unattended on a throwaway PR — this is quickstart.md Scenario 2's complete happy path

---

## Phase 6: Round-cap and no-auto-merge guarantees under full automation (US4 — FR-008, FR-011)

**Goal**: The loop is still bounded once nothing paces it, and no path in the extended workflow can merge a PR.

**Independent Test**: quickstart.md Scenario 4 (5 `CHANGES_REQUESTED` reviews in a row hand back to a human, no 6th round) and Scenario 5 (PR state never becomes `MERGED` via an automation actor, across every scenario observed).

### Implementation for US4

- [ ] T120 [US4] Confirm (by reading, not by adding new code) that no step added in Phases 2–5 contains a `gh pr merge` call or equivalent under any condition, across `.github/workflows/claude-agents-pipeline.yml` — this is a verification task, not an implementation task; if one is found, remove it (FR-011)
- [ ] T121 [US4] Confirm the existing round-cap "Stop and hand back" step's condition still correctly gates `dev-agent`'s dispatch at the new cap value of 5 (T105) and that reaching it produces a visible failure/comment per FR-013, in `.github/workflows/claude-agents-pipeline.yml`

**Checkpoint**: Safety guarantees hold under the fully automated loop, not just the happy path

---

## Phase 7: Cost/latency measurement and pre-real-use smoke test (US5 — FR-002, FR-009, FR-010)

**Goal**: The invocation-based smoke tests every prior phase's tasks call for are actually run, and a real cost/latency number is recorded, before this feature is enabled for real (non-throwaway) `claude-dev`-labeled issues.

**Independent Test**: quickstart.md Scenarios 1, 2, 3, 6 all pass against one real throwaway issue/PR run end-to-end; a project-owner accept/reject decision on the measured cost/latency is recorded.

### Implementation for US5

- [ ] T122 [US5] Run quickstart.md Scenario 1 (tool-restriction smoke test) against a throwaway PR and record the literal result (`permission_denials_count` and/or explicit tool-denial text) in `docs/validation/002-smoke-test.md` — do not proceed to T123 until this passes (FR-002, SC-002)
- [ ] T123 [US5] Run quickstart.md Scenario 2 (full lifecycle) against a throwaway issue end-to-end and record the observed run sequence, review objects, and validation-report commit in `docs/validation/002-smoke-test.md` (FR-009, SC-001)
- [ ] T124 [P] [US5] Run quickstart.md Scenario 3 (stale-approval rejection) against a throwaway PR and record the result in `docs/validation/002-smoke-test.md` (FR-007 verification)
- [ ] T125 [P] [US5] Record `ANTHROPIC_API_KEY_REVIEWER`/`ANTHROPIC_API_KEY_QA`'s actual per-key usage and the workflow run's actual wall-clock duration from T123's run in `docs/validation/002-smoke-test.md`, per FR-009's "measure, don't estimate" requirement (SC-003)
- [ ] T126 [US5] Present T122–T125's recorded results to the project owner and record their explicit accept/reject decision (and any conditions) in `docs/validation/002-smoke-test.md` before this feature is enabled for real, non-throwaway `claude-dev`-labeled issues by default (SC-003)

**Checkpoint**: All success criteria (SC-001 through SC-005) have recorded evidence — this feature is ready for real use once T126's decision is "accept"

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and header-comment updates reflecting the now-implemented feature — safe to do in parallel with each other since they touch different files.

- [ ] T127 [P] Update `.github/workflows/claude-agents-pipeline.yml`'s own header comment to describe the three-job structure and both new trigger paths, mirroring how it already documents the two `dev-agent` triggers (ADR 0009)
- [ ] T128 [P] Update `CLAUDE.md`'s Subagents section to remove or qualify the "reviewer and qa are deliberately manually-invoked local sessions" statement, since it is no longer true once this feature is enabled (Constitution Principle II/IV context)
- [ ] T129 [P] Update `docs/adr/0005`–`0009`'s Consequences sections with the actual confirmed facts from Phase 7's smoke test (bot login string, `claude-code-action` output field name, whether the default-token cascading concern was confirmed or refuted) — these ADRs currently flag several facts as unconfirmed-pending-smoke-test; close that loop once real data exists

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (T102's confirmed bot identity is referenced by Phase 2's job skeletons' eventual trigger conditions, though the skeletons themselves in T103/T104 can be written before T102 finishes, since their triggers start as `if: false` placeholders). BLOCKS all later phases — both new jobs must exist before any trigger wiring is added to them.
- **US1 (Phase 3)**: Depends on Phase 2 (T103 in particular). No dependency on US2–US5.
- **US2 (Phase 4)**: Depends on US1 (needs `reviewer-agent` actually dispatching and seeing a diff before its verdict can be posted).
- **US3 (Phase 5)**: Depends on US2 (the `approved` trigger it wires up doesn't exist meaningfully until `reviewer-agent` can actually post an APPROVE).
- **US4 (Phase 6)**: Depends on Phase 2 (T105) and can be verified once US1–US3 exist, but T120/T121 are pure verification and can technically run any time after Phase 2.
- **US5 (Phase 7)**: Depends on US1–US4 all being complete — it smoke-tests the whole assembled feature.
- **Polish (Phase 8)**: Depends on Phase 7 (T129 specifically needs Phase 7's confirmed facts).

### Within Each Phase

Tasks within Phases 2–7 are listed in the order they must be applied to the same file (`claude-agents-pipeline.yml`) — treat them as sequential, not parallel, unless individually marked `[P]`.

### Parallel Opportunities

Genuinely limited by this feature's single-file nature:
- T101 and T102 (Phase 1) can run in parallel — different concerns, no shared file edit.
- T124 and T125 (Phase 7) can run in parallel — independent verification/recording tasks against the same completed run, not sequential edits.
- All of Phase 8 (T127–T129) can run in parallel — three different files.

---

## Implementation Strategy

### Smallest safely-mergeable increment

Phase 1 + Phase 2 alone (T101–T105) can merge with zero behavior change (`if: false` placeholders) and are a safe, independently reviewable first PR — establishing the new jobs' isolated tool/secret grants (the FR-002/FR-005/FR-008/FR-012 guarantees) before any trigger logic exists to exercise them.

### Incremental delivery

1. Phase 1 + 2 → jobs exist, gated off. Safe to merge.
2. Phase 3 → `reviewer-agent` fires and sees real diffs, but posts nothing yet. Verifiable via workflow logs alone before any GitHub-visible side effect exists.
3. Phase 4 → `reviewer-agent` posts real reviews. This is the point at which SC-002's tool-restriction smoke test becomes meaningful to run.
4. Phase 5 → `qa-agent` completes the loop. This is quickstart.md Scenario 2's full happy path.
5. Phase 6 → safety-guarantee verification, can run any time after Phase 2 but is most meaningful once Phases 3–5 give it something real to check.
6. Phase 7 → the mandatory pre-real-use gate (FR-009/FR-014's own requirement) — nothing in this feature is enabled for real work until this phase's accept/reject decision is recorded.
7. Phase 8 → documentation catch-up, done last since it depends on Phase 7's confirmed facts.

### Suggested "MVP" scope

Phases 1–5 constitute the minimum for spec.md's SC-001 (full lifecycle with no human running local reviewer/qa) to be demonstrable at all; Phase 7 is not optional polish — FR-009/FR-014 make it a hard gate before real (non-throwaway) use, not an MVP-vs-later distinction.
