# RUN_LOG — felipemateusdecarvalho — 2026-10-14 11:22

Skill run: `code-review`, by a sub-agent, on task 4.0 of `tasks/prd-fidelity-guard/` (the verification marks in the minutes, the plan, the stories and the board, and the degraded-transcript banner in the drafts).

- **Request:** after merging PR #16 the user wrote "continue, fiz o merge" (go on, I merged), continuing the agreed flow per task: implementation, review by a sub-agent, fixes, PR.
- **Arguments:** `since origin/main; spec: tasks/prd-fidelity-guard/ task 4.0 (tasks.md 4.0; techspec.md §3 BuildDailyPlan/DraftUserStories, §4 minutes_markdown/stories_markdown/publisher_backlogmd and the "As built" notes; prd.md FR2, FR4, FR5, decisions 2, 9, 10); standards: AGENTS.md and docs/COMMITS.md`.
- **Scope:** the five commits `43a156b..ecddfec` on `feat/verification-marks`.
- **Mode:** read-only.
  - The reviewer handed back with the Standards sub-agent's report, which it had checked, and did the Spec axis itself.
  - The Spec sub-agent then reported separately. It added a byte-for-byte comparison with `main` for unverified inputs (identical) and one new finding (FR4).
  - Checks: one pytest session (526 passed, 8 skipped), mypy clean, every commit importable (checked against the extracted commit, not the editable install).

## Questions asked to the user
None. The defaults the reviewers took: the fixed point `origin/main` and the spec in `tasks/prd-fidelity-guard/`, as given. The missing `docs/agents/issue-tracker.md` was ignored. The reviewer did the Spec axis itself when its sub-agent had not reported.

## Answers given by the user
None (no questions asked).

## Outcome
Findings reproduced by the main session, all fixed with tests (five of them fail on the reviewed commit `ecddfec`):

| Severity | Finding |
|---|---|
| Medium (once verification is on) | A line break in a verifier reason split a row of the minutes' action table and broke every row after it. `_` or `*` in a reason broke its italics |
| Medium (docs) | PRD pages 03 (minutes) and 06 (daily plan) did not describe the marks, and AGENTS.md's renderer rows were stale |
| Low-medium | The drafts banner cut its gap list after three ranges with "and 2 more", an English notification string, unlike the minutes' banner. The renderer imported a use case for it |
| Low | An unconfirmed management or communication action was not marked in the drafts (FR4) |
| Low | Without a reason, the card mark read "A confirmar na transcrição: não confirmada na transcrição" |
| Low (docs) | Tech spec §3's original line ("go to the writer marked 'a confirmar'") contradicted the "As built" note |
| Low (smell) | The mark's formatting was repeated in four places and the minutes re-listed the claims (now `domain.unconfirmed_reason` and `domain.verifications`); `doubtful` renamed |

Judgement calls kept, recorded in the tech spec:
- **FR5:** unconfirmed features and bugs are always listed as left out, never turned into a story's open questions. FR5 allows either.
- **For task 5.0:** the story writer still sees unconfirmed decisions and other people's actions in its context, and its prompt has no rule about the marks.
- **Banner scope:** the drafts banner covers every source meeting of the plan's new actions, including plan-only ones.
- **Stale marks:** an action already in `open_actions.json` keeps the verification it had when it was first planned.
- **Deduplication:** a marked task card can win the same-text duplicate check against an unverified twin.
- **Priorities:** on a day where every item is unconfirmed, the planner prompt's "3 to 5 priorities" and "unconfirmed is never a priority" pull against each other.
- **Commit `c31a3e2`:** it calls the renderer with the new argument one commit before the adapter accepts it. It imports, and the wave passes at its end, as `docs/COMMITS.md` allows.

## Notes for the user
- The marks show once task 7.0 switches verification on. The drafts banner for degraded transcripts works now.
