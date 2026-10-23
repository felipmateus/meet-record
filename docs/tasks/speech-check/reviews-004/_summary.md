# Review round 4: speech-check spec (verification only)

Scope: a verification-only round, as the user agreed. It checks that the 4 round 3 fixes (`reviews-003/`) and round 2 issue 005 (`reviews-002/issue_005.md`) landed correctly and consistently across `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`. It was not a new full review. New defects are reported only when a fix introduced them. Code references were checked with `grep -n` against the working tree of `feat/language-detection` at `0d58857`. The spec files were not edited.

**Recommendation: approve after fixes.** Nothing is critical or high. Two small text fixes are needed before tasks are cut:
- finish round 3 issue 001 (reopened, two wording points);
- state E2E-002's preconditions (new issue 001, low).

| ID | Severity | Target | Defect |
|---|---|---|---|
| r4 001 | low | `_tests.md:221` | E2E-002 is a byte-for-byte case, but it pins neither the language mode nor a `meta.json` duration. In auto mode with no duration, check off plans `[0.0]` and check on plans `[10.0, 30.0]`, so the logged `trec-lang-` argv differ |
| r3 001 (reopened) | medium (unchanged) | `_spec.md:521`, `_user_stories.md:67` | (1) The "only" clauses (Invariant 4, US-003.AC-1, Goals, ADR) leave out the duration stand-in, which Business Rules `:76,79` name as a cause of a different `-l`. (2) "Byte-for-byte today's" (`:31,76,521`, ADR `:74`) uses the wrong baseline. Rule B changes `health`, and so whether the retry runs (`processing.py:182`), for every new transcript. The baseline should be `speech_check = false`, as US-003.AC-1 and UT-043 already have it |

Counts: 0 critical, 0 high, 0 medium, 1 low new. 4 of 5 verified fixes are resolved, and 1 is reopened.

## Previous fixes verified

| Issue | Verdict | Evidence |
|---|---|---|
| r3 001 (medium) | **pending** (reopened) | Landed: Business Rules `_spec.md:75-79` give the correct condition. UT-043 runs with a fixed `pt`. UT-056 is written against the real `FakeLanguageDetector` (`tests/fakes/__init__.py:200-222`). That fake answers by position at p 0.99, and a shorter list repeats its last answer. The two runs share an audio path, so they need two instances, which "each run gets its own script" covers. The arithmetic holds under `choose_language` (`language.py:77-91`). Check off: 8 counted, `en` 5, `5*2 > 8` and `5 >= 2`, so `en`. Check on: 3 kept with `planned=8`, so `needed = min_votes = 2`, and `pt` 3 of 3 gives `pt`. `FakeTranscriber.calls` records `(audio, language)` (`tests/fakes/__init__.py:189-192`), so "differ only in the language" can be asserted. Still wrong: see the table above and the round 4 note in `reviews-003/issue_001.md` |
| r3 002 (low) | resolved | E2E-002 replaces each `trec-whisper-…` / `trec-lang-…` directory with a placeholder before comparing, and says why. That can be implemented (`transcriber_whispercpp.py:68`). The precondition gap it exposes is new issue 001 |
| r3 003 (low) | resolved | Every cited symbol line matches `grep -n`. `_decode` is at `repository_fs.py:68` (range `:66-73`), `_decoded` at `:60` and `load_transcript` at `:241-242`. `processing.py` has `:32/:77/:102/:179`, `language.py` `:13/:52/:77/:87`, `container.py` `:132/:214/:226/:254/:265` and `config.py` `:50/:287/:310`. The `cli.py` ranges contain `status :81`, `_language_segment :197`, `_language_line :205`, `doctor :241`, `_check_transcript_health :314`, `transcribe :472` and `analyze :528`. `_load` no longer appears in any of the five files |
| r3 004 (low) | resolved | UT-041 has the repeat case. The matrix has the rows for US-002.EC-3, US-003.AC-1 auto mode and US-003.EC-1. The test IDs match in both directions, counting ranges: UT-001–008, 010–018, 020–023, 025–026, 030–036, 040–053, 055–056, 060–064, IT-001–005 and E2E-001–002 |
| r2 005 (low) | resolved | `audio_convert.py` agrees across Architectural Boundaries (`_spec.md:239`), Core Interfaces (`:331,345`), Integration Points (`:385`) and both Impact rows (`:403,404`). It imports only `constants`. Today's argv uses only `Audio.WHISPER_SAMPLE_RATE` (`transcriber_whispercpp.py:43`), so that is enough. Neither adapter imports the other (AGENTS.md `:66`). Neutral helpers already exist under `adapters/outbound/`: `process_control` and `fs_retry` (AGENTS.md `:144`). `test_commands` (`tests/unit/test_transcriber.py:27-34`) still calls `tr.convert_command`. No text places `wav_convert_command` in `transcriber_whispercpp.py`. `_spec.md:540` cites `convert_command` there, which stays true |

## Verified correct

- **Grep for unconditional wording.** "byte-for-byte", "byte for byte", "exactly today's", "every other key" and "unchanged" were checked across all five files. Every "byte-for-byte" is now conditioned on a fixed language, or on Business Rules › A recording with speech. Every remaining "unchanged" is about something else, for example:
  - exit codes (`_dx.md:100`);
  - the loop rule for long lines;
  - the comparison key;
  - old files loading;
  - `test_two_lines_alternating_are_a_loop_too`;
  - audio retention;
  - first-pass VAD.

  The exception is the matrix label "whisper commands unchanged for the chosen language" (`_tests.md:48`), which is scoped. The baseline issue is in the reopened r3 001.
- **US-003.AC-2** lists both by-design exceptions: `language_detection` lists only the samples sent and may change language, and `health.total_minutes` comes from the measured length.
- **E2E-002 arithmetic.** `--segments 0:6000` keeps both offsets of `sample_offsets(70.0)` = `[10.0, 30.0]`, provided the duration is 70 s.
- **Technical Dependencies** (`_spec.md:470`) names the `whisper-vad-speech-segments` target and what the no-homebrew draft must add, and the draft is left unchanged.

Non-defect observations, left as they are:
- `transcriber_whispercpp.py:43-60` starts one line after `def convert_command` (`:42`).
- `_finite` runs to `:203`, not `:200`.
- The matrix lists US-002.EC-3 before EC-2.

## Not reviewed

- Everything outside the five fixes, by the agreed scope: Windows packaging, VAD figures, the rule B scratch run, `trec doctor` order and the gates' design.

Round state: 1 new issue (`pending`), and 1 round 3 issue reopened (`reviews-003/issue_001.md`, `pending`). The round is not clean.

Next step: dispatch the `fixer` on `docs/tasks/speech-check/reviews-004/issue_001.md` and the reopened `reviews-003/issue_001.md`, or run `/cy-fix-reviews speech-check`. Both are wording changes, so a further verification round can be a single grep pass.

## Fix status (2026-10-23)

The main session fixed both wording items, round 4 issue 001 and round 3 issue 001 (reopened), as the user asked ("siga como proposto"). A grep pass finds no unconditional "today's" or "byte-for-byte" wording about whisper commands left. The two remaining "today's" hits are the conversion argv and the failure behavior, and both are correct.
