"""Unit tests for issue #80 ("Collapse to one PR per task: qa should
commit its report onto the implementation's own branch").

Root cause per the issue: `git log --all --graph` across Phase 2
(T004-T008) showed every task producing *two* PRs -- the implementation
PR, then a separate PR for qa's validation report on its own branch,
merging 4-36 minutes after the implementation had already merged to
`main`. That means the durable validation evidence this project's
evidence-over-self-report discipline depends on lands after the merge
decision it's supposed to inform, not before.

This is a doc/prompt-convention fix (no application code involved), so
these tests assert the convention is actually spelled out in the three
places the issue calls out -- `.claude/agents/qa.md`, `CLAUDE.md`, and
`.specify/memory/constitution.md` -- not that any runtime behavior
changed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QA_MD = REPO_ROOT / ".claude" / "agents" / "qa.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
CONSTITUTION_MD = REPO_ROOT / ".specify" / "memory" / "constitution.md"


def _normalized(text: str) -> str:
    """Collapse whitespace/newlines so manually-wrapped markdown lines
    don't hide a missing/reworded phrase."""
    return re.sub(r"\s+", " ", text.lower())


def test_qa_md_no_longer_instructs_writing_exactly_one_artifact_unqualified():
    # The old instruction ("Write exactly one artifact") said nothing
    # about *which* branch that artifact belongs on, which is exactly what
    # let the two-PR practice drift in. Guard against a regression back to
    # the bare, branch-agnostic phrasing.
    text = QA_MD.read_text()
    normalized = _normalized(text)
    assert "write exactly one artifact: a validation report" not in normalized or (
        "own branch" in normalized or "same branch" in normalized
    )


def test_qa_md_instructs_checking_out_the_implementation_branch():
    text = QA_MD.read_text()
    normalized = _normalized(text)
    assert "checkout" in normalized.replace(" ", "") or "check out" in normalized
    assert "same branch" in normalized or "implementation's own branch" in normalized
    assert "commit" in normalized
    assert "push" in normalized


def test_qa_md_says_pushing_updates_the_existing_pr_not_a_new_one():
    text = QA_MD.read_text()
    normalized = _normalized(text)
    assert "existing" in normalized and "pr" in normalized
    assert "do not open a second pr" in normalized or ("not open a second pr" in normalized)


def test_qa_md_instructs_surfacing_a_missing_or_merged_branch_rather_than_rerouting():
    text = QA_MD.read_text()
    normalized = _normalized(text)
    # Must call out the "branch/PR no longer exists or is already merged"
    # case, and must say to report it plainly rather than opening a new
    # PR/branch to route around it.
    assert "already merged" in normalized or "already been merged" in normalized
    assert "no longer exist" in normalized
    assert "process" in normalized  # "process order was skipped" / "process defect"
    assert "route around" in normalized or "silently opening a new" in normalized


def test_qa_md_hard_rule_still_scopes_write_access_to_the_validation_report():
    # The one-PR-per-task fix must not loosen qa's existing "only file I
    # write" constraint -- it should still say the report is the only
    # thing qa writes, just now qualified with *where* it lands.
    text = QA_MD.read_text()
    normalized = _normalized(text)
    assert "the only file you write" in normalized
    assert "application code" in normalized


def test_claude_md_documents_report_lands_on_same_branch_pr():
    text = CLAUDE_MD.read_text()
    normalized = _normalized(text)
    assert "one branch" in normalized or "one pr per task" in normalized
    assert "same branch" in normalized or "same pr" in normalized
    assert "qa" in normalized
    # Should explicitly rule out a follow-up/second PR, not just describe
    # the happy path.
    assert "follow-up" in normalized or "second branch" in normalized or ("second pr" in normalized)


def test_constitution_principle_iv_states_one_pr_per_branch():
    text = CONSTITUTION_MD.read_text()
    normalized = _normalized(text)
    # Principle IV heading must exist, and the branch-per-task rule must
    # now explicitly say one PR per branch.
    assert "branch-per-task" in normalized
    assert "one pr per that branch" in normalized or "one pr per branch" in normalized


def test_constitution_principle_iv_or_v_states_report_commits_onto_same_branch():
    text = CONSTITUTION_MD.read_text()
    normalized = _normalized(text)
    # Whichever principle carries it, the constitution must explicitly say
    # the validation report is committed onto the *same* branch/PR as the
    # implementation, not a second one.
    assert "same branch" in normalized or "same pr" in normalized
    assert "qa" in normalized
    assert (
        "second branch" in normalized or "second pr" in normalized or ("follow-up pr" in normalized)
    )


def test_constitution_version_was_bumped_and_sync_report_added_for_issue_80():
    text = CONSTITUTION_MD.read_text()
    # A version bump (and accompanying Sync Impact Report entry) is
    # required by the constitution's own Governance section whenever a
    # principle's guidance changes.
    assert "2026-09-05" in text
    assert "#80" in text or "issue #80" in text.lower()
    match = re.search(r"\*\*Version\*\*:\s*(\d+)\.(\d+)\.(\d+)", text)
    assert match is not None, "constitution.md must state a Version line"
    major, minor, patch = (int(part) for part in match.groups())
    # Must be strictly newer than the pre-#80 version (1.2.0).
    assert (major, minor, patch) > (1, 2, 0)


def test_constitution_qa_process_defect_guidance_present():
    text = CONSTITUTION_MD.read_text()
    normalized = _normalized(text)
    # Mirrors qa.md's "don't silently open a new PR/branch" instruction --
    # the constitution should carry the same expectation, not just the
    # agent file.
    assert "already merged" in normalized
    assert "process" in normalized
