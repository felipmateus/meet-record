---
status: completed
title: "Task 1: Progress statements in the analysis, verifier and minutes"
type: feature
complexity: medium
---

# Task 1: Progress statements in the analysis, verifier and minutes

## Overview

The existing analysis call learns to extract what a meeting said about pre-existing work (`status_updates`: done, in progress, blocked, delayed, date changed, reassigned, cancelled, with who, the literal quote and the time) and who each action is for (`for_whom`). The verifier checks each statement like any other claim, and the minutes gain a `🔄 Andamento informado` section. This is the input the curator needs to put progress on the right item; the analyzer stays unaware of the activities document.

## Shippable Outcome

- Outcome: a newly analyzed meeting's `analysis.json` carries `status_updates` and `for_whom` (only when non-empty), each status update has a verifier verdict, and `minutes.md` lists them with ⚠️ and the reason when unconfirmed; old `analysis.json` files load and re-save unchanged.
- Verify in this task: UT-028, UT-050–UT-055, UT-057–UT-059 on fakes; existing `tests/unit/test_llm_claude.py`, `test_verification.py`, `test_verifier_claude.py`, `test_minutes_markdown.py` stay green.
- Integration verification: Q-001 (status-update precision/recall and verifier injection) runs in task_08 with the user's approval.

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`domain/models.py` block: `StatusChange`, `StatusUpdate`, `Analysis.status_updates`, `Action.for_whom`, `ClaimKind.STATUS_UPDATE`; `domain/excerpts.py`), › Data Models (the `status_updates` and `for_whom` rows, the derived `Claim` of kind `STATUS_UPDATE`, the `AnalysisOut` and verifier notes), and `_dx.md` › `minutes.md` (new section, exact line shape).
- Only the `domain/models.py` additions listed for the analyzer belong here; `UserStory.source_text`, `SkippedAction.source_line` and the `is_task_card` change belong to task_13, the `ActionStatus.OVERDUE` change to task_14.
- `who` is `Llm.OWNER_SELF`, a name, or `Llm.OWNER_UNKNOWN`; `evidence` ≤ 20 words with hedges kept; an intention is not progress (prompt rule).
- Strict schema: `StatusUpdateOut` and `ActionOut.for_whom` in `llm_schema.py`, `additionalProperties=false`, field descriptions in `messages.Prompt`.
- Codec writes the new keys only when non-empty/non-null; absent keys decode to `[]` / `None`.
- Verifier: `domain/verification.claims`, `_claim_verification` and `with_verifications` gain a `STATUS_UPDATE` branch keyed by position; claim `text = "<change>: <about> — \"<evidence>\""` (`reassigned to <new_owner>: …` for reassignments), `owner = who` (no owner for `indefinido`), `due = new_due`, `at = at`; `prompts/verify_system.md` gains the two axes (does the quote support the change; is the new date/owner what was said).
- `domain/excerpts.excerpt_window` is pure; `verifier_claude.transcript_for` keeps its output identical and calls it (the head-of-transcript part becomes `head_chars`). No adapter imports another adapter for this.
- Minutes labels (Portuguese) in `messages.Minutes`; the section comes after the actions.
- The analyzer runs in the daemon: do not run `trec agent restart`; task_08 asks the user for it.

## Subtasks

- [x] 1.1 Domain: `StatusChange`, `StatusUpdate`, `Analysis.status_updates`, `Action.for_whom`, `ClaimKind.STATUS_UPDATE`; exports.
- [x] 1.2 `llm_schema.py` (`StatusUpdateOut`, `ActionOut.for_whom`, `to_domain`), `messages.Prompt` descriptions, progress cues and rules in `prompts/analyze_system.md`.
- [x] 1.3 Codec round trip with the new keys omitted when empty.
- [x] 1.4 `domain/excerpts.py`; `transcript_for` reuses it with unchanged output.
- [x] 1.5 Verifier branch for `STATUS_UPDATE`, `describe(claim)` carrying change, quote and new date, prompt axes.
- [x] 1.6 Minutes section `### 🔄 Andamento informado` with ⚠️ + reason on unconfirmed lines.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/models.py:176-300` — `ActionStatus`, `ClaimKind`, `Action`, `Analysis`.
- `src/teams_recorder/domain/verification.py` — `claims`, `_claim_verification`, `with_verifications`.
- `src/teams_recorder/adapters/outbound/llm_schema.py:37-114` — `ActionOut` / `AnalysisOut` / `to_domain`.
- `prompts/analyze_system.md` — cues section for the progress cues.
- `src/teams_recorder/adapters/outbound/codec.py` — analysis codec (defaults on old files).
- `src/teams_recorder/adapters/outbound/verifier_claude.py:77-104` — `transcript_for` windowing to move into `domain/excerpts.py`.
- `prompts/verify_system.md` — the two new axes.
- `src/teams_recorder/adapters/outbound/minutes_markdown.py`, `src/teams_recorder/messages.py` (`Minutes`, `Prompt`).

### Dependent Files

- `src/teams_recorder/application/use_cases/activities.py` (task_05) builds `MeetingContext.excerpts` with `excerpt_window` and counts `status_updates` for the empty-analysis rule.
- `src/teams_recorder/adapters/outbound/curator_claude.py` (task_04) renders `n.u1` refs and `p/ <quem>` from these fields.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — the analyzer stays document-unaware; the curator does all matching.

## Deliverables

- Domain, schema, prompt, codec, verifier, excerpt and minutes changes with their tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-050, UT-051, UT-055 — schema mapping (`new_due` date, `for_whom`) and the codec on old files.
- [x] UT-052, UT-057, UT-058, UT-059 — verifier claims, claim text per change kind, message content and prompt axes, an intention planted as `done` unconfirmed.
- [x] UT-028, UT-053 — `excerpt_window` and `transcript_for` unchanged after the move (UT-053's clause about `CurateMeetings` is a requirement of task_05, which builds its excerpts with the same function).
- [x] UT-054 — minutes section.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- The fixture analyses in `tests/fixtures/` (`sample_analysis.json`, `sample_analysis_v2.json`) load with empty `status_updates` and no `for_whom`, and saving them adds no key.
