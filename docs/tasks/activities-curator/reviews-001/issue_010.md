---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 283
severity: medium
author: claude-code
provider_ref:
---

# Issue 010: Undo can restore a different pass than the one previewed

## Review Comment

`UndoLastPass` has `preview()` and `execute()` as two separate calls. `execute()` takes no argument and acquires the lock non-blocking at execution time (`_spec.md:282-283`). Between the two calls the CLI shows the diff and waits at `Restore the document to before this pass? [y/N]` (`_dx.md:181-190`). That can take minutes, because the user is reading a diff. The daemon's curator runs a few minutes after every meeting, so a pass N+1 can commit while the prompt is open. `execute()` then undoes pass N+1, which the user never saw. The archive check (`archive_bytes_before`) does not help here, because N+1 is now the last pass and its sizes match.

Result: the user confirms one diff and loses a different pass's edits, plus the "lines you edited after the pass" count shown for N is wrong for N+1. No test covers a pass committing between preview and execute (UT-060–064 and IT-006 run them back to back).

Suggested fix: `preview()` returns the `version` of the pass it describes, and `execute(expected_version: str)` refuses with a new `messages.Cli` line if the last not-undone pass is different. For example: `A new pass ran while you were deciding; run trec activities undo again.` and exit 1. Add a use-case test where the fake store gains a pass between preview and execute.

## Triage

- Decision: `VALID`
- Notes: Valid. `preview()` and `execute()` were separate with no identity link, so a pass committing while the diff was on screen made `execute` undo a pass the user never saw.
- Verified: `UndoPreview` carries `version`, `execute(expected_version)` raises `UndoStale` under the same non-blocking lock, message and exit 1 in `_dx.md`, US-010 AC-5/EC-4, Safety Invariant 7, UT-065/066.

### Resolution

Fixed as suggested. `UndoPreview` carries the pass `version`; `execute(expected_version)` refuses with new `UndoStale` when the last not-undone pass differs (`A new pass ran while you were deciding; run trec activities undo again.`, exit 1), checked under the same non-blocking lock. Spec Core Interfaces, Safety Invariant 7, `_dx.md` (undo notes, Errors table), US-010 AC-5/EC-4. Tests: UT-060/UT-061 updated, UT-065 (pass gained between preview and execute), UT-066.

