---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_tests.md
line: 38
severity: low
author: claude-code
provider_ref:
---

# Issue 019: Several story criteria have no test case in the coverage matrix

## Review Comment

Some acceptance criteria and edge cases in `_user_stories.md` have no matching case in `_tests.md`. In each instance below, a test that the spec could carry would catch a regression:

- **US-012 AC-2** (`_user_stories.md:230`): "my edit removed a line a pass edit targets → that edit fails and goes to the one retry; my edit wins". IT-005 (`_tests.md:138`) only adds a user edit *elsewhere*. UT-006 likewise. No case deletes or changes an op's target between snapshot and apply.
- **US-014 AC-3** (`_user_stories.md:259`): "writer skips it → tag stays and the CLI prints the reason". UT-070–074 cover draft, numbering, duplicate, edited line and no tag, but not skip.
- **US-014 EC-4** (`_user_stories.md:268`): busy curator lock during `trec stories`. Not covered; see issue 011.
- **US-016 EC-2** (`_user_stories.md:298`): `waiting for the curator…` printed while a pass runs. IT-007 checks blocking at the use-case level only, not the CLI message.
- **US-019 AC-2** (`_user_stories.md:337`): "only touched others' items or context → no notification". UT-044 tests that `notify=False` is honoured, but whether the curator sets it is prompt behaviour, and it has no Q-002 target.

Suggested fix: add UT/IT ids for the first four, e.g. `UT-0xx apply_ops on F' where the target line was deleted by the user → OpFailure("not found"), repair receives it`. Add a Q-002 target for notification precision (passes touching only others/context with `notify=false` ≥ 95%). Add the new rows to the coverage matrix.

## Triage

- Decision: `VALID`
- Notes: Valid. The five criteria listed had no case in `_tests.md`; US-012 AC-2 in particular was only covered by "user edit elsewhere".
- Verified: UT-046 and IT-016 (target deleted by the user), UT-075 (writer skip), UT-076/077 and IT-017 (busy lock), UT-089/105 (`waiting for the curator…` via `on_wait`), Q-002 notification precision >= 95% both ways; coverage matrix rows present.

### Resolution

Fixed. New cases: UT-046 and IT-016 (US-012 AC-2, the target deleted by the user), UT-075 (US-014 AC-3 skip), UT-076/UT-077/IT-017 (US-014 EC-4), UT-089 and UT-105 (US-016 EC-2 CLI message through a new `on_wait` callback on `CurateMeetings.execute`), and a Q-002 notification-precision target (≥ 95% both ways) for US-019 AC-2. Coverage matrix rows added or extended; `Safety Invariants 1–12` row updated. All 19 US-NNN still appear in `_tests.md`.

