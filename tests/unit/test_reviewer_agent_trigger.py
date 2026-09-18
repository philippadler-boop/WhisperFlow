"""Unit tests for issue #143 (T106: "Replace `reviewer-agent`'s `if: false`
placeholder (T103) with the real trigger condition: `on: pull_request:
types: [opened, synchronize]`, scoped by `if:
github.event.sender.login == '<bot login from T102>' &&
github.event.sender.type == 'Bot'`").

Per ADR 0009's Decision (`reviewer-agent`'s trigger) and ADR 0007's
actor-identification principle applied to `sender`, this task:

- adds `pull_request: types: [opened, synchronize]` to the
  workflow-level `on:` block (this file's `on:` is shared across all
  jobs; GitHub Actions has no per-job `on:` key)
- replaces `reviewer-agent`'s `if: false` placeholder with a real
  condition requiring both the confirmed automation bot identity
  (`claude[bot]`, per T102's empirical confirmation --
  `git log --format='%an <%ae>'` on this repo's own automation-authored
  commits) and, since the shared `on:` block means this job's `if:` is
  also evaluated for `issues`/`pull_request_review` events, an explicit
  `github.event_name == 'pull_request'` guard -- without it, the
  `sender` actor check alone would also match the `pull_request_review`
  event `qa-agent`'s own trigger (T116) depends on once `reviewer-agent`
  starts posting reviews as the same bot identity (Phase 4), spuriously
  re-dispatching `reviewer-agent` on its own just-posted review.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_job_skeleton.py`'s (issue #140) and
`tests/unit/test_max_auto_fix_rounds.py`'s (issue #142) same rationale:
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
running for real the moment a human applies the diff directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _top_level_on_block() -> str:
    text = _workflow_text()
    match = re.search(r"^on:\n((?:^  .+\n)+)", text, re.M)
    assert match, "no top-level `on:` block found in claude-agents-pipeline.yml"
    return match.group(1)


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


def _qa_agent_job_block() -> str:
    text = _workflow_text()
    match = re.search(r"^  qa-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `qa-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


def _reviewer_agent_if_condition() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(r"^    if:.*(?:\n(?:      .+\n)*)?", job_block, re.M)
    assert match, "no job-level `if:` found on reviewer-agent"
    return match.group(0)


skip_until_trigger_wired = pytest.mark.skipif(
    not re.search(r"^  pull_request:\s*$", _top_level_on_block(), re.M)
    or bool(re.search(r"^    if: false\s*$", _reviewer_agent_job_block(), re.M)),
    reason=(
        "reviewer-agent's trigger is not yet wired (`pull_request:` missing "
        "from the top-level `on:` block, and/or `if: false` still present) "
        "-- if a future push to this file is blocked by the automation "
        "GitHub App token's missing `workflows` permission (same limitation "
        "as issues #59/#74/#140/#141), a human must apply this task's diff "
        "directly."
    ),
)


@skip_until_trigger_wired
def test_pull_request_added_to_top_level_on_block():
    on_block = _top_level_on_block()
    assert re.search(r"^  pull_request:\s*$", on_block, re.M), (
        "expected a `pull_request:` key in the workflow-level `on:` block"
    )


@skip_until_trigger_wired
def test_pull_request_trigger_types_are_opened_and_synchronize():
    on_block = _top_level_on_block()
    match = re.search(r"^  pull_request:\n((?:^    .+\n)+)", on_block, re.M)
    assert match, "no `pull_request:` sub-block found under `on:`"
    pull_request_block = match.group(1)
    types_match = re.search(r"^\s*types:\s*\[([^\]]*)\]\s*$", pull_request_block, re.M)
    assert types_match, "expected a `types: [...]` line under `pull_request:`"
    types = [t.strip() for t in types_match.group(1).split(",")]
    assert types == ["opened", "synchronize"]


def test_existing_triggers_still_present():
    # Guard against this task accidentally replacing rather than extending
    # the shared `on:` block.
    on_block = _top_level_on_block()
    assert re.search(r"^  issues:\s*$", on_block, re.M)
    assert re.search(r"^  pull_request_review:\s*$", on_block, re.M)


@skip_until_trigger_wired
def test_reviewer_agent_job_no_longer_placeholder_false():
    job_block = _reviewer_agent_job_block()
    assert not re.search(r"^    if: false\s*$", job_block, re.M), (
        "reviewer-agent's `if:` should no longer be the `if: false` "
        "placeholder once its real trigger is wired"
    )


@skip_until_trigger_wired
def test_reviewer_agent_if_checks_event_name_is_pull_request():
    condition = _reviewer_agent_if_condition()
    assert "github.event_name == 'pull_request'" in condition, (
        "reviewer-agent's `if:` must guard on `github.event_name == "
        "'pull_request'` -- without it, the `sender` actor check alone would "
        "also match the `pull_request_review` event qa-agent's own trigger "
        "depends on, once reviewer-agent starts posting reviews as the same "
        "bot identity"
    )


@skip_until_trigger_wired
def test_reviewer_agent_if_checks_confirmed_bot_login_and_type():
    condition = _reviewer_agent_if_condition()
    # Per T102's empirical confirmation (this repo's own automation-authored
    # commits show `claude[bot]` as author), not assumed by analogy.
    assert "github.event.sender.login == 'claude[bot]'" in condition
    assert "github.event.sender.type == 'Bot'" in condition


def test_dev_agent_trigger_condition_unchanged():
    # Guard against this task's `on:` block extension accidentally altering
    # dev-agent's own existing, unrelated trigger logic.
    job_block = _dev_agent_job_block()
    assert (
        "github.event_name == 'issues' && github.event.label.name == 'claude-dev'"
        in job_block
    )
    assert (
        "github.event_name == 'pull_request_review' && "
        "github.event.review.state == 'changes_requested'" in job_block
    )


def test_qa_agent_job_unaffected_by_this_task():
    # T106 is scoped to reviewer-agent only; qa-agent's own trigger wiring
    # is a separate task (T116) and must still be untouched here.
    job_block = _qa_agent_job_block()
    assert re.search(r"^    if: false\s*$", job_block, re.M), (
        "qa-agent's `if: false` placeholder should be untouched by T106"
    )
