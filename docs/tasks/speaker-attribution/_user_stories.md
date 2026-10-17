# User Stories: Speaker attribution from the Teams window

Canonical behavior catalog for speaker attribution. Companion to `_spec.md`; consumed by `_spec.md` Part II (component mapping) and `_tests.md` (coverage matrix). There is no `_uiux.md`: the product has no graphical interface.

## Personas

- **The user** — owner of the Mac and the Teams account; attends several meetings a day and reads the minutes, the daily plan and the story drafts the pipeline writes. Wants the right owners without taking notes.
- **The operator** — the same person maintaining the installation: builds the native helpers, grants macOS permissions, reads `trec doctor` and the logs when something looks wrong.

## Story Index

| ID | Feature Area | Persona | Story |
| --- | --- | --- | --- |
| US-001 | Labelled lines | user | Lines said by other participants carry their display name |
| US-002 | Labelled lines | user | Lines said by the user carry the user's name |
| US-003 | Labelled lines | user | Lines nobody could be attributed to stay as today |
| US-004 | Analysis on labels | user | Owners in the minutes come from the labelled lines |
| US-005 | Analysis on labels | user | The minutes' participants are the people seen in the meeting window |
| US-006 | Analysis on labels | user | An automatic recording is titled with the meeting's subject |
| US-007 | Operation | user | A recording never waits for or fails because of the labels |
| US-008 | Operation | user | A day's first unlabelled meeting raises one notification with the reason |
| US-009 | Operation | operator | `trec doctor`, `trec status` and `trec transcribe` show the helper's state and the coverage |
| US-010 | Installation | operator | Build the helper and grant its permission with the existing tools |
| US-011 | Compatibility | user | Meetings recorded before this feature behave exactly as before |

## Labelled lines

### US-001: Lines said by other participants carry their display name

**As a** user, **I want** each transcript line said by another participant to start with that person's display name as Teams shows it, **so that** I and the analysis know who said what without guessing.

Acceptance criteria:

- AC-1: Given a recorded meeting during which a Teams meeting window (main or compact view) was visible on screen, when the meeting is transcribed, then every line whose speaking interval in the window covered at least 30% of the line reads `[HH:MM:SS] <display name>: <text>` in `transcript.txt`.
- AC-2: Given two participants whose speaking intervals both overlap a line, when it is labelled, then the line carries the name with the larger overlap.
- AC-3: Given the main window and the compact view both open, when either shows a participant speaking, then that participant counts as speaking.
- AC-4: Given the labelled transcript, when the analysis and the verification run, then the messages they receive show the same names on the same lines.

Edge cases:

