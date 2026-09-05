# Validation Report: Issue #74 — PR-body closing-keyword convention

- **PR**: #76, "Require a literal PR-body closing keyword (#74)"
  (`74-pr-body-closing-keyword-convention` → `main`; CI green; reviewer
  `philippadler-boop` verdict: **Approve** after one round that added a
  missing test assertion, per PR description).
- **Branch validated**: `74-pr-body-closing-keyword-convention` @ commit
  `1187f3b` ("PR #76 review: assert immediately-followed-by-#N nuance is
  documented"), the branch checked out in the working directory at the
  start of this validation.
- **Issue source**: GitHub issue #74, "PRs don't reliably auto-close their
  issue: 3 instances (#1, #5, #8) of missing/broken closing keywords."
- **Validated by**: `qa` (independent re-check; CI status and the
  reviewer's approval were not trusted as evidence — `CLAUDE.md` and
  `.claude/agents/developer.md` were read directly and reasoned about
  against GitHub's publicly documented closing-keyword matcher, the three
  historical PRs/issues named in the issue were inspected live via `gh`
  to confirm they actually stayed open through merge, the test file's
  assertions were read (not just its pass/fail result), the test suite
  was run directly, and two adversarial doc mutations were applied,
  observed to fail the suite, and fully reverted).
- **Validation date**: 2026-09-05

## Requirement

> Issue #74's core ask: `CLAUDE.md` and `.claude/agents/developer.md` must
> clearly document that every PR body needs a literal closing-keyword line
> (e.g. "Closes #N") with the keyword immediately followed by `#N` and no
> other words in between, distinct from the existing title-only
> traceability requirement.

## Evidence

### 1. Direct reading of `CLAUDE.md` and `developer.md`

Read both files in full (not via the test's excerpts). `CLAUDE.md`
("Working conventions" section, lines 92–104) states:

> Every PR **body** must additionally contain a literal, correctly-formed
> GitHub closing-keyword line -- `Closes #N` or `Fixes #N` (or any of
> GitHub's other recognized keywords: `close`, `closed`, `fix`, `fixed`,
> `resolve`, `resolves`, `resolved`), with the keyword immediately
> followed by `#N` and no other words in between. A title-only reference
> is not enough: `traceability.yml` only checks the title... and GitHub
> only auto-closes an issue from keywords it finds in the PR body or a
> commit message, never the title.

`.claude/agents/developer.md` (lines 22–31) states the same thing in the
developer's own responsibilities list, independently worded (not a
copy-paste of the `CLAUDE.md` bullet):

> Separately, the PR **body** must contain a literal, correctly-formed
> GitHub closing-keyword line -- `Closes #N` or `Fixes #N` (any of
> GitHub's recognized keywords works: `close`, `closed`, `fix`, `fixed`,
> `resolve`, `resolves`, `resolved`, immediately followed by `#N`, no
> other words in between). The title reference alone does not close the
> issue on merge...

Checked against the three sub-requirements of the issue:

| Sub-requirement | `CLAUDE.md` | `developer.md` |
|---|---|---|
| (a) Exact recognized keyword set or clear example | Lists `close`, `closed`, `fix`, `fixed`, `resolve`, `resolves`, `resolved` plus `Closes`/`Fixes` as the worked examples — combined, this is exactly GitHub's documented 9-keyword set (`close`/`closes`/`closed`, `fix`/`fixes`/`fixed`, `resolve`/`resolves`/`resolved`), no more, no fewer | Same set, same structure |
| (b) "immediately followed by #N, no other words in between" | Present verbatim | Present verbatim |
| (c) BODY requirement distinct from existing TITLE requirement | Explicit: separate bullet immediately after the pre-existing title bullet, plus "A title-only reference is not enough" and a citation of `traceability.yml` checking only the title | Explicit: "Separately, the PR **body** must..." directly follows the title-reference responsibility, plus "The title reference alone does not close the issue on merge" |

**PASS** — both files genuinely state all three elements, in the authors'
own words rather than boilerplate, and both correctly reflect GitHub's
actual documented keyword set (verified against GitHub's own docs from
training knowledge: `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`,
`resolve`, `resolves`, `resolved` — no extraneous or missing keywords).

### 2. Independent reasoning about the three historical failure phrasings, checked against live issue/PR data

Reasoned from GitHub's publicly documented matcher (a keyword from the
9-word set above, followed by whitespace, then `#N`, with nothing else
between the keyword and the `#`):

- **"closes issue #1"** — the word "issue" sits between the keyword
  `closes` and the `#1`. GitHub's matcher requires the `#N` to
  *immediately* follow the keyword (only whitespace allowed in between);
  a word in between breaks the match. Expected: does **not** close.
- **"Refs #5"** — `Refs` is not in GitHub's recognized keyword set at
  all. Expected: does **not** close.
- **Title-only reference, no body mention** — GitHub's auto-close only
  scans PR body text and commit messages, never the PR title. Expected:
  does **not** close.

All three predictions are "stays open," matching the issue's claim.
Independently confirmed this actually happened, rather than trusting the
issue's narrative:

```
$ gh issue view 1 --json number,state,title -q '.number, .state, .title'
1
CLOSED
T001: Create project structure...

$ gh issue view 5 ...  -> 5, CLOSED, T005: ...
$ gh issue view 8 ...  -> 8, CLOSED, T008: ...
```

All three issues are `CLOSED` today, but the requirement is about whether
they were closed *automatically by the merge*, not whether they are open
right now. Pulled each issue's timeline to check the `closed` event's
actor and associated commit:

```
issue #1: closed event -> actor "philippadler-boop" (human), commit_id: null,
          at 2026-09-04T20:29:33Z (PR #38 merged 2026-09-04T13:04:16Z — ~7h15m earlier)
issue #5: closed event -> actor "philippadler-boop" (human), commit_id: null,
          at 2026-09-05T01:06:03Z (PR #63 merged 2026-09-04T23:22:12Z — ~1h44m earlier)
issue #8: closed event -> actor "philippadler-boop" (human), commit_id: null,
          at 2026-09-05T01:06:04Z (PR #71 merged 2026-09-05T00:56:51Z — ~9m earlier)
```

Every `closed` event has `commit_id: null` and a human actor, not an
automated close tied to the merging commit — i.e. none of the three
issues auto-closed on merge. Issues #5 and #8 were closed one second
apart (`01:06:03` / `01:06:04`), consistent with a single manual sweep
across both, and issue #74 itself was opened one minute later
(`01:07:28`), matching the issue's own narrative that a manual audit
caught all three well after merge.

**PASS** — the reasoning about all three phrasings matches GitHub's
documented matcher behavior, and live GitHub data independently confirms
none of the three issues auto-closed on merge (all three `closed` events
are human, commit-less, and occur well after their PR's merge timestamp).

### 3. Also checked: did PR #76 itself follow its own new convention?

Not required by the task, but a natural sanity check. Pulled PR #76's
raw body via `gh pr view 76 --json body`. The body's prose narrates the
three historical bad examples (including a literal "Fixes issue #74:" as
descriptive text about the bug class, correctly *not* a real closing
line), and separately ends with a standalone line:

```
Closes #74
```

A regex for `\b(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\b\s*#(\d+)`
against the full raw body matched only this one line (`Closes #74`) —
confirming the narrative "Fixes issue #74" text does not itself
accidentally trigger a close (the word "issue" breaks it, exactly as the
convention describes), while the real closing line at the end does.
PR #76 correctly follows its own new convention.

### 4. Test suite run directly, then its assertions read

```
$ python -m pytest tests/unit/test_pr_closing_keyword_convention.py -v
tests/unit/test_pr_closing_keyword_convention.py::test_claude_md_documents_pr_body_closing_keyword_convention PASSED
tests/unit/test_pr_closing_keyword_convention.py::test_developer_agent_documents_pr_body_closing_keyword_convention PASSED
tests/unit/test_pr_closing_keyword_convention.py::test_developer_agent_still_requires_title_reference PASSED
3 passed in 0.02s
```

Read the test file's actual assertions (`tests/unit/test_pr_closing_keyword_convention.py`):

- `test_claude_md_documents_pr_body_closing_keyword_convention` checks:
  a literal `Closes #N`/`closes #n` example is present; the word `body`
  appears; `_mentions_recognized_keyword_set` (≥6 of the 9 real GitHub
  keywords present, not just a generic reminder); `"title-only"`/`"title
  only"` is called out; and `_documents_immediately_followed_nuance`,
  which whitespace-normalizes the text (to survive manual markdown line
  wrapping) and requires both the literal phrases `"immediately followed
  by"` and `"no other words in between"` to appear together.
- `test_developer_agent_documents_pr_body_closing_keyword_convention`
  checks the same set of things against `developer.md`.
- `test_developer_agent_still_requires_title_reference` is a regression
  guard that the pre-existing title requirement (`FR-xxx`/`FR-` and the
  word `title`) wasn't accidentally dropped while adding the body
  requirement.

These assertions genuinely target the issue's three sub-requirements
((a) keyword set, (b) immediately-followed nuance, (c) body-vs-title
distinction) rather than something weaker — in particular,
`_documents_immediately_followed_nuance` requires the *exact* nuance
phrase, not merely the presence of the keyword list, so a doc that listed
the keywords but dropped the adjacency rule (the actual root cause of
the "closes issue #1" failure) would fail this test. Confirmed this by
adversarial mutation below rather than by inspection alone.

**PASS** — tests pass, and their assertions are substantive, not
tautological.

### 5. Adversarial check: deliberately weaken the docs and confirm the suite catches it

Confirmed clean tree first (`git status --porcelain` empty).

**Mutation A** — removed the "immediately followed by `#N` and no other
words in between" clause from `CLAUDE.md`'s convention bullet (collapsed
it to end at "...`resolve`, `resolves`, `resolved`)."):

```
$ python -m pytest tests/unit/test_pr_closing_keyword_convention.py -v
tests/unit/test_pr_closing_keyword_convention.py::test_claude_md_documents_pr_body_closing_keyword_convention FAILED
tests/unit/test_pr_closing_keyword_convention.py::test_developer_agent_documents_pr_body_closing_keyword_convention PASSED
tests/unit/test_pr_closing_keyword_convention.py::test_developer_agent_still_requires_title_reference PASSED
1 failed, 2 passed in 0.07s
```

Failure was exactly on `_documents_immediately_followed_nuance(text)` for
`CLAUDE.md`, as expected — the other two tests (which don't touch
`CLAUDE.md`) were unaffected. Reverted with `git checkout -- CLAUDE.md`;
confirmed `git status --porcelain` and `git diff --stat` both empty
before continuing.

**Mutation B** — changed `developer.md`'s worked example from
`` `Closes #N` or `Fixes #N` `` to `` `Refs #N` `` (a non-closing
keyword, mirroring the issue's second historical failure mode):

```
$ python -m pytest tests/unit/test_pr_closing_keyword_convention.py -v
tests/unit/test_pr_closing_keyword_convention.py::test_claude_md_documents_pr_body_closing_keyword_convention PASSED
tests/unit/test_pr_closing_keyword_convention.py::test_developer_agent_documents_pr_body_closing_keyword_convention FAILED
tests/unit/test_pr_closing_keyword_convention.py::test_developer_agent_still_requires_title_reference PASSED
1 failed, 2 passed in 0.07s
```

Failure was exactly on `developer.md`'s `"Closes #N" in text or "closes
#n" in text.lower()` assertion, as expected. Reverted with
`git checkout -- .claude/agents/developer.md`; confirmed
`git status --porcelain` and `git diff --stat` both empty, then re-ran
the full convention test file to confirm a clean 3/3 pass:

```
$ python -m pytest tests/unit/test_pr_closing_keyword_convention.py -v
3 passed in 0.02s
```

**PASS** — both mutations, each targeting a distinct sub-requirement of
issue #74, caused the expected and only the expected test to fail; both
were fully reverted, and a clean re-pass was confirmed immediately after
each revert.

### 6. Full test suite

```
$ python -m pytest -q
........................................................................ [ 59%]
..................................................                       [100%]
122 passed in 0.56s
```

All 122 tests pass, no failures. Note: PR #76's own description reports
"120 passed, 2 pre-existing failures (`test_conftest_fixtures.py`,
missing `ffmpeg` binary in this sandbox)" for the same command. In this
validation environment `ffmpeg` is present (`C:\ProgramData\chocolatey\
bin\ffmpeg.exe`), so those same two tests pass here instead of failing —
confirmed by running `pytest tests -k conftest -v` directly (6/6 passed,
including the two ffmpeg-dependent ones). This is an environment
difference the PR description itself flags as pre-existing and unrelated
to this change, not a regression introduced by this PR; not counted
against this validation.

**PASS.**

## Pass/Fail

| Sub-requirement | Result |
|---|---|
| `CLAUDE.md` documents the exact closing-keyword set, the immediately-followed-by-#N/no-other-words nuance, and the body-vs-title distinction | **PASS** |
| `.claude/agents/developer.md` documents the same three elements, independently worded | **PASS** |
| Reasoning about "closes issue #1", "Refs #5", and title-only-reference matches GitHub's documented matcher behavior | **PASS** |
| That reasoning matches what actually happened to issues #1, #5, #8 (confirmed live via `gh`: all three closed manually, commit-less, well after their PR's merge — none auto-closed) | **PASS** |
| `tests/unit/test_pr_closing_keyword_convention.py` passes, and its assertions genuinely target the issue's three sub-requirements (not a weaker proxy) | **PASS** (3/3) |
| Adversarial check: weakening either doc causes the corresponding, specific test to fail; reverting restores a clean pass | **PASS** (both mutations caught, both reverts confirmed clean) |
| Full test suite passes | **PASS** (122/122; a documented environment difference in `ffmpeg` availability, not a regression) |

**Overall: PASS.** Issue #74's core ask is genuinely satisfied on branch
`74-pr-body-closing-keyword-convention` at commit `1187f3b`. Both
`CLAUDE.md` and `.claude/agents/developer.md` state, in their own words,
the exact GitHub-recognized keyword set, the immediately-followed/no-
other-words adjacency rule, and the fact that this is a body requirement
distinct from the pre-existing title requirement. Independent reasoning
about GitHub's documented closing-keyword matcher predicts that all three
historical phrasings ("closes issue #1", "Refs #5", title-only) would
fail to close their issue, and live GitHub data confirms all three
issues were in fact closed manually — by a human, with no associated
commit, well after their PR merged — not automatically. The new test
file's assertions were read in full and confirmed to target the real
sub-requirements rather than a weaker proxy, and this was verified
adversarially: two independent doc mutations, each removing one distinct
sub-requirement, each caused exactly the expected test to fail, and both
were fully reverted with a clean re-pass confirmed. CI's green status and
the reviewer's approval were consulted only for context and were not
relied upon as evidence for any claim in this report.

## Scope note

Item 3 of issue #74's proposed fix (updating
`.github/workflows/claude-dev-agent.yml`'s prompt template) is explicitly
out of scope for PR #76 per its own description — the GitHub App token
that workflow uses lacks `workflows` permission, so a human must apply
that diff manually. This validation does not assess that item, since
PR #76 does not claim to implement it. Item 4 (a CI check on PR bodies)
is tracked separately as issue #75 and likewise out of scope here.

## Environment cleanup

Two adversarial mutations were applied directly to `CLAUDE.md` and
`.claude/agents/developer.md` in this session (Section 5) and reverted
immediately after each, via `git checkout -- <file>`, each confirmed via
`git status --porcelain` and `git diff --stat` returning empty before the
next step proceeded. The PR #76 body and the three historical issues'
timelines were read via `gh` (read-only) and a scratch copy of the PR
body was written to the session scratchpad directory outside the repo
(`%TEMP%\...\scratchpad\pr76_body.txt`), never copied into the repo.
Final `git status --porcelain` before writing this report was empty.
This report (`docs/validation/issue-74.md`) is the only file added or
modified by this validation.
