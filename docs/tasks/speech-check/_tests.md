# Test Specification: Check for speech before transcribing, and stop counting short replies as loops

The canonical test contract for the speech check. Companion to `_spec.md`. It is derived from `_user_stories.md` (behavior), `_spec.md` Part II (components) and `_dx.md` (CLI journeys). There is no `_uiux.md`.

## Strategy

- **Frameworks and harnesses: pytest.**
  - **Use-case tests** run on fakes. There is one new fake, `FakeSpeechDetector` in `tests/fakes/__init__.py`. It returns a scripted `SpeechActivity`, or raises a scripted exception, and records the audio paths it was given. A mapping from audio path to activity covers cases where meetings must differ. The existing fakes are reused: `FakeTranscriber` (its calls are recorded), `FakeLanguageDetector`, `FakeNotifier` and the in-memory repository.
  - **Adapter tests** run the adapter with real ffmpeg against a new stand-in, `tests/fixtures/fake_whisper_vad.py`. The stand-in prints the real tool's format:

    ```
    Detected <n> speech segments:
    Speech segment <i>: start = <cs>, end = <cs>
    ```

    Its flags:
    - `--segments 0:419,458:720` gives centisecond pairs.
    - `--none` prints `Detected 0 speech segments:`.
    - `--garbled` prints no count line.
    - `--mismatch` prints a count that differs from the lines.
    - `--fail` exits 1.
    - `--log FILE` appends the received argv.

    A `ScriptedSpeechDetector` subclass appends the scenario flags to `vad_command`, the way `ScriptedLanguageDetector` does. ffmpeg-dependent cases are skipped when ffmpeg is missing.
- **Execution:**
  - Run `pytest` for the fast suite.
  - The real tool runs with `TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_speech_whispercpp.py`.
  - Never run two pytest sessions at once.
- **Conventions:**
  - Test names start with the case ID in lowercase (`test_ut001_…`). Where an ID already exists in another spec's test file, cite it in the docstring instead.
  - Strings are asserted through the `messages` constants.

## Coverage Matrix