- EC-1: The Teams meeting window is fully covered by other windows for a stretch of the meeting → lines in that stretch get no name from the window (the user's lines may still be labelled from the microphone); the share reported by `trec transcribe` reflects it.
- EC-2: A participant's tile disappears (they leave) while marked speaking → their speaking state ends at that moment; no later line is attributed to them from the window.
- EC-3: Two participants share the same display name → both tiles contribute to one name; lines are labelled with that name (no disambiguation in this delivery).
- EC-4: The meeting is a one-to-one call → the other person's lines are labelled like any participant; the window title gives their name as the subject (US-006).
- EC-5: The observer reports a speaking state change less than 0.5 s long → it still opens and closes a turn; a line it covers under 30% is not attributed to it.

### US-002: Lines said by the user carry the user's name

**As a** user, **I want** my own lines labelled with my name, **so that** my commitments are attributed to me without relying on first-person phrasing.

Acceptance criteria:

- AC-1: Given a line during which no remote participant qualifies and the microphone track is at least 6 dB louder than the Teams track and above −50 dBFS, when the meeting is transcribed, then the line reads `[HH:MM:SS] <user label>: <text>`.
- AC-2: Given `[user] name` is set in the configuration, when lines are labelled as the user's, then the label is that name.
- AC-3: Given no configured name but the user's own tile was seen, when lines are labelled as the user's, then the label is the own tile's display name.
- AC-4: Given neither, when lines are labelled as the user's, then the label is "Você".

Edge cases:

- EC-1: Another participant speaks loudly through the Mac's speakers while the user is silent → the Teams track is louder than the microphone, so the line is not attributed to the user.
- EC-2: The user is muted in Teams but speaks in the room → the microphone track still records them, so the line is attributed to the user (the microphone is recorded independently of Teams' mute).
- EC-3: The energy file is missing (measurement failed) → no line is attributed to the user; remote labels are unaffected; `trec transcribe` reports the smaller share.
- EC-4: The user and a remote participant talk over each other → the remote participant wins when their turn covers at least 30% of the line; otherwise the energy rule applies.

### US-003: Lines nobody could be attributed to stay as today

**As a** user, **I want** lines without evidence left unlabelled, **so that** a wrong name never appears where the pipeline does not know.

Acceptance criteria:

- AC-1: Given a line covered under 30% by every remote turn and not dominated by the microphone, when the meeting is transcribed, then the line reads `[HH:MM:SS] <text>` with no name.
- AC-2: Given no observer events and no energy file, when the meeting is transcribed, then the transcript has no labels and every downstream step behaves as before this feature.

Edge cases:

- EC-1: whisper's non-speech markers (such as `[BLANK_AUDIO]`) → never labelled and not counted in the labelled share.
- EC-2: A labelling failure (unreadable events file, inconsistent data) → the transcript is saved unlabelled, a warning is logged, transcription succeeds.

## Analysis on labels

### US-004: Owners in the minutes come from the labelled lines

**As a** user, **I want** the analysis to take the owner of a commitment from the name on the line, **so that** the owner column stops guessing from who was mentioned.

Acceptance criteria:

- AC-1: Given a labelled line in which the named person takes on a task, when the meeting is analyzed, then the action's owner is that person (the recording owner literal when the label is the user's).
- AC-2: Given an unlabelled line, when the meeting is analyzed, then the current rules apply (first person for the user, a name addressed for others, `indefinido` otherwise).
- AC-3: Given the claim verifier runs, when it reads the transcript, then its prompt treats a name on a line as reliable attribution of that line.

Edge cases:

- EC-1: A labelled line quotes someone else ("o Bruno disse que faz") → the owner rule still follows what the transcript makes evident; the label says who spoke, not who was quoted.
- EC-2: The label is the user's name and the line assigns the task to someone else by name ("Ana, você revisa?") → the owner is Ana, as today.

### US-005: The minutes' participants are the people seen in the meeting window

**As a** user, **I want** the participants list to be the people who were in the meeting, **so that** someone only mentioned never appears as present.

Acceptance criteria:

- AC-1: Given the observer saw participant tiles, when the meeting is analyzed, then the analysis's `participants` are exactly the names seen in the window (the user's own tile included), in order of first appearance.
- AC-2: Given the observer saw no tiles, when the meeting is analyzed, then the current rule applies (people who speak or are addressed).
- AC-3: Given a participant in the roster who never spoke, when the participant code check runs, then it does not flag them, and the verifier receives the roster as evidence of their presence; whether the claim ends confirmed is the verifier's verdict (unverified when verification is off).

Edge cases:

- EC-1: A participant joins late and leaves early → still in the roster (seen once).
- EC-2: The roster has a name the model never finds in the text → it is listed anyway; the code check does not flag it, and the verifier sees it in the roster.
- EC-3: A tile with an empty or placeholder name (for example a dial-in number) → listed as the text Teams showed.

### US-006: An automatic recording is titled with the meeting's subject

**As a** user, **I want** automatic recordings named after the meeting's subject, **so that** `trec status`, the minutes and the plan show the real name instead of an invented one.

Acceptance criteria:

- AC-1: Given a recording started without a title and a window title read by the observer, when the recording stops, then the meeting's title is the subject segment of the window title (before the first ` | `, or after the compact-view prefix).
- AC-2: Given a recording started with `trec start --title`, when it stops, then the title is kept.
- AC-3: Given no subject was read, when the meeting is analyzed, then the analysis's title is used as today.

Edge cases:

- EC-1: A one-to-one call → the subject is the other person's name, which becomes the title.
- EC-2: The subject changes during the meeting (the window title updates) → the first subject read wins.

## Operation

### US-007: A recording never waits for or fails because of the labels

**As a** user, **I want** recording, mixing, transcription and analysis to proceed even when the observer is missing, unauthorised, blind or dead, **so that** a diagnostics feature never costs me a meeting.

Acceptance criteria:

- AC-1: Given the helper is not built or the Accessibility permission is missing, when a call is detected, then the recording starts and `speakers.jsonl` holds one `unavailable` line with the reason code.
- AC-2: Given the helper dies during the call before reading any window, when the call ends, then the recorders stop, the tracks are mixed and transcribed, the daemon log names the death once, and the transcript's reason is "died before reading a window".
- AC-3: Given no Teams window could be read during the call, when the call ends, then the helper's `stop` event says so and the transcript is labelled with whatever was captured (possibly only the user's lines).
- AC-4: Given `trec stop` is run from another terminal, when the recording stops, then the helper started by the daemon or by `trec start` is stopped too.

Edge cases:

- EC-1: `[speakers] enabled = false` → no helper is started, no `unavailable` line is written, the user's lines are still labelled from the microphone track.
- EC-2: The energy measurement fails (ffmpeg error or timeout) → mixing continues, the raw tracks are deleted after mixing as today, the failure is logged.
- EC-3: The daemon restarts in the middle of a recording → recovery stops the observer along with the recorders; events written so far are kept.
- EC-4: Windows → no observer; nothing in the recording flow changes.

