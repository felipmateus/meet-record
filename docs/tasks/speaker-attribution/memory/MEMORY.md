# Workflow memory: speaker-attribution

## Durable facts for later tasks
- Task 1 (domain, codec, repository methods) and task 6 (labelling at transcription, daily notice) are done and uncommitted.
- `TranscribeMeeting` now returns the labelled copy of the transcript (`label_segments` copies), so tests tell passes apart by `segments`, not by object identity with the fake transcriber's transcript.
- `Transcript.labels.reason` (a `SpeakerReason` value) is what `trec transcribe` (task 8) prints; the reason table texts for the CLI are not in `messages.py` yet. The notification bodies are `Notify.NO_SPEAKER_LABELS_REASON` (keyed by reason value).
- Every transcript saved after task 6 carries a `speakers` summary, also when nothing was labelled (reason `no-observer` for a meeting without `speakers.jsonl`).
- Task 7 (labels, roster, owner rules in the model input) is done and uncommitted: both prompts, `build_user_message`, `transcript_for`, `participant_heard` use labels and roster. The verifier prompt now differs from `VERIFY_SYSTEM` by a third replacement (pinned); the fidelity gate must re-measure it.
- Task 2 (the `teams-speakers` helper) is built and tested but `in_progress`: the live-call run (2.5) is pending for the user; task 3 and task 9 depend on it. Helper event shapes and exit codes are in `memory/task_02.md`.
- task_02 completed after the 2026-10-17 live run (tile markers matched on the first " | " part; a guest account is needed for a remote tile). Open: is the AXEnhancedUserInterface request needed? Re-test after a Teams restart without the probe.

- Task 4 (ports, adapters, config, wiring) is done and uncommitted: see `memory/task_04.md` for the observer/energy contracts used by tasks 5 and 8. The observer's `start` takes about 1.5 s (startup grace) and maps the helper's exit 3 to `permission-missing`.
- Task 5 (observer and energy in the recording use cases, daemon watch and recovery, container wiring) is done and uncommitted: see `memory/task_05.md`. The daemon must be restarted (with the user's approval) for it to take effect; `trec stop`'s observer line is task 8.
- Task 8 (CLI lines: doctor, status, transcribe, start) is done and uncommitted: see `memory/task_08.md`. Status hides the speakers segment for `no-observer`; the doctor `[WARNING]` wording changed (terminal no longer involved). Task 9 owns the build, docs and E2E-001.
- Task 9 documentation (9.1, 9.2) is done and uncommitted: installer, README, PRD pages, requirements §10, AGENTS.md. Status `in_progress`: 9.3 / E2E-001 (agent restart with the user's approval, gates G1-G5) wait for real meetings; see `memory/task_09.md`.
