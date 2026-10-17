# Task 8.0: Real-data validation, schema tuning, switch-on decision and documentation (gates G3, G4)

## Overview

Starts once at least 15 work meetings are recorded (spike, techspec §9: only 3 existed on 2026-10-10, too few for the comparison to mean anything). Until then the wiki can be ingested by hand (`trec wiki ingest`) with `enabled = false`.

Prove the wiki on the user's own meetings: backfill every analyzed meeting, run the evaluation with the user's answer key, sample the pages for fidelity, tune `prompts/wiki_schema.md` where the pages fall short, decide with the user whether automatic ingest is switched on, and bring every document in line with the shipped behavior. Every step that reads real content or calls the model waits for the user's approval.

<skills>
### Skills compliance

- `verification-before-completion`: evidence from real runs (report, fidelity sample, status output) before the feature is called done.
- `prompt-engineering-patterns`: schema changes driven by observed failures, one change at a time, rerun after each.
- `code-review`: the wave is reviewed before its commits (as the previous feature did).
</skills>

<requirements>
- Backfill: `trec wiki ingest` over the real data dir (13 meetings and whatever was recorded since), oldest first; a rerun writes nothing; `trec wiki lint` clean; `trec status` and `trec doctor` show the wiki.
- Real evaluation: the user completes `data/wiki-eval/questions.toml` to 20–30 questions with the answer key (started in task 1); `scripts/wiki_eval.py run --data data --conditions minutes,wiki --runs 3`; judge, 20+ user labels, calibration; `fidelity --sample 30` with the user confirming the verdicts; `report.md`.
- Failure drill (G4): with the daemon's provider pointed at a failing `claude` (or `FAKE_CLAUDE_MODE=error` in a copy of the data dir), one ingest fails: the meeting stays `analyzed`, `trec plan` for that day is unchanged, `wiki_error.txt` exists, the notification arrived, `trec wiki ingest` afterwards succeeds.
- Decision: G3 pass → `[wiki] enabled = true` in `config.toml` and `trec agent restart` (approval); G3 fail → `enabled` stays false, the reasons and numbers recorded, and the user chooses between manual ingest and stopping. Either way §10 of the requirements gets a dated note with the numbers.
- Documentation in sync per AGENTS.md: new `docs/prd/pages/09-llm-wiki.md` (flows, options, data, rules, evaluation summary); `docs/prd/README.md` (module row, flow row 9, roadmap, out-of-scope list: Obsidian mention updated); `docs/prd/appendix/data-layout.md` (wiki tree, `wiki.json`), `enum-dictionary.md` (`wiki.json`, `wiki_error.txt` rows), `integrations.md` (git), `relationships.md`; `README.md` (what the wiki is, `trec wiki` commands, how to query with Claude Code and Obsidian, editing `prompts/wiki_schema.md`, the evaluation script); `AGENTS.md` (ports table rows for `WikiWriter`/`WikiStore`/`WikiHistory`, the `trec wiki` and `TREC_REAL_WIKI` commands, the rule that the wiki and `data/wiki-eval/` are never committed, `git_ignore.py` in the adapters list); `docs/COMMITS.md` (wave 9); `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (feature note, spike and evaluation results, decision).
- Full suite, the opt-in tests that were run, and `mypy` clean; `git status` shows nothing under `data/`.
</requirements>

## Subtasks

- [ ] 8.1 Backfill the real meetings (approval); review a sample of pages with the user; `lint`, `status`, `doctor`.
- [ ] 8.2 Complete the answer key with the user; run the real evaluation (approval); label; calibrate; fidelity sample.
- [ ] 8.3 Tune `prompts/wiki_schema.md` from the failures (at most three iterations, `trec wiki rebuild` between them, rerun the affected categories).
- [ ] 8.4 Failure drill and the second-run idempotency check.
- [ ] 8.5 Record G3/G4 and the decision in §10; switch `enabled` on and restart the agent only with the user's OK.
- [ ] 8.6 Update every document listed above; review the wave with `code-review`; prepare the commits (not committed without approval).

## Implementation details

Keep the first backfill's wiki as a Git tag or a `.bak-*` folder before any schema iteration, so the evaluation can be rerun on the same pages. When the baseline wins a category, look at the failing answers before changing anything: a retrieval miss (the wrong page opened) is a `CLAUDE.md` query-workflow problem; a wrong fact on a page is an ingest-prompt problem; a missing fact is a `send_transcript` or section problem. Report the outcome plainly, including a loss.

## Success criteria

- G3 and G4 decided from evidence (report, fidelity table, drill output) and recorded.
- `config.toml` reflects the decision; the daemon runs the new code.
- Every listed document describes the shipped behavior; `pytest`, `mypy`, the strings guard and `git status` clean.

## Task tests

- [ ] Unit tests — none new; the full suite stays green.
- [ ] Integration tests — the full suite plus the opt-in tests of tasks 5 and 7.
- [ ] E2E tests — the real backfill, the real evaluation run, the fidelity sample and the failure drill, with the user.

## Relevant files

- `config.toml`, `prompts/wiki_schema.md`
- `docs/prd/pages/09-llm-wiki.md` (new), `docs/prd/README.md`, `docs/prd/appendix/*.md`, `README.md`, `AGENTS.md`, `docs/COMMITS.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md`
- `data/wiki/`, `data/wiki-eval/` (ignored), `docs/run-logs/`
