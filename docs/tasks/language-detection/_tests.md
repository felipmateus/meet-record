# Test Specification: Detect the meeting's language before transcribing

Canonical test contract for language detection. Companion to `_spec.md`. Derived from `_user_stories.md` (behavior), `_spec.md` Part II (components) and `_dx.md` (CLI journeys). No `_uiux.md`.

## Strategy

- Frameworks and harnesses: pytest. Use-case tests run on fakes: a new `FakeLanguageDetector` in `tests/fakes/__init__.py` (returns scripted samples, records calls, can raise; the script is one list of answers, or a mapping from audio path to answers when meetings must differ), plus the existing `FakeTranscriber`, `FakeNotifier` and `InMemory…` fakes. `FakeTranscriber` gains an optional `by_audio: dict[Path, Transcript]`, which overrides `transcript` for those paths (E2E-002). The adapter is tested against `tests/fixtures/fake_whisper_cli.py`, extended with a `-dl` mode. For each `-f` the stand-in prints `main: processing '<path>' (…)` and then `whisper_full_with_state: auto-detected language: <code> (p = <p>)` to stderr. Answers come from `--langs en:0.99,is:0.96,-` (`-` = no answer for that file; all `-` = whisper ran and printed no answer line, the format-change case); `--fail` and `--log FILE` work as today. A `ScriptedLanguageDetector` subclass appends the scenario flags to `detect_command`, the way `ScriptedTranscriber` does. The name avoids `detector`, which is the Teams call detector (`Container.detector`) and its fakes. ffmpeg-dependent cases are skipped without ffmpeg.
- Execution: `pytest` (fast suite). Real whisper: `TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_language_whispercpp.py`. Do not run two pytest sessions at once.
- Conventions: test names start with the case ID in lowercase (`test_ut001_…`), as in `tests/unit/test_cli_speakers.py`. Strings are asserted through `messages` constants. No literal prose in tests outside fixtures (`test_no_hardcoded_strings.py` covers `src/` only, but keep tests aligned).

## Coverage Matrix

