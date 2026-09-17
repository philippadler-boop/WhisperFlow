# CLI Contract: `whisperflow transcribe`

WhisperFlow v1 exposes exactly one user-facing command (FR-005). This is
the interface contract that `tests/contract/` verifies.

## Command

```text
whisperflow transcribe VIDEO_PATH [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `VIDEO_PATH` | Yes | Path to the input video file (FR-001) |

### Options

| Option | Default | Description |
|---|---|---|
| `--output`, `-o PATH` | `<video_basename>.srt` next to the input video | Where to write the `.srt` file (FR-006) |
| `--model {tiny,base,small,medium,large}` | `base` | faster-whisper model size — smaller is faster, larger is more accurate (research.md). See the minimum-hardware note below for when `tiny` is recommended instead. |
| `--review / --no-review` | `--review` | With `--review`, after generating a draft `.srt` the command opens it in `$EDITOR` (or `--editor`) and waits for confirmation before finalizing (FR-009, FR-010, User Story 2). `--no-review` finalizes immediately — for scripting/automation. |
| `--editor CMD` | value of `$EDITOR`/`$VISUAL`, else a built-in fallback prompt | Overrides which editor `--review` opens |

## Output contract

On success, exactly one `.srt` file is written at the resolved output
path, containing zero or more subtitle blocks in standard SubRip format,
time-coded against the input video's audio (FR-002, FR-006).

- Zero subtitle blocks is a valid output when no speech was detected
  (FR-008) — this is a successful run, not an error.
- Subtitle line text reflects any edits made during the `--review` step
  (FR-010); timings are not user-editable in v1 (data-model.md).

## Progress contract (FR-011)

While in the `Transcribing` stage (data-model.md — ProcessingJob), the
command prints a progress indicator to stderr showing the current
completion percentage. Stage transitions (`Extracting audio…`,
`Transcribing…`, `Writing subtitles…`) are each announced with a single
line to stderr. Machine-readable output (the `.srt` file itself) is never
mixed into stdout progress noise: v1 writes the subtitle file directly to
`--output`, not to stdout.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — `.srt` file written (including the zero-subtitle-blocks case, FR-008) |
| `1` | Fatal error before or during processing: unsupported/corrupt video format, video exceeds the 2-hour maximum, required `ffmpeg` binary not found, or the ASR model failed to load (FR-007) |

Error messages for exit code `1` are printed to stderr as a single
human-readable line identifying the problem (e.g. `Error: video exceeds
maximum supported length of 2 hours (got 2:14:03)`), per FR-007's "clearly
report an error" requirement.

## Non-functional contract

- No outbound network requests are made at any point during
  `transcribe` (FR-004). Contract tests assert this (e.g. by running
  with network access blocked and confirming no failure attributable to
  a network call).
- Rerunning the same command after an interrupted prior run always starts
  a fresh job from `Extracting audio…` (Out of Scope: Resumable
  processing) — there is no `--resume` option in v1.

## Minimum-hardware note (SC-002/SC-006, T029)

`scripts/benchmark.py time` (T025/T028) was run on CPU-only reference
hardware with no GPU (a 4-vCPU host — representative of a typical CI
runner / constrained consumer machine with no dedicated GPU), against a
short (~3.5s) speech fixture, at several `--model` sizes. On that short
fixture, `base` sometimes fell outside the SC-002/SC-006 ~2x-real-time
target while `tiny` consistently met it.

That short-clip result is **not** treated as sufficient evidence to
change the CLI's default: a short clip's elapsed time is dominated by
fixed per-run overhead (process startup, model load, one `ffmpeg`
invocation) rather than the model's steady-state decode throughput that
SC-002/SC-006 actually gate on, and it directly conflicts with a separate,
real ~59-minute video benchmarked at `--model base` on comparable
hardware, which completed in 48.7s (realtime ratio ~0.014 — roughly 35x
inside the target, not borderline). The accuracy cost of `tiny` relative
to `base` (SC-003, ≥90% accuracy) has also not been measured with
`scripts/benchmark.py corpus`.

Given that unresolved conflict, `base` remains the CLI default. `--model
tiny` is recommended as a fallback specifically for constrained or
CPU-only hardware (e.g. CI runners, or a laptop with no GPU and limited
CPU headroom) if you find `base` doesn't keep up with SC-002/SC-006 on
your machine — verify with `scripts/benchmark.py time` against a
representative, realistically long video before relying on either
model size for a time-sensitive workflow. A GPU (`device="auto"` in
`research.md`'s ASR-engine decision already uses one automatically when
present) removes most of this concern regardless of model size.
