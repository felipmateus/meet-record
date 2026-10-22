---
provider: manual
pr:
round: 3
round_created_at: 2026-10-22T00:30:08Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 387
severity: medium
author: claude-code
provider_ref:
---

# Issue 001: Prompt edits reach every Portuguese meeting with no regression gate

## Review Comment

Key Decisions (`_spec.md:387`) says the header line appears only for non-Portuguese transcripts, and that this "keeps every Portuguese analysis request identical to today's, so prompt-level evaluations stay comparable". The same spec changes the system prompts that every Portuguese request carries:

- `prompts/analyze_system.md:1` ("a work meeting held in Brazilian Portuguese") and `:50-66` (File References `_spec.md:420`; Impact row `_spec.md:326`).
- `prompts/verify_system.md` (Impact row `_spec.md:326`).
- `prompts/curate_system.md:1, 34, 43, 281` and `messages.Prompt.CURATE_TASK` step 7 (`messages.py:684-693`). The spec itself says this change is unconditional and that "every pass, Portuguese meetings included, sees the changed sentence" (`_spec.md:327`).

Only the user message stays byte-identical (US-002.AC-3, UT-050). The system prompt is part of the request, so a Portuguese analysis, verification or curator pass is no longer the request it was today. The sentence at `:387` is therefore false, and the risk notes at `:326-327` ("low") rest on it.

Nothing measures the effect. UT-053 (`_tests.md:129`) checks substrings only. The real-call suites are opt-in (`_tests.md:179`). Gates G1 and G2 (`_tests.md:172-173`) measure detection and English transcription, not Portuguese analysis. The project already has a rule for this: after the verifier's label sentence changed, `docs/REQUIREMENTS-AND-ARCHITECTURE.md:549` item (4) recorded that "the fidelity gate must re-measure the verifier prompt". This spec changes three prompts and the curator's task block and records no such step.

A smaller mismatch in the same area: the curator Impact row (`_spec.md:327`) says "UT-053 asserts on `Prompt.CURATE_TASK` and the four prompt lines". UT-053 (`_tests.md:129`) names only lines 1, 34 and 281, so line 43 (the 💬 literal-quote format) is unchecked.

Failure mode: one reworded sentence in `analyze_system.md` (for example "usually, not always, held in Brazilian Portuguese") or in the curator's step 7 can change the output for all 25 Portuguese meetings. The spec claims those requests are unchanged, so nobody would look.

Suggested fix (spec only):
1. Rewrite `_spec.md:387`: the Portuguese user messages stay byte-identical, while the analyzer, verifier and curator system prompts change for every meeting.
2. Add an evidence gate to task 6, in the style of `REQUIREMENTS:549` (4): run `scripts/fidelity_eval.py` (`gate`/`defend`) on the changed analyzer and verifier prompts, plus one curator pass on a Portuguese meeting, before and after, with the user's approval because it spends the subscription. Record the result in §10.
3. Make UT-053 list line 43, or change the Impact row to say three lines.

## Triage

