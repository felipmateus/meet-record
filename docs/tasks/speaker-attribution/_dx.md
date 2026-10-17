# Developer Experience: Speaker attribution from the Teams window

Public-surface contract for speaker attribution. Companion to `_spec.md` (Part II serves this surface) and `_tests.md` (E2E journeys use these exact invocations). Written as if shipped.

## Golden Path

```
$ scripts/build-native.sh
binary: /Users/me/Projetos/Pessoal/teams-recorder/native/teams-tap/.build/release/teams-tap
binary: /Users/me/Projetos/Pessoal/teams-recorder/native/teams-speakers/.build/release/teams-speakers
note: if macOS asked for the Accessibility permission before, it may ask again for the rebuilt teams-speakers (trec doctor tells)

# System Settings > Privacy & Security > Accessibility > + > Cmd+Shift+G >
#   native/teams-speakers/.build/release/teams-speakers > Open; the switch on
# (the daemon starts the helper as its own launchd job, so the grant must be on the helper itself)

$ trec doctor
[ok ] ffmpeg: /opt/homebrew/bin/ffmpeg
…
[ok ] speaker labels: teams-speakers at native/teams-speakers/.build/release/teams-speakers; Accessibility permission granted
…

$ trec agent restart          # with the user's approval: the daemon loads the new code
daemon restarted.

# a Teams meeting happens; the daemon records it with a Teams window visible on screen

$ trec transcribe 2026-10-17_09-30-12
Transcribing 2026-10-17_09-30-12… ok (214 segments, 42.0 min)
  Health: 0% of segments in repetition loops, text in 42 of 42 min
  Speakers: 78% of 214 lines labelled (Felipe, Lucas Huguenin Gurgel de Moura)
  Text: data/recordings/2026-10-17_09-30-12/transcript.txt
Analyze with `trec analyze`.

$ sed -n 40,43p data/recordings/2026-10-17_09-30-12/transcript.txt
[00:03:12] Lucas Huguenin Gurgel de Moura: então eu subo o ambiente de homologação até quarta
[00:03:20] Felipe: pode deixar comigo o relatório
[00:03:30] a gente combina o resto depois
[00:03:41] Lucas Huguenin Gurgel de Moura: fechado
```

## Files

Written per meeting, in `data/recordings/<id>/`, next to the transcript. Both are deleted with the meeting.

`speakers.jsonl` — one JSON object per line, written by `teams-speakers` during the recording (`t` is Unix seconds):

```json
{"t": 1760655012.418, "event": "start", "epoch": 1760655010.000, "interval": 0.5, "teams_pid": 15347, "version": 1}   ← epoch is the time origin of every event
{"t": 1760655012.931, "event": "window", "kind": "main", "state": "found", "title": "Planejamento da sprint | RADIX ENGENHARIA E DESENVOLVIMENTO DE SOFTWARE S/A | felipe.mateus@radixeng.com | Microsoft Teams"}
{"t": 1760655012.931, "event": "title", "subject": "Planejamento da sprint"}
{"t": 1760655012.931, "event": "seen", "name": "Felipe Mateus de Carvalho", "me": true, "window": "main"}
{"t": 1760655012.931, "event": "seen", "name": "Lucas Huguenin Gurgel de Moura", "me": false, "window": "main"}
{"t": 1760655201.104, "event": "speaking", "name": "Lucas Huguenin Gurgel de Moura", "speaking": true, "window": "main"}
{"t": 1760655209.620, "event": "speaking", "name": "Lucas Huguenin Gurgel de Moura", "speaking": false, "window": "main"}
{"t": 1760655215.000, "event": "heartbeat"}
{"t": 1760655340.207, "event": "window", "kind": "main", "state": "lost", "title": "Planejamento da sprint | RADIX ENGENHARIA E DESENVOLVIMENTO DE SOFTWARE S/A | felipe.mateus@radixeng.com | Microsoft Teams"}
{"t": 1760655340.207, "event": "window", "kind": "compact", "state": "found", "title": "Modo de exibição compacto da reunião | Planejamento da sprint | RADIX ENGENHARIA E DESENVOLVIMENTO DE SOFTWARE S/A | felipe.mateus@radixeng.com | Microsoft Teams"}
{"t": 1760657530.512, "event": "stop", "reason": "signal", "passes": 5021, "transitions": 388, "ax_errors": 0, "slow_passes": 3}
```

