# Developer Experience: Detect the meeting's language before transcribing

Public-surface contract for language detection. Companion to `_spec.md` (Part II serves this surface) and `_tests.md` (E2E journeys use these exact invocations). Written as if shipped.

## Golden Path

```
$ git pull && trec agent restart          # with the user's approval: the daemon loads the new code
daemon restarted.

$ trec doctor
…
[ok ] whisper model: /Users/me/Projetos/Pessoal/teams-recorder/data/models/ggml-large-v3-turbo-q5_0.bin
[info] transcription: whisper -mc 0; a transcript is degraded above 10% of its segments in repetition loops
[ok ] retry of a degraded transcript: on (-mc 0 with VAD: /Users/me/Projetos/Pessoal/teams-recorder/data/models/ggml-silero-v5.1.2.bin)
[info] language: detected per meeting among pt, en (fallback pt)
…

# a client meeting in English happens; the daemon records, transcribes and analyzes it

$ trec transcribe 2026-10-23_14-00-05      # (or let the daemon do it; this is the same step by hand)
Transcribing 2026-10-23_14-00-05… ok (412 segments, 52.3 min)
  Health: 1% of segments in repetition loops, text in 52 of 52 min
  Language: en (heard in 11 of 11 counted samples; 11 taken)
  Speakers: 74% of 412 lines labelled (Felipe, John Carter)
  Text: data/recordings/2026-10-23_14-00-05/transcript.txt
Analyze with `trec analyze`.

$ trec status
…
  2026-10-23_14-00-05 Revisão do fluxo de inspeção  [analyzed]  · speakers 74%  · en
  2026-10-23_09-30-11 Daily do time  [analyzed]  · speakers 81%
…
```

`data/recordings/2026-10-23_14-00-05/minutes.md` then opens with these lines (no banner, since the transcript is healthy):

```markdown
# Ata: Revisão do fluxo de inspeção

📅 **Data:** 23/10/2026, 14:00–14:52 (52 min)
🗣️ **Idioma:** inglês
👥 **Participantes:** Felipe, John Carter
```

## Config

`config.toml`, `[transcription]` section (the two keys and their comment, as shipped):

```toml
[transcription]
# whisper.cpp ggml model. "large-v3-turbo-q5_0" (574 MB) has quality close to the full
# large-v3-turbo (1.6 GB). Download it with scripts/download-model.sh.
whisper_model = "large-v3-turbo-q5_0"
# Spoken language of the meetings. "auto" detects it per meeting before transcribing: 30-second
# samples spread over the audio (one per 5 minutes, 3 to 12) go through whisper's language
# identification; a sample counts when it heard one of `languages` with probability 0.5 or more,
# and the language more than half of the counted samples heard (at least 2) is used. Otherwise,
# or if detection fails, the first of `languages`. A code ("pt", "en") fixes the language for
# every meeting and skips the detection (the behavior before 2026-10-21).
language = "auto"
languages = ["pt", "en"]
```

| Key | Default | Observable effect |
|---|---|---|
| `language` | `"auto"` | `"auto"`: each meeting is transcribed in its detected language and `transcript.json` gets `language_detection`. A code: every meeting with `-l <code>`, no detection, no `language_detection` |
| `languages` | `["pt", "en"]` | The only languages detection may choose; the first is the fallback. Validated in both modes, used only when `language` is `"auto"`. A single string is read as a list of one; duplicates are dropped |

## CLI

### `trec transcribe [id]`

One `Language:` line per meeting, after the health block (the `Health:` line and any `WARNING:` lines under it) and before `Speakers:` and `Text:`:

```
Transcribing 2026-10-08_10-30-52… ok (1207 segments, 86.1 min)
  Health: 2% of segments in repetition loops, text in 86 of 86 min
  Language: en (heard in 12 of 12 counted samples; 12 taken)
```

The other forms of the line:

```
  Language: pt (heard in 8 of 8 counted samples; 8 taken)
  Language: pt (fallback: no sample heard pt or en clearly; 8 taken)
  Language: pt (fallback: no majority among 4 counted samples: pt 2, en 2)
  Language: pt (fallback: only one counted sample (en); 2 needed; 3 taken)
  Language: pt (fallback: language detection failed; see the warning above)
  Language: pt (fixed by [transcription] language)
```

When detection fails, the reason is the `language detection of <id> failed; …` warning (Logs below). In a CLI run it reaches stderr as it is logged, so it appears between `Transcribing <id>…` and ` ok (…)`:

```
Transcribing 2026-10-21_09-30-28…language detection of 2026-10-21_09-30-28 failed; transcribing in pt: whisper-cli: timed out after 300s
 ok (530 segments, 38.2 min)
  Health: 0% of segments in repetition loops, text in 38 of 38 min
  Language: pt (fallback: language detection failed; see the warning above)
```

Exit codes are unchanged: 0 when every meeting was transcribed, 1 when one failed. A detection failure is not a transcription failure.

### `trec status`

A meeting whose transcript language is not `pt` gets `  · <code>` after its other markers:

```
  2026-10-08_10-30-52 Revisão da plataforma SPIRE com a MARTA  [analyzed]  · en
```

Portuguese meetings and meetings without a transcript get no language marker.

### `trec doctor`

One informational line right after the `retry of a degraded transcript:` line, so the two loop-guard lines (`transcription:`, `retry …`) stay together; it never fails the doctor:

```
[info] language: detected per meeting among pt, en (fallback pt)
```

```
[info] language: pt for every meeting ([transcription] language)
```

## Files

`data/recordings/<id>/transcript.json` gains `language_detection` when the language was detected (absent with a fixed language and on transcripts made before 2026-10-21). `language` keeps its meaning: the language the transcript was made in.

```json
{
  "language": "en",
  "language_detection": {
    "language": "en",
    "reason": "majority",
    "counted": 3,
    "votes": 3,
    "samples": [
      {"at": 134.7, "language": "en", "p": 0.993},
      {"at": 404.1, "language": "is", "p": 0.965},
      {"at": 673.4, "language": "is", "p": 0.9},
      {"at": 942.8, "language": "en", "p": 0.997},
      {"at": 1212.2, "language": "en", "p": 0.987},
      {"at": 1481.6, "language": "is", "p": 0.946},
      {"at": 1750.9, "language": "is", "p": 0.979},
      {"at": 2020.3, "language": null, "p": 0.0}
    ]
  },
  "health": {"loop_share": 0.03, "...": "..."},
  "segments": [{"start": 0.0, "end": 2.1, "text": "Hello, guys."}]
}
```

`reason` is one of `majority`, `no-usable-sample`, `too-few-votes`, `no-majority`, `detection-failed` (`samples` is empty for the last). `votes` is 0 whenever the reason is not `majority`.

`minutes.md` gets one line after the date line when the transcript language is not `pt` (`en` → `inglês`; another code → the code):

```
📅 **Data:** 08/10/2026, 10:30–11:56 (86 min)
🗣️ **Idioma:** inglês
```

`transcript.txt` is unchanged in format: it holds the text in the language spoken.

## Logs

In `data/log/daemon.log` when the daemon transcribes, at info level unless marked. Only the daemon configures logging. In a CLI run the warnings go to stderr (Python's last-resort handler, shown above under `trec transcribe`) and the info lines are not shown:

```
language of 2026-10-08_10-30-52: en (12 of 12 counted samples; 12 taken)
language of 2026-10-17_10-15-32: pt, the fallback (no-usable-sample; 0 of 3 samples counted)
language detection of 2026-10-17_10-15-32 failed; transcribing in pt: whisper-cli: timed out after 300s   (warning)
language detection of 2026-10-21_09-30-28 failed; transcribing in pt: whisper-cli printed no language for any of the 8 samples; output tail: …   (warning)
```

## Errors

Configuration: `load_settings` raises `ValueError` with the message below, so every `trec` command and the daemon stop with it (exit 1), as for the other invalid keys such as `max_loop_share`:

| Condition | Message |
|---|---|
| `language = "pt-BR"` (not `auto`, not a 2–3 letter lowercase code) | `invalid transcription.language: 'pt-BR'; use "auto" or a language code such as "pt" or "en"` |
| `languages = []`, `["auto"]`, `["PT"]`, `[1]`, whatever `language` is | `invalid transcription.languages: []; use a non-empty list of language codes such as ["pt", "en"]` (the value as written) |

Detection at run time never produces an error the user sees. Every failure becomes the fallback with the reason `detection-failed`, the `Language:` line above and a warning in the log. A code that whisper does not know is only harmless after the first entry. In `languages = ["pt", "xx"]`, detection never chooses `xx`, since whisper never answers it. As the first entry (`["xx", "pt"]`), `xx` is the fallback: every meeting detection cannot decide is sent to whisper as `-l xx` and fails at transcription with whisper's own message in `error.txt`, like a fixed `language = "xx"` (today's behavior for a bad code). The configuration does not check codes against whisper's list.
