# task_04 memory

Status: implemented and verified on the fake transports; changes left uncommitted.

Evidence: `pytest -q` (one session, whole fast suite) green, `mypy` clean (63 files), `tests/unit/test_no_hardcoded_strings.py` green (inside the full run, no module allowance). No real model call.
New tests: `tests/unit/test_curator_claude.py` (message order and refs, strict schema, field-by-field mapping, repair, both transports, usage tags, errors, imports), `tests/unit/test_curator_prompt.py` (sections, corrected anchor rule, worked example machine-checked). Fixture module `tests/fixtures/curator_example.py` (the example document, meeting and answer). Edited `tests/fixtures/fake_claude_cli.py` (new env switches, default behaviour unchanged).

Decisions for later tasks:
- User message: the user-name line (`Prompt.USER_NAME`) and `Now: seg 19/10/2026 10:12` come first, then `<document>` (as on disk) ... `<task>`; the first TAG is `<document>`. Meeting block attributes `n id title when health` (`when` parsed from the id, absent when the id is not a timestamp; `health` = `degraded` and/or `wrong_sample_rate`, only when set). Lines: `n.a1 text | due | priority | for | at | ⚠️ unconfirmed: reason`, `n.o1 ... | owner: X`, `n.u1 <change>: <about> | who | new date | new owner | quote | at`, `n.p1`, `n.n1`, `n.d1`, `n.q1`, `n.r1`. Empty parts print `(none)`. Excerpts are `<excerpt n="1">` blocks inside `<excerpts>`; `CurateMeetings` must pass `MeetingContext.excerpts` already windowed.
- `repair` has its own schema `RepairOut` (only `ops`) and message (`<document>` = `current`, `<calendar>`, `<failed_edits>` with `[index] error (detail)` + the op as JSON, `<task>`); it does not resend the meetings. `ops` is a required field of both `CuratorOut` and `RepairOut` (an answer without it is a schema violation); `text`/`reason`/`anchor` default to None, lists default empty.
- `to_output` normalises only `summary`/`focus`/`note`/`why` (one line, blank focus lines dropped); targets, texts and `user_removed.text` are never touched. Usage tags `curate:<first id>` / `curate-repair:<first id>`, `extra={"meeting": first id}`; `data.meetings` must not be empty.
- The prompt's worked example is generated from `tests/fixtures/curator_example.py` (`example_input()` through `build_user_message`, `ANSWER`); the test asserts the prompt shows exactly that input (up to `<task>`) and that answer, and that the answer applies with no failure. Changing the message builder or the example needs the prompt block regenerated (same text, paste the builder output).
- Known cosmetic effect for task_05/Q-002: a new item inserted after a section heading lands above the heading's blank line, so the list is split by one blank line until the next pass. The skeleton text is task_05's.
- Spec said the example has 7 ops; it has 8 (the extra one is the `archive` of an old ticked item, so the example shows all four kinds).

Left to others: container wiring and config (`[activities] model/cli_model/effort`) task_06; IT-008 through `fake_claude_cli.py` (use `FAKE_CLAUDE_SCRIPT` for curate-then-repair, `FAKE_CLAUDE_RECORD` to assert messages) task_06; Q-001/Q-002 real runs task_08.
