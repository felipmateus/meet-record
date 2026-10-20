---
status: completed
title: "Task 2: The pure document functions"
type: feature
complexity: high
---

# Task 2: The pure document functions

## Overview

Gives the feature its one code rule and its document vocabulary as pure functions: `apply_ops` applies the curator's `replace` / `insert_after` / `move` / `archive` edits to whole lines of the body and rejects, edit by edit, any edit that changes a checkbox state or removes a checkbox line without `archive`; the box, its pass stamp, the link block, the calendar strip, the body diff and the working-day arithmetic are rendered and read from a `DocFormat`. Every later task (store, curator, use case) builds on these types; nothing user-visible changes yet.

## Shippable Outcome

- Outcome: `apply_ops(fmt, document, ops)` returns the edited text, the archived texts with reasons and one `OpFailure` per rejected edit, with every untouched line byte-identical; `render_box` / `box_stamp` / `body_span` / `render_links` / `rescue_box_lines` / `calendar_strip` / `unified_diff` / `working_days_ago` behave as `_spec.md` › Core Interfaces states; `doc_format()` builds the `DocFormat` from the real constants.
- Verify in this task: the table-driven unit tests listed below, no fakes.
- Integration verification: none (consumers: task_03 reconciles with `box_stamp`; task_04 serializes `Op`/`CuratorOutput`; task_05 runs a pass with these functions).

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`domain/activities.py` block: `OpKind`, `Op`, `OpFailure`, `Applied`, `DocFormat`, the function signatures and the per-op rule comments, `PassKind`, `MeetingContext`, `RemovedItem`, `IgnoredRef`, `CuratorInput`, `CuratorOutput`, `PassRecord`), › Business Rules (Open-line rule, checkbox regexes), › Architectural Boundaries (`DocFormat`), Safety Invariants 1, 4, 5.
- `domain/activities.py` imports only the standard library and `domain`; never `messages` or `constants`, and no string literal containing the recordings folder name (UT-116 checks it by AST). `test_no_hardcoded_strings` passes with no allowance for the module.
- `doc_format()` lives in `application/use_cases/activities.py` (created here with only this function; task_05 adds the use cases) and builds the `DocFormat` from `messages.ActivityDoc` (Portuguese markers, headings, box labels, weekdays, `(hoje)`), `constants.Parse` (open/ticked regexes), `constants.Activities.SKELETON_STAMP` (`00000000-000000`), `constants.Files.RECORDINGS_DIR` and `domain.status.MINUTES`.
- Failure strings of `OpFailure.error` are the closed set in Core Interfaces; keep them as domain constants (a `StrEnum` or module constants), since the domain imports nothing outside itself.
- `tagged_blocks`, `replace_tag` and `TaggedBlock` are not part of this task: task_13 adds them with their consumer.
- Matching ignores trailing whitespace only (UT-009); targets and anchors are matched inside the body only (box and link block excluded).

## Subtasks

- [x] 2.1 Types: `OpKind`, `Op`, `OpFailure`, `Applied`, `DocFormat`, `PassKind`, `MeetingContext`, `RemovedItem`, `IgnoredRef`, `CuratorInput`, `CuratorOutput`, `PassRecord`; exports from `domain/__init__.py`.
- [x] 2.2 `body_span`, `body_text`, `box_stamp` (stamp optional in the closing marker), `open_count`, `ticked_count`.
- [x] 2.3 `apply_ops` with the per-op rule, `move` byte-for-byte with its anchor errors, failures that leave the text unchanged and let later ops apply.
- [x] 2.4 `render_box` (header, numbered focus, stamp in the closing marker, returns the user's box lines), `rescue_box_lines`, `render_links`.
- [x] 2.5 `calendar_strip`, `working_days_ago`, `unified_diff`.
- [x] 2.6 `messages.ActivityDoc`, `constants.Parse`, `constants.Activities` (`SKELETON_STAMP`), `doc_format()`; Portuguese fixtures in `tests/fixtures/activities/`.
- [x] 2.7 Unit tests.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/models.py` — `Analysis`, `TranscriptHealth` referenced by `MeetingContext`.
- `src/teams_recorder/domain/status.py:11-23` — `MINUTES` used by `doc_format()`.
- `src/teams_recorder/constants.py:80-170`, `src/teams_recorder/messages.py` — where `Parse`, `Activities`, `ActivityDoc` go.
- `tests/unit/test_no_hardcoded_strings.py` — the string gate.
- `_dx.md` › Files — the document as the user sees it (box, sections, link block) for fixtures.

### Dependent Files

- `src/teams_recorder/adapters/outbound/activities_fs.py` (task_03), `curator_claude.py` (task_04), `application/use_cases/activities.py` (task_05).

### Related ADRs

- [ADR-001](adrs/adr-001.md) — edit operations and the one rule; no whole-document backstop (UT-025 withdrawn).
- [ADR-003](adrs/adr-003.md) — the stamp in the box's closing marker.

## Deliverables

- `src/teams_recorder/domain/activities.py`, `doc_format()` in `src/teams_recorder/application/use_cases/activities.py`, the `messages` / `constants` additions, fixtures and unit tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-001, UT-002, UT-003, UT-006, UT-007, UT-008, UT-009 — `apply_ops` matching: found once, not found, ambiguous, re-read document, box/link-block targets, 150 items, trailing whitespace.
- [x] UT-004, UT-005, UT-019, UT-020, UT-021, UT-022, UT-023, UT-024, UT-029 — the per-op checkbox rule, `move`, drop-and-add, rule evaluated on the current text.
- [x] UT-112, UT-113, UT-114, UT-115 — the documented limit, `move` ordering and anchors, anchor errors, replace then move.
- [x] UT-010, UT-011, UT-117 — `render_box`, box lines, `box_stamp`.
- [x] UT-012, UT-013, UT-014 — `render_links`.
- [x] UT-015, UT-018, UT-026, UT-027 — `unified_diff`, `calendar_strip`, `working_days_ago`, `rescue_box_lines`.
- [x] UT-116 — the import boundary and `doc_format()` round trip.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green with no allowance for `domain/activities.py`.
