# Phase 0 Research: Video Subtitle Generator

Each unknown from the plan's Technical Context, resolved below as
Decision / Rationale / Alternatives Considered.

## Local ASR engine

**Decision**: `faster-whisper` (CTranslate2-based reimplementation of
OpenAI Whisper), CPU inference with int8 quantization by default, GPU
used automatically when available.

**Rationale**: FR-004 requires all transcription to run locally, and
SC-002/SC-006 require roughly 2x-real-time-or-better throughput on
typical consumer hardware. Public benchmarks show faster-whisper with
int8 quantization outperforming both stock OpenAI Whisper and
whisper.cpp's CPU path on equivalent hardware (e.g., ~1m42s vs
whisper.cpp's ~2m05s on the same clip/model, and further down to ~51s at
batch_size=8), while installing as a pure pip package that's simple to
wrap in a Python CLI. That throughput margin gives headroom to still meet
SC-002 on mid-range hardware even before considering GPU acceleration.

**Alternatives considered**:
- **whisper.cpp**: Faster on Apple Silicon via Metal/Core ML (~10x
  real-time on large-v3), and has first-class streaming support this
  feature doesn't need. Rejected as the default because it's a
  C/C++ project requiring bindings or a subprocess boundary from Python,
  adding packaging complexity for a v1 CLI tool, and its plain-CPU path
  is not clearly faster than faster-whisper's int8 path off Apple
  hardware.
- **Stock `openai-whisper`**: Reference implementation, simplest
  integration, but noticeably slower than both alternatives above with no
  quantization support — highest risk of missing SC-002/SC-006 on
  CPU-only machines.

Sources: [faster-whisper vs whisper.cpp with CoreML (GitHub discussion)](https://github.com/SYSTRAN/faster-whisper/discussions/368), [faster-whisper vs whisper.cpp vs OpenAI Whisper (2026)](https://codersera.com/blog/faster-whisper-vs-whisper-cpp-speech-to-text-2026/), [Whisper.cpp vs faster-whisper 2026: STT Speed Test](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026), [faster-whisper (PyPI)](https://pypi.org/project/faster-whisper/)

## Audio extraction from video

**Decision**: Shell out to an `ffmpeg` binary (via `subprocess`) to
extract a mono 16kHz WAV audio track from the input video before handing
it to `faster-whisper`.

**Rationale**: ffmpeg is the de facto standard for container/codec
demuxing across the wide range of video formats WhisperFlow must accept
(Assumptions: MP4, MOV, MKV, ...), is available on all three target
platforms, and `faster-whisper`/CTranslate2 already expect exactly this
audio shape. Shelling out avoids adding a compiled Python binding as a
dependency.

**Alternatives considered**:
- **`ffmpeg-python` / `pyav` bindings**: Slightly more Pythonic call
  sites, but add another dependency layer on top of the same underlying
  ffmpeg binary, with less predictable error messages for FR-007 (must
  clearly report unsupported-format errors). A thin, well-tested
  subprocess wrapper is simpler to reason about and test.
- **Pure-Python demuxers**: No mature, actively maintained pure-Python
  library covers the breadth of container formats required; rejected.

## Subtitle file composition

**Decision**: The `srt` Python library (`pip install srt`) to compose
`Subtitle` objects (index, start, end, text) into the final `.srt` file
text.

**Rationale**: Small, single-purpose, well-documented library for
exactly the transcript-segments → `.srt` text step FR-006 requires ­—
`srt.compose()` takes an iterable of subtitle objects and returns the
final file text, avoiding hand-rolled timestamp formatting.

**Alternatives considered**:
- **`pysrt`**: Comparable scope; `srt` was preferred for its simpler,
  more current API surface (`compose`/`parse`) and lighter footprint.
- **Hand-rolled `.srt` writer**: Trivial format, but avoidable
  string-formatting bugs (timestamp precision, index numbering) are
  exactly the kind of thing a small maintained library already handles.

Source: [srt library API docs](https://srt.readthedocs.io/en/latest/api.html)

## CLI framework and progress display

**Decision**: `typer` for the command-line interface, `rich` for the
progress indicator required by FR-011.

**Rationale**: Typer gives type-hint-driven argument/option parsing with
minimal boilerplate and generates `--help` output for free, which keeps
the CLI's contract (see `contracts/cli.md`) easy to keep in sync with the
implementation. `rich` integrates with Typer/Click's output and provides
a ready-made determinate progress bar, which — driven by faster-whisper's
segment-by-segment output — satisfies FR-011 without hand-rolling
terminal redraw logic.

**Alternatives considered**:
- **stdlib `argparse` + manual `\r`-based progress printing**: Zero extra
  dependencies, but more code to maintain for the same behavior, and no
  first-class `--help` ergonomics.
- **`click` directly**: Typer is a thin layer over Click with the same
  ecosystem compatibility; Typer's type-hint style was preferred for
  readability.

## Testing framework

**Decision**: `pytest`.

**Rationale**: Standard for Python CLI/library testing; supports the
`tests/{contract,integration,unit}` split in the plan's Project
Structure, and integrates cleanly with `typer.testing.CliRunner` for
contract-level CLI invocation tests.

**Alternatives considered**: stdlib `unittest` — viable but more
verbose for fixture-heavy tests (e.g., a shared small sample video fixture
across integration tests); rejected in favor of pytest's fixtures.
