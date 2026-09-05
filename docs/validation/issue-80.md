# Validation Report: Issue #80 — Collapse to one PR per task

- **PR**: #81, "Collapse to one PR per task: qa commits its report onto the
  implementation branch (#80)" (`80-qa-collapse-one-pr-per-task` → `main`;
  CI green — `build`/`codeql`/`lint`/`test`/`traceability` all `pass`;
  reviewer `philippadler-boop` verdict: **Approve**, after one round of
  **Request Changes** that fixed a vacuous regression-guard assertion in
  the new test file).
- **Branch validated**: `80-qa-collapse-one-pr-per-task` @ commit
  `380d452` ("Fix vacuous regression guard in
  test_qa_one_pr_per_task_convention.py (#81 review)"), checked out
  directly for this validation and returned to `main` afterward.
- **Issue source**: GitHub issue #80, "Collapse to one PR per task: qa
  should commit its report onto the implementation's own branch."
- **Validated by**: `qa` (independent re-check; CI status and the
  reviewer's Approve/Request-Changes verdicts were not trusted as
  evidence — all three required files were read directly off the PR
  branch, the new test file's assertions were read line-by-line rather
  than trusted from its pass/fail result alone, the full suite and `ruff`
  were run directly, `.github/workflows/claude-dev-agent.yml` was diffed
  directly against `main`, and the constitution's new Sync Impact Report
  entry was compared against a prior entry's own format).
- **Validation date**: 2026-09-05
- **Process note**: this PR modifies `qa`'s own instructions (`qa.md`) to
  say future validation reports should commit onto the implementation's
  branch. Per explicit orchestrator instruction, this validation was
  carried out under the **current, pre-merge** `qa.md` on `main` (which
  still says "write exactly one artifact... under `docs/validation/`"
  with no branch qualifier) — this report is delivered as a standalone
  file for the orchestrating session to commit on its own branch, not
  committed onto PR #81's branch. This is deliberate, not an oversight:
  applying the new convention to the PR that hasn't merged it yet would
  beg the question.

## Requirement

> Issue #80: three files need concrete changes so that qa's validation
> report lands on the *same* PR as the implementation it validates,
> instead of opening a second, follow-up PR:
> 1. `.claude/agents/qa.md` — instruct checking out the implementation's
>    branch, committing the report there, pushing to update the existing
>    PR, and explicit guidance to say so plainly (not silently reroute) if
>    that branch/PR no longer exists or is already merged.
> 2. `CLAUDE.md` — the branch-per-task working-convention bullet states
>    the report lands on the same branch/PR.
> 3. `.specify/memory/constitution.md` — Principle IV and/or V strengthened
>    to state the same, with a correct version bump and Sync Impact Report
>    entry per the file's own convention.

## Evidence

### 1. Direct reading of all three files off the PR branch, plus their diffs against `main`

Fetched `origin` and checked out `80-qa-collapse-one-pr-per-task` directly
(not via the PR's own diff view) and read `.claude/agents/qa.md`,
`CLAUDE.md`, and `.specify/memory/constitution.md` in full. Then pulled
`git diff main...80-qa-collapse-one-pr-per-task -- <file>` for each to see
exactly what changed, independent of the PR's own description.

**`.claude/agents/qa.md`** — the old bare bullet:

```
Write exactly one artifact: a validation report under `docs/validation/`,
one per task/PR, structured as requirement → evidence → pass/fail.
```

is now immediately followed by "Land it on the implementation's own
branch so it updates the existing PR rather than opening a new one," and
a new subsection, "Committing the report — one PR per task, not two,"
spells out the concrete sequence:

```
- Check out the *same branch* the implementation PR you're validating is
  on (not a new branch, and not `main`) ...
- Add the report at `docs/validation/T0xx.md` on that branch, commit it
  there, and `git push` to that branch's remote.
- Pushing updates the existing, already-open PR in place — do not open a
  second PR for the report. ...
- If that branch or its PR no longer exists, or the PR has already been
  merged, stop and say so plainly rather than silently opening a new PR or
  a new branch to route around it. ...
```

The Hard Rules section was also updated in place: "The validation report
is the only file you write, and it belongs on the implementation's own
branch/PR (above) — never a new branch, and never application code,
tests, or any other doc." All four required elements of item 1 are
genuinely present: checkout, commit, push-to-update-existing-PR, and the
missing/merged-branch escape hatch that explicitly forbids silent
rerouting.

**`CLAUDE.md`** — the branch-per-task bullet in "Working conventions" now
ends with: "One branch means one PR per task: `qa`'s validation report is
committed onto that same branch (updating the existing PR), not pushed to
a second branch/PR opened after the fact -- see constitution.md Principle
IV/V and `qa.md`." This is the exact bullet named in the requirement, and
it now states the same-PR rule plainly, with cross-references to both
other changed files.

**`.specify/memory/constitution.md`** — both named principles were
modified. Principle IV, "Branch-per-Task, Protected Main," now opens with
"one PR per that branch — not two" and adds: "`qa`'s validation report
(Principle V) is committed onto that same branch, updating the same PR
the merge decision is made on, not pushed to a second branch or opened as
a follow-up PR after the fact. If the implementation's branch or PR is
missing or already merged by the time `qa` runs, that is a process-order
defect to report, not a reason to open a new branch/PR to route around
it." Principle V, "Evidence-Based Validation," now ends: "'One per
task/PR' means the *same* PR as the implementation: `qa` checks out the
implementation's own branch, commits the report there, and pushes to
update that existing PR (Principle IV) — it does not open a second PR for
the report." Both principles carry the substance, independently worded,
matching item 3's "IV and/or V" framing exactly (it does both).

**PASS** — all three files genuinely contain the required substance, in
each file's own established voice, not copy-pasted boilerplate across
files.

### 2. Instruction-clarity judgment on `qa.md` (the task's explicit ask: read it as a future qa session would, with no other context)

Reading `qa.md` cold, the core sequence is concrete and actionable
without needing to infer anything: check out the implementation's branch
→ add `docs/validation/<name>.md` → commit → `git push` → this updates
the existing PR, don't open a second one → if the branch/PR is gone or
merged, say so and stop. This is the reviewer's own assessment too
("checkout -> add report -> commit -> push -> ... sequence is concrete
and unambiguous"), and independently reading the file confirms it: the
five-step sequence has no missing verb and no step that requires
guessing what to do next.

Two genuine (non-blocking) clarity gaps were found by reading it fresh,
one flagged by the reviewer and one not:

- **Filename convention is incomplete, not just informally stated.**
  `qa.md` says "Add the report at `docs/validation/T0xx.md`" — but the
  repository's actual established convention (confirmed by listing
  `docs/validation/` on `main`: `T001.md` … `T008.md`, plus
  `issue-74.md`) already has a second, equally real naming pattern for
  issue-only work with no task number, which `qa.md` never mentions. A
  future qa session validating an issue-only PR (exactly this one, #80/
  #81) has no textual basis in `qa.md` itself for producing
  `issue-80.md` rather than guessing at some `T0xx`-shaped name — it
  would have to notice the precedent by directory-listing
  `docs/validation/` itself, which `qa.md` doesn't instruct it to do
  either. This is a real ambiguity for a "cold start" qa session, though
  it isn't one of issue #80's stated sub-requirements (which are about
  branch/PR mechanics, not filenames) and isn't newly *introduced* by
  this PR — the pre-PR `qa.md` never specified a filename pattern at
  all, so this PR made the instruction more specific but not completely
  so.
- **Discovering "the implementation's branch" isn't spelled out.**
  "Check out the *same branch* the implementation PR you're validating is
  on ... e.g. `git checkout <the implementation's branch>`" assumes the
  branch name is already known to the reader. It doesn't say, e.g., `gh
  pr view <PR> --json headRefName` as the concrete way to look it up if
  qa is invoked with only a PR number or issue number. In practice this
  is usually supplied by whoever invokes `qa`, but a strictly
  context-free reading of the file has a one-step gap here.

Neither gap affects the actual sub-requirement issue #80 was raised to
fix (the two-PR-per-task drift) — both concern peripheral mechanics
(exact filename, branch lookup) rather than the checkout → commit → push
→ don't-open-a-second-PR chain, which is unambiguous. The reviewer
separately flagged a third, purely cosmetic nit (two "never"s merged
into one Hard Rules clause) that doesn't change meaning; read fresh, that
sentence is inelegant but not actually ambiguous.

**Assessment: substantially unambiguous for the requirement it exists to
fix; two minor, non-blocking clarity gaps identified independently above
for peripheral mechanics the issue didn't require it to address.**

### 3. New test file run directly, then its assertions read

```
$ python -m pytest tests/unit/test_qa_one_pr_per_task_convention.py -v
test_qa_md_no_longer_instructs_writing_exactly_one_artifact_unqualified PASSED
test_qa_md_instructs_checking_out_the_implementation_branch PASSED
test_qa_md_says_pushing_updates_the_existing_pr_not_a_new_one PASSED
test_qa_md_instructs_surfacing_a_missing_or_merged_branch_rather_than_rerouting PASSED
test_qa_md_hard_rule_still_scopes_write_access_to_the_validation_report PASSED
test_claude_md_documents_report_lands_on_same_branch_pr PASSED
test_constitution_principle_iv_states_one_pr_per_branch PASSED
test_constitution_principle_iv_or_v_states_report_commits_onto_same_branch PASSED
test_constitution_version_was_bumped_and_sync_report_added_for_issue_80 PASSED
test_constitution_qa_process_defect_guidance_present PASSED
10 passed in 0.04s
```

Read every assertion in the file (not just the pass/fail summary). The
first test,
`test_qa_md_no_longer_instructs_writing_exactly_one_artifact_unqualified`,
is exactly the assertion the reviewer's Request-Changes round targeted:
its own docstring explains a *prior* version used an `X or Y` disjunction
where `Y` ("own branch"/"same branch" appearing anywhere in the file)
could pass even if the old bare sentence were fully reverted, because
those words could exist unrelated elsewhere in the file. The current
version slices only the text between the old bare sentence and the next
bullet marker and requires the qualifier to appear in that slice
specifically — a genuine positive regression guard, not a vacuous one.
The remaining nine tests check, per file, that the specific required
phrases (checkout, commit, push, "existing PR"/"not a second PR",
"already merged"/"no longer exist", "process", "same branch"/"same PR",
the version bump being strictly `> 1.2.0`, and `#80` being referenced)
are present — substantive, targeted checks rather than a single generic
keyword scan.

**Independent adversarial spot-check**: to confirm
`test_qa_md_no_longer_instructs_writing_exactly_one_artifact_unqualified`
really does what its docstring claims (rather than trusting the
docstring), reverted just the qualifying clause in `qa.md` in a scratch
copy and hand-traced the test logic: `after_sentence` would then not
contain "own branch"/"same branch" before the next bullet, so the
assertion would fail — confirmed by re-reading the slicing logic
(`after_sentence.split(...)`, `next_bullet = after_sentence.find(" - ")`)
directly against the actual current file content rather than running a
mutation in the working tree (a full mutate-and-revert cycle was
judged unnecessary here since the slicing logic is short enough to trace
by hand against the real file text, and this validation prioritized
checking the tree stayed clean given the branch-switching already
underway).

**PASS** — 10/10 pass, and the assertions target real substance, most
notably the exact regression this PR's own review round required fixing.

### 4. Full test suite and `ruff check .`

On the PR branch:

```
$ python -m pytest -q
........................................................................ [ 54%]
............................................................             [100%]
132 passed in 0.50s

$ ruff check .
All checks passed!
```

For comparison, on `main` (pre-PR): `122 passed` — exactly the +10 new
tests in `test_qa_one_pr_per_task_convention.py` account for the
difference, no other test count changed. `ruff check .` is clean on the
PR branch (doc/prompt/markdown-only change plus one new Python test file
that itself passes lint).

**PASS.**

### 5. `.github/workflows/claude-dev-agent.yml` confirmed untouched

```
$ git diff main...80-qa-collapse-one-pr-per-task -- .github/workflows/claude-dev-agent.yml
(empty output)
$ git diff main...80-qa-collapse-one-pr-per-task -- .github/
(empty output)
```

Confirmed empty for both the specific file and the entire `.github/`
directory — this PR touches no CI/automation configuration, consistent
with its own scope (a doc/prompt-convention fix, no application or
workflow code).

**PASS.**

### 6. Constitution version bump and Sync Impact Report format, checked against a prior amendment

Read the constitution's Governance section rule directly: "MINOR for a
new principle or materially expanded guidance." This amendment expands
guidance in two *existing* principles (IV, V) without adding a new one —
correctly MINOR, `1.2.0 → 1.3.0`, matching the identical precedent set by
the prior "third same-day amendment" (`1.1.0 → 1.2.0`), which also
expanded Principle IV's existing guidance without adding a principle and
was likewise marked MINOR.

Compared the new Sync Impact Report entry's structure field-by-field
against the fullest prior entry (the `1.0.0` initial-ratification entry,
which — like this one — includes "Templates checked for alignment," a
field some later entries omit):

| Field | Prior entry (1.1.0→1.2.0) | New entry (1.2.0→1.3.0) |
|---|---|---|
| Version change | present | present |
| Rationale (with root-cause narrative) | present | present, cites issue #80 and the specific `git log --all --graph` finding by name |
| Modified principles | present, named | present, named (IV and V, matching the issue's "IV and/or V" framing) |
| Added sections | `none` | `none` |
| Removed sections | `none` | `none` |
| Templates checked for alignment | present | present |
| Deferred TODOs | `none` | `none` |

Every field matches the file's own established shape; no field is
missing or reordered relative to precedent. The `**Version**` /
`**Ratified**` / `**Last Amended**` footer line was updated correctly:
`1.3.0`, `Ratified: 2026-09-03` (unchanged, as in every prior amendment),
`Last Amended: 2026-09-05` (today, correctly bumped from `2026-09-04`).

**PASS** — the version bump is the correct semver category per the
constitution's own rule, and the new Sync Impact Report entry matches the
file's established format field-for-field.

### 7. Scope check: exactly the three intended files, plus one new test file

```
$ git diff main...80-qa-collapse-one-pr-per-task --stat
 .claude/agents/qa.md                             |  26 +++-
 .specify/memory/constitution.md                  |  45 +++++-
 CLAUDE.md                                        |   6 +-
 tests/unit/test_qa_one_pr_per_task_convention.py | 178 +++++++++++++++++++++++
 4 files changed, 246 insertions(+), 9 deletions(-)
```

Exactly the three files item 1–3 of the requirement name, plus the new
test file that validates them — no unrelated files touched, no
application code changed. Matches the issue's own framing of "exactly
three file changes" (the test file is validation infrastructure added to
verify those three, not a fourth requirement-bearing change).

**PASS.**

### 8. PR mechanics, read directly (not trusted from the review)

```
$ gh pr view 81 --json number,title,headRefName,baseRefName,state
{"baseRefName":"main","headRefName":"80-qa-collapse-one-pr-per-task",
 "number":81,"state":"OPEN", ...}
$ gh pr view 81 --json body -q '.body'
Closes #80

Implements the fix from issue #80: ...
```

Confirmed directly (not by trusting the reviewer's "false alarm, already
verified resolved" note on this same point) that PR #81's body contains a
correctly-formed closing keyword, `Closes #80` on its own line, per the
project's own PR-body convention from issue #74.

```
$ gh pr checks 81
build          pass
codeql         pass
lint           pass
test           pass
traceability   pass
```

CI is green (consulted for context only, not relied on as evidence for
any requirement above).

**PASS.**

## Pass/Fail

| Sub-requirement | Result |
|---|---|
| `.claude/agents/qa.md` instructs checkout → commit → push to update the existing PR, plus explicit missing/merged-branch escape-hatch guidance | **PASS** |
| `CLAUDE.md`'s branch-per-task bullet states the report lands on the same branch/PR | **PASS** |
| `.specify/memory/constitution.md` Principle IV and V both strengthened to state the same, with correct MINOR version bump and a Sync Impact Report entry matching the file's own established format | **PASS** |
| `qa.md`'s new instructions are clear enough for a future qa session to follow without ambiguity, on the core checkout/commit/push/no-second-PR sequence | **PASS**, with two minor, non-blocking gaps on peripheral mechanics (exact filename convention for issue-only work; how to discover the branch name from a cold start) noted for awareness, not counted as a failure of issue #80's stated scope |
| `tests/unit/test_qa_one_pr_per_task_convention.py` passes, and its assertions are substantive (in particular, the fixed regression guard genuinely enforces the qualifier is attached to the old bare sentence, not present-anywhere) | **PASS** (10/10) |
| Full test suite passes; `ruff check .` clean | **PASS** (132/132 on PR branch vs. 122/122 on `main`, difference exactly accounted for by the 10 new tests; ruff clean) |
| `.github/workflows/claude-dev-agent.yml` and all of `.github/` genuinely untouched | **PASS** (empty diff both ways) |
| Scope: exactly the three named files changed, plus one new test file, no application code | **PASS** |

**Overall: PASS.** Issue #80's requirement is genuinely satisfied on
branch `80-qa-collapse-one-pr-per-task` at commit `380d452`. All three
named files were read directly off the PR branch and each independently
confirmed to carry the required substance in its own voice; the
constitution's version bump and Sync Impact Report entry were checked
against the file's own established format field-by-field and match; the
new test file's ten assertions were read and confirmed to target real
substance, most notably the exact vacuous-guard defect the review round
required fixing, which was traced by hand against the actual file content
rather than trusted from the test's docstring; the full suite (132/132)
and `ruff check .` were run directly on the PR branch; and
`.github/workflows/claude-dev-agent.yml` (and all of `.github/`) was
confirmed genuinely untouched via direct diff. Reading `qa.md` cold, as
the task specifically asked, found the core checkout → commit → push →
don't-open-a-second-PR sequence unambiguous, with two minor, non-blocking
clarity gaps on peripheral mechanics outside issue #80's stated scope
(documented above for awareness). CI's green status and the reviewer's
Approve verdict were consulted only for context and were not relied upon
as evidence for any claim in this report — where the review made a
factual claim relevant to this validation (the PR body's closing
keyword), it was independently re-verified via `gh` rather than taken on
trust.

## Environment cleanup

One unintended side effect occurred during this validation and was
corrected immediately: a `git checkout main -- .` intended only to list
`docs/validation/` filenames via the working tree was run while still on
branch `80-qa-collapse-one-pr-per-task`, which staged `main`'s older
versions of `qa.md`, `CLAUDE.md`, and `constitution.md` onto that branch's
working tree. This was caught by `git status` immediately afterward (the
next command run), corrected with `git reset --hard HEAD` (restoring the
branch to its actual remote-tracked commit `380d452`), and verified via
`git diff origin/80-qa-collapse-one-pr-per-task --stat` (empty) and a
re-run of the full test suite (132/132, unchanged) before proceeding. No
commit, push, or any other durable action occurred while the branch was
in the accidentally-modified state. Final steps: switched back to `main`
(`git checkout main`); `git status` on `main` shows a clean tree aside
from a pre-existing, unrelated untracked directory (`docs/usr_tasks/`)
that predates this session and was not created or modified by it. This
report (`docs/validation/issue-80.md`) is the only file added by this
validation, written on `main` as a standalone artifact per this session's
explicit instruction to follow the current (pre-PR-#81) version of
`qa.md`'s delivery convention, not the new one this PR itself introduces.
