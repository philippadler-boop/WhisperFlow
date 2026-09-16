#!/usr/bin/env python3
"""Benchmark helper for `transcribe` runs (T025, extended by T028).

Two independent things this script does, both anchored to specific
success criteria in `specs/001-video-subtitle-generator/spec.md`:

1. **Timing** (``benchmark.py time VIDEO``): runs the real `transcribe`
   pipeline (`cli.pipeline.run_pipeline`) against a single video, times it
   with `time.perf_counter()`, and prints the elapsed time alongside the
   video's own duration -- the exact manual check
   `specs/001-video-subtitle-generator/quickstart.md`'s Scenario 8
   describes (``time whisperflow transcribe ...``), just scripted so it
   doesn't have to be redone by hand for every run. Anchors SC-002 (a
   10-minute-or-less video finishes within 5 minutes) and SC-006 (processing
   scales roughly proportionally, ~2x real time, up to the 2-hour maximum).

2. **Reference-corpus scoring** (``benchmark.py corpus MANIFEST``): given a
   small labeled corpus -- sample videos paired with their known-correct
   transcript text -- runs `transcribe` against each one and reports two
   *rough, automated* percentages:

   - **Transcript accuracy**: `1 - word_error_rate` between the
     known-correct reference text and the generated subtitle text,
     word-level, via a standard Levenshtein-distance WER calculation.
   - **Subtitle timing-sync**: the fraction of generated subtitle lines
     whose display duration is long enough for their text length at a
     plausible reading speed (`DEFAULT_MAX_READING_CPS`, in characters per
     second) -- a line that flashes by faster than a viewer could read it
     is a concrete, machine-checkable symptom of the timing feeling
     "out of sync," even without a ground-truth reference timestamp to
     compare against (the labeled corpus this script expects only supplies
     known-correct *text*, not hand-verified timings).

   These two numbers are printed alongside an explicit meets/MISSES verdict
   (`sc003_note()`/`sc004_note()`) against SC-003's >=90% accuracy target
   and SC-004's >=95% timing-sync target (`DEFAULT_SC003_MIN_ACCURACY`/
   `DEFAULT_SC004_MIN_SYNC_RATIO`, overridable via `--min-accuracy`/
   `--min-sync-ratio`) -- concrete data points for `qa`, **not** a
   certification of those criteria themselves. SC-003 is explicitly "judged
   by a reviewing user" and SC-004 "perceived by a viewer" in spec.md --
   both are human-judgment criteria by the spec's own design, not something
   a script can certify on its own. This script exists to give `qa` a
   concrete, reproducible number (and, with ``--strict``, a nonzero exit
   status) to anchor that human judgment against (Principle V: validation
   reports are `qa`-owned; this script informs that report, it does not
   replace it).

Usage::

    python scripts/benchmark.py time samples/ten-minutes.mp4 --no-review
    python scripts/benchmark.py corpus tests/fixtures/benchmark_corpus.json
    python scripts/benchmark.py corpus tests/fixtures/benchmark_corpus.json --strict

Run from the repository root, or with the project installed
(``pip install -e .``) -- see this module's `_bootstrap_src_path()` for the
fallback when it isn't.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _bootstrap_src_path() -> None:
    """Make `src`'s top-level packages importable when run without install.

    Mirrors `scripts/build-windows-msi.ps1`'s own `--paths src` for
    PyInstaller: this script is meant to work equally well after a normal
    ``pip install -e .`` (which already puts `src` on `sys.path` via the
    editable install's `.pth`/import hook) and when invoked directly from a
    repo checkout with nothing installed at all, e.g. ``python
    scripts/benchmark.py ...`` right after cloning.
    """
    src_dir = Path(__file__).resolve().parent.parent / "src"
    if src_dir.is_dir() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_bootstrap_src_path()

from cli.pipeline import run_pipeline  # noqa: E402
from lib.errors import WhisperFlowError  # noqa: E402
from subtitles.models import SubtitleFile, SubtitleLine  # noqa: E402
from transcription.transcribe import DEFAULT_MODEL_SIZE  # noqa: E402

#: Plausible maximum reading speed, in characters per second, used as the
#: `subtitle_timing_sync_ratio()` proxy threshold -- widely-cited subtitle
#: style guides (e.g. Netflix's own timed-text guidelines) treat ~17-20
#: characters/second as the upper bound for a line an average viewer can
#: read before it disappears. A line whose text is longer than this rate
#: allows for its own displayed duration is flagged as "out of sync": not
#: because its timestamps are provably wrong against some ground truth
#: (this script has none), but because a viewer could not have actually
#: read it in the time it was on screen, which is itself a concrete,
#: automatable proxy correlated with SC-004's "no noticeable lag or lead."
DEFAULT_MAX_READING_CPS = 20.0

#: SC-003's own threshold: "At least 90% of generated subtitle lines... are
#: judged by a reviewing user to accurately reflect what was actually said."
#: `sc003_note()` compares `CorpusBenchmarkResult.overall_accuracy` against
#: this so the printed report gives `qa` an explicit met/missed verdict for
#: this automated proxy, mirroring `sc002_sc006_note()`'s own met/OUTSIDE
#: wording for SC-002/SC-006 -- not a certification of SC-003 itself, which
#: (per spec.md) is a human-judgment criterion this script can only anchor.
DEFAULT_SC003_MIN_ACCURACY = 0.90

#: SC-004's own threshold: "At least 95% of generated subtitle lines are
#: perceived by a viewer as in sync with the spoken audio." `sc004_note()`
#: compares `CorpusBenchmarkResult.overall_sync_ratio` against this, same
#: caveat as `DEFAULT_SC003_MIN_ACCURACY` above.
DEFAULT_SC004_MIN_SYNC_RATIO = 0.95

_WORD_RE = re.compile(r"[\w']+")


# ---------------------------------------------------------------------------
# Timing (SC-002 / SC-006, quickstart.md Scenario 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimingResult:
    """The outcome of timing one `transcribe` run against one video."""

    video_path: Path
    output_path: Path
    model_size: str
    video_duration_seconds: float
    elapsed_seconds: float

    @property
    def realtime_ratio(self) -> float:
        """`elapsed_seconds / video_duration_seconds` -- 1.0 is real time,
        0.5 matches SC-002/SC-006's "~1 minute of processing per 2 minutes
        of video" target."""
        if self.video_duration_seconds <= 0:
            return float("nan")
        return self.elapsed_seconds / self.video_duration_seconds


def time_transcription(
    video_path: Path | str,
    *,
    output_path: Path | str | None = None,
    model_size: str = DEFAULT_MODEL_SIZE,
    stream: Any = None,
) -> TimingResult:
    """Run the real pipeline against `video_path` and time it.

    Args:
        video_path: The input video to transcribe.
        output_path: Where to write the resulting `.srt` file. Defaults to
            `<video_basename>.srt` next to the input video, matching
            `cli.main`'s own default (contracts/cli.md).
        model_size: `faster-whisper` model size (contracts/cli.md's
            `--model`).
        stream: Where `run_pipeline`'s stage/progress announcements go
            (defaults to `sys.stderr` inside `run_pipeline` itself when
            `None`).

    Returns:
        A `TimingResult` with the elapsed wall-clock time and the video's
        own probed duration (read back from the written `SubtitleFile`'s
        `source_video`, so this doesn't need a second, separate probe
        call).

    Raises:
        lib.errors.WhisperFlowError: propagated unmodified from
            `run_pipeline` -- an unsupported/oversized video, missing
            `ffmpeg`, or a failed model load/transcription.
    """
    resolved_video_path = Path(video_path)
    resolved_output_path = (
        Path(output_path) if output_path is not None else resolved_video_path.with_suffix(".srt")
    )

    start = time.perf_counter()
    subtitle_file = run_pipeline(
        video_path=resolved_video_path,
        output_path=resolved_output_path,
        model_size=model_size,
        stream=stream,
    )
    elapsed_seconds = time.perf_counter() - start

    video = subtitle_file.source_video
    duration_seconds = float(video.duration_seconds) if video is not None else float("nan")

    return TimingResult(
        video_path=resolved_video_path,
        output_path=resolved_output_path,
        model_size=model_size,
        video_duration_seconds=duration_seconds,
        elapsed_seconds=elapsed_seconds,
    )


def format_seconds(seconds: float) -> str:
    """Render a duration in seconds as e.g. ``12.3s`` -- ``nan`` renders as
    ``unknown`` rather than the literal string ``"nan"``."""
    if seconds != seconds:  # noqa: PLR0124 -- the standard nan self-inequality check
        return "unknown"
    return f"{seconds:.1f}s"


def sc002_sc006_note(duration_seconds: float, elapsed_seconds: float) -> str:
    """A one-line note on SC-002/SC-006's ~2x-real-time processing target.

    SC-002 states a hard 5-minute cap for a <=10-minute video; SC-006
    generalizes that to "roughly proportional... about 1 minute of
    processing per 2 minutes of video" up to the 2-hour maximum. This
    reduces both to the same underlying ratio -- processing time no more
    than half the video's own duration -- and reports whether this run met
    it. It is a rough generalization of two criteria that spec.md only
    pins down exactly at two specific video lengths (10 minutes, 2 hours);
    treat this note as directional, not as SC-002/SC-006's own official
    pass/fail check at those exact lengths.
    """
    if duration_seconds != duration_seconds or duration_seconds <= 0:  # nan or zero
        return "SC-002/SC-006 target: could not be evaluated (unknown video duration)."
    target_seconds = duration_seconds / 2.0
    met = elapsed_seconds <= target_seconds
    verdict = "within" if met else "OUTSIDE"
    return (
        f"SC-002/SC-006 target (~2x real time, i.e. processing <= half the "
        f"video's duration): {verdict} target "
        f"({format_seconds(elapsed_seconds)} elapsed vs. "
        f"{format_seconds(target_seconds)} target)."
    )


def _percent_target_note(
    *,
    sc_label: str,
    metric_name: str,
    ratio: float,
    min_ratio: float,
) -> str:
    """Shared wording for a "met/OUTSIDE target" note against a min-ratio
    threshold (SC-003/SC-004's own `_ratio >= min_ratio` shape) -- an
    unevaluable (`nan`, e.g. an empty corpus) ratio is reported as such
    rather than as a false pass or fail."""
    if ratio != ratio:  # noqa: PLR0124 -- nan self-inequality check
        return f"{sc_label} target: could not be evaluated (empty corpus)."
    met = ratio >= min_ratio
    verdict = "meets" if met else "MISSES"
    return (
        f"{sc_label} target (>= {min_ratio:.0%} {metric_name}): {verdict} target "
        f"({ratio:.1%} measured vs. {min_ratio:.0%} target)."
    )


def sc003_note(overall_accuracy: float, *, min_accuracy: float = DEFAULT_SC003_MIN_ACCURACY) -> str:
    """A one-line "meets/MISSES" verdict for SC-003's >=90% accuracy target,
    given a `CorpusBenchmarkResult.overall_accuracy` value.

    This is the automated proxy's own verdict, not SC-003 itself -- SC-003
    is spec.md's human-judgment criterion ("judged by a reviewing user");
    see this module's docstring and `run_corpus_benchmark()`.
    """
    return _percent_target_note(
        sc_label="SC-003",
        metric_name="transcript accuracy",
        ratio=overall_accuracy,
        min_ratio=min_accuracy,
    )


def sc004_note(
    overall_sync_ratio: float, *, min_sync_ratio: float = DEFAULT_SC004_MIN_SYNC_RATIO
) -> str:
    """A one-line "meets/MISSES" verdict for SC-004's >=95% timing-sync
    target, given a `CorpusBenchmarkResult.overall_sync_ratio` value.

    Same caveat as `sc003_note()`: this is the automated timing-sync
    proxy's own verdict, not a certification of SC-004 itself.
    """
    return _percent_target_note(
        sc_label="SC-004",
        metric_name="timing-sync",
        ratio=overall_sync_ratio,
        min_ratio=min_sync_ratio,
    )


# ---------------------------------------------------------------------------
# Transcript accuracy (SC-003 anchor)
# ---------------------------------------------------------------------------


def _normalize_words(text: str) -> list[str]:
    """Lowercase, punctuation-stripped word tokens for WER comparison."""
    return _WORD_RE.findall(text.lower())


def _levenshtein_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    """Standard word-level edit distance (insertions/deletions/substitutions)."""
    previous_row = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, start=1):
        current_row = [i]
        for j, hyp_word in enumerate(hypothesis, start=1):
            if ref_word == hyp_word:
                current_row.append(previous_row[j - 1])
            else:
                current_row.append(
                    1 + min(previous_row[j], current_row[j - 1], previous_row[j - 1])
                )
        previous_row = current_row
    return previous_row[-1]


