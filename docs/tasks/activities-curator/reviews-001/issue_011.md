---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_user_stories.md
line: 268
severity: medium
author: claude-code
provider_ref:
---

# Issue 011: `trec stories` "waits only seconds" contradicts a lock held for minutes

## Review Comment

US-014 EC-4 (`_user_stories.md:268`) says: "The curator is running → `trec stories` drafts without waiting and waits only seconds for the tag replacement." The tag replacement is done "under a short lock (doc + base)" (`_spec.md:293`, Safety Invariant 10). But the lock it needs is the curator lock, and the curator holds that lock "through the LLM call" (`_spec.md:451`). That call has a 900 s timeout in `ClaudeCodeTransport` (`_spec.md:375`), plus one repair call. If a pass is running, `trec stories` waits up to the end of that pass, which can be tens of minutes, not seconds.

The spec defines no timeout, no message and no exit code for that wait. `DraftStoriesFromTags.execute()` has no `wait` parameter (`_spec.md:293`). `_dx.md` › `trec stories` shows only the no-contention output. If the user presses Ctrl-C during that wait, the drafts are already saved but the tags are not replaced, so the next `trec stories` drafts the same items again. Duplicate detection then relies on the writer's judgment. No test covers EC-4: the coverage matrix row for US-014 lists only UT-073, which is an edited line and not a busy lock.

Suggested fix: choose one behaviour and write it into `_dx.md` and `_tests.md`. Option (a): try the lock non-blocking; if busy, print `The curator is working; the drafts are saved. Run trec stories again later to replace the tags.`, exit 0, and keep a record so the rerun replaces tags without re-drafting. Option (b): wait with a stated bound and the `waiting for the curator…` line. Fix the EC-4 wording to match, and add a test with the lock held by another process.

## Triage

- Decision: `VALID`
- Notes: Valid. The tag replacement needs the curator lock, which is held through a call with a 900 s timeout, so "waits only seconds" was false and there was no timeout, message, exit code or test.
- Reopened (round 2): the fix does not close the duplicate-drafting path this issue described. `DraftStoriesFromTags.execute` step 1 applies `pending_tags.json` only when `lock(wait=False)` succeeds ("if busy, leave them") and step 2 then reads tagged blocks from the document, where those lines still carry `#história`, so a second `trec stories` while a pass runs (passes last minutes and follow every meeting) sends the already-drafted blocks to the writer again. The writer's duplicate check does not catch it: `existing` comes from `recent_story_drafts(before=today, days)`, whose window is `start <= d < before` (repository_fs.py:330-332), so today's drafts file is excluded, and `trec publish` would send both copies to the board. Step 4 also does not say whether `save_pending_tags` merges with or overwrites earlier entries. UT-077 covers only the free-lock case. Needed: step 2 skips blocks whose tagged line equals a pending `PendingTag.line`; pending entries are merged; today's drafts are part of `existing`; add a UT where the lock is busy at step 1 of the second run.
- Verified (round 3): `pending_tags.json`/`PendingTag` are gone (grep finds no reference). `DraftStoriesFromTags` step 2 skips a tagged line that is the first line of a stored `source_text` or equals a stored `source_line`, over `recent_story_drafts(before=tomorrow, days=dedup_days + 1)`, so today's drafts count. Only step 5 (the tag replacement) is retried. UT-122 (lock busy on both runs) and IT-017 (child process holds the flock) cover the duplicate path this issue described, and Invariant 10, US-014 EC-4 and `_dx.md` say the same thing.

### Resolution

Fixed with option (a). `DraftStoriesFromTags.execute` never waits: after saving the drafts it writes the replacements to `.curator/pending_tags.json` (new `PendingTag`, `ActivityStore.pending_tags/save_pending_tags`) and tries the lock with `wait=False`; when busy it reports `deferred`, prints `The curator is working; the drafts are saved. Run trec stories again later to replace the tags.` and exits 0; the next `trec stories` applies pending replacements first (line found exactly once, document and base) without re-drafting, so Ctrl-C after the drafts are saved no longer causes duplicates. US-014 EC-4 rewritten, Key Decisions and Safety Invariant 10 updated, `_dx.md` stories section and Errors table. Tests: UT-076, UT-077, IT-017; coverage matrix rows for US-014 EC-4.

### Resolution (round 2)

Round-2 fix (simplification: `pending_tags.json` and `PendingTag` are deleted). The drafts file is the memory: `DraftStoriesFromTags` now skips any tagged line that is the first line of a stored `UserStory.source_text` or equals a stored `SkippedAction.source_line` in the recent drafts, with today included (`recent_story_drafts(before=tomorrow, days=dedup_days + 1)`, which also closes the `d < before` gap), so a second `trec stories` while a pass runs sends nothing already drafted to the writer, and the only retried work is the tag replacement (computed from the stored story, or from `duplicate_of` for a duplicate skip). No pending file means no merge/overwrite question. Updated: spec (Interfaces, Key Decisions, Business Rules, Invariant 10, Data Models, Files), `_dx.md`, US-014 EC-4. Tests: UT-076 and UT-077 rewritten, new UT-122 (lock busy at both runs), IT-017 rewritten.
