---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 174
severity: low
author: claude-code
provider_ref:
---

# Issue 006: "transcript.txt is empty" is false with today's repository

## Review Comment

`_spec.md:71`, US-001.AC-2, `_dx.md:149` and IT-003 (`_tests.md:174`, "`transcript.txt` exists and is empty") all promise an empty file. `FsMeetingRepository.save_transcript` writes `transcript.as_timestamped_text() + "\n"` (`repository_fs.py:192`), so a transcript with no segments produces a one-byte file holding `"\n"`. An IT asserting `read_text() == ""` fails. Making it pass needs a change to `repository_fs.py`, which is not in Impact Analysis.

Suggested fix: either say "contains no lines" (and assert `.strip() == ""`), or list the `repository_fs.save_transcript` change (no trailing newline for an empty transcript) with its own test.


## Triage

- Decision: `VALID`
- Notes: Valid. `save_transcript` writes `as_timestamped_text() + "\n"` (`repository_fs.py:192`).
- Verified: `repository_fs.py:189-192`.
- Verified (round 2, 2026-10-23): "no lines" is used in `_spec.md:71`, US-001.AC-2, `_dx.md:152` and IT-003 (`read_text().strip() == ""`), and the Impact row records `repository_fs.py` as unchanged. No "empty transcript.txt" or "exists and is empty" wording is left.

### Resolution

The contract now says "no lines" (one newline), not "empty": Business Rules, US-001.AC-2, `_dx.md` Files, and IT-003 (`read_text().strip() == ""`). There is no repository change, and the Impact table records `repository_fs.py` as unchanged.