def word_error_rate(reference_text: str, hypothesis_text: str) -> float:
    """The standard ASR word-error-rate metric: edit distance / reference length.

    Both texts are normalized (lowercased, punctuation stripped) before
    comparison so formatting differences alone (casing, trailing periods)
    don't get counted as transcription errors.

    An empty reference is a degenerate case handled explicitly: `0.0` if
    the hypothesis is also empty (nothing to transcribe, nothing produced --
    a match), `1.0` (maximum error) if the hypothesis produced any text
    the reference doesn't account for at all.
    """
    reference_words = _normalize_words(reference_text)
    hypothesis_words = _normalize_words(hypothesis_text)
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    distance = _levenshtein_distance(reference_words, hypothesis_words)
    return distance / len(reference_words)


def transcript_accuracy(reference_text: str, hypothesis_text: str) -> float:
    """`1 - word_error_rate`, clamped to `[0.0, 1.0]` (SC-003's own metric shape).

    A hypothesis with more insertion errors than the reference has words
    can push the raw WER above 1.0; clamped here so the reported accuracy
    never reads as a nonsensical negative percentage.
    """
    return max(0.0, 1.0 - word_error_rate(reference_text, hypothesis_text))


# ---------------------------------------------------------------------------
# Subtitle timing-sync (SC-004 anchor)
# ---------------------------------------------------------------------------


