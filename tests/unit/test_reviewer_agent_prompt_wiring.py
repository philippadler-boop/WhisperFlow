"""Unit tests for issue #146 (T109: "Extend `reviewer-agent`'s
prompt-building step to embed the fetched diff text into `reviewer`'s
prompt (via the `prompt:` `with:`-field YAML substitution, never a `run:`
shell splice) and instruct `reviewer` to use `Read`/`Grep`/`Glob` against
the checked-out tree only for context beyond the diff, never to attempt
re-deriving the diff itself").

Per ADR 0005 Decision 3, this task adds a dedicated `Build prompt for
reviewer` step (id: `build_prompt`) to `reviewer-agent` -- after `Fetch PR
diff` (T108) and before the `claude-code-action` step -- that assembles
the diff fetched by T108 into `reviewer`'s actual prompt text and exposes
it as this new step's own `prompt` output. The `claude-code-action` step's
`prompt:` `with:`-field then references that output via a YAML-level
`${{ steps.build_prompt.outputs.prompt }}` substitution -- never a `run:`
shell splice of the diff itself, which is the injection-unsafe pattern
`Fetch PR diff` (T108) and `dev-agent`'s existing "Build prompt for this
trigger" step already avoid for the same reason.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse for the assertions below -- mirroring
`tests/unit/test_reviewer_agent_fetch_pr_diff.py`'s (issue #145) same
rationale: this project has no PyYAML dependency declared, and adding one
just for these regex-shaped assertions would be a heavier footprint than a
handful of anchored regexes on a file this targeted. (A separate,
one-off `yaml.safe_load` sanity check was performed manually against this
file while implementing this task, since the new step's multi-line heredoc
content makes YAML block-scalar indentation easy to get subtly wrong --
but that check is not encoded as one of these tests, to keep this test
file dependency-free like its siblings.)
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


def _steps_block(job_block: str) -> str:
    match = re.search(r"^    steps:\n(.*)\Z", job_block, re.M | re.S)
    assert match, "no `steps:` block found in job"
    return match.group(1)


def _build_prompt_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Build prompt for reviewer\n(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no `Build prompt for reviewer` step block found in reviewer-agent"
    return match.group(1)


def _claude_code_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Run Claude Code \(reviewer agent, unattended\)\n(.*?)\Z",
        job_block,
        re.M | re.S,
    )
    assert match, "no claude-code-action step found in reviewer-agent"
    return match.group(1)


def _run_script_body(step_block: str) -> str:
    """Return just the `run:` script body of a step block (excluding its
    `env:` block), so assertions about `${{ }}` splicing only look at the
    actual script text bash will parse.
    """
    match = re.search(r"^\s*run: \|\n(.*)\Z", step_block, re.M | re.S)
    assert match, "no `run: |` block found in step"
    return match.group(1)


def test_reviewer_agent_has_build_prompt_step():
    job_block = _reviewer_agent_job_block()
    assert re.search(r"^      - name: Build prompt for reviewer\s*$", job_block, re.M), (
        "expected a `Build prompt for reviewer` step in reviewer-agent"
    )


def test_build_prompt_step_has_expected_id():
    step_block = _build_prompt_step_block()
    assert re.search(r"^\s*id: build_prompt\s*$", step_block, re.M), (
        "expected `Build prompt for reviewer` to have id: build_prompt, "
        "matching ADR 0005 Decision 3's `steps.build_prompt.outputs.prompt` naming"
    )


def test_build_prompt_step_is_after_fetch_diff_and_before_claude_code_action():
    job_block = _reviewer_agent_job_block()
    steps_block = _steps_block(job_block)
    fetch_index = steps_block.find("- name: Fetch PR diff")
    build_index = steps_block.find("- name: Build prompt for reviewer")
    claude_index = steps_block.find("- name: Run Claude Code (reviewer agent, unattended)")
    assert fetch_index != -1, "Fetch PR diff step not found in reviewer-agent steps"
    assert build_index != -1, "Build prompt for reviewer step not found in reviewer-agent steps"
    assert claude_index != -1, (
        "Run Claude Code (reviewer agent, unattended) step not found in reviewer-agent steps"
    )
    assert fetch_index < build_index < claude_index, (
        "Build prompt for reviewer must come after Fetch PR diff and "
        "before the claude-code-action step"
    )


def test_build_prompt_step_reads_diff_via_env_block_not_run_splice():
    step_block = _build_prompt_step_block()
    env_match = re.search(r"^\s*env:\n((?:^\s{10}.+\n)+)", step_block, re.M)
    assert env_match, "expected an `env:` block on Build prompt for reviewer"
    env_block = env_match.group(1)
    assert "DIFF: ${{ steps.fetch_diff.outputs.diff }}" in env_block, (
        "expected the fetched diff to arrive via env:, mirroring dev-agent's "
        "existing $ISSUE_TITLE pattern"
    )
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in env_block


def test_build_prompt_run_script_never_splices_expression_syntax():
    # Core injection-safety property (ADR 0005 Decision 3 / Consequences):
    # the `run:` script body itself -- what bash actually parses -- must
    # contain no `${{ }}` GitHub Actions expression syntax. The diff must
    # arrive already-expanded via the env: block and be referenced only as
    # a plain shell variable.
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    assert "${{" not in run_body, (
        "Build prompt for reviewer's run: script body must not contain any "
        "`${{ }}` GitHub Actions expression -- the diff must flow through "
        "env: and be referenced as $DIFF, never spliced directly into the "
        "script text (ADR 0005 Decision 3)"
    )


def test_build_prompt_references_diff_as_shell_variable():
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    assert '"$DIFF"' in run_body, (
        'expected the diff to be referenced as "$DIFF" (e.g. via echo "$DIFF"), '
        "not re-spliced any other way"
    )
    assert '"$PR_NUMBER"' in run_body or "#$PR_NUMBER" in run_body


def test_build_prompt_writes_multiline_output_via_randomized_delimiter():
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    assert re.search(r"prompt<<\$\w", run_body), (
        "expected a `prompt<<$DELIM`-style multiline GITHUB_OUTPUT heredoc "
        "opener referencing a shell variable, not a literal fixed word"
    )
    assert '>> "$GITHUB_OUTPUT"' in run_body
    delim_match = re.search(r'^\s*DELIM="([^"]*)"', run_body, re.M)
    assert delim_match, 'expected a DELIM="..." assignment building the heredoc delimiter'
    delim_expr = delim_match.group(1)
    assert "$(" in delim_expr or "$RANDOM" in delim_expr, (
        "the outer GITHUB_OUTPUT delimiter for this step's prompt value "
        "must be randomized at runtime, same as the Fetch PR diff step's "
        "own delimiter, since the diff embedded inside it is exactly as "
        "large and attacker-influenced here as it was there (ADR 0005 "
        "Decision 2's collision-risk reasoning applies equally to this "
        "step's own multiline output boundary)"
    )


def test_build_prompt_never_places_diff_inside_a_fixed_heredoc():
    # The diff must be emitted via a plain `echo "$DIFF"`, not embedded
    # inside a `cat <<FIXED_WORD` heredoc -- otherwise a diff line that
    # happens to equal the fixed delimiter word would silently truncate
    # the prompt (the same collision class ADR 0005 Decision 2 already
    # flags for the Fetch PR diff step's own delimiter).
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    for match in re.finditer(r"cat <<(\S+)\n(.*?)^\1\s*$", run_body, re.M | re.S):
        heredoc_body = match.group(2)
        assert "$DIFF" not in heredoc_body, (
            f"found $DIFF referenced inside a fixed-delimiter heredoc "
            f"(<<{match.group(1)}) -- the diff must only be emitted via a "
            f"standalone echo \"$DIFF\", never inside a heredoc whose "
            f"delimiter is a fixed word a diff line could collide with"
        )


def test_build_prompt_text_instructs_read_grep_glob_for_context():
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    assert re.search(r"Read.{0,20}Grep.{0,20}Glob", run_body, re.S), (
        "expected the prompt text to instruct reviewer to use its Read/"
        "Grep/Glob tools"
    )
    assert "checked out" in run_body or "checked-out" in run_body, (
        "expected the prompt text to reference the already-checked-out "
        "working tree (T107) as the surface those tools operate against"
    )


def test_build_prompt_text_instructs_not_to_rederive_diff():
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    assert re.search(r"not attempt to re-derive|never to reconstruct or re-derive", run_body), (
        "expected the prompt text to explicitly instruct reviewer never to "
        "attempt re-deriving/reconstructing the diff itself"
    )
    assert re.search(r"no Bash, git, or gh tool", run_body), (
        "expected the prompt text to explain reviewer has no tool capable "
        "of re-deriving the diff itself"
    )


def test_build_prompt_text_embeds_diff_between_markers():
    step_block = _build_prompt_step_block()
    run_body = _run_script_body(step_block)
    assert "--- BEGIN DIFF ---" in run_body
    assert "--- END DIFF ---" in run_body
    begin_index = run_body.find("--- BEGIN DIFF ---")
    diff_echo_index = run_body.find('echo "$DIFF"')
    end_index = run_body.find("--- END DIFF ---", diff_echo_index)
    assert begin_index != -1 and diff_echo_index != -1 and end_index != -1
    assert begin_index < diff_echo_index < end_index, (
        "expected the diff to be echoed between the BEGIN/END DIFF markers"
    )


def test_claude_code_action_prompt_references_build_prompt_output():
    step_block = _claude_code_step_block()
    prompt_line_match = re.search(r"^\s*prompt:.*$", step_block, re.M)
    assert prompt_line_match, "no `prompt:` field found in reviewer-agent's claude-code-action step"
    prompt_line = prompt_line_match.group(0)
    assert "${{ steps.build_prompt.outputs.prompt }}" in prompt_line, (
        "expected reviewer's prompt: with:-field to reference "
        "${{ steps.build_prompt.outputs.prompt }} via YAML-level "
        "substitution, per ADR 0005 Decision 3"
    )
    assert "Placeholder" not in prompt_line, (
        "the placeholder prompt text from T103/T108 must be replaced now "
        "that the diff is actually wired in (T109)"
    )


def test_claude_code_action_prompt_field_is_not_a_run_step():
    # Guard against someone "fixing" this by moving the substitution into a
    # run: shell splice instead of the with:-field YAML substitution ADR
    # 0005 Decision 3 requires.
    step_block = _claude_code_step_block()
    assert "uses: anthropics/claude-code-action@v1" in step_block
    # Line-anchored (not a plain substring check): this step's surrounding
    # comments legitimately mention "run:" in prose (contrasting this
    # with:-field substitution with T108's run: step), which must not
    # trip this assertion -- only an actual `run:` YAML key would.
    assert not re.search(r"^\s*run:\s*(\||>|\S)", step_block, re.M), (
        "reviewer-agent's claude-code-action step must remain an action "
        "invocation (with: prompt:), not a run: shell step"
    )
