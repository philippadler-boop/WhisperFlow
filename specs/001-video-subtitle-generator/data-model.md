# Data Model: Video Subtitle Generator

Entities derived from [spec.md](spec.md)'s Key Entities section and
Functional Requirements. This is a single-process CLI tool with no
persistent storage (Technical Context: Storage = N/A) — these are
in-memory/on-disk-file structures for one run, not database records.

## Video

The user-supplied input media file (spec: Key Entities — Video).

| Field | Type | Notes |
|---|---|---|
| `path` | path | Input file location, provided by the user |
| `container_format` | string | Detected from the file (e.g. mp4, mov, mkv) |
| `duration_seconds` | float | Probed via ffmpeg; validated against the 2-hour max |
| `has_audio_track` | bool | False triggers the FR-008 "no detectable speech" report |

**Validation rules**:
- `container_format` MUST be one of the supported formats (Assumptions);
  otherwise FR-007 applies (clear error, not a crash).
- `duration_seconds` MUST be ≤ 7200s (2 hours, per Clarifications);
  otherwise FR-007 applies.

## AudioTrack

The mono, 16kHz audio extracted from `Video` for transcription (research.md
— Audio extraction).

| Field | Type | Notes |
|---|---|---|
| `source_video` | Video | Back-reference |
| `extracted_path` | path | Temporary WAV file, removed after the run |
| `sample_rate_hz` | int | Fixed at 16000 for the ASR engine |

## TranscriptSegment

One ASR-produced unit of timed text, before any subtitle-specific line
splitting (spec: FR-002).

| Field | Type | Notes |
|---|---|---|
| `start_seconds` | float | Segment start, from the ASR engine |
| `end_seconds` | float | Segment end, from the ASR engine |
| `text` | string | Recognized text for this segment, source language |

## Transcript

The full time-coded transcript of a `Video` (spec: Key Entities —
Transcript).

| Field | Type | Notes |
|---|---|---|
| `source_video` | Video | Back-reference |
| `language` | string | Source (spoken) language — see spec Assumptions |
| `segments` | list[TranscriptSegment] | Ordered by `start_seconds`; empty list represents "no detectable speech" (FR-008), distinct from a failed run |

**Validation rules**:
- An empty `segments` list is a valid, successful outcome (FR-008) and
  MUST be surfaced to the user as "no speech detected," not as an error.

## SubtitleLine

One caption line in the output file, initially derived 1:1 from a
`TranscriptSegment` but independently editable (spec: FR-009, FR-010,
User Story 2).

| Field | Type | Notes |
|---|---|---|
| `index` | int | 1-based line number in the `.srt` file |
| `start_seconds` | float | Initially copied from the source `TranscriptSegment` |
| `end_seconds` | float | Initially copied from the source `TranscriptSegment` |
| `text` | string | Initially copied from the source `TranscriptSegment`; user edits (FR-010) overwrite this field only — timings are not user-editable in v1 |
| `edited` | bool | True once a user has changed `text` from its generated value; lets review tooling (FR-009) distinguish generated vs. corrected lines |

## SubtitleFile

The final output artifact (spec: Key Entities — Subtitle File; FR-006).

| Field | Type | Notes |
|---|---|---|
| `source_video` | Video | Back-reference |
| `format` | string | Fixed to `"srt"` for v1 (spec Assumptions) |
| `lines` | list[SubtitleLine] | Ordered by `index` |
| `output_path` | path | Where the composed `.srt` text is written |

## ProcessingJob (runtime state, not persisted)

Models the pipeline stages a single CLI invocation moves through, to
support FR-011 (progress reporting) and the interruption behavior fixed
by Clarifications (no checkpointing — a job never resumes).

**States**: `ExtractingAudio` → `Transcribing` → `WritingSubtitles` →
`AwaitingReview` (if the interactive review step runs) → `Done`, with a
`Failed` state reachable from any stage (surfaces the FR-007/FR-008 error
messages).

**Rules**:
- State is held only in process memory; nothing is written to disk that
  would let a future run resume mid-job (Out of Scope: Resumable
  processing). A rerun after interruption always starts a fresh
  `ProcessingJob` at `ExtractingAudio`.
- Progress percentage (FR-011) is derived from
  `current_segment_end_seconds / video.duration_seconds` while in the
  `Transcribing` state, since that is the longest-running stage.
