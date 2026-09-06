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

Use `--output` or `-o` to select the subtitle destination. The destination
directory must already exist:

```powershell
whisperflow transcribe .\samples\hello.mp4 `
	--output .\output\hello.srt `
	--no-review
```

### Choose a transcription model

The default model is `base`. Smaller models are faster; larger models can be
more accurate and require more resources:

```powershell
whisperflow transcribe .\samples\hello.mp4 --model tiny --no-review
```

Available models are `tiny`, `base`, `small`, `medium`, and `large`.

### Review mode

The command currently defaults to review mode. The completed non-interactive
User Story 1 path uses `--no-review` as shown above. The review/edit workflow
is a separate task and is not yet available in this release.

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

No partial subtitle file is left behind for input validation failures.

### Command reference

```text
whisperflow transcribe VIDEO_PATH [OPTIONS]
```

Options:

- `--output`, `-o`: output `.srt` path; defaults beside the input video
- `--model`: `tiny`, `base`, `small`, `medium`, or `large`; default `base`
- `--review` / `--no-review`: review is the default; `--no-review` finalizes
	immediately
- `--editor CMD`: editor command for the review workflow

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
