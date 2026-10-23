---
provider: manual
pr:
round: 3
round_created_at: 2026-10-23T16:25:44Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 214
severity: low
author: claude-code
provider_ref:
---

# Issue 002: E2E-002 compares logged whisper argv that holds random temp paths

## Review Comment

E2E-002 (`_tests.md:214`) asserts that "the scripted whisper ran with the same argv as with `speech_check = false`". This cannot hold literally between two runs:
- `WhisperCppTranscriber.transcribe` builds its WAV and its output prefix inside `tempfile.TemporaryDirectory(prefix="trec-whisper-")` (`transcriber_whispercpp.py:68-72`). The argv therefore carries `-f <random dir>/audio16k.wav` and `-of <random dir>/out`.
- `fake_whisper_cli.py --log` appends `sys.argv[1:]` verbatim as one JSON line (`tests/fixtures/fake_whisper_cli.py:26-29`).
- In the E2E's default auto mode, the language detection's `-f` clips also come from a random `trec-lang-` dir (`language_whispercpp.py:63-73`).

The two runs log different paths, so a plain equality check fails even when the feature is correct. UT-043 and IT-004 are not affected: `FakeTranscriber` records the meeting's audio path and the language, and both are stable.

Suggested fix: compare the argv after replacing each temporary directory with a placeholder. Alternatively, compare only the flags and values that are not paths: `-l`, `-mc`, `-t`, `-m`, the VAD arguments, and whether `--vad` is present. Say which approach the test uses, so that the "same argv" check stays meaningful.

## Triage

- Decision: `VALID`
- Notes: Valid. The argv carries random `trec-whisper-`/`trec-lang-` paths.
- Verified: `transcriber_whispercpp.py:68-72`, `tests/fixtures/fake_whisper_cli.py:26-29`.

- Verified (round 4, 2026-10-23): E2E-002 (`_tests.md:221`) names both random prefixes (`trec-whisper-` from `transcriber_whispercpp.py:68`, `trec-lang-` from `language_whispercpp.py`) and says each temporary directory is replaced with a placeholder before the comparison, and why. That is implementable as written. A separate gap in the case's preconditions, which issue 001's scoping exposed, is tracked as `reviews-004/issue_001.md`.

### Resolution

E2E-002 compares the argv after replacing each temporary directory with a placeholder, and says why.
