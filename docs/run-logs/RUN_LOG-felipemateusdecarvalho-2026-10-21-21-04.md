# Run log: peer review of the language-detection spec (rounds 1 and 2)

Request (in Portuguese): "faça a revisão" ("do the review"), the optional independent peer review that step 8 of cy-create-spec offers once the spec is saved.

## Skills run

- Round 1, `reviewer` subagent: loaded `cy-review-round` and `cy-final-verify`. It asked the user nothing and received no answers. It stopped at its turn limit before writing, was asked to write up, and filed 11 findings (0 critical, 0 high, 3 medium, 8 low) in `docs/tasks/language-detection/reviews-001/`.
- Round 2, `reviewer` subagent: loaded `cy-review-round` and `cy-final-verify`. It asked the user nothing and received no answers. It verified all 11 round-1 fixes and filed 3 new findings (1 medium, 2 low) in `reviews-002/`. Its own run log is `RUN_LOG-felipemateusdecarvalho-2026-10-21-21-02.md`.

## Questions asked and answers given

1. **Which review findings should I apply to the spec?** (after round 1)
   Options: all 11 (recommended; then a second review round verifies the fixes); only the 3 medium ones; choose one by one.
   **Answer: "Todos os 11 (Recomendado)"** ("all 11, recommended").

No other question was asked. The 3 round-2 findings were applied under the same choice to apply every finding. The summary to the user says so.

## Outcome

- 14 findings, all triaged `VALID` and `resolved` in the owning files: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md`, `adrs/adr-001.md`.
- Changes that alter the design:
  - the fallback comes from a single source (`settings.fallback_language`, and `TranscribeMeeting` refuses `"auto"`);
  - a whisper output with no answer line is a detection failure (`Err.WHISPER_NO_LANGUAGE`);
  - the new reason `too-few-votes`;
  - the curator's "all content in Portuguese" rule gains an exception for quotes (`Prompt.CURATE_TASK` step 7 and four prompt lines).
- The false lock claim was removed: the purge does not take the meeting lock, and the spec now states the real, fail-soft race.
- Spec preflight markers and the test-ID consistency check pass after the fixes.
- Nothing committed. No source file changed. Nothing written under `data/`.

## Open items left to the user

- Approve the spec, then the task breakdown (`cy-create-tasks`).
- The spec's two Open Questions are unchanged: the backfill of the two English meetings (before 2026-11-07 and 2026-11-13), and short backchannels in the loop guard.
