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

## 12. Scale test (90 meetings): keeping the disk footprint small

The first synthetic run (9 short meetings, 2026-10-10) ended in a tie: all the minutes fit in one context, so the wiki only cost more. The question that decides the feature is what happens with many meetings. This section plans a 90-meeting corpus on a Mac with 4–5 GB free, where the recorder itself needs about 1 GB per hour of call for its raw tracks (`Audio.LOW_DISK_HOURS = 2` → keep at least ~2 GB for it).

### Where the disk goes (measured)

| Stage | Rate | Lifetime |
|---|---|---|
| `say` output and the two source tracks (22.05 kHz, 16-bit, mono) | 2.65 MB/min each | one meeting, in a temp dir |
| Raw tracks as the recorder writes them (48 kHz, 16-bit, mic mono + Teams stereo) | 17.3 MB/min | one meeting, deleted after the mix |
| `audio.m4a` from the project's mixer (AAC 64 kbps mono) | 0.48 MB/min | kept by default |
| whisper's input (16 kHz WAV) | 1.92 MB/min | one meeting, deleted by the transcriber |
| transcript, analysis, minutes | ~10–40 KB per meeting | kept |
| wiki, answers, verdicts, report | < 10 MB in total | kept |

Rendering 90 realistic meetings (about 30 min each, 45 h of audio) would keep **~1.3 GB of `audio.m4a`**, peak at **~0.7 GB** of temporary files while one 30-minute meeting is being mixed, and take **~7–8 h of whisper CPU** (measured ~10 s per minute of audio on the M1).

### Plan

1. **Audio only where it measures something.** The 9 planted meetings already validate audio → whisper → analysis. The other ~81 are distractors whose job is to make the minutes long and the wiki large: they are generated directly as `transcript.json` / `transcript.txt` (realistic length and recognition noise, written by an LLM once) and skip audio and whisper entirely. This removes ~1.2 GB of audio and the 7–8 h of CPU. (`wiki_corpus.py fill`.)
2. **One meeting at a time, cleaned as it goes.** For the meetings that do get audio: render → mix → transcribe → delete `audio.m4a` (it is never read again; `--keep-audio` keeps it for listening). The raw tracks are already deleted after the mix, as the recorder does. Peak footprint is then one meeting's temporaries (~50 MB for the 2–3-minute planted meetings).
3. **Temporary files under the run folder**, not `$TMPDIR`, so an interrupted run leaves nothing behind in `/var/folders` and a single `rm -rf` of the run folder frees everything.
4. **A disk guard before every meeting**: stop with a clear message when free space on the data volume is below `max(3 GB, 2 × raw_bytes_per_hour)` or when `data/current_recording.json` exists (a real call is being recorded). Uses the project's `DataDirDiskSpace`. The real recordings always win.
5. **Distractor fixtures outside Git**: the ~81 generated transcripts (~3 MB) are written once to `data/wiki-eval/corpus-fillers/` (ignored) with a seed and the generation prompt in the repository, so runs are repeatable without regenerating them and the public repository does not grow.
6. **Keep only what the report needs.** At the end, the run folder keeps `answers.jsonl`, `judged.jsonl`, `report.md` and the wiki's Git history (< 15 MB); `wiki_corpus.py clean --run <dir>` removes recordings and temporaries. The scratch data dir is deleted after the report is copied to `data/wiki-eval/runs/`.

### Expected footprint

| | Everything as audio | This plan |
|---|---|---|
| Peak while generating | ~0.7 GB + 1.3 GB accumulated | ~50 MB |
| Kept after the run | ~1.4 GB | < 20 MB |
| CPU for whisper | ~7–8 h | ~3 min |

Memory counts as disk on this Mac: during the first run (4 parallel `claude -p` calls, whisper and ingest agents) swap grew to 7 GB and free space fell by 1 GB in half an hour. The user chose to keep `--jobs 4` (2026-10-10); the disk guard also stops when swap usage (`sysctl vm.swapusage`) leaves less than the guard's margin free.

Quota is unaffected by the disk plan; it is driven by the ingest of 90 meetings and the answers over much longer minutes (estimate: about three five-hour subscription windows). The run must not start on a weekday during working hours, so the daemon's own analyses keep their quota.

