# Spec: Detect the meeting's language before transcribing

> Slug `language-detection` · Date 2026-10-21 · Status: approved by the user on 2026-10-21, after review rounds 1–4 (`reviews-001/` to `reviews-004/`; the four fixes of round 4 are `valid`, not yet verified by a reviewer)
> Evidence: §"Evidence (2026-10-21)" below (language detection run on 30-second samples of four real meetings, and the 2026-10-14 meeting re-transcribed in English)
> Companions: [user stories](_user_stories.md) · [developer experience](_dx.md) · [tests](_tests.md) · [ADR-001](adrs/adr-001.md)

---

# Part I — Product

## Overview

- **Motivating Problem**: the transcriber is pinned to Portuguese (`[transcription] language = "pt"`), so a meeting held in English comes out as Portuguese text that was never said: whisper translates or hallucinates. Two of the 27 recorded meetings were held in English. The 86-minute MARTA client review (2026-10-08) was transcribed as Portuguese. The 37-minute vans meeting (2026-10-14) still has 69% of its lines in a repetition loop after the anti-loop retry ("Apenas a gente vai ver a sua vida"). Their analyses, minutes and activities rest on that text. The simplest end-to-end behavior that solves it: before transcribing, the app listens to samples spread over the meeting, decides whether it was held in Portuguese or English, and transcribes it in that language. An English meeting then gets an English transcript, and its minutes are still written in Portuguese from it.
- **Who it is for**: the single user of teams-recorder, whose meetings are mostly in Brazilian Portuguese and sometimes in English with a client.
- **Why it is valuable**: an English meeting becomes usable (real words, no loops), while Portuguese meetings are transcribed exactly as today. Nothing leaves the Mac and nothing needs to be set per meeting.

## Goals

- After this ships, an English meeting is transcribed in English without the user changing the configuration or re-running anything.
- A Portuguese meeting is transcribed with the same whisper command as today: the detection only decides the language and never changes the decoding settings.
- The detection never blocks or fails a transcription: when it cannot decide, or cannot run, the meeting is transcribed in Portuguese as today, and the reason is recorded.
- Minutes, actions, decisions and activities stay in Brazilian Portuguese whatever language the meeting was held in. Quotes keep the words that were said.
- The user can see which language each transcript was made in and why: in `trec transcribe`, `trec status`, `transcript.json` and the minutes. `trec doctor` shows how the language is chosen.

## User Stories

- US-001 to US-003: the language is detected and used for the transcription (English meetings, Portuguese meetings, undecidable audio).
- US-004: the analysis of an English transcript stays in Portuguese with literal quotes.
- US-005 to US-007: visibility (`trec transcribe`, `trec status`, the minutes) and diagnostics (`trec doctor`).
- US-008: configuration (automatic, fixed, allowed languages) and compatibility with existing transcripts.
- [Full user stories](_user_stories.md)

## Core Features

- **Language detection.** Before whisper transcribes a meeting, short samples of its audio are taken at regular intervals across the whole recording. Whisper's language identification runs on each sample, and the samples' answers are combined into one language for the meeting. Requirements: samples are spread across the meeting, not taken only from its start; only the allowed languages count; a sample whose answer is not confident does not count; the result and the evidence for it are kept with the transcript.
- **Transcription in the detected language.** The transcription runs, and the anti-loop retry when there is one, in the chosen language. Every other transcription setting stays as it is (model, `-mc 0`, VAD, health check, speaker labels).
- **Analysis across languages.** The analysis and the claim verification are told when the transcript is not in Portuguese. The activities curator's prompt gains a rule that holds for every meeting: a quote keeps the words said, in the language they were said in. All three keep writing in Brazilian Portuguese and quote the transcript literally. The verifier's participant check recognises an English greeting ("Hi John", "Thanks, John") as it recognises "oi João".
- **Visibility and configuration.** `trec transcribe` prints the language and the reason. `trec status` marks meetings that were not transcribed in Portuguese. The minutes name the meeting's language when it is not Portuguese. `trec doctor` shows the mode. `config.toml` chooses between automatic detection among allowed languages and a fixed language.

Interaction: detection feeds the language to the transcription. The transcript carries the language and the detection record. The analysis, the verifier, the curator, the minutes and the CLI read them from the transcript.

## Business Rules

- **Modes.** With `[transcription] language = "auto"` (the new default), each meeting's language is detected among `[transcription] languages` (default `["pt", "en"]`). With a language code (`"pt"`, `"en"`, …), every meeting is transcribed in that language and nothing is detected, as before this feature.
- **Fallback.** The fallback language is the first entry of `languages` (`pt` by default). A meeting whose language cannot be decided is transcribed in the fallback.
- **Samples.** A sample is 30 seconds of the meeting's audio (whisper identifies a language from one 30-second window). The number of samples is one per 5 minutes of meeting, rounded up, with at least 3 and at most 12. It is never more than the number of whole 30-second windows the meeting holds, and never fewer than 1. Samples are spread evenly: sample *i* of *n* starts at `(duration − 30) × (i + ½) / n` seconds, so none sits at the very first or very last second. A meeting shorter than 30 seconds gets one sample from its start that covers all of it. A meeting whose length is unknown gets one sample at its start.
- **Counted samples.** A sample counts only when whisper's answer is one of the allowed languages with a probability of at least 0.5. The floor discards weak answers; it does not separate silence or noise from speech, since whisper answers those `en` with probabilities that overlap real speech (Evidence). Any other answer (a language not allowed, such as `is` or `gl`; a low probability; no answer) is kept in the record and does not count.
- **Decision.** A language wins when more than half of the counted samples heard it and at least 2 of them did. When the meeting has a single sample, 1 is enough. The winner can be any allowed language, the fallback included. Otherwise the meeting is transcribed in the fallback, with one of three reasons. `no usable sample`: nothing counted. `too few votes`: one sample counted, in a meeting with more than one sample. `no majority`: no language reached more than half.
- **Fail-soft.** When detection cannot run (whisper or ffmpeg missing, a timeout, an error exit, or whisper running without printing a single recognizable answer), the meeting is transcribed in the fallback with the reason `detection failed`, and the failure is logged. Detection never writes `error.txt`, never fails the transcription and never sends a notification.
- **Same decoding.** The chosen language replaces only whisper's `-l` value. The first pass and the anti-loop retry use the same language. The model, `-mc`, VAD, threads, the health check, the retry rule and speaker labelling are unchanged.
- **One language per meeting.** A meeting is transcribed in a single language (user decision, 2026-10-21: mixed-language meetings are rare). In a meeting that mixes both, the minority language's speech comes out translated into the winner.
- **Record.** The transcript keeps the language it was made in and, when detection ran, the detection record: the language, the reason, how many samples counted, how many voted for the winner, and every sample (start time, answer, probability). A transcript made with a fixed language has no detection record.
- **Output language.** The analysis, the verifier's reasons, the curator's document and the story drafts stay in Brazilian Portuguese. A literal quote (`evidence`, a status update's quote, a 💬 line's quote) keeps the transcript's words and is never translated.
- **What the model is told.** When the transcript language is not Portuguese, the analyzer's and the verifier's messages say so in one header line naming the language. A Portuguese transcript's user message is byte-for-byte what it is today. The system prompts are not: the analyzer's, the verifier's and the curator's change for every meeting (the wording for non-Portuguese transcripts and the quote exception), so gate G3 re-measures Portuguese output before the change ships.
- **Existing transcripts** load unchanged. Their language is whatever they stored (`pt` for all 27 today), and they have no detection record. Nothing is re-transcribed automatically.
- **Validation.** `language` must be `"auto"` or a lowercase code of 2 or 3 letters. `languages` must be a non-empty list of such codes (a single code is accepted as a list of one). Duplicates are dropped and the first occurrence keeps its place. `"auto"` is not a code. An invalid value stops the program at configuration load with a message naming the key, like every other invalid key. `languages` is validated in both modes, so a typo surfaces before the user switches to `"auto"`, and it is used only when `language` is `"auto"`.

