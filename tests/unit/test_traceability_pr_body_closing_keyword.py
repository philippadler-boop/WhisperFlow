"""Unit tests for issue #75 ("Add a non-blocking PR-body closing-keyword
check to traceability.yml (follow-up to #74)").

`traceability.yml`'s existing title check is a hard gate but deliberately
title-only (see its own in-file comment on why). That leaves a gap: a PR
whose title references an issue (satisfying the hard gate) can still merge
without ever actually closing that issue, because GitHub only reads closing
keywords ("Closes #N", "Fixes #N", etc.) from the PR *body* or a commit
message, never the title. This exact bug hit PRs #38, #63, and #71 (see
#74) before a manual audit caught it.

These tests exercise the actual shell script the workflow calls (rather
than reimplementing its regex in Python), so a regression in the real
check -- not just in a parallel Python model of it -- would fail here.
They also assert the workflow wires that script in as non-blocking, once
that wiring has actually been applied to `traceability.yml` -- see the
note below on why that step isn't part of this same commit.

Note: the `.github/scripts/check_pr_body_closing_keyword.sh` script and
its direct unit tests below *are* pushed by this change. The edit to
`.github/workflows/traceability.yml` that calls the script, however,
could not be pushed from this session: the GitHub App token this repo's
agent sessions use deliberately lacks the `workflows` permission needed
to modify files under `.github/workflows/` (the same limitation hit by
issues #59 and #74's item 3). That exact diff is left in the PR
description for a human with push access to apply directly. The two
workflow-wiring tests below are written to skip (not fail) until that
diff lands, so this PR's own CI run stays green, and they'll start
actually asserting once the manual follow-up is applied.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "check_pr_body_closing_keyword.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "traceability.yml"
_WORKFLOW_WIRED = "check_pr_body_closing_keyword.sh" in WORKFLOW.read_text()


def _run(pr_body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PR_BODY": pr_body, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111, "script must be executable"


@pytest.mark.parametrize(
    "body",
    [
        "Closes #75",
        "closes #75",
        "Fixes #75.",
        "This change fixes #75",
        "Resolves: #75",
        "Some context first.\n\nCloses #75\n",
        "Closed #75",
    ],
)
def test_recognized_closing_keyword_immediately_followed_by_issue_number_passes(body):
    result = _run(body)
    assert result.returncode == 0
    assert "::warning::" not in result.stdout
    assert "recognized github closing-keyword" in result.stdout.lower()


@pytest.mark.parametrize(
    "body",
    [
        "",
        "See #75 for context.",
        "Refs #75",
        "closes issue #75",
        "This PR is related to #75",
        "prefixes #75",
        "discloses #75",
    ],
)
def test_missing_or_malformed_closing_reference_warns_but_does_not_fail(body):
    result = _run(body)
    # Non-blocking: must never fail the job even when no valid reference
    # is present.
    assert result.returncode == 0
    assert "::warning::" in result.stdout


def test_unset_pr_body_does_not_error():
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "::warning::" in result.stdout


@pytest.mark.skipif(
    not _WORKFLOW_WIRED,
    reason=(
        "traceability.yml hasn't had the body-check step applied yet -- "
        "see this change's PR description for the exact diff a human "
        "needs to push manually (see module docstring for why)."
    ),
)
def test_workflow_calls_the_body_check_script_non_blocking():
    text = WORKFLOW.read_text()
    assert "check_pr_body_closing_keyword.sh" in text
    assert "github.event.pull_request.body" in text
    # The title check step is (and must remain) the hard gate -- assert the
    # body-check step doesn't introduce its own `exit 1`.
    body_step = text.split("check_pr_body_closing_keyword.sh", 1)[0].rsplit(
        "- name:", 1
    )[-1]
    assert "exit 1" not in body_step


def test_title_check_step_is_still_present_and_still_hard_gate():
    # Guard against this change accidentally weakening the pre-existing
    # hard gate while adding the new non-blocking one.
    text = WORKFLOW.read_text()
    assert "PR title must reference an FR-xxx requirement ID" in text
    assert "exit 1" in text