| Source | Behavior | Unit | Integration | E2E |
|---|---|---|---|---|
| US-001 | English meeting transcribed in English | UT-007, UT-030, UT-031 | IT-001, IT-004 | E2E-001 |
| US-001.AC-2 | Retry in the same language | UT-032 | — | — |
| US-001.AC-3 | MARTA detected `en` | gate G1 (evidence, task 6) | — | — |
| US-001.EC-1 | Non-allowed answers discarded | UT-008 | IT-001 | — |
| US-001.EC-2 | Under 30 s: one sample | UT-002, UT-012 | — | — |
| US-001.EC-3 | Long meeting capped at 12 | UT-003 | — | — |
| US-001.EC-4 | Truncated audio: past-the-end samples unanswered | — | IT-003 | — |
| US-001.EC-5 | Rate mismatch: detection still runs | UT-036 | — | — |
| US-002 | Portuguese unchanged | UT-009, UT-038 | IT-004 | — |
| US-002.AC-2 | 25 Portuguese meetings → `pt`, where someone speaks (G1) | gate G1 (evidence, task 6) | — | — |
| US-002.AC-3 | pt message byte-identical | UT-050 | — | — |
| US-002.EC-1/EC-2 | Minority / `es` sample | UT-008, UT-009 | — | — |
| US-003.AC-1 | No usable sample → fallback | UT-010 | — | — |
| US-003.AC-2 | No majority → fallback | UT-011 | — | — |
| US-003.AC-3 | Detector failure → fallback, no error.txt | UT-033, UT-034 | IT-002 | — |
| US-003.EC-1 | One counted vote among several → `too-few-votes` | UT-012 | — | — |
| US-003.EC-2 | No answer line at all → `detection-failed` | UT-016 | IT-002 | — |
| US-003.EC-3 | Unknown duration | UT-004, UT-035 | — | — |
| US-003.EC-4 | Transcription fails after detection | UT-037 | — | — |
| US-004.AC-1 | Analyzer header line for en | UT-050, UT-051 | — | — |
| US-004.AC-2/AC-4 | Literal quotes, Portuguese output | UT-053 (prompt text) | real-call suites when run (`TREC_REAL_CLAUDE_CLI=1`) | — |
| US-004.AC-3 | Verifier header line | UT-052 | — | — |
| US-004.EC-1 | Under 20 words | existing short-circuit tests (`tests/unit/test_llm_claude.py`) | — | — |
| US-004.EC-2 | Old transcript: no line | UT-050 | — | — |
| US-004.EC-3 | English greeting confirms a participant | UT-054 | — | — |
| Prompts | Portuguese output unchanged by the system-prompt edits | UT-053 (text only) | gate G3 (evidence, task 6) | — |
| US-005 | `trec transcribe` Language line, six forms | UT-060–UT-064, UT-062a | — | E2E-001 |
| US-005.AC-4 | Failure line, and the warning it points to logged in a CLI run | UT-063 | — | — |
| US-005.EC-1 | One line per meeting | — | — | E2E-002 |
| US-006.AC-1/AC-2 | `trec status` marker | UT-065, UT-066 | — | E2E-001 |
| US-006.AC-3/AC-4 | Minutes line; both use cases pass the language | UT-070, UT-071, UT-073 | — | — |
| US-006.EC-1 | Other code shown as code | UT-066, UT-072 | — | — |
| US-006.EC-2 | `trec minutes --all` on old meetings | UT-073 | — | — |
| US-007 | `trec doctor` line and its place after the retry line | UT-067, UT-068 | — | — |
| US-008.AC-1 | Default auto | UT-020 | — | — |
| US-008.AC-2 | Fixed code: no detection, no record | UT-021, UT-039, UT-040 | — | — |
| US-008.AC-3 | Fallback is first of languages | UT-022 | — | — |
| US-008.AC-4 | Re-run with a fixed language | UT-039 | — | — |
| US-008.AC-5 | Old transcripts unchanged | UT-041, UT-042 | — | — |
| US-008.EC-1–EC-5 | Validation, in both modes | UT-023, UT-024, UT-025, UT-025a | — | — |
| Codec | `language_detection` round trip, absent, damaged (through the repository) | UT-041, UT-042, UT-043 | — | — |
| Container and fallback source | `fallback_language` reaches whisper, never `"auto"`; `language_detector` field | UT-040, UT-044, UT-045 | — | E2E-001 |
| `sample_offsets` | Offsets, caps, bounds | UT-001–UT-006 | — | — |
| `choose_language` | Vote, threshold, fallback order, tally | UT-007–UT-012, UT-012a, UT-012b, UT-012c | — | — |
| Adapter | Commands, parsing (basename binding, apostrophe in the path), missing model | UT-013–UT-017, UT-015a | IT-001–IT-004 | — |
| Config | Repository `config.toml` loads | UT-020–UT-026 | — | — |

## Unit Tests

### Domain: `sample_offsets` (Spec: Implementation Design › Core Interfaces)

- **UT-001** (happy): `sample_offsets(2185.0)` returns `[134.7, 404.1, 673.4, 942.8, 1212.2, 1481.6, 1750.9, 2020.3]` (8 samples, spaced by 2155/8 s, rounded to 0.1 s).
- **UT-002** (boundary): `sample_offsets(20.0)` returns `[0.0]`, and `sample_offsets(30.0)` returns `[0.0]`.
- **UT-003** (boundary): `sample_offsets(5165.0)` returns 12 offsets (the cap), and `sample_offsets(4 * 3600.0)` returns 12.
- **UT-004** (boundary): `sample_offsets(None)` and `sample_offsets(0.0)` return `[0.0]`.
- **UT-005** (boundary): `sample_offsets(100.0)` returns `[11.7, 35.0, 58.3]` (the floor of 3 fits the 3 whole windows of 100 s), and `sample_offsets(60.0)` returns `[7.5, 22.5]` (only 2 whole windows).
- **UT-006** (happy): every offset of `sample_offsets(d)` for d in (45, 600, 2185, 5165) satisfies `0 <= offset <= d - 30`.

