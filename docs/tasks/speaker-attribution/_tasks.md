---
schema_version: "spec-tasks/v2"
workflow: speaker-attribution
graph:
  nodes:
    - id: task_01
      file: task_01.md
    - id: task_02
      file: task_02.md
    - id: task_03
      file: task_03.md
    - id: task_04
      file: task_04.md
    - id: task_05
      file: task_05.md
    - id: task_06
      file: task_06.md
    - id: task_07
      file: task_07.md
    - id: task_08
      file: task_08.md
    - id: task_09
      file: task_09.md
  edges:
    - from: task_02
      to: task_03
    - from: task_01
      to: task_04
    - from: task_03
      to: task_04
    - from: task_01
      to: task_05
    - from: task_04
      to: task_05
    - from: task_01
      to: task_06
    - from: task_01
      to: task_07
    - from: task_04
      to: task_08
    - from: task_05
      to: task_08
    - from: task_06
      to: task_08
    - from: task_02
      to: task_09
    - from: task_07
      to: task_09
    - from: task_08
      to: task_09
---

# Tasks: Speaker attribution from the Teams window

> Spec: [_spec.md](_spec.md) · Stories: [_user_stories.md](_user_stories.md) · Surface: [_dx.md](_dx.md) · Tests: [_tests.md](_tests.md) · Requirements: [docs/tasks/speaker-attribution/prd.md](prd.md)
> Rules that apply to every task: AGENTS.md (English only; strings in `messages.py` / `constants.py`, file names in `domain/status.py`; `pytest` and `mypy` green; never two pytest sessions at once; ask before committing, before `trec agent restart`, before touching the installed daemon or macOS permissions).

Slice 1 (the Motivating Problem: a recorded meeting whose transcript names who said each line and whose analysis takes owners from those lines) is tasks 1–7. Slice 2 (coverage lines, notification, installer and documentation, the manual gates) is tasks 8–9.

| Task | Title | Type | Complexity | Depends on | Tests owned |
| --- | --- | --- | --- | --- | --- |
| task_01 | Domain and persistence of speaker labels | feature | medium | — | UT-001–UT-027 (30 cases) |
| task_02 | The `teams-speakers` helper | feature | high | — | UT-076, IT-006 |
| task_03 | Permission identity spike | infra | medium | task_02 | IT-007 (manual) |
| task_04 | Ports, adapters, configuration and wiring | feature | medium | task_01, task_03 | UT-060, UT-070–UT-075, IT-002–IT-004 |
| task_05 | Observer and energy in the recording use cases | feature | high | task_01, task_04 | UT-030–UT-039 |
| task_06 | Labelling at transcription and the daily notice | feature | medium | task_01 | UT-040–UT-047, IT-001 |
| task_07 | Labels, roster and owner rules in the model input | feature | medium | task_01 | UT-050–UT-056 |
| task_08 | CLI lines: doctor, status, transcribe, start | feature | low | task_04, task_05, task_06 | UT-061–UT-065, IT-005 |
| task_09 | Installer, documentation and the manual gates | docs | low | task_02, task_07, task_08 | E2E-001 (manual gates G1–G5) |

Graph notes: task_03 needs the helper's `--check` from task_02 and the user's approval to spawn it from the installed daemon; task_04's observer adapter depends on task_03's identity decision (plain spawn, disclaimed responsibility or a launchd job). task_06 and task_07 only need the domain and codec of task_01 and can run in parallel with task_02–task_05.
