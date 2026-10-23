---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 204
severity: medium
author: claude-code
provider_ref:
---

# Issue 005: Gate recordings will be purged by audio retention before the gates run

## Review Comment

The user decided that the two no-speech recordings and the two English meetings are kept as test cases. G1/G2 (`_tests.md:204-205`) read `audio.m4a` of "every meeting with audio (28 on 2026-10-22)", and US-001.AC-5 names 2026-10-08_02-50-26 and 2026-10-17_10-15-32. `PurgeOldAudio` deletes `audio.m4a` of transcribed meetings older than `[audio] retention_days` (30 by default; AGENTS.md ports table, "retention"), and the daemon runs it once a day. The oldest gate inputs are 2026-10-05 (seven meetings), so their audio goes from about 2026-11-04. 2026-10-08_02-50-26 and MARTA (2026-10-08_10-30-52) go about 2026-11-07, and vans (2026-10-14_15-00-56) about 2026-11-13. Nothing in the spec, the sequencing or the gates says how those four inputs survive that. The count is already 29, not 28 (2026-10-23_09-32-12 was recorded today; read-only listing of `data/recordings`).

Suggested fix: state how the four named recordings are preserved for the gates, for example a read-only copy outside `data/` and outside the repo, made now, or a gate deadline. Ask the user before touching retention for them. Phrase G1/G2 against the named recordings plus "whatever has audio on the day", not a fixed count.


## Triage

- Decision: `VALID`
- Notes: Valid. `PurgeOldAudio` removes the gate audio from about 2026-11-04, and 2026-10-23_09-32-12 makes the count 29.
- Verified: The meeting dates in `data/recordings` (listing by the reviewer); retention is 30 days.
- Verified (round 2, 2026-10-23): the purge dates are correct (+30 days: 11-04, 11-07, 11-13, 11-16). The retention paragraph is in `_spec.md:456-461` and `_tests.md:220-226`. G1 is phrased per date (`28 on 2026-10-22, 29 on 2026-10-23`), not as a fixed count. The remaining "28" mentions (`_spec.md:4,154`, ADR-001 `:23`) describe the dated 2026-10-22 Evidence and are correct.

### Resolution

Technical Dependencies gains "Gate inputs and audio retention", with the purge date of each named recording. The gates run on every meeting with audio on the day, and the four named recordings are mandatory. If the gates cannot run before 2026-11-07, those four are copied read-only, with the user's approval, to a folder outside `data/` and outside the repo. Retention is not changed. `_tests.md` gates have an Inputs and retention paragraph, G1 names the counts per date, and G2 runs on every recording that still has audio and a G1 result.
