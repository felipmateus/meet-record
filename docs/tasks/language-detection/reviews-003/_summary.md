# Review round 3: language-detection (spec)

- Round: 3 · Created: 2026-10-22T00:30:08Z · Reviewer: claude-code · Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`, checked against the current source. No code for this feature exists yet.
- Recommendation: safe to approve with follow-ups. There are no blocking (critical or high) issues.
- New issues: 4 (critical 0, high 0, medium 1, low 3).

| Issue | Severity | Target | Defect |
|---|---|---|---|
| 001 | medium | `_spec.md:387` | The analyzer, verifier and curator prompts change for every Portuguese meeting, but the spec says those requests stay identical, and no gate re-measures them (precedent: `REQUIREMENTS:549` item 4). UT-053 covers 3 of the 4 curator lines. |
| 002 | low | `_spec.md:332` | The docs-sync list misses `prd/appendix/data-layout.md`, `integrations.md`, `REQUIREMENTS:136`, `README.md:7`, `AGENTS.md:133` (reviews-002 issue 001 item 5 was not applied) and `guide/commands.md`. |
| 003 | low | `_dx.md:157` | "See the log" and "(or the CLI's log)": only `trec daemon` configures logging (`cli.py:779`). In a CLI run the warning goes bare to stderr, mixed into the `Transcribing…` line, and the info lines are dropped. |
| 004 | low | `_spec.md:325` | `Verify.ADDRESS` (`constants.py:244-247`) matches Portuguese greetings only, so English meetings get more ⚠️ on participants. This is neither in scope nor listed as a known risk. |

## Reviews-002 verification

All three issues were already `resolved` when this round started, and none was `valid`. No status was changed. Each fix was re-checked in the current files:

| Issue | Result | Evidence |
|---|---|---|
| 001 curator Portuguese-only wording | holds, with one gap | `_spec.md:327` (new curator row with the step-7 text, lines 1/34/43/281, and the risk note corrected to unconditional), `:421-422` (File References include `messages.py:684-693`), UT-053 (`_tests.md:129`). Checked against `messages.py:684-693` and `curate_system.md:1, 34, 281`. Gap: suggested-fix item 5 (`AGENTS.md:133`) was not applied. It is tracked in new issue 002. UT-053 lists 3 of the 4 lines (new issue 001). |
| 002 optional directory in the regex | holds | `_spec.md:266-267`, UT-015a (`_tests.md:88`). Checked at runtime: real `whisper-cli` 1.9.4 `-l auto -dl` with two `-f` under `…/O'Brien/trec-lang-x/` printed `main: processing '…/O'Brien/trec-lang-x/c0.wav' (…` and `auto-detected language: en (p = 0.999880)`, and exited 0. The spec's regexes, run in Python `re`, bound `c0.wav` → `en`, and also matched the bare name `c0.wav` and a Windows path with an apostrophe. A clip cut past the end (78-byte WAV) printed `failed to read audio file` with no answer, and the exit code was still 0, which matches the spec's `None` sample. |
| 003 unknown first code; timeout text | holds | `_dx.md:162` reads `whisper-cli: timed out after 300s`, which matches `Err.TIMED_OUT` (`messages.py:107`). `_dx.md:175` covers `["pt", "xx"]` against `["xx", "pt"]`. |

Round-1 spot check after the round-2 edits: still in place. That covers the single fallback source (`_spec.md:229-241`, Safety Invariant 6, UT-040/044/045; `container.py:130` still passes `settings.language` positionally, as the spec says it must change), `WHISPER_NO_LANGUAGE` (`_spec.md:265, 310`), the purge/lock wording (`_spec.md:385`), the timing (about 0.6 s + about 2 s per sample everywhere), `FakeMinutesRenderer`/`RenderMinutes` (`_spec.md:328`), the codec `isinstance` rule (`_spec.md:291`), `language_detector` naming, and `too-few-votes`.

## Checked and correct

- Offset arithmetic: UT-001, UT-002, UT-003, UT-005, the golden path (3138 s gives 11 samples) and E2E-001 (180 s gives 3).
- Vote rules: `min_votes` only matters at one counted sample, and every reason list agrees across the five files.
- Data: `data/recordings/` has 27 meetings, each with `audio.m4a` and a `transcript.json` with `language: "pt"` and no `language_detection`, and every `meta.json` has an end time. This was read only.
- Code claims: `TranscribeMeeting` fields and `_checked`/`_transcribe` (`processing.py:49-162`). `label_segments` uses `dataclasses.replace` (`domain/speakers.py:212`), so the new `Transcript` field survives labelling. `transcript_from_dict`/`_decode` error mapping. `Settings`/`load_settings`/`_as_list`/`_parse_share` (`config.py`). `build_retry_transcriber`. The CLI `status`/`doctor`/`transcribe` lines and their slots. `MinutesRenderer.render` and `FakeMinutesRenderer` (`tests/fakes/__init__.py:432-437`). `ScriptedTranscriber` and `fake_whisper_cli.py` (`--fail`, `--log`, `--loop-always`).
- Eval scripts: `wiki_corpus.py:223-256` goes through `transcribe_meeting()`, so it inherits `auto`. `fidelity_eval.py:1169, 1191` pass `"pt"` explicitly and are unaffected.

## Not reached

The turn limit ended the review early. Three possible points were not written up:
- E2E-002 needs answers that differ per meeting, and a `ScriptedLanguageDetector` with a fixed `--langs` cannot give them.
- Whether `languages` is validated when `language` is a code (`_dx.md:173` against US-008.EC-5).
- Whether the doctor line goes before or after the retry line.

Next step: send `issue_001.md`–`issue_004.md` to the `fixer`, or run `/cy-fix-reviews language-detection`.

## Points not reached, settled during the fixes (2026-10-21)

The user asked for these three to be checked and fixed together with issues 001–004. They are recorded here, not as issue files, because the reviewer did not write them up.

- **E2E-002 needs different answers per meeting.** Confirmed: `--langs` and `--loop-always` apply to every call of the stand-in, so both meetings would get the same language and both would be degraded. E2E-002 now uses a `FakeLanguageDetector` keyed by audio path and a `FakeTranscriber` with `by_audio`, with `retry_on_loop = false` (`_tests.md` Strategy and E2E-002).
- **Whether `languages` is validated when `language` is a code.** Decided: validated in both modes, used only in `"auto"` mode, so a typo surfaces before the switch to `"auto"` (`_spec.md` Business Rules › Validation, US-008.EC-5, `_dx.md` Config and Errors, new UT-025a).
- **Where the doctor line goes.** Decided: right after the `retry of a degraded transcript:` line, keeping the two loop-guard lines together (`_dx.md` golden path and `trec doctor`, US-007.AC-4, UT-067).