def _line_is_in_sync(line: SubtitleLine, max_reading_cps: float) -> bool:
    """Whether one line's display duration is enough to read its text.

    Empty text is trivially in sync (nothing to read); a non-positive
    duration is never in sync (a line that isn't displayed long enough to
    even register can't be "in sync" with anything, regardless of text
    length) -- though `SubtitleLine.__post_init__` already guarantees
    `end_seconds >= start_seconds`, so this only excludes the boundary
    case of a zero-length line with non-empty text.
    """
    duration = line.end_seconds - line.start_seconds
    text_length = len(line.text.strip())
    if text_length == 0:
        return True
    if duration <= 0:
        return False
    return (text_length / duration) <= max_reading_cps


def _count_in_sync_lines(
    subtitle_file: SubtitleFile, max_reading_cps: float
) -> tuple[int, int]:
    """`(in_sync_count, total_line_count)` for `subtitle_file.lines`."""
    lines = subtitle_file.lines
    in_sync = sum(1 for line in lines if _line_is_in_sync(line, max_reading_cps))
    return in_sync, len(lines)


def subtitle_timing_sync_ratio(
    subtitle_file: SubtitleFile,
    *,
    max_reading_cps: float = DEFAULT_MAX_READING_CPS,
) -> float:
    """Fraction of `subtitle_file.lines` judged "in sync" (see `_line_is_in_sync`).

    A `SubtitleFile` with no lines at all (FR-008's valid "no detectable
    speech" outcome) reports `1.0` -- vacuously, there are no
    out-of-sync lines to find.
    """
    in_sync, total = _count_in_sync_lines(subtitle_file, max_reading_cps)
    return 1.0 if total == 0 else in_sync / total


