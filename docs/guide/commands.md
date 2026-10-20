# Command reference

`trec --help` and `trec <command> --help` list everything. All commands work from any terminal with the venv active (`source .venv/bin/activate`).

| Command | What it does |
|---|---|
| `trec status` | Data folder, API key status, meetings with state and next step (and the share of labelled lines, `· speakers 78%`), degraded transcripts, unconfirmed claims, recording in progress, the activities summary (`Activities: 7 yours · 3 waiting on others (last pass …)`), stories waiting to be published |
| `trec doctor` | Checks dependencies, models, the transcript-loop guard, the claim verifier, the speaker labels (helper build and Accessibility permission), the activities document (information only), permissions, disk and story destinations |
| `trec start [--pid N] [--title T]` | Starts a manual recording (Teams must be running, or pass `--pid`); prints a `Speakers:` line when the observer started |
| `trec stop` | Stops the recording, mixes the tracks and writes `audio.m4a`. Works from any terminal |
| `trec cancel` | Discards the recording in progress and deletes its files |
| `trec transcribe [id]` | Transcribes one meeting, or all meetings in state `recorded`, and prints how many lines got a speaker label, or why none did |
| `trec analyze [id]` | Analyzes one meeting, or all meetings in state `transcribed`, writes `minutes.md`, then updates the activities document for the meetings it analyzed (skipped with `[activities] enabled = false`) |
| `trec minutes [id] [--all]` | Re-renders `minutes.md` from existing analyses, with no model call |
| `trec activities [--open]` | Where the activities document stands: path, last update, the focus, counts, the last pass and the meetings not curated yet with their retry command; `--open` also opens the file |
| `trec activities curate <id>… \| --since YYYY-MM-DD [--yes]` | Reruns the curator for analyzed meetings, or builds the document from the meetings since a date (asks first: meetings, passes, estimated time) |
| `trec activities undo [--yes]` | Shows the last pass and what undoing it changes, then restores the document to before it |
| `trec stories` | Drafts a user story for each item of the activities document tagged `#história` and replaces the tag with a link to the draft; with `[stories] publish = true` it also publishes today's drafts |
| `trec publish [--date YYYY-MM-DD] [--only 1,3]` | Sends a day's drafts (default today) to the configured boards, skipping what is already there |
| `trec purge` | Deletes `audio.m4a` from transcribed meetings older than `audio.retention_days` (the daemon also does it once a day) |
| `trec daemon [--once]` | Runs the detector loop (used by the LaunchAgent); `--once` is a single diagnostic reading |
| `trec agent install [--env K=V]` | Installs the daemon as a service (starts at login, restarts on a crash) and removes the daily planner job an older version installed; `--env` is macOS only |
| `trec agent status \| restart \| uninstall` | Inspects, restarts or removes the service (`restart` and `uninstall` also remove the old planner job when it is still there) |
| `trec version` | Prints the version |

Processing commands without an id act on every pending meeting and keep going when one fails. They exit with code 1 if any failed. Errors are written to `error.txt` in the meeting folder, and re-running clears them.
