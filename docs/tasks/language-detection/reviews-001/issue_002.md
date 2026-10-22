---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 364
severity: medium
author: claude-code
provider_ref:
---

# Issue 002: LANGUAGE_NO_ANSWER needs data no single layer has; format change misreported

## Review Comment

`Log.LANGUAGE_NO_ANSWER = "whisper gave no language for %d of %d samples of %s; output tail: %s"` (`_spec.md:364`) needs two things:
- the meeting id, which only the use case has: the port is `detect(audio, offsets, window_seconds)` (`_spec.md:217`);
- whisper's output tail, which only the adapter has, since `detect` returns a bare `list[LanguageSample]`.

IT-002 (`_tests.md:150`) expects `TranscribeMeeting` "over the real adapter" to log it, so the test cannot be written as specified. The use case also cannot tell "whisper printed no answer line" (a format change) apart from "every clip was past the real end, whisper never ran" (`_spec.md:256`). Both come back as all-`None`.

The reason chosen for an unparsable output also misleads. `_spec.md:299` and US-003.EC-2 (`_user_stories.md:72`) map it to `no-usable-sample`, which `trec transcribe` prints as `fallback: no sample heard pt or en clearly` (`_dx.md:81`). After a whisper.cpp upgrade, every meeting would claim unclear audio, and the CLI would give no pointer to the log. `detection-failed` prints `see the log` (`_dx.md:83`), which is the line the operator needs.

Suggested fix:
- The adapter raises `TranscriptionError(Err.WHISPER_NO_LANGUAGE.format(tail=...))` when whisper exited 0 on at least one clip and no answer line matched any of them. The use case then logs `LANGUAGE_DETECTION_FAILED` with the message, which carries the tail, and the reason is `detection-failed`.
- Keep `no-usable-sample` for answers that parsed but did not count.
- Update US-003.EC-2, `_dx.md` Logs and IT-002 to match. If the current mapping is kept, say which layer logs and how the meeting id reaches it.

## Triage

- Decision: `VALID`
- Notes: Valid. The log needed the meeting id (use case) and the output tail (adapter); a format change was reported as unclear audio.
- Verified: `_spec.md` Monitoring and Integration Points; `_dx.md` Logs; `_tests.md` IT-002.

### Resolution

The adapter raises `TranscriptionError(Err.WHISPER_NO_LANGUAGE)` (text in `_spec.md`, carries the output tail) when whisper exited 0 on at least one clip and no answer line matched any; some clips unanswered is not an error. The use case logs `LANGUAGE_DETECTION_FAILED` (meeting id + exception) and stores `detection-failed`. `LANGUAGE_NO_ANSWER` removed. `no-usable-sample` stays for answers that parsed but did not count, and for every clip being past the end (whisper not called). Updated: Business Rules › Fail-soft, adapter rules, Integration Points, Monitoring, US-003.EC-2, `_dx.md` Logs, UT-016, IT-002, ADR Implementation Notes.
