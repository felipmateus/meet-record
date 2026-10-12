# PRD: Fidelity guard — keep what reaches the plan, the stories and the board true to what was said

> **Status:** draft for approval · **Date:** 2026-10-11 · **Slug:** `fidelity-guard`
> **Evidence:** [evaluation of the LLM wiki and the pipeline](../prd-llm-wiki/evaluation.md) §14 (tests run on 2026-10-11 with `scripts/fidelity_eval.py` and `scripts/wiki_corpus.py`)
> **Supersedes as the next step:** the LLM wiki implementation (tasks 2–6 of `tasks/prd-llm-wiki/`), which the evaluation did not justify for question answering.
> **Progress:** task 1.0 (transcript health and language) implemented on 2026-10-11 and reviewed with the `code-review` skill (run log `docs/run-logs/RUN_LOG-felipemateusdecarvalho-2026-10-11-20-34.md`); FR1 and FR2 below record what changed while building it, and G1 is met. Tasks 2.0–8.0 are not started.

## 1. Problem

The pipeline is a chain: audio → transcript → analysis → daily plan → stories → board. Each step trusts the previous one, so one mistake travels. The evaluation measured where mistakes enter and how far they go:

- **Transcription can fail silently.** In a real 86-minute client meeting spoken largely in English (2026-10-08), whisper, forced to Portuguese, fell into a hallucination loop: one line repeated 1,761 times, and the first 59 minutes produced no usable text. The analysis, the minutes and the stories of that day only cover the last half hour, and nothing warned the user. Portuguese meetings are healthy (synthetic word error rate 2.9%, every fact-bearing term recognized).
- **The analysis is right about 84% of the time, claim by claim** (359 claims, 15 synthetic meetings, ground truth from dialogues that say who spoke). The main errors: the wrong owner (22 of 57), because the transcript does not say who is speaking; people only mentioned listed as participants (14); facts nobody said (8). It sometimes copies sensitive personal data into the minutes.
- **One analysis error contaminates every following day.** A single inverted owner injected into one meeting's analysis appeared in all six following daily plans, because open actions accumulate.
- **The story writer invents requirements.** Across 17 stories, 10% of the claims were not supported by the meetings; 7 of those 10 were added by the writer (plausible acceptance criteria nobody asked for), 3 came from analysis errors. These are exactly the details a reviewer approves on the board without noticing.

## 2. Goal

Every fact that reaches the plan, the stories or the board is either confirmed by the transcript or visibly marked as unconfirmed, and a broken transcript is detected and repaired before anything is built on it. Coverage must not drop: an unconfirmed item is shown as "a confirmar", never silently removed.

## 3. Evidence for each measure (summary)

| Measure | What the tests showed |
|---|---|
| Transcript health check + anti-loop decoding | The loop covered 70% of the lines of one real meeting; see evaluation §14.7 for the re-transcription with `-mc 0` (no text context) and VAD |
| Claim verifier after the analysis (Sonnet, transcript as evidence) | Caught 100% of injected errors and 61–74% of the analysis's own errors, rejecting 6% of correct claims; precision of what passes 84% → 93% (out of sample: 89% → 97%); passes the regression gate |
| Two code checks (sensitive data, unconfirmed participant) | Add participant errors (81% → 98%) at +2 points of false positives; the other code checks rejected more correct claims than they caught errors and are dropped |
| Mark, do not drop | Dropping flagged claims removed the propagated error from all plans, but also halved the stories (17 → 9) with no gain in story precision |
| Provenance in the stories (writer cites the source of each criterion or marks "(sugestão)") + marking unconfirmed analysis claims | Silent story errors (wrong and unmarked) 8.2% (6.9–9.7) → 3.8% (1.9–5.5) over three runs each, with the same number of stories; a verifier run on finished stories was not usable (it either missed 60–80% of the bad claims or flagged 12–22% of the good ones) |
| Glossary prompt for whisper | Mixed: fixed names on synthetic audio but made whisper invent a known hallucination line; undetermined on real audio without a human reference — not enabled until the review kit is scored |
| Wiki | Not better than the minutes for questions (17/20 vs 16/20 at 90 meetings, 3× the tokens); its pages are 80–92% factually correct and keep owner errors; its ingest, reading the transcript, did correct an inverted analysis |

