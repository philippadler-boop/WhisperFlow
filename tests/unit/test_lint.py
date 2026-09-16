"""Unit tests for T027 ("Lint/type-check cleanup pass across `src/` and
`tests/` (`ruff check --fix`)").

`ci.yml`'s `lint` job already runs `ruff check .` on every PR, but that
gate lives in a workflow file: it only fires after a PR is open, and it's
invisible to anyone running `pytest` locally who hasn't also thought to run
`ruff` separately. This brings the same invariant into the local/CI test
suite itself, using the exact command T027 names (`ruff check --fix`, run
here in its non-mutating `--diff` form so the test can't rewrite files out
from under a developer's working tree) so a future change that reintroduces
a lint violation is caught by `pytest`, not just discovered later by a
separate `ruff check .` step.

`ruff`'s own project config (`pyproject.toml`'s `[tool.ruff]`/
`[tool.ruff.lint]`, verified separately by
`tests/unit/test_pyproject.py::test_ruff_lint_config_present`) is what
actually defines the ruleset (`E`, `F`, `I`, `UP`, `B`) -- this file just
asserts the codebase is clean *against* that ruleset, not what the ruleset
should be.

No standalone type-checker (e.g. `mypy`) is configured anywhere in this
project (`pyproject.toml`, `ci.yml`); `ruff`'s own checks (`F` for
undefined names/unused imports, `UP` for outdated type-hint syntax) are the
only "type-check-adjacent" linting this repo runs, so that's the scope
covered here.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The directories T027 scopes this cleanup pass to, plus `scripts/` --
# `pyproject.toml`'s `[tool.ruff] src` setting also lints `scripts/`, and
# `ci.yml`'s `lint` job lints the whole repo (`ruff check .`), so excluding
# it here would silently narrow the guarantee this test is meant to give.
LINT_TARGETS = ["src", "tests", "scripts"]


def _ruff_available() -> bool:
    return shutil.which("ruff") is not None or _ruff_importable()


def _ruff_importable() -> bool:
    try:
        import ruff  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(
    not _ruff_available(),
    reason="ruff is not installed (see pyproject.toml's `dev` extra)",
)
def test_ruff_check_reports_no_lint_errors():
    """`ruff check` (the project's configured ruleset) finds nothing to
    flag across `src/`, `tests/`, and `scripts/` -- the codebase T027 is
    meant to leave lint-clean."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *LINT_TARGETS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "`ruff check` found lint errors that a T027-style cleanup pass "
        f"(`ruff check --fix`) should clear:\n{result.stdout}{result.stderr}"
    )


@pytest.mark.skipif(
    not _ruff_available(),
    reason="ruff is not installed (see pyproject.toml's `dev` extra)",
)
def test_ruff_check_fix_has_nothing_left_to_fix():
    """`ruff check --fix --diff` (T027's own named command, run in its
    non-mutating `--diff` form) produces no diff -- there is nothing an
    auto-fix pass could still change."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", "--diff", *LINT_TARGETS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "`ruff check --fix --diff` proposed changes -- run `ruff check "
        f"--fix` to apply them:\n{result.stdout}{result.stderr}"
    )
    assert result.stdout.strip() == ""