## User Experience

- **Persona: the user.** Journey: after the update and a daemon restart, nothing changes for a Portuguese meeting. After an English meeting, the transcript is in English, the minutes are in Portuguese with a line naming the meeting's language, and the activities document gets its items in Portuguese. To see what happened: `trec transcribe <id>` prints `Language: en (…)`, and `trec status` marks the meeting `· en`.
- **Persona: the operator** (the same person maintaining the install). Journey: `trec doctor` shows `language: detected per meeting among pt, en (fallback pt)`. When a meeting came out in the wrong language, `transcript.json` holds the samples and their answers. The fix is `language = "pt"` (or `"en"`) in `config.toml` and `trec transcribe <id>`.
- Discoverability: the comment on the two keys in `config.toml`, the configuration and transcription guides, and the `trec doctor` line.
- Accessibility: no graphical interface; CLI output and Markdown only.

## High-Level Technical Constraints

- Local only: detection uses the whisper model already installed (`large-v3-turbo-q5_0`) and ffmpeg. No new model, no network, no new dependency.
- Performance from the user's view: detection adds about 25 seconds per meeting on the development Mac (M1), for the 12 samples of a meeting of an hour or more, to a transcription that takes minutes. Measured: about 0.6 s to load the model once, plus about 2 s of encoder time per sample (3 samples in one call: 7 s). Windows (CPU-only whisper) is unmeasured.
- Platform: macOS and Windows use the same whisper CLI. Windows remains untested on real hardware.
- Compatibility: the repository's `config.toml` switches to `language = "auto"`. A config that pins a code keeps today's behavior exactly.

## Non-Goals (Out of Scope)

- Detecting the language per stretch of a meeting and transcribing each stretch in its own language: user decision of 2026-10-21 (mixed meetings are rare). The design leaves room for it (ADR-001).
- Languages beyond Portuguese and English by default. Other codes can be added to `languages` by the user; they are not evaluated in this delivery.
- Translating an English transcript into Portuguese. The transcript stays in the language spoken; only the LLM output is Portuguese.
- Re-transcribing or re-analyzing existing meetings automatically (see Open Questions).
- Changing the whisper model, VAD defaults or the loop guard.

## Open Questions

- **Short backchannels in the loop guard.** The English retry of the vans meeting has 10.4% of its segments in "loops", all natural "Okay." lines, just above the 10% threshold, so it stays marked degraded. Whether to exempt very short lines from the loop rule is decided after gate G2 measures the MARTA meeting. It is not part of this delivery.
- **Backfill of the two English meetings** (2026-10-08 MARTA and 2026-10-14 vans). Re-running `trec transcribe <id>` and `trec analyze <id>` on them fixes their transcripts and minutes. But re-analysis spends the Claude Code subscription and runs a curator pass that may add or change items in `atividades.md`. The user decides after slice 1 ships. Their audio is deleted by the 30-day retention after 2026-11-07 and 2026-11-13. The daily purge does not take the meeting lock (Key Decisions), so a backfill should run well before those dates.

---

# Part II — Technical

## Executive Summary

A new port, `LanguageDetector`, runs before the transcription in `TranscribeMeeting`. Its whisper.cpp adapter cuts the sample windows out of `audio.m4a` with ffmpeg and passes all of them to a single `whisper-cli -l auto -dl` call: whisper.cpp accepts several `-f` files and loads the model once. It then parses the `auto-detected language: xx (p = 0.97)` line printed for each file. Choosing the sample offsets and the winning language is pure domain code (`domain/language.py`, thresholds in `LanguageRules`). The chosen language goes to the existing `Transcriber.transcribe(audio, language)` for the first pass and for the retry. The detection record travels on the `Transcript` (new optional field), so the CLI, the minutes, the analyzer and the verifier read it without new port parameters. Everything is additive. Old transcripts load unchanged, a fixed `language` skips the detector entirely, and any detection failure falls back to the first allowed language with a log line.

The evidence that shaped the design: whisper's own `-l auto` decides from the first 30 seconds only, and on degraded audio it answered `is` (Icelandic) with p = 0.97. So detection samples the whole meeting and counts only allowed languages (ADR-001).

## Evidence (2026-10-21)

Language detection (`whisper-cli -l auto -dl`, `large-v3-turbo-q5_0`, M1) on 30-second clips of real meetings in `data/recordings/` (read-only; clips in a scratch directory):

| Meeting | Length | Answers | Today's transcript |
|---|---|---|---|
| 2026-10-08_10-30-52 (MARTA review) | 86 min | `en` in 12 of 12 clips (p 0.65–0.9998) | `pt`, translated text |
| 2026-10-14_15-00-56 (vans) | 37 min | `en` in 3 (p ≥ 0.987), `is` in 5 (p 0.90–0.98) | `pt`, 69% of lines in loops after the retry |
| 2026-10-21_09-30-28 | 38 min | `pt` in 8 of 8 (p ≥ 0.99) | `pt` |
| 2026-10-13_09-18-44 | 23 min | `pt` in 7 of 7 (p ≥ 0.998) | `pt` |

