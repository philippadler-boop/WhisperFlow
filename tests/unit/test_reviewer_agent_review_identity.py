"""Unit tests for issue #149 (T112: "Add a step obtaining the non-default
GitHub identity needed to post the review -- reuse whichever mechanism
`claude-code-action` exposes for a subsequent plain `gh` step to
authenticate as the same Claude GitHub App identity `dev-agent` already
uses (confirm this reuse path exists first; if it does not, fall back to
`actions/create-github-app-token` with dedicated credentials, and flag
this back to the project owner as new Manual Setup beyond spec.md's
original scope per ADR 0007 Consequences)").

Per ADR 0007 Decision 1, the `gh pr review` step that will post
`reviewer`'s verdict (T113, a separate task) MUST authenticate using a
token other than the default `${{ github.token }}`. This task confirms
that `claude-code-action` itself exposes a reusable `github_token` output
(the Claude GitHub App token it authenticated with internally, since the
"Run Claude Code (reviewer agent, unattended)" step already omits its own
`github_token` input) and adds a step that captures and validates that
output for a later plain `gh` step to consume -- it does NOT itself post
anything or add `gh pr review` dispatch logic (that's T113).

This task does not need the `actions/create-github-app-token` fallback or
its associated new-Manual-Setup flag: the reuse path exists.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_verdict_instruction.py`'s (issue #148)
same rationale: this project has no PyYAML dependency declared.

NOTE on why the identity-step-specific tests below are conditionally
skipped: the actual `.github/workflows/claude-agents-pipeline.yml` edit
this task calls for could not be pushed from this session -- the
automation GitHub App token this environment authenticates as lacks the
`workflows` permission needed to push changes under
`.github/workflows/` (GitHub rejects the push outright: "refusing to
allow a GitHub App to create or update workflow ... without `workflows`
permission"). This is the exact same limitation
`tests/unit/test_agent_model_pins.py` (issue #59),
`tests/unit/test_pr_closing_keyword_convention.py` (issue #74, see PR
#76), `tests/unit/test_reviewer_agent_job_skeleton.py` (issue #140, see
PR #168), and `tests/unit/test_qa_agent_job_skeleton.py` (issue #141,
see PR #176) already hit and documented. A human with real push access
must apply the diff given in this PR's description directly to
`claude-agents-pipeline.yml`; these tests are written against the target
state that diff produces and will start running for real the moment it
lands (no test-file edit needed) -- they skip cleanly rather than
failing CI in the meantime.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _identity_step_present() -> bool:
    return bool(
        re.search(
            r"^      - name: Obtain non-default GitHub identity for posting the review\n",
            _workflow_text(),
            re.M,
        )
    )


skip_until_workflow_diff_applied = pytest.mark.skipif(
    not _identity_step_present(),
    reason=(
        "identity-obtaining step not yet present in claude-agents-pipeline.yml "
        "-- the automation GitHub App token used to push this PR lacks "
        "`workflows` permission (same limitation as issues #59/#74/#140/"
        "#141); see this PR's description for the exact diff a human must "
        "apply directly."
    ),
)


def _reviewer_agent_job_block() -> str:
    """Return the `reviewer-agent:` job's own YAML block (from its header
    line up to, but not including, the next top-level-under-`jobs:` job
    header or end of file).
    """
    text = _workflow_text()
    match = re.search(r"^  reviewer-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `reviewer-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


def _claude_code_action_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Run Claude Code \(reviewer agent, unattended\)\n"
        r"(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no `Run Claude Code (reviewer agent, unattended)` step block found"
    return match.group(1)


def _identity_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Obtain non-default GitHub identity for posting the review\n"
        r"(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, (
        "no `Obtain non-default GitHub identity for posting the review` step block found"
    )
    return match.group(1)


def _run_script_body(step_block: str) -> str:
    match = re.search(r"^\s*run: \|\n(.*)\Z", step_block, re.M | re.S)
    assert match, "no `run: |` block found in step"
    return match.group(1)


@skip_until_workflow_diff_applied
def test_claude_code_action_step_has_an_id_for_output_reuse():
    step_block = _claude_code_action_step_block()
    assert re.search(r"^\s*id:\s*run_reviewer\s*$", step_block, re.M), (
        "expected the claude-code-action step to have `id: run_reviewer` so "
        "a later step can reference its `github_token` output"
    )


@skip_until_workflow_diff_applied
def test_reviewer_agent_has_identity_step_after_claude_code_action():
    job_block = _reviewer_agent_job_block()
    claude_index = job_block.find("- name: Run Claude Code (reviewer agent, unattended)")
    identity_index = job_block.find(
        "- name: Obtain non-default GitHub identity for posting the review"
    )
    assert claude_index != -1, "claude-code-action step not found"
    assert identity_index != -1, "identity-obtaining step not found"
    assert claude_index < identity_index, (
        "the identity-obtaining step must come after the claude-code-action "
        "step, since it consumes that step's own output"
    )


@skip_until_workflow_diff_applied
def test_identity_step_reuses_claude_code_actions_github_token_output():
    step_block = _identity_step_block()
    env_match = re.search(r"^\s*env:\n((?:^\s{10}.+\n)+)", step_block, re.M)
    assert env_match, "expected an `env:` block on the identity-obtaining step"
    env_block = env_match.group(1)
    assert "REVIEW_TOKEN: ${{ steps.run_reviewer.outputs.github_token }}" in env_block, (
        "expected the identity step to reuse claude-code-action's own "
        "`github_token` output (confirmed present in action.yml) rather "
        "than inventing a new credential"
    )


@skip_until_workflow_diff_applied
def test_identity_step_does_not_fall_back_to_default_github_token():
    step_block = _identity_step_block()
    assert "github.token" not in step_block, (
        "the identity step must not reference the default GITHUB_TOKEN -- "
        "ADR 0007 Decision 1 requires a non-default identity"
    )
    assert "create-github-app-token" not in step_block, (
        "the create-github-app-token fallback should not be used: this task "
        "confirms the claude-code-action github_token output reuse path "
        "exists, so the fallback is not needed"
    )


@skip_until_workflow_diff_applied
def test_identity_step_fails_visibly_if_token_is_empty():
    step_block = _identity_step_block()
    run_body = _run_script_body(step_block)
    assert re.search(r'if\s*\[\s*-z\s*"\$REVIEW_TOKEN"\s*\]', run_body), (
        "expected an explicit empty-token check on the reused token"
    )
    empty_check_match = re.search(
        r'if\s*\[\s*-z\s*"\$REVIEW_TOKEN"\s*\];\s*then\n(.*?)fi\n', run_body, re.S
    )
    assert empty_check_match, "could not isolate the empty-token if-block body"
    assert "exit 1" in empty_check_match.group(1) or re.search(
        r"exit [1-9]", empty_check_match.group(1)
    ), "the empty-token branch must exit with a non-zero status (FR-013, no silent fallback)"


@skip_until_workflow_diff_applied
def test_identity_step_masks_the_token_in_logs():
    step_block = _identity_step_block()
    run_body = _run_script_body(step_block)
    assert re.search(r"::add-mask::\$REVIEW_TOKEN", run_body), (
        "expected the token to be masked via `::add-mask::` before being "
        "written to GITHUB_OUTPUT, since it is a live credential"
    )


@skip_until_workflow_diff_applied
def test_identity_step_exposes_token_as_its_own_output():
    step_block = _identity_step_block()
    assert re.search(r"^\s*id:\s*get_review_identity\s*$", step_block, re.M), (
        "expected the identity step to have `id: get_review_identity` so a "
        "later step (T113) can reference `steps.get_review_identity.outputs.token`"
    )
    run_body = _run_script_body(step_block)
    assert re.search(r'echo\s+"token=\$REVIEW_TOKEN"\s*>>\s*"\$GITHUB_OUTPUT"', run_body), (
        "expected the reused token to be exposed as this step's own `token` "
        "output"
    )


@skip_until_workflow_diff_applied
def test_identity_step_does_not_itself_post_a_review():
    # T112 is scoped to obtaining/validating the identity only; the actual
    # `gh pr review` dispatch is T113, a separate task.
    step_block = _identity_step_block()
    assert "gh pr review" not in step_block, (
        "T112 must not add `gh pr review` dispatch logic -- that's T113's "
        "scope"
    )


def test_dev_agent_job_unaffected_by_this_task():
    text = _workflow_text()
    match = re.search(r"^  dev-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `dev-agent:` job found"
    dev_block = match.group(1)
    assert "Obtain non-default GitHub identity for posting the review" not in dev_block
