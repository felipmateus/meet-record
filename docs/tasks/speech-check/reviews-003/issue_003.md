---
provider: manual
pr:
round: 3
round_created_at: 2026-10-23T16:25:44Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 526
severity: low
author: claude-code
provider_ref:
---

# Issue 003: File References cite ranges and a name the code does not have

## Review Comment

Several File References point outside the symbols they name. One names a function that does not exist. Checked at `0d58857` with `grep -n`:
- `_spec.md:351`: "`_load` reports … (`repository_fs.py:72-73`)". `repository_fs.py` has no `_load`. The function that turns `TypeError` into `RepositoryError` is `_decode` (`:68-73`), reached through `_decoded` (`:60`) from `load_transcript` (`:241-242`). The other matches are `_load_json` (`:44`) and `_load_drafts` (`:295`), and neither is the one meant.
- `_spec.md:526`: `processing.py:32-140` is said to hold `_transcribe`, but `_transcribe` is at `:179`.
- `_spec.md:527`: `language.py:77-92` is said to hold `LanguageRules` and `sample_offsets`, but they are at `:13` and `:52`. Only `choose_language` (`:77`) and line 87 match.
- `_spec.md:538`: `container.py:220-290` is said to hold `transcribe_meeting()`, the method this feature wires, but it is at `:132`. The builders are at `:254` and `:265`, and the first-pass transcriber is built inside `build_container` (`:227`).
- `_spec.md:539`: `config.py:280-300` covers `vad` (`:287`) but not `retry_vad` (`:310`). `speech_check` is meant to be parsed "like `vad` and `retry_vad`" (`_spec.md:372`).

The other ranges match: `health.py:22-50`, `test_transcript_health.py:30-38,64-66`, `processing.py:93-99`, `repository_fs.py:189-192`, `cli.py:527-570`, `models.py:97-163`, `codec.py:140-200` (`_finite` at `:195`), `llm_schema.py:23`, `config.py:50-61` and `config_tool.py:25`.

This would bite one way: an implementer looking for `_load`, or for `transcribe_meeting()` in the container range, does not find it.

Suggested fix: name `_decode` (`repository_fs.py:68-73`), and correct the ranges to `processing.py:32-205`, `language.py:13-92`, `container.py:132-136,214-285` and `config.py:280-315`. Alternatively, cite symbols without line numbers.

## Triage

- Decision: `VALID`
- Notes: Valid. `_load` does not exist, and several ranges missed their symbols.
- Verified: `repository_fs.py:66-73`, `processing.py:77,102,179`, `language.py:13,52,77`, `container.py:132,214,254,265`, `config.py:287,310` (grep in the main session).

- Verified (round 4, 2026-10-23): `grep -n` at `0d58857`. `_decode` is at `repository_fs.py:68` (`:66-73` holds it, starting on the two blank lines after `_decoded`), `_decoded` at `:60`, `load_transcript` at `:241-242`. `processing.py` `TranscribeMeeting :32`, `execute :77`, `_language :102`, `_transcribe :179`, notifications `:94-99`. `language.py` `LanguageRules :13`, `sample_offsets :52`, `choose_language :77`, `needed` line `:87`. `container.py` `transcribe_meeting :132`, `build_container :214` (first-pass transcriber `:226`), `build_language_detector :254`, `build_retry_transcriber :265`, last line `:284`. `config.py` `find_tool :50`, `Settings` VAD paths `:140-146`, `vad :287`, `retry_vad :310`. `cli.py` `status :81`, `_language_segment :197`, `_language_line :205`, `doctor :241`, `_check_transcript_health :314`, `transcribe :472`, `analyze :528`. `llm_schema.trivial_analysis :23`, `config_tool.py:25` `vad_path`. `_load` no longer appears in any of the five files. Untouched off-by-ones, not defects: `transcriber_whispercpp.py:43-60` (`convert_command` is defined at `:42`), and `_finite` runs `:195-203`, not `:195-200`.

### Resolution

Data Models names `_decode` (through `_decoded` from `load_transcript`). File References: `processing.py:32-205`, `language.py:13-92`, `container.py:132-136,214-285` and `config.py:…,280-315`, with the symbol lines.
