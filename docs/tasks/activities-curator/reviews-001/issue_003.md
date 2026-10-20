---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 67
severity: high
author: claude-code
provider_ref:
---

# Issue 003: A meeting whose pass never ran is never curated nor reported

## Review Comment

The recovery rule only re-runs meetings when *another* pass happens, and only within two days. A meeting that never got a pass at all is listed nowhere. Together these recreate the Motivating Problem: analyzed work silently missing from the one place the user looks.

Evidence:
- The CuratorWorker queue is in memory (`_spec.md:124`, `queue.Queue`). If the daemon dies or restarts between `AnalyzeMeeting` saving `analysis.json` and the pass commit, the queued id is lost. The window is minutes long, because the lock is held through a call with a 900 s timeout. Causes include `trec agent restart`, which AGENTS.md requires after every Python change; the Mac sleeping or rebooting; and a launchd kill.
- On restart, the daemon's `_resume_pending` (`src/teams_recorder/adapters/inbound/daemon.py:299-305`) calls `Pipeline.resume_pending`. That function only processes `RECORDED`/`TRANSCRIBED` meetings (`src/teams_recorder/application/pipeline.py:83-85`). An `ANALYZED` meeting never reaches `after_analysis` again.
- `pending()` is consulted only when a pass is about to run: "added to the next pass" (`_spec.md:67`), "when any later pass runs" (US-011 AC-3, `_user_stories.md:215`). If the last meeting of a Friday loses its pass, the next pass runs on Monday. By then the meeting is past the 2-day window (`pending(days=2)`, `_spec.md:277`) and is never curated.
- The meeting never *failed*, so it has no `curation_error.txt`. `trec activities` lists only failed meetings ("Given failed meetings", US-017 AC-2; `_dx.md:144-145`). `trec doctor` says "N meetings not curated", but it is undefined whether that counts never-attempted meetings. The user gets no signal.

Suggested fix:
1. On daemon start, after `_resume_pending`, enqueue `CurateMeetings.pending()` into the CuratorWorker so a lost queue is rebuilt.
2. Define "not curated" as "analyzed within the bootstrap/visibility window with no successful pass record", whether or not it failed. Show it in `trec activities` and `trec doctor` with the retry command. Keep the 2-attempt cap for *failures* only.
3. Count the 2-day window in working days, so Monday picks up Friday. Or state why calendar days are intended.
4. Add tests: daemon start with an analyzed meeting that has no pass record → enqueued; `trec activities` lists a never-attempted meeting.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified in source: the worker queue is in memory, `Pipeline.resume_pending` handles only RECORDED/TRANSCRIBED, `pending()` was consulted only when another pass ran and in calendar days, and the listing covered only failed meetings, so a never-attempted meeting was invisible.
- Verified: daemon start enqueues `CurateMeetings.pending()` (System Architecture), `pending(max_attempts=2, working_days=2)`, `not_curated(working_days=10)` lists failed and never-attempted meetings in `trec activities`/`trec doctor` (`_dx.md`), US-011 AC-3/5/6, UT-101/106/107, E2E-005. UT-101's Thursday case contradicts UT-026 + `pending()`; tracked as reviews-002/issue_006.

### Resolution

Fixed as suggested. Business Rules "Recovery"; System Architecture (daemon start enqueues `CurateMeetings.pending()` after `_resume_pending`); `pending(max_attempts=2, working_days=2)` with new pure `working_days_ago`; new `not_curated(working_days=10)` returning `NotCurated(meeting_id, title, reason | None)` and `ActivitiesSummary`/`ActivitiesStatus` defined; `trec activities` lists failed and never-attempted meetings (`not attempted yet`), `trec doctor` counts both; the 2-attempt cap applies to failures only. Known limitation stated: after a shorter bootstrap, meetings outside it appear as not curated until they leave the 10-working-day window. US-011 AC-3, AC-5, AC-6 added/updated; `_dx.md` updated. Tests: UT-038 (rewritten), UT-101 (Monday picks Friday), UT-106, UT-107, UT-087, E2E-005.

