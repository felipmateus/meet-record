# Run log: review round 4 of the language-detection spec, and its fixes

Request (in Portuguese): "faça mais uma revisão" ("do one more review"). The user sent it after interrupting a `cy-create-tasks` run. I had started that run after reading an earlier "pode seguir" ("go ahead") as approval of the spec, and it was not.

## Skills run

- `cy-create-tasks`, interrupted by the user after `_tasks.md`, `task_01.md` and `task_02.md` were written. Those three draft files were deleted at the user's request (question 3 below).
- `reviewer` subagent: loaded `cy-review-round` and `cy-final-verify`. It asked the user nothing. Its own run log is `RUN_LOG-felipemateusdecarvalho-2026-10-21-23-17.md`. Results:
  - reviews-003 issues 002 and 004 are `resolved`;
  - issues 001 (gate G3 cannot measure the verifier) and 003 (UT-063's stderr assertion fails under pytest) went back to `pending`;
  - 2 new low issues are in `reviews-004/`.
- `cy-spec-preflight` checks after the fixes: `check-spec-markers.py` and `check-spec-part1-leak.py` both report OK.

## Questions asked and answers given

1. **How should gate G3 measure the verifier prompt?**
   Options: before/after on `VerifyAnalysis` (recommended); make `defend` read the real prompt; drop G3(a).
   **Answer: "Antes/depois no VerifyAnalysis (Recomendado)"** ("before/after on VerifyAnalysis, recommended").
2. **Should I apply the other 3 findings (UT-063 via caplog, the 3 docs pages, the test IDs)?**
   Options: yes, all of them (recommended); choose one by one.
   **Answer: "Sim, todos (Recomendado)"** ("yes, all of them, recommended").
3. **And the draft tasks (`_tasks.md`, `task_01.md`, `task_02.md`)?**
   Options: delete them (recommended); keep them.
   **Answer: "Apagar (Recomendado)"** ("delete them, recommended").

No other question was asked.

## Outcome

- Issues reviews-003/001, reviews-003/003, reviews-004/001 and reviews-004/002 are `valid`, each with a Resolution section. They wait for a reviewer to verify them.
- Changes by issue:
  - **G3:** the gate now compares two checkouts, an old worktree at the base commit and the feature branch, on scratch copies of three Portuguese meetings. The verifier runs `VerifyAnalysis` twice per side on the same stored analyses, and run-to-run noise is listed. The analyzer and curator are compared with `trec analyze`. `fidelity_eval.py` is not used, and the gate says why.
  - **UT-063:** asserts the warning with `caplog`. The stray space is removed from `_dx.md`.
  - **Docs row:** the three activities and PRD pages are added.
  - **Test IDs:** `UT-001–UT-012c` and `UT-020–UT-026, UT-025a`.
- A memory was saved: a bare "pode seguir" after a review is not spec approval.
- Nothing committed. No source file changed. Nothing written under `data/`; only a count of the stored analyses was read.

## Open items left to the user

- An optional round 5 to verify these four fixes.
- Approve the spec explicitly before `cy-create-tasks`.