- The `is` clips of the vans meeting are English speech on loud, clipped audio (mean −20 dB, peak 0 dB). Transcribed with `-l en`, the clip at 15:00 reads "When you select another type of van, you need to select a zone". This is why non-allowed answers are discarded rather than trusted.
- `-np` (no prints) suppresses the `auto-detected language` line. The detection command must not pass it.
- Several `-f` in one call: 3 clips in 7.1 s, against about 2.9 s for a call with one clip. whisper's own timings for the 3-clip call: load 0.56 s, encoder 2.06 s per clip. So the cost grows with the number of samples, not with the model load.
- The vans meeting re-transcribed in English on a scratch copy, measured with `domain.health.transcript_health` (max_loop_share 0.10, 37 min), as the pipeline would run it:

  | Pass | Loops | Minutes with text | Notes |
  |---|---|---|---|
  | Stored `pt` (first pass + retry) | 69% | 35 of 37 | "Apenas a gente vai ver a sua vida." 177 times |
  | `en` first pass (`-mc 0`), 6.7 min | 69% | 32 of 37 | Real sentences in places; "I'm a little bit more than a day." 112 times |
  | `en` retry (`-mc 0` + VAD), 1.5 min | 10.4% | 35 of 37 | Coherent throughout ("if you select a van and then you select a mobility or reach, okay, there's no problem"); the top repeat is "Okay." (9 times); `is_healthier_than` keeps it over the first pass |

  With detection, the existing retry rescues this meeting: 69% → 10.4%. The retry still sits just above the 10% threshold because of natural "Okay." lines, so the transcript stays marked degraded (see Known Risks).
- Silence and noise (2026-10-22, 30-second generated clips, one `-dl` call): silence → `en` p = 0.38; pink noise at amplitude 0.01 → `en` p = 0.48; brown noise at amplitude 0.05 → `en` p = 0.51. whisper's guess without speech is `en`, an allowed language, so the allow-list does not discard it. On real recordings without speech the guesses are higher: gate G1 measured `en` p = 0.61 on 10.9 s of near silence (2026-10-08_02-50-26) and p = 0.68, 0.63, 0.49 on 5 minutes of noise (2026-10-17_10-15-32), while the lowest probability on real English speech is 0.647 (MARTA, at 30:00). No probability floor separates the two. Recordings without speech are left to the separate speech-check spec (Silero VAD before the vote), decided by the user on 2026-10-22; the floor stays 0.5.
- whisper's own `-l auto` decides once per file (2026-10-22, 60-second files made from two real 30-second clips): `pt`+`en` gave one `pt` answer and the English half came out in English; `en`+`pt` gave one `en` answer and the Portuguese half came out as "What? What? What?". A Portuguese meeting whose first 30 s are silence would therefore be transcribed under `en` and lose its speech (ADR-001, Alternative 1).

## MVP Boundary

MVP = tasks 1–4 of the breakdown: domain and config; the adapter; the use case and wiring; the analyzer, verifier and curator prompts, with the participant check's English greetings. Slice 1 solves the Motivating Problem: an English meeting is transcribed in English and analyzed in Portuguese, and a Portuguese meeting is transcribed as today. Post-MVP, in this spec: the CLI, status, doctor and minutes lines (task 5); the evaluation gates on the real meetings and the documentation (task 6). Out of scope: per-stretch languages, automatic backfill.

## Developer Experience

- [Developer experience contract](_dx.md): the two `[transcription]` keys; the `trec transcribe`, `trec status` and `trec doctor` lines; the `language_detection` object in `transcript.json`; the minutes line; the log lines; the error surface.
- No `_uiux.md`: the product has no graphical interface.

## System Architecture

```
audio.m4a ─► sample_offsets(duration, rules) ─► LanguageDetector.detect(audio, offsets, 30 s)
                                                  │  ffmpeg: one 16 kHz WAV per offset (temp dir)
                                                  │  whisper-cli -l auto -dl -f c0.wav … -f cN.wav  (model loaded once)
                                                  ▼
                                   [LanguageSample(at, language, p), …]
                                                  │
                         choose_language(samples, allowed, fallback, rules) ─► LanguageDetection(language, reason, …)
                                                  │
           Transcriber.transcribe(audio, language)  (first pass, and the retry when degraded)
                                                  │
     Transcript(language, language_detection, health, labels…) ─► transcript.json / transcript.txt
                                                  │
   analyzer / verifier header line (non-pt) · curator excerpts · minutes line · trec transcribe / status
```

- `domain/language.py` (new, pure): `LanguageRules`, `LanguageSample`, `LanguageReason`, `LanguageDetection`, `sample_offsets`, `choose_language`.
- `application/ports.py`: `LanguageDetector` protocol.
- `adapters/outbound/language_whispercpp.py` (new): `WhisperCppLanguageDetector`.
- `application/use_cases/processing.py`: `TranscribeMeeting` gains the detection step.
- `container.py`: a new `Container.language_detector` field (the name `detector` is the Teams call detector), built by `build_language_detector(settings)` when `settings.detects_language`, else None; `transcribe_meeting()` passes it with `settings.fallback_language` and `settings.languages`.
- `adapters/outbound/codec.py`: `language_detection` to and from JSON.
- `adapters/outbound/llm_schema.py`, `verifier_claude.py`: the header line. `prompts/analyze_system.md`, `prompts/verify_system.md`, `prompts/curate_system.md`: wording. `constants.Verify.ADDRESS`: English greetings.
- `adapters/outbound/minutes_markdown.py`, `adapters/inbound/cli.py`: the lines users see.

## Architectural Boundaries

- `domain/language.py` imports only the standard library and `domain` modules. No I/O.
- The adapter imports `domain`, `constants`, `messages` and `process_control` (`NO_WINDOW`), like `transcriber_whispercpp`. It does not import the transcriber's module: the two share only `Bin`, `Audio` and `Proc` constants. It spawns processes through `subprocess.run` with `creationflags=NO_WINDOW`, as the transcriber does.
- `TranscribeMeeting` depends on the `LanguageDetector` protocol only. `container.py` (the composition root) is the only place that instantiates `WhisperCppLanguageDetector`.
- No new package. Import direction stays `domain ← application ← adapters/container`.

## Implementation Design

### Core Interfaces

