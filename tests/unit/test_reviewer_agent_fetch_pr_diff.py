"""Unit tests for issue #145 (T108: "Add a `Fetch PR diff` step to
`reviewer-agent`: run `gh pr diff <PR_NUMBER>`, write the output to
`GITHUB_OUTPUT` via a randomly generated (not fixed) heredoc delimiter,
following the exact `env:`-then-`"$VAR"` pattern the existing 'Build
prompt for this trigger' step already uses for attacker-controlled text").

Per ADR 0005 Decision 2 and its Consequences section, this task adds a
`Fetch PR diff` step to the `reviewer-agent` job -- after `Checkout PR
head` (T107) and before the `claude-code-action` step -- that fetches the
PR's diff via `gh pr diff` and exposes it as a step output, WITHOUT wiring
it into `reviewer`'s prompt yet (that is T109). This is the most
security-sensitive step added by this feature so far: a PR's diff is
exactly as attacker-controlled as an issue title or review body (anyone
who can push to the PR branch controls it), so it MUST follow the same
`env:`-then-`"$VAR"`-in-heredoc discipline `dev-agent`'s "Build prompt for
this trigger" step already uses, but with a randomized (not fixed)
heredoc delimiter, and it MUST fail visibly rather than silently
continuing if the fetch fails or returns empty (FR-013).

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_checkout_pr_head.py`'s (issue #144) and
`tests/unit/test_reviewer_agent_trigger.py`'s (issue #143) same rationale:
this project has no PyYAML dependency declared, and adding one just for
this test would be a heavier footprint than a handful of anchored regexes
on a file this targeted.
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


def _fetch_pr_diff_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Fetch PR diff\n(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no `Fetch PR diff` step block found in reviewer-agent"
    return match.group(1)


def _build_prompt_step_block() -> str:
    dev_block = _dev_agent_job_block()
    match = re.search(
        r"^      - name: Build prompt for this trigger\n(.*?)(?=^      - name:|\Z)",
        dev_block,
        re.M | re.S,
    )
    assert match, "no `Build prompt for this trigger` step block found in dev-agent"
    return match.group(1)


def _run_script_body(step_block: str) -> str:
    """Return just the `run:` script body of a step block (excluding its
    `env:` block), so assertions about `${{ }}` splicing only look at the
    actual script text bash will parse, not the `env:` mapping (which is
    expected and safe to contain `${{ }}` -- those are GitHub Actions
    context expressions resolved into plain environment variable values
    before bash ever runs, not shell script text).
    """
    match = re.search(r"^\s*run: \|\n(.*)\Z", step_block, re.M | re.S)
    assert match, "no `run: |` block found in step"
    return match.group(1)


def test_reviewer_agent_has_fetch_pr_diff_step():
    job_block = _reviewer_agent_job_block()
    assert re.search(r"^      - name: Fetch PR diff\s*$", job_block, re.M), (
        "expected a `Fetch PR diff` step in reviewer-agent"
    )


def test_fetch_pr_diff_is_after_checkout_and_before_claude_code_action():
    job_block = _reviewer_agent_job_block()
    steps_block = _steps_block(job_block)
    checkout_index = steps_block.find("- name: Checkout PR head")
    fetch_index = steps_block.find("- name: Fetch PR diff")
    claude_index = steps_block.find("- name: Run Claude Code (reviewer agent, unattended)")
    assert checkout_index != -1, "Checkout PR head step not found in reviewer-agent steps"
    assert fetch_index != -1, "Fetch PR diff step not found in reviewer-agent steps"
    assert claude_index != -1, (
        "Run Claude Code (reviewer agent, unattended) step not found in reviewer-agent steps"
    )
    assert checkout_index < fetch_index < claude_index, (
        "Fetch PR diff must come after Checkout PR head and before the "
        "claude-code-action step"
    )


def test_fetch_pr_diff_uses_env_block_for_context_values():
    step_block = _fetch_pr_diff_step_block()
    env_match = re.search(r"^\s*env:\n((?:^\s{10}.+\n)+)", step_block, re.M)
    assert env_match, "expected an `env:` block on Fetch PR diff"
    env_block = env_match.group(1)
    assert "GH_TOKEN: ${{ github.token }}" in env_block
    assert "REPO: ${{ github.repository }}" in env_block
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in env_block


def test_fetch_pr_diff_run_script_never_splices_expression_syntax():
    # The core injection-safety property (ADR 0005 Consequences): the
    # `run:` script body itself -- what bash actually parses -- must
    # contain no `${{ }}` GitHub Actions expression syntax at all. Every
    # attacker-influenced or context-derived value must arrive via an
    # already-expanded shell variable (from the `env:` block above),
    # referenced as a plain `$VAR`/`"$VAR"`, never spliced directly into
    # the script text via `${{ }}`.
    step_block = _fetch_pr_diff_step_block()
    run_body = _run_script_body(step_block)
    assert "${{" not in run_body, (
        "Fetch PR diff's run: script body must not contain any `${{ }}` "
        "GitHub Actions expression -- context values must flow through "
        "env: and be referenced as $VAR, never spliced directly into the "
        "script text (ADR 0005 Consequences)"
    )


def test_fetch_pr_diff_references_env_vars_as_shell_variables():
    step_block = _fetch_pr_diff_step_block()
    run_body = _run_script_body(step_block)
    assert '"$PR_NUMBER"' in run_body
    assert '"$REPO"' in run_body
    # The diff itself must be captured into a shell variable and referenced
    # as "$VAR" inside the heredoc, mirroring the exact env:-then-"$VAR"
    # pattern of dev-agent's "Build prompt for this trigger" step.
    assert re.search(r'^\s*DIFF="\$\(gh pr diff', run_body, re.M), (
        "expected `gh pr diff` output to be captured into a $DIFF shell "
        "variable via command substitution"
    )
    assert '"$DIFF"' in run_body, (
        'expected the captured diff to be referenced as "$DIFF" inside the '
        "heredoc body, not re-spliced any other way"
    )


def test_fetch_pr_diff_writes_multiline_output_via_heredoc_to_github_output():
    step_block = _fetch_pr_diff_step_block()
    run_body = _run_script_body(step_block)
    assert "diff<<$" in run_body or re.search(r"diff<<\$\w", run_body), (
        "expected a `diff<<$DELIM`-style multiline GITHUB_OUTPUT heredoc "
        "opener referencing a shell variable, not a literal fixed word"
    )
    assert '>> "$GITHUB_OUTPUT"' in run_body


def test_fetch_pr_diff_heredoc_delimiter_is_randomized_not_fixed():
    step_block = _fetch_pr_diff_step_block()
    run_body = _run_script_body(step_block)
    delim_match = re.search(r'^\s*DELIM="([^"]*)"', run_body, re.M)
    assert delim_match, "expected a DELIM=\"...\" assignment building the heredoc delimiter"
    delim_expr = delim_match.group(1)
    # Evidence of runtime randomization: a command substitution (reading a
    # fresh UUID, or some other runtime-computed source) and/or $RANDOM,
    # not merely "not literally EOF". A delimiter built from a fixed string
    # alone (no $(...) and no $RANDOM anywhere in its construction) would
    # be exactly the fixed-delimiter risk ADR 0005 Decision 2 calls out.
    assert "$(" in delim_expr or "$RANDOM" in delim_expr, (
        "heredoc delimiter must be built using a command substitution "
        "(e.g. reading a fresh UUID) and/or $RANDOM at runtime -- a "
        "delimiter that is just a fixed string, even a random-looking one "
        "hardcoded in the file, does not satisfy ADR 0005 Decision 2's "
        "randomization requirement"
    )


def test_fetch_pr_diff_delimiter_differs_in_kind_from_build_prompt_step():
    # dev-agent's existing step uses a fixed delimiter
    # (PROMPT_EOF_8f3a2b91); confirm this new step's delimiter mechanism is
    # not simply copy-pasted as another fixed string.
    build_prompt_block = _build_prompt_step_block()
    assert "PROMPT_EOF_8f3a2b91" in build_prompt_block

    fetch_diff_block = _fetch_pr_diff_step_block()
    assert "PROMPT_EOF_8f3a2b91" not in fetch_diff_block


def test_fetch_pr_diff_fails_on_empty_diff_without_silent_fallback():
    step_block = _fetch_pr_diff_step_block()
    run_body = _run_script_body(step_block)
    assert re.search(r'if\s*\[\s*-z\s*"\$DIFF"\s*\]', run_body), (
        "expected an explicit empty-output check on the captured diff"
    )
    # The empty-check branch must actually fail the step (non-zero exit),
    # not just log and continue.
    empty_check_match = re.search(
        r'if\s*\[\s*-z\s*"\$DIFF"\s*\];\s*then\n(.*?)fi\n', run_body, re.S
    )
    assert empty_check_match, "could not isolate the empty-diff if-block body"
    assert "exit 1" in empty_check_match.group(1) or re.search(
        r"exit [1-9]", empty_check_match.group(1)
    ), "the empty-diff branch must exit with a non-zero status (FR-013, no silent fallback)"


def test_fetch_pr_diff_does_not_swallow_gh_command_failure():
    step_block = _fetch_pr_diff_step_block()
    run_body = _run_script_body(step_block)
    gh_line_match = re.search(r'^\s*DIFF="\$\(gh pr diff.*\)"\s*$', run_body, re.M)
    assert gh_line_match, "expected a DIFF=\"$(gh pr diff ...)\" line"
    gh_line = gh_line_match.group(0)
    # No error-swallowing idioms (|| true, || echo, 2>/dev/null) may be
    # attached to the gh pr diff invocation itself -- a non-zero exit here
    # must propagate (GitHub Actions' default `bash -eo pipefail` for
    # run: steps turns that into a failed step), per FR-013's no-silent-
    # fallback requirement. (The UUID-generation fallback later in the
    # script is a separate, allowed use of `||` for a non-security-critical
    # randomness source, not an error-swallow on the diff fetch itself.)
    assert "||" not in gh_line
    assert "2>/dev/null" not in gh_line


def test_fetch_pr_diff_not_wired_into_prompt_yet():
    # T108 is scoped to fetching only; wiring the fetched diff into
    # reviewer's actual prompt is T109, a separate task. This only
    # inspects the live `prompt:` field's own value line -- explanatory
    # comments elsewhere in the step (including ones documenting that the
    # diff is now available as a step output, for T109 to consume later)
    # are expected and fine.
    job_block = _reviewer_agent_job_block()
    claude_step_match = re.search(
        r"^      - name: Run Claude Code \(reviewer agent, unattended\)\n(.*?)\Z",
        job_block,
        re.M | re.S,
    )
    assert claude_step_match, "no claude-code-action step found in reviewer-agent"
    claude_step_block = claude_step_match.group(1)
    prompt_line_match = re.search(r"^\s*prompt:.*$", claude_step_block, re.M)
    assert prompt_line_match, "no `prompt:` field found in reviewer-agent's claude-code-action step"
    assert "steps.fetch_diff.outputs.diff" not in prompt_line_match.group(0), (
        "T108 must not wire the fetched diff into reviewer's prompt -- "
        "that is T109's scope"
    )


def test_reviewer_agent_job_permissions_gain_pull_requests_read():
    # `gh pr diff` needs `pull-requests: read` on the job's GITHUB_TOKEN
    # permissions in addition to the existing `contents: read`.
    job_block = _reviewer_agent_job_block()
    permissions_match = re.search(r"^    permissions:\n((?:^      .+\n)+)", job_block, re.M)
    assert permissions_match, "expected a `permissions:` block on reviewer-agent"
    permissions_block = permissions_match.group(1)
    assert re.search(r"^\s*contents: read\s*$", permissions_block, re.M)
    assert re.search(r"^\s*pull-requests: read\s*$", permissions_block, re.M)
    assert "write" not in permissions_block


def test_dev_agent_job_unaffected_by_this_task():
    # T108 is scoped to reviewer-agent only; dev-agent's own
    # "Build prompt for this trigger" step must remain untouched.
    dev_block = _dev_agent_job_block()
    assert re.search(r"^      - name: Build prompt for this trigger\s*$", dev_block, re.M)
