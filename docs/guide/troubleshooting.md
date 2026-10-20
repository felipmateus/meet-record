# Troubleshooting

**The Teams track is silent; only my voice is recorded.**
`teams-tap` lacks **Screen & System Audio Recording** permission. Grant it under System Settings > Privacy & Security, then record again. Running `teams-tap --list` during a call shows whether the Teams processes are audio clients.

**`trec transcribe` prints `Speakers: no labels (...)`, or `trec status` shows `· speakers 0% (...)`.**
The reason in the parentheses says what to do. Only your own lines are labelled while there are no labels from the window.
- *the observer did not run: Accessibility permission missing*: add `native/teams-speakers/.build/release/teams-speakers` under System Settings > Privacy & Security > Accessibility with the **+** button and switch it on (granting your terminal or Python does not help), then `trec doctor`. If you added it already, a rebuild may have invalidated the grant: remove the entry and add it again.
- *the observer did not run: teams-speakers not built*: run `scripts/build-native.sh`.
- *the observer did not run: it failed to start; see data/log/speakers.log*: read the end of that log; the helper's exit code and message are there.
- *the observer died before reading a Teams window*: the helper stopped early in the call; see `data/log/speakers.log` and the daemon log.
- *no Teams meeting window was read during the call*: no Teams window was rendered, so nothing could be read. Keep a Teams window visible (the compact view is enough). If one was visible all along, Teams may have changed its window; `data/log/speakers.log` shows what the helper found.
- *speaker events found but no line matched them*: the helper read the window but no speaking turn overlapped a line. Log only, no notification; check `speakers.jsonl` for `speaking` events.
- *no observer data for this meeting*: no `speakers.jsonl` exists: the meeting was recorded before the feature, `[speakers] enabled = false`, on Windows, or the daemon was not restarted since the feature was installed (`trec agent restart`).

**Only part of a meeting is labelled (for example `speakers 40%`).**
The Teams window was covered for part of the call, so nobody was detected speaking while it was. Keep a Teams window visible during meetings; the compact view counts. The share is lines labelled out of lines with speech.

**`trec doctor` says the permission is granted, but recordings still report it missing.**
The `[WARNING] speaker labels` line. The grant may not hold for the daemon's job (a rebuilt binary is a new identity to macOS). Record another meeting to confirm; if it still reports it missing, remove the `teams-speakers` entry from the Accessibility list, add it again with the **+** button and run `trec agent restart`.

**The Accessibility list shows no `teams-speakers` entry.**
macOS creates none for a background job's request. Add it by hand with the **+** button (Cmd+Shift+G to type the path).

**My second device (or my phone on the same account) has no label.**
The same account on two devices is one Teams participant, so the second device has no tile of its own and nothing labels it. Test with another account (see [Speaker labels](speaker-labels.md)).

**The daemon does not start recording.**
Run `trec daemon --once` during a call. If Teams is not seen, check `audio.teams_process_name` (new Teams is `MSTeams`) and look at `pmset -g assertions` for the Teams process. Make sure the service runs with `trec agent status`, and read `data/log/teams-recorder.log`.

**`[Errno 11] Resource deadlock avoided` in the logs.**
The project or its data is in `~/Documents`, `~/Desktop`, `~/Downloads` or iCloud, where macOS blocks background processes. Move the project (for example to `~/Projetos/teams-recorder`) and run `scripts/install.sh` again.

**A meeting is stuck in `failed`.**
Read `data/recordings/<id>/error.txt`, fix the cause and re-run the step (`trec transcribe <id>` or `trec analyze <id>`). Re-running clears the error.

**Transcription fails with "model not found" or "whisper-cli not found".**
Run `scripts/download-model.sh` or `brew install whisper-cpp`. `trec doctor` lists what is missing.

**A meeting's minutes say "Transcrição degradada", or `trec status` marks a degraded transcript.**
whisper repeated one line for part of the meeting, and the retry with VAD did not repair it. The ranges listed have no text, so the minutes miss what was said there. Check that `trec doctor` shows the retry as on (it needs the VAD model: `scripts/download-model.sh silero-v5.1.2`). While `audio.m4a` still exists, `trec transcribe <id>` and then `trec analyze <id>` redo the transcript, the analysis and the minutes (they replace the previous files).

**Analysis fails with an authentication error.**
With `api`, check that `.env` has `ANTHROPIC_API_KEY` and permission 600. With `claude-code`, run `claude` once in a terminal and log in. The daemon needs a logged-in session too.

**The keep-or-discard dialog never shows up.**
If Teams is in full screen, the dialog may be on another desktop. When the dialog cannot be shown, the recording is kept. To turn the question off, set `[confirmation] enabled = false`.

**`trec publish` refuses to publish.**
`trec doctor` lists the board's problems: missing `backlog` binary, an uninitialized project, no `Triagem` status, a board Git does not ignore, or a configuration that auto-commits or reaches remotes.

**`trec activities` lists a meeting under `Not curated`, or I got an `Activity curation failed` notification.**
The line gives the reason (the meeting's `curation_error.txt`) and the command to rerun it: `trec activities curate <id>`. The daemon retries a meeting analyzed in the last two working days by itself, at most twice for one curated alone. The document is untouched by a failed pass.

**The last update to the activities document is wrong.**
`trec activities undo` previews the change, asks, and restores the document to before that pass (the lines you edited after it are discarded, and the preview says how many). Then `trec activities curate <id>` curates that meeting again.

**The activities document is not updated after a meeting.**
The daemon needs `trec agent restart` once after the feature is installed. Check `[activities] enabled`, `trec doctor` (the `Activities document` line) and `data/log/teams-recorder.log`.

**I changed `config.toml` or the code and nothing changed.**
Run `trec agent restart`.

**The first `pytest` after big edits hangs for minutes.**
Endpoint security scanning on the first open of new files (`.pyc` included) can stall a cold run. It then completes in about 10 s.