When the helper could not start, the file has exactly one line, written by the recorder:

```json
{"t": 1760655012.418, "event": "unavailable", "reason": "permission-missing"}
```

`reason` is one of `binary-missing`, `permission-missing`, `start-failed`. The reasons the pipeline derives, what `trec transcribe` prints and whether the daily notification fires:

| Reason code | `trec transcribe` line | Notifies | Notification body |
| --- | --- | --- | --- |
| `binary-missing` | `Speakers: no labels (the observer did not run: teams-speakers not built)` | yes | `teams-speakers is not built. Run scripts/build-native.sh.` |
| `permission-missing` | `Speakers: no labels (the observer did not run: Accessibility permission missing)` | yes | `Accessibility permission missing for teams-speakers. Run trec doctor.` |
| `start-failed` | `Speakers: no labels (the observer did not run: it failed to start; see data/log/speakers.log)` | yes | `the observer failed to start. See data/log/speakers.log.` |
| `observer-died` | `Speakers: no labels (the observer died before reading a Teams window; see data/log/speakers.log)` | yes | `the observer died before reading a Teams window. See data/log/speakers.log.` |
| `no-window` | `Speakers: no labels (no Teams meeting window was read during the call)` | yes | `no Teams meeting window was read during the call. Keep a Teams window visible.` |
| `no-match` | `Speakers: no labels (speaker events found but no line matched them)` | no (log only) | — |
| `no-observer` | `Speakers: no labels (no observer data for this meeting)` | no | — |

`energy.json` — the level of each raw track per 100 ms, measured before the tracks are deleted:

```json
{"step_seconds": 0.1, "tracks": {"tap.wav": [-120.0, -61.2, -58.9, -31.4, -29.8], "mic.wav": [-120.0, -70.3, -69.1, -66.0, -38.2]}}
```

Levels are dBFS; `-120.0` is digital silence. The arrays are as long as the longer track in 100 ms steps.

`transcript.txt` — labelled lines carry the name after the timestamp; unlabelled lines are unchanged:

```
[00:03:12] Lucas Huguenin Gurgel de Moura: então eu subo o ambiente de homologação até quarta
[00:03:20] Felipe: pode deixar comigo o relatório
[00:03:30] a gente combina o resto depois
```

`transcript.json` — each labelled segment gains `"speaker"`, and the file gains a `speakers` summary (absent on transcripts made before this feature, present even when nothing was labelled):

```json
{"start": 192.0, "end": 199.5, "text": "então eu subo o ambiente de homologação até quarta", "speaker": "Lucas Huguenin Gurgel de Moura"}
{"start": 210.0, "end": 213.2, "text": "a gente combina o resto depois"}
```

```json
"speakers": {"roster": ["Felipe Mateus de Carvalho", "Lucas Huguenin Gurgel de Moura"], "user_label": "Felipe", "labelled": 167, "eligible": 214, "reason": null}
```

## CLI

### `teams-speakers`

```
$ teams-speakers --out data/recordings/<id>/speakers.jsonl --epoch 1760655010.000      # both options are required
teams-speakers: Accessibility permission granted; watching Teams (pid 15347) every 0.5 s; events → data/recordings/<id>/speakers.jsonl
teams-speakers: window found (main): Planejamento da sprint | …
teams-speakers: tile seen: Felipe Mateus de Carvalho (me) (main)
teams-speakers: tile seen: Lucas Huguenin Gurgel de Moura (main)
…
teams-speakers: stopping (signal); 5021 passes, 388 transitions, 0 accessibility errors, 3 slow passes
```

Exit codes: `0` stopped normally · `2` bad arguments (usage on stderr; `--out` and `--epoch` are required) · `3` Accessibility permission missing · `4` the output file could not be written. Every event line is flushed as it is written. `--check` reports the permission of the process macOS holds responsible in the context it runs from: typed in a terminal it reports the terminal's grant. The daemon starts the helper as its own launchd job (`local.teams-recorder.speakers`), where the helper's own grant applies, and `trec doctor` runs its check the same way.

