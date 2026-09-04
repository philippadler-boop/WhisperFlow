# Feature Specification: Video Subtitle Generator

**Feature Branch**: `001-video-subtitle-generator`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "A tool that takes a given video and generates subtitles in a chosen language." (from `docs/ideas/initial-idea.md`)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transcribe a video into subtitles (Priority: P1)

A user has a video with spoken dialogue and wants a subtitle file that
captions what is said, timed to match the audio, without needing any video
editing or transcription skill of their own.

**Why this priority**: This is the core value of the product. Even before
translation exists, a working transcription-to-subtitles flow is a usable,
shippable product on its own (e.g., adding captions to a video in its
original language).

**Independent Test**: Can be fully tested by submitting a video with clear
spoken audio and verifying the tool produces a subtitle file whose text
matches the spoken words and whose timing lines up with the audio.

**Acceptance Scenarios**:

1. **Given** a video file with clear spoken audio in a supported language,
   **When** the user submits it for subtitle generation, **Then** the user
   receives a subtitle file containing text that matches the spoken words,
   broken into lines timed to the audio.
2. **Given** a video with multiple distinct sentences separated by pauses,
   **When** subtitles are generated, **Then** each subtitle line's start
   and end time aligns with when the corresponding words are actually
   spoken.

---

### User Story 2 - Review and correct generated subtitles (Priority: P2)

A user reviews the generated subtitles before treating them as final,
because automated transcription/translation is not always perfectly
accurate, and fixes any lines that are wrong.

**Why this priority**: Improves trust in the output but is not required
for the tool to deliver initial value — a user can already download and
manually fix subtitles outside the tool if this isn't built yet.

**Independent Test**: Can be fully tested by generating subtitles for a
video, editing the text of one or more lines, and verifying the exported
subtitle file reflects the edits rather than the original generated text.

**Acceptance Scenarios**:

1. **Given** a set of generated subtitles, **When** the user edits the
   text of a specific line, **Then** the exported subtitle file contains
   the edited text, not the originally generated text, for that line.

---

### Edge Cases

- What happens when the video has no detectable speech (e.g., silent or
  music-only)? The tool should report this clearly rather than failing or
  producing a blank/garbled file.
- How does the system handle a video with multiple overlapping speakers or
  heavy background noise that degrades transcription quality?
- How does the system handle an input file that isn't a valid or supported
  video format?
- How does the system handle a video longer than the supported maximum
  length?
- How does the system handle audio in a language it cannot detect or does
  not support?

## Out of Scope for v1

- **Translation**: Generating subtitles in a language different from the
  video's original spoken audio is deferred to a future release. v1
  produces subtitles only in the video's source language. (Resolved
  2026-09-04: transcription-only for v1.)
- **Graphical interface**: v1 ships as a command-line tool only; a GUI is
  a candidate for a future release. (Resolved 2026-09-04.)
- Verifying content rights/ownership of a submitted video.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a video file as input and extract its
  spoken audio for processing.
- **FR-002**: System MUST produce a time-synchronized transcript of the
  spoken audio in the video's original (source) language.
- **FR-003**: System MUST generate subtitles in the same language as the
  video's spoken audio; translating into a different language is out of
  scope for v1 (see Out of Scope).
- **FR-004**: System MUST perform all transcription processing locally,
  on the user's own machine; video/audio content MUST NOT be transmitted
  to a cloud or third-party service.
- **FR-005**: System MUST expose subtitle generation through a
  command-line interface for v1 (see Out of Scope regarding a GUI).
- **FR-006**: System MUST write the generated subtitles to a subtitle
  file in a standard subtitle format (see Assumptions).
- **FR-007**: System MUST clearly report an error, rather than silently
  failing, when given an input file that is not a supported video format
  or exceeds the maximum supported length.
- **FR-008**: System MUST clearly report when a video contains no
  detectable speech instead of producing a blank or misleading subtitle
  file.
- **FR-009**: Users MUST be able to review the text of generated subtitle
  lines before treating the output as final.
- **FR-010**: Users MUST be able to edit the text of individual subtitle
  lines, with edits reflected in the exported subtitle file.

### Key Entities

- **Video**: The user-supplied input media file; relevant attributes are
  its format, duration, and spoken audio track.
- **Transcript**: A time-coded sequence of text segments derived from the
  video's spoken audio, in the source language.
- **Subtitle File**: A time-coded set of caption lines, in the video's
  source language and a standard subtitle file format, derived from the
  transcript.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user comfortable running a single command-line command,
  but with no programming or ML background, can go from providing a
  video to receiving a subtitle file without outside help.
- **SC-002**: For a typical short video (10 minutes or less) with clear
  speech, the user receives a completed subtitle file within 5 minutes of
  submitting the video.
- **SC-003**: At least 90% of generated subtitle lines, for clear speech
  in a supported language, are judged by a reviewing user to accurately
  reflect what was actually said.
- **SC-004**: At least 95% of generated subtitle lines are perceived by a
  viewer as in sync with the spoken audio (no noticeable lag or lead).
- **SC-005**: A user attempting subtitle generation for the first time
  succeeds in producing a usable subtitle file on their first attempt at
  least 90% of the time.

## Assumptions

- The initial supported source language for transcription is English,
  with broader source-language support treated as a fast-follow rather
  than a v1 requirement.
- Local/on-device transcription implies the user's machine must have
  sufficient compute to run a local speech-recognition model within the
  timing expectations in Success Criteria; minimum hardware requirements
  are a technical detail for the design phase, not this spec.
- Supported input video formats are common container formats (e.g., MP4,
  MOV, MKV); the maximum supported video length for v1 is capped (e.g.,
  around 2 hours) to bound processing time and cost.
- The default, and initially only, output subtitle format is the
  industry-standard `.srt` format; other formats (e.g., `.vtt`) are
  candidates for a later version.
- The user submitting a video has the rights/permission to use its
  content; verifying content rights or ownership is out of scope for v1.
