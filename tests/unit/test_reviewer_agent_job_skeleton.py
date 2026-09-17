"""Unit tests for issue #140 (T103: "Add the `reviewer-agent` job skeleton
to `.github/workflows/claude-agents-pipeline.yml`").

Per ADR 0008/ADR 0009 and FR-002/contracts/automation-triggers.md's
tool-grant table, this task adds an inert `reviewer-agent` job -- gated by
an `if: false` placeholder until Phase 3 (T106) wires its real trigger --
that establishes reviewer's own isolated secret and tool grant ahead of
that trigger wiring:

- no `github_token` input on its `claude-code-action` step (mirroring
  `dev-agent`'s existing omission, so it authenticates as the Claude
  GitHub App rather than the default `GITHUB_TOKEN`)
- `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_REVIEWER }}` (its own
  role's secret, not `ANTHROPIC_API_KEY_DEV`)
- `claude_args` containing exactly `--agent reviewer --model sonnet
  --allowedTools "Read,Grep,Glob"`

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- this project has no PyYAML
dependency (see `tests/unit/test_agent_model_pins.py`'s frontmatter
parser for the same rationale), and adding one just for this test would
be a heavier footprint than a handful of anchored regexes on a file this
targeted.

NOTE on why the reviewer-agent-specific tests below are conditionally
skipped: the actual `.github/workflows/claude-agents-pipeline.yml` edit this
task calls for could not be pushed from this session -- the automation
GitHub App token this environment authenticates as lacks the `workflows`
permission needed to push changes under `.github/workflows/` (GitHub
rejects the push outright: "refusing to allow a GitHub App to create or
update workflow ... without `workflows` permission"). This is the exact
same limitation `tests/unit/test_agent_model_pins.py` (issue #59) and
`tests/unit/test_pr_closing_keyword_convention.py` (issue #74, see PR
#76) already hit and documented. A human with real push access must
apply the diff given in this PR's description directly to
`claude-agents-pipeline.yml`; these tests are written against the target state
that diff produces and will start running for real the moment it lands
(no test-file edit needed) -- they skip cleanly rather than failing CI
in the meantime.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _reviewer_agent_job_present() -> bool:
    return bool(re.search(r"^  reviewer-agent:\n", _workflow_text(), re.M))


skip_until_workflow_diff_applied = pytest.mark.skipif(
    not _reviewer_agent_job_present(),
    reason=(
        "reviewer-agent job not yet present in claude-agents-pipeline.yml -- the "
        "automation GitHub App token used to push this PR lacks `workflows` "
        "permission (same limitation as issues #59/#74); see this PR's "
        "description for the exact diff a human must apply directly."
    ),
)


def _reviewer_agent_job_block() -> str:
    """Return the `reviewer-agent:` job's own YAML block (from its header
    line up to, but not including, the next top-level-under-`jobs:` job
    header or end of file).

    Top-level job keys are indented exactly two spaces under `jobs:` in
    this file (see `dev-agent:`/`reviewer-agent:`), so the next job's
    header is identifiable as a line starting with exactly two spaces of
    indent followed by a bareword and a colon.
    """
    text = _workflow_text()
    match = re.search(r"^  reviewer-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `reviewer-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


def _reviewer_claude_step_block(job_block: str) -> str:
    match = re.search(
        r"uses: anthropics/claude-code-action@v1\n(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no anthropics/claude-code-action step found in reviewer-agent job"
    return match.group(1)


def test_dev_agent_job_still_present():
    # Guard against this task accidentally clobbering the existing job
    # instead of adding a new one alongside it.
    assert re.search(r"^  dev-agent:\n", _workflow_text(), re.M)


@skip_until_workflow_diff_applied
def test_reviewer_agent_job_exists_exactly_once():
    text = _workflow_text()
    assert len(re.findall(r"^  reviewer-agent:\n", text, re.M)) == 1


@skip_until_workflow_diff_applied
def test_reviewer_agent_job_trigger_is_placeholder_false():
    # Per T103: "trigger condition left as `if: false` placeholder for
    # now, wired for real in Phase 3". Must be the job-level `if:` key
    # (indented one level under the job), with the literal boolean
    # `false`, not e.g. a quoted string, so GitHub Actions actually
    # short-circuits the job.
    job_block = _reviewer_agent_job_block()
    assert re.search(r"^    if: false\s*$", job_block, re.M), (
        "expected a job-level `if: false` placeholder directly under "
        "`reviewer-agent:`"
    )


@skip_until_workflow_diff_applied
def test_reviewer_agent_job_runs_on_ubuntu():
    job_block = _reviewer_agent_job_block()
    assert re.search(r"^    runs-on: ubuntu-latest\s*$", job_block, re.M)


@skip_until_workflow_diff_applied
def test_reviewer_step_uses_reviewer_secret_not_dev_secret():
    job_block = _reviewer_agent_job_block()
    step_block = _reviewer_claude_step_block(job_block)
    assert "anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_REVIEWER }}" in step_block
    # Belt-and-suspenders per ADR 0008's no-fallback guarantee: the actual
    # `anthropic_api_key:` value must not reference the dev key. (Explanatory
    # comments elsewhere in the step are allowed to mention the dev key by
    # name for context, so this only inspects the live `with:` field line,
    # not the whole step block.)
    key_line = re.search(r"^\s*anthropic_api_key:.*$", step_block, re.M).group(0)
    assert "ANTHROPIC_API_KEY_DEV" not in key_line


@skip_until_workflow_diff_applied
def test_reviewer_step_omits_github_token():
    # Mirrors dev-agent's existing omission (see that job's own step and
    # its "github_token is deliberately omitted" comment): leaving it
    # unset authenticates as the Claude GitHub App instead of the default
    # GITHUB_TOKEN.
    job_block = _reviewer_agent_job_block()
    step_block = _reviewer_claude_step_block(job_block)
    assert "github_token:" not in step_block


@skip_until_workflow_diff_applied
def test_reviewer_step_claude_args_match_tool_grant_contract():
    job_block = _reviewer_agent_job_block()
    step_block = _reviewer_claude_step_block(job_block)
    match = re.search(r"claude_args: '([^']*)'", step_block)
    assert match, "no single-quoted claude_args value found in reviewer-agent step"
    claude_args = match.group(1)

    assert "--agent reviewer" in claude_args
    assert "--model sonnet" in claude_args
    # Exact tool list per FR-002/contracts/automation-triggers.md's
    # tool-grant table: reviewer MUST get exactly Read,Grep,Glob and MUST
    # NOT get Write/Edit/Bash in automation mode.
    assert '--allowedTools "Read,Grep,Glob"' in claude_args
    for forbidden in ("Write", "Edit", "Bash"):
        assert forbidden not in claude_args


@skip_until_workflow_diff_applied
def test_reviewer_agent_job_has_minimal_read_only_permissions():
    # No checkout/diff-fetch step exists yet at this skeleton stage (that
    # lands in Phase 3, T107/T108), so no permission beyond read-only
    # `contents` is needed or should be granted yet.
    job_block = _reviewer_agent_job_block()
    permissions_match = re.search(
        r"^    permissions:\n((?:^      .+\n)+)", job_block, re.M
    )
    assert permissions_match, "expected a `permissions:` block on reviewer-agent"
    permissions_block = permissions_match.group(1)
    assert re.search(r"^\s*contents: read\s*$", permissions_block, re.M)
    assert "write" not in permissions_block
