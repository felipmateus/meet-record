# task_02 memory

Status: implemented and verified; changes left uncommitted.

Evidence: `pytest -q` (one session, whole fast suite) green, `mypy` clean (61 files), `tests/unit/test_no_hardcoded_strings.py` green (inside the full run, no module allowance).
New tests: `tests/unit/test_activities_apply.py` (UT-001 to UT-009, UT-019 to UT-024, UT-029, UT-112 to UT-115), `tests/unit/test_activities_render.py` (UT-010 to UT-015, UT-018, UT-026, UT-027, UT-116, UT-117). Fixture: `tests/fixtures/activities/atividades.md` (the `_dx.md` document).

Left to others: skeleton text (task_05, via `render_box`), `tagged_blocks`/`replace_tag`/`TaggedBlock` (task_13), archive entry rendering with `../../` links (task_03), `OpFailure` serialization (task_04).
