# task_01 memory

Status: implemented and verified on fakes; changes left uncommitted.

Evidence: `pytest -q` (one session, whole fast suite) green, `mypy` clean (59 files), `tests/unit/test_no_hardcoded_strings.py` green (inside the full run).
New tests: `tests/unit/test_status_updates.py` (UT-050 to UT-052, UT-054, UT-055, UT-057 to UT-059), `tests/unit/test_excerpts.py` (UT-028, UT-053). Edited: `test_llm_claude.py` (`for_whom` is now a required field of the strict action schema), `test_verifier_claude.py` (prompt-identity test allows the one status_update paragraph).

Left to others: docs of the feature (task_11), `CurateMeetings` building excerpts with `excerpt_window` (task_05), Q-001 and agent restart (task_08).
