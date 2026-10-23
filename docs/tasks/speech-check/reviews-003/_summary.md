# Review round 3: speech-check spec

Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`. This is a spec-only review: no code exists for this feature yet. Code references were checked against the working tree of `feat/language-detection` at `0d58857`. The spec files were not edited. The decisions the user approved on 2026-10-23 were taken as given and not re-argued.

**Recommendation: approve after fixes.** No issue is critical or high. Before tasks are cut:
- fix issue 001 (medium), the unconditional "byte-for-byte" promise;
- fix the reopened leftover of round 2 issue 005 (one Architectural Boundaries line).

Issues 002 to 004 are low and can go in the same pass.

| ID | Severity | Target | Defect |
|---|---|---|---|
| 001 | medium | `_spec.md:516` | Safety Invariant 4, Goals, BR `:75`, US-003.AC-1/AC-2 and ADR promise byte-identical whisper commands with no condition. The sample filter, the planned-count rule and the duration stand-in can change `-l` (and `language_detection.samples`) by design |
| 002 | low | `_tests.md:214` | E2E-002 compares logged whisper argv across two runs. The argv holds random `trec-whisper-`/`trec-lang-` temp paths, so plain equality fails |
| 003 | low | `_spec.md:526` | File References: `_load` does not exist (it is `_decode`, `repository_fs.py:68-73`); `_transcribe`, `LanguageRules`/`sample_offsets`, `transcribe_meeting()` and `retry_vad` parsing fall outside the cited ranges |
| 004 | low | `_tests.md:45` | US-002.EC-3 (two transcriptions → two notifications, no de-duplication) has no test; US-003.EC-1 is not mapped (only G1 covers it) |

Counts: 0 critical, 0 high, 1 medium, 3 low.

## Previous fixes verified

### Round 2

| Round 2 | Verdict | Evidence |
|---|---|---|
| 001 (medium) | resolved | G2 pass line `_tests.md:229-234`: language equal; `majority` only for MARTA and vans; a language change goes back to the user; MVP independent. The old "No recording loses …" line is gone from all five files. US-004.AC-3 says "result equals the G1 result", and in context (AC-2 "the result is still `en`") "result" means the language. Not reopened |
| 002 (low) | resolved | `_dx.md:104`, `_spec.md:398,558`, US-006.AC-3/EC-4 and UT-063 agree: no language marker for no speech, whatever the fallback; count line after `Degraded transcripts:` and the optional rate-mismatch line, before `Unconfirmed claims:`. This matches `cli.py:124-127`, and the `_dx.md:109-111` lines match `messages.py:242,246` (`Degraded transcripts: {count}`, `Unconfirmed claims: {claims} in {meetings} meeting(s)`). "follows the existing summary lines" is gone. `_spec.md:558` still says "never shows `· en`", but now as a consequence of "prints no language marker … whatever the fallback", which is correct |
| 003 (low) | resolved | `_spec.md:345-351` spells out the checks, and "as for `language_detection`" is gone. Scratch run (outside the repo, real `codec._finite` and `json.loads`, which accepts `NaN`): each UT-023 value fails as stated — string → TypeError, list → TypeError, `found: "false"`, `speech_seconds: "1.5"`, `segments: 2.7`, `segments: true` and `audio_seconds: NaN` all raise `TypeError`, and the valid record loads. `_decode` turns `TypeError` into `RepositoryError(Err.BAD_JSON …)` naming the path (`repository_fs.py:68-73`). The cited name `_load` is wrong: see issue 003 |
| 004 (low) | resolved | UT-017 `_tests.md:104` says each separator is a *different* 3-word line and explains why |
| 005 (low) | **pending**, one line | `wav_convert_command` is consistent at `_spec.md:327,341,381,399,465`. "same as WhisperCppTranscriber.convert_command" is gone. The extraction keeps `tests/unit/test_transcriber.py::test_commands` (`:26-33`, the only caller of `convert_command` in tests) passing as written, because the method stays and returns the same list. Reopened: Architectural Boundaries (`_spec.md:235`) still limits the adapter's imports to "the same set as `language_whispercpp.py`", which excludes the new import from `transcriber_whispercpp.py`. AGENTS.md › Architecture also needs the exception stated. Note added to `reviews-002/issue_005.md` |

### Round 1 (reopened in round 2)

| Round 1 | Verdict | Evidence |
|---|---|---|
| 001 (high) | resolved | `_spec.md:19` and `:33` now state rule B: flagged by the window rule *and* in a run of 3+ short flagged lines, texts may differ. "3 times in a row" as a sufficient condition and "unless they repeat 3 or more times" are gone. `:55` says "short, repeated lines in a row" and then "may differ", which is consistent |
| 002 (medium) | resolved | Known Risks `_spec.md:503` gives the three-step recovery. "redo it" with two steps is gone |
| 007 (low) | resolved | `_spec.md:74` and `:557` say the `LogNotifier` logs at info level, which a CLI run does not show. "goes to the log, like every notification" and "a log line in headless CLI runs" are gone |

The other round 1 issues (003–006) were resolved in round 2 and were not reopened.

Round state: 4 new issues are open (`pending`), and 1 round 2 issue is reopened (`reviews-002/issue_005.md`, `pending`). The round is not clean.

## Verified correct

- **Test IDs.** Every ID in the coverage matrix is defined, and every defined ID is in the matrix, counting the ranges UT-010–UT-013, UT-020–UT-023 and UT-060–UT-063. The defined IDs are UT-001–008, 010–018, 020–023, 025–026, 030–036, 040–053, 055, 060–064, IT-001–005 and E2E-001–002.
- **Story coverage.** Every story AC and EC is mapped, except the two in issue 004.
- **`trec status` against the code.** `_language_segment` (`cli.py:197-202`) compares with `Audio.DEFAULT_LANGUAGE`, so the no-speech suppression is a needed change, as the Impact row says. `MEETING_LINE` (`messages.py:236`) and `next_step` (`status.py:55-61`, `None` for `analyzed`) give exactly the golden-path line `  2026-10-17_10-15-32  [analyzed]  · no speech`. `_speakers_segment(None)` is `""`, so a no-speech meeting has no other marker.
- **`trec transcribe` against the code.** ` ok (0 segments, 0.0 min)` follows from `TRANSCRIBED_OK` with `transcript.duration_seconds / 60` (`cli.py:498`). `_language_line` is printed unconditionally today (`cli.py:507`), so the no-speech branch must skip it, as the Impact row says. `_speakers_line` is already `None` without labels.
- **Use case and language detection.** An empty kept-sample list is safe. `WhisperCppLanguageDetector.detect(audio, [], …)` returns `[]` without running whisper (`language_whispercpp.py:62-71`). `choose_language([], …)` gives `no-usable-sample` with the fallback (scratch run), so US-004.EC-1 holds even if the use case calls the detector.
- **Numbers in the cases.** `sample_offsets(1800.0)` has 6 offsets (UT-045), `sample_offsets(70.0)` is `[10.0, 30.0]` (E2E-002, both inside 60 s of speech), and 36.4 min gives 8 (UT-044/UT-055).
- **Display arithmetic.** It matches `_dx.md`: 2676.4/3138.0 → `44.6 of 52.3 min (85%)`; 60/70 s → `1.0 of 1.2 min (86%)`; 309.6 s → `5.2 min`.
- **Consistency of rules.** Safety Invariants 1–3 and 5–8, the Business Rules and `_dx.md` do not contradict each other: advisory failure, the guarded no-speech notification, the lock, rule B and the three-step recovery. Invariant 4 is the exception (issue 001).
- **File References.** Most ranges match the code: `health.py:22-50`, `test_transcript_health.py:30-38,64-66`, `processing.py:93-99`, `repository_fs.py:189-192`, `cli.py:527-570`, `models.py:97-163`, `codec.py:140-200` (`_finite` `:195-200`), `llm_schema.py:23`, `config.py:50-61` and `config_tool.py:25`. The ones that do not are in issue 003.

## Not reviewed

- Windows: whether `whisper-bin-x64.zip` ships `whisper-vad-speech-segments.exe` (no network check).
- The VAD figures and timing claims in Evidence: not re-measured, by design.
- The rule B scratch run: not repeated. Round 2's run covered UT-010–UT-018, and this round only checked the reworded text.
- `trec doctor` line order and `_check_transcript_health`: round 1 verified them, and they were not re-checked.
- mypy on the planned signatures: no code exists.
- The `docs/tasks/no-homebrew/` draft: only the cross-reference was checked, per the user's decision.

Next step: dispatch the `fixer` on `docs/tasks/speech-check/reviews-003/issue_001.md` to `issue_004.md` and on the reopened `reviews-002/issue_005.md`, or run `/cy-fix-reviews speech-check`.

## Fix status (2026-10-23)

All 4 findings were triaged `VALID` and resolved at the user's request ("siga como proposto"), using the resolutions proposed in the main session. Round 2 issue 005, reopened here, is resolved by moving `wav_convert_command` to a new neutral module, `adapters/outbound/audio_convert.py`, so neither adapter imports the other. Architectural Boundaries names it. Round 4 is a verification-only round, as the user agreed.
