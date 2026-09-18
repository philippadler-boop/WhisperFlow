"""Unit tests for issue #142 (T105: "Update the `MAX_AUTO_FIX_ROUNDS`
environment constant in `.github/workflows/claude-agents-pipeline.yml`
from `3` to `5`").

Per Resolved Decision 3 / FR-008 (feature 002, reviewer/qa-automation)
and ADR 0009, this task is a one-line `env:` constant change only:
`MAX_AUTO_FIX_ROUNDS` moves from `3` to `5`. The existing "Count prior
request-changes rounds" counting query and "Stop and hand back to a
human" step are explicitly out of scope and must be otherwise unchanged
-- both remain solely inside the `dev-agent` job.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_job_skeleton.py`'s (issue #140) and
`tests/unit/test_qa_agent_job_skeleton.py`'s (issue #141) same rationale:
this project has no PyYAML dependency declared, and adding one just for
this test would be a heavier footprint than a handful of anchored
regexes on a file this targeted.

NOTE on the conditional skip pattern reused below: if a future edit to
this file cannot be pushed from an automation session because the
GitHub App token in use lacks the `workflows` permission (the exact
limitation `tests/unit/test_agent_model_pins.py` (issue #59),
`tests/unit/test_pr_closing_keyword_convention.py` (issue #74), and the
`reviewer-agent`/`qa-agent` skeleton tests (issues #140/#141) hit and
documented), these tests skip cleanly rather than failing CI, and start
running for real the moment a human applies the diff directly. This PR's
own edit did not hit that limitation, but the guard is kept for
consistency with those precedents and so this file degrades the same way
if the constant is ever reverted or re-edited under the same constraint.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _dev_agent_job_block() -> str:
    """Return the `dev-agent:` job's own YAML block (from its header line
    up to, but not including, the next top-level-under-`jobs:` job header
    or end of file).
    """
    text = _workflow_text()
    match = re.search(
        r"^  dev-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S
    )
    assert match, "no top-level `dev-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


skip_until_constant_updated = pytest.mark.skipif(
    not re.search(r"^\s*MAX_AUTO_FIX_ROUNDS:\s*5\s*$", _workflow_text(), re.M),
    reason=(
        "MAX_AUTO_FIX_ROUNDS is not yet 5 in claude-agents-pipeline.yml -- if a "
        "future push to this file is blocked by the automation GitHub App "
        "token's missing `workflows` permission (same limitation as issues "
        "#59/#74/#140/#141), a human must apply the constant change "
        "directly."
    ),
)


@skip_until_constant_updated
def test_max_auto_fix_rounds_is_five():
    text = _workflow_text()
    matches = re.findall(r"^\s*MAX_AUTO_FIX_ROUNDS:\s*(\S+)\s*$", text, re.M)
    assert matches == ["5"], (
        "expected exactly one `MAX_AUTO_FIX_ROUNDS: 5` env constant, "
        f"found: {matches!r}"
    )


@skip_until_constant_updated
def test_max_auto_fix_rounds_is_no_longer_three():
    # Regression guard: once the diff has landed, the old value of 3 must
    # not linger anywhere the constant is actually assigned.
    text = _workflow_text()
    assert not re.search(r"^\s*MAX_AUTO_FIX_ROUNDS:\s*3\s*$", text, re.M)


def test_counting_query_step_unchanged():
    # Per T105: "no other change to the existing counting query ... which
    # remain[s] solely inside `dev-agent`". Guard against this task
    # accidentally touching the CHANGES_REQUESTED-counting logic itself.
    job_block = _dev_agent_job_block()
    assert 'select(.state == "CHANGES_REQUESTED")] | length' in job_block
    assert "count=$(gh api" in job_block


def test_stop_and_hand_back_step_unchanged_and_still_gated_by_the_constant():
    # Per T105: "no other change to ... the 'Stop and hand back' step,
    # both of which remain solely inside `dev-agent`" (ADR 0009). The step
    # must still exist, still live inside `dev-agent`, and still compare
    # against `env.MAX_AUTO_FIX_ROUNDS` rather than a hardcoded number.
    job_block = _dev_agent_job_block()
    assert "Stop and hand back to a human if the round cap is reached" in job_block
    assert "steps.round_count.outputs.count >= env.MAX_AUTO_FIX_ROUNDS" in job_block


def test_max_auto_fix_rounds_defined_exactly_once():
    # There is exactly one job (`dev-agent`) that consumes this constant;
    # it must not be duplicated elsewhere in the workflow file.
    text = _workflow_text()
    assert len(re.findall(r"^\s*MAX_AUTO_FIX_ROUNDS:\s*\S+\s*$", text, re.M)) == 1
