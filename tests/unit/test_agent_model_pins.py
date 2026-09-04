"""Unit tests for issue #59 ("Pin an explicit model for each subagent
instead of silently inheriting one").

These assert that every subagent definition under `.claude/agents/`
declares an explicit `model:` in its YAML frontmatter -- not that any
application behavior changed, since this is a config-only fix.

Note: this PR covers only the five agent-frontmatter pins (item 1 of the
issue's proposed fix). Item 2 -- adding `--model sonnet` to
`claude-dev-agent.yml`'s `claude_args` -- could not be pushed from this
unattended run: the GitHub App token `claude-dev-agent.yml` deliberately
uses (so commits trigger downstream CI, per that workflow's own comments)
lacks the `workflows` permission needed to modify files under
`.github/workflows/`. That one-line change is left for a human to apply
directly; see the PR description for the exact diff.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

EXPECTED_AGENT_NAMES = {"analyst", "architect", "developer", "reviewer", "qa"}


def _agent_files() -> list[Path]:
    files = sorted(AGENTS_DIR.glob("*.md"))
    assert files, f"no agent files found under {AGENTS_DIR}"
    return files


def _parse_frontmatter(path: Path) -> dict:
    """Parse the flat `key: value` YAML frontmatter these agent files use.

    Deliberately not a full YAML parser (no PyYAML dependency in this
    project) -- these frontmatter blocks are always simple scalar
    `key: value` pairs, never nested structures or lists.
    """
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} does not start with a frontmatter block"
    _, frontmatter, _ = text.split("---\n", 2)
    result: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip()
    return result


def test_agents_dir_has_all_five_expected_agents():
    names = {_parse_frontmatter(p)["name"] for p in _agent_files()}
    assert names == EXPECTED_AGENT_NAMES


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
def test_agent_frontmatter_pins_explicit_model(path: Path):
    frontmatter = _parse_frontmatter(path)
    assert "model" in frontmatter, (
        f"{path.name} has no `model:` field in its frontmatter -- it will "
        "silently inherit whatever model the invoking session defaults to"
    )
    # The alias (e.g. "sonnet"), not a full versioned model ID, per the
    # issue's proposed fix: tracks whatever "sonnet" currently resolves to
    # rather than needing a manual bump on every point release.
    assert frontmatter["model"] == "sonnet"
