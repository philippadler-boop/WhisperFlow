"""Unit tests for issue #141 (T104: "Add the `qa-agent` job skeleton to
`.github/workflows/claude-agents-pipeline.yml`").

Per ADR 0008/ADR 0009 and FR-005/FR-012, this task adds an inert
`qa-agent` job -- gated by an `if: false` placeholder until Phase 5
(T116) wires its real trigger -- that establishes `qa`'s own isolated
secret and tool grant ahead of that trigger wiring:

- no `github_token` input on its `claude-code-action` step (mirroring
  `dev-agent`'s/`reviewer-agent`'s existing omission, so it authenticates
  as the Claude GitHub App rather than the default `GITHUB_TOKEN`)
- `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_QA }}` (its own role's
  secret, not `ANTHROPIC_API_KEY_DEV` or `ANTHROPIC_API_KEY_REVIEWER`)
- `claude_args` containing exactly `--agent qa --model sonnet
  --allowedTools "Read,Bash,Grep,Glob,Write"` -- copied verbatim from
  `.claude/agents/qa.md`'s own `tools:` frontmatter line, not paraphrased

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_job_skeleton.py`'s (issue #140) same
rationale: this project has no PyYAML dependency declared, and adding one
just for this test would be a heavier footprint than a handful of
anchored regexes on a file this targeted.

NOTE on why the qa-agent-specific tests below are conditionally skipped:
the actual `.github/workflows/claude-agents-pipeline.yml` edit this task calls
for could not be pushed from this session -- the automation GitHub App
token this environment authenticates as lacks the `workflows` permission
needed to push changes under `.github/workflows/` (GitHub rejects the
push outright: "refusing to allow a GitHub App to create or update
workflow ... without `workflows` permission"). This is the exact same
limitation `tests/unit/test_agent_model_pins.py` (issue #59),
`tests/unit/test_pr_closing_keyword_convention.py` (issue #74, see PR
#76), and `tests/unit/test_reviewer_agent_job_skeleton.py` (issue #140,
see PR #168) already hit and documented. A human with real push access
must apply the diff given in this PR's description directly to
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
QA_AGENT_MD_PATH = REPO_ROOT / ".claude" / "agents" / "qa.md"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _qa_agent_job_present() -> bool:
    return bool(re.search(r"^  qa-agent:\n", _workflow_text(), re.M))


skip_until_workflow_diff_applied = pytest.mark.skipif(
    not _qa_agent_job_present(),
    reason=(
        "qa-agent job not yet present in claude-agents-pipeline.yml -- the "
        "automation GitHub App token used to push this PR lacks `workflows` "
        "permission (same limitation as issues #59/#74/#140); see this PR's "
        "description for the exact diff a human must apply directly."
    ),
)


def _qa_agent_job_block() -> str:
    """Return the `qa-agent:` job's own YAML block (from its header line
    up to end of file, since it's currently the last top-level job).

    Top-level job keys are indented exactly two spaces under `jobs:` in
    this file (see `dev-agent:`/`reviewer-agent:`/`qa-agent:`), so the
    next job's header (if any were ever added after this one) is
    identifiable as a line starting with exactly two spaces of indent
    followed by a bareword and a colon.
    """
    text = _workflow_text()
    match = re.search(r"^  qa-agent:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert match, "no top-level `qa-agent:` job found in claude-agents-pipeline.yml"
    return match.group(1)


def _qa_claude_step_block(job_block: str) -> str:
    match = re.search(
        r"uses: anthropics/claude-code-action@v1\n(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no anthropics/claude-code-action step found in qa-agent job"
    return match.group(1)


def _qa_md_tools_line() -> str:
    text = QA_AGENT_MD_PATH.read_text()
    match = re.search(r"^tools:\s*(.+)$", text, re.M)
    assert match, "no `tools:` frontmatter line found in .claude/agents/qa.md"
    return match.group(1).strip()


def test_dev_agent_and_reviewer_agent_jobs_still_present():
    # Guard against this task accidentally clobbering an existing job
    # instead of adding a new one alongside them.
    text = _workflow_text()
    assert re.search(r"^  dev-agent:\n", text, re.M)
    assert re.search(r"^  reviewer-agent:\n", text, re.M)


@skip_until_workflow_diff_applied
def test_qa_agent_job_exists_exactly_once():
    text = _workflow_text()
    assert len(re.findall(r"^  qa-agent:\n", text, re.M)) == 1


@skip_until_workflow_diff_applied
def test_qa_agent_job_trigger_is_placeholder_false():
    # Per T104: "trigger condition left as `if: false` placeholder for
    # now, wired for real in Phase 5". Must be the job-level `if:` key
    # (indented one level under the job), with the literal boolean
    # `false`, not e.g. a quoted string, so GitHub Actions actually
    # short-circuits the job.
    job_block = _qa_agent_job_block()
    assert re.search(r"^    if: false\s*$", job_block, re.M), (
        "expected a job-level `if: false` placeholder directly under `qa-agent:`"
    )


@skip_until_workflow_diff_applied
def test_qa_agent_job_runs_on_ubuntu():
    job_block = _qa_agent_job_block()
    assert re.search(r"^    runs-on: ubuntu-latest\s*$", job_block, re.M)


@skip_until_workflow_diff_applied
def test_qa_step_uses_qa_secret_not_other_role_secrets():
    job_block = _qa_agent_job_block()
    step_block = _qa_claude_step_block(job_block)
    assert "anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY_QA }}" in step_block
    # Belt-and-suspenders per ADR 0008's no-fallback guarantee: the actual
    # `anthropic_api_key:` value must not reference either other role's
    # key. (Explanatory comments elsewhere in the step are allowed to
    # mention the other keys by name for context, so this only inspects
    # the live `with:` field line, not the whole step block.)
    key_line = re.search(r"^\s*anthropic_api_key:.*$", step_block, re.M).group(0)
    assert "ANTHROPIC_API_KEY_DEV" not in key_line
    assert "ANTHROPIC_API_KEY_REVIEWER" not in key_line


@skip_until_workflow_diff_applied
def test_qa_step_omits_github_token():
    # Mirrors dev-agent's/reviewer-agent's existing omission (see those
    # jobs' own steps and their "github_token is deliberately omitted"
    # comments): leaving it unset authenticates as the Claude GitHub App
    # instead of the default GITHUB_TOKEN.
    job_block = _qa_agent_job_block()
    step_block = _qa_claude_step_block(job_block)
    assert "github_token:" not in step_block


@skip_until_workflow_diff_applied
def test_qa_step_claude_args_match_tool_grant_contract():
    job_block = _qa_agent_job_block()
    step_block = _qa_claude_step_block(job_block)
    match = re.search(r"claude_args: '([^']*)'", step_block)
    assert match, "no single-quoted claude_args value found in qa-agent step"
    claude_args = match.group(1)

    assert "--agent qa" in claude_args
    assert "--model sonnet" in claude_args
    # Exact tool list per FR-005/FR-012: qa's automation-mode grant must
    # match qa.md's own `tools:` frontmatter line exactly (order and all),
    # not a paraphrase or narrowing of it.
    assert '--allowedTools "Read,Bash,Grep,Glob,Write"' in claude_args


@skip_until_workflow_diff_applied
def test_qa_step_allowed_tools_matches_qa_md_frontmatter_exactly():
    # Directly ties the workflow's --allowedTools value back to the
    # source of truth (.claude/agents/qa.md's `tools:` line) rather than
    # just asserting a hardcoded expectation twice -- catches drift if
    # either file changes without the other.
    job_block = _qa_agent_job_block()
    step_block = _qa_claude_step_block(job_block)
    match = re.search(r'--allowedTools "([^"]*)"', step_block)
    assert match, "no --allowedTools value found in qa-agent's claude_args"
    workflow_tools = match.group(1)

    qa_md_tools = [t.strip() for t in _qa_md_tools_line().split(",")]
    assert workflow_tools.split(",") == qa_md_tools


@skip_until_workflow_diff_applied
def test_qa_agent_job_has_minimal_read_only_permissions():
    # No checkout/push step exists yet at this skeleton stage (that lands
    # in Phase 5, T117), so no permission beyond read-only `contents` is
    # needed or should be granted yet.
    job_block = _qa_agent_job_block()
    permissions_match = re.search(r"^    permissions:\n((?:^      .+\n)+)", job_block, re.M)
    assert permissions_match, "expected a `permissions:` block on qa-agent"
    permissions_block = permissions_match.group(1)
    assert re.search(r"^\s*contents: read\s*$", permissions_block, re.M)
    assert "write" not in permissions_block
