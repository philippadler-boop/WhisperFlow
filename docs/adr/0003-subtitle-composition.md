# 0003: Subtitle File Composition Library

> **Status**: Accepted — approved at the Design Gate (Principle II).
> Feature 001 (video-subtitle-generator) predates the branch-per-planning-
> phase process (Constitution Principle IV's documented one-time
> exception); this ADR was committed directly to `main` on 2026-09-04 as
> part of that grandfathered flow, and its decision was implicitly
> ratified by the feature's full implementation and release (T001-T029,
> all merged).

## Context

FR-006 requires the system to write generated subtitles to a file in a
standard subtitle format; per spec Assumptions, the default and initially
only output format for v1 is `.srt`. The data model's `SubtitleFile` /
`SubtitleLine` entities (index, start/end timestamps, text, `edited`
flag) need to be serialized into correctly formatted `.srt` text —
including index numbering and `HH:MM:SS,mmm`-style timestamp formatting —
without introducing subtle, hard-to-notice formatting bugs that would
undermine SC-004 (subtitle sync) or produce a file media players reject.

## Decision

Use the `srt` Python library (`pip install srt`) to compose in-memory
`Subtitle` objects (index, start, end, text) into the final `.srt` file
text via `srt.compose()`.

## Alternatives Considered

- **`pysrt`**: Comparable scope and maturity for reading/writing `.srt`
  files. `srt` was preferred for its simpler, more current
  `compose`/`parse` API surface and lighter footprint for the narrow
  compose-only use case v1 needs (v1 does not need to parse existing
  `.srt` files).
- **Hand-rolled `.srt` writer**: The `.srt` format itself is simple, but
  timestamp precision and sequential index-numbering are exactly the kind
  of small, easy-to-get-wrong string-formatting details a small,
  already-maintained library handles correctly; rejected in favor of not
  re-solving a solved problem.

## Consequences

- Adds one small, single-purpose third-party dependency (`srt`) scoped
  narrowly to the `src/subtitles/` module (Project Structure); it has no
  bearing on the ASR or audio-extraction dependency choices (ADRs 0001,
  0002).
- Because v1 only needs `compose()` (not `parse()`), the dependency's
  surface area actually used is small, limiting exposure to any future
  breaking API changes in the library.
- `SubtitleLine` → `srt.Subtitle` field mapping (data-model.md) is a
  direct 1:1 translation (`index`, `start_seconds`/`end_seconds` →
  `timedelta`, `text`), so unit tests for `src/subtitles/` (per Project
  Structure's `tests/unit/`) can assert on the library's own output
  rather than a custom formatter's.
- If a future version adds a second output format (e.g. `.vtt`, per spec
  Assumptions' "candidates for a later version"), this decision will need
  revisiting since `srt` is `.srt`-specific — that is an explicit,
  accepted v1 limitation, not an oversight.