### Domain: `choose_language`

- Every `choose_language` case below passes `allowed=("pt", "en")` and `fallback="pt"` unless it says otherwise.
- **UT-007** (happy): 12 samples answering `en` with p 0.65–0.99 give `LanguageDetection("en", MAJORITY, counted=12, votes=12)`.
- **UT-008** (happy): the vans pattern, samples `[en .993, is .965, is .90, en .997, en .987, is .946, is .979, None]`, gives `en`, `MAJORITY`, `counted=3`, `votes=3`, and all 8 samples kept in `samples`.
- **UT-009** (happy): `[pt .99, pt .99, en .97, pt .99, es .60]` gives `pt`, `MAJORITY`, `counted=4`, `votes=3`.
- **UT-010** (error): `[is .97, gl .80, en .40, None]` gives `pt` (the fallback), `NO_USABLE_SAMPLE`, `counted=0`, `votes=0`.
- **UT-011** (boundary): `[en .9, en .9, pt .9, pt .9]` gives `pt`, `NO_MAJORITY`, `counted=4`, `votes=0`.
- **UT-012** (boundary): one sample `[en .9]` gives `en`, `MAJORITY`, `votes=1`; three samples `[en .9, is .9, None]` give `pt`, `TOO_FEW_VOTES`, `counted=1`, `votes=0` (one vote is under `min_votes`); two samples `[en .9, pt .9]` give `pt`, `NO_MAJORITY`.
- **UT-012a** (boundary): a sample with p exactly `0.5` counts; one with `0.4999` does not.
- **UT-012b** (happy): `allowed=("en", "pt")`, `fallback="en"` with `[is .9]` falls back to `en`.
- **UT-012c** (happy): `counted_tally` of UT-011's detection returns `{"pt": 2, "en": 2}` in `allowed` order.

### Adapter: `WhisperCppLanguageDetector` (Spec: Implementation Design › Core Interfaces)

- **UT-013** (happy): `clip_command(Path("a.m4a"), 134.7, 30.0, Path("c0.wav"))` places `-ss 134.7 -t 30` before `-i a.m4a`, and has `-ac 1 -ar 16000 -c:a pcm_s16le c0.wav`.
- **UT-014** (happy): `detect_command([c0, c1, c2])` has `-l auto`, `-dl`, `-m <model>`, `-t <threads>`, three `-f` in order, and no `-np`.
- **UT-015** (happy): `parse_detection` on the output of three files `c0.wav`–`c2.wav` (processing line + answer each) returns `[("en", 0.993), ("is", 0.965), ("en", 0.997)]`.
- **UT-015a** (boundary): the same output with the clips under `/tmp/O'Brien/trec-lang-x/` (an apostrophe in the directory), and again with bare names (`processing 'c0.wav' (`), returns the same three answers, bound by basename. `detect_command` passes full paths (asserted with UT-014).
- **UT-016** (error): `parse_detection` on output with no answer lines returns `[(None, 0.0)] * 3` (the adapter turns that into `Err.WHISPER_NO_LANGUAGE`, IT-002); with the second file's answer and processing line missing (a clip whisper skipped) it returns `[("en", …), (None, 0.0), ("pt", …)]` (answers bound to files, not to positions).
- **UT-017** (error): `detect` with a missing model raises `TranscriptionError(Err.MODEL_MISSING…)` before spawning anything.

### Config (Spec: Config Lifecycle)

