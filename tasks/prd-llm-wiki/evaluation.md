# Evaluation protocol: does the wiki answer better than the minutes in context?

> Part of the `llm-wiki` plan ([prd.md](./prd.md) FR12, gates G2 and G3 in §7). Executed by tasks 7 and 8.
> Method: `ai-evals-course/evals-skills` (installed with the user's approval; every run of its skills produces a `RUN_LOG` in `docs/run-logs/`) and Anthropic's pass@k / pass^k metrics for repeated runs.

## 1. Question

Given the meetings recorded so far, does a model answer questions about them better when it reads the wiki than when it receives all the minutes in its context? "Better" is measured per question category, over repeated runs, with correctness decided by code where possible and by a calibrated judge otherwise.

## 2. Three layers

| Layer | What it proves | Deterministic? | Where |
|---|---|---|---|
| 1. Unit tests of the ingest mechanics | pages are validated, written atomically, indexed, logged, sourced; failures isolated | yes | `tests/unit`, `tests/integration` (techspec §12) |
| 2. Synthetic corpus with planted facts | the wiki tracks changes over time, aggregates across meetings, does not invent | no: pass rates over k runs | `tests/fixtures/wiki_corpus/`, `scripts/wiki_eval.py`, opt-in test |
| 3. Real meetings with the user's answer key | the wiki helps on *this* user's questions; the pages are faithful | no: user labels + calibrated judge | `data/wiki-eval/` (ignored) |

## 3. Conditions

Same model and effort for every condition (the project's provider, `claude-code` by default). Each question runs `k` times per condition (default 3).

| Condition | How the answer is produced |
|---|---|
| **A · minutes** (baseline, what the user can do today) | `claude -p` with no tools; the system prompt asks for a cited answer in Portuguese and to say when something was not discussed; the user message is every `minutes.md` of the corpus, oldest first |
| **B · wiki** | `claude -p` with the wiki folder as working directory, read-only tools (Read, Grep, Glob; exact flags fixed in task 7), the wiki's `CLAUDE.md` as the system prompt (read the index first, open pages, cite meetings and timestamps) |
| **C · transcripts** (optional ceiling) | as A, with every `transcript.txt` instead of the minutes |

Each run records the answer, input/output tokens and wall time (usage comes from the Claude Code envelope the transport already parses).

## 4. Synthetic corpus (layer 2)

- Eight fictional meetings in Brazilian Portuguese (test fixtures may be in Portuguese per AGENTS.md), 400–900 words each, spread over three weeks (ids `2026-01-05_10-00-00` …), with a fictional company, three people (e.g. Ana Tavares, Bruno Lemos, José "Zé" Fontes) and two projects. Written to sound like transcripts (interruptions, filler, a few whisper-like errors), not like minutes.
- `facts.toml` lists every planted fact with the meeting and the line it appears in. Facts cover: a deadline stated, then moved; an owner handed over; a decision reversed; a blocker mentioned in three meetings; an alias (`Zé` / `José Fontes`); a number stated once; a topic never discussed (budget).
- The runner creates a temporary data dir, writes `meta.json`, `transcript.json` and `transcript.txt` per meeting, runs the real analyzer (so the chain analysis → ingest is what is measured), ingests oldest first, then asks the questions. `--analyses <dir>` reuses saved analyses to skip the analyzer on reruns.

## 5. Questions

`questions.toml`, one table per question:

```toml
[[question]]
id = "prazo-atual-aurora"
category = "current-state"        # fact | synthesis | current-state | aggregation | unanswerable
text = "Qual é o prazo atual da fase 2 do Projeto Aurora e quem é o responsável?"
must_include = ["22/01", "Bruno"]              # all present (case- and accent-insensitive)
must_not_include = ["15/01 é o prazo", "Ana é a responsável"]   # none present
must_cite = ["2026-01-12_10-00-00"]            # a meeting id or page path in the answer
judge = ""                                     # rubric for open questions; empty = code checks only

[[question]]
id = "orcamento"
category = "unanswerable"
text = "Qual foi o orçamento aprovado para o Aurora?"
judge = "PASS only if the answer says the budget was not discussed in the meetings and gives no figure."
```

A question **passes a run** when every code check passes and, when `judge` is set, the judge says PASS. Twenty questions, four per category, for the synthetic corpus. The user writes 20–30 of the same shape for the real meetings (`data/wiki-eval/questions.toml`), answer key first, before any run.

## 6. The judge

- One criterion per judge, binary PASS/FAIL, critique written before the verdict (`write-judge-prompt` skill); the rubric comes from the question's `judge` field plus the answer key.
- Output through `StructuredTransport` with a `{critique, verdict}` schema; the judge prompt lives in `scripts/wiki_eval/judge_system.md`.
- **Calibration before use** (`validate-evaluator` skill): the user labels at least 20 answers sampled across conditions and categories (PASS/FAIL with a one-line critique); the runner reports TPR, TNR and whether the judge is harsh or lenient. The judge is used in the decision only when TPR and TNR are both ≥ 0.8; otherwise the rubric is fixed and relabeled. The labels file (`labels.toml`) stays with the run.
- The fidelity check reuses the judge with a different criterion: given a claim sampled from a wiki page and the transcript window around the cited timestamp (± 60 s), is the claim supported? The user confirms a sample of those verdicts.

## 7. Metrics

- Per question and condition: passes out of `k` runs; **pass^k** (passed every run) is the headline, because a knowledge base must be reliable, not lucky; pass@k is reported for context.
- Per category and condition: mean pass^k; count of fabricated facts (`must_not_include` hits) and of invented sources (`must_cite` misses).
- Cost: median input tokens and wall time per answer, per condition.
- Fidelity (real data): supported claims / sampled claims.

## 8. Decision rule

| Gate | Pass when |
|---|---|
| G2 (synthetic) | wiki pass^3 ≥ 0.8 on `current-state` and `aggregation`; wiki ≥ minutes on every category; zero fabricated facts in the wiki condition |
| G3 (real) | wiki ≥ minutes overall and strictly better on `synthesis`, `current-state`, `aggregation`; fidelity ≥ 95%; judge calibrated (TPR, TNR ≥ 0.8) |

A tie or a loss is a valid result: with 13 meetings the baseline is strong. The outcome and the numbers go to `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10; the harness stays for a rerun when the volume grows or the schema changes.

## 9. Runner

`scripts/wiki_eval.py` (imports `teams_recorder`; standard library plus the project):

```
scripts/wiki_eval.py run   --corpus tests/fixtures/wiki_corpus --questions tests/fixtures/wiki_corpus/questions.toml \
                           --conditions minutes,wiki --runs 3 --out data/wiki-eval/runs/<timestamp>/
scripts/wiki_eval.py run   --data data --questions data/wiki-eval/questions.toml --conditions minutes,wiki --runs 3 ...   # real meetings
scripts/wiki_eval.py judge --run <dir>                 # judge the open questions of a run
scripts/wiki_eval.py calibrate --run <dir> --labels labels.toml
scripts/wiki_eval.py fidelity --wiki data/wiki --data data --sample 30 --out <dir>
scripts/wiki_eval.py report --run <dir>                # report.md with the tables of §7 and the decision rule of §8
```

Every answer is appended to `answers.jsonl` as soon as it arrives, so an interrupted run resumes (`--resume`). The opt-in test `tests/integration/test_wiki_eval_real.py` (`TREC_REAL_WIKI=1`, `-m slow`) runs the synthetic corpus with `--runs 2` and asserts only the hard parts: at least one page per planted person and project exists, the planted change is reflected in the project page, and `must_not_include` never hits in the wiki condition.

## 10. Cost and time

Synthetic run with `k = 3`, two conditions: 8 analyses + 16 ingest calls + 120 answers + ~36 judge calls ≈ 180 model calls. With the subscription that is time, not money: 1–2 hours in the background. The real-data run adds the user's 20–30 questions (≈ 150 calls) and 30 fidelity checks. Both runs need the user's approval before they start (AGENTS.md: real model, real content).

## 11. Privacy

Layer 2 content is fictional and lives in the repository. Layer 3 questions, answers, labels and reports contain meeting content and live under `data/wiki-eval/`, which Git ignores with the rest of `data/`. The judge sees the same text the model already saw.
