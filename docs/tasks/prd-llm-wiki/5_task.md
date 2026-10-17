# Task 5.0: Claude wiki writer and the ingest prompt

## Overview

Implement `ClaudeWikiWriter` over the shared `StructuredTransport`: two schema-constrained calls (plan, then compose), user messages built from the analysis, the transcript, the index and the selected pages, the schema file appended to the system prompt and re-read on every call, and a deterministic mapping of the model's output to `PageEdit`s. Write `prompts/wiki_ingest_system.md`, the contract for the two calls, alongside the schema from task 1.

<skills>
### Skills compliance

- `prompt-engineering-patterns`: explicit output contract, no invention, merge-not-replace rules, examples of slugs; the prompt is versioned in `prompts/`.
- `python-pro`: Pydantic models with field descriptions from `messages.Prompt`; `strict_schema` as the other adapters.
- `python-testing-patterns`: message builders and mapping tested without the model; one opt-in real call.
</skills>

<requirements>
- `adapters/outbound/wiki_claude.py` as in techspec §5.3: `PageRefOut`, `PlanOut`, `PageOut`, `ComposeOut`; `ClaudeWikiWriter(transport, schema_path, prompt_path, user_name, max_pages)` with `_system()` (ingest prompt + `Prompt.WIKI_SCHEMA_HEADER` + schema, missing/empty schema → `AnalysisError`), `plan()`, `compose()`, `to_edits()`; `build_plan_message()` and `build_compose_message()` as module functions (user name, meeting header, index, analysis JSON, transcript when present, previous pages on force, plan notes and refs, the pages' full text).
- Tags `wiki-plan:<id>` and `wiki-compose:<id>`, `extra={"meeting": id}` for the usage log.
- `prompts/wiki_ingest_system.md` (English): the two-call contract; only facts from the meeting; full page content, merging into the existing text, moving changed values to the history with the meeting link and timestamp; never write meeting pages; ASCII slugs with transliteration examples (`João Silva` → `joao-silva`); respect the limits; Brazilian Portuguese prose; when the schema and these rules disagree on format, the schema wins, these rules decide the contract.
- Field descriptions and section headers in `messages.Prompt` (`FIELD_WIKI_*`, `WIKI_*`).
- `tests/fixtures/fake_claude_cli.py` answers both schemas (by inspecting `--json-schema`), with a `FAKE_CLAUDE_MODE=wiki_bad_slug` variant.
</requirements>

## Subtasks

- [ ] 5.1 Write `prompts/wiki_ingest_system.md`; review `prompts/wiki_schema.md` so both read as one instruction set.
- [ ] 5.2 Implement the output models and `ClaudeWikiWriter`.
- [ ] 5.3 Implement the message builders and `to_edits`.
- [ ] 5.4 Extend `fake_claude_cli.py` for the two wiki schemas.
- [ ] 5.5 Write the tests below; run the opt-in real call on one fixture meeting with the user's approval.

## Implementation details

Follow `stories_claude.py`: the guide-like file (`wiki_schema.md`) is appended on every call; the model may only reference pages by type and slug, never by path; an unknown type or an invalid slug is passed through to `validate_edits` as an edit that will be rejected with a reason, so a prompt regression shows up in `wiki.json` and the log instead of as an exception. The transcript goes last in the message (largest block, least structured); the index goes first after the header so the model picks pages before reading content.

## Success criteria

- `build_plan_message` contains the header, the index, the analysis JSON and (when given) the transcript and the previous pages, in that order; `build_compose_message` adds the plan and each page under its path.
- `to_edits` maps every field, trims whitespace, and keeps an unknown type as a rejectable edit.
- The real opt-in call on `tests/fixtures/sample_meeting_rich.json` returns a plan with at least one page to create and a compose with valid slugs (recorded in the task notes, not asserted on content).
- `pytest`, `mypy` and the strings guard clean.

## Task tests

- [ ] Unit tests — `tests/unit/test_wiki_claude.py` (new): messages, schema tightening, `to_edits`, missing schema, tags.
- [ ] Integration tests — none new (the CLI integration arrives in task 6 with the fake `claude`).
- [ ] E2E tests — `TREC_REAL_CLAUDE_CLI=1 pytest -m slow tests/integration/test_wiki_claude_real.py` (new, one meeting, structure asserted only).

## Relevant files

- `src/teams_recorder/adapters/outbound/wiki_claude.py` (new), `messages.py`
- `prompts/wiki_ingest_system.md` (new), `prompts/wiki_schema.md`
- `tests/fixtures/fake_claude_cli.py`, `tests/unit/test_wiki_claude.py` (new), `tests/integration/test_wiki_claude_real.py` (new)