| Source | Behavior | Unit | Integration | E2E |
|---|---|---|---|---|
| US-001.AC-1/AC-2 | No speech: whisper, detection and labelling skipped; empty transcript with the record | UT-001, UT-040, UT-048 | IT-003 | E2E-001 |
| US-001.AC-3 | `no speech` warning logged | UT-040 | — | — |
| US-001.AC-4 | Empty transcript → local analysis, no LLM call | existing `tests/unit/test_llm_claude.py` short-circuit tests (`trivial_analysis`, 0 words) | — | E2E-001 (analyze step) |
| US-001.AC-5 | The two stored no-speech recordings → no speech; all others → speech | gate G1 | — | — |
| US-001.EC-1/EC-3 | 1 s → none; exactly 2.0 s → speech | UT-002 | — | — |
| US-001.EC-2 | Noise → none | gate G1 (the 5-min noise recording) | — | — |
| US-001.EC-4 | Re-transcription replaces the transcript | UT-049 | — | — |
| US-001.EC-5 | Rate mismatch + no speech | UT-047 | — | — |
| US-002 | Notification at ≥ 60 s only | UT-041 | — | — |
| US-002.EC-3 | Two transcriptions → two notifications, no de-duplication | UT-041 (repeat case) | — | — |
| US-002.EC-2 | Notifier failure is caught and logged; the transcript is kept | UT-042 | — | — |
| US-003 | Speech → whisper commands unchanged for the chosen language; record found | UT-043 | IT-004 | E2E-002 |
| US-003.AC-1 (auto mode) | The filter changes only `-l`, by design | UT-056 | — | — |
| US-003.EC-1 | Little speech in a long silence → transcribed | gate G1 (the vans meeting) | — | — |
| US-004.AC-1/EC-3 | Samples without speech not sent; log line | UT-005, UT-044 | — | — |
| US-004.AC-2/AC-3 | Vans still `en`; every result unchanged | gate G2 | — | — |
| US-004.AC-4 | No duration → planned over the audio length | UT-045 | — | — |
| US-004.EC-1 | No sample with speech → `no-usable-sample` | UT-046 | — | — |
| US-004.EC-2 | Check off/failed → samples as today | UT-050, UT-051 | — | — |
| US-004.EC-4 | One sample kept of several planned → no one-vote decision | UT-008, UT-055 | — | — |
| US-005.AC-1–AC-3 | Short-line condition, including runs of different short lines | UT-010–UT-013, UT-017 | — | — |
| US-005.AC-4 | Vans English retry 10.4% → 0% | UT-016, gate G3 | — | — |
| US-005.EC-1/EC-2 | Punctuation-only short; key unchanged | UT-014, UT-015 | — | — |
| US-005.EC-3 | Stored health not rewritten | UT-022 (old file loads unchanged) | — | — |
| US-005.EC-4 | A lone short copy in the window is not flagged | UT-018 | — | — |
| US-006 | `Speech:` lines, no-speech block, status marker and count | UT-060–UT-063 | — | E2E-001, E2E-002 |
| US-007 | Doctor line, four forms, exit code | UT-064 | — | — |
| US-008.AC-1 | Off → no VAD, no record | UT-050 | — | — |
| US-008.AC-2/EC-3 | Off forces whisper on a no-speech meeting; `trec analyze <id>` rebuilds the analysis | UT-052 | — | E2E-001 (steps 6–7) |
| US-008.AC-3 | Installers get the model | UT-026 | — | — |
| US-008.EC-1 | Key absent → on | UT-025 | — | — |
| US-008.EC-2 | Audio purged → today's missing-audio error | existing `TranscribeMeeting` no-audio test (`Err.NO_AUDIO_FILE`) | — | — |
| US-009.AC-1 | Any failure → warning, today's transcription, no error.txt or notification | UT-035, UT-036, UT-051 | IT-002 | — |
| US-009.AC-2 | Format change → failed check, never "no speech" | UT-033, UT-034 | IT-002 | — |
| US-009.EC-1/EC-2 | ffmpeg failure; temp folder removed | UT-036 | IT-001, IT-002 | — |
| `domain/speech.py` | Rounding, overlap arithmetic, sample boundaries, empty inputs | UT-003, UT-004, UT-006, UT-007 | — | — |
| `WhisperCppSpeechDetector` | Command shape; segment parsing (centiseconds), zero segments | UT-030, UT-031, UT-032 | IT-001 | — |
| Codec | `speech` round trip, absent key, damaged shapes | UT-020–UT-023 | — | — |
| Container | Wiring on and off | UT-053 | — | — |
| Real tool | Silence → 0 segments; speech → found | — | IT-005 | — |

## Unit Tests

### Domain: `domain/speech.py` (Spec: Implementation Design › Core Interfaces)

- **UT-001** (happy): `check_speech(SpeechActivity(309.6, ()))` → `SpeechCheck(found=False, speech_seconds=0.0, audio_seconds=309.6, segments=0)`.
- **UT-002** (boundary): with segments summing to 1.99 s → `found` False; to exactly 2.0 s → `found` True; to 1.0 s (the "alô?" case) → `found` False.
- **UT-003** (happy): `check_speech` rounds seconds to 0.1 and counts the segments. For example, `((0.0, 4.19), (4.58, 7.2))` in 27.3 s of audio → `speech_seconds=6.8`, `segments=2`.
- **UT-004** (boundary): `SpeechActivity.speech_between`. A segment straddling the window start or end counts only its overlap, a segment touching `end` exactly adds 0, and an empty activity gives 0.0.
- **UT-005** (happy): `samples_with_speech` on the vans pattern keeps the 4th, 5th and 6th of 8 offsets, in order. The pattern is 8 windows with 0, 0, 0, 9, 14, 5, 0 and 0 s of speech.
- **UT-006** (boundary): a window with exactly 3.0 s of speech is kept, and one with 2.9 s is dropped.
- **UT-007** (boundary): an activity with no segments → `[]`. No offsets → `[]`.

