#!/usr/bin/env bash
# Non-blocking check: does the PR body contain a valid GitHub closing-keyword
# reference (a recognized keyword immediately followed by #N, with no other
# words in between -- whitespace/a colon is fine, an intervening word is
# not)?
#
# Background (issue #75, follow-up to #74): traceability.yml's title check
# is a hard gate, but it only proves the PR *references* an issue -- not
# that merging it will actually *close* that issue. GitHub only reads
# closing keywords from the PR body or a commit message, never the title,
# so a title-only reference (or a body with wrong phrasing, e.g. "closes
# issue #1", or a non-closing reference, e.g. "Refs #5") passes the title
# check cleanly while leaving the issue open after merge. This bug class
# hit PRs #38, #63, and #71 (see #74) before a manual audit caught it.
#
# This check is deliberately non-blocking (always exits 0, uses
# ::warning:: rather than ::error::) -- see #75's own rationale: PR body
# text is far more often pasted/auto-generated than the title, so a body
# check is inherently more prone to false positives/negatives than the
# strict, hand-written title check traceability.yml already enforces as a
# hard gate. This check flags misses for a human to notice, it doesn't
# block them.
#
# Usage: PR_BODY=<text> check_pr_body_closing_keyword.sh
set -euo pipefail

# GitHub's own recognized closing-keyword set.
KEYWORDS='close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved'

# A keyword, not preceded by a letter (so "prefixes #5" / "discloses #5"
# don't count as containing "fixes" / "closes"), followed only by
# whitespace and/or a colon -- never another word -- before the "#N".
PATTERN="(^|[^A-Za-z])(${KEYWORDS})[[:space:]]*:?[[:space:]]*#[0-9]+"

if printf '%s' "${PR_BODY:-}" | grep -Eiq "$PATTERN"; then
  echo "PR body contains a recognized GitHub closing-keyword reference."
  exit 0
fi

echo "::warning::PR body does not contain a recognized GitHub closing-keyword reference (e.g. 'Closes #N' or 'Fixes #N', keyword immediately followed by #N with no other words in between). A title-only issue reference satisfies traceability's hard gate but will NOT auto-close the issue on merge -- GitHub only reads closing keywords from the PR body or commit messages, never the title. See issues #74/#75."
exit 0