- Decision: `VALID`
- Notes: Valid. The analyzer, verifier and curator system prompts are part of every request, so a Portuguese request changes even though its user message stays byte-identical; `_spec.md` Key Decisions claimed otherwise, and no gate measured it, against the precedent of `REQUIREMENTS` §10 (speaker attribution, pending item 4). UT-053 named curator lines 1, 34 and 281 but not 43.
- Verified: `prompts/analyze_system.md:1, 65`; `prompts/curate_system.md:1, 34, 43, 281`; `scripts/fidelity_eval.py:1312-1333` (`gate`: owner/date catch rates, false positives, baseline noise band); `docs/REQUIREMENTS-AND-ARCHITECTURE.md:549` item (4).
- Round 4 verification (2026-10-22): not confirmed, set back to `pending`. The prose fixes hold: Business Rules › What the model is told (`_spec.md:54`) and Key Decisions (`_spec.md:390`) now say only the user message stays byte-identical, and UT-053 (`_tests.md:133`) asserts curator line 43. Gate G3 part (a) (`_tests.md:179`) cannot do what it claims, for four reasons checked in the code and at runtime on a scratch copy of `data/wiki-eval/fidelity-2026-10-11/`:
  1. `defend` never reads `prompts/verify_system.md`. It sends its own inline `VERIFY_SYSTEM` (`scripts/fidelity_eval.py:396`, used at `:431`), which is already a different text from the shipped prompt (no speaker labels, no roster sentence). A grep finds no reference to `verify_system` in the script. Editing the shipped prompt changes nothing that `defend` or `gate` measures. The Impact row `_spec.md:331` ("unaffected in code") confirms nobody plans to change that.
  2. `defend` resumes. It loads `l1.json` and skips every `<meeting>#<k>` already there (`:458-469`). On the existing work dir, 14 meetings × 3 runs = 42 keys are all present, so the job list is empty: no new verifier call is made.
  3. `gate` reads `defense_metrics.json` when it exists (`:1313`). Only `report` writes that file (`:540`), so "`defend` then `gate`" scores stale metrics.
  4. The pass criterion "the gate prints PASS" fails before any change. `gate --work <copy>` with its default `--config "L1 + L2"` printed `FAIL` (correct claims rejected 18% against the 10% cap). The earlier PASS runs in `gate_report.md` used `L1 verifier` and `L1 + L2 tuned`.
  The suggested fix in this issue (item 2, "run `scripts/fidelity_eval.py` (`gate`/`defend`)") already carried this flaw. Still needed, spec only: make G3(a) measure the shipped verifier prompt. One way is to extend `defend` to load `prompts/verify_system.md` (a task-6 script change: then remove `fidelity_eval.py` from the "unaffected" row). The other is to drop `fidelity_eval` for the verifier and compare the shipped `VerifyAnalysis` verdicts before and after, on the three meetings of part (b). If `defend`/`gate` stay, state a fresh work dir, or deleting `l1.json` and `defense_metrics.json`, the order `defend` → `report` → `gate`, a named `--config`, and a baseline measured with the old prompt in the same harness.
- Verified (round 5, 2026-10-22): resolved. `_spec.md:54` and `:390` say only the user message stays byte-identical. UT-053 checks curator line 43 (`tests/unit/test_curator_prompt.py`, `test_the_prompt_and_the_task_let_a_quote_keep_the_language_it_was_said_in`, passing). Gate G3 ran as `_tests.md` describes it. (a) The throwaway `g3a.py` called `VerifyAnalysis(build_verifier(s), s.user_name)` twice per meeting. Its logs show the old side importing the code and `prompts/` of the `db83537` worktree and the new side using the repository's. (b) `trec analyze` ran per checkout with `language = "pt"` on scratch data dirs. The results are in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (from line 617): 51 of 52 stable claims kept; the one changed verdict was accepted by the user as noise; (b) was signed off by the user on 2026-10-22. G3 measured the shipped prompts, which was the gap this issue raised.

### Resolution

`_spec.md`: Business Rules › What the model is told and Key Decisions now say only the user message stays byte-identical and the system prompts change for every meeting; both prompt Impact rows name gate G3; Testing Approach and Build Order (task 6, now depending on 4) add G3 with the user's approval; File References add `fidelity_eval.py` and the §10 precedent. `_tests.md`: new gate G3 (verifier `defend` + `gate` PASS; analyzer and curator before/after on three Portuguese meetings in a scratch data dir, signed off by the user), a Coverage Matrix row and a Coverage Decisions note; UT-053 now asserts line 43. Also fixed in passing: Testing Approach said G2 measures the vans meeting, while `_tests.md` G2 measures MARTA; it now says MARTA.

### Resolution (after round 4, 2026-10-21)

User decision: measure the verifier before and after with the shipped `VerifyAnalysis`, not with `fidelity_eval.py`. `_tests.md` G3 now has a Setup (an "old" worktree at the base commit and the feature branch; prompts come from `settings.prompts_dir`; scratch data dirs holding copies of three Portuguese meetings; `language = "pt"`). Part (a) runs `VerifyAnalysis(build_verifier(settings), …)` twice per checkout on the same stored analyses. It passes when every claim whose two old runs agree keeps its status in both new runs; disagreeing claims are listed as noise. Part (b) is `trec analyze <id>` per checkout. G3 says why `fidelity_eval.py` is not used (`defend` sends an inline prompt). `_spec.md` Testing Approach and File References (`container.py:288-296`, `verification.py:29-60`, `config.py:138-139`, `fidelity_eval.py:396, 431`) follow. `scripts/fidelity_eval.py` stays unaffected in code.
