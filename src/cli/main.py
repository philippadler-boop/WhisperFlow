"""WhisperFlow CLI entrypoint (T007, T014).

Implements the argument/option surface of the single user-facing command,
``whisperflow transcribe VIDEO_PATH [OPTIONS]``, exactly as documented in
``specs/001-video-subtitle-generator/contracts/cli.md`` (spec FR-005).

``_run_pipeline`` wires the ``--no-review`` command path to T013's real
orchestration (``cli.pipeline.run_pipeline``): probe -> extract ->
transcribe -> write. ``--review`` (the default) is not implemented yet --
that's T020/T021's job (the interactive review step and its branching) --
so it still raises ``NotImplementedError`` for now. Every domain error
T013's stages can raise (``lib.errors.WhisperFlowError`` and its
subclasses -- unsupported video format, oversized video, missing
``ffmpeg``/``ffprobe``, or a failed ASR model load/transcription) is
caught exactly once here, at the top level, and reported as contracts/
cli.md's Exit codes section requires: a single ``Error: ...`` line on
stderr, exit code 1 (spec FR-007).
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import typer

from cli import pipeline
from lib.errors import WhisperFlowError

# ruff: noqa: E501
BANNER = r""" __          ___     _                     ______ _
\ \        / / |   (_)                   |  ____| |
 \ \  /\  / /| |__  _ ___ _ __   ___ _ __| |__  | | _____      __
  \ \/  \/ / | '_ \| / __| '_ \ / _ \ '__|  __| | |/ _ \ \ /\ / /
    \  /\  /  | | | | \__ \ |_) |  __/ |  | |    | | (_) \ V  V /
     \/  \/   |_| |_|_|___/ .__/ \___|_|  |_|    |_|\___/ \_/\_/
                                 | |
                                 |_|"""
HELP_BANNER = BANNER.replace("\n", "\n\n")

app = typer.Typer(
    name="whisperflow",
    help=f"{HELP_BANNER}\n\nGenerate time-synced .srt subtitles from a video's spoken audio.",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"max_content_width": 220},
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
    """Dispatch to T013's real pipeline for the ``--no-review`` path (T014).

    ``--review`` (``review=True``, the contract default) still has no
    implementation to dispatch to -- T020 (the interactive review flow) and
    T021 (wiring it in here) haven't landed yet -- so it keeps failing
    loudly with ``NotImplementedError`` rather than silently skipping the
    review step it was asked for. ``editor`` is accordingly unused until
    then; it's already threaded through so T021 only has to change this
    function's body, not its (or ``transcribe``'s) signature.
    """
    if review:
        raise NotImplementedError(
            "whisperflow transcribe --review: pipeline not yet implemented (see T020/T021)"
        )
    pipeline.run_pipeline(
        video_path=video_path,
        output_path=output_path,
        model_size=model.value,
    )


@app.command(
    help=f"{HELP_BANNER}\n\nTranscribe VIDEO_PATH's spoken audio into a time-synced .srt file."
)
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
    resolved_output = output if output is not None else _default_output_path(video_path)
    resolved_editor = editor if editor is not None else _default_editor()

    try:
        _run_pipeline(
            video_path=video_path,
            output_path=resolved_output,
            model=model,
            review=review,
            editor=resolved_editor,
        )
    except WhisperFlowError as exc:
        # contracts/cli.md's Exit codes section: every FR-007 fatal error
        # (unsupported/corrupt format, oversized video, missing ffmpeg, a
        # failed ASR model load) is reported as a single human-readable
        # stderr line, exit code 1 -- caught exactly once, here, regardless
        # of which pipeline stage (T009-T012, via T013) actually raised it.
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
