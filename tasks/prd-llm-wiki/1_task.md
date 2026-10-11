# Task 1.0: Spike — a manual LLM wiki over the existing meetings (gate G1)

## Overview

Before writing code, build the wiki by hand with Claude Code over the 13 real meetings, with a hand-written `CLAUDE.md`, and let the user judge whether the person and project pages are correct and useful. The spike produces the first `prompts/wiki_schema.md`, the numbers that size the limits, the `send_transcript` default and the first ten real questions with answers for the evaluation. If the pages are not useful, the feature stops here and the reason is recorded.

<skills>
### Skills compliance

- `prompt-engineering-patterns`: the schema is a prompt; iterate on it with real output, keep the rules short and testable.
- `verification-before-completion`: the go/no-go is the user's verdict on real pages, not an impression from one run.
</skills>

<requirements>
- Nothing under `src/` or `tests/` changes. The wiki is built in `data/wiki-spike/` (ignored by Git); no real page content is copied into the repository.
- Uses the user's Claude Code subscription and real meeting content: ask for approval before the first run, and again before each full re-ingest.
- Ingest in chronological order, one meeting at a time, from `minutes.md` first; then repeat two meetings with `transcript.txt` to compare page quality (techspec §9.2).
- Record the answers to techspec §9 (1–5) in the techspec itself, including the counts (pages touched per meeting, largest page) and the user's verdict with examples of what was right and wrong.
- The resulting `CLAUDE.md` becomes `prompts/wiki_schema.md` (English rules, Portuguese page content), reviewed so it works both as the ingest system prompt and as the wiki's own `CLAUDE.md`.
- The user writes ten questions with answers in `data/wiki-eval/questions.toml` (format in evaluation.md §5), answer key before any model answer.
</requirements>

## Subtasks

- [x] 1.1 Draft `data/wiki-spike/CLAUDE.md`: page types, sections per type, conventions (current value first, `Histórico`, `[[meetings/<id>]]` citations with timestamps, `⚠️ Conflito`), ingest, query and lint workflows, Brazilian Portuguese content.
- [x] 1.2 With the user's approval, ingest the 13 meetings oldest first from `minutes.md` (Claude Code interactive, in the spike folder); keep `index.md` and `log.md` as the pattern asks.
- [x] 1.3 Re-ingest two meetings with the transcript as the source and compare the pages; decide the `send_transcript` default.
- [ ] 1.4 Review the pages with the user: correct facts, wrong facts, missing cross-references, usefulness per page type; count pages touched per meeting and page sizes.
- [ ] 1.5 Ask the ten first real questions interactively (Claude Code in the spike folder) and record whether the answers were right; the user writes the answer key in `data/wiki-eval/questions.toml` first.
- [ ] 1.6 Write `prompts/wiki_schema.md` from the final `CLAUDE.md`; fill techspec §9; write the go/no-go in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (one paragraph, dated).

## Implementation details

The spike folder is `data/wiki-spike/` so it never collides with the future `data/wiki/`. Obsidian can be pointed at it to see the graph (hubs and orphans) during the review. When the schema uses a Portuguese section name, it is a label of the user's document, which the conventions allow; the rules themselves stay in English.

## Success criteria

- The user confirms, on real pages, that at least the project pages are accurate and would save re-reading minutes (gate G1), or the plan is stopped with the reason recorded.
- `prompts/wiki_schema.md` exists and reads as a complete instruction set for both ingest and query.
- Techspec §9 has the five answers with numbers; `data/wiki-eval/questions.toml` has ten questions with answers.

## Task tests

- [ ] Unit tests — not applicable (no code).
- [ ] Integration tests — not applicable.
- [ ] E2E tests — the manual review itself; its outcome is the gate.

## Relevant files

- `data/wiki-spike/` (new, ignored), `prompts/wiki_schema.md` (new)
- `tasks/prd-llm-wiki/techspec.md` §9, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10
- `data/wiki-eval/questions.toml` (new, ignored)
