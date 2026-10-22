# User Stories: Detect the meeting's language before transcribing

Canonical behavior catalog for language detection. Companion to `_spec.md`; consumed by `_spec.md` Part II (component mapping) and `_tests.md` (coverage matrix). No `_uiux.md`: there is no graphical interface.

## Personas

- **The user**: owner of the Mac and of the recordings. Holds most meetings in Brazilian Portuguese and some in English with clients. Reads transcripts, minutes and the activities document, and wants all of them in Portuguese and faithful to what was said.
- **The operator**: the same person maintaining the install. Needs to see which language a meeting was transcribed in and why, and to pin the language when detection gets it wrong.

## Story Index

| ID | Feature Area | Persona | Story |
|---|---|---|---|
| US-001 | Detection | user | An English meeting is transcribed in English |
| US-002 | Detection | user | A Portuguese meeting is transcribed exactly as today |
| US-003 | Detection | user | A meeting whose language cannot be decided is transcribed in Portuguese |
| US-004 | Analysis | user | Minutes of an English meeting are in Portuguese with literal quotes |
| US-005 | Visibility | operator | `trec transcribe` says which language and why |
| US-006 | Visibility | user | `trec status` and the minutes show a non-Portuguese meeting |
| US-007 | Diagnostics | operator | `trec doctor` shows how the language is chosen |
| US-008 | Configuration | operator | Choose automatic detection, the allowed languages, or a fixed language |

## Detection

### US-001: An English meeting is transcribed in English

**As** the user, **I want** a meeting held in English to be transcribed in English, **so that** its transcript holds what was said instead of a Portuguese translation or a hallucination loop.

Acceptance criteria:

- AC-1: Given `language = "auto"` and `languages = ["pt", "en"]`, when a meeting where most samples hear English with p ≥ 0.5 is transcribed, then whisper runs with `-l en` and `transcript.json` has `"language": "en"` and a `language_detection` object with `"reason": "majority"`.
- AC-2: Given such a meeting whose first pass is degraded, when the anti-loop retry runs, then the retry also runs with `-l en`.
- AC-3: Given the 2026-10-08 MARTA meeting (86 min, English throughout), when its language is detected, then the result is `en` (gate G1).
- AC-4: Given a meeting that the daemon transcribes after recording, when it finishes, then the language was chosen without any action from the user.

Edge cases:

- EC-1: Some samples answer a language that is not allowed (`is`, `gl`) → those samples are recorded and do not count, and the remaining English samples decide (the vans meeting: 3 counted `en` of 8 taken → `en`).
- EC-2: A meeting shorter than 30 s → one sample covering all of it; its answer alone decides when it counts.
- EC-3: A meeting of 2 hours or more → at most 12 samples, spread evenly; detection time stays near 25 s on the development Mac (about 0.6 s plus about 2 s per sample).
- EC-4: The audio file is shorter than the recorded duration (truncated) → samples past the real end get no answer and do not count; the rest decide.
- EC-5: The Teams track was recorded at the wrong sample rate → detection still runs; garbled samples answer non-allowed languages or low probabilities and do not count; the transcript is flagged as today.

### US-002: A Portuguese meeting is transcribed exactly as today

**As** the user, **I want** my Portuguese meetings to be transcribed with today's settings, **so that** the feature cannot make them worse.

Acceptance criteria:

- AC-1: Given `language = "auto"`, when a meeting where most samples hear Portuguese is transcribed, then the whisper transcription command is identical to today's (`-l pt`, same model, `-mc`, VAD and threads).
- AC-2: Given the 25 Portuguese meetings recorded up to 2026-10-21, when their language is detected, then every one in which someone speaks comes out `pt` (gate G1; recordings with only silence or noise are outside the gate, see `_tests.md` › G1).
- AC-3: Given a Portuguese transcript, when it is analyzed, then the message sent to the model is byte-for-byte what it is today (no language line).

Edge cases:

- EC-1: A Portuguese meeting with a few English words or one English sample → `pt` wins by majority; the transcript is Portuguese.
- EC-2: A Portuguese clip answered `es` or `gl` → it does not count; the other samples decide, and with none left the fallback `pt` applies.

### US-003: A meeting whose language cannot be decided is transcribed in Portuguese

**As** the user, **I want** a meeting the detection cannot decide to be transcribed in Portuguese, **so that** detection never leaves me worse off than today.

Acceptance criteria:

- AC-1: Given no sample that hears `pt` or `en` with p ≥ 0.5, when the meeting is transcribed, then it is transcribed in `pt` and the record says `"reason": "no-usable-sample"`.
- AC-2: Given counted samples split so that no language has more than half (for example 2 `en` and 2 `pt`), when the meeting is transcribed, then it is transcribed in `pt` with `"reason": "no-majority"`.
- AC-3: Given whisper-cli or ffmpeg failing, timing out or missing during detection, when the meeting is transcribed, then the transcription still runs in `pt`, the record says `"reason": "detection-failed"`, a warning is logged, and no `error.txt` or notification is produced.

Edge cases:

- EC-1: Exactly one counted sample in a meeting with several samples → it does not decide alone (`min_votes` = 2); fallback `pt`, reason `too-few-votes`.
- EC-2: whisper runs but its output has no recognizable answer line for any sample (a format change) → the detection fails: fallback `pt`, reason `detection-failed`, `trec transcribe` says `see the warning above`, and the warning (on stderr in a CLI run, in `data/log/daemon.log` for the daemon) carries whisper's output tail.
- EC-3: The meeting has no known duration (no end time in `meta.json`) → one sample at the start decides when it counts.
- EC-4: The transcription itself fails after detection → it fails as today (`error.txt`); re-running repeats the detection.

