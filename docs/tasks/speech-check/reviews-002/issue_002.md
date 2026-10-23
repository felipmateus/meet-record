---
provider: manual
pr:
round: 2
round_created_at: 2026-10-23T15:10:53Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 548
severity: low
author: claude-code
provider_ref:
---

# Issue 002: `trec status`: `· en` claim wrong when the fallback is not `pt`; count line has no fixed position

## Review Comment

1. `_spec.md:548` says "A no-speech transcript's `language` is the fallback language, so `trec status` never shows `· en` for it." The marker does not depend on the fallback. `_language_segment` (`cli.py:197-202`) prints `  · <language>` whenever `transcript.language != Audio.DEFAULT_LANGUAGE` (`"pt"`). With `languages = ["en", "pt"]`, or a fixed `language = "en"`, a no-speech transcript is saved with `language == "en"` (`_spec.md:70`, `_no_speech`: `language = self.language`). Status then prints `  · en` before the new `  · no speech` (`marker += _language_segment(...)` comes last at `cli.py:116`, and `_dx.md:104` puts `· no speech` "after its other markers"). The result is a language claim for a recording in which nobody spoke. UT-063 uses only the `pt` fallback, so it cannot catch this.
   Fix: either suppress the language marker when `transcript.speech` is not found (and add that case to UT-063), or reword the assumption to "with the default `pt` fallback" and accept the marker.
2. `_dx.md:104` says the count line "follows the existing summary lines". `status` prints `Degraded transcripts`, the optional rate-mismatch line and `Unconfirmed claims`, and then `Recording in progress`, `Activities:` and `Stories waiting` (`cli.py:120-145`). The golden path (`_dx.md:31-36`) elides everything between the meeting lines and the count, and UT-063 does not fix a position. State the slot, for example "right after `Unconfirmed claims:`", next to the other conditional count line (`RATE_MISMATCH_TRANSCRIPTS`), and assert it in UT-063.


## Triage

- Decision: `VALID`
- Notes: Valid. `_language_segment` compares with `pt` (`cli.py:197-202`), and the count line had no slot.
- Verified: `cli.py:100-128`, `messages.py:242-246`.

### Resolution

A no-speech transcript gets no language marker in `trec status`, whatever the fallback. This matches the Goal "no language guess". The count line goes after `Degraded transcripts:` and the optional rate-mismatch line, before `Unconfirmed claims:`. Updated: Impact row `cli.py status`, Assumptions, `_dx.md` › `trec status` with the real summary lines, US-006.AC-3 and new EC-4, and UT-063, which covers an `en`-language no-speech meeting and the slot.
