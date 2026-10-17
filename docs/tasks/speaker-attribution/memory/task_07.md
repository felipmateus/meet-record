# Task 7 memory

- `build_user_message` adds `Prompt.ROSTER` then `Prompt.SPEAKER_LABELS` after the duration line, each only when the transcript has a roster / `user_label`; the verifier message adds only the roster line, after the meeting date.
- The verifier prompt's label sentence replaces "it has no speaker labels and may contain recognition errors." and also tells the verifier the roster names were present; the pin test in `tests/unit/test_verifier_claude.py` lists it as the third replacement (the text must match exactly).
- `participant_heard` treats a roster entry or a segment `speaker` like the owner's name: token subset in either direction.
- Schema descriptions (`FIELD_PARTICIPANTS`, `FIELD_ACTION_OWNER`, `FIELD_DEADLINE_WHO`) gained the roster and owner-label rules. `scripts/fidelity_eval.py` untouched.
- Evidence: `pytest` 629 passed, 8 skipped; `mypy` clean. Live gates G1/G3 (task 9) and the fidelity gate's re-measure of the verifier prompt remain.
