---
provider: manual
pr:
round: 2
round_created_at: 2026-10-22T00:02:17Z
status: resolved
file: docs/tasks/language-detection/_dx.md
line: 175
severity: low
author: claude-code
provider_ref:
---

# Issue 003: _dx.md says an unknown first code is harmless, but it is the fallback

## Review Comment

`_dx.md` › Errors (line 175) says: "A code that whisper does not know (for example `languages = ["xx", "pt"]`) is never chosen by detection, since whisper never answers it." In that example `xx` is the first entry, so it is the fallback (Business Rules › Fallback; `_dx.md` line 67 "the first is the fallback"; `Settings.fallback_language = languages[0]`). Every meeting that does not reach a majority (`no-usable-sample`, `too-few-votes`, `no-majority`, `detection-failed`) is then transcribed with `-l xx`. The same paragraph says whisper-cli rejects that code at transcription and the meeting fails with `error.txt`. So the example produces exactly the outcome the Goals rule out ("The detection never blocks or fails a transcription"), and the contract calls it harmless. Validation accepts it, since `^[a-z]{2,3}$` matches `xx`.

Second, smaller mismatch in the same contract, `_dx.md` › Logs line 162: `whisper-cli timed out after 300 seconds`. The adapter is to mirror the transcriber's `_run` error mapping, which formats `Err.TIMED_OUT = "{what}: timed out after {seconds:.0f}s"` (`messages.py:107`, used at `transcriber_whispercpp.py:88`). That gives `whisper-cli: timed out after 300s`.

Suggested fix: change the example to `languages = ["pt", "xx"]`. Add that an unknown code as the first entry, which is the fallback, fails every undecided meeting the same way a fixed `language = "xx"` does. If preferred, require the fallback to be a code whisper knows (out of scope here unless the user wants it). Make the timeout log example match `Err.TIMED_OUT`.

## Triage

- Decision: `VALID`
- Notes: Valid. `xx` first in `languages` is the fallback, so undecided meetings fail; the timeout log did not match `Err.TIMED_OUT`.
- Verified: `_dx.md` Errors and Logs; `messages.py:107` (`TIMED_OUT = "{what}: timed out after {seconds:.0f}s"`).

### Resolution

`_dx.md` Errors explains that an unknown code is harmless only after the first entry, and what happens when it is the fallback; the configuration does not check codes against whisper's list. The log example now reads `whisper-cli: timed out after 300s`.
