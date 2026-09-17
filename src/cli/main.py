"""WhisperFlow CLI entrypoint (T007, T014, T021).

Implements the argument/option surface of the single user-facing command,
``whisperflow transcribe VIDEO_PATH [OPTIONS]``, exactly as documented in
``specs/001-video-subtitle-generator/contracts/cli.md`` (spec FR-005).

``_run_pipeline`` wires both command paths to their real implementations:
``--no-review`` dispatches straight to T013's orchestration
(``cli.pipeline.run_pipeline``): probe -> extract -> transcribe -> write.
``--review`` (the contract default) runs that same pipeline first -- its
written ``.srt`` doubles as the draft -- and then hands the resulting
``SubtitleFile`` to T020's interactive review step
(``cli.review.review_subtitle_file``), which opens it in ``$EDITOR``/
``--editor``, blocks for confirmation, and returns a `SubtitleFile` with
any edited lines' text folded back in (FR-009, FR-010); this function
then writes that finalized `SubtitleFile` back to ``output_path`` so the
edits are reflected in the file left on disk. Every domain error either
path can raise (``lib.errors.WhisperFlowError`` and its subclasses --
unsupported video format, oversized video, missing ``ffmpeg``/``ffprobe``,
a failed ASR model load/transcription, or a failed/aborted review edit)
is caught exactly once here, at the top level, and reported as
contracts/cli.md's Exit codes section requires: a single ``Error: ...``
line on stderr, exit code 1 (spec FR-007).
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import typer
from rich.align import Align
from rich.console import Console
from rich.text import Text
from typer.core import TyperGroup

from cli import pipeline
from cli.review import review_subtitle_file
from lib.errors import SubtitleWriteError, WhisperFlowError

BANNER = """
██╗    ██╗██╗  ██╗██╗███████╗██████╗ ███████╗██████╗ ███████╗██╗      ██████╗ ██╗    ██╗
██║    ██║██║  ██║██║██╔════╝██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔═══██╗██║    ██║
██║ █╗ ██║███████║██║███████╗██████╔╝█████╗  ██████╔╝█████╗  ██║     ██║   ██║██║ █╗ ██║
██║███╗██║██╔══██║██║╚════██║██╔═══╝ ██╔══╝  ██╔══██╗██╔══╝  ██║     ██║   ██║██║███╗██║
╚███╔███╔╝██║  ██║██║███████║██║     ███████╗██║  ██║██║     ███████╗╚██████╔╝╚███╔███╔╝
 ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝
"""
TAGLINE = "Local video-to-subtitle transcription"
console = Console(highlight=False)


class BannerGroup(TyperGroup):
    """Render the WhisperFlow banner before root help."""

    def format_help(self, ctx, formatter) -> None:
        show_banner()
        super().format_help(ctx, formatter)


def show_banner() -> None:
    """Display the colored banner and tagline."""
    colors = ["bright_magenta", "magenta", "dark_orange", "gold3", "gold1", "bright_white"]
    styled_banner = Text()
    for line, color in zip(BANNER.strip("\n").splitlines(), colors, strict=False):
        styled_banner.append(line + "\n", style=color)
    styled_banner.no_wrap = True
    console.print(Align.center(styled_banner), overflow="ignore", crop=False)
    console.print(Align.center(Text(TAGLINE, style="italic bright_yellow")))
    console.print()


app = typer.Typer(
    name="whisperflow",
    help="Generate time-synced .srt subtitles from a video's spoken audio.",
    cls=BannerGroup,
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
    set, letting the review step (``cli.review.review_subtitle_file``)
    fall back to its own built-in prompt.
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
    """Dispatch to T013's pipeline, and T020's review step when requested (T021).

    Always runs T013's full probe -> extract -> transcribe -> write
    pipeline (``cli.pipeline.run_pipeline``) first: its written ``.srt`` is
    the finished output for ``--no-review``, and doubles as the draft
    ``--review`` opens for editing.

    When ``review`` is true (the contract default), the freshly written
    ``SubtitleFile`` is then handed to ``cli.review.review_subtitle_file``,
    which opens it in ``editor`` (already resolved from ``--editor``/
    ``$EDITOR``/``$VISUAL`` by ``transcribe``), blocks until the user
    confirms they're done, and returns a new ``SubtitleFile`` with any
    edited lines' text folded in (FR-009, FR-010). That finalized
    ``SubtitleFile`` is then written back to ``output_path`` so the file
    left on disk reflects the user's edits, not just the original draft.
    A failure writing that finalized file back (e.g. output directory
    permissions changed, disk full, mid-review) is reported the same way
    ``write_subtitles()`` reports T013's own initial write failure: wrapped
    as a ``SubtitleWriteError`` rather than left as a raw ``OSError``, so
    it's caught by ``transcribe``'s top-level ``WhisperFlowError`` handler
    instead of surfacing as an unhandled traceback.
    """
    subtitle_file = pipeline.run_pipeline(
        video_path=video_path,
        output_path=output_path,
        model_size=model.value,
    )
    if review:
        subtitle_file = review_subtitle_file(subtitle_file, editor=editor)
        try:
            subtitle_file.write()
        except OSError as exc:
            raise SubtitleWriteError(output_path, reason=str(exc)) from exc


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
        ModelSize.TINY,
        "--model",
        case_sensitive=False,
        help=(
            "faster-whisper model size — smaller is faster, "
            "larger is more accurate (research.md). Defaults to `tiny`: "
            "T029's benchmarking (contracts/cli.md's minimum-hardware note) "
            "found `base` misses the SC-002/SC-006 ~2x-real-time target on "
            "CPU-only reference hardware, while `tiny` meets it with margin "
            "to spare. Pick a larger size explicitly if your hardware has "
            "more headroom (e.g. a GPU) and you want higher accuracy."
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