## Analysis

### US-004: Minutes of an English meeting are in Portuguese with literal quotes

**As** the user, **I want** the minutes, actions and activities of an English meeting to be written in Portuguese while quoting what was said, **so that** everything I read is in one language and the evidence is real.

Acceptance criteria:

- AC-1: Given an English transcript, when it is analyzed, then the message to the model carries the line `Transcript language: English`, and every field of the analysis except `evidence` and quotes is in Brazilian Portuguese.
- AC-2: Given an English transcript, when an action's `evidence` or a status update's quote is extracted, then it is the literal English words from the transcript.
- AC-3: Given an English transcript, when the claims are verified, then the verifier's message carries the same language line and its reasons are in Portuguese.
- AC-4: Given an analyzed English meeting, when the curator adds a 💬 sub-line, then the line is in Portuguese and its quote is the English words said.

Edge cases:

- EC-1: An English transcript under 20 words → the analyzer short-circuits as it does today.
- EC-2: A transcript stored before this feature → `language` is `pt`; no language line.
- EC-3: An English meeting without speaker labels, where a participant is greeted once by name ("Hi John", "Thanks, John") → the participant is confirmed, as "oi João" is in a Portuguese meeting, and gets no ⚠️.

## Visibility

### US-005: `trec transcribe` says which language and why

**As** the operator, **I want** `trec transcribe` to print the transcript's language and how it was chosen, **so that** I can tell at once whether detection worked.

Acceptance criteria:

- AC-1: Given a detected language, when `trec transcribe <id>` finishes, then it prints `  Language: en (heard in 3 of 3 counted samples; 8 taken)`.
- AC-2: Given a fallback without usable samples, then it prints `  Language: pt (fallback: no sample heard pt or en clearly; 8 taken)`.
- AC-3: Given a fallback without a majority, then it prints `  Language: pt (fallback: no majority among 4 counted samples: pt 2, en 2)`.
- AC-4: Given a failed detection, then it prints `  Language: pt (fallback: language detection failed; see the warning above)`, and the `language detection of <id> failed; …` warning with the reason is on stderr.
- AC-5: Given a fixed language, then it prints `  Language: pt (fixed by [transcription] language)`.
- AC-6: Given one counted sample among several (too few votes), then it prints `  Language: pt (fallback: only one counted sample (en); 2 needed; 3 taken)`.

Edge cases:

- EC-1: Several meetings transcribed in one run → one `Language:` line per meeting, after that meeting's health block (the `Health:` line and any `WARNING:` lines under it) and before its `Speakers:` and `Text:` lines.

### US-006: `trec status` and the minutes show a non-Portuguese meeting

**As** the user, **I want** meetings held in another language to be marked where I look, **so that** I know why quotes are in English.

Acceptance criteria:

- AC-1: Given a meeting whose transcript language is `en`, when `trec status` runs, then its line ends with `  · en`.
- AC-2: Given a Portuguese meeting, then `trec status` adds no language marker.
- AC-3: Given an English meeting, when its minutes are rendered (`trec analyze` or `trec minutes`), then `minutes.md` has the line `🗣️ **Idioma:** inglês` right after the date line.
- AC-4: Given a Portuguese meeting, then the minutes have no language line.

Edge cases:

- EC-1: A language other than `pt` or `en` (allowed by the user) → `trec status` shows its code, and the minutes show the code (`🗣️ **Idioma:** es`).
- EC-2: `trec minutes --all` on old meetings → no language line (their transcripts are `pt`).

## Diagnostics

### US-007: `trec doctor` shows how the language is chosen

**As** the operator, **I want** `trec doctor` to show the language mode, **so that** I can confirm the configuration in effect.

Acceptance criteria:

- AC-1: Given `language = "auto"`, then `trec doctor` prints `[info] language: detected per meeting among pt, en (fallback pt)`.
- AC-2: Given `language = "pt"`, then it prints `[info] language: pt for every meeting ([transcription] language)`.
- AC-3: The language line never makes `trec doctor` fail.
- AC-4: The language line comes right after the `retry of a degraded transcript:` line.

## Configuration

### US-008: Choose automatic detection, the allowed languages, or a fixed language

**As** the operator, **I want** to choose between automatic detection among allowed languages and a fixed language, **so that** I can correct a wrong detection or restore the old behavior.

Acceptance criteria:

- AC-1: Given no `language` key, then the language is detected (`auto`) among `["pt", "en"]`.
- AC-2: Given `language = "en"`, then every meeting is transcribed with `-l en`, nothing is detected, and the transcript has no `language_detection`.
- AC-3: Given `languages = ["en", "pt"]`, then the fallback is `en`.
- AC-4: Given `language = "pt"` and a re-run of `trec transcribe <id>` on a meeting that was detected wrong, then the meeting is re-transcribed in Portuguese.
- AC-5: Given transcripts written before this feature, when they are loaded, read by the analysis, rendered or listed, then they behave exactly as before.

Edge cases:

- EC-1: `language = "Portuguese"` or `language = "pt-BR"` → configuration load fails with `invalid transcription.language: 'pt-BR'; use "auto" or a language code such as "pt" or "en"`.
- EC-2: `languages = []` or `languages = ["auto"]` → configuration load fails with `invalid transcription.languages: []; use a non-empty list of language codes such as ["pt", "en"]` (the value as written).
- EC-3: `languages = "en"` (no brackets) → accepted as `["en"]`.
- EC-4: `languages = ["pt", "en", "pt"]` → `["pt", "en"]`.
- EC-5: `language = "pt"` with a valid `languages` → `languages` is not used. With an invalid one (`languages = []`) → configuration load fails with the EC-2 message, as in `"auto"` mode.
