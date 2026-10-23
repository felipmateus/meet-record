# User Stories: Check for speech before transcribing, and stop counting short replies as loops

The canonical behavior catalog for the speech check. Companion to `_spec.md`, and consumed by `_spec.md` Part II (component mapping) and `_tests.md` (coverage matrix). There is no `_uiux.md`, because the feature has no graphical interface.

## Personas

- **The user** owns the Mac and the recordings. The daemon records Teams calls on its own, so some recordings are accidental and some captures fail. The user wants no invented minutes, and wants to know quickly when a real meeting was not captured.
- **The operator** is the same person maintaining the install. They need to see whether the check works and which recordings had no speech, and to force a transcription when the check is wrong.

## Story Index

| ID | Feature Area | Persona | Story |
|---|---|---|---|
| US-001 | Speech check | user | A recording with no speech is not transcribed, and the flow continues |
| US-002 | Speech check | user | A long recording with no speech notifies me |
| US-003 | Speech check | user | A recording with speech is transcribed as today |
| US-004 | Language | user | Only language samples with speech vote |
| US-005 | Loops | user | Short replies do not make a transcript degraded |
| US-006 | Visibility | operator | `trec transcribe` and `trec status` show the speech check |
| US-007 | Diagnostics | operator | `trec doctor` shows whether the check can run |
| US-008 | Configuration | operator | Turn the check off to force a transcription |
| US-009 | Robustness | user | A check that fails never blocks a transcription |

## Speech check

### US-001: A recording with no speech is not transcribed, and the flow continues

**As** the user, **I want** a recording in which nobody speaks to get no transcription, **so that** whisper cannot invent text and minutes for it.

Acceptance criteria:

- AC-1: Given `speech_check = true`, when VAD measures under 2.0 s of speech in a recording, then whisper is not run, and neither are the language detection or the speaker labelling.
- AC-2: Given such a recording, when it is transcribed, then `transcript.json` has no segments, `"speech": {"found": false, …}`, the fallback language, and no `health`, `language_detection` or `labels`. `transcript.txt` has no lines, and the meeting's status is `transcribed`.
- AC-3: Given such a recording, when it is transcribed, then the warning `no speech in <id>: …` is logged.
- AC-4: Given such a transcript, when the meeting is analyzed, then the analysis is the local empty one (`Empty transcript: no speech recognized.`) and no LLM call is made.
- AC-5: Given the two stored recordings without speech (2026-10-08_02-50-26 and 2026-10-17_10-15-32), when the check runs on them, then both come out with no speech, and every other stored recording comes out with speech (gate G1).

Edge cases:

- EC-1: A recording of a few seconds where one person says "alô?" (1 s of speech) → no speech, the same as silence. Nothing in it is worth transcribing.
- EC-2: A recording of loud noise, music or keyboard sound with no voice → no speech. VAD tells a voice apart from noise (the 5-minute noise recording measured 0.0 s).
- EC-3: Exactly 2.0 s of speech → speech found, so it is transcribed. The rule is "under 2.0 s".
- EC-4: The recording is transcribed again (`trec transcribe <id>`) → it is checked again, and the result replaces the earlier transcript.
- EC-5: The Teams track was recorded at the wrong sample rate and holds no speech → no speech. With no health record there is no rate flag, and the rate warning is still logged.

### US-002: A long recording with no speech notifies me

**As** the user, **I want** a notification when a recording of a minute or more has no speech, **so that** I notice a failed capture while I can still do something about it.

Acceptance criteria:

- AC-1: Given a no-speech recording whose audio is 60 s or longer, when the daemon transcribes it, then one desktop notification "No speech in a recording" names the meeting and the minutes of audio, and points to `trec doctor`. In a `trec transcribe` run, the same notification is logged at info level through the headless `LogNotifier`, which a CLI run does not show. There, the user-visible signal is the `WARNING:` line of US-006.AC-2.
- AC-2: Given a no-speech recording shorter than 60 s, when it is transcribed, then there is no notification, and the warning is logged.

Edge cases:

