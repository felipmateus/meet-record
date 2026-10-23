# Review round 2: speech-check spec

Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`. This is a spec-only review, and no code exists for this feature yet. Code references were checked against the working tree of `feat/language-detection` at `0d58857`. The spec files were not edited.

**Recommendation: approve after fixes.** No new issue is critical or high. Fix issue 001 (medium) and the three reopened round-1 wording leftovers before tasks are cut. Issues 002 to 005 are low and can be fixed in the same pass.

| ID | Severity | Target | Defect |
|---|---|---|---|
| 001 | medium | `_tests.md:230` | G2's "no `too-few-votes`" clause fails `pt` meetings whose fallback is still `pt` (09-44-07 `5 3 0`, 09-56-47 `0 25 2 8`), and no failure path is stated |
| 002 | low | `_spec.md:548` | `· en` claim is false when the fallback is not `pt` (`_language_segment` compares against `pt`); the count line has no fixed slot in `trec status` |
| 003 | low | `_spec.md:343` | The codec "isinstance as for `language_detection`": that decoder coerces with `str`/`int`/`float`, so mirroring it fails UT-023; `bool` passes an `int` check |
| 004 | low | `_tests.md:104` | UT-017's separated case fails if the 3-word separator repeats (scratch run: the 12 separators are flagged) |
| 005 | low | `_spec.md:114` | The no-homebrew draft builds only `whisper-cli` and moves the conversion to afconvert; it drops `whisper-vad-speech-segments` and the third converter, and the check would degrade silently |

Counts: 0 critical, 0 high, 1 medium, 4 low.

## Round 1 fixes verified

The round-1 files were marked `resolved` by the fixer. Each fix was re-checked:

| Round 1 | Verdict | Evidence or leftover |
|---|---|---|
| 001 (high) | **pending**, wording only | Rule substance confirmed at runtime (below). Leftover: `_spec.md:19` and `:33` give "3 times in a row" as sufficient, but UT-012 says it is not without 5 copies in the window, and the texts may differ |
| 002 (medium) | **pending**, one line | The 3-step contract is consistent everywhere except Known Risks `_spec.md:493`, which still has "`speech_check = false` and `trec transcribe <id>` redo it" |
| 003 (medium) | resolved | Guard and `Log.NO_SPEECH_NOTIFY_FAILED` are consistent in spec, dx, stories and UT-042. No "as for the degraded notification" wording left |
| 004 (medium) | resolved | `planned` is consistent in 5 spec places, US-004.EC-4, UT-008 and UT-055. Matches `language.py:87-91` |
| 005 (medium) | resolved | The purge dates are correct. G1 is counted per date. The remaining "28" mentions are the dated Evidence |
| 006 (low) | resolved | "No lines" / `.strip() == ""` everywhere. No "empty transcript.txt" left |
| 007 (low) | **pending**, two lines | `_dx.md`, US-002.AC-1, UT-061 and E2E-001 are fixed. `_spec.md:74` ("goes to the log, like every notification there") and `:547` ("a log line in headless CLI runs") keep the inaccurate wording |

Rule B runtime check, read-only, from a scratch folder outside the repo (`ruleb.py` wraps the real `domain.health._key`/`loop_flags`; a pytest plugin patches it into `teams_recorder.domain` and `teams_recorder.domain.health`):
- UT expectations: UT-010 `[]`, UT-011 `[12, 13, 14]`, UT-012 `[]`, UT-014 spread `[]` and back-to-back `[2..6]`, UT-015 `[]` and `[3, 4, 5]`, UT-017 alternating (both pairs) all flagged, UT-018 within `[26, 27, 28, 29]` and spread `[]`. All as written, apart from UT-017's separated case (issue 004).
- Full suite with the rule patched in: `1 failed, 1316 passed, 10 skipped in 62.13s`. The one failure is `test_a_loop_is_five_copies_within_thirty_segments_ignoring_case_and_punctuation` at line 38 (`[26, 27, 28, 29]` against `[0, 26, 27, 28, 29]`), the test listed in Impact Analysis. `test_two_lines_alternating_are_a_loop_too` and `test_segments_without_words_cover_nothing_but_can_loop` (`♪` ×12, a no-word key) pass. `git status` was unchanged afterwards.

Round state: 3 of 7 round-1 issues are open again (`pending`), and 5 new issues are open. The round is not clean.

## Verified correct

- `test_no_hardcoded_strings`: the guard flags prose literals (with a space, longer than 3 characters) outside `constants.py`, `messages.py` and `domain/status.py`. The spec puts every new text in `messages` (`Log.*`, `Notify.NO_SPEECH`, `Err.VAD_BAD_OUTPUT`) and every identifier and regex in `constants` (`Bin.WHISPER_VAD`, `Proc.SPEECH_CHECK_TIMEOUT`, `Parse.VAD_*`). Tool flags such as `"-vm"` and `"-np"` have no space, so the guard ignores them. `domain/speech.py` needs no strings. No conflict.
- Named fakes and files exist: `ScriptedLanguageDetector` (`tests/integration/test_transcriber_whispercpp.py:42`), `tests/integration/test_cli.py`, `tests/unit/test_cli_language.py`, `tests/unit/test_language.py`, `tests/unit/test_llm_claude.py`, and `FakeNotifier` (`tests/fakes/__init__.py:60`, which never raises, as UT-042 expects: "a new raising fake, or a scripted error"). `FakeTranscriber`, `FakeLanguageDetector` and `InMemoryMeetingRepository` exist.
- The no-audio test exists as `test_transcribe_requires_audio` (`tests/unit/test_processing_use_cases.py:23`). It asserts only `TranscriptionError`, not the `Err.NO_AUDIO_FILE` text the coverage matrix names (`processing.py:79` raises that text). This is accurate enough for US-008.EC-2 ("fails as today"). It is not an issue.
- Reused error constants exist with the shapes the spec relies on: `Err.MODEL_MISSING`, `AUDIO_MISSING`, `EXECUTABLE_MISSING`, `TIMED_OUT`, `STEP_FAILED_CODE` and `EMPTY_TRANSCRIPT` (`messages.py:104-108,135`), and `Cli.NO_PENDING_ANALYSIS` (`messages.py:329`, printed at `cli.py:541`). `_dx.md:180` shortens `EXECUTABLE_MISSING`, which also appends "Install with: brew install whisper-cpp". Tests assert through the constant, so this does not matter.
- `convert_command` (`transcriber_whispercpp.py:42-43`) is the 16 kHz mono s16 ffmpeg command the spec says to reuse. The language adapter's `_run` maps `FileNotFoundError`, `TimeoutExpired` and non-zero exit to the three error texts UT-036 expects (`language_whispercpp.py:85-91`).
- `find_tool` searches PATH and then `<project>/tools`, and falls back to the bare name (`config.py:48-61`), as `_spec.md:116` states.
- `choose_language` with `planned` (UT-008 cases) follows from `language.py:77-92`. `_language` (`processing.py:102-117`) is where the filter and `planned=len(offsets)` go. The duration is read before the lock (`processing.py:80`), so step 6's stand-in sits between steps 5 and 7, as written.

## Not reviewed

- Windows: whether `whisper-bin-x64.zip` ships `whisper-vad-speech-segments.exe` (no network check).
- The VAD per-recording and per-window figures, and the timing claims: not re-measured, as instructed.
- mypy on the planned signatures. No code exists, and the interfaces as written type-check by inspection.
- `trec doctor` line order. Round 1 verified it, and it was not re-checked.
- The real tool's behavior on a no-speech m4a. Round 1 ran it on WAV.

Next step: dispatch the `fixer` on `docs/tasks/speech-check/reviews-002/issue_001.md` to `issue_005.md`, and on the three reopened round-1 files (`reviews-001/issue_001.md`, `issue_002.md`, `issue_007.md`), or run `/cy-fix-reviews speech-check`.

## Fix status (2026-10-23)

All 5 findings were triaged `VALID` and resolved at the user's request ("faça as correções e uma nova review"), with the resolutions proposed in the main session (G2 passes on language, not on reason; no language marker for no speech; a shared conversion function). The three round 1 issues reopened here (001, 002, 007) had their leftover wording fixed in `_spec.md` and are resolved again. Round 3 verifies.
