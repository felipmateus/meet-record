# Run log: cy-execute-task (speech-check, task 4)

Skill run: cy-execute-task, with cy-workflow-memory and cy-final-verify loaded by the same dispatch. Task: `docs/tasks/speech-check/task_04.md` ("Language samples only where there is speech, and the duration stand-in"). Branch `feat/speech-check`. Nothing committed or pushed, nothing written under `data/`, no `trec agent` command run, no Claude call. No workflow memory folder exists for this feature (`docs/tasks/speech-check/memory/` is absent and none was supplied), so none was read or written.

## Questions asked and answers given

None. No question was asked of the user during this run, so there are no answers to record. The task was dispatched with the instruction to begin immediately, and the spec was already approved by the user on 2026-10-23.

## Outcome

- `domain/language.py`: `choose_language(..., planned: int | None = None)`. A lone counted sample decides only when one sample was planned (`planned == 1`; None means `len(samples)`, today's behavior).
- `application/use_cases/processing.py`: `execute` takes `duration = recorded or (activity.audio_seconds if activity is not None else None)` after the no-speech return and passes the activity to `_language`; `_language` keeps `samples_with_speech(...)` of the planned offsets when there is an activity, logs `Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH` when any were dropped, does not call the detector when none is left, and passes `planned=len(planned)`.
- `messages.py`: `Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH`.
- Tests: UT-008 (`tests/unit/test_language.py`, named `test_speech_ut008_*` because the language-detection spec already owns `test_ut008_*` there); UT-044, UT-045, UT-046, UT-055, UT-056 (`tests/unit/test_transcribe_speech.py`). The task 3 test `test_ut043_a_recording_with_speech_gets_the_check_off_commands_and_the_record` now gives its meeting a recorded length, because the stand-in moves `health.total_minutes` for a meeting without one (spec, Business Rules, "A recording with speech").
- Verification: `pytest` 1489 passed, 12 skipped; `mypy` no issues in 68 source files. Four mutations (drop `planned=`, drop the filter, drop the stand-in, call the detector with no offsets) each made a new test fail.
- Task file: `status: completed`, subtasks 4.1, 4.2 and the two test lines ticked. `_tasks.md` untouched.
