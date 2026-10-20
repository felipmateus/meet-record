---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/adrs/adr-003.md
line: 17
severity: high
author: claude-code
provider_ref:
---

# Issue 001: Reconcile rolls forward a document that was never replaced

## Review Comment

ADR-003 (`adrs/adr-003.md:17`, `_spec.md:605`, Safety Invariant 3 at `_spec.md:628`) tells `lock()` what to do with a version triple that has no pass-log line. It rolls the commit back only when the document is byte-identical to `_before`. In every other case it rolls forward, writing `base.md` from `_base` and appending the pass-log line. IT-014 (`_tests.md:202`) requires this: "a document edited by the user after such a stop (neither `_before` nor `_after`) is rolled forward instead". The stated reason is "a surplus archive entry is harmless and a missing one is not" (ADR-003 Risks, `:55`: "the safe direction"). That reason looks only at the archive. It ignores `base.md`.

Failure mode: the process stops after the archive append and before the document replace (a SIGKILL, `launchctl bootout` while `retry_io` is sleeping between retries, a power loss). Later the user edits `atividades.md`, which they do every day. So the document is neither `_before` nor `_after` when the next pass takes the lock, and reconcile rolls forward:

- `base.md` becomes `_base`, which contains everything the pass added. The document never received those lines.
- The next `<user_edits>` = `diff(_base, document)` shows every line the pass added as **deleted by the user**. The lines the pass archived, still in the document, show as **re-added by the user**.
- The pass-log line marks the 1–4 meetings as successfully curated. So `pending()` and `not_curated()` never list them again.

Simulated with the rule exactly as written (scratchpad `sim/rule_sim.py`):

```
reconcile decision: roll forward
next pass <user_edits> after roll forward: ['-- [ ] New item from M1 · [M1][m1]', '+- [ ] Ligar para o João']
```

Following Principle 1, the curator then archives the meetings' new items as `removido por você`, or applies the editor-overwrite heuristic. Either way the items leave the user's view, no retry is pending, and the reason given is false. This is the Motivating Problem, and it is the exact damage ADR-003 rejected in Alternative 2 ("a stale document against a new base reads as the user deleting everything the pass added"). It breaks US-011 EC-3 ("the curator never mistakes its own lines for mine") and Safety Invariant 3.

Of the four cases (stop before or after the replace, user edited or not), three are correct. The wrong one is stop before the replace followed by a user edit. A byte comparison cannot tell it apart from stop after the replace followed by a user edit.

Suggested fix: make "was the document replaced?" observable. For example, write an empty marker `versions/<v>_replaced` immediately after the atomic replace, before `base.md`. Reconcile then works as follows:
- marker present, or document == `_after` → roll forward;
- otherwise → roll back (truncate the archive, delete the triple). The meetings then have no successful record, so `pending()` retries them.

Update ADR-003 (Decision, Risks), `_spec.md` Key Decisions and Safety Invariant 3, and IT-014: "neither `_before` nor `_after`, no marker → rolled back; with the marker → rolled forward". Also state that `commit` measures the archive size before it writes `_pass.json`. Today step 1 writes `_pass.json`, but `_spec.md:605` records the size only at step 2, and the rollback reads it from `_pass.json`. Finally, say that `passes()` treats a torn last JSONL line as absent, since the pass-log line is the commit point.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified against ADR-003 and the old Key Decisions: byte equality with `_before` cannot distinguish stop-before-replace plus user edit from stop-after-replace plus user edit, so the second-to-last case rolled forward a document that was never replaced and the next diff read the pass's items as deleted.
- Verified (round 3): the rule is the same in ADR-003 Decision ("the document was replaced iff its box stamp equals the stamp of the set's `_after`"), Key Decisions, Safety Invariant 3 and `ActivityStore.lock`. For each of the four cases (stop before or after the replace, document edited or not) I checked that the stamp in the box decides correctly. `commit` measures both sizes before `_pass.json`, and `passes()` drops a torn last line (UT-125). IT-019 covers a stop before the replace followed by a user edit. Some wording gaps for undo records remain; they are tracked in reviews-003/issue_002.

### Resolution

Fixed with the simplest observable: the box's closing marker carries the pass stamp (the version), written by `render_box` into the document the pass replaces. Reconcile: document stamp == stamp of `_after` → roll forward, else roll back. No extra file, no gap, independent of user edits. A `_replaced` marker file was rejected (a stop between replace and marker, then a user edit, is still ambiguous). Also stated: `commit` measures archive sizes (before and after) before writing `_pass.json`; `passes()` treats a torn last line as absent. Updated: ADR-003 (Decision, Alternatives 4 and 5, Consequences, Risks), `_spec.md` (Key Decisions, Invariant 3, DocFormat/`box_stamp`, ActivityStore), `_dx.md` (box example, user note), IT-013, IT-014, new IT-019, UT-117, UT-125.