```
$ teams-speakers --check
Accessibility permission: granted
$ echo $?
0

$ teams-speakers --check
Accessibility permission: missing. Run with --prompt to request it, then allow teams-speakers under System Settings > Privacy & Security > Accessibility.
$ echo $?
3

$ teams-speakers --check --prompt
Accessibility permission: missing. Allow teams-speakers under System Settings > Privacy & Security > Accessibility, then run --check again.
```

A window whose call timer has not changed for 3 s is logged `window frozen (main): the call timer has not changed for 3 s; the window is covered or not rendering` (and `window live again (main): the call timer moved` when it moves), with the matching `frozen` and `found` `window` events; a `heartbeat` event is written every 5 s. With `--verbose`, each pass logs its element count and duration. Teams not running: `teams-speakers: Teams (com.microsoft.teams2) is not running; waiting` once a minute until stopped.

### `trec doctor`

One new line, never failing the doctor:

```
[ok ] speaker labels: teams-speakers at native/teams-speakers/.build/release/teams-speakers; Accessibility permission granted; last recording 2026-10-17_09-30-12: observer ran, 78% of lines labelled
[info] speaker labels: teams-speakers at native/teams-speakers/.build/release/teams-speakers; Accessibility permission missing → run `native/teams-speakers/.build/release/teams-speakers --check --prompt` and allow teams-speakers (add it with the + button: native/teams-speakers/.build/release/teams-speakers) under System Settings > Privacy & Security > Accessibility
[WARNING] speaker labels: Accessibility permission granted to teams-speakers now, but the last recording 2026-10-17_09-30-12 reported it missing → record again to confirm; if it still reports it missing, add teams-speakers again (add it with the + button: native/teams-speakers/.build/release/teams-speakers)
[info] speaker labels: teams-speakers not built → scripts/build-native.sh
[info] speaker labels: off ([speakers] enabled = false); only your own lines are labelled, from the microphone track
```