### Script changes (`scripts/wiki_corpus.py`)

- `fill --count 81 --seed <n> --out data/wiki-eval/corpus-fillers`: generates the distractor meetings (other projects and people, some with near-duplicate names and dates to stress retrieval) as transcripts plus `meta.json`, once.
- `render`: `--keep-audio` (default off: delete `audio.m4a` after transcription), temporary files under `<data>/.tmp`, the disk guard of step 4 before each meeting.
- `process`: transcribes and deletes the audio immediately when `--keep-audio` is off; links the distractor transcripts into `<data>/recordings/` (symlinks, no copies) before analyzing them.
- `clean --run <dir>`: removes `recordings/`, `.tmp/` and logs, keeps the files of step 6.

## 13. Results

### Run 1: nine synthetic meetings (2026-10-10)

Corpus `tests/fixtures/wiki_corpus` rendered to audio, transcribed by whisper and analyzed by the project's own code; wiki built with schema v2 by a Claude Code agent from `analysis.json` + `transcript.txt`, one meeting at a time; 20 questions × 3 runs × 2 conditions; judge not yet calibrated. Raw results in `data/wiki-eval/sim-runs/2026-10-10-r1-9-meetings/`.

| | minutes | wiki |
|---|---|---|
| pass^3 (all 20) | 16/20 | **18/20** |
| current-state / aggregation / synthesis | 5/5 · 3/4 · 4/4 | 5/5 · 3/4 · 4/4 |
| fact / unanswerable | 2/4 · 2/3 | 3/4 · 3/3 |
| fabricated or leaked (must_not_include hits) | 3 | 0 |
| median input tokens per answer | 43k | 134k |
| median seconds per answer | 15 | 26 |

