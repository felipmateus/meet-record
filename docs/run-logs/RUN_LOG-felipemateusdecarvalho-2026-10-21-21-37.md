# Run log: review round 3 of the language-detection spec, and its fixes

Request (in Portuguese): "faça uma nova review" ("do a new review"), for the `language-detection` spec, after rounds 1 and 2.

## Skills run

- `reviewer` subagent: loaded `cy-review-round` and `cy-final-verify`. It stopped at its turn limit, was asked to write up, and filed 4 findings (0 critical, 0 high, 1 medium, 3 low) in `docs/tasks/language-detection/reviews-003/`, plus three points it did not reach. It asked the user nothing. Its own run log is `RUN_LOG-felipemateusdecarvalho-2026-10-21-21-30.md`.
- `cy-spec-preflight` (spec branch), after the fixes: `check-spec-markers.py` and `check-spec-part1-leak.py` both report OK. A test-ID check finds no referenced ID without a definition.

## Questions asked and answers given

1. **Which round-3 findings should I apply to the spec?**
   Options: all 4 (recommended; a round 4 verifies the fixes); only the medium one (001); choose one by one.
   **Answer: "Todos os 4 (Recomendado)"** ("all 4, recommended").
2. **And the 3 points the reviewer did not reach?**
   Options: I verify and fix them (recommended); leave them to round 4; ignore them.
   **Answer: "Eu verifico e corrijo (Recomendado)"** ("I verify and fix them, recommended").

No other question was asked.

## Outcome

- Issues 001–004 are triaged `VALID`, with a Resolution note each. They stay `valid` until a reviewer verifies them.
- Changes by issue:
  - **001:** the spec no longer claims Portuguese requests stay identical (only the user message does). A new gate G3 re-measures Portuguese output after the system-prompt edits. It runs with the user's approval because it spends the subscription. UT-053 now covers curator line 43.
  - **002:** the docs row lists the six missing pages plus `enum-dictionary.md`.
  - **003:** the CLI line now says `see the warning above`. The spec states that only the daemon writes `daemon.log`, and UT-063 asserts the warning on stderr.
  - **004:** `Verify.ADDRESS` gains English greetings (US-004.EC-3, UT-054).
- The three points the reviewer did not reach are recorded in `reviews-003/_summary.md`:
  - E2E-002 now uses per-audio fakes.
  - `languages` is validated in both modes (UT-025a).
  - The doctor line goes right after the retry line (US-007.AC-4, UT-067).
- Fixed in passing: the spec's Testing Approach named the vans meeting for G2, while `_tests.md` measures MARTA. It now says MARTA.
- Nothing committed. No source file changed. Nothing written under `data/`.

## Open items left to the user

- An optional round 4 to verify the fixes.
- Approve the spec, then the task breakdown (`cy-create-tasks`).
- The two Open Questions are unchanged: the backfill of the two English meetings, and short backchannels in the loop guard.
