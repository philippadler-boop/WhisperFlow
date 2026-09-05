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

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "check_pr_body_closing_keyword.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "traceability.yml"
_WORKFLOW_WIRED = "check_pr_body_closing_keyword.sh" in WORKFLOW.read_text()


def _run(pr_body: str) -> subprocess.CompletedProcess:
    # Inherit the invoking process's own PATH rather than hard-coding a
    # POSIX one (e.g. "/usr/bin:/bin"): that literal string isn't a valid
    # Windows PATH entry, so a hard-coded override would make `bash` itself
    # fail to resolve (FileNotFoundError) when these tests are run from a
    # plain Windows shell rather than Git Bash, even though this repo is
    # otherwise developed on Windows. Inheriting os.environ keeps whatever
    # PATH already let the current Python process (and therefore pytest)
    # run in the first place, on every platform.
    env = {**os.environ, "PR_BODY": pr_body}
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()

    # Check the mode git actually tracks for this file, not what the local
    # OS reports via os.stat()/os.access(): Windows has no POSIX executable
    # bit concept at all, so a stat()-based check fails there unconditionally
    # regardless of what's committed, while telling us nothing about what CI
    # (which runs on Linux and does honor the bit) will actually see. `git
    # ls-files -s` reports the mode stored in the git index -- the thing
    # that genuinely determines executability when the repo is checked out
    # on Linux -- so this is meaningful and passes on every platform.
    rel_path = SCRIPT.relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        ["git", "ls-files", "-s", rel_path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout.strip()
    assert output, f"{rel_path} is not tracked by git"

    tracked_mode = output.split()[0]
    assert int(tracked_mode, 8) & 0o111, (
        f"script must be tracked in git as executable (mode 100755), "
        f"but git ls-files reports mode {tracked_mode}"
    )


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
    env = {k: v for k, v in os.environ.items() if k != "PR_BODY"}
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "::warning::" in result.stdout


# --- Adversarial payloads (PR #79 review) -----------------------------------
#
# The script never `eval`s or otherwise re-parses PR_BODY as shell source --
# it only ever expands it as a quoted variable's *value* (`"${PR_BODY:-}"`),
# which bash does not re-tokenize for metacharacters. These cases exist to
# pin that property down as an executable regression test: a future refactor
# that started interpolating PR_BODY into a command string (or otherwise
# re-parsing it) should fail here, rather than being caught only by manual
# review as happened with #38/#63/#71 (see #74/#75).
#
# Each payload targets a unique, per-test-invocation temp path and then
# asserts on the filesystem, not just on the exit code -- proving the
# injected command genuinely never ran, not merely that the script didn't
# crash while it was embedded in PR_BODY.
@pytest.mark.parametrize(
    "make_payload",
    [
        lambda marker: f"Closes #75\n$(touch {marker.as_posix()})",
        lambda marker: f"Closes #75; touch {marker.as_posix()}",
        lambda marker: f"Closes #75 `touch {marker.as_posix()}`",
        lambda marker: f'Closes #75"; touch {marker.as_posix()}; echo "',
    ],
    ids=[
        "command-substitution",
        "semicolon-sequencing",
        "backticks",
        "double-quote-breakout",
    ],
)
def test_adversarial_shell_metacharacters_in_pr_body_are_never_executed(
    tmp_path, make_payload
):
    marker = tmp_path / "pwned"
    body = make_payload(marker)

    result = _run(body)

    assert result.returncode == 0
    assert not marker.exists(), (
        "PR_BODY containing shell metacharacters must never be executed as "
        f"a command, but the injected payload's target file was created: {marker}"
    )


def test_adversarial_rm_payload_in_pr_body_does_not_delete_existing_file(tmp_path):
    victim = tmp_path / "pwned_target"
    victim.write_text("do not delete")
    body = f"Closes #75; rm -rf {victim.as_posix()}"

    result = _run(body)

    assert result.returncode == 0
    assert victim.exists(), "injected `rm -rf` must never actually run"
    assert victim.read_text() == "do not delete"


# --- Positive control for the adversarial tests above (PR #79 review) ------
#
# The adversarial tests above assert `not marker.exists()`. That assertion
# would pass identically whether the script is actually safe, or whether the
# test harness itself is broken (wrong tmp_path scoping, wrong env dict, a
# bash-resolution issue that silently no-ops `_run`) -- a broken harness
# would just never observe the marker either way. This test proves the
# harness would in fact catch a real injection: it runs the same
# subprocess/env/tmp_path plumbing as `_run` (and the same payload style)
# against a small, deliberately naive/vulnerable script that re-interprets
# PR_BODY via `eval`, and asserts the marker DOES get created there. That
# makes the "marker never created" result above meaningful evidence of
# safety, rather than a vacuous pass.
def test_positive_control_methodology_detects_a_real_injection(tmp_path):
    vulnerable = tmp_path / "vulnerable.sh"
    vulnerable.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\neval "echo ${PR_BODY:-}" >/dev/null\n'
    )
    vulnerable.chmod(0o755)

    marker = tmp_path / "pwned"
    # Deliberately the "command-substitution" payload shape from the
    # adversarial tests above, not the "semicolon-sequencing" one: bash
    # treats a bare `#` as starting a comment that runs to end of line, so
    # "Closes #75; touch <marker>" -- fed through this script's `eval` --
    # has its `; touch <marker>` swallowed by the comment starting at `#75`
    # and would never fire, even against this genuinely vulnerable script
    # (confirmed by manually running both variants against it). Putting the
    # payload on its own line after a newline sidesteps that.
    #
    # `.as_posix()` (forward slashes), not the plain WindowsPath str (which
    # is backslash-separated): Git Bash on Windows treats an un-quoted
    # backslash as an escape character, so `touch C:\Users\...\pwned` has
    # every backslash stripped and silently touches a mangled, wrong-named
    # file in the cwd instead of `marker` -- a second path-shaped footgun
    # in this harness, distinct from the shell-metacharacter one this test
    # exists to guard against, but one that would also make this positive
    # control (and by extension the adversarial tests' shared plumbing)
    # falsely look like the vulnerability wasn't detected on Windows.
    body = f"Closes #75\n$(touch {marker.as_posix()})"
    env = {**os.environ, "PR_BODY": body}

    result = subprocess.run(
        ["bash", str(vulnerable)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert marker.exists(), (
        "harness failed to detect injection in a known-vulnerable script -- "
        "the adversarial tests above would pass vacuously if this happened"
    )


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
