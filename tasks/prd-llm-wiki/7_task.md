# Task 7.0: Evaluation harness and the synthetic run (gate G2)

## Overview

Build the repeatable evaluation of [evaluation.md](./evaluation.md): a fictional corpus with planted facts, a question file with code checks and judge rubrics, a runner that produces answers under each condition `k` times, a binary judge with a calibration step, a fidelity sampler and a report. Then run it on the synthetic corpus and record whether gate G2 passes. The evals-skills from `ai-evals-course` guide the judge and the calibration; installing them and every model run need the user's approval.

<skills>
### Skills compliance

- `llm-evaluation` / `evaluation`: multi-condition comparison, pass^k over repeated runs, judge calibrated against human labels, outcome-focused checks.
- `python-testing-patterns`: the harness itself is unit-tested on canned answers; the real run is opt-in.
- Skills from `ai-evals-course/evals-skills` once installed: `generate-synthetic-data` (corpus dimensions), `write-code-eval` (checks), `write-judge-prompt`, `validate-evaluator`. Each run of a skill ends with `docs/run-logs/RUN_LOG-<user>-<date>-<time>.md` (organization rule).
</skills>

<requirements>
- Ask the user before `npx skills add https://github.com/ai-evals-course/evals-skills` (external code) and before every run that calls the model.
- `tests/fixtures/wiki_corpus/`: eight Portuguese fictional transcripts (`<id>/transcript.txt` and `meta.json`), `facts.toml` (planted facts with meeting and line), `questions.toml` (20 questions, four per category, format of evaluation.md §5). No real names, companies or meeting content.
- `scripts/wiki_eval.py` with the subcommands of evaluation.md §9 (`run`, `judge`, `calibrate`, `fidelity`, `report`), `--runs`, `--conditions`, `--resume`, `--analyses`; answers appended to `answers.jsonl` as they arrive; condition A/B/C built as evaluation.md §3 says, the exact `claude -p` flags for read-only tools fixed and documented in the script header. Reuses `teams_recorder` (container, transports, codec) rather than duplicating them; its own usage log under the run folder.
- `scripts/wiki_eval/judge_system.md`: binary PASS/FAIL, one criterion, critique before verdict; `calibrate` reports TPR, TNR, accuracy and harsh/lenient bias from `labels.toml`.
- Code checks: accent- and case-insensitive substring matching (`unicodedata` normalization), `must_cite` on meeting ids or page paths.
- `tests/unit/test_wiki_eval.py`: corpus and questions load, every check type on canned answers, pass^k and pass@k arithmetic, report rendering. `tests/integration/test_wiki_eval_real.py`: opt-in (`TREC_REAL_WIKI=1`, `-m slow`), `--runs 2`, asserting only the hard parts of evaluation.md §9.
- The synthetic run (`--runs 3`, conditions minutes and wiki) executed once, in the background, with the report saved under `data/wiki-eval/runs/` and its numbers copied into the techspec (§9 results) and `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10.
</requirements>

## Subtasks

- [ ] 7.1 Install the evals-skills (user approval); read `evals-start`, `generate-synthetic-data`, `write-code-eval`, `write-judge-prompt`, `validate-evaluator`; write the RUN_LOG.
- [ ] 7.2 Write the corpus: people, projects, timeline, the planted facts of evaluation.md §4, then the eight transcripts and `facts.toml`.
- [ ] 7.3 Write `questions.toml` (20 questions) with checks derived from `facts.toml`; review with the user that each check is unambiguous.
- [ ] 7.4 Implement `scripts/wiki_eval.py` (`run`, `report`) and the condition builders; fix the read-only `claude -p` flags with a smoke test.
- [ ] 7.5 Implement `judge`, `calibrate` and `fidelity`; write `judge_system.md`.
- [ ] 7.6 Unit tests on canned answers; the opt-in integration test.
- [ ] 7.7 With approval, run the synthetic evaluation (`--runs 3`); label 20 judge outputs with the user; calibrate; write `report.md`; record G2.

## Implementation details

The runner builds its own temporary data dir from the corpus and runs the project's `AnalyzeMeeting` and `IngestMeetingIntoWiki` through the container (`TEAMS_RECORDER_DIR` and `paths.data_dir` pointed at the temp dir), so the harness measures the shipped code, not a copy. Condition B's working directory is the wiki built by the run; the system prompt is the wiki's `CLAUDE.md`. Runs are long (evaluation.md §10): start them with `run_in_background` and poll `answers.jsonl`. The real-data path (`--data data`) is the same code with the user's questions; it is executed in task 8, not here.

## Success criteria

- Unit tests prove the checks and metrics on canned data; the opt-in test passes on the real model at `--runs 2`.
- `report.md` shows, per category and condition, pass^3, pass@3, fabricated facts, tokens and time; the calibration table shows TPR/TNR.
- Gate G2 decided from the report (pass or fail), with the numbers in the techspec and §10. A failed G2 ends in a diagnosis (schema, prompt or retrieval) and either a fix-and-rerun or a recorded stop.

## Task tests

- [ ] Unit tests — `tests/unit/test_wiki_eval.py` (new).
- [ ] Integration tests — none beyond the opt-in.
- [ ] E2E tests — `TREC_REAL_WIKI=1 pytest -m slow tests/integration/test_wiki_eval_real.py` (new), and the full synthetic run.

## Relevant files

- `tests/fixtures/wiki_corpus/` (new: transcripts, `meta.json`, `facts.toml`, `questions.toml`)
- `scripts/wiki_eval.py` (new), `scripts/wiki_eval/judge_system.md` (new)
- `tests/unit/test_wiki_eval.py` (new), `tests/integration/test_wiki_eval_real.py` (new)
- `data/wiki-eval/runs/<timestamp>/` (ignored), `docs/run-logs/RUN_LOG-*.md`, `tasks/prd-llm-wiki/techspec.md` §9, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10
