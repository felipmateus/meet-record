---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 154
severity: low
author: claude-code
provider_ref:
---

# Issue 018: Planned surface departs from AGENTS.md conventions without updating them

## Review Comment

Several planned choices diverge from the rules in `AGENTS.md`. The spec does not list the matching AGENTS.md updates; its Impact Analysis (`_spec.md:395`) mentions only the "AGENTS.md ports table".

1. **Meeting file names.** `recordings/<id>/curation_error.txt` (`_spec.md:347`) is a meeting-folder file. AGENTS.md says "Meeting file names stay in `domain/status.py`", and every other per-meeting file, including those that are "not part of status", is declared there (`src/teams_recorder/domain/status.py:11-23`). Architectural Boundaries put file names in `constants.Files` instead (`_spec.md:154`). Also, `FsActivityStore.mark_meeting_failed` writes into meeting folders that `FsMeetingRepository` owns. The spec does not say whether it honours the meeting `.lock`.
2. **English-only output.** The CLI line `Updated seg 19/10 10:12 after Daily` (`_dx.md:24,138`) puts a code-rendered Portuguese weekday into English CLI output. The notification body is the curator's Portuguese summary (`_dx.md:292`). AGENTS.md allows Portuguese only for LLM-built documents, with a fixed list of label classes (`messages.Minutes`, `messages.StoryDoc`). `messages.ActivityDoc`, Portuguese in a notification body, and the focus lines printed by `trec activities` need to be added to that list, or the CLI should render English weekdays.
3. **Cross-adapter import.** `curator_claude → verifier_claude` (`_spec.md:151`) is outside the allowed LLM-stack exceptions (see issue 015).

Suggested fix: declare `CURATION_ERROR = "curation_error.txt"  # not part of status` in `domain/status.py`. Route `mark_meeting_failed`/`clear_meeting_failed` through `MeetingRepository`, which owns the meeting folder, rather than `ActivityStore`. Add AGENTS.md edits to the Impact Analysis: the Portuguese allowance for `ActivityDoc`, curator notification bodies and printed focus lines; the new ports in the table; the lock/file layout. Or print `Updated Mon 19/10 10:12` in the CLI.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: `domain/status.py` declares every meeting-folder file, AGENTS.md reserves the Portuguese allowance for named label classes, and the `curator → verifier` import was outside the LLM-stack exception (resolved by issue 015).
- Verified: `CURATION_ERROR` in `domain/status.py`; `mark_curation_failed`/`clear_curation_failed`/`curation_error` on `MeetingRepository`; CLI prints English weekdays (`Mon 19/10`); AGENTS.md row lists the Portuguese allowance, ports, commands and layout; UT-109. A separate string-placement conflict inside `domain/activities.py` is reviews-002/issue_004.

### Resolution

Fixed as suggested. `CURATION_ERROR = "curation_error.txt"  # not part of status` goes in `domain/status.py`; `mark_curation_failed` / `clear_curation_failed` / `curation_error` move from `ActivityStore` to `MeetingRepository` (atomic write, no meeting `.lock`, reason stated); the CLI prints English weekdays (`Mon 19/10`) built from the pass record; the Portuguese allowance for `messages.ActivityDoc`, the curator's summary echoed in notification bodies and CLI lines and the printed focus lines is declared in `_dx.md` and listed as an AGENTS.md edit; the Impact Analysis AGENTS.md row now lists all edits (ports table, commands, intro sentence, Portuguese allowance, file layout, restart rule). The cross-adapter import is removed (issue 015). Tests: UT-109 (repository), UT-034/UT-039 updated to use the repository.

