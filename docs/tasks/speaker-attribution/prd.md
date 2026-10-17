# PRD: Speaker attribution — who said each line, read from the Teams window, without a voice model

> **Status:** approved 2026-10-16 · **Slug:** `speaker-attribution`
> **Evidence:** [investigation and spike runs](../../SPEAKER-ATTRIBUTION.md) (eight probe runs on 2026-10-16 with `scripts/ax-speaker-probe.swift`, the last two with a colleague in a test meeting)
> **Follows:** the fidelity guard (`docs/tasks/prd-fidelity-guard/`), whose evaluation measured the owner errors this PRD removes at the source and which listed speaker diarization as out of its scope
> **Recreated:** 2026-10-17, after the original (`tasks/prd-speaker-attribution/prd.md`, never committed) was lost when the `tasks/` folder moved under `docs/tasks/`; rebuilt from the session that wrote it, with every note added since.
> **Progress:** the specification (product and technical parts, user stories, developer-experience contract, tests and ADRs) is in this folder (`cy-create-spec`, 2026-10-16), reviewed once (12 issues, applied). The task list is [_tasks.md](_tasks.md). Tasks 1–8 done (2026-10-16/17), including the live run of the helper (task 2) and the permission spike (task 3); task 9's documentation done; the gates below are pending, with `trec agent restart` (the user's approval). The implementation review (rounds 2 and 3) came back clean on 2026-10-17.

## 1. Problem

The transcript has no speaker labels, so the analysis guesses who said what from the words alone:

- **Owners are the biggest class of analysis errors.** Of 57 wrong claims measured in the fidelity evaluation (359 claims over 15 synthetic meetings), 22 had the wrong owner and 14 listed as a participant someone who was only mentioned. The analysis prompt told the model that "there is no speaker identification" and gave it heuristics (first person = the user, a name addressed = that person); the claim verifier then marks what it cannot confirm. Natural owner errors are the verifier's hard case (52% caught), because the transcript itself is ambiguous.
- **The user's own commitments rest on a heuristic.** "Eu faço", "pode deixar comigo" are taken as the user's; anyone else's first person is taken as the user's too, and the user's spontaneous commitments were kept in the plan only by a deliberate prompt decision (fidelity guard, task 6.0).
- **A wrong owner travels.** One inverted owner reached all six following daily plans and that day's stories (fidelity evaluation §14).
- **Automatic recordings have no title**, so the model invents one, and the minutes list participants the model inferred, not the people who were there.

The obvious fix, recognising voices, does not fit: the people in the user's meetings change constantly, so a voiceprint per person would never be complete, and the project keeps every model and every byte of audio local.

## 2. Goal

Every line of a Teams meeting's transcript carries the display name of the person who said it whenever Teams itself showed who was speaking, the user's own lines are labelled from the microphone track, and the analysis takes owners, participants and the meeting title from those labels instead of guessing. No voice is modelled, nothing leaves the Mac, and a recording never depends on it: when the labels cannot be read, the pipeline behaves exactly as before and says so.

## 3. Evidence (summary of the investigation)

| Finding | Where it was measured |
|---|---|
| Teams' audio reaches the recorder as one stereo mixdown of every remote participant: there is no per-participant audio to record, and Teams writes nothing about speakers to its logs | `capture.log`, the client's logs and telemetry cache (investigation §1–2) |
| The new Teams client (WebView2 on Chromium) exposes its meeting window through the macOS Accessibility API, with DOM ids and classes | runs 1, 7 |
| Each remote participant is a tile (`AXMenuItem`) whose text starts with the display name; the own tile is an `AXImage` "Vídeo de mim mesmo, <name>, …, Mudo desativado"; the mute state is text, the speaking state is not | runs 1, 7 |
| **The tile's frame element gains the class `vdi-frame-occlusion` (with eight atomic classes) while its participant speaks and loses it when they stop.** With the user muted and a colleague talking in bursts: 12 transitions in 115 s, in sync with the bursts; a change shows up within one polling pass (0.5–1 s) | run 8, confirmed against run 7's two states |
| The accessibility tree of a window that is fully covered freezes; a visible window, or the compact meeting view Teams keeps on top when the meeting loses focus, updates every second | runs 6, 7 |
| The meeting window's title starts with the meeting subject (or the other person's name in a one-to-one call) | runs 1, 2, 7 |
| The microphone is already a separate track aligned to the same start instant as the Teams track, so the user's lines can be told apart by energy without any model; remote speech leaking from the speakers into the microphone is louder on the Teams track | pipeline (investigation §1, option B) |
| Alternatives ruled out for this delivery: Teams' own transcript through Graph (tenant policy, admin consent, visible to all participants), a Graph media bot, spatial-audio panning, per-meeting voice clustering (kept as a possible fallback) | investigation §3 C–F |

