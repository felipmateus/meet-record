# Review round 5: language-detection (implementation)

- Round: 5 · Created: 2026-10-22T19:48:59Z · Reviewer: claude-code · Scope: the uncommitted implementation of task_01 to task_06 on `feat/language-detection` against HEAD `db83537`. Checked against `_spec.md`, `_dx.md`, `_tests.md`, `_user_stories.md`, `adrs/adr-001.md` and each `task_NN.md`, plus the docs task_06 changed. Out of scope: `docs/SPEAKER-ATTRIBUTION.md`, `docs/tasks/speaker-attribution-windows/` and `docs/run-logs/`.
- Recommendation: **safe to merge with follow-ups.** Nothing is critical, high or medium. One low docs issue. The round is **not clean**: issue 001 is new and `pending`.
- New issues: 1 (critical 0, high 0, medium 0, low 1).
- Prior issues: 4 verified and `resolved` (reviews-003 001 and 003, reviews-004 001 and 002). None is left `valid` or `pending` in earlier rounds.
- Pending a user decision, not filed: gate G1 is not met as written. Two no-speech recordings (2026-10-08_02-50-26 and 2026-10-17_10-15-32) were detected as `en`. A criterion change is under discussion, and `task_06.md` stays `in_progress` with the G1 box unchecked. The open questions (backfill of the two English meetings, backchannels in the loop guard) are also the user's.

| Issue | Severity | Target | Defect |
|---|---|---|---|
| 001 | low | `docs/REQUIREMENTS-AND-ARCHITECTURE.md:617` | §10 cites the G3 outputs, which the G3(b) sign-off depends on, in a session scratchpad under `/private/tmp` that a reboot will delete. |

## Prior issues

| Issue | Was | Now | Evidence |
|---|---|---|---|
| reviews-003 001 | valid | resolved | `_spec.md:54, 390` wording. UT-053 asserts curator line 43. G3 ran with the shipped `VerifyAnalysis(build_verifier(...))` on old (`db83537` worktree code and prompts) and new checkouts, as the throwaway scripts and logs show. The result and the user's acceptance are in §10. |
| reviews-003 003 | valid | resolved | UT-063 asserts through `CliRunner` plus `caplog`, and passes. A runtime probe outside pytest put the warning on stderr and the `see the warning above` line on stdout, with exit 0. |
| reviews-004 001 | valid | resolved | The three pages are in the docs row and were changed in the working tree. A grep for the pinned-Portuguese wording is clean apart from the historical line in §10. |
| reviews-004 002 | valid | resolved | `_spec.md:317` reads `UT-001–UT-012c` and `:347` reads `(UT-020–UT-026, UT-025a)`. All of those tests exist and pass. |

## Runtime evidence

- `pytest` (fast suite, one session): all passed (11 skipped, which are the opt-in suites). `mypy`: `Success: no issues found in 65 source files`.
- `TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_language_whispercpp.py`: IT-004 passed for both voices (Samantha → `en`, Luciana → `pt`) in 18 s. The real whisper.cpp output format matches `Parse.WHISPER_PROCESSING` / `WHISPER_LANGUAGE`.
- CLI probe without pytest (a scratch script, a temp project, a detector raising `Err.WHISPER_NO_LANGUAGE`): stdout matched `_dx.md`, the warning was on stderr, exit 0.
- Read-only: all 28 stored `transcript.json` have `"language": "pt"` and no `language_detection` (the daemon still runs the old code until `trec agent restart`).
- No Claude call was made. Nothing was written under `data/`.

## Test-contract parity

Every ID assigned in the task files is implemented and asserts the contracted behavior: UT-001 to UT-017 (with UT-012a–c and UT-015a), UT-020 to UT-026 (with UT-025a), UT-030 to UT-045, UT-050 to UT-054, UT-060 to UT-073 (with UT-062a), IT-001 to IT-004, E2E-001 and E2E-002. E2E-001 also checks that the scripted whisper got `-l en`. UT-050 to UT-054 are not named with the `test_ut05x_` prefix `_tests.md` › Conventions asks for (they cite the ID in the docstring), because those IDs already exist in other specs' suites. This is a cosmetic deviation and is not filed.

## Known deviations judged

- `Err.NOT_A_LANGUAGE_CODE`, `Err.CLIP_BAD_WAV`, `Err.STEP_CUT_SAMPLE` and `Audio.MIN_LANGUAGE_CLIP_SECONDS`: sound. They keep the never-auto guard, the unreadable-clip mapping, the ffmpeg step name and the 1-second rule out of inline literals, as AGENTS.md requires.
- `test_the_shipped_prompt_is_the_measured_prototype_prompt` (task_04): sound. The spec requires the verifier-prompt paragraph, and the test still pins everything else to the measured prototype.
- `test_transcribe_prints_the_speakers_line_after_the_language_line` (task_05): sound. `_dx.md` puts `Language:` between the health block and `Speakers:`.
- New `TranscribeMeeting` fields after `user_name` (task_03): sound. The container's positional call covers only the first six fields, and every new field is passed by keyword.

## Well implemented

- The never-auto guard holds on both sides: `config._parse_language` and `TranscribeMeeting.__post_init__` use the same `Transcription.LANGUAGE_CODE`, and `Container.transcribe_meeting()` passes `fallback_language` (UT-040, UT-044, UT-045).
- `parse_detection` binds answers by basename, survives an apostrophe and a skipped clip, and is proven against the real whisper output (IT-004).
- Fail-soft detection: one broad catch with a reason. Every failure is logged with its exception and recorded as `detection-failed`, with no `error.txt` and no notification (UT-033, UT-034, IT-002).
- The codec checks types before reading, so every damaged record surfaces as `RepositoryError` naming the file (UT-043, four shapes).
- The Portuguese user messages are byte-identical, which the tests prove by string equality, not by substring.

## Observations, not filed

- `Proc.LANGUAGE_DETECT_TIMEOUT` (300 s) applies to each subprocess, not to the whole detection: up to 12 ffmpeg cuts plus one whisper call, each with its own 300 s. Its comment in `constants.py` reads like a single budget. With a local M4A this has no reproducible failure, so it is not filed. A one-line comment fix would make it accurate.
- A meeting whose `meta.json` has no end time gets one sample at its start, and one vote decides (spec, UT-035). G1 showed that near-silence can answer `en` with p 0.61. All 28 stored meetings have an end time, so there is no current failure. The case belongs to the same user decision as G1.

## Not reached

- Windows behavior: the adapter is untested on real Windows, as for every Windows path. That includes cleanup of `TemporaryDirectory` while files may still be held.
- I did not re-read the full prose of each changed `docs/` page for accuracy. The pages were checked against the Impact row by diff and grep only.