```python
# domain/language.py
@dataclass(frozen=True)
class LanguageRules:
    """Thresholds of the language detection; fixed constants in this delivery (changing one is a code change)."""
    window_seconds: float = 30.0     # one sample = whisper's identification window
    every_seconds: float = 300.0     # one sample per 5 minutes of meeting
    min_samples: int = 3
    max_samples: int = 12
    min_probability: float = 0.5     # a sample under this does not count
    min_votes: int = 2               # the winner needs this many counted samples (1 when the meeting has one sample)


@dataclass(frozen=True)
class LanguageSample:
    at: float                        # start of the sample, seconds into the audio
    language: str | None             # whisper's answer; None: no answer for this sample
    probability: float = 0.0


class LanguageReason(StrEnum):
    MAJORITY = "majority"                    # more than half of the counted samples, and at least min_votes
    NO_USABLE_SAMPLE = "no-usable-sample"    # no sample heard an allowed language confidently
    TOO_FEW_VOTES = "too-few-votes"          # one sample counted, in a meeting with more than one sample
    NO_MAJORITY = "no-majority"
    DETECTION_FAILED = "detection-failed"    # the detector raised (it could not run, or whisper printed no answer); the samples are empty


@dataclass(frozen=True)
class LanguageDetection:
    language: str                            # the language the transcript was made in
    reason: LanguageReason
    counted: int = 0                         # samples that heard an allowed language with p >= min_probability
    votes: int = 0                           # counted samples that heard `language` (0 whenever the reason is not MAJORITY)
    samples: tuple[LanguageSample, ...] = ()

    @property
    def detected(self) -> bool:
        return self.reason is LanguageReason.MAJORITY


def sample_offsets(duration: float | None, rules: LanguageRules = LanguageRules()) -> list[float]: ...
def choose_language(samples: Sequence[LanguageSample], allowed: Sequence[str], fallback: str,
                    rules: LanguageRules = LanguageRules()) -> LanguageDetection: ...
def counted_tally(detection: LanguageDetection, allowed: Sequence[str], rules: LanguageRules = LanguageRules()) -> dict[str, int]:
    """Counted samples per allowed language, in `allowed` order (for the `no majority` and `too few votes` CLI lines)."""
```

```python
# application/ports.py
@runtime_checkable
class LanguageDetector(Protocol):
    def detect(self, audio: Path, offsets: Sequence[float], window_seconds: float) -> list[LanguageSample]:
        """One sample per offset, in order. A sample whisper gave no answer for has language None.
        Raises TranscriptionError when the detection could not run at all."""
        ...
```

```python
# application/use_cases/processing.py (additions)
@dataclass
class TranscribeMeeting:
    ...
    language: str = Audio.DEFAULT_LANGUAGE        # whisper's language without a detector; the fallback with one. Never "auto"
    language_detector: LanguageDetector | None = None   # None: [transcription] language is a code, nothing is detected
    languages: tuple[str, ...] = Transcription.LANGUAGES   # the languages detection may choose (the vote's allow-list)
    language_rules: LanguageRules = LanguageRules()

    def __post_init__(self) -> None:
        """Raises ValueError when `language` is not a code (`"auto"` included): whisper must never get `-l auto`."""

    def _language(self, meeting_id: str, audio: Path, duration: float | None) -> LanguageDetection | None:
        """None without a detector. Any detector failure: `self.language`, reason DETECTION_FAILED, logged."""
```

`self.language` is the only source of the fallback: `_language` passes it to `choose_language` as `fallback` and uses it for `DETECTION_FAILED`. `languages` is only the allow-list. `Container.transcribe_meeting()` passes `language=settings.fallback_language` (never `settings.language`, which is `"auto"` in detection mode), `languages=settings.languages` and `language_detector=self.language_detector`.

`execute` calls `_language` after `_rate_mismatch` and before `_transcribe`, inside the meeting lock like the transcription. `_transcribe` and `_checked` take the language as a parameter, replacing `self.language`. `_checked` sets `transcript.language = language`, because whisper's `result.language` echoes the forced code anyway. `execute` sets `transcript.language_detection = detection` before `_label` and `save_transcript`.

