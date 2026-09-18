"""Unit tests for issue #149 (T112: "Add a step obtaining the non-default
GitHub identity needed to post the review ... in
`.github/workflows/claude-agents-pipeline.yml` (ADR 0007 Decision 1)").

Per ADR 0007 Decision 1, the `gh pr review` call that will post reviewer's
verdict (T113) must authenticate as a non-default GitHub identity. Decision
1 names two paths: (a) reuse whichever mechanism `claude-code-action`
exposes for a subsequent plain `gh` step to authenticate as the same Claude
GitHub App identity `dev-agent`/`reviewer-agent`'s own `claude-code-action`
steps already use when `github_token` is omitted, or (b) -- if no such
reuse path exists -- fall back to `actions/create-github-app-token` with
dedicated credentials.

This repo has no evidence anywhere (research.md, ADR 0005/0007/0009, or
`claude-agents-pipeline.yml`'s own pre-existing comments) of a specific,
confirmed claude-code-action output/token-reuse mechanism for path (a) --
every existing mention of omitting `github_token` documents only that doing
so changes which identity the *action's own internal* git/gh calls use,
never that the resulting token is exported for a later step to consume.
Per the task's own instruction for this fork, and per Constitution
Principle V / CLAUDE.md's "test by invocation, not self-report" lesson
(inventing an unverified output field name is exactly the mistake those
rules exist to prevent), this task implements fallback path (b):
`actions/create-github-app-token`, referencing two repo secrets
(`REVIEWER_GITHUB_APP_ID`, `REVIEWER_GITHUB_APP_PRIVATE_KEY`) that do NOT
exist yet -- new Manual Setup beyond spec.md's original scope, flagged back
to the project owner per ADR 0007 Consequences.

This task only obtains the identity/token -- it does NOT add T113's
verdict-parsing or `gh pr review` posting logic, and does NOT wire this
step's output into anything yet.

These are plain text/regex assertions against the raw workflow file,
deliberately not a full YAML parse -- mirroring
`tests/unit/test_reviewer_agent_fetch_pr_diff.py`'s (issue #145) same
rationale: this project has no PyYAML dependency declared.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "claude-agents-pipeline.yml"

NEW_APP_ID_SECRET = "REVIEWER_GITHUB_APP_ID"
NEW_PRIVATE_KEY_SECRET = "REVIEWER_GITHUB_APP_PRIVATE_KEY"


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


def _identity_step_block() -> str:
    job_block = _reviewer_agent_job_block()
    match = re.search(
        r"^      - name: Obtain non-default GitHub identity for posting the review\n"
        r"(.*?)(?=^      - name:|\Z)",
        job_block,
        re.M | re.S,
    )
    assert match, "no `Obtain non-default GitHub identity for posting the review` step found"
    return match.group(1)


def test_reviewer_agent_has_identity_step():
    job_block = _reviewer_agent_job_block()
    assert re.search(
        r"^      - name: Obtain non-default GitHub identity for posting the review\s*$",
        job_block,
        re.M,
    ), "expected a step obtaining the non-default GitHub identity in reviewer-agent (T112)"


def test_identity_step_is_after_claude_code_action_step():
    # Verdict-posting (T113) logically happens after the agent has actually
    # produced its verdict -- the end of the job, after the
    # claude-code-action step, is the correct position (task's own
    # framing).
    job_block = _reviewer_agent_job_block()
    steps_block = _steps_block(job_block)
    claude_index = steps_block.find("- name: Run Claude Code (reviewer agent, unattended)")
    identity_index = steps_block.find(
        "- name: Obtain non-default GitHub identity for posting the review"
    )
    assert claude_index != -1, (
        "Run Claude Code (reviewer agent, unattended) step not found in reviewer-agent steps"
    )
    assert identity_index != -1, "identity step not found in reviewer-agent steps"
    assert claude_index < identity_index, (
        "the identity-acquisition step must come after the claude-code-action "
        "step -- verdict-posting (T113, which will consume this step's "
        "output) logically happens after the agent has run"
    )


def test_identity_step_is_last_step_in_reviewer_agent_job():
    # T113/T114/T115 are separate, not-yet-implemented tasks; nothing in
    # this task should add posting/parsing logic after this step.
    job_block = _reviewer_agent_job_block()
    steps_block = _steps_block(job_block)
    step_names = re.findall(r"^      - name: (.+)$", steps_block, re.M)
    assert step_names, "expected at least one named step in reviewer-agent"
    assert step_names[-1] == "Obtain non-default GitHub identity for posting the review", (
        "expected the identity-acquisition step to currently be the last "
        "step in reviewer-agent's job -- T113 (verdict parsing/posting) is "
        "explicitly out of scope for this task"
    )


def test_identity_step_uses_create_github_app_token_fallback():
    # Confirms the fallback path (b) from ADR 0007 Decision 1 was
    # implemented, not an invented claude-code-action output reference.
    step_block = _identity_step_block()
    assert re.search(r"uses:\s*actions/create-github-app-token@v\d+", step_block), (
        "expected the identity step to use the documented, standard "
        "actions/create-github-app-token marketplace action (ADR 0007 "
        "Decision 1's fallback path)"
    )


def test_identity_step_does_not_invent_a_claude_code_action_output_reference():
    # Guards against exactly the mistake this task's instructions warn
    # against: referencing an unverified claude-code-action output field
    # (e.g. steps.<id>.outputs.github-token) as if it were a confirmed
    # reuse mechanism.
    step_block = _identity_step_block()
    assert "claude-code-action" not in step_block
    assert "outputs.github-token" not in step_block
    assert "outputs.github_token" not in step_block


def test_identity_step_references_not_yet_provisioned_app_id_secret():
    step_block = _identity_step_block()
    assert f"secrets.{NEW_APP_ID_SECRET}" in step_block, (
        f"expected the identity step to reference secrets.{NEW_APP_ID_SECRET} "
        "(a new secret that must be flagged to the project owner as Manual "
        "Setup, per ADR 0007 Consequences)"
    )


def test_identity_step_references_not_yet_provisioned_private_key_secret():
    step_block = _identity_step_block()
    assert f"secrets.{NEW_PRIVATE_KEY_SECRET}" in step_block, (
        f"expected the identity step to reference secrets.{NEW_PRIVATE_KEY_SECRET} "
        "(a new secret that must be flagged to the project owner as Manual "
        "Setup, per ADR 0007 Consequences)"
    )


def test_identity_step_does_not_reference_existing_role_secrets():
    # This step's two new secrets must be distinct from the default
    # GITHUB_TOKEN and from the Anthropic API key secrets already
    # provisioned for developer/reviewer/qa (ADR 0007 Decision 1: those are
    # the wrong credential type for a GitHub API call).
    step_block = _identity_step_block()
    assert "ANTHROPIC_API_KEY_DEV" not in step_block
    assert "ANTHROPIC_API_KEY_REVIEWER" not in step_block
    assert "ANTHROPIC_API_KEY_QA" not in step_block
    assert "github.token" not in step_block


def test_identity_step_comment_flags_new_manual_setup_to_project_owner():
    # Per ADR 0007 Consequences, a dedicated GitHub App/PAT constitutes new
    # Manual Setup beyond spec.md's original scope and "must be raised back
    # to the project owner explicitly, not added silently as an
    # implementation detail". Assert the workflow's own comment actually
    # says so, near where the new secrets are introduced -- not just that
    # the secret names happen to appear.
    job_block = _reviewer_agent_job_block()
    # Search the wider job block (not just the step block, which excludes
    # leading comment lines under the same indent as the step body -- the
    # explanatory comment sits directly above the `- name:` line).
    manual_setup_match = re.search(
        r"MANUAL SETUP REQUIRED.*?(?=^      - name:)", job_block, re.M | re.S
    )
    assert manual_setup_match, (
        "expected an explicit 'MANUAL SETUP REQUIRED' comment ahead of the "
        "identity step, flagging the new secrets to the project owner per "
        "ADR 0007 Consequences"
    )
    manual_setup_comment = manual_setup_match.group(0)
    assert NEW_APP_ID_SECRET in manual_setup_comment
    assert NEW_PRIVATE_KEY_SECRET in manual_setup_comment
    assert re.search(r"project owner", manual_setup_comment, re.I)


def test_identity_step_honestly_documents_unconfirmed_reuse_path():
    # Guards against silently skipping the "confirm this reuse path exists
    # first" instruction -- the workflow's own comment must show the
    # reuse-path question was actually considered and found unconfirmed,
    # not just skipped straight to the fallback with no explanation.
    job_block = _reviewer_agent_job_block()
    preceding_comment_match = re.search(
        r"(?:^      #.*\n)+(?=^      - name: Obtain non-default GitHub identity)",
        job_block,
        re.M,
    )
    assert preceding_comment_match, (
        "expected an explanatory comment block directly above the identity "
        "step"
    )
    comment = preceding_comment_match.group(0)
    assert re.search(r"no evidence", comment, re.I), (
        "expected the comment to honestly state that no evidence of a "
        "confirmed claude-code-action token-reuse mechanism was found in "
        "this repo, rather than silently assuming the fallback without "
        "explanation"
    )


def test_identity_step_uses_continue_on_error_so_missing_secrets_dont_break_job():
    # Per the task: "make sure this step's absence-of-secrets doesn't
    # silently break anything else in this job that doesn't yet depend on
    # it". Since this step is currently the last step in an already-live
    # job (dispatches on every real PR per T106) and nothing downstream
    # consumes its output yet (T113 is separate, not part of this task),
    # an unguarded failure here would flip the whole job red for every real
    # PR reviewed from now on even though nothing is actually broken.
    step_block = _identity_step_block()
    assert re.search(r"^\s*continue-on-error:\s*true\s*$", step_block, re.M), (
        "expected `continue-on-error: true` on the identity step so a "
        "failure caused by the not-yet-provisioned secrets doesn't fail "
        "the overall reviewer-agent job before anything depends on this "
        "step's output"
    )


def test_reviewer_agent_job_unaffected_steps_still_present():
    # Guard against this task accidentally clobbering pre-existing steps.
    job_block = _reviewer_agent_job_block()
    assert re.search(r"^      - name: Checkout PR head\s*$", job_block, re.M)
    assert re.search(r"^      - name: Fetch PR diff\s*$", job_block, re.M)
    assert re.search(r"^      - name: Build prompt for reviewer\s*$", job_block, re.M)
    assert re.search(
        r"^      - name: Run Claude Code \(reviewer agent, unattended\)\s*$", job_block, re.M
    )


def test_dev_agent_and_qa_agent_jobs_unaffected_by_this_task():
    text = _workflow_text()
    assert re.search(r"^  dev-agent:\n", text, re.M)
    assert re.search(r"^  qa-agent:\n", text, re.M)
    qa_match = re.search(r"^  qa-agent:\n(.*?)\Z", text, re.M | re.S)
    assert qa_match
    assert re.search(r"^    if: false\s*$", qa_match.group(1), re.M), (
        "qa-agent's if: false placeholder (T104, wired for real in T116) "
        "must remain untouched by this task"
    )