## 4. Scope

**In scope**
- **S1 Speaker observer (P0, macOS):** a helper beside `teams-tap`, started and stopped with every recording, reads the Teams meeting windows through the Accessibility API and writes a timeline of `(wall-clock, participant name, speaking on/off)` events, the names seen (the roster), the user's own display name and the meeting subject, with the window found/lost events and counters needed to diagnose it.
- **S2 Energy of the raw tracks (P0):** before the raw tracks are deleted after mixing, the level of each track is measured in 100 ms windows and saved with the meeting.
- **S3 Labelling at transcription (P0):** every whisper segment gets the remote participant whose speaking interval covers it, else the user when the microphone track dominates, else no label.
- **S4 Downstream use (P1):** `transcript.txt` and the messages sent to the analyzer and the claim verifier show the name on each labelled line; the analysis prompt takes owners from the labels and participants from the roster; the participant code check accepts a labelled speaker; the meeting title comes from the window's subject when the recording has none.
- **S5 Fail-soft operation and diagnostics (P0):** the observer can fail to start, lose the window or die without the recording noticing; a day's first unlabelled meeting raises one notification with the reason; `trec doctor` shows the helper's build and the Accessibility permission; the helper and the pipeline log what a bug report needs.
- **S6 Installation and documentation (P1):** the native build script builds the helper, the installer and the README explain the third macOS permission (Accessibility), the PRD pages and the requirements document record the behaviour.

**Out of scope**
- Voice identification (a voiceprint per person): the premise of this PRD.
- Voice clustering as a fallback when the window cannot be read: considered after gates G1–G2 show how much coverage the window gives.
- Windows parity (UI Automation on the WebView2): a separate task after the macOS behaviour settles.
- Reading the live captions pane, Teams' own transcript (Graph) or a media bot.
- Driving Teams: the observer only reads; it never focuses, moves or clicks anything.

## 5. Functional requirements

