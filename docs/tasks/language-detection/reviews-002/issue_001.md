---
provider: manual
pr:
round: 2
round_created_at: 2026-10-22T00:02:17Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 323
severity: medium
author: claude-code
provider_ref:
---

# Issue 001: Curator message still ends "Write all content in Portuguese"

## Review Comment

Round 1 (issue 007) settled on one fix: the curator is not told the language, and `prompts/curate_system.md` gains an unconditional rule that a quote keeps the words said, in their language. The spec plans to change only that file, and only around line 43 (File References: `prompts/curate_system.md:43`; Impact Analysis row `prompts/...curate_system.md`). The curator's input also has instructions that the plan leaves alone and that point the other way:

- `src/teams_recorder/messages.py:684-693`: `Prompt.CURATE_TASK`, the `<task>` block that `curator_claude.build_user_message` puts at the very end of every curator user message (`curator_claude.py:204`), ends with `"7. Write all content in Brazilian Portuguese."` and has no exception for quotes. This is the last instruction the model reads, and it comes right after the `<excerpts>` block (`curator_claude.py:208-209`). For an English meeting those excerpts are English transcript lines, and the analysis's `status_updates[].evidence` quotes are English too (`CURATE_QUOTE`, `messages.py:678`).
- `prompts/curate_system.md:1` describes the user's meetings as "held in Brazilian Portuguese". Line 34 says "Everything in the document is in Brazilian Portuguese", and line 281 repeats "(7) all content in Brazilian Portuguese".

Failure mode: when an English meeting is curated, the model gets a new rule in the system prompt and an older instruction at the end of the user message that says the opposite. Translating the English quote into Portuguese obeys the last instruction. That breaks US-004.AC-4 (the 💬 quote is the English words said) and Safety Invariant 5, which names the curator. UT-053 checks only the new sentence in `curate_system.md`, so it passes while the conflicting `CURATE_TASK` stays. The opt-in real-call suites are the only check, and they spend the subscription.

A related wording error: the Impact Analysis row says the prompt risk is low because "the added text is conditional on the header line". The curator has no header line, and its new rule is unconditional (Core Features), so it changes every Portuguese curator pass too.

Suggested fix (spec only):
1. Add `messages.Prompt.CURATE_TASK` step 7 to the Impact Analysis and File References. Reword it, for example: "7. Write all content in Brazilian Portuguese; a quote keeps the words said, in the language they were said in."
2. Add `curate_system.md:1, 34, 281` to the wording change, so "held in Brazilian Portuguese" no longer claims something that is now false, and the two "all content" lines carry the quote exception.
3. Extend UT-053 to assert the quote exception in `Prompt.CURATE_TASK`.
4. Correct the risk note: the curator's added text is unconditional.
5. `AGENTS.md:133` also says "meetings are held in Brazilian Portuguese". The task-6 docs row lists only the AGENTS.md ports table, so add this line to it.

## Triage

- Decision: `VALID`
- Notes: Valid. `Prompt.CURATE_TASK` step 7 (`messages.py:684-693`) and `curate_system.md` lines 1, 34 and 281 ask for all content in Brazilian Portuguese with no exception for quotes.
- Verified: `src/teams_recorder/messages.py:684-693`; `prompts/curate_system.md:1, 34, 281`.

### Resolution

`_spec.md` Impact Analysis splits the prompts row: the analyzer and verifier wording is conditional on the header line; a new row plans the unconditional curator change (step 7 text given, lines 1, 34, 43, 281) and corrects the risk note. File References add `messages.py:684-693`. UT-053 asserts on `Prompt.CURATE_TASK` and the four prompt lines.
