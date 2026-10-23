---
provider: manual
pr:
round: 4
round_created_at: 2026-10-23T16:35:33Z
status: resolved
file: docs/tasks/speech-check/_tests.md
line: 221
severity: low
author: claude-code
provider_ref:
---

# Issue 001: E2E-002 leaves out the conditions its "same argv" check needs

## Review Comment

The round 3 fixes made E2E-002 (`_tests.md:221`) a byte-for-byte case. Coverage Decisions (`_tests.md:254`) lists it with UT-043 and IT-004 as "byte-for-byte cases". Its normalization names `trec-lang-…`, so the comparison includes the language-detection calls, and those exist only in auto mode.

The fixed issue 001 scopes that promise in Business Rules (`_spec.md:76`): byte-for-byte holds "with a fixed `language`, or in auto mode when the filter drops no sample and `meta.json` has a duration". E2E-002 pins only one of these conditions. Its `--segments 0:6000` keeps both windows of `sample_offsets(70.0)`, `[10.0, 30.0]`. It does not say:
- which language mode the run uses;
- whether the meeting's `meta.json` has a duration. "The same setup" is E2E-001, which names only "a generated 70 s silent `audio.m4a`".

Here is how a correct implementation fails the case. The existing CLI E2E tests set `language = "auto"` in `config.toml` and create the meeting with `_recorded_at(repo, …, minutes=…)` (`tests/integration/test_cli.py:651-652`). If the new test follows that pattern without `minutes`, the meeting has no duration:
- with `speech_check = false`, `sample_offsets(None)` is `[0.0]`, so one language clip is cut and logged;
- with the check on, the stand-in gives `[10.0, 30.0]`, so two clips are cut and logged (`_spec.md:79`).

The logged argv then differ after the placeholder substitution, and the case fails while the feature is correct.

Suggested fix: state E2E-002's preconditions in the case. Either:
- auto mode (`language = "auto"`) with `meta.json` carrying the 70 s duration, which keeps the `trec-lang-` comparison meaningful; or
- a fixed `language = "pt"`, with `trec-lang-` dropped from the normalization.

In the auto-mode option, say that the scripted language detector answers the same in both runs.

## Triage

- Decision: `VALID`
- Notes: Valid. In auto mode with no duration, the check-off run plans `[0.0]` and the check-on run `[10.0, 30.0]`.
- Verified: `domain/language.py:52-63` `sample_offsets`; `tests/integration/test_cli.py` `_recorded_at`.

### Resolution

E2E-002 runs in auto mode with a 70 s `meta.json` duration (`_recorded_at(..., minutes=…)`), so both runs plan `[10.0, 30.0]` and the filter drops none. It says why a missing duration would make the argv differ by design.
