# 0002: Audio Extraction via ffmpeg Subprocess

> **Status**: Proposed — pending human approval at the Design Gate
> (Principle II). Not yet binding until sign-off.

## Context

FR-001 requires the system to accept a video file and extract its spoken
audio for processing. Per spec Assumptions, supported input formats span
common video containers (e.g. MP4, MOV, MKV), and the tool must run
cross-platform (Windows, macOS, Linux — Technical Context: Target
Platform). The chosen ASR engine (`faster-whisper`/CTranslate2 — see ADR
0001) expects audio in a specific shape (mono, 16kHz WAV). FR-007 also
requires that unsupported-format or over-length input produce a clear
error rather than a crash, which depends on getting predictable,
parseable failure output from whatever does the demuxing.

## Decision

Shell out to an external `ffmpeg` binary via Python's `subprocess` module
to extract a mono 16kHz WAV audio track from the input video, and to
probe container format/duration, before handing the audio to
`faster-whisper`.

## Alternatives Considered

- **`ffmpeg-python` / `pyav` Python bindings**: Offer a more Pythonic call
  site, but both sit on top of the same underlying `ffmpeg`/`libav`
  binary or libraries, adding another dependency layer without removing
  the external-binary requirement. Error messages surfaced through a
  binding layer are also less predictable to parse for FR-007's
  clear-error requirement than the wrapper's own subprocess handling.
- **Pure-Python demuxers**: No mature, actively maintained pure-Python
  library was found covering the breadth of container formats WhisperFlow
  must accept (MP4, MOV, MKV, ...); rejected as not viable.

## Consequences

- WhisperFlow now has a hard runtime dependency on an `ffmpeg` binary
  being present on the host `PATH` (Technical Context: Constraints).
  Installation/setup documentation and FR-007's error handling must cover
  the case where `ffmpeg` is missing or unresolvable, since this is a
  distinct failure mode from "unsupported video format."
- A thin, purpose-built subprocess wrapper module (`src/audio/`) owns
  invoking `ffmpeg`, parsing its stderr/exit code, and translating
  failures into the clear, non-crashing errors FR-007 requires — this
  wrapper is untested third-party surface area that needs its own unit
  tests (per Project Structure's `tests/unit/`).
- No compiled Python binding is added to the dependency tree, keeping the
  Python package installable via plain `pip` across all three target
  platforms; the trade-off is that CLI startup must verify `ffmpeg`'s
  presence/version explicitly rather than relying on `import` failing
  fast.
- The extraction step fixes audio to mono/16kHz specifically to match
  `faster-whisper`'s expected input shape (ADR 0001); if the ASR engine
  choice changes in the future, this extraction step's output format
  assumption should be re-reviewed.