## 4. Scope

**In scope**
- **Transcript health (P0, done in task 1.0):** after whisper, measure the share of segments in repetition loops and the minutes without speech text; above a threshold, retranscribe with anti-loop settings, and if still degraded mark the meeting `degraded` with a notification and a banner in the minutes.
- **Language (P0, done in task 1.0):** decoding settings that survive long English or bilingual meetings (chosen from evaluation §14.7), configurable in `[transcription]`: whisper `-mc 0` (`max_context`) on every pass, Silero VAD on the retry.
- **Claim verification after the analysis (P1):** a verifier call per meeting (transcript windows around each claim for long meetings), plus the two kept code checks; each decision, action, deadline and participant gets `verified: confirmed | unconfirmed` with the reason.
- **Use of verification downstream (P1):** the minutes mark unconfirmed items with ⚠️; the planner receives unconfirmed actions labelled "a confirmar" and does not treat them as facts; the story writer receives only confirmed actions as story sources and unconfirmed ones as open questions.
- **Provenance in the stories (P2):** the writer ends every acceptance criterion and detail line with the transcript timestamp it comes from or with "(sugestão)" when nobody said it; the drafts document and the Backlog.md task show both, so the reviewer sees at once what was proposed by the model. (A verifier run on finished stories was tested and rejected: see §3.)
- **Analysis prompt fixes (P2):** owners only when named, addressed or clearly self-assigned (else `indefinido`), participants only people who speak, tentative statements never as decisions, no sensitive personal data (two follow-up tasks already filed).
- **Regression gate (P3):** `scripts/fidelity_eval.py gate` run on the synthetic corpus whenever a prompt or the verifier changes.

**Out of scope**
- Speaker diarization (the root cause of owner errors; a separate project).
- The LLM wiki (kept as an evaluated experiment; see its evaluation).
- Enabling the whisper glossary (pending the human reference in `data/wiki-eval/transcription-review/`).

## 5. Functional requirements

| # | Requirement |
|---|---|
| FR1 | After transcription, a health check computes the loop share (segments whose text appears 5+ times within 30 consecutive segments, compared as lower-case words) and the minutes with speech text, measured against the meeting's length (whisper's non-speech markers such as `[BLANK_AUDIO]` are not text); above `[transcription] max_loop_share` the meeting is retranscribed once with the anti-loop settings, and the pass with more minutes of text is kept (then the one not degraded, then the one with fewer loops), so an empty or cut-short retry never replaces a pass with text. A retry that fails for any reason keeps the first pass. |
| FR2 | A transcript still degraded after the retry is saved with `degraded` health, the analysis runs on it, and the user is notified; the minutes show a banner with the uncovered time ranges. The same banner in the drafts document moved to task 4.0: it needs the drafts to know their source meetings' transcript health. |
| FR3 | The analysis is followed by a verification step that labels every decision, action, deadline and participant `confirmed` or `unconfirmed` with a reason, using the transcript; a verifier failure leaves everything `unconfirmed` and never blocks the analysis. |
| FR4 | Unconfirmed items stay in `analysis.json`, `minutes.md`, the plan and the drafts, visibly marked; nothing is deleted. |
| FR5 | The story writer only cites confirmed actions as sources; unconfirmed candidate actions become open questions of the story or are listed as left out with the reason "não confirmada na transcrição". |
| FR6 | Every acceptance criterion and detail line of a drafted story carries its provenance: a transcript timestamp or "(sugestão)"; the code checks that each criterion has one (a criterion without it is shown as "(sugestão)") and that cited timestamps exist in the source meeting. |
| FR7 | `trec doctor` shows the verification model and the transcript-health thresholds; `trec status` counts meetings with degraded transcripts. |
| FR8 | Costs and calls of the verification steps are logged in `llm_usage.jsonl` like the others. |