- **UT-020** (happy): `load_settings` on a config without `[transcription] language` gives `language == "auto"`, `languages == ("pt", "en")`, `detects_language is True` and `fallback_language == "pt"`.
- **UT-021** (happy): `language = "en"` gives `detects_language is False` and `fallback_language == "en"`; `languages` is ignored.
- **UT-022** (happy): `languages = ["en", "pt"]` gives `fallback_language == "en"`.
- **UT-023** (error): `language = "pt-BR"`, `"Portuguese"` and `""` each raise `ValueError` with `Err.INVALID_LANGUAGE` formatted with the value.
- **UT-024** (error): `languages = []`, `["auto"]`, `["PT"]` and `[1]` each raise `ValueError` with `Err.INVALID_LANGUAGES`.
- **UT-025** (boundary): `languages = "en"` gives `("en",)`, and `["pt", "en", "pt"]` gives `("pt", "en")`.
- **UT-025a** (error): `language = "pt"` with `languages = []` raises `ValueError` with `Err.INVALID_LANGUAGES`: the list is validated when `language` is a code too.
- **UT-026** (happy): the repository's own `config.toml` loads with `language == "auto"` and `languages == ("pt", "en")`.

### Use case: `TranscribeMeeting` (Spec: Core Interfaces › processing.py)

- **UT-030** (happy): with a `FakeLanguageDetector` answering `en` on every offset, `execute` calls `FakeTranscriber.transcribe(audio, "en")`, and the saved transcript has `language == "en"` and `language_detection.reason == MAJORITY`.
- **UT-031** (happy): the detector receives `sample_offsets(meta.duration_seconds)` and `window_seconds == 30.0`.
- **UT-032** (state): with a looped first pass and a retry transcriber, both calls receive `"en"`.
- **UT-033** (error): a `language_detector` raising `TranscriptionError` gives a transcript in `pt` with `reason == DETECTION_FAILED` and empty `samples`; `LANGUAGE_DETECTION_FAILED` is logged at warning; no notification is sent.
- **UT-034** (error): a detector raising `RuntimeError` (a bug) is handled the same way, and `execute` returns normally.
- **UT-035** (boundary): a meeting whose `meta.json` has no end time calls the detector with `[0.0]`.
- **UT-036** (state): with capture stats showing a rate mismatch, detection still runs, and the health keeps `rate_mismatch=True`.
- **UT-037** (ordering): detection succeeds and the transcriber raises `TranscriptionError`; `execute` raises it and no transcript is saved.
- **UT-038** (happy): with all samples `pt`, the transcriber receives `"pt"`; the record is saved with `MAJORITY`.
- **UT-039** (state): with `language_detector=None` and `language="pt"`, the transcriber receives `"pt"`, no detection runs, and `language_detection is None`.
- **UT-040** (happy): `build_container` on settings with `language="pt"` gives `Container.language_detector is None` and a `transcribe_meeting()` with `language == "pt"`. With `"auto"`, it gives a `WhisperCppLanguageDetector` built from the model path, whisper-cli, ffmpeg and threads of the settings, and `transcribe_meeting()` has `language == "pt"` (never `"auto"`) and `languages == ("pt", "en")`. `Container.detector` is still the call detector in both.
- **UT-044** (error): a container built from `language="auto"` settings, with `language_detector` replaced by a `FakeLanguageDetector` that raises and the transcriber by a `FakeTranscriber`: `transcribe_meeting().execute(id)` calls the transcriber with `"pt"`, never `"auto"`, and the saved transcript has `language == "pt"`.
- **UT-045** (error): `TranscribeMeeting(repo, transcriber, language="auto")` raises `ValueError`.

### Codec (Spec: Data Models)

- **UT-041** (happy): `transcript_to_dict` then `transcript_from_dict` preserves a `LanguageDetection` with 8 samples, `None` answers included.
- **UT-042** (state): a transcript dict without `language_detection` (any of the 27 stored today) loads with `language_detection is None`, and `transcript_to_dict` writes no `language_detection` key for it.
- **UT-043** (error): `FsMeetingRepository.load_transcript` on a `transcript.json` whose `language_detection` is damaged raises `RepositoryError` naming the file, for each of three shapes: a non-object (`"language_detection": "en"`), an unknown reason (`{"language": "en", "reason": "bogus", …}`) and a non-object sample (`"samples": ["en"]`). None of them raises `AttributeError`.

### LLM messages and prompts (Spec: Business Rules › What the model is told)

