---
provider: manual
pr:
round: 2
round_created_at: 2026-10-22T00:02:17Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 266
severity: low
author: claude-code
provider_ref:
---

# Issue 002: Processing regex needs a directory separator before c<i>.wav

## Review Comment

The round-1 fix for issue 011 binds answers to clips by basename with `WHISPER_PROCESSING = r"processing '.*[\\/](c\d+\.wav)' \("`. That pattern requires a `/` or `\` before `c<i>.wav`. whisper-cli prints the `-f` argument as it was given. If the adapter passes bare names and runs whisper with `cwd=` the temporary directory (a natural way to avoid apostrophes and Windows paths altogether), the processing line is `main: processing 'c0.wav' (480000 samples, …)` and the regex matches nothing. Checked with Python `re`:

```
"main: processing '/tmp/O'Brien/trec-lang-x/c0.wav' (480000 samples"  -> c0.wav
"main: processing 'C:\Users\O'Brien\...\trec-lang-1\c11.wav' (480000"   -> c11.wav
"main: processing 'c0.wav' (480000 samples, 30.0 sec)"                -> no match
```

With no match, every clip is unanswered. Under the spec's rule that is `Err.WHISPER_NO_LANGUAGE`, so every meeting falls back to `pt` with `detection-failed`. The use case catches the error, so the only sign is a warning in the log.

Nothing in the spec rules this out. `detect_command(wavs)` and UT-014 do not say whether the paths include their directory. UT-015 says only "the output of three files `c0.wav`–`c2.wav`", so a test fixture that prints bare names would make the specified regex fail UT-015. A fixture that prints full paths would hide the problem.

Suggested fix: make the directory part optional, `r"processing '(?:.*[\\/])?(c\d+\.wav)' \("`, and add a bare-name line to UT-015a. Alternatively, state that `detect_command` passes the full temporary paths (as `transcriber_whispercpp.whisper_command` does with `str(wav)`) and that UT-015 prints full paths.

## Triage

- Decision: `VALID`
- Notes: Valid. The pattern required a directory separator before the clip name.
- Verified: Pattern in `_spec.md`; the reviewer's `re` check.

### Resolution

`WHISPER_PROCESSING = r"processing '(?:.*[\\/])?(c\d+\.wav)' \("` (directory optional), and `detect_command` is stated to pass full paths, like `whisper_command`. UT-015a adds a bare-name variant.