```python
# adapters/outbound/language_whispercpp.py
class WhisperCppLanguageDetector:
    def __init__(self, model_path: Path, whisper_cli: str = Bin.WHISPER_CLI, ffmpeg: str = Bin.FFMPEG,
                 threads: int = 0, timeout: float = Proc.LANGUAGE_DETECT_TIMEOUT) -> None: ...
    def clip_command(self, audio: Path, offset: float, window: float, wav: Path) -> list[str]:
        # ffmpeg -hide_banner -loglevel error -nostdin -y -ss <offset> -t <window> -i <audio> -ac 1 -ar 16000 -c:a pcm_s16le <wav>
    def detect_command(self, wavs: Sequence[Path]) -> list[str]:
        # whisper-cli -m <model> -l auto -dl -t <threads> -f <wav0> … -f <wavN>   (never -np: it hides the answer line)
    def detect(self, audio: Path, offsets: Sequence[float], window_seconds: float) -> list[LanguageSample]: ...


def parse_detection(output: str, wavs: Sequence[Path]) -> list[tuple[str | None, float]]:
    """Answers per wav, in order, from whisper-cli's combined stdout+stderr: each `processing '<path>' (` line opens a file,
    identified by its basename (`c<i>.wav`, a name the adapter chose), and the next `auto-detected language: <code> (p = <float>)`
    line answers it; a file with no answer gets (None, 0.0)."""
```

- The clips go to a `tempfile.TemporaryDirectory(prefix="trec-lang-")`. A clip whose WAV holds less than 1 second of audio (an offset past the real end of a truncated file) is left out of the whisper call, and its sample is `None`. When no clip is usable, the result is all `None` and whisper is not called.
- The clips are named `c0.wav … c<n-1>.wav` after their offset's index. Answers are bound to files by that basename, never by position or by the full path. A temporary directory can contain an apostrophe (on Windows, `C:\Users\O'Brien\AppData\Local\Temp`), which would cut a pattern that stops at the first quote.
- Errors become `TranscriptionError` with `Err` messages: model missing, executable missing, timeout, non-zero exit (stderr tail), and `Err.WHISPER_NO_LANGUAGE` (`"whisper-cli printed no language for any of the {count} samples; output tail: {tail}"`) when whisper exited 0 on at least one clip and no answer line matched any of them (a format change after an upgrade). Some clips without an answer while others have one is not an error: those samples are `None`. The use case catches every exception from `detect` (a `noqa: BLE001` with the reason, as the retry does) and logs `LANGUAGE_DETECTION_FAILED` with the meeting id and the exception, whose message carries the output tail. Detection is advisory.
- `detect_command` passes the clips' full temporary paths, as `transcriber_whispercpp.whisper_command` passes `str(wav)`; the pattern accepts a bare name too, in case a future whisper prints only the file name.
- Regexes in `constants.Parse`: `WHISPER_PROCESSING = r"processing '(?:.*[\\/])?(c\d+\.wav)' \("` and `WHISPER_LANGUAGE = r"auto-detected language: ([a-z]+) \(p = ([0-9.]+)\)"`, matched line by line.

### Data Models

`Transcript` gains one field, and `transcript.json` one optional object written only when the field is not None:

| Field | Type | Purpose |
|---|---|---|
| `Transcript.language_detection` | `LanguageDetection \| None`, default None | How the language was chosen; None with a fixed language and on transcripts made before this feature |
| `language_detection.language` | `str` | The language the transcript was made in (equal to `Transcript.language`) |
| `language_detection.reason` | `LanguageReason` value | `majority`, `no-usable-sample`, `too-few-votes`, `no-majority`, `detection-failed` |
| `language_detection.counted` | `int ≥ 0` | Samples that heard an allowed language with p ≥ 0.5 |
| `language_detection.votes` | `int ≥ 0` | Counted samples that heard the winner; 0 whenever the reason is not `majority` |
| `language_detection.samples[]` | list of `{at: float, language: str \| null, p: float}` | Every sample taken, in order, the discarded ones included |

Storage: JSON inside `transcript.json`, not a side table or a separate file. The record is opaque evidence: nothing queries it across meetings, it is always read together with its transcript, and it must be deleted with it. This matches how `health` and the `speakers` summary are stored. Shape (samples abridged):

```json
"language_detection": {
  "language": "en", "reason": "majority", "counted": 3, "votes": 3,
  "samples": [{"at": 134.7, "language": "en", "p": 0.993}, {"at": 404.1, "language": "is", "p": 0.965}, {"at": 2020.3, "language": null, "p": 0.0}]
}
```

`codec.transcript_from_dict` reads it when present and leaves it None otherwise. `language` keeps its place and meaning. The decoder checks the object and each sample with `isinstance(…, dict)` before reading them, raising `TypeError(Err.BAD_LANGUAGE_DETECTION.format(value=…))` (`"the language detection must be an object with a list of sample objects, not {value!r}"`, a detail inside `BAD_JSON`), as `transcript_from_dict` does for `speakers`. An unknown `reason` raises `ValueError` from `LanguageReason(…)`. The codec itself raises no `RepositoryError`: `FsMeetingRepository._decode` turns `KeyError`, `TypeError` and `ValueError` into `RepositoryError(Err.BAD_JSON…)` naming the file, and deliberately lets `AttributeError` through (`repository_fs.py:58-73`). So a decoder that called `.get` on a value it had not checked would crash `trec status` instead of reporting the file.

Config keys (`[transcription]`):

- `language STR = "auto"`: `"auto"` detects per meeting, a code fixes it. The code default changes from `"pt"` to `"auto"`, and the repository's `config.toml` changes with it.
- `languages LIST[STR] = ["pt", "en"]`: the allowed languages, fallback first.

`Settings`: `language: str` (now `"auto"` or a code), plus `languages: tuple[str, ...] = Transcription.LANGUAGES`, and the properties `detects_language` (`language == Transcription.AUTO`) and `fallback_language` (`languages[0]` when detecting, else `language`).

Language names live with the other user-facing and model-facing text, not in `constants.py`: `messages.Prompt.LANGUAGE_NAMES = {"pt": "Portuguese", "en": "English"}` for the header line (another code: the code itself), and `messages.Minutes.LANGUAGE_NAMES = {"en": "inglês"}` for the minutes line (another code: the code; `pt`: no line). `LanguageReason` values contain no space, so `test_no_hardcoded_strings.py` does not flag them, like `SpeakerReason`.

Constants: `Transcription.AUTO = "auto"`, `Transcription.LANGUAGES = ("pt", "en")`, `Transcription.LANGUAGE_CODE = r"^[a-z]{2,3}$"`, `Proc.LANGUAGE_DETECT_TIMEOUT = 300.0`. `Audio.DEFAULT_LANGUAGE = "pt"` stays: it is the language of transcripts that stored none, and the `Transcript` default.

### API Endpoints

Not applicable: no HTTP surface.

## Integration Points

- **whisper.cpp `whisper-cli`** (Homebrew 1.9.4 on the dev Mac; bundled on Windows): `-l auto -dl` with several `-f`. The answer line format is version-dependent. Output with no recognizable answer line raises `Err.WHISPER_NO_LANGUAGE`, which means the fallback with the reason `detection failed`, `trec transcribe` saying `see the warning above`, and a warning log that carries the whisper output's tail (in `data/log/daemon.log` for the daemon, on stderr for a CLI run: Monitoring and Observability). The slow real-whisper test (IT-004) catches a format change on upgrade.
- **ffmpeg**: `-ss` before `-i` (fast seek) on the M4A, one process per clip (about 0.1 s each).

## Impact Analysis

| Component | Impact Type | Description and Risk | Required Action |
|---|---|---|---|
| `domain/language.py` | new | Pure offsets and vote; low risk | UT-001–UT-012c |
| `domain/models.Transcript` | modified | New optional field; old transcripts unaffected | codec round-trip tests |
| `application/ports.py` | modified | New `LanguageDetector` protocol | fake in `tests/fakes` |
| `adapters/outbound/language_whispercpp.py` | new | Subprocess adapter; output format is whisper-version-dependent (medium) | scripted fake CLI + slow real test |
| `TranscribeMeeting` | modified | Detection step; language passed to both passes; fail-soft; `__post_init__` refuses `"auto"` as `language` | use-case tests on fakes |
| `container.py` | modified | `language_detector` field built only in `auto` mode; `transcribe_meeting()` passes `settings.fallback_language`, not `settings.language` (risk: high if missed, since whisper would get `-l auto`) | UT-040, UT-044 |
| `config.py`, `config.toml` | modified | Default becomes `auto`; validation of two keys | config tests; comment in `config.toml` |
| `codec.py` | modified | Optional `language_detection` object | round-trip, absent, damaged |
| `llm_schema.build_user_message`, `verifier_claude.user_message` | modified | One header line for non-pt transcripts; pt message unchanged byte for byte | message tests |
| `prompts/analyze_system.md`, `verify_system.md` | modified | Wording for English transcripts. The system prompt is part of every request, so every Portuguese analysis and verification sees the changed text; only the user message stays byte-identical. Risk: Portuguese analyses drift (low, since the added sentences are conditioned on the language header line, but measured: gate G3) | prompt read by tests (UT-053); gate G3 |
| `prompts/curate_system.md` (lines 1, 34, 43, 281) and `messages.Prompt.CURATE_TASK` step 7 | modified | Today every curator pass ends with "7. Write all content in Brazilian Portuguese." (`messages.py:684-693`), and the prompt says the same at lines 1, 34 and 281, with no exception for quotes: an English meeting's 💬 quote would be translated. Step 7 becomes "Write all content in Brazilian Portuguese, except quotes: a quote keeps the words said, in the language they were said in."; line 1 says meetings are usually, not always, held in Brazilian Portuguese; lines 34, 43 and 281 carry the same exception. The curator gets no header line, so this rule is unconditional: every pass, Portuguese meetings included, sees the changed sentence. Risk low, since a Portuguese quote is already literal, but measured: gate G3 | UT-053 asserts on `Prompt.CURATE_TASK` and the four prompt lines; gate G3 |
| `constants.Verify.ADDRESS` (`constants.py:244-247`) and its docstring | modified | The participant check (`domain/verification.participant_heard`, `verification.py:135-164`) confirms someone addressed by name only after a Portuguese greeting (`bom dia`, `obrigado`, `oi`, …) or before a comma. An English meeting without observer data (Windows, `[speakers] enabled = false`, a backfill) would get more ⚠️ on participants. The greeting group gains `hi`, `hello`, `hey`, `thanks` and `thank you` (lowercase, no accents, like the others); the docstring says the patterns cover Portuguese and English. A Portuguese transcript rarely contains these words, so its results do not change | UT-054 in `tests/unit/test_verification.py` |
| `MinutesRenderer` port, `minutes_markdown`, `AnalyzeMeeting`, `RenderMinutes`, `FakeMinutesRenderer` | modified | `render(…, language=None)` keyword; a line when not pt. `AnalyzeMeeting` passes `transcript.language`. `RenderMinutes` keeps the transcript it already loads for `health` and passes its `language`, and `None` when there is no transcript. `FakeMinutesRenderer.render` (`tests/fakes/__init__.py:432-437`) gains the keyword and records it in `languages`, or every use-case test that uses it raises `TypeError` | renderer tests; UT-073 on the fake's recorded `language` for both use cases |
| `cli.py` (`transcribe`, `status`, `doctor`) | modified | New lines | CLI tests |
| `scripts/wiki_corpus.py`, `scripts/fidelity_eval.py` | unaffected in code | They inherit `language = "auto"`: synthetic meetings are Portuguese, so detection should pick `pt`, adding up to about 25 s per meeting | none; a run that must match an old baseline exactly can set `language = "pt"` |
| Windows installer (`scripts/install.ps1`, `config_tool.py`, repo `meet-record-windows`) | unaffected | They do not write `[transcription] language`; the shipped `config.toml` carries the new default | none |
| Docs: `docs/REQUIREMENTS-AND-ARCHITECTURE.md` (row 12 "Portuguese only… Whisper pinned to pt", line 136 the adapter catalogue, §10), `docs/prd/pages/02-transcription.md`, `docs/prd/appendix/data-layout.md` (`transcript.json`, lines 51-56), `docs/prd/appendix/integrations.md` (whisper-cli row, line 8), `docs/prd/appendix/enum-dictionary.md`, `docs/guide/configuration.md`, `docs/guide/troubleshooting.md`, `docs/guide/commands.md` (`trec transcribe` row, line 12), `README.md` (line 7), `AGENTS.md` (ports table; line 133 "meetings are held in Brazilian Portuguese"), `docs/prd/README.md` (line 65), `docs/prd/pages/09-activities.md` (line 14), `docs/guide/activities-and-stories.md` (line 15) | modified | Row 12 becomes "Portuguese and English meetings; language detected per meeting; output pt-BR". Line 136 gains `WhisperCppLanguageDetector`; the integrations row gains the `-l auto -dl -f …` call (never `-np`); the data layout gains `language_detection`; the enum dictionary gains a `LanguageReason` section; the commands row names the `Language:` line; README and AGENTS.md say meetings are mostly in Brazilian Portuguese and sometimes in English, with all output in Portuguese. `docs/prd/README.md:65` reads "produced in Brazilian Portuguese (meetings are mostly in Portuguese, sometimes in English); literal quotes keep the language said", and the two activities pages name the quote exception | task 6 |

Compatibility regime: user state (`transcript.json`) migrates losslessly, since the field is additive and old files load as before. The public surface `[transcription] language` keeps accepting a code with its old meaning, so no shim is needed. The default changes for configs that omit the key, and the repository's `config.toml` changes with it. Internal code takes hard cuts: `TranscribeMeeting._checked` stops reading `self.language` (no fallback path that ignores the chosen language). There are no delete targets.

## Agent Manageability Plan

The feature is operated through the CLI and files only. Agents use `trec transcribe <id>` (the `Language:` line), `trec status` (the `· en` marker), `trec doctor` (the `language:` line) and `transcript.json` › `language_detection`. Deterministic configuration errors are listed in `_dx.md` › Errors.

## Config Lifecycle

- Added: `[transcription] languages`. Changed: the default of `[transcription] language` (`"pt"` → `"auto"`), with the new value `"auto"`.
- Validation in `config.load_settings` (`_parse_language`, `_parse_languages`), raising `ValueError(Err.INVALID_LANGUAGE / INVALID_LANGUAGES)` like `_parse_share`.
- `config.toml`: both keys with the comment shown in `_dx.md`.
- Docs: `docs/guide/configuration.md` and `docs/prd/pages/02-transcription.md` key tables.
- Tests: `tests/unit/test_config.py` (UT-020–UT-026, UT-025a).

## Testing Approach

- pytest. Use-case tests run on fakes (`FakeLanguageDetector`, `FakeTranscriber`). The adapter is tested with `tests/fixtures/fake_whisper_cli.py` extended with a `-dl` mode: for each `-f` it prints the `processing` line and a scripted answer from `--langs en:0.99,is:0.96,…` (or no answer for `-`). The adapter's commands are wrapped the way `ScriptedTranscriber` wraps the transcriber's. ffmpeg-dependent cases are skipped when ffmpeg is missing, as today.
- Slow, opt-in (`TREC_REAL_WHISPER=1`): the real adapter on clips spoken by macOS `say` in English and Portuguese voices (skipped without `say` or the model).
- Evaluation gates (evidence, not CI): G1, detection on every real meeting with audio (copies, read-only), with no wrong language wherever someone speaks (criterion in `_tests.md` › G1); G2, the MARTA meeting re-transcribed in English is not degraded; G3, the changed system prompts leave Portuguese output unchanged: before and after, with the shipped code on scratch copies of three Portuguese meetings. The verifier (`VerifyAnalysis` with `build_verifier`) checks the same stored analyses; the analyzer and curator are compared by re-analysis (`trec analyze`). `scripts/fidelity_eval.py` cannot measure this, because its `defend` uses its own inline verifier prompt. G3 spends the Claude Code subscription, so it runs only with the user's approval, as `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 required for the verifier's label sentence (speaker attribution, pending item 4). All three are recorded in §10.

## Development Sequencing

### Build Order

1. Domain (`domain/language.py`, `Transcript.language_detection`), codec, constants, config keys and validation. Gate: unit tests and mypy.
2. Port and adapter (`LanguageDetector`, `WhisperCppLanguageDetector`, fake CLI `-dl` mode, fake detector). Gate: adapter tests with the scripted CLI. Depends on 1.
3. `TranscribeMeeting` detection step and `container.py` wiring. Gate: use-case tests and container test. Depends on 1–2. **Slice 1 lands here** with 4.
4. Analyzer and verifier header line, the three prompts' wording and the English greetings in `Verify.ADDRESS`. Depends on 1 (it reads `Transcript.language`).
5. CLI lines (`transcribe`, `status`, `doctor`), minutes line (`MinutesRenderer.render` keyword, `RenderMinutes`, `FakeMinutesRenderer`). Depends on 1 and 3.
6. Gates G1 and G2 on real meetings (read-only copies), gate G3 on the prompts (with the user's approval), docs and `AGENTS.md`. Depends on 3 and 4 (5 for the CLI evidence).

### Technical Dependencies

- None to install: whisper-cli, ffmpeg and the model are already required. After merge, `trec agent restart` (with the user's approval) for the daemon to load the new code.

## Monitoring and Observability

Log lines (`messages.Log`, printf-style):

- `LANGUAGE_DETECTED = "language of %s: %s (%d of %d counted samples; %d taken)"` (info)
- `LANGUAGE_FALLBACK = "language of %s: %s, the fallback (%s; %d of %d samples counted)"` (info)
- `LANGUAGE_DETECTION_FAILED = "language detection of %s failed; transcribing in %s: %s"` (warning; the last argument is the exception, so a format change logs `Err.WHISPER_NO_LANGUAGE` with whisper's output tail)

Only the daemon configures logging (`_setup_logging`, `cli.py:779, 795-802`), so these lines reach `data/log/daemon.log` from the daemon only. A CLI run (`trec transcribe`) configures none: the warning reaches stderr through Python's last-resort handler when it is logged, right after `Transcribing <id>…` and before ` ok (…)`, and the two info lines are not shown. This is how the retry's warnings behave in a CLI run today; configuring CLI logging is out of scope. That is why the CLI's `detection failed` line says `see the warning above`.

No notification: a wrong language is visible in `trec status` and the minutes, and detection never blocks anything.

## Technical Considerations

### Key Decisions

- **Sampling plus allow-list vote, not whisper's `-l auto` on the transcription.** See ADR-001.
- **One whisper call for all samples.** `-f` repeated loads the model once: about 0.6 s plus about 2 s per sample, so about 25 s for 12 samples, instead of about 35 s with one call per sample. The saving is modest; the encoder dominates, so the sample cap (12) is what bounds the cost.
- **Detection inside the meeting lock.** It runs under the same lock as the transcription, so two transcriptions of one meeting never interleave. The lock does not protect `audio.m4a` from the purge: `PurgeOldAudio` (`retention.py:18-26`) deletes without taking it. The purge only targets meetings that already have a transcript and are past the retention period, so only a re-transcription of such a meeting (the backfill in Open Questions) can race it. The outcome is fail-soft: ffmpeg fails, detection falls back with `detection-failed`, and the transcription then fails with `AUDIO_MISSING` and `error.txt`, as a transcription racing the purge does today. Making the purge honour the lock is out of scope.
- **The offsets ignore `energy.json`.** It exists only for meetings recorded since speaker attribution. Neither the allow-list nor the probability floor filters silence and noise: whisper answers them `en`, with probabilities that overlap real speech (Evidence). Skipping windows without speech belongs to the separate speech-check spec (Silero VAD before the vote), decided on 2026-10-22 and not opened yet.
- **The header line only for non-Portuguese transcripts.** It keeps every Portuguese user message byte-identical to today's. The system prompts still change for every meeting (the analyzer's and the verifier's wording, the curator's quote exception), so a Portuguese request is not identical to today's, and gate G3 re-measures it rather than assuming comparability.

### Known Risks

- **A Portuguese meeting detected as English** (it would come out translated). Likelihood low: every Portuguese clip measured gave `pt` with p ≥ 0.99, and a switch needs more than half of the counted samples and at least 2. Mitigation: gate G1 on all 25 Portuguese meetings; a fixed `language = "pt"` restores today's behavior.
- **Samples that land on silence or noise.** whisper answers them `en`, with p up to 0.68 on real recordings (Evidence), so they can vote. A Portuguese meeting where most samples land on silence or noise could be detected `en`. Mitigation: a majority of counted samples and at least two votes, so a few silent samples in a meeting with speech are outvoted (G1: 26 of 26 recordings with speech correct). The speech-check follow-up (VAD before the vote) removes the case at its root.
- **A mixed meeting** loses the minority language's text to translation. Accepted by the user's decision; the detection record shows the split (`counted` against `votes`).
- **whisper output format change** on a whisper.cpp upgrade: falls back to `pt` with a warning; IT-004 catches it.
- **Windows** CPU-only whisper may take longer per sample (untested); the timeout is 300 s and a timeout falls back.
- **The loop guard on English backchannels.** The vans meeting's English retry has 10.4% of its segments in "loops", and they are the natural "Okay." lines, so it stays marked degraded at the 10% threshold. Portuguese meetings measured 0%. Changing the loop guard is out of scope. Gate G2 measures the MARTA meeting; if English meetings regularly land just above 10% on backchannels, a follow-up tunes the loop rule for short lines (Open Questions).

## Safety Invariants

1. Detection never raises out of `TranscribeMeeting`: every exception from the detector becomes `LanguageDetection(fallback, DETECTION_FAILED)`.
2. The first pass and the retry of one meeting use the same language.
3. With a fixed `language`, the whisper command is byte-for-byte today's, and no detector is built.
4. Detection writes nothing in the meeting folder: the clips live in a temporary directory removed on exit. A missing or vanishing `audio.m4a` is a detection failure, never a crash.
5. A literal quote is never translated by the analysis, the verifier or the curator (prompt rule; checked by gate G3 and by the real-call suites when they run).
6. `TranscribeMeeting.language` is never `"auto"`: whisper never receives `-l auto`.

## File References

### Repo Files

- `src/teams_recorder/adapters/outbound/transcriber_whispercpp.py:22-102`: the adapter shape to mirror (constructor, public `*_command`, `_run` error mapping, `NO_WINDOW`).
- `src/teams_recorder/application/use_cases/processing.py:29-161`: `TranscribeMeeting`, where detection goes and how `_checked` and the retry pass the language.
- `src/teams_recorder/application/ports.py:100-101`: the `Transcriber` port the new protocol sits next to.
- `src/teams_recorder/domain/models.py:136-160`: `Transcript`, which gains `language_detection`.
- `src/teams_recorder/adapters/outbound/codec.py:85-150`: transcript and health (de)serialization to extend.
- `src/teams_recorder/config.py:63-110, 236-335`: `Settings` and `load_settings`, with `_parse_share` and `_as_list` as validation patterns.
- `src/teams_recorder/container.py:129-131, 215-265`: `transcribe_meeting()` and `build_retry_transcriber`, where the detector is wired.
- `src/teams_recorder/constants.py:188-280`: `Audio`, `Transcription` and `Parse`, where the new constants go.
- `src/teams_recorder/adapters/outbound/llm_schema.py:135-149`: `build_user_message`, which gets the header line.
- `src/teams_recorder/adapters/outbound/verifier_claude.py:135-143`: `user_message`, same.
- `prompts/analyze_system.md:1, 50-66`: the "held in Brazilian Portuguese" line, the cues and the Language section.
- `prompts/verify_system.md`, `prompts/curate_system.md:1, 34, 43, 281`: verifier wording; the curator's Portuguese-only sentences and the 💬 literal quote.
- `src/teams_recorder/messages.py:684-693`: `Prompt.CURATE_TASK`, whose step 7 must carry the quote exception.
- `src/teams_recorder/adapters/outbound/minutes_markdown.py`, `src/teams_recorder/messages.py:720-750`: minutes header lines (`DATE`, `PARTICIPANTS`).
- `src/teams_recorder/adapters/inbound/cli.py:85-115, 210-300, 432-472`: `status`, `doctor` (`_check_transcript_health`) and `transcribe`.
- `tests/fixtures/fake_whisper_cli.py`, `tests/integration/test_transcriber_whispercpp.py:25-40`: the scripted whisper stand-in and the `ScriptedTranscriber` wrapping to mirror.
- `tests/fakes/__init__.py:176-191`: `FakeTranscriber`, the model for `FakeLanguageDetector`.
- `tests/fakes/__init__.py:432-437`, `src/teams_recorder/application/use_cases/processing.py:188-202`: `FakeMinutesRenderer` and `RenderMinutes`, both changed by the minutes keyword.
- `src/teams_recorder/adapters/outbound/repository_fs.py:58-73`, `codec.py:136-150`: how a damaged file becomes `RepositoryError`, and the `isinstance` check on `speakers` to mirror.
- `src/teams_recorder/application/use_cases/retention.py:18-26`: the purge, which does not take the meeting lock.
- `src/teams_recorder/constants.py:226-247`, `src/teams_recorder/domain/verification.py:135-164`: `Verify.ADDRESS` and `participant_heard`, the Portuguese-only greetings that gain English forms.
- `src/teams_recorder/adapters/inbound/cli.py:448, 779, 795-802`: `Transcribing…` printed without a newline, and logging configured by the daemon only (where a CLI run's warning goes).
- `src/teams_recorder/container.py:288-296`, `src/teams_recorder/application/use_cases/verification.py:29-60`, `src/teams_recorder/config.py:138-139`: `build_verifier` and `VerifyAnalysis`, which gate G3 runs on stored analyses, and `prompts_dir` under the project dir, which lets two checkouts compare the old and new prompts.
- `scripts/fidelity_eval.py:396, 431`: `defend` sends its own inline `VERIFY_SYSTEM`, not `prompts/verify_system.md`, so G3 does not use it.
- `docs/prd/README.md:65`, `docs/prd/pages/09-activities.md:14`, `docs/guide/activities-and-stories.md:15`: say all activities content is Portuguese, with no exception for quotes.
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md` (row 12, line 136, §10 and the speaker-attribution pending item 4, the precedent for G3), `docs/prd/pages/02-transcription.md`, `docs/prd/appendix/data-layout.md`, `integrations.md`, `enum-dictionary.md`, `docs/guide/commands.md`, `README.md`, `AGENTS.md:133`: documents to update.

### Design and Analysis Sources

- `docs/tasks/prd-llm-wiki/evaluation.md` §14.1, §14.7: the 2026-10-08 loop incident on the English meeting, and `-mc 0` leaving Portuguese accuracy unchanged.
- whisper.cpp `whisper-cli --help` (1.9.4): cited by concept; no path in this repo.

## Assumptions and Defaults

- Window 30 s; one sample per 300 s; 3 to 12 samples; probability ≥ 0.5; winner > ½ of counted and ≥ 2 votes (1 with one sample).
- `language = "auto"`, `languages = ["pt", "en"]`, fallback `pt`.
- Detection timeout 300 s; threads as the transcriber's (`[transcription] threads`).
- The minutes name the language in Portuguese: `pt` → not shown, `en` → `inglês`, any other code → the code itself.
- Old transcripts keep `pt` and have no detection record. The analyzer reads `Transcript.language` (always present).

## Architecture Decision Records

- [ADR-001: Detect from samples spread over the meeting, counting only allowed languages](adrs/adr-001.md): sampled `-dl` with an allow-list majority, rather than `-l auto`, per-stretch transcription or LLM detection.