- **UT-050** (happy): `build_user_message` for a `pt` transcript equals today's output (no `Transcript language` line), and for an `en` transcript contains `Prompt.TRANSCRIPT_LANGUAGE.format(name="English")` in the header, before the transcript.
- **UT-051** (boundary): a transcript in `es` gives the line with the code (`Transcript language: es`).
- **UT-052** (happy): `ClaudeClaimVerifier.user_message` carries the same line for `en` and none for `pt`.
- **UT-053** (happy): `prompts/analyze_system.md` states that `evidence` keeps the transcript's language and that output stays Brazilian Portuguese; `prompts/verify_system.md` carries its sentence about quotes in the language said. For the curator, `Prompt.CURATE_TASK` step 7 contains the quote exception, none of `prompts/curate_system.md` lines 1, 34 and 281 still asks for all content in Brazilian Portuguese without it, and line 43 (the 💬 format) says the quote keeps the language it was said in (asserted by substring of the prompt file and of the `messages` constant).
- **UT-054** (happy): `participant_heard("John Carter", …)` with `Verify.ADDRESS`, on a transcript without labels or roster where the name appears once, is true for each of `Hi John.`, `hello John`, `Hey, John`, `Thanks John` and `thank you, John`; it stays false for `John` mentioned once with no greeting or comma; the existing Portuguese cases in `tests/unit/test_verification.py` pass unchanged.

### CLI (Spec: Developer Experience)

- **UT-060** (happy): the transcribe line for `LanguageDetection("en", MAJORITY, counted=3, votes=3, samples=8 items)` is `  Language: en (heard in 3 of 3 counted samples; 8 taken)`.
- **UT-061** (happy): for `NO_USABLE_SAMPLE` with 8 samples and allowed `("pt", "en")`: `  Language: pt (fallback: no sample heard pt or en clearly; 8 taken)`.
- **UT-062** (happy): for `NO_MAJORITY` with tally pt 2, en 2: `  Language: pt (fallback: no majority among 4 counted samples: pt 2, en 2)`.
- **UT-062a** (happy): for `TOO_FEW_VOTES` with one counted `en` sample among 3: `  Language: pt (fallback: only one counted sample (en); 2 needed; 3 taken)`.
- **UT-063** (happy): for `DETECTION_FAILED`: `  Language: pt (fallback: language detection failed; see the warning above)`. Through `CliRunner` with a container whose `language_detector` raises `TranscriptionError(Err.WHISPER_NO_LANGUAGE…)`, `trec transcribe <id>` exits 0, stdout has that line, and `caplog` holds one WARNING record of `LANGUAGE_DETECTION_FAILED` with the meeting id and the exception's message: the warning the line points to. The test asserts the record with `caplog`, not `CliRunner`'s stderr: pytest's logging plugin captures the record, so it never reaches the last-resort handler there. That the handler prints it on stderr in a real run is stdlib behavior, and this suite does not test it.
- **UT-064** (happy): for a transcript without a record, made with a fixed language: `  Language: pt (fixed by [transcription] language)`.
- **UT-065** (happy): the status segment of an `en` transcript is `  · en`.
- **UT-066** (state): no status segment for a `pt` transcript or a meeting without a transcript; an `es` transcript gives `  · es`.
- **UT-067** (happy): `trec doctor` with `language="auto"` prints `[info] language: detected per meeting among pt, en (fallback pt)` on the line right after the `retry of a degraded transcript:` line.
- **UT-068** (happy): `trec doctor` with `language="pt"` prints `[info] language: pt for every meeting ([transcription] language)`, and the doctor's exit code is unaffected.

### Minutes (Spec: Impact Analysis › MinutesRenderer)

