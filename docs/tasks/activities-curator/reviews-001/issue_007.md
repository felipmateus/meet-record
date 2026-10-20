---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 472
severity: medium
author: claude-code
provider_ref:
---

# Issue 007: Commit order contradicts the all-or-nothing invariant on failure

## Review Comment

Safety Invariant 3 (`_spec.md:472`) says: "failures leave `atividades.md`, `base.md`, the archive and versions unchanged". The commit order is "versions → archive → document atomic → base → pass log" (`_spec.md:136`). Safety Invariant 6 requires that "every archived text is appended to the archive before the document is replaced". US-011 EC-2 covers "Disk write fails → document unchanged".

If the document replace fails (disk full, a transient TCC errno after `retry_io` gives up, EACCES on Windows), the version files and archive entries are already written, which breaks Invariant 3. The pass record is never written because the pass log comes last. So `undo` cannot truncate those archive entries (it needs `archive_bytes_before` from the record), and `pending()` re-runs the meeting. The re-run archives the same items again, giving duplicate archive entries.

There is a second, smaller window. A crash after the document is written but before `base.md` makes the next `diff(base_old, document)` show the whole previous pass as user edits (see issue 006). The curator then freezes its own lines as user-authored.

Suggested fix: specify the rollback in `ActivityStore.commit`. On any failure after the archive append, truncate each touched archive file back to its recorded size and delete the version files of this pass, then re-raise. Write `base.md` *before* the document replace: a stale document with a new base is harmless, because the pass is re-run and the rerun rule applies. Or relax Invariant 3 to "document and base unchanged; the archive may hold entries that are reconciled by truncation". Add an `FsActivityStore` test where `os.replace` of the document raises → archive size and versions dir unchanged.

## Triage

- Decision: `VALID`
- Notes: Valid. The listed order wrote versions and archive before the document, so a failed replace broke Invariant 3 and left no record to truncate by; a stop between document and base made the next diff misattribute the whole pass to the user.
- Verified: the in-process failure path is all-or-nothing (truncate archive + delete versions before the replace, IT-012) and the document→base window is closed by rolling forward when the document was replaced (IT-013); ADR-003 records the decision. The reconcile branch that rolls forward a document that was never replaced (stop before the replace, then a user edit) is a regression of the fix, tracked as reviews-002/issue_001.

### Resolution

Fixed differently from the suggestion, with a decision record (ADR-003). The suggestion to write `base.md` before the document is not harmless: a stale document against a new base reads as the user deleting everything the pass added (archived as `removido por você` or treated as an editor overwrite). Instead: order versions (incl. `_base`, `_pass.json`) → archive (sizes recorded first) → document → base → pass-log line, the last being the commit point; an exception inside the process undoes (truncate archive to recorded sizes and delete version files before the replace, retry remaining steps after it); after a hard stop `lock()` reconciles on entry (roll back only when the document is byte-identical to `_before`, otherwise roll forward). Undo restores the document before truncating the archive. Spec: Key Decisions, Safety Invariants 3, 6, 7, Core Interfaces (`ActivityStore.commit/lock`), Known Risks; `_user_stories.md` US-011 EC-2/EC-3; new `adrs/adr-003.md`. Tests: IT-012 (replace raises → archive and versions unchanged), IT-013, IT-014, IT-015.

