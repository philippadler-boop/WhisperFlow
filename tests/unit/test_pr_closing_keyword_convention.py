"""Unit tests for issue #74 ("PRs don't reliably auto-close their issue:
3 instances (#1, #5, #8) of missing/broken closing keywords").

Root cause per the issue: nothing in `CLAUDE.md`, `developer.md`, or
`claude-dev-agent.yml`'s prompt template required a PR *body* to contain a
literal, correctly-formed GitHub closing-keyword line (e.g. `Closes #N`),
as distinct from a bare `#N` reference anywhere, or a reference confined to
the PR title. A title-only reference passes `traceability.yml` but never
auto-closes the issue, since GitHub only reads closing keywords from the
PR body or commit messages.

This is a doc/prompt-convention fix (no application code involved), so
these tests assert the convention is actually spelled out in the places
the issue calls out -- not that any runtime behavior changed.

Note: this PR covers the `CLAUDE.md` and `developer.md` updates (items 1-2
of the issue's proposed fix). Item 3 -- updating
`claude-dev-agent.yml`'s prompt template -- could not be pushed from this
unattended run: the GitHub App token `claude-dev-agent.yml` deliberately
uses (so commits trigger downstream CI, per that workflow's own comments)
lacks the `workflows` permission needed to modify files under
`.github/workflows/` (same limitation hit by issue #59's fix). That change
is left for a human to apply directly; see the PR description for the
exact diff. Item 4 (a CI check on PR bodies) is tracked separately as #75.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
DEVELOPER_MD = REPO_ROOT / ".claude" / "agents" / "developer.md"

# GitHub's own recognized closing-keyword set.
CLOSING_KEYWORDS = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
)


def _mentions_recognized_keyword_set(text: str) -> bool:
    """True if the text lists (most of) GitHub's actual closing keywords,
    not just a generic "reference your issue" reminder."""
    lowered = text.lower()
    return sum(1 for kw in CLOSING_KEYWORDS if kw in lowered) >= 6


def _documents_immediately_followed_nuance(text: str) -> bool:
    """True if the text spells out the specific "keyword immediately
    followed by #N, with no other words in between" nuance -- as distinct
    from just listing the recognized keywords. This is the exact detail
    that caused PR #38's failure ("closes issue #1" was accepted as if it
    were a valid closing keyword, because a word sat between the keyword
    and the `#N`), so it's the single highest-value thing to guard against
    regressing.

    Both `CLAUDE.md` and `developer.md` wrap this sentence across a
    manually-wrapped markdown line, so the phrases below can span a
    newline in the raw source; whitespace is normalized before matching so
    that wrapping doesn't hide a missing/reworded nuance.
    """
    normalized = re.sub(r"\s+", " ", text.lower())
    return (
        "immediately followed by" in normalized
        and "no other words in between" in normalized
    )


def test_claude_md_documents_pr_body_closing_keyword_convention():
    text = CLAUDE_MD.read_text()
    assert "Closes #N" in text or "closes #N" in text.lower()
    assert re.search(r"\bbody\b", text)
    assert _mentions_recognized_keyword_set(text)
    # Should call out that a title-only reference is not sufficient.
    assert "title-only" in text.lower() or "title only" in text.lower()
    # Should spell out the "keyword immediately followed by #N, no other
    # words in between" nuance -- not just list the recognized keywords.
    assert _documents_immediately_followed_nuance(text)


def test_developer_agent_documents_pr_body_closing_keyword_convention():
    text = DEVELOPER_MD.read_text()
    assert "Closes #N" in text or "closes #n" in text.lower()
    assert re.search(r"\*\*body\*\*|\bbody\b", text)
    assert _mentions_recognized_keyword_set(text)
    # Should spell out the "keyword immediately followed by #N, no other
    # words in between" nuance -- not just list the recognized keywords.
    assert _documents_immediately_followed_nuance(text)


def test_developer_agent_still_requires_title_reference():
    # Guard against the body-convention addition accidentally dropping the
    # pre-existing title requirement that traceability.yml's title-only
    # check depends on.
    text = DEVELOPER_MD.read_text()
    assert "title" in text.lower()
    assert "FR-xxx" in text or "FR-" in text