- **UT-070** (happy): `MarkdownMinutesRenderer.render(meeting, analysis, health, language="en")` puts `🗣️ **Idioma:** inglês` on the line after the date line.
- **UT-071** (state): `language="pt"` and `language=None` render no language line, and the rest of the minutes is identical to today's.
- **UT-072** (boundary): `language="es"` renders `🗣️ **Idioma:** es`.
- **UT-073** (state): `FakeMinutesRenderer` records the `language` keyword in `languages`. `AnalyzeMeeting` on an `en` transcript records `"en"`. `RenderMinutes` records the stored transcript's language (`"pt"` for a transcript without `language_detection`) and `None` for a meeting without `transcript.json`.

## Integration Tests

### Adapter with the scripted whisper stand-in and real ffmpeg

- **IT-001**: `ScriptedLanguageDetector(--langs en:0.993,is:0.965,en:0.997)` on a 10-minute generated tone (`ffmpeg -f lavfi sine`) with offsets `[15, 285, 555]` returns three samples with those answers, bound to their offsets. `--log` shows one whisper call with three `-f`.
- **IT-002**: `--fail` makes `detect` raise `TranscriptionError` naming whisper-cli and exit code 2. `--langs -,-,-` (whisper ran, no answer line) makes `detect` raise `TranscriptionError` with `Err.WHISPER_NO_LANGUAGE` carrying the output tail; `TranscribeMeeting` over the real adapter then logs `LANGUAGE_DETECTION_FAILED` with the meeting id and that message, transcribes in `pt`, and stores `reason == "detection-failed"`. `--langs en:0.99,-,pt:0.98` returns a `None` middle sample and raises nothing.
- **IT-003**: offsets `[15, 900]` on a 60-second file: the second clip holds under 1 s of audio, it is left out of the whisper call (the `--log` line has one `-f`), and its sample is `None`.

### Real whisper (slow, `TREC_REAL_WHISPER=1`)

- **IT-004**: macOS `say -v Samantha` speaking 40 s of English and `say -v Luciana` speaking 40 s of Portuguese, each encoded to M4A: the real `WhisperCppLanguageDetector` returns `en` (p ≥ 0.5) for every sample of the first and `pt` for every sample of the second, and `choose_language` picks each. Skipped without `say`, whisper-cli or the model.

## End-to-End Tests

### An English meeting through `trec transcribe` (US-001, US-005, US-006)

- **E2E-001**: `tests/integration/test_cli.py` harness (`ENV_PROJECT_DIR` = tmp project with a `config.toml` whose `[transcription]` sets `language = "auto"`). A recorded meeting with a 3-minute generated `audio.m4a`; `cli.build_container` patched so the container's `transcriber` is `ScriptedTranscriber` and its `language_detector` is `ScriptedLanguageDetector(--langs en:0.99,en:0.98,en:0.97 --log <file>)`; the call `detector` is left alone. `trec transcribe <id>` exits 0 and prints `  Language: en (heard in 3 of 3 counted samples; 3 taken)`; `transcript.json` has `"language": "en"` and `language_detection.reason == "majority"`; `trec status` prints the meeting's line ending in `  · en`; the stand-in's `--log` file has exactly one line (one detection call), so a run that bypassed the scripted detector fails.
- **E2E-002**: the E2E-001 harness with two recorded meetings, A and B, and `retry_on_loop = false` in the tmp `config.toml` (no retry transcriber). `cli.build_container` is patched so the container's `language_detector` is a `FakeLanguageDetector` keyed by audio path (A: `en` ×3, B: `pt` ×3) and its `transcriber` a `FakeTranscriber` whose `by_audio` gives B `looped_transcript()`, so B is degraded and A is not. A scripted whisper stand-in cannot do this: `--langs` and `--loop-always` apply to every call. `trec transcribe` (no id) prints one `Language:` line per meeting, `en` for A and `pt` for B, each after that meeting's health block (for B, after its `WARNING: degraded transcript` line) and before its `Text:` line.

## Evaluation gates (evidence, task 6; not CI)

