---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 228
severity: medium
author: claude-code
provider_ref:
---

# Issue 001: Fallback language has two sources; container would pass "auto" to whisper

## Review Comment

`TranscribeMeeting` gets both `language` ("the fixed language; with a detector, the fallback", `_spec.md:228`) and `languages` ("the allowed languages, fallback first", `_spec.md:230`). `choose_language` falls back to `allowed[0]` (`_spec.md:45`), but nothing says which field `_language` uses for `DETECTION_FAILED`, and nothing checks that the two agree.

The wiring makes this a real failure, not just a style point. Today `container.py:130` passes `self.settings.language` positionally as `TranscribeMeeting.language`. Under the new default that value is `"auto"` (`_spec.md:286`). The spec says only that `container.py` "builds the detector when settings.language == "auto"" (`_spec.md:150`). It never says that the container must pass `settings.fallback_language` (`_spec.md:289`) in place of `settings.language`. If that line is left as it is, a detection failure transcribes with `-l auto`. That is whisper's own first-30-seconds guess, the rejected Alternative 1 (`adrs/adr-001.md:29-34`), which can answer `is`. `_checked` then stores `transcript.language = "auto"` (`_spec.md:237`). No planned test catches it: UT-033/UT-034 build `TranscribeMeeting` directly, and UT-040 (`_tests.md:111`) checks only the detector type.

Suggested fix: keep one source of truth. Either derive the fallback from `languages[0]` and use `language` only when `detector is None`, or drop `languages` and pass `allowed` to the detector call. State in Part II that `Container.transcribe_meeting()` passes `settings.fallback_language`. Extend UT-040 to assert `transcribe_meeting().language == "pt"` in auto mode. Add a container-level case: a failing detector in auto mode gives a transcriber call with `"pt"` and never `"auto"`.

## Triage

- Decision: `VALID`
- Notes: Valid. `container.py:130` passes `self.settings.language` positionally; under the new default that is `"auto"`, and the spec never said to pass `fallback_language`.
- Verified: `src/teams_recorder/container.py:129-131`; `_spec.md` Core Interfaces and Config sections.

### Resolution

One source of the fallback: `TranscribeMeeting.language` (whisper's language without a detector, the fallback with one), passed by `Container.transcribe_meeting()` as `settings.fallback_language`; `languages` is only the allow-list; `choose_language(samples, allowed, fallback, rules)` takes the fallback explicitly; `TranscribeMeeting.__post_init__` refuses `"auto"` (Safety Invariant 6). Impact row for `container.py` names the risk. Tests: UT-040 asserts `language == "pt"` in auto mode, new UT-044 (failing detector through the container gives `"pt"`, never `"auto"`), new UT-045 (`language="auto"` raises), UT-007–UT-012b pass `fallback`.
