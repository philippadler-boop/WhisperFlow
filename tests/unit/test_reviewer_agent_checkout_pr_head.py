"""Unit tests for issue #144 (T107: "Add a `Checkout PR head` step to
`reviewer-agent`, checking out `github.event.pull_request.head.sha` (not
`main`, not a bare default-branch checkout)").

Per ADR 0005 Decision 1, this task adds a checkout step to the
`reviewer-agent` job -- before its `claude-code-action` step -- that
checks out the PR's own head branch at its current `head.sha`, so
`reviewer`'s Read/Grep/Glob calls resolve against the PR's actual current
file tree rather than `main` or a bare default-branch checkout.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_trigger.py`'s (issue #143) and
`tests/unit/test_reviewer_agent_job_skeleton.py`'s (issue #140) same
rationale: this project has no PyYAML dependency declared, and adding one
just for this test would be a heavier footprint than a handful of anchored
regexes on a file this targeted.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _reviewer_agent_job_block() -> str:
    """Return the `reviewer-agent:` job's own YAML block (from its header
    line up to, but not including, the next top-level-under-`jobs:` job
    header or end of file).
    """
    text = _workflow_text()
    match = re.search(r"^  reviewer-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `reviewer-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


def _dev_agent_job_block() -> str:
    text = _workflow_text()
    match = re.search(r"^  dev-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `dev-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


def _steps_block(job_block: str) -> str:
    match = re.search(r"^    steps:\n(.*)\Z", job_block, re.M | re.S)
    assert match, "no `steps:` block found in job"
    return match.group(1)


def test_reviewer_agent_has_checkout_pr_head_step():
    job_block = _reviewer_agent_job_block()
    assert re.search(r"^      - name: Checkout PR head\s*$", job_block, re.M), (
        "expected a `Checkout PR head` step in reviewer-agent"
    )


def _checkout_pr_head_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Checkout PR head\n(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no `Checkout PR head` step block found in reviewer-agent"
    return match.group(1)


def test_checkout_pr_head_uses_actions_checkout():
    step_block = _checkout_pr_head_step_block()
    assert re.search(r"^\s*uses: actions/checkout@v\d+\s*$", step_block, re.M), (
        "expected `Checkout PR head` to use actions/checkout"
    )


def test_checkout_pr_head_matches_dev_agent_checkout_action_version():
    # Consistency of style with dev-agent's own existing checkout step, per
    # the task's instruction to match whatever version dev-agent already
    # pins.
    dev_block = _dev_agent_job_block()
    dev_checkout_match = re.search(r"uses: (actions/checkout@v\d+)", dev_block)
    assert dev_checkout_match, "no actions/checkout step found in dev-agent for comparison"

    reviewer_checkout_match = re.search(
        r"uses: (actions/checkout@v\d+)", _checkout_pr_head_step_block()
    )
    assert reviewer_checkout_match, "no actions/checkout step found in Checkout PR head"

    assert reviewer_checkout_match.group(1) == dev_checkout_match.group(1)


def test_checkout_pr_head_refs_pull_request_head_sha():
    step_block = _checkout_pr_head_step_block()
    assert (
        "ref: ${{ github.event.pull_request.head.sha }}" in step_block
    ), "Checkout PR head must check out github.event.pull_request.head.sha"


def test_checkout_pr_head_does_not_reference_main_branch():
    step_block = _checkout_pr_head_step_block()
    # Guard against a bare default-branch checkout or an explicit `ref:
    # main` sneaking in instead of the PR's own head SHA (ADR 0005
    # Decision 1 explicitly rules both out).
    assert not re.search(r"ref:\s*['\"]?main['\"]?\s*$", step_block, re.M)


def test_checkout_pr_head_is_before_claude_code_action_step():
    job_block = _reviewer_agent_job_block()
    steps_block = _steps_block(job_block)
    checkout_index = steps_block.find("- name: Checkout PR head")
    claude_index = steps_block.find("- name: Run Claude Code (reviewer agent, unattended)")
    assert checkout_index != -1, "Checkout PR head step not found in reviewer-agent steps"
    assert claude_index != -1, (
        "Run Claude Code (reviewer agent, unattended) step not found in reviewer-agent steps"
    )
    assert checkout_index < claude_index, (
        "Checkout PR head must come before the claude-code-action step"
    )


def test_dev_agent_job_unaffected_by_this_task():
    # T107 is scoped to reviewer-agent only; dev-agent's own checkout step
    # must remain untouched.
    dev_block = _dev_agent_job_block()
    assert re.search(r"^      - name: Checkout repository\s*$", dev_block, re.M)
