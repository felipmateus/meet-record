---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_tests.md
line: 161
severity: low
author: claude-code
provider_ref:
---

# Issue 008: "detector" already names the CallDetector in Container

## Review Comment

`Container` already has `detector: CallDetector` (`src/teams_recorder/container.py:105`), the Teams call detector the daemon polls. The spec adds `TranscribeMeeting.detector: LanguageDetector` (`_spec.md:229`) and never names the new `Container` field. E2E-001 (`_tests.md:161`) patches "the container's transcriber … and its detector `ScriptedDetector(...)`". Read literally, that replaces the call detector, and the test would still pass in auto mode with the real `WhisperCppLanguageDetector` failing soft on a fake model, which hides the defect it is meant to catch. `ScriptedDetector` and `FakeLanguageDetector` sit next to existing call-detector fakes, which makes the confusion likely.

Suggested fix: name the field `language_detector` in `Container` and `TranscribeMeeting`, and the stand-in `ScriptedLanguageDetector`. Have E2E-001 assert that the stand-in's `--log` file shows one call, so a test that skips the scripted detector fails.

## Triage

- Decision: `VALID`
- Notes: Valid. `Container.detector` is the call detector (`container.py:105`).
- Verified: `src/teams_recorder/container.py:105`.

### Resolution

Renamed to `language_detector` in `TranscribeMeeting` and `Container` (built by `build_language_detector(settings)`), stand-in `ScriptedLanguageDetector`. E2E-001 patches `language_detector` explicitly, leaves the call `detector` alone, and asserts the stand-in's `--log` has exactly one call.
