---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 258
severity: low
author: claude-code
provider_ref:
---

# Issue 011: processing-line regex breaks on paths with an apostrophe (needs verification)

## Review Comment

`Parse.WHISPER_PROCESSING = r"processing '(.+?)'"` (`_spec.md:258`) stops at the first `'`. The clips live under `tempfile.TemporaryDirectory(prefix="trec-lang-")` (`_spec.md:256`). On Windows that is `%TEMP%`, under the user's profile folder, which can contain an apostrophe (for example `C:\Users\O'Brien\AppData\Local\Temp`). The captured path then never equals the clip path, every answer is unbound, and every meeting silently falls back. Needs verification on Windows, which is untested hardware for this project.

Verified locally: the line format is `main: processing '<path>' (479829 samples, 30.0 sec), …` on stderr. A clip whisper cannot read gets no `processing` line and the call still exits 0 (tested with a 78-byte WAV from a seek past the end), so binding answers to files rather than positions is the right design.

Suggested fix: anchor on the clip file names the adapter itself chooses (`c0.wav … cN.wav`, matched by basename with `processing '.*[\\/](c\d+\.wav)' \(`), or match greedily up to `' (`. Add a UT-015 variant with an apostrophe in the directory.

## Triage

- Decision: `VALID`
- Notes: Valid (Windows still needs verification on real hardware, as for every Windows path).
- Verified: Regex in `_spec.md`; the reviewer's local check of the `processing '<path>' (` format and of skipped clips.

### Resolution

Answers are bound by the clip's basename (`c<i>.wav`, chosen by the adapter): `WHISPER_PROCESSING = r"processing '.*[\\/](c\d+\.wav)' \("`, matched line by line. Rule and the apostrophe example in the adapter section and the ADR Implementation Notes. New UT-015a (apostrophe in the directory).