- EC-1: Audio of exactly 60.0 s → notifies.
- EC-2: The notifier raises → the exception is caught, the warning `no-speech notification for <id> failed: …` is logged, the transcript is saved and `execute` returns it. No `error.txt` is written. The existing degraded and rate-mismatch notifications are not changed by this spec.
- EC-3: The same recording is transcribed twice → two notifications, one per transcription. There is no de-duplication.

### US-003: A recording with speech is transcribed as today

**As** the user, **I want** recordings with speech to go through whisper exactly as before, **so that** the check cannot make a real meeting worse.

Acceptance criteria:

- AC-1: Given a recording with 2.0 s of speech or more and a fixed language, when it is transcribed, then the whisper commands (first pass and retry) are byte-for-byte the same as with `speech_check = false`. In auto mode they are the same except for the `-l` value, which can change only through the language-sample filter, the planned-count rule and the duration stand-in (US-004).
- AC-2: Given such a recording, when it is transcribed, then `transcript.json` has `"speech": {"found": true, …}` with the measured seconds. Every other key is as today, with two exceptions by design:
  - `language_detection` lists only the samples sent, and its language can differ (US-004);
  - when `meta.json` has no duration, `health.total_minutes` comes from the measured length (US-004.AC-4).

Edge cases:

- EC-1: A recording with little speech in a long silence (the vans meeting: 6.2 of 36.4 min) → speech found, transcribed as today.

## Language

### US-004: Only language samples with speech vote

**As** the user, **I want** language detection to ignore samples where nobody speaks, **so that** silence cannot vote for a language.

Acceptance criteria:

- AC-1: Given `language = "auto"` and a check result, when a planned sample's 30-second window holds under 3.0 s of speech, then that sample is not sent to whisper and is not listed in `language_detection.samples`.
- AC-2: Given the vans meeting (5 of its 8 samples without speech), when its language is detected with the filter, then the result is still `en` (gate G2).
- AC-3: Given every stored recording with speech, when its language is detected with the filter, then the result equals the language-detection G1 result (gate G2).
- AC-4: Given a meeting whose `meta.json` has no duration, when it is transcribed with a check result, then the samples are planned over the audio length the check measured, not as a single sample at the start.

Edge cases:

- EC-1: Speech is found, but no planned sample holds 3.0 s of it → the result is `no-usable-sample` and the fallback language is used, as today.
- EC-2: The check is off or failed → the samples are planned and sent exactly as today.
- EC-3: Some samples were dropped → the info line `language samples of <id>: N of M without speech, not sent` is logged.
- EC-4: Several samples were planned and only one holds speech → that one sample does not decide alone. It needs 2 votes like any multi-sample meeting, so the result is `too-few-votes` and the fallback language. A meeting that was planned with a single sample keeps today's one-vote rule.

## Loops

### US-005: Short replies do not make a transcript degraded

**As** the user, **I want** natural short replies ("Okay.", "Thank you.", "Tá.") not to count as a hallucination loop, **so that** a healthy meeting is not flagged degraded or transcribed twice. A real loop must still be caught.

Acceptance criteria:

- AC-1: Given a line of at most 2 words that never stands in a run of 3 or more short, window-flagged lines, when the transcript's health is measured, then it does not count as a loop, however often it appears.
- AC-2: Given lines of at most 2 words that the window rule flags, when 3 or more of them stand in a row, then that run counts as a loop. Its lines may be the same ("e aí" ×3) or different ("Obrigado." / "Tchau." alternating).
- AC-3: Given a line of 3 or more words, when the health is measured, then the rule is today's.
- AC-4: Given the vans English retry transcript ("okay" ×8, at most 2 in a row, 10.4% today), when its health is measured, then it is 0.0% and not degraded (gate G3).

Edge cases:

- EC-1: A punctuation-only line (`...`) → counts as short.
- EC-2: "Ok." and "OK" → the same line (the comparison key is unchanged).
- EC-3: Health stored in older transcripts → unchanged until the meeting is transcribed again.
- EC-4: A lone short line inside a loop's window ("Ok." once, then "Ok." ×4 back to back 26 lines later) → only the back-to-back copies are flagged; the lone one is not.