### Domain: `choose_language` planned count (Spec: Business Rules › Language samples; `domain/language.py`)

- **UT-008** (boundary), in `tests/unit/test_language.py`: one sample hearing `en` at p 0.99, with allowed `pt, en` and fallback `pt`:
  - `planned=None` → `en`, `majority` (today's behavior; the existing tests pass unchanged);
  - `planned=1` → `en`, `majority`;
  - `planned=8` → `pt`, `too-few-votes`, `counted == 1`.

  Two samples both hearing `en` with `planned=8` → `en`, `majority`.

### Domain: loop rule (Spec: Business Rules › Loop rule; `domain/health.py`)

- **UT-010** (happy): 77 segments, 8 of them "Okay." spread out with at most 2 in a row, all 8 within 30 segments → no segment flagged. The other 69 lines have 3 or more words and are all different.
- **UT-011** (happy): "e aí" × 6 within 30 segments, 3 of them back to back → exactly the 3 back-to-back copies are flagged, and the 3 spread copies are not.
- **UT-012** (boundary): "e aí" × 3 back to back and no other copy (the window rule needs 5) → none flagged.
- **UT-013** (happy): "eu estou aberto" (3 words) × 5 within 30 segments, never back to back → all 5 flagged, as today.
- **UT-014** (boundary): "..." × 6 spread out → none flagged. "..." × 5 back to back → flagged.
- **UT-015** (state): 8 copies mixing "Ok." and "OK" (one key), never more than 2 consecutive segments, separated by long lines → none flagged. "Ok.", "OK", "ok" back to back with 5 copies in the window → the back-to-back copies are flagged.
- **UT-017** (happy): `["Obrigado.", "Tchau, tchau."] * 5` → all 10 flagged. This is the existing `test_two_lines_alternating_are_a_loop_too`, which keeps passing unchanged; cite it in the new test's docstring rather than duplicating it. Also, "Okay." / "Yeah." alternating 6 times each, back to back → all flagged. The same 12 lines, each separated by a *different* 3-word line (`f"frase distinta {k}"`) → none flagged. A repeated separator would be flagged by the unchanged rule for long lines.
- **UT-018** (state): the `within` case of the existing `test_a_loop_is_five_copies_within_thirty_segments…` ("Ok." at 0, 25 filler lines, "Ok." ×4 at 26–29) → flagged indices `[26, 27, 28, 29]`. The existing assertion `[0, 26, 27, 28, 29]` is updated: an intended contract change listed in the spec's Impact Analysis. The `spread` case of that test still flags nothing.
- **UT-016** (happy): `transcript_health` of the UT-010 transcript with `max_loop_share=0.10` → `loop_share == 0.0` and `degraded` False. The same transcript under the old rule would be degraded (10.4%), and the case documents that.

### Codec (Spec: Data Models)

- **UT-020** (happy): `transcript_to_dict` and back with `speech=SpeechCheck(False, 0.0, 309.6, 0)` and with `SpeechCheck(True, 2676.4, 3138.0, 612)` → equal records. The key is `speech` and the field names are as in `_dx.md` › Files.
- **UT-021** (state): a transcript with `speech=None` → no `speech` key in the dict.
- **UT-022** (state): a `transcript.json` without `speech` (written before the feature) → `speech is None`, and the stored `health` is unchanged.
- **UT-023** (error): damaged `speech` values, read through `FsMeetingRepository`, raise `RepositoryError` naming `transcript.json`. The values are: a string, a list, `found` as the string `"false"`, `speech_seconds` as the string `"1.5"`, `segments` as `2.7`, `segments` as `true`, and `audio_seconds` as `NaN`.

### Config (Spec: Config Lifecycle)

- **UT-025** (happy): defaults → `speech_check` True and `speech_model_path == models_dir / "ggml-silero-v5.1.2.bin"`. `speech_check = false` → `speech_model_path is None`. A key absent from the TOML → True.
- **UT-026** (happy): `scripts/config_tool.py` `vad_path` with `vad = false`, `retry_vad = false` and `speech_check = true` → the Silero model path. With all three false → `""`.

### Adapter: `WhisperCppSpeechDetector` (Spec: Implementation Design › Core Interfaces)

- **UT-030** (happy): `vad_command(wav)` → `[tool, "-vm", model, "-f", wav, "-np", "-t", threads, "-vt", "0.5", "-vsd", "300", "-vp", "150"]`.
- **UT-031** (happy): `parse_speech_segments("Detected 2 speech segments:\nSpeech segment 0: start = 0.00, end = 419.00\nSpeech segment 1: start = 458.00, end = 720.00\n")` → `((0.0, 4.19), (4.58, 7.2))`. Unrelated lines around them (ggml logs) are ignored.
- **UT-032** (boundary): `"Detected 0 speech segments:\n"` → `()`.
- **UT-033** (error): output with segment lines but no `Detected … speech segments` line → `TranscriptionError` with `Err.VAD_BAD_OUTPUT` and the output tail.
- **UT-034** (error): `Detected 3 speech segments:` followed by 2 segment lines → `TranscriptionError(Err.VAD_BAD_OUTPUT)`.
- **UT-035** (error): the model path is missing → `TranscriptionError(Err.MODEL_MISSING)`, raised before any process starts. The audio path is missing → `TranscriptionError(Err.AUDIO_MISSING)`.
- **UT-036** (error): with `subprocess.run` patched, a missing executable gives `Err.EXECUTABLE_MISSING`, a timeout gives `Err.TIMED_OUT`, and exit code 1 gives `Err.STEP_FAILED_CODE` with the tail. In each case the temporary directory no longer exists afterwards.

### Use case: `TranscribeMeeting` (Spec: Core Interfaces › processing.py)

- **UT-040** (happy): `FakeSpeechDetector` returns `SpeechActivity(309.6, ())`. Then:
  - `FakeTranscriber` is never called, and neither are `FakeLanguageDetector` or the retry;
  - the saved transcript has `segments == []`, `language == "pt"` (the fallback), `health is None`, `language_detection is None`, `labels is None` and `speech == SpeechCheck(False, 0.0, 309.6, 0)`;
  - one WARNING record with `Log.NO_SPEECH` is logged.
- **UT-041** (boundary): no speech with `audio_seconds` 59.9 → no notification. With 60.0 → one notification, title `Notify.NO_SPEECH`, body with the meeting id and `1 min`. With 309.6 → one notification whose body says `5 min`. Repeat case (US-002.EC-3): `execute` twice on the same 309.6 s no-speech meeting → `FakeNotifier` has 2 `Notify.NO_SPEECH` calls.
- **UT-042** (error): no speech at 309.6 s with a notifier whose `notify` raises `RuntimeError` (a new raising fake, or `FakeNotifier` with a scripted error) → the transcript is saved, `execute` returns it, and one WARNING record `Log.NO_SPEECH_NOTIFY_FAILED` names the meeting. The existing degraded and rate-mismatch notifications are not part of this case.
- **UT-043** (happy): a fixed `language = "pt"` (no language detector) and `SpeechActivity(3138.0, segments summing to 2676.4 s)`. Then:
  - the arguments recorded by `FakeTranscriber` equal those of a run with `speech_detector=None`, for the first pass and for the retry;
  - the saved transcript has `speech == SpeechCheck(True, 2676.4, 3138.0, n)`.
- **UT-044** (happy): `language_detector` set and an activity matching the vans pattern → `FakeLanguageDetector` receives only the three offsets with speech. `language_detection.samples` holds 3 samples, and one INFO record `Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH` says `5 of 8`.
- **UT-045** (state): `meta.duration_seconds is None` and an activity of 1800.0 s with speech everywhere → the offsets sent equal `sample_offsets(1800.0)` (6 samples), and `health.total_minutes == 30`.
- **UT-046** (boundary): there is speech (2.5 s), but none of the planned windows holds 3.0 s → `FakeLanguageDetector` is not called, `language_detection.reason == "no-usable-sample"`, and the language is the fallback.
- **UT-047** (state): the capture counters show a rate mismatch and the recording has no speech → `Log.RATE_MISMATCH` is still logged, the transcript is the empty one (no `health`, so no rate flag), and there is no rate-mismatch notification.
- **UT-048** (state): no speech, with a speaker log present that would label nothing → `_label` is not run, and no no-labels notice or marker is written.
- **UT-049** (idempotency): a meeting with a saved transcript with speech, transcribed again when the activity is now empty → the stored transcript is the empty one with `found` False. The reverse also holds: speech found again replaces the empty transcript.
- **UT-050** (state): `speech_detector=None` → no activity requested, `speech is None`, and the offsets and whisper arguments are as before the feature.
- **UT-051** (error): `FakeSpeechDetector` raises `TranscriptionError`, or `RuntimeError` → one WARNING `Log.SPEECH_CHECK_FAILED`, the transcription runs as in UT-050, `speech is None`, there is no notification, and `execute` returns normally.
- **UT-052** (state): a meeting saved as no speech, transcribed again with `speech_detector=None` (the off switch) → `FakeTranscriber` is called, and the saved transcript has segments and no `speech`.
- **UT-055** (boundary): `language_detector` set, 8 offsets planned, and an activity with speech only in the 4th window; `FakeLanguageDetector` answers `en` at p 0.99 → `language_detection.reason == "too-few-votes"`, the language is the fallback `pt`, and `language_detection.samples` holds the one sample sent.
- **UT-056** (state): auto mode, 8 planned offsets, and an activity matching the vans pattern (speech in windows 4–6). `FakeLanguageDetector` answers by position, so each run gets its own script:
  - with `speech_detector=None`, the script is `en, en, en, pt, pt, pt, en, en`, and the language is `en` (5 of 8);
  - with the activity, the 3 kept offsets get `pt, pt, pt`, and the language is `pt` (3 of 3);
  - `FakeTranscriber`'s recorded arguments differ only in the language between the two runs.

### Container (Spec: System Architecture)

- **UT-053** (happy): with `speech_check = true`, `build_speech_detector(settings)` returns a `WhisperCppSpeechDetector` whose tool is `find_tool("whisper-vad-speech-segments", project_dir)` and whose model is `settings.speech_model_path`, and `Container.transcribe_meeting().speech_detector` is that object. With `speech_check = false` → None in both.

### CLI (Spec: Developer Experience)

- **UT-060** (happy): `trec transcribe <id>` for a transcript with `speech` found → the line right after ` ok (…)` is `  Speech: 44.6 of 52.3 min (85%)`, followed by `  Health: …`.
- **UT-061** (happy): for a no-speech transcript, the output is, in order:
  - ` ok (0 segments, 0.0 min)`, with the `Log.NO_SPEECH` warning asserted through `caplog` (it goes to stderr in a real run, as in `_dx.md`);
  - `  Speech: none (0.0 s of speech in 5.2 min); whisper did not run`;
  - the `WARNING: the transcript is empty. …` line naming the meeting id;
  - `  Text: …`.

  No line starts with `  Health:`, `  Language:` or `  Speakers:`, and the exit code is 0.
- **UT-062** (state): with `speech_check = false` → `  Speech: not checked ([transcription] speech_check = false)`. With the check on and `speech is None` after the run → `  Speech: not checked (the speech check failed; see the warning above)`, and `caplog` holds the `Log.SPEECH_CHECK_FAILED` warning. The warning is asserted through `caplog`, as UT-063 of language-detection was.
- **UT-063** (happy): `trec status` with two no-speech meetings, one meeting with speech and one transcript made before the feature:
  - each no-speech line ends with `  · no speech` and has no language marker, including one no-speech meeting saved with `language == "en"` (a non-`pt` fallback, US-006.EC-4);
  - the summary has `Recordings without speech: 2`, after `Degraded transcripts:` and before `Unconfirmed claims:`;
  - with no no-speech meeting, there is no count line.
- **UT-064** (happy): `trec doctor`:
  - tool and model present → `[ok ] speech check: on (<path>); a recording with under 2 s of speech is not transcribed`;
  - tool missing → the `[WARNING] … not found …` line;
  - model missing → the `[WARNING] … VAD model missing …` line with the download hint;
  - `speech_check = false` → `[info] speech check: off (…)`.

  The line sits right after the retry line and before `language:`, and the exit code equals the one with the line removed.

## Integration Tests

### Adapter with the stand-in and real ffmpeg

- **IT-001**: `ScriptedSpeechDetector` with `--segments 0:419,458:720 --log L` on a generated 27.3 s `audio.m4a`. The result:
  - `activity()` returns `audio_seconds` 27.3 ± 0.1 (read from the WAV) and segments `((0.0, 4.19), (4.58, 7.2))`;
  - `L` holds one call carrying `-vm`, `-np` and `Audio.VAD_ARGS`;
  - the `trec-speech-` temporary directory is gone afterwards.
- **IT-002**: the same with `--garbled`, then with `--mismatch`, then with `--fail` → each raises `TranscriptionError`, and the temporary directory is gone after each.
- **IT-003**: `TranscribeMeeting` wired to `ScriptedSpeechDetector --none`, `FsMeetingRepository` on a temporary data dir and `FakeTranscriber` → `transcript.json` on disk has `"speech": {"found": false, …}`, `transcript.txt` exists and has no lines (`read_text().strip() == ""`; the repository writes one newline), and `FakeTranscriber` was not called.
- **IT-004**: the same with `--segments 0:2000` (20 s of speech) → `FakeTranscriber` is called once with the same arguments as without a detector, and the file has `"found": true`.

### Real tool (slow, `TREC_REAL_WHISPER=1`)

- **IT-005**: `WhisperCppSpeechDetector` with the real tool and `data/models/ggml-silero-v5.1.2.bin` (read-only):
  - on a generated 10 s silent WAV → `segments == ()`;
  - on a `say -v Luciana`-generated 8 s speech clip (macOS) → `speech_seconds >= 2.0`.

  Skipped without the tool, the model or `say`.

## End-to-End Tests

### A recording with no speech through `trec transcribe`, `trec status` and `trec analyze` (US-001, US-006)

- **E2E-001**: a temporary data dir holds one meeting with a generated 70 s silent `audio.m4a`, and the container uses `ScriptedSpeechDetector --none` and a scripted whisper with `--log`. The steps and results:
  1. `trec transcribe <id>` prints the `_dx.md` no-speech block, with the `Speech: none (0.0 s of speech in 1.2 min)` line and the WARNING naming the id, and exits 0.
  2. The whisper log is empty.
  3. With `caplog.set_level(logging.INFO)`, the log holds the `Notify.NO_SPEECH` title, logged by the headless `LogNotifier`.
  4. `trec status` shows `  · no speech` and `Recordings without speech: 1`.
  5. `trec analyze <id>` writes `analysis.json` with the summary `Err.EMPTY_TRANSCRIPT` and makes no transport call (the Claude analyzer with a counting fake transport).
  6. The recovery (US-008.AC-2): set `speech_check = false` in the test's config, with the scripted whisper now producing segments. `trec transcribe <id>` writes a transcript with segments and no `speech`.
  7. `trec analyze` without an id prints `Cli.NO_PENDING_ANALYSIS` and makes no transport call. `trec analyze <id>` then makes one transport call, and `analysis.json` no longer has the `Err.EMPTY_TRANSCRIPT` summary.

### A recording with speech (US-003, US-006)

- **E2E-002**: the same setup with `--segments 0:6000`, in auto mode, and with a `meta.json` duration of 70 s (`_recorded_at(..., minutes=…)`, as in the existing CLI E2E tests), so both runs plan the same offsets `[10.0, 30.0]` and the filter drops none. Without a duration, the check-off run would plan `[0.0]` and the argv would differ by design. Then `trec transcribe <id>` prints `  Speech: 1.0 of 1.2 min (86%)` before `  Health:`, the scripted whisper ran with the same argv as with `speech_check = false`, compared after each temporary directory (`trec-whisper-…`, `trec-lang-…`) is replaced with a placeholder, because those paths are random per run, and `trec status` shows no `no speech` marker.

## Evaluation gates (evidence, last task; not CI)

All gates read copies of `data/recordings/*/audio.m4a` and write only to temporary folders, never under `data/`. They make no Claude calls.

**Inputs and retention.** The 30-day audio purge removes gate inputs from about 2026-11-04 (spec › Technical Dependencies). The gates run on every meeting with `audio.m4a` on the day they run, and the four named recordings are mandatory:
- 2026-10-08_02-50-26;
- 2026-10-17_10-15-32;
- vans (2026-10-14_15-00-56);
- MARTA (2026-10-08_10-30-52).

If the gates will not run before 2026-11-07, those four are first copied read-only, with the user's approval, to a folder outside `data/` and the repository, and the gates read them from there. Each gate records the date it ran and the number of meetings it read.

- **G1, the verdict on every stored recording.** Run the shipped `WhisperCppSpeechDetector` and `check_speech` on every meeting with `audio.m4a` on the day (28 on 2026-10-22, 29 on 2026-10-23), plus the four named recordings. Pass: 2026-10-08_02-50-26 and 2026-10-17_10-15-32 → `found` False, and every other → `found` True. Record speech seconds and time per meeting in §10. The pre-spec measurement (spec › Evidence) predicts a pass.
- **G2, language detection with the filter.** Run the shipped detector with `samples_with_speech` and the planned-count rule on every recording with speech that has a language-detection G1 result and still has audio. MARTA and vans are mandatory.
  - Pass: every transcript language equals its language-detection G1 language (MARTA and vans `en`, the others `pt`).
    - MARTA and vans, whose language differs from the fallback, must also be decided by `majority`.
    - For the others, a fallback to `pt` (`too-few-votes`, `no-usable-sample`, `no-majority`) passes. Their reasons are recorded as evidence.
  - A failure is any recording whose language changes. In that case the language-sample filter is not shipped as specified: the result goes back to the user before the last task closes, with the per-window evidence. The speech check itself (the MVP) does not depend on G2.
  - Record the samples taken and dropped per meeting, and the unrounded seconds of speech per window for 2026-10-17_09-44-07, whose windows sit near the 3.0 s line.
- **G3, the loop rule.** Recompute `transcript_health` with the shipped rule on every stored `transcript.json` and on the two language-detection G2 transcripts, if a copy is still available; otherwise on transcripts from a fresh G2-style scratch run of MARTA and vans in `en`. Pass:
  - the vans English retry is not degraded, at 0.0% in the Evidence;
  - no stored transcript changes its `degraded` value;
  - the vans `pt`-forced transcript stays degraded;
  - no run of 3 or more *different* short, window-flagged lines appears in a stored or G2 transcript that is not degraded today. If one does, record it, as evidence on the Known Risk of frequent short replies back to back.

  Record each changed share.

## Coverage Decisions

- **The empty-transcript analysis** (US-001.AC-4) is owned by the existing short-circuit tests of `trivial_analysis`. E2E-001 checks the whole path once, with a counting transport.
- **The curator** needs no new test. An empty analysis reaches it like any other analysis without actions, and the activities feature covers that case.
- **The whisper commands of a recording with speech** (Safety Invariant 4): byte-for-byte cases are compared in UT-043 (fakes, fixed language), IT-004 (adapter wiring) and E2E-002 (CLI, temporary paths normalized), each at its own layer. UT-056 owns the auto-mode case, where only `-l` may differ.
- **Windows** gets no automated test beyond `find_tool` (existing tests). It is untested on hardware, like every Windows path.
- **The thresholds** are measured by the gates, not by CI: their values come from the stored recordings.