Amendment (2026-10-17, task 8): the doctor's check runs the helper as its own launchd job (task 3's design), so it reports the helper's grant, the same one the daemon's observer uses, not the terminal's. The `[WARNING]` therefore no longer says "for this terminal"; it fires when that check passes but the latest transcript's summary reason is `permission-missing` (the permission was granted after that recording, or the grant does not hold for the daemon's job), replaces the `[ok ]` line, and advises recording again before adding the helper again. The last-recording clause reads the latest transcribed meeting: `observer ran, NN% of lines labelled` when it has labels, otherwise the reason text of the table above (for example `no Teams meeting window was read during the call`, or `no observer data for this meeting` when the daemon was not restarted since the feature was installed); nothing when that transcript has no summary. The line is not shown on Windows (the helper reads the macOS Accessibility API).

### `trec transcribe`

After the health line:

```
  Speakers: 78% of 214 lines labelled (Felipe, Lucas Huguenin Gurgel de Moura)
```

When nothing was labelled, the reason:

```
  Speakers: no labels (the observer did not run: Accessibility permission missing)
  Speakers: no labels (the observer did not run: teams-speakers not built)
  Speakers: no labels (the observer did not run: it failed to start; see data/log/speakers.log)
  Speakers: no labels (no Teams meeting window was read during the call)
  Speakers: no labels (speaker events found but no line matched them)
  Speakers: no labels (no observer data for this meeting)
```

### `trec status`

The meeting line gains a speakers segment when the transcript has labels:

```
  2026-10-17_09-30-12 Planejamento da sprint  [analyzed]  · speakers 78%
  2026-10-17_14-00-03 Daily  [analyzed]  · speakers 0% (no Teams meeting window was read during the call)
  2026-10-14_19-58-07  [analyzed]
```

Amendment (2026-10-17, task 8, the user's review): a transcript whose summary reason is `no-observer` (feature off, Windows, meetings recorded without observer data) gets no speakers segment, like one without a summary; `· speakers NN%` shows when labels exist and `· speakers 0% (<reason text>)` for every other zero-label reason (reason texts as in the table under Files). The segment comes right after the status and next step, before the degraded, wrong-rate and unconfirmed markers. `trec transcribe` prints the `Speakers:` line after the whole health block (the health line and its warnings), before `Text:`, and prints the `no-observer` text there because the user asked for that command.

### `trec start` / `trec stop`

Unchanged invocations. `trec start` prints one more track line when the observer started:

```
Recording meeting 2026-10-17_09-30-12 (target PID 15347).
  Teams:       data/recordings/2026-10-17_09-30-12/tap.wav  (recorder PID 65201)
  Microphone:  data/recordings/2026-10-17_09-30-12/mic.wav  (recorder PID 65202)
  Speakers:    data/recordings/2026-10-17_09-30-12/speakers.jsonl  (observer PID 65203)
Stop with `trec stop` or discard with `trec cancel`.
```

Without the observer: `  Speakers:    not running (Accessibility permission missing; see trec doctor)`. The reason is the one the recording wrote to `speakers.jsonl`: `teams-speakers not built` and `Accessibility permission missing` point to `see trec doctor`, `it failed to start` to `see data/log/speakers.log`. With `[speakers] enabled = false` (or on Windows) there is no observer and no line. `trec stop` prints nothing more: it stops the observer through the persisted handle.

## Config

```toml
[speakers]
# Read who is speaking from the Teams meeting window during each recording and label the
# transcript lines with the display names. Needs the teams-speakers helper (scripts/build-native.sh)
# and the Accessibility permission for it (trec doctor tells how). Keep a Teams window visible
# during meetings: a fully covered window stops updating. false = no observer; your own lines are
# still labelled from the microphone track.
enabled = true
```

- `enabled` (default `true`): with `false`, `trec doctor` shows the feature off, no helper is started, `speakers.jsonl` is not written, and only the user's lines are labelled.

## Notification

Once per calendar day (the day the transcription runs), on the first transcribed meeting whose observer was wired and that has no label for a notifying reason (table above):

```
Speaker labels unavailable
Meeting 2026-10-17_09-30-12: Accessibility permission missing for teams-speakers. Run trec doctor.
```

The other bodies are in the reason table above. No notification for `no-match` (log only) or `no-observer` (feature off, Windows, meetings recorded before this feature).

## Errors

| Condition | What the user or agent sees | Points to |
| --- | --- | --- |
| Helper not built | `trec doctor`: `[info] speaker labels: teams-speakers not built → scripts/build-native.sh`; recording proceeds; `speakers.jsonl` = `{"event":"unavailable","reason":"binary-missing"}` | `scripts/build-native.sh` |
| Accessibility permission missing | `teams-speakers --check` exit 3 with the message above; `trec doctor` info line with the request command; recording proceeds; `reason: "permission-missing"`; one daily notification | System Settings > Privacy & Security > Accessibility |
| Helper exits right after starting | daemon log `speaker observer unavailable for <id>: start-failed (…tail…)`; recording proceeds; `reason: "start-failed"` | `data/log/speakers.log` |
| Helper dies mid-call | daemon log `capturer teams-speakers (pid N) died during call <id>; see data/log/speakers.log` once; recording proceeds; if it died before reading any window the transcript's reason is `observer-died` (notifies) | `data/log/speakers.log` |
| No Teams window read | helper log once a minute `no Teams meeting window found; waiting (<seconds> s without a call window with tiles)`; `stop` event `reason: "signal"` with zero `seen` events; `trec transcribe`: `no labels (no Teams meeting window was read during the call)` | keep a Teams window visible |
| Energy measurement failed | daemon log `energy of <track> could not be measured: <error>; the user's lines will not be labelled`; mixing proceeds | ffmpeg error text in the log |
| Labelling failed | daemon log `speaker labels of <id> could not be computed: <error>; transcript saved without labels`; transcription succeeds | the events file |
| `energy.json` or `speakers.jsonl` unreadable | treated as absent, with the log line above | the file |
