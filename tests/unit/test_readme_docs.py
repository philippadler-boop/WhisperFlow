"""Unit tests for T024 ("Document the `transcribe` command's usage in
`README.md`").

`tests/contract/test_cli_contract.py` (T008) is the source-of-truth check
that the *actual* `--help` surface matches
`specs/001-video-subtitle-generator/contracts/cli.md`. This file is the
analogous check for the *human-facing* documentation: it asserts
`README.md` actually documents the `transcribe` command's argument,
options (names, defaults, choice sets), exit codes, and worked examples
from `contracts/cli.md`, so a future change to the CLI surface or the
contract can't silently leave `README.md` stale.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


def _read_readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_documents_the_command_shape():
    text = _read_readme()
    assert "whisperflow transcribe VIDEO_PATH [OPTIONS]" in text


def test_readme_documents_the_video_path_argument():
    text = _read_readme()
    assert "VIDEO_PATH" in text
    assert "Path to the input video file" in text


def test_readme_documents_output_option():
    text = _read_readme()
    assert "--output" in text
    assert "-o" in text
    assert "<video_basename>.srt" in text


def test_readme_does_not_claim_output_directory_must_preexist():
    """Regression guard for the QA-caught inaccuracy on PR #125:
    `SubtitleFile.write()` (`src/subtitles/models.py`) calls
    `target.parent.mkdir(parents=True, exist_ok=True)` before writing, so
    the destination directory is created automatically -- it is not
    required to already exist. The README must not claim otherwise."""
    text = _read_readme()
    assert "directory must already exist" not in text
    assert "created automatically" in text


def test_readme_documents_model_option_and_all_contract_sizes():
    text = _read_readme()
    assert "--model" in text
    for size in ("tiny", "base", "small", "medium", "large"):
        assert size in text
    assert (
        "| `--model {tiny,base,small,medium,large}` | `tiny` |" in text
    )


def test_readme_documents_review_option_and_default():
    text = _read_readme()
    assert "--review" in text
    assert "--no-review" in text
    # `--review` is the contract default (contracts/cli.md).
    assert "is the default" in text


def test_readme_documents_editor_option():
    text = _read_readme()
    assert "--editor" in text
    assert "$EDITOR" in text
    assert "$VISUAL" in text


def test_readme_documents_review_workflow_behavior():
    """The review section should no longer say the workflow is unavailable
    (T020-T023 shipped it) -- guards against the README regressing back to
    its earlier "not yet available in this release" placeholder text."""
    text = _read_readme()
    assert "is not yet available in this release" not in text
    assert "waits for you to confirm" in text or "waits for confirmation" in text
    assert "fallback prompt" in text.lower() or "press Enter" in text


def test_readme_documents_exit_codes():
    text = _read_readme()
    assert "| `0` | Success" in text
    assert "| `1` | Fatal error" in text


def test_readme_includes_a_review_mode_example_with_blocking_editor_flag():
    # Mirrors quickstart.md Scenario 3's `--editor "code --wait"` example.
    text = _read_readme()
    assert "code --wait" in text


def test_readme_references_the_cli_contract_doc():
    text = _read_readme()
    assert "contracts/cli.md" in text


def test_readme_documents_why_tiny_is_the_default_model():
    """T029: the default `--model` changed from `base` to `tiny` after
    benchmarking found `base` misses the SC-002/SC-006 timing target on
    CPU-only reference hardware -- README should explain the rationale
    and point at contracts/cli.md's minimum-hardware note, not just state
    the bare default."""
    text = _read_readme()
    assert "minimum-hardware" in text
    assert "SC-002" in text or "SC-006" in text
