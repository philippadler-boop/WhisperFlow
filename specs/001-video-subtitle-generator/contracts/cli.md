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
| `--model {tiny,base,small,medium,large}` | `base` | faster-whisper model size — smaller is faster, larger is more accurate (research.md) |
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