| # | Requirement |
|---|---|
| FR1 | For the whole recording, the observer samples the Teams meeting windows (the main window and the compact view) at least twice per second and writes one JSON line per event to `speakers.jsonl` in the meeting folder: a participant's speaking state changing, a participant tile seen for the first time, the window's subject, a call window found or lost, start/stop records with counters. The speaking state is the presence of the `vdi-frame-occlusion` class set on the tile's frame element; a lost window ends the speaking state of its tiles. |
| FR2 | Before the raw tracks are deleted, the level of each track is measured in 100 ms windows and saved as `energy.json`. A measurement failure is logged and mixing proceeds. |
| FR3 | At transcription each segment is labelled: the remote participant whose speaking intervals cover at least 30% of it (largest overlap wins); else the user, when the microphone track is at least 6 dB louder than the Teams track and above −50 dBFS; else no label. Missing inputs yield fewer labels, never an error. |
| FR4 | A labelled segment is written as `[HH:MM:SS] <name>: <text>` in `transcript.txt`, the analyzer's and the verifier's messages; unlabelled segments are unchanged. Old transcripts load and render as before. `trec transcribe` and `trec status` report the labelled share. |
| FR5 | The analysis prompt takes owners from labels (the first-person heuristic applies only to unlabelled lines); with a roster, `participants` is the roster; the verifier treats labels as reliable attribution; the participant code check accepts a labelled speaker or a roster name. |
| FR6 | An untitled recording takes the window's subject as its title when it stops. |
| FR7 | The observer never blocks or fails a recording; failures are logged. The first meeting of a day that ends with no labels raises one notification with the reason; later ones that day only log. |
| FR8 | `trec doctor` shows the helper's build and its Accessibility permission without failing; the helper logs to `data/log/speakers.log`; the pipeline logs start, stop, failures, energy and labelling results. |
| FR9 | Everything stays on the Mac; the observer writes nothing to Teams. `speakers.jsonl` and `energy.json` live and die with the meeting. |
| FR10 | `scripts/build-native.sh` builds the helper; `scripts/install.sh` and the README name the Accessibility permission; `trec agent restart` (with the user's approval) is needed for the daemon to use it. |

Notes from the spec's review round 1 (2026-10-16):
- **FR7:** the reasons that notify are helper not built, permission missing, failed to start, died before reading a window, and no window read; "events found but no line matched" only logs; a meeting without observer data never notifies. The day is the day the transcription runs.
- **FR5:** the roster and the user's label travel with the transcript; the verifier receives the roster as evidence of presence; the participant code check does not flag roster names.
- **FR4/FR7:** a labelling summary is stored with the transcript, so `trec status` shows `0%` with the reason when labelling ran and found nothing.
- **FR10 / decision 1:** measured on 2026-10-17 (task 3) and decided by the user: the daemon starts the helper as its own launchd job per recording, the only context where the helper's own Accessibility grant applies (spawned by the daemon's Python, macOS asks for the Python's permission instead). The user adds the helper to the Accessibility list by hand; the installer and `trec doctor` say how.
- **FR9:** the helper sets no accessibility attribute at all.

Notes from the implementation review (round 2, 2026-10-17):
- **FR1/FR3:** the helper writes a heartbeat every 5 s and marks a window frozen when its call timer has not changed for 3 s; a speaking turn left open ends at the last event of the file, never at the meeting's end, so a dead helper or a covered window credits nobody with later lines.
- **FR7:** the observer's health check never delays the daemon's call handling; every launchctl call has a timeout; a helper job left by a crash during its start is booted out by recovery.

## 6. Success criteria

| Gate | Criterion | Status |
|---|---|---|
| G1 fidelity | In three real meetings with at least two remote participants, at least 90% of the labelled lines name the right speaker, checked by the user against the audio on a sample of 30 lines per meeting. | Pending |
| G2 coverage | In the same meetings, while a Teams window was rendered, at least 70% of the lines with speech carry a label (the share `trec status` reports). | Pending |
| G3 owners | Over the first ten real meetings with labels, the user agrees with at least 90% of the owner attributions in the minutes, and the owner marks "a confirmar" are fewer than in the ten meetings before. | Pending |
| G4 robustness | Two weeks of daemon operation with no recording lost, delayed or marked failed because of the observer, the energy measurement or the labelling. | Pending |
| G5 footprint | The helper averages under 10% of one CPU core during a meeting, and Teams stays responsive with it attached. | Pending |

## 7. Decisions

Proposed (from the evidence):
1. **A separate Swift helper, `teams-speakers`,** beside `teams-tap`, with its own embedded `Info.plist`. As built (task 3): it runs as its own launchd job per recording.
2. **The speaking state is a class on the tile's frame**, not text (run 8). The helper also records the tile's text, so a future Teams build that changes the class can be diagnosed.
3. **Wall-clock events, transcript seconds at use**, with the recording's start instant as the origin.
4. **Main and compact windows are merged**: a participant is speaking when either window says so.
5. **The helper is read-only.** It never changes focus, never keeps a window on top, never clicks anything. Keeping a Teams window visible is the user's part, stated in the README.
6. **Thresholds are constants, not settings** (30% overlap, 6 dB, −50 dBFS), tuned once by G1–G2.

Decided by the user on 2026-10-16 (the PRD interview):
7. **Scope: remote speakers from the window plus the user's lines from the two tracks' energy.** No voice clustering in this delivery.
8. **The minutes' participants are the names seen in the meeting window.** The model completes the list only when the window was not read.
9. **The meeting subject read from the window is the title** of a recording that has none.
10. **Without the permission or with a covered window, the recording goes on without labels and the user is told once a day**; the details stay in the logs and in `trec doctor`.

Adopted with the spec (the PRD's open questions): the daily notification carries only the reason; the observer runs for manual recordings too; the minutes gain no "said by" column.

Open after the live runs (2026-10-17): whether the helper needs to ask Chromium for its accessibility tree (the `AXEnhancedUserInterface` request the spike probe made); to be checked after a Teams restart without running the probe first. A test with a second participant needs a different account (a guest): the same account on two devices is one participant in Teams.
