# Review round 1: speech-check spec

Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`. This is a spec-only review; no code exists for this feature yet. Code references were checked against the working tree of `feat/language-detection`. There are no previous rounds.

Recommendation: approve after fixes. Issue 001 (high) must be fixed before tasks are cut. Issues 002 to 005 should be settled in the spec too, because each one changes a test or a contract the implementer would otherwise guess at.

| ID | Severity | Target | Defect |
|---|---|---|---|
| 001 | high | `_spec.md:86` | The same-key run rule breaks `test_two_lines_alternating_are_a_loop_too` and `test_a_loop_is_five…` (`within`), and it drops short-line cycle detection; neither is listed |
| 002 | medium | `_spec.md:89` | Recovery (`speech_check = false` + `trec transcribe <id>`) leaves the empty analysis, the minutes and the `skipped_empty` curator pass; `trec analyze` with no id does nothing for the meeting |
| 003 | medium | `_tests.md:124` | UT-042 / US-002.EC-2 rely on a notifier guard that does not exist (`processing.py:94-99` has no try/except) |
| 004 | medium | `_spec.md:77` | After the filter, `choose_language`'s one-sample rule (`language.py:87`) lets one speech window decide a long meeting |
| 005 | medium | `_tests.md:204` | The gate recordings will be purged by the 30-day audio retention (from about 2026-11-04); the count is already 29 |
| 006 | low | `_tests.md:174` | `transcript.txt` is `"\n"`, not empty (`repository_fs.py:192`); IT-003 fails as written |
| 007 | low | `_dx.md:24` | The no-speech CLI block omits the stderr WARNING; in a CLI run `LogNotifier` INFO is discarded, so the notification is not really "in the log" |

Counts: 0 critical, 1 high, 4 medium, 2 low.

Verified correct:
- `whisper-vad-speech-segments` is installed at `/opt/homebrew/bin` (whisper.cpp 1.9.4). Its help lists `-vm -f -np -t -vt -vsd -vp` and says "Output timestamps are in centiseconds".
- A run in a scratch folder on a generated clip (3 s silence + `say` speech + 3 s silence) printed `Detected 1 speech segments:` / `Speech segment 0: start = 289.00, end = 879.00` on stdout. A 10 s silent WAV printed `Detected 0 speech segments:` with exit 0. Supported inputs are flac/mp3/ogg/wav, so the m4a-to-WAV conversion is needed.
- `Audio.VAD_ARGS == ["-vt","0.5","-vsd","300","-vp","150"]` (`constants.py:203`). `Proc`, `Parse` and `Bin` exist.
- `find_tool` falls back to the bare name, so a missing tool shows up as an executable-missing error at run time (`config.py:50-61`). `scripts/config_tool.py:25` is `vad_path`.
- `trivial_analysis` is at `llm_schema.py:23-33` and returns `Err.EMPTY_TRANSCRIPT` for 0 words, and `ClaudeAnalyzer.analyze` short-circuits on it before any transport call.
- Downstream consumers of an empty transcript: the verifier makes no call when there are no claims, the curator logs `skipped_empty` with no LLM call, the minutes get no banner when health is `None`, and status shows no speaker marker when `labels` is `None`. None of these crash or hallucinate.
- The doctor's retry line is followed by the language line inside `_check_transcript_health`, so the planned slot exists. The CLI's `trec transcribe` and `trec status` use the headless `LogNotifier`.
- The loop Evidence table was reproduced exactly, read-only: stored transcripts (MARTA 1.0→1.0, vans 68.7→65.7, 09-56-47 3.8→1.9, all others no loops) and the G2 scratch transcripts (vans en retry 10.4→0.0, MARTA en 1.2→0.4).
- File references `processing.py:32-140`, `health.py:22-50`, `codec.py:155-178` and `config.py` ranges match the current tree.

Not reviewed (the round was cut short):
- The VAD speech-per-recording and per-sample-window figures and the timing claims (19 s / 86 min) were not re-measured on the stored audio.
- Windows: whether `whisper-bin-x64.zip` ships `whisper-vad-speech-segments.exe`.
- `test_no_hardcoded_strings` impact; codec isinstance details (the spec's "as for `language_detection`" is loose: that decoder uses `int()`/`float()`).
- That the named test files and fakes exist (`ScriptedLanguageDetector`, `tests/integration/test_cli.py`, the no-audio test).
- The `trec status` count-line placement; the `· en` claim when the fallback is not `pt`; the mypy implications; the cross-check with the untracked `docs/tasks/no-homebrew/` spec (it may move whisper.cpp off Homebrew).

## Fix status (2026-10-23)

All 7 findings were triaged `VALID` and resolved in their owning files (`_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md`, `adrs/adr-001.md`). The user chose to apply every finding, and for 001 the flagged-short-run reading (option B). Each issue file records what was verified and the resolution. Round 2 verifies the fixes and covers the areas listed under "Not reviewed".
