# 0001: Local ASR Engine

> **Status**: Proposed — pending human approval at the Design Gate
> (Principle II). Not yet binding until sign-off.

## Context

FR-002 requires a time-synchronized transcript of a video's spoken audio,
and FR-004 requires that all transcription processing happen locally on
the user's machine, with no video/audio content transmitted to a cloud or
third-party service. SC-002 and SC-006 require roughly 2x-real-time (or
better) throughput on typical consumer hardware — a 10-minute video must
complete within 5 minutes, and this ratio must hold up to the 2-hour
maximum supported video length (~1 hour of processing).

The tool must run CPU-only on typical consumer hardware by default (no
GPU assumed), while still leaving room to take advantage of a GPU when
one is available. It also needs to be straightforward to package and
invoke from a Python CLI without adding heavyweight build dependencies.

## Decision

Use `faster-whisper` (a CTranslate2-based reimplementation of OpenAI's
Whisper models) as the local ASR engine, running CPU inference with int8
quantization by default, and using a GPU automatically when one is
available.

## Alternatives Considered

- **whisper.cpp**: Faster on Apple Silicon via Metal/Core ML (reported
  ~10x real-time on large-v3) and has first-class streaming support this
  feature doesn't need. Rejected as the default because it is a C/C++
  project requiring bindings or a subprocess boundary from Python, which
  adds packaging complexity for a v1 CLI tool, and its plain-CPU path is
  not clearly faster than faster-whisper's int8 path off Apple hardware.
- **Stock `openai-whisper`**: The reference implementation and the
  simplest possible integration, but noticeably slower than both
  alternatives with no quantization support — the highest-risk option for
  missing SC-002/SC-006 on CPU-only machines.

## Consequences

- Transcription runs entirely on-device, satisfying FR-004 by
  construction (no network call is part of the transcription path).
- `faster-whisper` installs as a pure pip package, keeping the CLI's
  packaging story simple relative to a C/C++ binding or subprocess
  boundary.
- Public benchmarks (see research.md sources) show faster-whisper with
  int8 quantization outperforming both stock OpenAI Whisper and
  whisper.cpp's CPU path on comparable hardware, giving throughput
  headroom toward SC-002/SC-006 even before GPU acceleration is
  considered — but actual throughput on a given user's hardware is
  unverified until benchmarked (`scripts/benchmark.py`) against real
  target machines.
- Apple Silicon users may see better raw throughput from whisper.cpp's
  Metal/Core ML path than from faster-whisper's CPU path; this is an
  accepted trade-off in exchange for simpler Python packaging, not
  something v1 attempts to optimize around.
- Model weight downloads (first-run model fetch) are a one-time exception
  to "no network calls," distinct from per-video transcription traffic;
  this should be made explicit in user-facing documentation so it isn't
  mistaken for a FR-004 violation.
- T029 followed up on the "actual throughput ... is unverified until
  benchmarked" caveat above: `scripts/benchmark.py time` against a short
  (~3.5s) fixture on CPU-only reference hardware showed the CLI's `base`
  default sometimes missing the SC-002/SC-006 ~2x-real-time target while
  `tiny` consistently met it. That result conflicted with a separate,
  real ~59-minute video benchmarked at `--model base` on comparable
  hardware, which finished in 48.7s (~35x inside the target) — a strong
  signal that the short-fixture numbers were dominated by fixed per-run
  overhead rather than steady-state decode throughput, and not sufficient
  evidence to justify defaulting every user to a less accurate model
  (SC-003's accuracy cost was also never measured). `base` therefore
  remains the CLI default; `contracts/cli.md`'s minimum-hardware note
  recommends `--model tiny` only for constrained/CPU-only hardware, and
  properly reconciling this conflict with a longer reference fixture and
  a measured SC-003 accuracy delta is left as follow-up work rather than
  changing the default on the current evidence.
