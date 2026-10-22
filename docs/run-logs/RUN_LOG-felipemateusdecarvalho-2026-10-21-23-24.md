# Run log: spec approval and task breakdown for language-detection

Request (in Portuguese): "aprovado a spec" ("the spec is approved").

## Skills run

- `cy-create-tasks`: generated `_tasks.md` and `task_01.md`–`task_06.md` in `docs/tasks/language-detection/`.

## Questions asked and answers given

No question was asked of the user, so no answer was given. The user's approval was the request itself.

## Outcome

- `_spec.md` status line: approved by the user on 2026-10-21, after review rounds 1–4. The four round-4 fixes are `valid` and not yet verified by a reviewer.
- Six tasks follow the spec's Build Order:
  1. domain, settings, transcript record and the never-auto guard;
  2. the whisper.cpp detector;
  3. detection in the transcription and its wiring;
  4. the analysis across languages;
  5. the CLI and minutes lines;
  6. the gates and the documentation.
- Slice 1 is tasks 1–4.
- One change from the spec's Build Order: task 1 also makes the container pass `fallback_language`, and makes `TranscribeMeeting` refuse `"auto"` (UT-045 moves there). Without it, the new `"auto"` default would send `-l auto` to whisper before task 3.
- Validation (a temporary PyYAML environment, not added to the project):
  - the frontmatter parses, every status is `pending`, and every title equals its H1;
  - the graph nodes match the task files one to one, and the graph is acyclic;
  - 73 test and gate IDs are defined in `_tests.md`, and each is owned by exactly one task.
- Nothing committed. No source file changed. Nothing written under `data/`.

## Open items left to the user

- Start the implementation (`claude --agent orchestrator`, or `cy-orchestrate-tasks language-detection`) when they decide to.
- Optionally, a reviewer round to verify the four `valid` spec fixes from round 4.
