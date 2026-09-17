# WhisperFlow

WhisperFlow is a local command-line tool that turns a video's spoken audio
into time-synced SubRip (`.srt`) subtitles. It transcribes the original spoken
language; translation is not part of v1.

## Prerequisites

- Windows, macOS, or Linux
- Python 3.11 or newer
- FFmpeg, with both `ffmpeg` and `ffprobe` available on `PATH`
- Enough disk space for the selected faster-whisper model and temporary audio

Verify FFmpeg before installing:

```powershell
ffmpeg -version
ffprobe -version
```

Install FFmpeg using your operating system's package manager or the official
FFmpeg distribution. WhisperFlow cannot probe or extract audio until both
commands are available.

## Installation

From the repository root, install WhisperFlow in editable mode:

```powershell
python -m pip install -e .
```

For development and tests, install the optional test dependency too:

```powershell
python -m pip install -e ".[dev]"
```

Confirm the command is available:

```powershell
whisperflow --help
whisperflow transcribe --help
```

The first transcription may take longer while faster-whisper prepares the
selected model. Processing is local; audio and transcripts are not sent to a
remote service.

## User Guide

### Transcribe a video

For an immediate, script-friendly run:

```powershell
whisperflow transcribe .\samples\hello.mp4 --no-review
```

The default output is next to the input video. For `hello.mp4`, the result is
`hello.srt`.

### Choose an output path

Use `--output` or `-o` to select the subtitle destination. Parent
directories are created automatically if they don't already exist:

```powershell
whisperflow transcribe .\samples\hello.mp4 `
	--output .\output\hello.srt `
	--no-review
```

### Choose a transcription model

The default model is `tiny`. Smaller models are faster; larger models can be
more accurate and require more resources:

```powershell
whisperflow transcribe .\samples\hello.mp4 --model base --no-review
```

