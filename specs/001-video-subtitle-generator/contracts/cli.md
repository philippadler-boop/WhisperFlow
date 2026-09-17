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
| `--model {tiny,base,small,medium,large}` | `tiny` | faster-whisper model size — smaller is faster, larger is more accurate (research.md). See the minimum-hardware note below for why `tiny` is the default. |
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
hardware with no GPU (a 4-vCPU AMD EPYC 7763 host — representative of a
typical CI runner / mid-range consumer machine with no dedicated GPU),
against both a short (~3.5s) and a longer (~120s) speech fixture, at
several `--model` sizes:

| `--model` | Realtime ratio (elapsed / video duration) | SC-002/SC-006 target (≤ 0.5) |
|---|---|---|
| `tiny` | ~0.37–0.44 | Meets target, with margin |
| `base` (previous default) | ~0.45–0.66, varying run to run | Borderline — repeatedly observed both just inside and outside the target on the same hardware |

Because `base` was observed missing the ~2x-real-time target on this
CPU-only reference hardware (and a real end-user's CPU-only laptop should
be expected to do no better than this reference machine), the default
`--model` was changed from `base` to `tiny` (T029) to reliably meet
SC-002 ("within 5 minutes" for a 10-minute video) and SC-006 (proportional
scaling to ~1 hour for a 2-hour video) out of the box.

`base`, `small`, `medium`, and `large` remain available via `--model` and
trade that timing margin for higher transcription accuracy (SC-003); they
are recommended only when either (a) a GPU is available (`device="auto"`
in `research.md`'s ASR-engine decision already uses one automatically when
present), or (b) the user has benchmarked their own hardware with
`scripts/benchmark.py time` against a representative video and confirmed
it meets SC-002/SC-006 at the chosen model size.
