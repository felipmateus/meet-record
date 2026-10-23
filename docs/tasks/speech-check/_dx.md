# Developer Experience: Check for speech before transcribing, and stop counting short replies as loops

Public-surface contract for the speech check. Companion to `_spec.md`, whose Part II serves this surface, and to `_tests.md`, whose E2E journeys use these exact invocations. It is written as if the feature has shipped.

## Golden Path

```
$ git pull && trec agent restart          # with the user's approval: the daemon loads the new code
daemon restarted.

$ trec doctor
…
[ok ] retry of a degraded transcript: on (-mc 0 with VAD: /Users/me/Projetos/Pessoal/teams-recorder/data/models/ggml-silero-v5.1.2.bin)
[ok ] speech check: on (/opt/homebrew/bin/whisper-vad-speech-segments); a recording with under 2 s of speech is not transcribed
[info] language: detected per meeting among pt, en (fallback pt)
…

# Teams starts a call by mistake, or the capture fails; the daemon records 5 minutes with nobody speaking.
# A notification appears on the Mac:
#   No speech in a recording
#   Meeting 2026-10-17_10-15-32: no speech in 5 min of audio, so it was not transcribed. If it was a meeting, check the capture with `trec doctor`.

$ trec transcribe 2026-10-17_10-15-32     # (or let the daemon do it; this is the same step by hand)
Transcribing 2026-10-17_10-15-32…no speech in 2026-10-17_10-15-32: 0.0 s of speech in 5.2 min of audio (under 2.0 s); whisper skipped, transcript empty
 ok (0 segments, 0.0 min)
  Speech: none (0.0 s of speech in 5.2 min); whisper did not run
  WARNING: the transcript is empty. If this was a meeting, check the capture with `trec doctor`. To transcribe it anyway, set [transcription] speech_check = false, run `trec transcribe 2026-10-17_10-15-32` and `trec analyze 2026-10-17_10-15-32`, then set it back to true.
  Text: data/recordings/2026-10-17_10-15-32/transcript.txt
Analyze with `trec analyze`.

$ trec status
…
  2026-10-17_10-15-32  [analyzed]  · no speech
  2026-10-17_09-56-47 Daily do time  [analyzed]  · speakers 78%
…
Recordings without speech: 1
```

A meeting with speech only gains the `Speech:` line:

```
$ trec transcribe 2026-10-23_14-00-05
Transcribing 2026-10-23_14-00-05… ok (412 segments, 52.3 min)
  Speech: 44.6 of 52.3 min (85%)
  Health: 0% of segments in repetition loops, text in 52 of 52 min
  Language: en (heard in 11 of 11 counted samples; 11 taken)
  Speakers: 74% of 412 lines labelled (Felipe, John Carter)
  Text: data/recordings/2026-10-23_14-00-05/transcript.txt
Analyze with `trec analyze`.
```

## Config

`config.toml`, `[transcription]` section, with the new key and its comment as shipped:

```toml
# Before transcribing, check that someone speaks: Silero VAD (the `vad_model` below) runs over the
# whole recording, and one with under 2 s of speech is not sent to whisper. Its transcript is saved
# empty and marked "no speech", a warning is logged, and a recording of 1 minute or more notifies.
# Set to false to transcribe every recording as before, for example to force one through.
speech_check = true
```

| Key | Default | Observable effect |
|---|---|---|
| `speech_check` | `true` | `true`: every transcription measures speech first. `transcript.json` gets `speech`, `trec transcribe` prints `Speech:`, and a recording with no speech is not transcribed. `false`: transcription runs as before 2026-10-22, with no `speech` key and `Speech: not checked (…)` |
| `vad_model` (existing) | `"silero-v5.1.2"` | Now also the model of the speech check. The installers download it whenever `speech_check` is on |

## CLI

### `trec transcribe [id]`

A `Speech:` line comes first, right after ` ok (…)` and before `Health:`. Its forms:

```
  Speech: 44.6 of 52.3 min (85%)
  Speech: none (0.0 s of speech in 5.2 min); whisper did not run
  Speech: not checked ([transcription] speech_check = false)
  Speech: not checked (the speech check failed; see the warning above)
```

For a recording with no speech, the `Log.NO_SPEECH` warning goes to stderr as it is logged, between `Transcribing <id>…` and ` ok (…)`, as in the golden path. After ` ok (…)`, the `Speech: none` line is followed by one `WARNING:` line. There is no `Health:`, `Language:` or `Speakers:` line, because whisper did not run:

```
  WARNING: the transcript is empty. If this was a meeting, check the capture with `trec doctor`. To transcribe it anyway, set [transcription] speech_check = false, run `trec transcribe 2026-10-17_10-15-32` and `trec analyze 2026-10-17_10-15-32`, then set it back to true.
```

The `WARNING:` line names `trec analyze <id>` because `trec analyze` without an id picks only `transcribed` meetings. In the daemon, a no-speech meeting has already been analyzed by the time the user reads the notification.

When the check fails, its warning goes to stderr as it is logged, between `Transcribing <id>…` and ` ok (…)`. This is the same mechanism as the language-detection warning:

```
Transcribing 2026-10-21_09-30-28…speech check of 2026-10-21_09-30-28 failed; transcribing without it: whisper-vad-speech-segments: timed out after 300s
 ok (530 segments, 38.2 min)
  Speech: not checked (the speech check failed; see the warning above)
  Health: 0% of segments in repetition loops, text in 38 of 38 min
  Language: pt (heard in 8 of 8 counted samples; 8 taken)
```

Exit codes are unchanged. A recording with no speech, and a failed check, both exit 0.

### `trec status`

A meeting whose transcript has no speech gets `  · no speech` after its other markers, and no language marker, whatever the fallback language. When at least one meeting has none, a count line is printed after `Degraded transcripts:` and the optional rate-mismatch line, before `Unconfirmed claims:`:

```
  2026-10-17_10-15-32  [analyzed]  · no speech
…
Degraded transcripts: 0
Recordings without speech: 2
Unconfirmed claims: 0 in 0 meeting(s)
```

Meetings with speech, unchecked meetings and meetings transcribed before this feature get no marker. The count line is absent when the count is 0.

### `trec doctor`

One line right after the `retry of a degraded transcript:` line and before `language:`. It never fails the doctor:

```
[ok ] speech check: on (/opt/homebrew/bin/whisper-vad-speech-segments); a recording with under 2 s of speech is not transcribed
[WARNING] speech check: whisper-vad-speech-segments not found; recordings are transcribed without the check
[WARNING] speech check: VAD model missing: /Users/me/Projetos/Pessoal/teams-recorder/data/models/ggml-silero-v5.1.2.bin  → scripts/download-model.sh silero-v5.1.2 (until then recordings are transcribed without the check)
[info] speech check: off ([transcription] speech_check = false)
```

On Windows, the hint names `scripts\download-model.ps1`, as the other model lines do.

## Notification

Sent once per recording with no speech whose audio is 60 s or longer. The daemon shows it as a desktop notification. A `trec transcribe` run has no desktop notifier, so the headless `LogNotifier` logs the same title and body at info level. A CLI run does not show info lines, so there the user sees the `WARNING:` line and the stderr warning instead. If the notifier raises, the warning `no-speech notification for <id> failed: …` is logged, and the transcription still succeeds.

```
No speech in a recording
Meeting 2026-10-17_10-15-32: no speech in 5 min of audio, so it was not transcribed. If it was a meeting, check the capture with `trec doctor`.
```

A shorter recording only logs.

## Files

`data/recordings/<id>/transcript.json` gains `speech` whenever the check ran. It is absent with `speech_check = false`, when the check failed, and on transcripts made before this feature.

A recording with no speech:

```json
{
  "segments": [],
  "language": "pt",
  "speech": {"found": false, "speech_seconds": 0.0, "audio_seconds": 309.6, "segments": 0}
}
```

The transcript has no `health`, `language_detection` or `labels`, and `transcript.txt` has no lines: it holds a single newline, like every transcript file the repository writes.

A recording with speech gets the key next to everything it has today:

```json
"speech": {"found": true, "speech_seconds": 2676.4, "audio_seconds": 3138.0, "segments": 612}
```

When the meeting is analyzed, `analysis.json` has the local empty analysis, as for any transcript with no words today (summary `Empty transcript: no speech recognized.`, no Claude call). The minutes are rendered from it.

## Logs

These lines go to `data/log/daemon.log` when the daemon transcribes, at info level unless marked. In a CLI run, the warnings reach stderr and the info lines are not shown.

```
speech in 2026-10-23_14-00-05: 44.6 of 52.3 min (612 segments)
no speech in 2026-10-17_10-15-32: 0.0 s of speech in 5.2 min of audio (under 2.0 s); whisper skipped, transcript empty   (warning)
speech check of 2026-10-21_09-30-28 failed; transcribing without it: whisper-vad-speech-segments: timed out after 300s   (warning)
language samples of 2026-10-14_15-00-56: 5 of 8 without speech, not sent
no-speech notification for 2026-10-17_10-15-32 failed: <exception>   (warning)
```

## Errors

The check never produces an error the user has to handle. Every failure leaves the meeting transcribed as before this feature, with the warning above and `Speech: not checked (…)`. The failures are:

| Condition | Warning text after `failed; transcribing without it: ` |
|---|---|
| Tool not installed | `whisper-vad-speech-segments: executable not found (whisper-vad-speech-segments)` (the existing `Err.EXECUTABLE_MISSING` wording) |
| Model missing | the existing `Err.MODEL_MISSING` text, naming the path and `scripts/download-model.sh` |
| Timeout (300 s per command) | `whisper-vad-speech-segments: timed out after 300s` |
| Non-zero exit | the existing `Err.STEP_FAILED_CODE` text with the output tail |
| Output not in the expected format | `whisper-vad-speech-segments printed no readable segment list; output tail: …` |

`speech_check` takes any value, like the neighboring flags (`vad`, `retry_vad`). There is no new configuration error.