Available models are `tiny`, `base`, `small`, `medium`, and `large`.
`tiny` is the default because benchmarking (see
[Benchmarking](#benchmarking) below and
`specs/001-video-subtitle-generator/contracts/cli.md`'s minimum-hardware
note) found larger sizes can miss the SC-002/SC-006 processing-time target
on CPU-only hardware with no GPU. If you have a GPU or have benchmarked
your own hardware and confirmed it keeps up, a larger `--model` gives more
accurate transcripts.

### Review mode

`--review` is the default (omit `--no-review` to use it). After the draft
`.srt` is generated, WhisperFlow opens it in an editor and waits for you to
confirm you're done before writing the finalized file:

```powershell
whisperflow transcribe .\samples\hello.mp4 --editor "code --wait"
```

- The editor command comes from `--editor`, falling back to the `$EDITOR`
	or `$VISUAL` environment variable. Use an editor flag that blocks until
	the file is closed (e.g. `code --wait`, `notepad`, `vim`) — WhisperFlow
	waits for that process to exit before re-reading the file.
- If no editor is configured anywhere, WhisperFlow instead prints the draft
	file's path and waits for you to press Enter after editing and saving it
	yourself.
- Only lines whose text actually changed are treated as edited; timings are
	not user-editable in this release. The finalized `.srt` written to
	`--output` reflects your edits, not the originally generated text.

For a script-friendly run that skips review entirely, pass `--no-review` as
shown above.

### Progress and output

Stage messages and transcription progress are written to stderr so the `.srt`
file remains the machine-readable output artifact. On success, the command
returns exit code `0` and writes one `.srt` file.

If no speech is detected, that is still a successful run: WhisperFlow returns
`0`, reports the result on stderr, and writes an empty `.srt` file.

### Errors

Fatal input and processing errors return exit code `1` and print one readable
error line to stderr. Common causes include:

- Unsupported or corrupt video input
- A video longer than the two-hour maximum
- Missing `ffmpeg` or `ffprobe`
- A transcription model that cannot be loaded
- In `--review` mode, a configured editor that fails to start or exits
	non-zero, or a saved draft that can no longer be parsed as valid `.srt`

No partial subtitle file is left behind for input validation failures.

### Command reference

```text
whisperflow transcribe VIDEO_PATH [OPTIONS]
```

Full contract: `specs/001-video-subtitle-generator/contracts/cli.md`.

Arguments:

| Argument | Required | Description |
|---|---|---|
| `VIDEO_PATH` | Yes | Path to the input video file |

Options:

| Option | Default | Description |
|---|---|---|
| `--output`, `-o PATH` | `<video_basename>.srt` next to the input video | Where to write the `.srt` file |
| `--model {tiny,base,small,medium,large}` | `tiny` | faster-whisper model size — smaller is faster, larger is more accurate; `tiny` is the default to reliably meet the SC-002/SC-006 timing target on CPU-only hardware (see contracts/cli.md's minimum-hardware note) |
| `--review` / `--no-review` | `--review` | With `--review`, opens the draft `.srt` in an editor and waits for confirmation before finalizing; `--no-review` finalizes immediately |
| `--editor CMD` | `$EDITOR`/`$VISUAL`, else a built-in fallback prompt | Overrides which editor `--review` opens |

Examples:

```powershell
# Script-friendly, no editor pause
whisperflow transcribe .\samples\hello.mp4 --no-review

# Custom output path
whisperflow transcribe .\samples\hello.mp4 -o .\output\hello.srt --no-review

# Larger/more accurate model (only if your hardware keeps up -- see
# contracts/cli.md's minimum-hardware note)
whisperflow transcribe .\samples\hello.mp4 --model base --no-review

# Review with an explicit, blocking editor
whisperflow transcribe .\samples\hello.mp4 --editor "code --wait"
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Success — `.srt` file written (including the zero-subtitle-blocks case when no speech is detected) |
| `1` | Fatal error — see [Errors](#errors) above |

For live option descriptions and the startup banner:

```powershell
whisperflow transcribe --help
```

## Development

Run the test suite from the repository root:

```powershell
python -m pytest
python -m ruff check .
```

### Benchmarking

`scripts/benchmark.py` times a `transcribe` run and, given a small labeled
reference corpus, reports rough transcript-accuracy and subtitle-timing-sync
percentages against it:

```powershell
# Time a single run (SC-002/SC-006, quickstart.md Scenario 8)
python scripts/benchmark.py time samples/ten-minutes.mp4 --model tiny

# Score accuracy/timing-sync against a labeled reference corpus.
# tests/fixtures/benchmark_corpus.json is a real, checked-in single-entry
# corpus (clear_speech.mp4 + its docs/validation/T011.md ground-truth
# transcript) -- a working example, not a template; author your own
# manifest for a larger/real corpus.
python scripts/benchmark.py corpus tests/fixtures/benchmark_corpus.json
```

A corpus manifest is a JSON list of `{"video": ..., "reference_text": ...}`
entries (or `"reference_text_path"` pointing at a plain-text file), each
giving a sample video's known-correct transcript. The reported accuracy and
timing-sync percentages are printed alongside an explicit meets/MISSES
verdict against SC-003's >=90% accuracy target and SC-004's >=95%
timing-sync target (overridable via `--min-accuracy`/`--min-sync-ratio`;
pass `--strict` to also exit with status `3` if either target is missed,
e.g. for a CI gate -- distinct from argparse's own status `2` for usage
errors, so a CI script can tell "invoked incorrectly" apart from "corpus
missed its target"). Both criteria are explicitly judged by a human (a reviewing
user, a viewer) in spec.md, so this script gives `qa` a concrete,
reproducible number to anchor that judgment against, not a replacement
for it.

`scripts/benchmark.py time` runs against CPU-only reference hardware were
also what motivated `tiny` as the CLI's default `--model` size (T029) --
see `specs/001-video-subtitle-generator/contracts/cli.md`'s
minimum-hardware note for the measured numbers behind that decision, and
run the benchmark yourself against your own hardware before choosing a
larger model for a time-sensitive workflow.

## Windows Installer Build

The Windows release is built as a PyInstaller one-directory application and
then packaged as an MSI with WiX. The MSI bundles Python dependencies plus
`ffmpeg.exe` and `ffprobe.exe`, so end users do not need a Python or FFmpeg
installation. Models are intentionally not bundled; faster-whisper manages
them outside the read-only Program Files installation.

On a Windows build machine, install PyInstaller and WiX, then supply an
FFmpeg directory containing `ffmpeg.exe` and `ffprobe.exe`:

```powershell
python -m pip install -e ".[packaging]"
winget install --id WiXToolset.WiXCLI --exact --source winget
wix eula accept wix7
.\scripts\build-windows-msi.ps1 -FfmpegDirectory C:\tools\ffmpeg\bin
```

The resulting installer is written to `dist\WhisperFlow-<version>.msi`.
Test it in Windows Sandbox or a clean virtual machine without Python or FFmpeg
installed before release. `wix eula accept wix7` is WiX v7's one-time,
per-user acceptance command; review WiX's Open Source Maintenance Fee terms
before running it.

The MSI installs per-machine (`Scope="perMachine"`) under
`C:\Program Files (x86)\WhisperFlow` and registers that directory on the
system `PATH`. Both install and uninstall require an elevated
(Administrator) session; running `msiexec` from a non-elevated terminal
fails with Error 1925 (install) or Error 1730 (uninstall) even though the
terminal looks like a normal PowerShell prompt. Confirm elevation first:

```powershell
([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
```

That must print `True` before running:

```powershell
msiexec /i "dist\WhisperFlow-0.1.0.msi" /qn /norestart
msiexec /x "dist\WhisperFlow-0.1.0.msi" /qn /norestart
```

Open a new terminal after installing so the updated `PATH` takes effect.

`<install-dir>\uninstall.exe`
(`C:\Program Files (x86)\WhisperFlow\uninstall.exe` by default) is also
installed as a friend-friendly alternative to `msiexec`/Programs & Features:
double-clicking it prompts for elevation via UAC and removes the installed
product.