- **G1**: the shipped adapter and `choose_language`, run read-only against every meeting in `data/recordings/` with `audio.m4a` (27 on 2026-10-21; clips in a temp dir, nothing written to the meeting folders). Pass: 2026-10-08_10-30-52 and 2026-10-14_15-00-56 → `en`; every other recording in which someone speaks → `pt` (by majority or fallback); no meeting gets a non-allowed language. Recordings with only silence or noise are outside the gate, because no language is right for them; they are recorded in §10 as known cases. Record the per-meeting result and the detection time in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10.
  - *Note, 2026-10-22: the criterion read "every other meeting → `pt`" until the G1 run. Two recordings without speech (2026-10-08_02-50-26, 10.9 s of silence; 2026-10-17_10-15-32, noise only) came out `en` on p 0.49 to 0.68, and the criterion was changed to "every other recording in which someone speaks" by the user's decision of 2026-10-22, since no language is right for a recording with no speech. A speech check before the vote is a separate future spec. This note is the record of the change.*
- **G2**: on scratch copies (never in `data/recordings/`), transcribe the MARTA meeting with `-l en` through `TranscribeMeeting` with the real adapters (first pass plus the retry if degraded). Pass: not degraded, and text in at least 95% of its minutes. Record the vans meeting's English result (first pass and retry) next to it as a known bad-audio case, without a pass/fail.
- **G3**: the changed system prompts, measured on Portuguese output with the shipped code. It spends the Claude Code subscription (about 3 × (4 verifier calls + 2 analyses, each with its verification and a curator pass)), so ask the user before running it.
  - **Setup.** Two checkouts: "old" is a git worktree at the base commit, with today's prompts; "new" is the feature branch. Prompts are read from `settings.prompts_dir`, under the project dir. Pick three Portuguese meetings from `data/recordings/` that have `analysis.json`, and copy each one's `meta.json`, `transcript.json` and `analysis.json` into two scratch data dirs, one per checkout, never under `data/`. Each checkout's `config.toml` sets `paths.data_dir` to its scratch dir and `language = "pt"`, so nothing is detected or re-transcribed.
  - **(a) Verifier, same claims on both sides.** A throwaway script (not committed) loads each copied meeting, analysis and transcript through the checkout's `FsMeetingRepository`. It runs `VerifyAnalysis(build_verifier(settings), settings.user_name).execute(meeting, analysis, transcript)` twice per checkout on the stored analysis, so both sides verify identical claims. It writes each claim's status and reason to JSON. Pass: every claim whose two old runs agree gets the same status from both new runs. A claim on which the old runs disagree is run-to-run noise and is listed, not judged. Every reason is in Brazilian Portuguese.
  - **(b) Analyzer and curator.** `trec analyze <id>` in each checkout, on its scratch dir, with the stored `analysis.json` removed first, runs the analysis, its verification and a curator pass from an empty activities document. Pass: every field and the activities document are in Brazilian Portuguese, every `evidence` and 💬 quote is literal, and the user signs off the side-by-side diff (no decision, action or owner gained or lost that the prompt change explains).
  - Record (a), (b) and the noise list in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10. `scripts/fidelity_eval.py` is not used: its `defend` sends its own inline verifier prompt, not `prompts/verify_system.md`.

## Coverage Decisions

- The vote and offset rules are pure, so they are owned by unit tests (UT-001–UT-012c); nothing re-tests them at integration level.
- The whisper output format is the riskiest external contract: parsing is owned by UT-015/UT-016, the multi-file call by IT-001, and the real format by IT-004.
- Portuguese output with literal quotes (US-004.AC-2/AC-4) is model behavior: no fast automated test can own it. UT-053 owns the prompt text; the opt-in real-call suites exercise it when the user runs them (they spend the subscription, ask first).
- Gates G1 and G2 own the real-meeting claims (US-001.AC-3, US-002.AC-2); they read real recordings and are run once, by hand, as task evidence. G3 owns the claim that the system-prompt edits leave Portuguese output unchanged; UT-053 only proves the text is there.
- The daemon path needs no new test: the daemon calls the same `Pipeline` → `TranscribeMeeting` (`tests/unit/test_pipeline.py` already drives it with fakes, and the use-case cases above own the new step).
