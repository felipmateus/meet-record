---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 299
severity: low
author: claude-code
provider_ref:
---

# Issue 008: PassRecord lacks the post-pass archive size undo checks against

## Review Comment

Safety Invariant 7 says undo "never truncates an archive that changed after the pass". US-010 EC-2, `_dx.md` › undo and UT-062 (`_tests.md:142`) implement this as: "archive size ≠ post-pass size → archive untouched".

`PassRecord` (`_spec.md:283-301`) stores only `archive_file` and `archive_bytes_before`. Nothing records the archive's size after the pass's append. `ActivityStore` has no method that returns it, and the appended bytes are not stored. As specified, `UndoLastPass` cannot tell "nothing appended since" from "another pass or the user appended". UT-062 cannot be written against the specified fields.

Suggested fix: add `archive_bytes_after: int | None` to `PassRecord`. `commit` fills it after the append and writes it in `_pass.json` and the pass-log line. Then state the check as `size(archive_file) == archive_bytes_after`. Mention it in the Data Models table.

## Triage

- Decision: `VALID`
- Notes: Valid. `PassRecord` stored `archive_bytes_before` only, so undo could not compare the archive's post-pass size and UT-062 could not be written.
- Verified (round 3): `PassRecord.archive_bytes_after` appears in Core Interfaces, the Data Models table and `truncate_archive` ("only while its size == archive_bytes_after"). `commit` knows the value before it writes `_pass.json`. UT-062 and IT-015 assert it.

### Resolution

Fixed: `PassRecord.archive_bytes_after` (size before + appended bytes, known before `_pass.json` is written, also in the pass-log line); undo's check is `size(archive_file) == archive_bytes_after` inside `ActivityStore.truncate_archive`. Data Models table, Core Interfaces, `_dx.md`, UT-062 rewritten, IT-015.

