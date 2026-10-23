---
provider: manual
pr:
round: 2
round_created_at: 2026-10-23T15:10:53Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 343
severity: low
author: claude-code
provider_ref:
---

# Issue 003: Codec says "isinstance as for language_detection", but that decoder coerces

## Review Comment

Data Models (`_spec.md:343`) says the `speech` decoder "checks each field with `isinstance` (… as for `language_detection`)", and File References (`_spec.md:526`) says "mirror `language_detection`". `_language_detection_from_dict` (`codec.py:140-152`) checks only that the record is a dict and that `samples` is a list of dicts. It reads every field by coercion: `str(d["language"])`, `int(d.get("counted", 0))`, `float(s["at"])`. Mirroring it fails UT-023 (`_tests.md:113`):
- `bool("false")` is `True`, so a `found` that is not a bool loads without error, with the wrong value;
- `int(2.7)` is `2`, so a float `segments` loads;
- `float("1.5")` succeeds, so a numeric string `speech_seconds` loads.

A plain `isinstance(x, int)` check also accepts `True` for `segments`, because `bool` is a subclass of `int`.

Suggested fix: drop "as for `language_detection`". Spell out the checks: `found` is `bool`; `segments` is `int` and not `bool`; `speech_seconds` and `audio_seconds` are `int`/`float` and not `bool`, as `_finite` does (`codec.py:195-200`). Each failure is a `TypeError`, which `_load` turns into the `RepositoryError` naming the file (`repository_fs.py:72-73`). Add `segments: true` to UT-023's damaged values.


## Triage

- Decision: `VALID`
- Notes: Valid. `_language_detection_from_dict` coerces (`codec.py:140-152`).
- Verified: `codec.py:140-152,195-200`, `repository_fs.py:72-73`.

### Resolution

Data Models spells out the checks: a `dict`; `found` a `bool`; `segments` an `int` and not a `bool`; the seconds `int`/`float`, not `bool`, and finite (`_finite`). Each failure raises `TypeError` and becomes `RepositoryError`. The "as for `language_detection`" wording is gone, and File References point at `_finite`. UT-023 adds `"false"`, `"1.5"`, `2.7`, `true` and `NaN`.
