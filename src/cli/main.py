"""WhisperFlow CLI entrypoint (T007).

Implements the argument/option surface of the single user-facing command,
``whisperflow transcribe VIDEO_PATH [OPTIONS]``, exactly as documented in
``specs/001-video-subtitle-generator/contracts/cli.md`` (spec FR-005).

This module is a *skeleton*: option parsing, defaulting, and validation
are fully wired up, but the actual pipeline (probe -> extract -> transcribe
-> write -> optional review) is not implemented yet. Once parsed, the
resolved options are handed to ``_run_pipeline``, a placeholder that a
later task (T013/T014, ``src/cli/pipeline.py``) will replace with the real
orchestration call.
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import typer

app = typer.Typer(
    name="whisperflow",
    help="Generate time-synced .srt subtitles from a video's spoken audio.",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """WhisperFlow: local, CLI-only video-to-subtitle transcription.

    Registering this (otherwise no-op) callback keeps ``transcribe`` a
    required subcommand name (``whisperflow transcribe VIDEO_PATH
    [OPTIONS]``, per contracts/cli.md) instead of Typer's single-command
    auto-flattening, which would otherwise let it be invoked as
    ``whisperflow VIDEO_PATH`` directly.
    """


class ModelSize(StrEnum):
    """Supported ``faster-whisper`` model sizes (contracts/cli.md)."""

    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


def _default_editor() -> str | None:
    """Resolve the default editor per contracts/cli.md's ``--editor`` row.

    Falls back to ``$EDITOR``, then ``$VISUAL``; ``None`` if neither is
    set, letting the (not-yet-implemented) review step fall back to its
    own built-in prompt.
    """
    return os.environ.get("EDITOR") or os.environ.get("VISUAL") or None


def _default_output_path(video_path: Path) -> Path:
    """``<video_basename>.srt`` next to the input video (contracts/cli.md)."""
    return video_path.with_suffix(".srt")


def _run_pipeline(
    *,
    video_path: Path,
    output_path: Path,
    model: ModelSize,
    review: bool,
    editor: str | None,
) -> None:
    """Placeholder for the not-yet-implemented processing pipeline.

    T013 (``src/cli/pipeline.py``) implements the real probe -> extract ->
    transcribe -> write orchestration, and T014/T021 wire it in here in
    place of this stub. Until then, invoking ``transcribe`` fails loudly
    rather than silently doing nothing.
    """
    raise NotImplementedError(
        "whisperflow transcribe: pipeline not yet implemented (see T013/T014)"
    )


@app.command()
def transcribe(
    video_path: Path = typer.Argument(
        ...,
        help="Path to the input video file (FR-001).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Where to write the .srt file (FR-006). "
            "Defaults to <video_basename>.srt next to the input video."
        ),
    ),
    model: ModelSize = typer.Option(
        ModelSize.BASE,
        "--model",
        case_sensitive=False,
        help=(
            "faster-whisper model size — smaller is faster, "
            "larger is more accurate (research.md)."
        ),
    ),
    review: bool = typer.Option(
        True,
        "--review/--no-review",
        help=(
            "With --review, after generating a draft .srt the "
            "command opens it in $EDITOR (or --editor) and waits for "
            "confirmation before finalizing (FR-009, FR-010, User Story 2). "
            "--no-review finalizes immediately — for scripting/automation."
        ),
    ),
    editor: str | None = typer.Option(
        None,
        "--editor",
        help=(
            "Overrides which editor --review opens. Defaults to "
            "$EDITOR/$VISUAL, else a built-in fallback prompt."
        ),
    ),
) -> None:
    """Transcribe VIDEO_PATH's spoken audio into a time-synced .srt file."""
    resolved_output = output if output is not None else _default_output_path(video_path)
    resolved_editor = editor if editor is not None else _default_editor()

    _run_pipeline(
        video_path=video_path,
        output_path=resolved_output,
        model=model,
        review=review,
        editor=resolved_editor,
    )


if __name__ == "__main__":
    app()
