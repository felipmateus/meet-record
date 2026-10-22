---
provider: manual
pr:
round: 4
round_created_at: 2026-10-22T02:12:24Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 347
severity: low
author: claude-code
provider_ref:
---

# Issue 002: _spec.md test-ID ranges omit UT-025a and the choose_language cases

## Review Comment

Two test-ID ranges in `_spec.md` no longer match `_tests.md`:

- Config Lifecycle › Tests (`_spec.md:347`) says `tests/unit/test_config.py (UT-020–UT-024)`. `_tests.md` › Config defines UT-020 to UT-026 plus UT-025a (`_tests.md:97-104`), and the Coverage Matrix rows "US-008.EC-1–EC-5" and "Config" (`_tests.md:54, 60`) use them. The range leaves out UT-025 (single string and duplicates), UT-026 (the repository's own `config.toml` loads) and UT-025a. UT-025a is the test for the decision settled after round 3 that `languages` is validated in both modes (reviews-003 `_summary.md`, "Points not reached"). That decision is consistent in `_spec.md:56`, US-008.EC-5 (`_user_stories.md:163`) and `_dx.md` Config/Errors. Only this pointer misses it.
- The `domain/language.py` Impact row (`_spec.md:317`) says `UT-001–UT-012`. `choose_language` also owns UT-012a, UT-012b and UT-012c (`_tests.md:82-84`, Coverage Matrix `:58`).

Runtime check: a script over `_tests.md` found 70 defined IDs, all in the Coverage Matrix once the ranges are expanded, with no duplicates. No ID is referenced in `_spec.md`, `_user_stories.md`, `_dx.md` or `adrs/adr-001.md` that `_tests.md` does not define. The two ranges above are the only drift.

Failure mode: whoever builds task 1 from Config Lifecycle writes UT-020–UT-024 and leaves out the validation of `languages` when `language` is a code. Validating in both modes was the point of the settled decision, and a typo would again only surface after the switch to `"auto"`.

Suggested fix: `_spec.md:347` → `(UT-020–UT-026, UT-025a)`. `_spec.md:317` → `UT-001–UT-012c`.

## Triage

- Decision: `VALID`
- Notes: Valid. Both ranges predate UT-012a–c and UT-025/025a/026.
- Verified: `_tests.md` › Domain and › Config definitions.
- Verified (round 5, 2026-10-22): resolved. `_spec.md:317` reads `UT-001–UT-012c`, and `_spec.md:347` reads `(UT-020–UT-026, UT-025a)`. All of those IDs are in the suite (`tests/unit/test_language.py`, `tests/unit/test_config.py`), and they pass.

### Resolution

`_spec.md` Impact row `domain/language.py` → `UT-001–UT-012c`; Config Lifecycle › Tests → `(UT-020–UT-026, UT-025a)`.
