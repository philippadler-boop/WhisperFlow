"""Unit tests for issue #148 (T111: "Add the required `VERDICT: APPROVE` /
`VERDICT: REQUEST_CHANGES` machine-readable first-line instruction to
`reviewer-agent`'s prompt-building step (not to `.claude/agents/reviewer.md`
itself, preserving FR-012)").

Per ADR 0006 Decision bullet 1, `reviewer`'s automation-mode prompt (built by
the `Build prompt for reviewer` step added in T109) must explicitly require
the response to begin with a single, fixed, literal machine-readable verdict
line as the first line of its returned text: either exactly
`VERDICT: APPROVE` or exactly `VERDICT: REQUEST_CHANGES`, followed by the
human-readable report on subsequent lines. This requirement must live
entirely in the workflow's own prompt-building step's static instructional
text -- never as a change to `.claude/agents/reviewer.md` itself (FR-012).

This task does NOT add the verdict-parsing/`gh pr review`-posting logic
(that's T112/T113) -- these tests only check that the instruction text
itself is present, unambiguous, and that `reviewer.md` is untouched.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_prompt_wiring.py`'s (issue #146) same
rationale: this project has no PyYAML dependency declared. Per that same
test file's own documented lesson (a heredoc-matching regex there was
recently found to be vacuous because it anchored against column-0 line
starts in text that was still YAML-indented), any regex here that anchors
against literal line starts within the `run:` script body is applied to a
`textwrap.dedent`-ed copy of that body first, not the raw indented text.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"
REVIEWER_AGENT_MD_PATH = REPO_ROOT / ".claude" / "agents" / "reviewer.md"


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


def _build_prompt_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Build prompt for reviewer\n(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no `Build prompt for reviewer` step block found in reviewer-agent"
    return match.group(1)


def _run_script_body(step_block: str) -> str:
    """Return just the `run:` script body of a step block (excluding its
    `env:` block), so assertions only look at the actual script text bash
    will parse.
    """
    match = re.search(r"^\s*run: \|\n(.*)\Z", step_block, re.M | re.S)
    assert match, "no `run: |` block found in step"
    return match.group(1)


def _dedented_run_body() -> str:
    step_block = _build_prompt_step_block()
    return textwrap.dedent(_run_script_body(step_block))


def test_prompt_requires_literal_verdict_approve_line():
    run_body = _dedented_run_body()
    assert re.search(r"^VERDICT: APPROVE\s*$", run_body, re.M), (
        "expected the prompt-building step's instructional text to contain "
        "the exact literal line `VERDICT: APPROVE`, per ADR 0006 Decision "
        "bullet 1"
    )


def test_prompt_requires_literal_verdict_request_changes_line():
    run_body = _dedented_run_body()
    assert re.search(r"^VERDICT: REQUEST_CHANGES\s*$", run_body, re.M), (
        "expected the prompt-building step's instructional text to contain "
        "the exact literal line `VERDICT: REQUEST_CHANGES`, per ADR 0006 "
        "Decision bullet 1"
    )


def test_prompt_instructs_verdict_line_must_be_first():
    run_body = _dedented_run_body()
    assert re.search(r"\bfirst line\b", run_body), (
        "expected the instruction to explicitly say the verdict line must "
        "be the first line of the response, not just present somewhere in "
        "it (ADR 0006 Decision bullet 1)"
    )


def test_prompt_instruction_is_unambiguous_not_vague():
    """Guard against a paraphrased, vague instruction (e.g. just "state your
    verdict") that would not reliably produce one of the two required
    literal strings. The instruction must actually spell out both exact
    literal strings the response must match, and must call out that
    variations/paraphrases are not acceptable.
    """
    run_body = _dedented_run_body()

    # Both literal strings must appear together in the instructional
    # prose (not just embedded once each incidentally) -- i.e. the
    # instruction enumerates both options explicitly.
    assert run_body.count("VERDICT: APPROVE") >= 1
    assert run_body.count("VERDICT: REQUEST_CHANGES") >= 1

    # The instruction must call out that this is a literal/exact match
    # requirement, not a vague request to "state your verdict".
    assert re.search(r"\bliteral\b", run_body), (
        "expected the instruction to explicitly say the verdict line must "
        "be a literal string, not a paraphrase or approximation"
    )
    assert re.search(r"exact(ly)?\b", run_body), (
        "expected the instruction to explicitly say the match must be exact"
    )

    # Must not be a bare, vague instruction with no literal strings
    # specified at all -- reject the "just state your verdict" failure mode
    # by requiring the two literal strings to co-occur near words like
    # "must begin"/"first line".
    assert re.search(r"begin", run_body, re.I), (
        "expected the instruction to say the response must *begin* with "
        "the verdict line"
    )


def test_prompt_gives_disambiguating_examples_of_what_not_to_write():
    run_body = _dedented_run_body()
    assert re.search(r"paraphrase|variation", run_body, re.I), (
        "expected the instruction to explicitly warn against paraphrasing "
        "or varying the required literal strings"
    )


def test_verdict_instruction_appears_after_review_report_instructions():
    """The verdict-line requirement must be additive to, not a replacement
    for, the existing "produce your review report" instruction the T109
    prompt text already carries (which itself mirrors reviewer.md's
    Responsibilities section) -- i.e. it should appear as a further
    requirement layered on top, not instead of that text.
    """
    run_body = _dedented_run_body()
    report_index = run_body.find("Produce your review report")
    verdict_index = run_body.find("VERDICT: APPROVE")
    assert report_index != -1, (
        "expected the pre-existing 'Produce your review report' instruction "
        "(T109) to still be present"
    )
    assert verdict_index != -1
    assert report_index < verdict_index, (
        "expected the verdict-line requirement to be layered on top of, not "
        "in place of, the existing review-report instruction"
    )


def test_reviewer_agent_md_is_untouched():
    """FR-012 / ADR 0006 Consequences: `.claude/agents/reviewer.md` itself
    must remain unchanged -- the verdict-line requirement lives entirely in
    the workflow's own prompt-building step, never in the interactive-mode
    agent definition file.
    """
    assert REVIEWER_AGENT_MD_PATH.exists(), "reviewer.md is expected to exist"
    text = REVIEWER_AGENT_MD_PATH.read_text()

    # reviewer.md's Responsibilities section already asks for "either
    # **approve**, or **request changes**" free-text output -- it must NOT
    # have gained any "VERDICT:" literal-string requirement of its own.
    assert "VERDICT:" not in text, (
        "reviewer.md must not be modified to include the VERDICT: line "
        "requirement -- that requirement belongs only in "
        "claude-agents-pipeline.yml's prompt-building step, per FR-012 "
        "and ADR 0006 Consequences"
    )
