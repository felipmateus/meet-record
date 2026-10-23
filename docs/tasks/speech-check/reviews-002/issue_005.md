---
provider: manual
pr:
round: 2
round_created_at: 2026-10-23T15:10:53Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 114
severity: low
author: claude-code
provider_ref:
---

# Issue 005: The no-homebrew plan drops the speech check's tool and conversion

## Review Comment

The spec takes `whisper-vad-speech-segments` from "Homebrew `whisper-cpp`, the same package as `whisper-cli`" (`_spec.md:114`, `:372`, `:454`; ADR-001 `:23`, `:75`). Its conversion is "the same command as the transcriber's" ffmpeg (`_spec.md:327`, `:373`). The untracked draft `docs/tasks/no-homebrew/_test-plan.md` moves both off Homebrew without knowing about this feature:
- Row 7 and S1 (`_test-plan.md:28`, `:47`) build only `whisper-cli` from pinned source. `whisper-vad-speech-segments` is not in the inventory.
- Row 4 (`:25`) replaces the ffmpeg m4a→WAV conversion with `afconvert` in `transcriber_whispercpp.py` and `language_whispercpp.py`. The speech detector is a third consumer, and it is not listed.

Lookup survives in form: `find_tool` (`config.py:48-61`) searches PATH and then `<project>/tools`, so a source-built binary is found if the build puts it in one of those places. Otherwise the advisory design hides the loss. The tool falls back to its bare name, every run logs `Log.SPEECH_CHECK_FAILED`, and `trec doctor` shows `[WARNING] speech check: … not found`. That contradicts that plan's own pass condition, "`trec doctor` green" (`_test-plan.md:76`). The missing-tool error also says "Install with: brew install whisper-cpp" (`Err.EXECUTABLE_MISSING`, `messages.py:106`), which that plan rules out.

Suggested fix: in Technical Dependencies, say that the check depends on whisper.cpp's `whisper-vad-speech-segments` target and on the shared conversion. Have `WhisperCppSpeechDetector.convert_command` reuse the transcriber's command, through a shared helper rather than a copy, so a later afconvert switch covers it. Note the dependency in `docs/tasks/no-homebrew/` when that plan is next edited (the plan is a draft and is outside this spec's scope, so this is a cross-reference, not a change to it).


## Triage

- Decision: `VALID`
- Notes: Valid. The no-homebrew draft builds only `whisper-cli` and moves the conversion to `afconvert` without knowing about this feature.
- Verified: `docs/tasks/no-homebrew/_test-plan.md` rows 4 and 7; `config.py:48-61`.
- Round 3 (2026-10-23): the shared `wav_convert_command` is consistent in Core Interfaces (`_spec.md:327`, `:341`), Integration Points (`:381`), Impact Analysis (`:399`) and Technical Dependencies (`:465`). Extracting it keeps `tests/unit/test_transcriber.py::test_commands` (`:26-33`, the only test that calls `convert_command`) passing as written. Reopened for one stale line. Architectural Boundaries (`_spec.md:235`) still says the new adapter imports "`constants`, `messages`, `domain` and `adapters/outbound/process_control`, the same set as `language_whispercpp.py`". The fix now requires `speech_whispercpp.py` to import `wav_convert_command` from `transcriber_whispercpp.py`, and that set excludes this import. AGENTS.md › Architecture also says adapters do not import each other's internals outside the LLM stack. There is precedent for shared adapter helpers (`detector_pmset.py` imports `process_finder.find_pid`, `speakers_ax.py` imports `launchd`), so the import is acceptable, but the boundary line must name it as an exception. Otherwise the function must move to a neutral module such as `process_control`.

- Verified (round 4, 2026-10-23): `adapters/outbound/audio_convert.py` is consistent in Architectural Boundaries (`_spec.md:239`), Core Interfaces (`:331`, `:345`), Integration Points (`:385`) and both Impact rows (`:403` new, `:404` `transcriber_whispercpp.py` delegates). The module imports only `constants`; today's argv (`transcriber_whispercpp.py:42-43`) uses only `Audio.WHISPER_SAMPLE_RATE`, so it can. Neither adapter imports the other, which fits AGENTS.md › Architecture (`:66`). There is precedent for neutral helpers under `adapters/outbound/` (`process_control`, `fs_retry`, AGENTS.md `:144`). `tests/unit/test_transcriber.py::test_commands` (`:27-34`) calls `tr.convert_command`, which stays, so it passes as written. No text says the function lives in `transcriber_whispercpp.py`. `_spec.md:540` cites `convert_command` there, which is still true after the extraction.

### Resolution

Technical Dependencies names the `whisper-vad-speech-segments` target and what the no-homebrew plan must add when it is next edited; that draft is not changed. The conversion is a shared `wav_convert_command(ffmpeg, audio, wav)` in `transcriber_whispercpp.py`, which `WhisperCppTranscriber.convert_command` delegates to with no behavior change. It appears in Core Interfaces, Integration Points and the Impact Analysis.

Round 3 leftover fixed (2026-10-23): `wav_convert_command` now lives in a new neutral module, `adapters/outbound/audio_convert.py`, which imports only `constants`. The transcriber and the speech detector both import it, and neither imports the other. Updated: Architectural Boundaries, Core Interfaces, Integration Points and Impact Analysis (a new row for `audio_convert.py`).