Notes on FR1 and FR7 (2026-10-11, task 1.0):
- **FR1 originally read "segments whose text repeats 5+ times", anywhere in the meeting.** Counted that way, natural fillers ("Entendeu?", "Tá") gave a healthy real Portuguese meeting (07/10) 9.8%, just under the 10% threshold, so the count was restricted to repeats close together. Measured on 13 real and 81 synthetic healthy transcripts:
  - **30 segments:** all score 0%, the looped 2026-10-08 transcript scores 68% (text in 28 of 86 minutes), and loops cycling through up to 7 lines are caught. It is the widest window that keeps the healthy meetings at 0%; at 40 the 07/10 meeting reaches 0.8%.
  - **10 segments:** the window shipped first. It missed loops of 3 or more lines and was changed after the code review.
- **FR7:** the transcript part is done (`trec doctor` shows `max_context`, the threshold and the retry state; `trec status` marks and counts degraded transcripts). The verification model line comes with task 7.0.

## 6. Success criteria

| Gate | Criterion | Status |
|---|---|---|
| G1 transcript | The real 2026-10-08 meeting retranscribed with the chosen settings has a loop share under 5% and speech text in at least 80 of its 86 minutes. | **Met on 2026-10-11:** retranscribed by `trec transcribe` with the shipped settings (with the user's approval; the old files are in `data/wiki-eval/backup-2026-10-08/`). The first pass with `-mc 0` was healthy, so no retry ran: 0.8% of segments in loops (1.0% with the final 30-segment window), text in 86 of 86 minutes, 12 min 47 s. The re-analysis covers the whole meeting instead of its last half hour. |
| G2 analysis | On the synthetic stories corpus, `gate` passes for the shipped configuration: injected owner and date errors caught ≥ 90% on every run, correct claims marked unconfirmed ≤ 10%. | Pending (tasks 2.0–3.0, 8.0) |
| G3 stories | On the same corpus, over three runs, silent story errors (wrong and unmarked) average at most 4% and never exceed 6% (measured with the prototype: 3.8%, 1.9–5.5%, against 8.2% today), with the number of drafted stories unchanged. | Pending (tasks 5.0, 8.0) |
| G4 real data | The user reviews one week of real drafts and agrees with at least 80% of the ⚠️ marks. | Pending (task 8.0) |

## 7. Decisions

Decisions proposed (from the evidence):
1. Verifier model: Sonnet at medium effort (fast, cheap; the 100% catch of injected errors and 6% false positives came from it). The analysis keeps the project's model.
2. Mark, do not drop.
3. Keep only the sensitive-data and participant code checks; the others hurt more than they helped.
4. Transcript repair before verification: verification against a broken transcript is meaningless.

Decisions taken while building task 1.0 (from measurements on the real and synthetic transcripts):
5. A loop is 5+ copies of a text within 30 consecutive segments, not 5+ copies anywhere (see the notes on FR1).
6. Between the first pass and the retry, the one with more minutes of text wins, both measured against the meeting's length; "not degraded" only breaks ties.
7. A degraded transcript is still saved and analyzed (FR2); it is not held back (whether it also produces stories: decision 9).
8. The first pass is not saved before the retry: if the daemon restarts during the retry, the meeting is retranscribed from scratch instead of being analyzed without the retry.

Decided by the user on 2026-10-12 (the three questions this PRD left open):
9. **A degraded transcript still produces stories, marked.** Its meeting's actions go through planning and drafting like any other, and the drafts document shows the degraded-transcript banner for that meeting (task 4.0). Nothing waits for a confirmation, because publishing to the board is already a manual step (`[stories] publish = false`), so the user reviews before anything leaves the drafts.
10. **Tasks with ⚠️ marks are published marked**, into the board's Triagem column, with the marks and their reasons in the task description (tasks 4.0–5.0). They are not held back in the drafts: Triagem is already where the user reviews them, and holding them would make a second place to review.
11. **The extra verifier call is accepted** (one Sonnet call at medium effort per meeting, and per drafted day, on the same subscription window as the daemon's analyses). Its cost and calls are measured in `llm_usage.jsonl` during the G4 week (FR8). If it crowds the window, `[verification] enabled = false` turns it off without touching the rest of the guard.
