---
provider: manual
pr:
round: 3
round_created_at: 2026-10-22T00:30:08Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 332
severity: low
author: claude-code
provider_ref:
---

# Issue 002: Docs-sync list misses pages that describe the pinned language

## Review Comment

The docs row of the Impact Analysis (`_spec.md:332`) is the task-6 list. It names `REQUIREMENTS` row 12 and §10, `docs/prd/pages/02-transcription.md`, `docs/guide/configuration.md`, `docs/guide/troubleshooting.md` and the AGENTS.md ports table. AGENTS.md says to "Keep `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 … and `docs/prd/` in sync when … a behavior changes". A grep finds more pages that this feature makes false:

- `docs/prd/appendix/data-layout.md:51-56`: the `transcript.json` shape and its field notes, with no `language_detection`.
- `docs/prd/appendix/integrations.md:8`: the whisper-cli row shows only `-l pt … -np`. The new `-l auto -dl -f …` call (never `-np`) is a second use of the tool with its own failure mapping.
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md:136`: the adapter catalogue describes `WhisperCppTranscriber` as `-l pt` and has no entry for `WhisperCppLanguageDetector`.
- `README.md:7`: "Meetings are in Brazilian Portuguese".
- `AGENTS.md:133`: "(meetings are held in Brazilian Portuguese, so prompts must keep asking for Portuguese output …)". Item 5 of reviews-002 issue 001 asked for this line to be added to the docs row. The fix did not apply it: the row still says only "AGENTS.md (ports table)".
- `docs/guide/commands.md:12`: the `trec transcribe` row says the command prints speaker labels and does not mention the new `Language:` line.

Failure mode: task 6 follows the list, so these pages would ship stating the old behavior (`-l pt` only, no `language_detection` in `transcript.json`). The agent guidance in AGENTS.md would keep saying that meetings are Portuguese.

Suggested fix: add the six locations to the docs row in `_spec.md:332`. Optionally add `docs/prd/appendix/enum-dictionary.md`, a section for `LanguageReason` like the other stored enums.

## Triage

- Decision: `VALID`
- Notes: Valid. Each of the six locations states the pinned-Portuguese behavior or a `transcript.json` shape without `language_detection`, and task 6 follows the Impact row. AGENTS.md:133 was item 5 of reviews-002 issue 001 and was not applied.
- Verified: `docs/prd/appendix/data-layout.md:51-56`, `docs/prd/appendix/integrations.md:8`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md:136`, `README.md:7`, `AGENTS.md:133`, `docs/guide/commands.md:12`; `docs/prd/appendix/enum-dictionary.md` has a section per stored enum.
- Verified (round 4, 2026-10-22): the docs Impact row (`_spec.md:333`) lists all six locations plus `enum-dictionary.md` and says what changes in each. File References (`_spec.md:436`) list them. Every location was re-checked: `data-layout.md:51-56`, `integrations.md:8`, `REQUIREMENTS:136`, `README.md:7`, `AGENTS.md:133`, `guide/commands.md:12`. Three further pages about curator and PRD content that a grep found are new in round 4 (reviews-004 issue 001). They are not a gap in this fix.

### Resolution

`_spec.md` docs Impact row lists the six locations plus `enum-dictionary.md` (a `LanguageReason` section), with what changes in each; File References list them.