### US-008: A day's first unlabelled meeting raises one notification with the reason

**As a** user, **I want** to be told once a day when meetings end with no labels, **so that** I fix the permission or the window without being nagged.

Acceptance criteria:

- AC-1: Given a transcribed meeting whose observer was wired (its events file exists), with zero labels for one of the reasons helper not built, permission missing, failed to start, died before reading a window or no window read, and no notification sent yet on the calendar day the transcription runs, when its transcription finishes, then one notification "Speaker labels unavailable" names the meeting and the reason.
- AC-4: Given a meeting with no events file (feature off, Windows, or recorded before this feature), when it is transcribed with zero labels, then no notification is sent.
- AC-5: Given tiles were read but no line matched them, when the transcription finishes, then no notification is sent; the daemon log and `trec transcribe` name the reason.
- AC-2: Given a notification already sent that day, when another meeting ends unlabelled, then no notification is shown and the daemon log records it.
- AC-3: Given a meeting with at least one label, when its transcription finishes, then no notification is sent.

Edge cases:

- EC-1: The marker file is missing or unreadable → treated as "not notified today"; one notification is sent and the marker is rewritten.
- EC-2: Several meetings are transcribed in the same minute (resume after a restart) → still at most one notification that day.

### US-009: `trec doctor`, `trec status` and `trec transcribe` show the helper's state and the coverage

**As an** operator, **I want** the CLI to tell me whether the helper can run and how much of each transcript got labels, **so that** I can see drift or a lost permission without reading logs.

Acceptance criteria:

- AC-1: Given the helper is built and authorised, when I run `trec doctor`, then a line says `speaker labels` is ok with the helper's path and that the permission is granted.
- AC-2: Given the permission is missing, when I run `trec doctor`, then the line is informational (the doctor does not fail) and names the exact command to request the permission and where to allow it.
- AC-3: Given the helper is not built, when I run `trec doctor`, then the line names the build script.
- AC-4: Given a transcribed meeting, when I run `trec transcribe <id>` or `trec status`, then I see the share of labelled lines (and, after transcribing, the names found or the reason for no labels); a transcript labelling ran on with zero labels shows `0%` and the reason in `trec status`, so drift is visible.
- AC-5: Given `--check` reports the permission granted in the doctor's own context but the last recording's observer reported it missing, when I run `trec doctor`, then the line warns about the mismatch and names the identity the grant must go to.

Edge cases:

- EC-1: `[speakers] enabled = false` → the doctor line says so instead of checking the permission.
- EC-2: A meeting transcribed before this feature (no labelling summary) → `trec status` shows no speakers segment for it.

## Installation

### US-010: Build the helper and grant its permission with the existing tools

**As an** operator, **I want** the native build script to build the helper and the installer to explain the third permission, **so that** a fresh install gets labels without reading source code.

Acceptance criteria:

- AC-1: Given a checkout, when I run `scripts/build-native.sh`, then both `teams-tap` and `teams-speakers` are built and their paths printed.
- AC-2: Given `scripts/install.sh`, when it reaches the permissions step, then it names Microphone, Screen & System Audio Recording and Accessibility, and can open the three settings panes.
- AC-3: Given the helper is built but not authorised, when I run its `--check --prompt`, then macOS asks for the Accessibility permission for the identity it holds responsible (determined by the permission spike and named by the installer), and `--check` returns 0 in that context once granted.

Edge cases:

- EC-1: The helper is rebuilt after the permission was granted → macOS may ask again; `trec doctor` shows the permission missing until it is granted again, and the build script prints that reminder.
- EC-2: Teams is not running when the helper starts → it keeps polling and logs once a minute until stopped.

## Compatibility

### US-011: Meetings recorded before this feature behave exactly as before

**As a** user, **I want** my existing meetings, transcripts and analyses untouched, **so that** nothing I already have changes or breaks.

Acceptance criteria:

- AC-1: Given a `transcript.json` without `speaker` fields, when it is loaded and rendered, then `transcript.txt`, the minutes and the model messages are byte-for-byte what they were.
- AC-2: Given a `current_recording.json` without `speakers_handle`, when the daemon recovers or `trec stop` runs, then the two recorders are stopped as before and no error is raised.
- AC-3: Given a meeting without `speakers.jsonl` or `energy.json`, when it is transcribed again, then it gets an unlabelled transcript whose reason is "no observer data for this meeting", and no notification is sent.

Edge cases:

- EC-1: An old analysis is re-rendered with `trec minutes` → unchanged output.
- EC-2: A transcript labelled by this feature is read by the previous version of the code → the `speaker` key is ignored and lines render without names.