# ---------------------------------------------------------------------------
# Reference corpus
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusEntry:
    """One labeled `(video, known-correct transcript text)` corpus pair."""

    label: str
    video_path: Path
    reference_text: str


def _resolve_relative(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else base_dir / candidate


def load_corpus(manifest_path: Path | str) -> list[CorpusEntry]:
    """Load a JSON corpus manifest into a list of `CorpusEntry`.

    The manifest is a JSON list of objects, each with:

    - ``"video"`` (required): path to the sample video, resolved relative
      to the manifest file's own directory (so a manifest and its videos
      can be shipped and moved together as a unit) unless already absolute.
    - ``"reference_text"`` **or** ``"reference_text_path"`` (exactly one
      required): the known-correct transcript text, either inline or as a
      path (resolved the same way as ``"video"``) to a plain-text file
      containing it.
    - ``"label"`` (optional): a human-readable name for reports; defaults
      to the video's own filename.

    Example::

        [
          {"video": "clear_speech.mp4", "reference_text": "Hello there."},
          {"video": "longer_clip.mp4", "reference_text_path": "longer_clip.txt"}
        ]

    Raises:
        ValueError: the manifest isn't a JSON list, an entry is missing
            ``"video"`` or both reference-text keys, or an entry's
            ``"video"``, ``"reference_text"``, ``"reference_text_path"``, or
            ``"label"`` value is present but not a JSON string.
    """
    manifest_path = Path(manifest_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(
            f"benchmark corpus manifest '{manifest_path}' must be a JSON list of "
            f"entries, got {type(raw).__name__}"
        )

    base_dir = manifest_path.resolve().parent
    entries: list[CorpusEntry] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or "video" not in item:
            raise ValueError(
                f"corpus entry {index} in '{manifest_path}' is missing the required "
                "'video' key"
            )
        if not isinstance(item["video"], str):
            raise ValueError(
                f"corpus entry {index} in '{manifest_path}' has a 'video' value "
                f"that isn't a string, got {type(item['video']).__name__}"
            )
        video_path = _resolve_relative(base_dir, item["video"])

        if "reference_text" in item:
            if not isinstance(item["reference_text"], str):
                raise ValueError(
                    f"corpus entry {index} ({item['video']!r}) in '{manifest_path}' has "
                    "a 'reference_text' value that isn't a string, got "
                    f"{type(item['reference_text']).__name__}"
                )
            reference_text = item["reference_text"]
        elif "reference_text_path" in item:
            if not isinstance(item["reference_text_path"], str):
                raise ValueError(
                    f"corpus entry {index} ({item['video']!r}) in '{manifest_path}' has "
                    "a 'reference_text_path' value that isn't a string, got "
                    f"{type(item['reference_text_path']).__name__}"
                )
            reference_text = _resolve_relative(base_dir, item["reference_text_path"]).read_text(
                encoding="utf-8"
            )
        else:
            raise ValueError(
                f"corpus entry {index} ({item['video']!r}) in '{manifest_path}' must "
                "have either 'reference_text' or 'reference_text_path'"
            )

        if "label" in item and item["label"] is not None and not isinstance(item["label"], str):
            raise ValueError(
                f"corpus entry {index} ({item['video']!r}) in '{manifest_path}' has a "
                f"'label' value that isn't a string, got {type(item['label']).__name__}"
            )
        label = item.get("label") or video_path.name
        entries.append(
            CorpusEntry(label=label, video_path=video_path, reference_text=reference_text)
        )
    return entries


@dataclass(frozen=True)
class CorpusEntryResult:
    """Per-video accuracy/sync scoring for one `CorpusEntry`."""

    label: str
    accuracy: float
    sync_ratio: float
    line_count: int
    in_sync_count: int


@dataclass(frozen=True)
class CorpusBenchmarkResult:
    """Aggregate accuracy/sync results across an entire reference corpus."""

    entries: list[CorpusEntryResult] = field(default_factory=list)

    @property
    def overall_accuracy(self) -> float:
        """Unweighted average of each entry's own (already-normalized)
        transcript accuracy -- each video contributes equally regardless
        of its own reference length."""
        if not self.entries:
            return float("nan")
        return sum(entry.accuracy for entry in self.entries) / len(self.entries)

    @property
    def overall_sync_ratio(self) -> float:
        """In-sync lines pooled across every entry, divided by the total
        line count across the whole corpus -- weighted by how many
        subtitle lines each video actually produced, rather than by video
        count.

        `nan` when the corpus produced zero subtitle lines in total,
        mirroring `overall_accuracy`'s `nan` for the analogous no-data case
        -- this isn't only reached by an empty manifest, but by any corpus
        where every entry happened to produce zero lines (e.g. all-silence
        videos, or a transcription bug producing empty output), and there
        is no line data at all to judge sync on in that case. Returning a
        vacuous `1.0` there would make `sc004_note()` print a false "meets
        target" verdict for a genuinely unevaluable corpus.
        """
        total_lines = sum(entry.line_count for entry in self.entries)
        if total_lines == 0:
            return float("nan")
        total_in_sync = sum(entry.in_sync_count for entry in self.entries)
        return total_in_sync / total_lines


def run_corpus_benchmark(
    entries: list[CorpusEntry],
    *,
    model_size: str = DEFAULT_MODEL_SIZE,
    max_reading_cps: float = DEFAULT_MAX_READING_CPS,
    stream: Any = None,
) -> CorpusBenchmarkResult:
    """Transcribe every `CorpusEntry` and score it against its reference text.

    Each video is transcribed via the real pipeline (`run_pipeline`) into a
    fresh temporary output path (never overwriting anything next to the
    corpus's own sample videos), then scored with `transcript_accuracy()`
    and `subtitle_timing_sync_ratio()`.

    Raises:
        lib.errors.WhisperFlowError: propagated unmodified from
            `run_pipeline` for any entry -- an unsupported/oversized video,
            missing `ffmpeg`, or a failed model load/transcription. A
            single bad entry aborts the whole corpus run rather than
            silently skipping it, so a broken reference video can't produce
            a falsely-inflated aggregate score.
    """
    results: list[CorpusEntryResult] = []
    with tempfile.TemporaryDirectory(prefix="whisperflow-benchmark-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        for index, entry in enumerate(entries):
            output_path = tmp_dir / f"{index:03d}_{entry.video_path.stem}.srt"
            subtitle_file = run_pipeline(
                video_path=entry.video_path,
                output_path=output_path,
                model_size=model_size,
                stream=stream,
            )
            hypothesis_text = " ".join(line.text for line in subtitle_file.lines)
            accuracy = transcript_accuracy(entry.reference_text, hypothesis_text)
            in_sync_count, line_count = _count_in_sync_lines(subtitle_file, max_reading_cps)
            sync_ratio = 1.0 if line_count == 0 else in_sync_count / line_count
            results.append(
                CorpusEntryResult(
                    label=entry.label,
                    accuracy=accuracy,
                    sync_ratio=sync_ratio,
                    line_count=line_count,
                    in_sync_count=in_sync_count,
                )
            )
    return CorpusBenchmarkResult(entries=results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_MODEL_CHOICES = ("tiny", "base", "small", "medium", "large")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark.py",
        description=(
            "Time a transcribe run (SC-002/SC-006), or score rough transcript "
            "accuracy/timing-sync against a labeled reference corpus "
            "(SC-003/SC-004 anchors)."
        ),
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    time_parser = subparsers.add_parser(
        "time", help="Time a single transcribe run against one video."
    )
    time_parser.add_argument("video", type=Path, help="Path to the input video.")
    time_parser.add_argument(
        "--output", "-o", type=Path, default=None, help="Where to write the .srt file."
    )
    time_parser.add_argument(
        "--model", choices=_MODEL_CHOICES, default=DEFAULT_MODEL_SIZE,
        help=f"faster-whisper model size (default: {DEFAULT_MODEL_SIZE}).",
    )

    corpus_parser = subparsers.add_parser(
        "corpus",
        help="Score rough transcript-accuracy/timing-sync against a labeled reference corpus.",
    )
    corpus_parser.add_argument(
        "manifest", type=Path, help="Path to a JSON reference-corpus manifest."
    )
    corpus_parser.add_argument(
        "--model", choices=_MODEL_CHOICES, default=DEFAULT_MODEL_SIZE,
        help=f"faster-whisper model size (default: {DEFAULT_MODEL_SIZE}).",
    )
    corpus_parser.add_argument(
        "--max-reading-cps", type=float, default=DEFAULT_MAX_READING_CPS,
        help=(
            "Maximum plausible reading speed in characters/second, used by the "
            f"timing-sync proxy (default: {DEFAULT_MAX_READING_CPS})."
        ),
    )
    corpus_parser.add_argument(
        "--min-accuracy", type=float, default=DEFAULT_SC003_MIN_ACCURACY,
        help=(
            "SC-003's minimum overall transcript-accuracy target, as a fraction "
            f"(default: {DEFAULT_SC003_MIN_ACCURACY})."
        ),
    )
    corpus_parser.add_argument(
        "--min-sync-ratio", type=float, default=DEFAULT_SC004_MIN_SYNC_RATIO,
        help=(
            "SC-004's minimum overall timing-sync target, as a fraction "
            f"(default: {DEFAULT_SC004_MIN_SYNC_RATIO})."
        ),
    )
    corpus_parser.add_argument(
        "--strict", action="store_true",
        help=(
            "Exit with status 3 if the corpus's overall accuracy/timing-sync "
            "fall short of --min-accuracy/--min-sync-ratio, instead of just "
            "reporting the numbers. Status 3 is distinct from argparse's own "
            "status 2 for usage errors (e.g. a missing argument or an invalid "
            "--model choice), so a CI script branching on exit code can tell "
            "'invoked incorrectly' apart from 'corpus missed its target'."
        ),
    )

    return parser


def _print_timing_report(result: TimingResult, out: Any) -> None:
    print(f"Video: {result.video_path}", file=out)
    print(f"Model: {result.model_size}", file=out)
    print(f"Video duration: {format_seconds(result.video_duration_seconds)}", file=out)
    print(f"Elapsed: {format_seconds(result.elapsed_seconds)}", file=out)
    print(f"Realtime ratio (elapsed / video duration): {result.realtime_ratio:.3f}", file=out)
    print(f"Output written to: {result.output_path}", file=out)
    print(sc002_sc006_note(result.video_duration_seconds, result.elapsed_seconds), file=out)


def _print_corpus_report(
    result: CorpusBenchmarkResult,
    out: Any,
    *,
    min_accuracy: float = DEFAULT_SC003_MIN_ACCURACY,
    min_sync_ratio: float = DEFAULT_SC004_MIN_SYNC_RATIO,
) -> bool:
    """Print the corpus report and return whether both SC-003/SC-004
    targets were met (`nan`, i.e. an empty corpus, counts as "not met" here
    -- there's no data to certify a pass on)."""
    print("Reference-corpus benchmark (rough automated proxy -- see script docstring)", file=out)
    for entry in result.entries:
        print(
            f"  {entry.label}: accuracy={entry.accuracy:.1%} "
            f"({entry.line_count} lines); "
            f"timing-sync={entry.sync_ratio:.1%} "
            f"({entry.in_sync_count}/{entry.line_count} lines in sync)",
            file=out,
        )
    print(f"Overall transcript accuracy: {result.overall_accuracy:.1%}", file=out)
    print(f"Overall subtitle timing-sync: {result.overall_sync_ratio:.1%}", file=out)
    print(sc003_note(result.overall_accuracy, min_accuracy=min_accuracy), file=out)
    print(sc004_note(result.overall_sync_ratio, min_sync_ratio=min_sync_ratio), file=out)
    print(
        "Note: SC-003/SC-004 are spec.md's own human-judgment criteria -- these "
        "numbers and verdicts are a rough automated proxy for `qa` to anchor "
        "that judgment against, not a substitute for it.",
        file=out,
    )
    accuracy_met = (
        result.overall_accuracy == result.overall_accuracy  # not nan
        and result.overall_accuracy >= min_accuracy
    )
    sync_met = (
        result.overall_sync_ratio == result.overall_sync_ratio  # not nan
        and result.overall_sync_ratio >= min_sync_ratio
    )
    return accuracy_met and sync_met


def main(argv: list[str] | None = None) -> int:
    """Run the `time` or `corpus` subcommand and return a process exit code.

    Exit codes:

    - ``0``: success.
    - ``1``: a domain error (`lib.errors.WhisperFlowError`) or an I/O/manifest
      error (`OSError`/`ValueError`) was raised and reported to stderr.
    - ``2``: argparse's own usage-error status (missing/invalid arguments,
      e.g. an unrecognized ``--model`` choice) -- raised via `SystemExit`
      from inside `argparse.ArgumentParser.parse_args`, not returned from
      here.
    - ``3``: ``corpus --strict`` ran successfully but the corpus's overall
      accuracy/timing-sync missed ``--min-accuracy``/``--min-sync-ratio``.
      Deliberately distinct from argparse's own ``2`` above so a CI script
      branching on exit code can tell "invoked incorrectly" apart from
      "corpus missed its target."
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.mode == "time":
            result = time_transcription(
                args.video, output_path=args.output, model_size=args.model
            )
            _print_timing_report(result, sys.stdout)
        elif args.mode == "corpus":
            entries = load_corpus(args.manifest)
            corpus_result = run_corpus_benchmark(
                entries, model_size=args.model, max_reading_cps=args.max_reading_cps
            )
            targets_met = _print_corpus_report(
                corpus_result,
                sys.stdout,
                min_accuracy=args.min_accuracy,
                min_sync_ratio=args.min_sync_ratio,
            )
            if args.strict and not targets_met:
                return 3
    except WhisperFlowError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
