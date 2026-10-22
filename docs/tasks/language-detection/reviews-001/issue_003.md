---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 374
severity: medium
author: claude-code
provider_ref:
---

# Issue 003: Meeting-lock rationale is false: trec purge ignores the lock

## Review Comment

Key Decisions (`_spec.md:374`) says detection runs inside the meeting lock because "a concurrent `trec purge` must not delete the file mid-detection". Safety invariant 4 (`_spec.md:391`) relies on the same idea.

The code gives no such protection:
- `PurgeOldAudio.execute` (`src/teams_recorder/application/use_cases/retention.py:18-26`) calls `repo.delete_file(meeting.id, AUDIO)` without taking or checking the lock.
- `FsMeetingRepository.delete_file` (`src/teams_recorder/adapters/outbound/repository_fs.py:123-126`) just unlinks the file.
- The `.lock` file is consulted only by `lock()` itself (`repository_fs.py:134-142`), and only `TranscribeMeeting`/`AnalyzeMeeting` take it (`processing.py:64,175`).
- The daemon runs the purge in a background thread on the first tick of each day (`adapters/inbound/daemon.py:232-247`).

This race is plausible here. The backfill in Open Questions (`_spec.md:83`) re-transcribes 2026-10-08 and 2026-10-14 close to their purge dates (2026-11-07 and 2026-11-13), and a re-run meets `TRANSCRIPT_JSON in files`, so the purge target condition holds during the run. The outcome is fail-soft today (ffmpeg fails, then `detection-failed`, then the transcriber raises `AUDIO_MISSING`), but the spec claims a guarantee that does not exist.

Suggested fix: either reword the decision ("runs inside the lock like the transcription; the purge does not honour the lock, and a deleted file fails soft into `detection-failed` and then the transcription's own `AUDIO_MISSING`"), or extend the scope so that `PurgeOldAudio` skips a meeting whose lock is held (with a test), and list `retention.py` in the Impact Analysis.

## Triage

- Decision: `VALID`
- Notes: Valid. `PurgeOldAudio.execute` (`retention.py:18-26`) deletes `audio.m4a` without the lock.
- Verified: `src/teams_recorder/application/use_cases/retention.py:18-26`.

### Resolution

Reworded, scope unchanged: Key Decisions says detection runs inside the lock like the transcription (no interleaved transcriptions of one meeting), that the purge does not honour it, that only a re-transcription of an old transcribed meeting can race it, and the fail-soft outcome (`detection-failed`, then `AUDIO_MISSING` and `error.txt`, as today). Safety Invariant 4 no longer claims lock protection. The backfill Open Question says to run it well before the purge dates. Making the purge honour the lock is stated as out of scope. `retention.py` added to File References.
