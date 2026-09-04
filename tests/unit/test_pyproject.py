"""Unit tests for repo-root pyproject.toml (T002).

These assert the project metadata, dependencies, and tool configuration
required by plan.md's Technical Context and research.md are actually
declared -- not that the (not-yet-implemented) application code behaves
any particular way.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as f:
        return tomllib.load(f)


def test_pyproject_exists():
    assert PYPROJECT_PATH.is_file()


def test_project_metadata():
    data = _load_pyproject()
    project = data["project"]
    assert project["name"] == "whisperflow"
    assert "version" in project


def test_requires_python_311_or_newer():
    data = _load_pyproject()
    requires_python = data["project"]["requires-python"]
    assert requires_python == ">=3.11"


def test_runtime_dependencies_declared():
    data = _load_pyproject()
    dependency_names = {
        dep.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower()
        for dep in data["project"]["dependencies"]
    }
    for expected in {"faster-whisper", "srt", "typer", "rich"}:
        assert expected in dependency_names, f"missing runtime dependency: {expected}"


def test_dev_dependency_pytest_declared():
    data = _load_pyproject()
    dev_deps = data["project"]["optional-dependencies"]["dev"]
    dev_dep_names = {
        dep.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower()
        for dep in dev_deps
    }
    assert "pytest" in dev_dep_names


def test_ruff_lint_config_present():
    data = _load_pyproject()
    ruff_config = data["tool"]["ruff"]
    assert ruff_config["target-version"] == "py311"
    assert "select" in ruff_config["lint"]


def test_pytest_testpaths_config_present():
    data = _load_pyproject()
    pytest_config = data["tool"]["pytest"]["ini_options"]
    assert pytest_config["testpaths"] == ["tests"]