## Visibility

### US-006: `trec transcribe` and `trec status` show the speech check

**As** the operator, **I want** to see how much speech each recording had, and which ones had none, **so that** I can spot a failed capture or a wrong verdict.

Acceptance criteria:

- AC-1: Given a recording with speech, when `trec transcribe <id>` finishes, then it prints `  Speech: <speech> of <audio> min (<share>)` before `Health:`.
- AC-2: Given a recording with no speech, when `trec transcribe <id>` finishes, then it prints the `Speech: none …` line and the `WARNING: the transcript is empty. …` line naming the meeting, and no `Health:`, `Language:` or `Speakers:` line.
- AC-3: Given meetings with no speech, when `trec status` runs, then each has `  · no speech` and no language marker, and the summary has `Recordings without speech: N` before `Unconfirmed claims:`.

Edge cases:

- EC-1: No meeting without speech → no count line.
- EC-2: Transcripts made before this feature → no marker, and they are not counted.
- EC-3: The check is off → `Speech: not checked ([transcription] speech_check = false)`.
- EC-4: The fallback language is not `pt` (`languages = ["en", "pt"]`) → a no-speech meeting still shows `· no speech` and no `· en`.

## Diagnostics

### US-007: `trec doctor` shows whether the check can run

**As** the operator, **I want** `trec doctor` to tell me whether the speech check is on and has its tool and model, **so that** I know whether recordings are being checked.

Acceptance criteria:

- AC-1: Given the tool and the model present, when `trec doctor` runs, then it prints `[ok ] speech check: on (<tool path>); …` after the retry line.
- AC-2: Given the tool missing, or the model missing, when `trec doctor` runs, then it prints the matching `[WARNING]` line (the model line with the download hint), and the doctor's exit code is unchanged.
- AC-3: Given `speech_check = false`, when `trec doctor` runs, then it prints `[info] speech check: off (…)`.

## Configuration

### US-008: Turn the check off to force a transcription

**As** the operator, **I want** a switch that turns the check off, **so that** I can transcribe a recording the check got wrong, or rule the check out when debugging.

Acceptance criteria:

- AC-1: Given `speech_check = false`, when a recording is transcribed, then no VAD runs, whisper runs as before 2026-10-22, and `transcript.json` has no `speech`.
- AC-2: Given a recording marked no speech, already analyzed by the daemon, and audio still kept, when the operator sets `speech_check = false` and runs `trec transcribe <id>` and then `trec analyze <id>`, then:
  - whisper transcribes it and its transcript replaces the empty one;
  - the analysis and the minutes are rebuilt from it, with an LLM call;
  - the curator runs a pass on it.

  The operator then sets `speech_check = true` again.
- AC-3: Given `speech_check = true`, `vad = false` and `retry_vad = false`, when the installer runs, then it downloads the Silero model.

Edge cases:

- EC-1: The key is absent → on.
- EC-2: The audio was already purged (after `retention_days`) → `trec transcribe <id>` fails as today for a missing `audio.m4a`.
- EC-3: The operator runs `trec analyze` without an id after the re-transcription → nothing happens for this meeting, because it is already `analyzed`. The WARNING line and the troubleshooting guide name `trec analyze <id>` for this reason.

## Robustness

### US-009: A check that fails never blocks a transcription

**As** the user, **I want** a broken or missing speech check to leave transcription as it was, **so that** this feature can never cost me a transcript.

Acceptance criteria:

- AC-1: Given the tool missing, the model missing, a timeout, a non-zero exit, or output in an unknown format, when a recording is transcribed, then whisper runs as with the check off, a warning `speech check of <id> failed; …` is logged, and no `error.txt` or notification is written.
- AC-2: Given the tool's output changes format, when the check runs, then it is a failed check, never "no speech".

Edge cases:

- EC-1: ffmpeg cannot read the audio → a failed check. The transcription then fails or succeeds on its own, as today.
- EC-2: The check's temporary folder → removed on success and on failure. Nothing is written to the meeting folder.
