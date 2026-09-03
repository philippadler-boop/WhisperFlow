# Idea: Video subtitle generator

**Captured:** 2026-09-03

A tool that takes a given video and generates subtitles in a chosen language.

This is intentionally just the raw idea, not yet a concept brief or
requirements spec — those come next, via GitHub Spec Kit, once this repo is
opened in Claude Code / VS Code. Known open questions to resolve during
Concept/Requirements (not answered here on purpose):

- Interface: CLI tool, simple GUI, or both?
- Transcription approach: local (e.g. a local Whisper model) vs. a cloud API?
- Translation approach: local model vs. cloud API vs. transcription-only for v1,
  with translation as a fast-follow?
- Which source/target languages matter most for the first version?
- Input formats/sources supported (local file formats, max length, etc.)
- Output subtitle format(s): .srt, .vtt, others?
- Any privacy/cost constraints on sending audio/video to a cloud service?
