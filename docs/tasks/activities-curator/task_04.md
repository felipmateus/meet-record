---
status: completed
title: "Task 4: The Claude curator and its prompt"
type: feature
complexity: high
---

# Task 4: The Claude curator and its prompt

## Overview

Implements the agent that does all the judgment: `ClaudeCurator` sends the current document, the new analyses with refs, transcript excerpts, a 14-day calendar, the user's edits, box lines, the last summary and recent archive entries, and maps the strict JSON answer to edits, removed items, focus, summary, notify and ignored refs; `repair` sends the failed edits back once. `prompts/curate_system.md` holds every rule of routing, ownership, retention and format. Code never parses item lines; the quality of the document is decided here.

## Shippable Outcome

- Outcome: `ClaudeCurator.curate(CuratorInput)` returns a `CuratorOutput` and `ClaudeCurator.repair(data, current, failures)` returns ops, over either transport (`api` or `claude-code`), with usage tags `curate:<first meeting id>` / `curate-repair:<first meeting id>`; transport errors surface as `AnalysisError`.
- Verify in this task: the adapter cases listed inline below, through the fake API transport and `tests/fixtures/fake_claude_cli.py`.
- Integration verification: IT-008 (curator + repair through `fake_claude_cli.py` in a committed pass) in task_06; Q-002 (curator sequence evaluation) in task_08.

## Requirements

- Contracts: `_spec.md` › Curator message and prompt (user-message order and tags, the normative content 1–11 of `prompts/curate_system.md`, the `<task>` checklist), › Data Models (`CuratorOut` strict schema), › Integration Points (transport, error mapping, no retry beyond one repair), › Business Rules (all rules the prompt carries); `_dx.md` › Files (line formats, markers, archive reasons).
- `ActivityCurator` Protocol from task_03; input/output types from task_02; `status_updates` / `for_whom` from task_01.
- Refs: `n.a1` (user's actions), `n.o1` (others'), `n.u1` (status updates), `n.p1` (deadlines), `n.n1` (next meetings), `n.d1` (decisions), `n.q1` (questions), `n.r1` (risks), each with `at` and `⚠️ unconfirmed: <reason>` when the verifier did not confirm; the meeting block names transcript health when degraded.
- Prompt in English, asking for Portuguese output; the user is addressed as "você", never "usuário". Include the worked example (input excerpt and the complete JSON answer) described in item 10.
- `curator_claude.py` imports only `llm_schema` helpers and `llm_transport` from other adapters; the `anthropic` SDK stays lazily imported. Schema field descriptions in `messages.Prompt`; XML tag names and fixed message fragments in `constants` / `messages` per the string rule.
- Model and effort come from the caller (task_06 wires `[activities] model` / `cli_model` / `effort`).

## Subtasks

- [x] 4.1 `CuratorOut` Pydantic schema (`additionalProperties=false`) and mapping to `CuratorOutput` / `Op`.
- [x] 4.2 `build_user_message` in the specified order; repair message (current text + failures with `error` and `detail`).
- [x] 4.3 `ClaudeCurator.curate` / `repair` over `StructuredTransport` with usage tags.
- [x] 4.4 `prompts/curate_system.md` with items 1–11.
- [x] 4.5 Adapter tests.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/outbound/llm_claude.py`, `stories_claude.py`, `verifier_claude.py` — patterns for a `StructuredTransport` client and message builder.
- `src/teams_recorder/adapters/outbound/llm_schema.py`, `llm_transport.py` — schema helpers, transports, usage log.
- `prompts/analyze_system.md`, `prompts/verify_system.md` — prompt house style.
- `tests/fixtures/fake_claude_cli.py`, `tests/unit/test_llm_transport.py`, `tests/unit/test_stories_claude.py` — fakes and test patterns.

### Dependent Files

- `src/teams_recorder/container.py` (task_06) builds it.
- `scripts/fidelity_eval.py` (task_08) runs it in the sequence evaluation.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — edits, not a rewrite; the prompt carries identity rules the code cannot check.

## Deliverables

- `src/teams_recorder/adapters/outbound/curator_claude.py`, `prompts/curate_system.md`, `messages.Prompt` entries, tests.

## Tests

`_tests.md` assigns no ID to the adapter alone (IT-008 is task_06's). Cases owned here (from `_spec.md` › Testing Approach):

- [x] The user message contains, in order, `<document>`, one `<meeting>` block per meeting oldest first with the refs above, `<excerpts>`, `<calendar>`, `<user_edits>`, `<box_lines>`, `<last_pass>`, `<recent_archive>`, `<task>`; an unconfirmed action shows `⚠️ unconfirmed: <reason>`.
- [x] A scripted answer with one op of each kind, `user_removed`, `focus`, `summary`, `notify`, `ignored` maps field by field to `CuratorOutput`; `text`/`reason`/`anchor` null map to `None`.
- [x] The generated schema is strict (`additionalProperties: false` at every object level).
- [x] `repair` sends the in-memory text and each failure's `error` and `detail` and returns only ops; it logs under `curate-repair:<id>`.
- [x] The same answer through `ClaudeCodeTransport` (`fake_claude_cli.py`) and the API fake transport gives the same `CuratorOutput`; a refusal, truncation or schema violation raises `AnalysisError`.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- No real model call in this task (any `TREC_REAL_*` run needs the user's approval and is not required here).
