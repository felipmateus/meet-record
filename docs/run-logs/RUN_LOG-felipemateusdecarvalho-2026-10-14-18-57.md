# RUN_LOG — felipemateusdecarvalho — 2026-10-14 18:57

Skill run: `code-review`, by a sub-agent, on task 1.1 of `tasks/prd-fidelity-guard/`. The task came from the wrong-sample-rate incident of 2026-10-13/14 (PR #18) and covers three things: the choice between whisper passes, no retry on a track recorded at the wrong rate, and the drafts banner for such tracks.

- **Request:** the user wrote "siga" (go on) after PR #19 was merged, continuing the agreed flow per task: implementation, review by a sub-agent, fixes, PR.
- **Arguments:** `since origin/main; spec: tasks/prd-fidelity-guard/tasks.md item 1.1 (and the docs it updated: prd.md FR1 and decision 6, techspec, prd/pages/02-transcription.md, requirements §10 "Retry choice and broken audio"); standards: AGENTS.md and docs/COMMITS.md`.
- **Scope:** the five commits `09ada1b..0b39563` on `fix/retry-choice`.
- **Mode:** read-only. Both the Standards and the Spec sub-agents reported, and the reviewer checked their main findings.
- **Checks:**
  - pytest: 557 passed, 8 skipped;
  - mypy: clean;
  - each commit was extracted and imported, and its tests were run;
  - a grid of covered minutes 0–37 × degraded/clean found the new ordering reflexive, antisymmetric and transitive;
  - probes of the rule.

## Questions asked to the user
None. The reviewers' defaults:

| # | Question the skill asked or would have asked | Default taken |
|---|---|---|
| 1 | Should `RETRY_KEEP_SHARE` be a configuration key? | No; the spec does not ask for one |
| 2 | Do failing tests in the middle commits break the layering rule? | No; docs/COMMITS.md allows it until the end of the wave |
| 3 | Should "without loops" in the docs mean "not degraded" (up to 10% in loops)? | The code is right; the wording was reported |

## Answers given by the user
None (no questions asked).

## Outcome
No bug was found: the choice, the skipped retry and the banner do what task 1.1 asks. The ordering still guarantees that an empty retry never replaces a usable first pass. Fixed after the review:

| Finding | Fix |
|---|---|
| The docs said a "pass without loops" wins, but the code uses "not degraded", which allows up to 10% of segments in loops | README, PRD page 02, prd.md FR1 and decision 6, §10, config.toml and the constant's comment now say "not degraded (at most 10% of its segments in loops)" |
| "An empty or cut-short retry never replaces a usable first pass" now overstated the rule: a clean retry can lose up to 15% of the text and win | Reworded everywhere to "a retry that loses more than 15% of the text, an empty or cut-short one included, never replaces the first pass" |
| AGENTS.md (Transcriber and StoryRenderer rows), the `StoryRenderer.render` docstring, techspec §3 and the drafts-banner note, and prd.md decision 9 still described only degraded transcripts and the unconditional retry | Updated |
| An intermediate commit (the application one) made the drafts show "Transcrição degradada 0%" for a meeting that was only at the wrong rate, until the adapter commit | The branch was not pushed, so the wave was recommitted with the adapter's banner before the application change |
| Tests matched copied text ("no retry for", "Transcrição degradada") instead of the constants | They use `Log.TRANSCRIPT_RETRY_SKIPPED` and `StoryDoc.DEGRADED` |
| Test gaps: the 85% rule was never exercised through `TranscribeMeeting`, and the retry with unreadable counters was not covered | Two tests added |
| Names: `degraded_sources` also returned meetings that were only at the wrong rate; the bool parameter `retry` sat beside `self.retry`, a Transcriber | Renamed to `untrusted_sources` and `allow_retry` (no default) |
| Style: three blank lines before new tests | Fixed |

Kept as judgement calls:
- **`RETRY_KEEP_SHARE`:** it stays in `domain/models.py`, next to the method that uses it, since `health.py` imports `models`; it is not a setting.
- **Duplicated banner logic:** it is still duplicated between the minutes and the drafts renderers.

## Notes for the user
- The PR follows these fixes.