- The wiki's two wins come from the ingest, not from the wiki's structure: it read the transcript (the analysis had dropped a participant's role) and its schema kept out a health remark that the analysis had copied into the minutes (a product bug, filed separately).
- Both conditions fail the two questions that depend on who said something: the pipeline has no speaker diarization, and the analysis attributed a vacation and a test task to the wrong people; the wiki inherits those errors.
- At this size the minutes fit in one context and the wiki costs about three times the tokens per answer (the agent opens several pages, four turns on average).

### Run 2: scale test, 90 meetings (2026-10-10 → 11)

The nine planted meetings (audio through the recorder's mixer, analyzed with Opus) plus 81 distractors (`fill`, transcripts only, analyzed with Sonnet), 9 distractor projects with near-duplicate names; wiki built with schema v2 by one Claude Code process per meeting (Opus for planted, Sonnet at medium effort for distractors). Raw results in `data/wiki-eval/sim-runs/2026-10-11-scale-90-meetings/`.

| | minutes | wiki |
|---|---|---|
| pass^3 (all 20) | 16/20 | **17/20** (18/20 pass@3) |
| current-state / aggregation / synthesis | 5/5 · 3/4 · 4/4 | 5/5 · 3/4 · 4/4 |
| fact / unanswerable | 2/4 · 2/3 | 3/4 · 2/3 |
| median input tokens per answer | 163k | **514k** |
| median seconds / turns per answer | 15 s / 1 | 28 s / 5 |
| content the model reads from | minutes: 368k chars | wiki: 1.5M chars (index.md alone 106k) |
| building cost | the analyses only | ingest: 5.7 h sequential, US$ 162 eq. |

- **Scale did not change the picture.** With ~100k tokens of minutes in the context, the model found every planted fact among 81 distractors as reliably as with 9 meetings; the wiki matched it, won the same two questions as in run 1 (transcript-derived role, sensitive data kept out) and lost one run of an unanswerable question to the judge's strictness.
- **The wiki got more expensive, not cheaper.** It grew to 4× the size of the minutes it came from (97 topic pages, 21 people, 10 projects, 90 meeting pages); `index.md` reached 106k characters and is re-read on every tool turn, so an answer reads 3× more tokens than reading all the minutes. The schema's limits did not hold at this size (`overview.md` far over 40 lines; topic sprawl).
- **Gate G2, as written, is not met**: aggregation pass^3 is 3/4 (< 0.8) for both conditions, because of the one diarization-dependent question; the wiki is never below the minutes and fabricated nothing. The decisive part is that it is not better where it was supposed to be.
- **Where the crossover would be**: real minutes average ~2.5k tokens (synthetic distractors ~1.1k), so a 200k context holds about 70–80 real meetings, roughly a month of this user's calls. Beyond that the alternative to compare is not "all minutes" but minutes filtered by project or date before answering, which costs a fraction of either.

### Notes for every run

- Voices: every speaker uses `say -v Luciana` at different rates. The other pt_BR voices installed by default mispronounce Portuguese and made whisper's output unrealistic; the pipeline has no diarization, so one voice loses nothing measured.
- Audio goes through the recorder's path: two raw tracks (48 kHz, `bit_depth` from config.toml), mixed by the project's `FfmpegMixer` with `bitrate_kbps` and `denoise` from config.toml. Against direct AAC encoding, transcripts differed in 1.3% of the words (punctuation, articles, digits) and no planted fact changed.
- Costs reported as "US$ equivalent" are Claude Code's `total_cost_usd` (API list price of the tokens), a relative measure; on the subscription the binding constraint is the five-hour window. The CLI's account and plan (`claude auth status`) decide that window, and the daemon's analyses share it: on 2026-10-10 the CLI was on a `pro` seat and hit the window while the user's dashboard (a `team` seat) showed 4%; after `claude auth login` on the team seat the run continued.

## 14. Pipeline fidelity (2026-10-11): does what reaches the plan and the stories match what was said?

The user's priorities after the question-answering runs: is the transcription good, do the stories match the audio, and does the wiki help or spread errors. Harness: `scripts/fidelity_eval.py` (with `scripts/wiki_corpus.py`); corpus: the nine planted meetings plus six about requirements, changed requirements and bugs (`corpus_stories.toml`, 15 meetings, audio through the recorder's mixer, the project's whisper, analysis, planner and story writer). Ground truth: an oracle (Opus) that reads the dialogues, which say who spoke; two runs, 99% agreement, spot-checked by hand against the scripts, and it labelled all 37 injected errors as wrong. Raw results in `data/wiki-eval/fidelity-2026-10-11/`.

### 14.1 Transcription

- **Synthetic Portuguese audio:** word error rate 2.9% (0.8–4.8% per meeting); 133/141 fact-bearing terms exact, the 8 misses only spacing or format ("Rota Fácil", "MetaBusiness", "70%").
- **Real audio, Portuguese meetings (07/10, 09/10):** only natural repetitions ("Entendeu?", "Tá"): 5–8% of lines.
- **Real audio, client meeting in English (08/10, 86 min):** whisper, forced to `pt`, fell into a hallucination loop: "A CIDADE NO BRASIL" 1,761 times, 70% of the lines; minutes 0–58 have no usable text. A three-minute English excerpt transcribes correctly with `-l pt`, `en` or `auto`, so the language setting alone is not the cause: on long audio whisper conditions on its previous text and a loop carries over. Re-transcription with anti-loop settings: see 14.7.
- Every analysis timestamp of that meeting is after 1h04: the minutes, the stories and the wiki pages of that day describe only its last half hour, and nothing warned the user.

### 14.2 Test B: how faithful is the analysis (359 claims, 15 meetings)

| Claim type | Claims | Correct |
|---|---|---|
| decision | 46 | 91% |
| statement (topic points, risks) | 198 | 90% |
| action | 44 | 73% |
| deadline | 27 | 70% |
| participant | 44 | 68% |
| **all** | 359 | **84%** |

Errors by kind (57): wrong owner 22, a person only mentioned listed as participant 14, other 10, not said 8, judgment 1, sensitive 1, tentative recorded as decided 1. The owner errors come from the transcript having no speaker labels: "eu falo com o Rafael" is attributed to whoever the model guesses.

### 14.3 Test A: what the defenses catch (37 injected errors plus the 57 natural ones; verifier run 3×)

| Defense | injected caught | natural caught | correct claims rejected | precision of what passes |
|---|---|---|---|---|
| none | — | — | — | 84% |
| L2 code checks | 68% | 26% | 13% | 86% |
| L1 verifier (Sonnet, transcript) | 100% | 61% | 6% | 93% |
| L1 + all L2 | 100% | 68% | 18% | 93% |
| **L1 + L2 tuned** (sensitive, participant) | 100% | 65% | 8% | 93% |

- By injected type the verifier caught 100% of owner swaps, invented dates, fabricated decisions, phantom participants, sensitive remarks and tentative-as-decided. Natural owner errors are the hard case: 52% caught, because the transcript itself is ambiguous about who speaks.
- The L2 code checks were tuned on the first nine meetings (keep only the checks that caught more errors than they rejected correct claims). **Out of sample** (the six new meetings, 122 claims): verifier 74% caught, 6% rejected, precision 89% → 97%; tuned L1+L2 the same with 7% rejected; untuned L1+L2 rejected 23%.

### 14.4 Test E: regression gate

Thresholds: owner and date errors caught ≥ 90% on every run, correct claims rejected ≤ 10%. PASS for the verifier alone and for the tuned combination; FAIL for the untuned combination (false positives) and for the code checks alone (they miss owners and dates). `scripts/fidelity_eval.py gate --config "L1 + L2 tuned"` keeps a per-configuration baseline and fails on a drop beyond the run-to-run noise band.

### 14.5 Stories: do they match what was said? (four variants, the project's planner and writer)

Plans and stories drafted for the 15 days by the project's planner and writer; each story split into claims (title, story sentence, acceptance criteria, detail lines) and judged against the dialogues by the oracle, which also names where each bad claim came from. "Silent" errors are bad claims that carry no mark ("(sugestão)" or "a confirmar"), i.e. reach the board as facts.

| Variant | runs | stories | claims supported | **silent errors** | origin of the silent ones |
|---|---|---|---|---|---|
| baseline (today) | 3 | 16–17 | 90–93% | **8.2%** (6.9–9.7) | writer 15, analysis 10 |
| + wiki pages as writer context | 1 | 16 | 93% | 7.1% | writer 3, analysis 4 |
| defended: flagged analysis claims dropped | 1 | **9** | 90% | 10.0% | — (half the stories lost) |
| defended + wiki | 1 | **9** | 96% | 3.9% | — (half the stories lost) |
| cited: writer cites each criterion's source or marks "(sugestão)" | 1 | 17 | 87% | 7.8% | 19 claims marked, 5 of them invented |
| **guarded: flagged claims marked "a confirmar" (tuned L1+L2) + cited** | 3 | 16–17 | 88–93% | **3.8%** (1.9–5.5) | writer 8, analysis 3 |

- Today about one story claim in twelve is wrong and unmarked. Most are acceptance criteria the writer invents and that read as reasonable ("each appointment type has its own message", "an existing route keeps its stops after the limit changes"); the rest are owner errors from the analysis ("Carla reported the bug" when it was Zé).
- Dropping what the defenses flag removes errors but also half the stories (the action behind a story is dropped when its owner is uncertain). Marking keeps every story and turns the uncertain owner into "indefinido, a confirmar".
- The guarded pipeline cuts silent errors by about half, and the ranges over three runs do not overlap (worst guarded run 5.5% vs best baseline run 6.9%). What remains is mostly the writer misreading a requirement while citing a timestamp, and owner errors the verifier did not catch.
- Wiki pages as context reduced the writer's inventions in the one run made (7 → 3), a hint rather than a result.
- **A verifier applied to the finished stories is not good enough**: flagging anything not fully supported caught 50–60% of the bad claims but also 12–22% of the good ones; flagging only "unsupported/contradicted" cut the false alarms to 2–7% but caught 20–40%. Invented criteria are hard to detect after the fact; asking the writer to declare provenance works better.

### 14.6 Test C: one error, traced; Test D: what the wiki stores

- **Propagation.** One inverted owner injected into the 12/01 analysis ("the routing module stays with Bruno") appeared in **all six following daily plans** and in that day's stories, because the planner carries open actions forward. With the verifier in front of the analysis, the inverted claims were rejected and every plan stayed clean. The wiki ingest (Claude Code reading the analysis *and* the transcript, schema v2) did not take the inverted claim as the current state even without the verifier: the page says Felipe took over the module and notes that the analysis's decisions disagreed. The transcript is a second opinion the analysis-only steps do not have.
- **Wiki audit.** 40 cited bullets sampled per wiki and judged against all the dialogues: 92% factually correct in the 9-meeting wiki, 80% in the 90-meeting wiki (the analysis itself: 84%). Almost every wrong bullet is an owner error inherited from the analysis (a vacation attributed to the wrong person, "Carla talked to Rafael" when it was Zé), now repeated on several pages. Another 6–8 bullets per sample are correct but cite a meeting that does not support them (traceability). The verifier flagged 6 of the 8 wrong bullets of the large wiki and 0 of the 3 in the small one.

### 14.7 Whisper settings: glossary prompt and anti-loop decoding

- **Glossary prompt** (`--prompt` with names and terms): on synthetic audio the mean word error rate fell from 3.4% to 1.9% and names came out right, but one meeting gained the hallucinated line "Legenda por <nome>" (a known whisper artifact from Brazilian subtitles, also seen in a real noise recording). On real audio it changed 11% of the words of the Portuguese meetings (a misheard client name disappeared, other terms moved both ways) and produced different loops on the English meeting. Undetermined without a human reference; not recommended yet. A review kit with three two-minute real excerpts, whisper's text with and without the glossary, and a file to correct by ear is in `data/wiki-eval/transcription-review/`; `scripts/fidelity_eval.py score-kit` scores it.
- **Anti-loop decoding on the real 08/10 meeting:** the whole 86-minute meeting re-transcribed with the same model and language:

  | whisper settings | segments in loops (5+ repeats) | minutes with speech text (of 86) | time |
  |---|---|---|---|
  | today (`-l pt`, defaults) | 70% ("A CIDADE NO BRASIL" ×1,761) | 28 | — |
  | `-mc 0` (no text context) | **4%** (natural "Ok."/"Okay.") | **86** | 14 min |
  | `-mc 0` + Silero VAD | 3% | 84 (silence skipped) | 19 min |

  On the nine synthetic Portuguese meetings `-mc 0` changes nothing measurable (word error rate 2.9% → 2.8%). **`-mc 0` should be the default for every transcription**; VAD additionally removes the hallucination whisper still produces on the silence at the very start (one "A CIDADE NO BRASIL" line remains with `-mc 0` alone) at 30% more time. The repaired transcript of the real meeting is in `data/wiki-eval/retranscribed/` (the meeting's own files were not touched).

### 14.8 Conclusions

1. **Transcription is good for Portuguese meetings and broken for long English or bilingual ones.** The fix is one whisper option (`-mc 0`), measured on the real meeting that failed and neutral on Portuguese; a loop detector should guard against the next unknown failure. The glossary prompt is not ready (hallucination risk, no real reference yet).
2. **The analysis is the main source of propagated errors** (84% of claims right; wrong owners dominate because the transcript has no speakers). A transcript verifier lifts the precision of what passes to 93–97% while marking 6–8% of correct claims as unconfirmed, and stops a single error from contaminating every following daily plan.
3. **Stories inherit the analysis's errors and add their own.** Marking (not dropping) unconfirmed claims and making the writer declare each criterion's provenance halves the errors that reach the board unmarked, with no lost stories.
4. **The wiki is not the lever against propagated errors.** It stores the analysis's owner errors on several pages (80–92% of its bullets correct) and costs far more tokens; its one clear benefit was that an ingest reading the transcript did not accept an inverted analysis. Its value for stories (fewer inventions as context) is a single-run hint.
5. **Next step:** the fidelity guard (`tasks/prd-fidelity-guard/`): transcript repair first, then claim verification with marks, then provenance in the stories, each measured with these scripts and the regression gate. Every number here comes from 15 synthetic meetings with clean synthetic voices; the human transcription reference (`data/wiki-eval/transcription-review/`) and a week of real drafts are the checks still owed to real data.
