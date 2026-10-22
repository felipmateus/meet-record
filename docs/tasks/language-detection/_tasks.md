---
schema_version: "spec-tasks/v2"
workflow: language-detection
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
  edges:
    - from: task_01
      to: task_02
    - from: task_01
      to: task_03
    - from: task_02
      to: task_03
    - from: task_01
      to: task_04
    - from: task_01
      to: task_05
    - from: task_03
      to: task_05
    - from: task_03
      to: task_06
    - from: task_04
      to: task_06
    - from: task_05
      to: task_06
---

# Tasks: Detect the meeting's language before transcribing

> Spec: [_spec.md](_spec.md) · Stories: [_user_stories.md](_user_stories.md) · Surface: [_dx.md](_dx.md) · Tests: [_tests.md](_tests.md) · [ADR-001](adrs/adr-001.md)
> Rules that apply to every task: AGENTS.md (English only; strings in `messages.py` / `constants.py`; `pytest` and `mypy` green; never two pytest sessions at once; ask before committing, before `trec agent restart` and before anything that spends the Claude Code subscription; never write under `data/`).

Slice 1 is tasks 1–4. It solves the Motivating Problem: an English meeting is transcribed in English and analyzed in Portuguese, and a Portuguese meeting is transcribed as today. Slice 2 is tasks 5–6: the lines users see, the evaluation gates and the documentation.

| Task | Title | Type | Complexity | Depends on | Tests owned |
| --- | --- | --- | --- | --- | --- |
| task_01 | Language domain, settings, transcript record and the never-auto guard | feature | medium | — | UT-001–UT-012c, UT-020–UT-026 (with UT-025a), UT-041–UT-043, UT-045 |
| task_02 | The whisper.cpp language detector | feature | high | task_01 | UT-013–UT-017 (with UT-015a), IT-001, IT-003, IT-004 |
| task_03 | Detection in the transcription and its wiring | feature | medium | task_01, task_02 | UT-030–UT-040, UT-044, IT-002 |
| task_04 | Analysis across languages: header line, prompts, English greetings | feature | medium | task_01 | UT-050–UT-054 |
| task_05 | Language lines in transcribe, status, doctor and the minutes | feature | low | task_01, task_03 | UT-060–UT-068 (with UT-062a), UT-070–UT-073, E2E-001, E2E-002 |
| task_06 | Evaluation gates and documentation | qa | medium | task_03, task_04, task_05 | gates G1, G2, G3 (evidence) |

Graph notes:

- task_01 changes the `language` default to `"auto"`. So the same task makes `Container.transcribe_meeting()` pass `settings.fallback_language`, and makes `TranscribeMeeting` refuse `"auto"` (Safety Invariant 6). Until task_03 wires the detector, every meeting is still transcribed in `pt`, exactly as today. No intermediate state sends `-l auto` to whisper.
- task_04 needs only `Transcript.language`, which exists today, and the texts of task_01. It can run before task_02 and task_03.
- task_06 runs the gates on read-only copies of real meetings. G3 spends the subscription and needs the user's approval. The daemon loads the new code only after `trec agent restart`, which also needs the user's approval.
