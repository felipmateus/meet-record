---
schema_version: "spec-tasks/v2"
workflow: speech-check
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
  edges:
    - from: task_01
      to: task_02
    - from: task_01
      to: task_03
    - from: task_02
      to: task_03
    - from: task_03
      to: task_04
    - from: task_03
      to: task_06
    - from: task_04
      to: task_06
    - from: task_04
      to: task_07
    - from: task_05
      to: task_07
    - from: task_06
      to: task_07
---

# Tasks: Check for speech before transcribing, and stop counting short replies as loops

> Spec: [_spec.md](_spec.md) (approved 2026-10-23) · Stories: [_user_stories.md](_user_stories.md) · Surface: [_dx.md](_dx.md) · Tests: [_tests.md](_tests.md) · [ADR-001](adrs/adr-001.md)
> Rules for every task: AGENTS.md. English only. Strings go in `messages.py` / `constants.py`. Keep `pytest` and `mypy` green. Never run two pytest sessions at once. Ask before committing, before `trec agent restart` and before anything that spends the Claude Code subscription. Never write under `data/`.

Slice 1 is tasks 1–3, the MVP. A recording with no speech gets no whisper run and no invented text. It is saved as an empty transcript marked "no speech", the `trec transcribe` lines say so, and a recording of a minute or more notifies.

Slice 2 is tasks 4–7: the speech-aware language samples, the loop rule, the status and doctor lines, the gates and the documentation.

| Task | Title | Type | Complexity | Depends on | Tests owned |
| --- | --- | --- | --- | --- | --- |
| task_01 | Speech domain, transcript record and the speech_check key | feature | low | — | UT-001–UT-007, UT-020–UT-023, UT-025 |
| task_02 | The whisper.cpp speech detector and the shared WAV conversion | feature | medium | task_01 | UT-030–UT-036, IT-001, IT-002, IT-005 |
| task_03 | Speech check in the transcription, its wiring and the transcribe lines | feature | medium | task_01, task_02 | UT-040–UT-043, UT-047–UT-053, UT-060–UT-062, IT-003, IT-004 |
| task_04 | Language samples only where there is speech, and the duration stand-in | feature | medium | task_03 | UT-008, UT-044–UT-046, UT-055, UT-056 |
| task_05 | Short replies are not loops | feature | low | — | UT-010–UT-018 |
| task_06 | Speech in trec status and trec doctor, the installers' model, and the CLI journeys | feature | low | task_03, task_04 | UT-026, UT-063, UT-064, E2E-001, E2E-002 |
| task_07 | Evaluation gates and documentation | qa | medium | task_04, task_05, task_06 | gates G1, G2, G3 (evidence) |

Graph notes:

- **task_05 is independent.** It touches only `domain/health.py` and `tests/unit/test_transcript_health.py`, so it can run at any point before task_07. It shares no file with tasks 1–4 or 6.
- **E2E-001 and E2E-002 belong to task_06, not task_03.** Both journeys assert the `trec status` marker and count line, which task_06 adds. Task_03 proves the MVP through IT-003, IT-004 and the `trec transcribe` unit cases UT-060–UT-062.
- **G2 decides whether task_04's filter ships.** If a recording's language changes under it, the result goes back to the user before task_07 closes. The speech check (tasks 1–3) does not depend on G2.
- **Retention deadline.** The gates read stored audio, and the four named recordings lose theirs from about 2026-11-07. If task_07 cannot run before then, the user approves a read-only copy of those four first.
- **The daemon restart.** The daemon loads the new code only after `trec agent restart`, which needs the user's approval.
