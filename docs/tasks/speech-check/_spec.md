# Spec: Check for speech before transcribing, and stop counting short replies as loops

> Slug `speech-check` · Date 2026-10-22 · Status: approved by the user on 2026-10-23 ("Sim, implemente"), after review rounds 1–4 · Review round 1 (2026-10-23) applied: [reviews-001](reviews-001/_summary.md)
> Evidence: §"Evidence (2026-10-22)" below (Silero VAD on all 28 stored recordings, speech inside every language sample, and the loop rule with and without the short-line exemption on the stored transcripts and the language-detection G2 transcripts)
> Companions: [user stories](_user_stories.md) · [developer experience](_dx.md) · [tests](_tests.md) · [ADR-001](adrs/adr-001.md)
> Origin: language-detection gate G1 (`docs/tasks/language-detection/_tests.md` › G1, note of 2026-10-22) and its open questions (2) and (3) in `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10.

# Part I — Product

## Overview

- **Motivating Problem**: a recording with nobody speaking still goes through whisper.
  - Whisper invents text for it: "Legenda por Sônia Ruberti" for 11 s of silence, "A CIDADE NO BRASIL" and "Se inscreva no canal" for 5 minutes of noise. With language detection it can also label that text English: both such recordings came out `en` in G1.
  - Nobody is told. A long recording with no speech is how a failed capture shows: Teams audio and microphone both missing. The user finds out only when the minutes are empty or invented.
  - A second, smaller problem: natural short replies count as a hallucination loop. In the English vans meeting, eight "Okay." lines out of 77 made the transcript "degraded" (10.4% against the 10% limit), with no loop in it.
  - **The simplest end-to-end behavior that solves it:**
    - Before transcribing, the daemon measures the speech in the recording with Silero VAD. Under 2 s of speech means no speech: whisper does not run, the transcript is saved empty and marked "no speech", and a warning goes to the log. A recording of 1 minute or more also raises a notification.
    - The flow then continues as for any empty transcript. The analysis is local, with no Claude call, and the minutes and the curator treat it as empty.
    - Short replies of up to 2 words no longer count as a loop, unless the loop rule already flags them and 3 or more such short lines stand in a row.
- **Who it is for**: the user, who records Teams meetings and relies on the minutes, and the same person as operator of the install.
- **Why it is valuable**:
  - No invented transcripts for empty recordings.
  - A failed capture is noticed the same day, while the audio is still kept (30 days).
  - Language detection no longer votes on silence.
  - Healthy meetings full of "Okay." are no longer flagged or re-transcribed for nothing.

## Goals

- A recording with no speech never produces text, an LLM call or a language guess. Its transcript says "no speech" and how much audio there was.
- When a recording of 1 minute or more has no speech, the user gets a notification that names it and points to `trec doctor`.
- A recording with speech is transcribed with the same whisper command as with the check off, for the language it was given. With a fixed language the command is byte-for-byte the check-off one. In auto mode, the language can change by design, because silent samples no longer vote and a missing meeting length is replaced by the measured one (Goal below). Otherwise the only additions are the speech measurement in its record and one `Speech:` line in `trec transcribe`.
- Language detection votes only on samples that hold speech, and it no longer takes a single sample at the start of a meeting whose recorded length is unknown.
- A transcript is not called degraded because of short replies spread through a conversation. Short lines that the loop rule flags are still a loop when 3 or more of them stand in a row, whether they are the same line or not.
- The operator can see whether the check is working (`trec doctor`), which recordings had no speech (`trec status`), and can turn the check off to force a transcription (`[transcription] speech_check = false`).

## User Stories

- US-001 to US-003, the speech check: no speech means no transcription, a notification for long recordings, and recordings with speech unchanged.
- US-004, language samples: only samples with speech vote, and the audio length is used when the meeting has none.
- US-005, loops: short replies do not count as loops.
- US-006 and US-007, visibility: `trec transcribe`, `trec status`, `trec doctor`.
- US-008 and US-009, operation: the off switch, and a check that fails never blocks a transcription.
- [Full user stories](_user_stories.md)

## Core Features

1. **Speech check.** Before the language detection and before whisper, the recording's audio goes through Silero VAD once.
   - The result is stored in `transcript.json`: seconds of speech, seconds of audio, and the number of speech segments.
   - Under 2.0 s of speech, the recording has no speech:
     - whisper, the language detection, the retry and the speaker labelling do not run;
     - the transcript is saved with no segments;
     - a warning is logged, and a notification is sent when the audio is 60 s or longer.
   - Otherwise, transcription runs as today.
2. **Speech-aware language samples.** The same VAD result tells how much speech falls inside each planned 30-second sample. A sample with under 3.0 s of speech is not sent to whisper's language identification. When the meeting has no recorded length, the audio's length from the check is used to plan the samples.
3. **Short replies are not loops.** In the loop rule (`domain/health.py`), a line of at most 2 words is flagged only when it is also part of a run of 3 or more short, repeated lines in a row. The lines of the run may differ, so a loop alternating two short lines is still caught.
4. **Visibility and control.**
   - A `Speech:` line in `trec transcribe`.
   - `· no speech` in `trec status`, with a count line.
   - A `speech check:` line in `trec doctor`.
   - `[transcription] speech_check` (default `true`).

The check (1) feeds the samples (2). The loop rule (3) is independent. The lines (4) read the record (1).

## Business Rules

- **No speech**: Silero VAD finds under `2.0` s of speech in the whole audio.
  - VAD settings are the project's (`-vt 0.5 -vsd 300 -vp 150`, `constants.Audio.VAD_ARGS`) and the model is `[transcription] vad_model` (default `silero-v5.1.2`).
  - The two no-speech recordings measured 0.0 s; every other stored recording measured 7.3 s or more.
- **What a no-speech recording gets**:
  - a `transcript.json` with no segments, `language` set to the fallback language (`[transcription] languages[0]`, or the fixed `language`), no `health`, no `language_detection`, no speaker `labels`, and the `speech` record with `"found": false`;
  - a `transcript.txt` with no lines (the repository writes one newline, as for any transcript).
  - The meeting's status becomes `transcribed`, and the pipeline continues.
  - `trec analyze` produces the local empty analysis it already produces for a transcript with no words: summary `Empty transcript: no speech recognized.`, and no Claude call (`llm_schema.trivial_analysis`).
- **Notification**: one per no-speech recording whose audio is at least `60` s, sent through the container's notifier. That is a Mac or Windows notification in the daemon. In a CLI run (`trec transcribe`, headless), the `LogNotifier` logs it at info level, which a CLI run does not show; there the `WARNING:` line is the visible signal. No daily de-duplication: a no-speech recording of a minute or more is rare and each one deserves a look. Shorter recordings only log.
- **A recording with speech**: the whisper commands (first pass and retry) are the ones `speech_check = false` gives, for the language and duration the use case chose. The baseline is the check-off run of the same code, not the code before this feature: the new loop rule changes `health`, and the retry runs only on a degraded first pass. The record gains `speech` with `"found": true`.
  - With a fixed `language`, or in auto mode when the filter drops no sample and `meta.json` has a duration, the commands and every other key are byte-for-byte the check-off run's.
  - In auto mode, the language-sample filter and the planned-count rule can change the chosen language, and so the `-l` value, on purpose. `language_detection.samples` lists only the samples sent.
  - When `meta.json` has no duration, the stand-in also changes the planned offsets and `health.total_minutes`.
  - Gate G2 measures the language changes on the stored recordings.
- **Language samples**:
  - a planned sample counts as holding speech when VAD found at least `3.0` s of speech inside its window `[offset, offset + 30 s)`;
  - samples without speech are not cut or sent, and are not listed in `language_detection.samples`;
  - when no planned sample holds speech, the result is `no-usable-sample` and the fallback language is used, the existing rule.
  - When `meta.json` has no duration, the planned offsets and the transcript health use the audio length the check measured.
  - **The one-vote exception follows the planned count.** `choose_language` lets a single counted sample decide only when one sample was *planned* (a meeting of 30 s or less, or of unknown length with no check result). When several samples were planned and the filter kept one, that one sample needs `min_votes` (2) like any other meeting, so it gives `too-few-votes` and the fallback. `choose_language` gains `planned: int | None = None` (None: the number of samples passed, today's behavior), and the use case passes the number of planned offsets.
  - With no check result (check off or failed), the samples are planned and sent exactly as today.
- **Loop rule**:
  - The rule is unchanged for lines of 3 or more words.
  - A line of at most 2 words is in a loop only when both of these hold:
    - the existing window rule flags it: 5 copies within 30 consecutive segments;
    - it sits in a run of at least 3 consecutive segments that are all short (at most 2 words) and all flagged by the window rule. Their texts may differ.
  - So "Okay." spread through a conversation, at most 2 in a row, is not a loop. "e aí" ×3 back to back is, and so is "Obrigado." / "Tchau." alternating back to back. The existing test `test_two_lines_alternating_are_a_loop_too` keeps passing unchanged.
  - Words are counted on the comparison key (`domain/health._key`: lowercase `\w+` words, a phrase written twice in one segment counted once). A key with no words (`...`) counts as short.
- **Check off or failed**: the meeting is transcribed exactly as before this feature, and `speech` is absent from the record. A failure (missing tool, missing model, timeout, non-zero exit, unreadable output) logs one warning and never writes `error.txt` or notifies.
- **Redoing a wrong "no speech" verdict.** Audio retention is unchanged (`[audio] retention_days`, 30). In the daemon the flow has already continued, so the meeting is `analyzed`, with the local empty analysis, minutes and a `skipped_empty` curator pass. The recovery takes three steps:
  1. set `[transcription] speech_check = false`;
  2. run `trec transcribe <id>` then `trec analyze <id>`. Only the id form re-analyzes and re-curates: `trec analyze` with no id picks only `transcribed` meetings, and this one is `analyzed`;
  3. set `speech_check = true` again.
  - The daemon reads the config once at start, so it keeps checking unless it is restarted while the key is false. There is no per-run override.
- **Existing transcripts are not rewritten.** The stored health of past transcripts keeps the old loop rule until a meeting is transcribed again.

## User Experience

- **The user**:
  - An accidental 11-second recording becomes `transcribed` with an empty transcript, and the user never sees invented minutes.
  - A 5-minute recording where the capture failed raises "No speech in a recording" on the Mac. The user runs `trec doctor`, fixes the capture and, if the meeting mattered, writes notes by hand.
  - If the verdict was wrong, the user follows the recovery in Business Rules: turn the check off, run `trec transcribe <id>` and `trec analyze <id>`, then turn it back on.
  - An English meeting full of "Okay." is no longer flagged degraded and no longer gets a second whisper pass.
- **The operator**:
  - `trec transcribe <id>` shows a `Speech:` line for every meeting.
  - `trec status` marks `· no speech`.
  - `trec doctor` shows whether the check can run.
  - To force a transcription, set `speech_check = false`, run `trec transcribe <id>` and `trec analyze <id>`, and set the key back to `true`.
- No graphical interface, so no `_uiux.md`.

## High-Level Technical Constraints

- Local only: Silero VAD through whisper.cpp's `whisper-vad-speech-segments` (Homebrew `whisper-cpp`, the same package as `whisper-cli`), with the VAD model already used by the retry.
- Cost: one extra ffmpeg conversion and one VAD run per meeting, measured at 19 s of VAD for 86 minutes of audio on the development Mac (M1). No subscription use.
- Windows: the tool is looked up like `whisper-cli` (PATH, then `<project>/tools`). This is untested on real hardware, like every Windows path. If it is missing, the check is skipped with a warning, and `trec doctor` says so.
- Strings live in `messages.py` and `constants.py`, and everything written to the repository is in English (AGENTS.md).

## Non-Goals (Out of Scope)

- Repairing a failed capture or diagnosing which track failed. The notification points to `trec doctor`, which already checks the capture tools.
- VAD on whisper's first pass (`[transcription] vad`, default off). It is unchanged; see ADR-001.
- Rewriting the health or the transcripts of past meetings, or backfilling the speech record.
- Changing the minutes, the curator or the analysis for empty transcripts. They already handle a transcript with no words.
- Detecting partial capture failures (one track silent, the other fine). Speech from either track is speech.
- Moving the language samples onto speech, as opposed to skipping samples without speech. See Key Decisions.

## Open Questions

None at the time of writing. The thresholds (2.0 s, 3.0 s, 60 s, 2 words, 3 in a row) are constants. The gates in `_tests.md` re-measure them on the stored recordings before the work is called done.

---

# Part II — Technical

## Executive Summary

A new `SpeechDetector` port has one adapter, `WhisperCppSpeechDetector`. It converts the audio to 16 kHz WAV with ffmpeg, runs `whisper-vad-speech-segments` with the project's VAD settings, and returns a pure `SpeechActivity`: the audio length and the speech segments.

`TranscribeMeeting` asks for it right after the capture-counter check:
- With under 2 s of speech, it saves an empty transcript with a `SpeechCheck` record, logs, notifies when the audio is 60 s or longer, and returns.
- Otherwise it keeps the record and uses the activity to drop language samples without speech, and to stand in for a missing meeting duration.

The check is advisory: any failure means no record and today's behavior.

The loop rule gains one condition for lines of at most two words: they count only inside a back-to-back run of three or more short, window-flagged lines.

Whole-audio VAD with a separate binary was chosen over VAD on whisper's first pass, an ffmpeg volume threshold, and VAD only inside the language detector (ADR-001).

## Evidence (2026-10-22)

Measured read-only on the development Mac (M1): whisper.cpp 1.9.4, `ggml-silero-v5.1.2.bin`, the project's VAD arguments, WAVs in a temporary folder. The scripts are throwaway and are not in the repository.

**Speech per recording (28 with audio):**
- 2026-10-08_02-50-26 (10.8 s): 0.0 s of speech, 0 segments.
- 2026-10-17_10-15-32 (309.6 s): 0.0 s of speech, 0 segments.
- Every other recording: between 7.3 s (2026-10-14_15-37-40, 23.7 s long) and 3,998 s (the 86-minute MARTA meeting) of speech. The speech share ran from 16.0% (2026-10-17_09-44-07) to 87.7%.
- VAD time: 0.1–0.4 s for recordings under 2 minutes, 19.0 s for 86 minutes, and 17.7 s for 66 minutes. The ffmpeg conversion comes on top of that.
- The 2.0 s threshold therefore sits between 0.0 and 7.3 with a wide margin on both sides.

**Speech inside each language sample** (seconds of speech in each planned 30-second window, `sample_offsets`):

| Recording | Samples | G1 heard |
|---|---|---|
| 2026-10-14_15-00-56 (vans, English) | 0 0 0 9 14 5 0 0 | `is` 5, `en` 3 |
| 2026-10-17_09-44-07 | 5 3 0 | `pt` 2, `ja` 1 |
| 2026-10-17_09-56-47 | 0 25 2 8 | `pt` 2, `ja` 1, `en` 1 |
| 2026-10-16_20-18-06 | 26 21 6 0 13 | `pt` 4, `en` 1 |
| 2026-10-08_02-50-26, 2026-10-17_10-15-32 | 0 / 0 0 0 | `en` (no speech) |

Every other meeting has speech in every sample. The stray answers G1 saw (`is`, `ja`, a lone `en`) appear only in meetings that have samples with little or no speech. G1 did not record which sample gave which answer, so gate G2 re-runs the detection with the filter.

**Loop rule** (share of segments in loops; * = degraded, above 10%):

| Transcript | Today | Short lines ≤ 2 words never count | ≤ 2 words count only in runs of 3+ short flagged lines (adopted) |
|---|---|---|---|
| vans, English retry (G2 scratch) | 10.4%* ("okay" ×8, at most 2 in a row) | 0.0% | 0.0% |
| MARTA, English (G2 scratch) | 1.2% ("okay" ×6, "thank you" ×5, 4 in a row) | 0.0% | 0.4% |
| vans, stored (forced `pt`) | 68.7%* ("e aí" ×18, 6 in a row, plus long loops) | 62.4%* | 65.7%* |
| 2026-10-17_09-56-47 (Portuguese) | 3.8% ("e aí" ×6, 3 in a row) | 0.0% | 1.9% |
| MARTA, stored | 1.0% (3–4-word lines) | 1.0% | 1.0% |

The other stored transcripts have no loops. The run condition keeps flagging what whisper repeats back to back ("e aí" ×6 in a row in a hallucinated transcript), which "never count" would miss. Review round 1 recomputed the adopted column and found the same shares under the narrower "3+ copies of the same key" reading. The adopted reading also keeps catching a back-to-back cycle of two short lines, which the same-key reading would drop.

## MVP Boundary

- **MVP:** the speech check end to end. That means the domain record, the adapter, the use case skipping whisper with the warning and the notification, the codec, the container wiring, and the `Speech:` line of `trec transcribe`. This solves the Motivating Problem: an empty recording gets no invented text, and a long one notifies.
- **The rest:** the language-sample filter and the duration stand-in, the loop rule, `trec status` and `trec doctor`, the off switch, the docs and the gates. The loop rule does not depend on the rest and can ship in any slice.
- **Out of scope:** the Non-Goals.

## Developer Experience

- [Developer experience contract](_dx.md):
  - the golden path;
  - `[transcription] speech_check`;
  - `trec transcribe`, `trec status` and `trec doctor` lines;
  - the notification;
  - `transcript.json` `speech`;
  - the log lines and the failure surface.

## System Architecture

```
TranscribeMeeting.execute(meeting_id)              (application/use_cases/processing.py)
  ├─ _rate_mismatch()                               unchanged
  ├─ _speech(meeting_id, audio) ─▶ SpeechDetector   new port; WhisperCppSpeechDetector
  │     └─ check_speech(activity, rules)            domain/speech.py (pure)
  ├─ no speech ─▶ save empty transcript, log, notify (≥ 60 s), return
  ├─ _language(meeting_id, audio, duration, activity)
  │     └─ samples_with_speech(offsets, activity, window, rules)   domain/speech.py
  ├─ _transcribe(...)                               unchanged; health via domain/health.py (new short-line condition)
  └─ _label(...), save, notifications               unchanged
```

- `domain/speech.py` (new, pure):
  - `SpeechRules` holds the thresholds;
  - `SpeechActivity` is what VAD found;
  - `SpeechCheck` is the stored record;
  - `check_speech()` and `samples_with_speech()` are the two functions.
- `domain/health.py`: `loop_flags` gains the short-line condition. `LOOP_REPEATS` and `LOOP_WINDOW` are unchanged, and `SHORT_LINE_WORDS = 2` and `SHORT_LINE_RUN = 3` are new.
- `domain/language.py`: `choose_language` gains `planned: int | None = None` for the one-vote exception.
- `application/ports.py`: `SpeechDetector`.
- `adapters/outbound/speech_whispercpp.py` (new): `WhisperCppSpeechDetector` and `parse_speech_segments`.
- `container.py`: `build_speech_detector(settings)` and `Container.speech_detector`. `transcribe_meeting()` passes both.
- `adapters/outbound/codec.py`: the `speech` key.
- `adapters/inbound/cli.py`:
  - the `Speech:` line and the no-speech warning in `transcribe`;
  - the `· no speech` marker and the count in `status`;
  - the `speech check:` line in `doctor`.
- `config.py`: `speech_check` and `Settings.speech_model_path`. `scripts/config_tool.py` includes the speech model in `vad_path`, so the installers download it.

## Architectural Boundaries

- `domain/speech.py` imports only the standard library and `domain` modules. `domain/health.py` stays pure.
- The adapter imports `constants`, `messages`, `domain`, `adapters/outbound/process_control` and the new neutral `adapters/outbound/audio_convert`. That is the set `language_whispercpp.py` imports, plus the shared conversion. It never imports another adapter's internals (AGENTS.md › Architecture).
- `application` depends on the port, never on the adapter. `container.py` is the composition root.
- No new package.

## Implementation Design

### Core Interfaces

```python
# domain/speech.py
@dataclass(frozen=True)
class SpeechRules:
    """Thresholds of the speech check; fixed constants (changing one is a code change, measured in the spec's Evidence)."""
    min_speech_seconds: float = 2.0         # under this much speech in the whole audio: no speech
    min_sample_speech_seconds: float = 3.0  # a language sample needs this much speech inside its window
    notify_min_audio_seconds: float = 60.0  # a no-speech recording at least this long notifies


@dataclass(frozen=True)
class SpeechActivity:
    """What VAD found: the audio's length and its speech segments, (start, end) in seconds, sorted, non-overlapping."""
    audio_seconds: float
    segments: tuple[tuple[float, float], ...] = ()

    @property
    def speech_seconds(self) -> float: ...

    def speech_between(self, start: float, end: float) -> float:
        """Seconds of speech inside [start, end)."""


@dataclass(frozen=True)
class SpeechCheck:
    """The record saved with the transcript (transcript.json `speech`)."""
    found: bool
    speech_seconds: float
    audio_seconds: float
    segments: int


def check_speech(activity: SpeechActivity, rules: SpeechRules = SpeechRules()) -> SpeechCheck:
    """found = speech_seconds >= rules.min_speech_seconds; seconds rounded to 0.1."""


def samples_with_speech(offsets: Sequence[float], activity: SpeechActivity, window_seconds: float,
                        rules: SpeechRules = SpeechRules()) -> list[float]:
    """The offsets whose window [offset, offset + window_seconds) holds at least rules.min_sample_speech_seconds of speech, in order."""
```

```python
# application/ports.py
class SpeechDetector(Protocol):
    def activity(self, audio: Path) -> SpeechActivity:
        """The speech segments of the whole audio. Raises TranscriptionError when the check could not run."""
        ...
```

```python
# application/use_cases/processing.py (additions to TranscribeMeeting; fields appended after language_rules)
    speech_detector: SpeechDetector | None = None   # None: [transcription] speech_check = false, nothing is checked
    speech_rules: SpeechRules = SpeechRules()

    def _speech(self, meeting_id: str, audio: Path) -> SpeechActivity | None:
        """VAD over the whole audio; None without a detector or when the check fails (warning Log.SPEECH_CHECK_FAILED).
        Advisory: never an error, a notification or an error.txt."""

    def _no_speech(self, meeting_id: str, check: SpeechCheck) -> Transcript:
        """The empty transcript of a recording with no speech: no segments, language = self.language, speech = check,
        no health, detection or labels. Logs Log.NO_SPEECH; saved by execute() like any transcript."""
```

`execute()` order:
1. audio present;
2. lock;
3. `_rate_mismatch`;
4. `activity = _speech(...)`; `check = check_speech(activity)` when there is an activity;
5. if `check` is not None and not `check.found`: `transcript = _no_speech(...)`, save it, then notify Notify.NO_SPEECH when `check.audio_seconds >= rules.notify_min_audio_seconds` (outside the lock, like the other notifications), and return.
   - This notification is guarded: an exception from `notify` is caught and logged as a warning (`Log.NO_SPEECH_NOTIFY_FAILED`), and `execute` still returns the saved transcript. Otherwise, in the daemon, `Pipeline.process` would write `error.txt` for a meeting whose transcript was saved.
   - The existing degraded and rate-mismatch notifications stay unguarded; changing them is out of scope.
6. `duration = meta.duration_seconds or (activity.audio_seconds if activity else None)`;
7. `_language(meeting_id, audio, duration, activity)`:
   - plans the offsets with `sample_offsets(duration)`;
   - with an activity, keeps `samples_with_speech(...)`, logging Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH when any were dropped;
   - calls `choose_language(samples, allowed, fallback, rules, planned=len(offsets))`, so that one surviving sample of several planned cannot decide alone;
8. `_transcribe`, `_label`, `transcript.speech = check`, save;
9. notifications as today.

```python
# adapters/outbound/speech_whispercpp.py
class WhisperCppSpeechDetector:
    def __init__(self, vad_model_path: Path, vad_tool: str = Bin.WHISPER_VAD, ffmpeg: str = Bin.FFMPEG,
                 threads: int = 0, timeout: float = Proc.SPEECH_CHECK_TIMEOUT) -> None: ...
    def convert_command(self, audio: Path, wav: Path) -> list[str]: ...   # audio_convert.wav_convert_command(self.ffmpeg, audio, wav), shared with the transcriber
    def vad_command(self, wav: Path) -> list[str]:
        """[vad_tool, "-vm", model, "-f", wav, "-np", "-t", threads, *Audio.VAD_ARGS]"""
    def activity(self, audio: Path) -> SpeechActivity: ...   # model and audio checked first; temp dir `trec-speech-`, removed on exit


def parse_speech_segments(output: str) -> tuple[tuple[float, float], ...]:
    """Reads `Detected <n> speech segments:` and the n lines `Speech segment <i>: start = <cs>, end = <cs>` (centiseconds,
    so 2067.00 is 20.67 s). Raises TranscriptionError(Err.VAD_BAD_OUTPUT) when the count line is missing or n differs
    from the lines read: a format change must not read as "no speech"."""
```

The audio length comes from the converted WAV (`frames / rate`), not from the meeting's metadata.

The conversion is one shared function, not a copy. A new neutral module, `adapters/outbound/audio_convert.py`, holds `wav_convert_command(ffmpeg, audio, wav)`, which returns today's argv. It imports only `constants`. `WhisperCppTranscriber.convert_command` delegates to it unchanged, so neither adapter imports the other. A later change of the conversion tool (the `no-homebrew` draft moves it to `afconvert`) then covers the speech check too.

### Data Models

`transcript.json` gains one optional key. The encoder writes it only when set. The decoder checks types and never coerces; the `language_detection` decoder coerces with `str()`/`int()`/`float()` and is not the model here. The checks:
- the record is a `dict`;
- `found` is a `bool`;
- `segments` is an `int` and not a `bool`;
- `speech_seconds` and `audio_seconds` are an `int` or a `float`, not a `bool`, and finite, as `_finite` checks (`codec.py:195-200`).

Each failure raises `TypeError`. `_decode` (`repository_fs.py:66-73`, reached through `_decoded` from `load_transcript`) reports it as the `RepositoryError` naming `transcript.json`.

```json
"speech": {"found": false, "speech_seconds": 0.0, "audio_seconds": 309.6, "segments": 0}
```

| Field | Type | Purpose |
|---|---|---|
| `speech.found` | bool | Whether the recording has speech (`speech_seconds >= 2.0`) |
| `speech.speech_seconds` | float | Seconds of speech VAD found, rounded to 0.1 |
| `speech.audio_seconds` | float | Length of the audio, rounded to 0.1 |
| `speech.segments` | int | Speech segments VAD found |
| `Transcript.speech` | `SpeechCheck \| None` | None means not checked: check off, check failed, or a transcript made before this feature |

Side-table vs JSON: there is no database in this project. The equivalent of a side-table would be a separate file in the meeting folder. The record is JSON inside `transcript.json` instead, for three reasons:
- it is opaque metadata of one transcription;
- it is read only together with the transcript, and no command queries it across meetings except `trec status`, which already loads each transcript;
- it is replaced whenever the meeting is transcribed again.

A separate file could go stale against the transcript, and it would add a file that `domain/status.py` must ignore.

Config: `[transcription] speech_check BOOL = true`, parsed like `vad` and `retry_vad` (`bool(...)`). `Settings.speech_model_path` is `models_dir / ggml_model_file(vad_model)` when `speech_check` is set, else None.

### API Endpoints

None: no HTTP surface.

## Integration Points

- `whisper-vad-speech-segments` (whisper.cpp, Homebrew `whisper-cpp` 1.9.4 on the development Mac): a local process, one run per meeting. Failure handling is in Business Rules: advisory, logged, today's behavior.
- ffmpeg: the conversion, through the shared `audio_convert.wav_convert_command`.

## Impact Analysis

| Component | Impact Type | Description and Risk | Required Action |
|---|---|---|---|
| `domain/speech.py` | new | Pure rules and records. Low risk. | Write with unit tests |
| `domain/health.py` `loop_flags` | modified | Short lines need a run of 3+ short, window-flagged lines to count. Changes the health of new transcripts only (Evidence table); `is_healthier_than` follows. Low–medium risk: a short hallucination spread out (not back to back) is no longer a loop. | Change and test; update the module docstring |
| `tests/unit/test_transcript_health.py` | modified | `test_a_loop_is_five_copies_within_thirty_segments…`: the `within` case's lone "Ok." at index 0 is no longer flagged, so the expected indices go from `[0, 26, 27, 28, 29]` to `[26, 27, 28, 29]`. This is an intended contract change. `test_two_lines_alternating_are_a_loop_too` and the other tests pass unchanged. | Update the one assertion |
| `domain/language.py` `choose_language` | modified | New keyword `planned` (default None = today's behavior). Existing callers and tests are unchanged. | Change and test |
| `application/ports.py` | new port | `SpeechDetector` | Add |
| `TranscribeMeeting` | modified | New first step and early return; language offsets filtered; duration stand-in. Medium risk: a wrong "no speech" skips whisper. Mitigated by the 2.0 s threshold (smallest real recording 7.3 s), the notification, the off switch and the 30-day audio retention. | Change and test |
| `adapters/outbound/speech_whispercpp.py` | new | Adapter and parser | Write with stand-in tests and an opt-in real test |
| `codec.py` | modified | `speech` key, written only when set; old files load unchanged | Change and test |
| `container.py` | modified | `build_speech_detector`, `Container.speech_detector`, `transcribe_meeting()` wiring | Change and test |
| `config.py`, `config.toml`, `scripts/config_tool.py` | modified | `speech_check` key; the speech model counts as a needed VAD model for the installers | Change and test |
| `cli.py` `transcribe` | modified | A `Speech:` line first, before `Health:`; for no speech, a `WARNING:` line and no `Health:` or `Language:` line. Tests that assert line positions (`tests/integration/test_cli.py`, `tests/unit/test_cli_language.py`) need updating | Change and test |
| `cli.py` `status`, `doctor` | modified | `· no speech` marker, and no language marker for a no-speech transcript (`_language_segment` compares with `pt`, so a non-`pt` fallback would otherwise print `· en` for silence). The count line goes after `Degraded transcripts:` and the optional rate-mismatch line, before `Unconfirmed claims:`. The `speech check:` line goes after the retry line. | Change and test |
| `adapters/outbound/audio_convert.py` | new | `wav_convert_command`, moved out of `WhisperCppTranscriber.convert_command`. | Add |
| `transcriber_whispercpp.py` | modified | `convert_command` delegates to `audio_convert.wav_convert_command` and returns the same argv. No behavior change: `tests/unit/test_transcriber.py::test_commands` passes as written. | Extract |
| `messages.py`, `constants.py` | modified | New texts and constants (`Bin.WHISPER_VAD`, `Proc.SPEECH_CHECK_TIMEOUT`, `Parse.VAD_*`, `Log.NO_SPEECH_NOTIFY_FAILED`) | Add |
| `repository_fs.py` | unchanged | `save_transcript` keeps writing `as_timestamped_text() + "\n"`, so a no-speech `transcript.txt` holds one newline. The contract says "no lines", not "empty". | None |
| `tests/fixtures/` | new | `fake_whisper_vad.py`, a stand-in printing scripted segments | Add |
| Docs | modified | See the docs row below | Update in the last task |

Docs row:
- `docs/guide/configuration.md`: the `speech_check` row.
- `docs/guide/commands.md`: the `Speech:` line, `· no speech` and the doctor line.
- `docs/guide/troubleshooting.md`: "No speech in a recording", with the three-step recovery (check off, `trec transcribe <id>` and `trec analyze <id>`, check back on).
- `docs/prd/pages/02-transcription.md`: the step before transcription and the loop rule's short-line condition.
- `docs/prd/appendix/data-layout.md`: `transcript.json` `speech`.
- `AGENTS.md`: the ports table gets a `SpeechDetector` row.
- `docs/REQUIREMENTS-AND-ARCHITECTURE.md`: the transcription requirement, the ports table, the adapter catalogue, and a §10 entry with the gates. The language-detection §10 open questions (2) and (3) get marked as handled by this spec.

There are no delete targets. Old transcripts load unchanged (no `speech` key), and no public surface is removed.

## Agent Manageability Plan

Agents operate the feature through the same CLI as the user:
- `trec transcribe <id>`;
- `trec status` (`· no speech`);
- `trec doctor` (`speech check:`);
- `transcript.json` `speech`;
- the config key.

There is no structured `--json` output, and none is added; the files are the structured state.

## Config Lifecycle

- Added: `[transcription] speech_check = true`.
  - It is in `config.toml` with the comment from `_dx.md` and in `docs/guide/configuration.md`.
  - Parsed with `bool(...)`, like the neighboring flags. No other validation: a missing key means `true`.
- `vad_model` now also selects the model of the speech check.
- `scripts/config_tool.py` `vad_path` returns the speech model when the check is on, so `install.sh` and `install.ps1` download the Silero model even with `vad = false` and `retry_vad = false`.
- Tests: UT-025 and UT-026.

## Testing Approach

- **Fakes and stand-ins:**
  - Unit tests of `domain/speech.py` and `domain/health.py` need no fakes.
  - Use-case tests run on a new `FakeSpeechDetector` (scripted `SpeechActivity` or an exception, records calls) with the existing `FakeTranscriber`, `FakeLanguageDetector`, `FakeNotifier` and in-memory repository.
  - The adapter is tested with real ffmpeg against `tests/fixtures/fake_whisper_vad.py`, a stand-in that prints the real tool's format from `--segments 0:419,458:720`, `--none`, `--garbled`, `--fail` and `--log FILE`.
  - An opt-in real test (`TREC_REAL_WHISPER=1`) runs the real tool on a generated silent WAV and on a `say`-generated speech WAV (macOS).
- **Levels:**
  - unit tests: the rules, the parser, the codec, the config, the CLI lines;
  - integration tests: the adapter with real ffmpeg, and the use case wired to the adapter on the stand-in;
  - E2E: `trec transcribe` on a silent generated `audio.m4a` and on a speech one, through `CliRunner`.
- **Gates:** run once by hand on read-only copies of the stored recordings, never writing under `data/`, with no subscription use. They are G1, G2 and G3 in `_tests.md`.

## Development Sequencing

### Build Order

1. `domain/speech.py`, `Transcript.speech`, codec, config key, messages and constants. Gate: unit tests and `mypy`.
2. `SpeechDetector` port and `WhisperCppSpeechDetector`, with the stand-in. Gate: adapter tests and the opt-in real test.
3. `TranscribeMeeting` check and skip, notification, container wiring, and the `trec transcribe` lines (needs 1 and 2). This is the MVP. Gate: use-case tests, IT and E2E-001.
4. Language-sample filter and duration stand-in (needs 3). Gate: use-case tests.
5. Loop rule short-line condition (needs nothing). Gate: health tests.
6. `trec status`, `trec doctor`, `config_tool` (needs 1 and 3). Gate: CLI tests.
7. Gates G1–G3 and docs (needs all).

### Technical Dependencies

- `whisper-vad-speech-segments` and the Silero model, both present on the development Mac (`/opt/homebrew/bin`, `data/models/ggml-silero-v5.1.2.bin`).
- The daemon loads the code only after `trec agent restart`, which needs the user's approval.
- **whisper.cpp's `whisper-vad-speech-segments` target.** The check needs this binary next to `whisper-cli`. Today it comes from Homebrew `whisper-cpp`. The untracked `docs/tasks/no-homebrew/` draft builds only `whisper-cli` from source and does not list it. When that plan is next edited, it must build and install this target too (on PATH or in `<project>/tools`, where `find_tool` looks), or `trec doctor` warns on the speech check. This spec does not change that draft; it records the dependency here.
- **Gate inputs and audio retention.** The gates read stored audio, and `PurgeOldAudio` deletes `audio.m4a` 30 days after a meeting. The named gate recordings lose their audio from these dates:
  - 2026-10-08_02-50-26 and MARTA (2026-10-08_10-30-52): about 2026-11-07;
  - vans (2026-10-14_15-00-56): about 2026-11-13;
  - 2026-10-17_10-15-32: about 2026-11-16.

  The oldest other recordings (2026-10-05) lose theirs from about 2026-11-04. The gates therefore run on "every meeting with audio on the day", and the four named recordings are mandatory. If the gates cannot run before 2026-11-07, then before that date, and with the user's approval, the `audio.m4a` and `meta.json` of the four named recordings are copied read-only to a folder outside `data/` and outside the repository. Retention settings are not changed for them.

## Monitoring and Observability

Log lines (logger `teams_recorder.application.use_cases.processing`):

| Event | Level | Line (format in `messages.Log`) |
|---|---|---|
| Speech found | INFO | `speech in %s: %.1f of %.1f min (%d segments)` |
| No speech | WARNING | `no speech in %s: %.1f s of speech in %.1f min of audio (under %.1f s); whisper skipped, transcript empty` |
| Check failed | WARNING | `speech check of %s failed; transcribing without it: %s` |
| Samples dropped | INFO | `language samples of %s: %d of %d without speech, not sent` |
| No-speech notification failed | WARNING | `no-speech notification for %s failed: %s` |

No metrics or alerting: a personal tool. The notification is the alert.

## Technical Considerations

### Key Decisions

- **Whole-audio VAD with whisper.cpp's separate tool, before everything else (ADR-001).** One run gives the verdict, the per-sample speech and the audio length.
- **Skip samples without speech instead of moving them onto speech.** Skipping is a pure filter on the existing offsets and keeps the detector unchanged. Moving windows needs a placement rule, and the evidence shows that the meetings that need it have enough speech in their other samples. G2 checks this.
- **No speech means no health and no detection in the record**, rather than a health of "0 of N minutes covered". The health describes whisper's output, and whisper did not run. Readers that see `health is None` already treat it as unknown (the minutes, `status`).
- **The run condition for short lines** rather than "never count". Evidence: back-to-back "e aí" ×6 in a hallucinated transcript, and the user's choice on 2026-10-22.
- **`bool(...)` for the new key**, the same as the neighboring flags. A stricter validation for one key would be inconsistent; the general looseness is a known item (`docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10, fidelity-guard leftovers).

### Known Risks

- **False "no speech" on a real meeting.** The likelihood is low: real recordings measured 7.3 s and more, against a 2.0 s threshold. The mitigations are:
  - the notification at 60 s;
  - `trec status` marks the meeting;
  - the audio is kept 30 days;
  - the three-step recovery redoes it: `speech_check = false`, `trec transcribe <id>` and `trec analyze <id>`, then the check back on.
- **Extra time per meeting.** About 20 s of VAD plus a conversion for an 86-minute meeting, against about 12 minutes of whisper. Acceptable. Sharing the WAV with the transcriber is a possible later optimization, outside this spec.
- **The VAD tool's output format changes in a whisper.cpp update.** The parser requires the count line to match the segment lines and raises otherwise, so the change reads as a failed check (transcribe as today), never as "no speech". The opt-in real test catches it.
- **Windows.** If the release archive lacks the tool, the check is skipped with a warning and `trec doctor` reports it. Untested on hardware.
- **A spread-out short hallucination** ("Obrigado." every few lines, never 3 in a row) is no longer a loop. None appears in the stored transcripts. VAD on the retry and the first pass's `-mc` setting already limit such output.
- **Three frequent short replies back to back** ("Okay." "Yeah." "Right.", each repeated often enough for the window rule) still count as a loop under the adopted run rule. It did not happen in any stored or G2 transcript (Evidence table), and G3 re-measures it.
- **One sample decides.** Without the planned-count rule, the filter could leave one window to decide a long meeting. The rule makes that case fall back (Business Rules › Language samples).

## Safety Invariants

1. Whisper is skipped only when a check completed and measured under `min_speech_seconds`. A check that is off, missing or failed never skips whisper.
2. A failed check never writes `error.txt`, never notifies, and never changes the whisper commands.
3. The check writes nothing in the meeting folder. Its WAV lives in a temporary directory removed on success and failure, and its result reaches the folder only inside `transcript.json`.
4. A recording with speech gets the whisper commands (first pass and retry) that `speech_check = false` gives, for the language and duration the use case chose. With a fixed language they are byte-for-byte the check-off ones. In auto mode only the `-l` value can differ, and only through the language-sample filter, the planned-count rule and the duration stand-in.
5. A no-speech transcript has no segments, so `trec analyze` never calls the LLM for it (`trivial_analysis`, 0 words).
6. The check runs under the meeting's lock, inside `TranscribeMeeting.execute`, like every other step of the transcription.
7. The loop rule for lines of 3 or more words is unchanged. A short line is still flagged when the window rule flags it and it sits in a back-to-back run of 3 or more short, window-flagged lines, whatever their texts.
8. The no-speech notification never turns a saved transcript into a failed step: its exceptions are caught and logged.

## File References

### Repo Files

- `src/teams_recorder/application/use_cases/processing.py:32-205`: `TranscribeMeeting`, with `execute` (`:77`), `_language` (`:102`) and `_transcribe` (`:179`), the steps the check goes before and feeds.
- `src/teams_recorder/domain/language.py:13-92`: `LanguageRules` (`:13`), `sample_offsets` (`:52`) and `choose_language` (`:77`). The samples are filtered after `sample_offsets` and before `detect`, and `needed = 1 if len(kept) == 1` (line 87) is where `planned` goes.
- `src/teams_recorder/domain/health.py:22-50`: `_key`, `loop_flags`, `LOOP_REPEATS` and `LOOP_WINDOW`, where the short-line condition goes.
- `tests/unit/test_transcript_health.py:30-38,64-66`: the window test whose expected indices change, and the alternating-lines test that must keep passing.
- `src/teams_recorder/application/use_cases/processing.py:93-99`: the existing unguarded notifications. The no-speech one is guarded, these are not.
- `src/teams_recorder/adapters/outbound/repository_fs.py:189-192`: `save_transcript`, the trailing newline of `transcript.txt`.
- `src/teams_recorder/adapters/inbound/cli.py:527-570`: `trec analyze`, which re-analyzes an `analyzed` meeting only with an id.
- `src/teams_recorder/domain/models.py:97-163`: `TranscriptHealth` and `Transcript`, which gain the `speech` field.
- `src/teams_recorder/adapters/outbound/language_whispercpp.py`: the adapter pattern to mirror (temp dir, `_run`, errors as `TranscriptionError`, output tail).
- `src/teams_recorder/adapters/outbound/transcriber_whispercpp.py:43-60`: `convert_command` (the same conversion) and `Audio.VAD_ARGS` usage.
- `src/teams_recorder/adapters/outbound/codec.py:140-200`: `transcript_to_dict`, the coercing `language_detection` decoder (not to copy), and `_finite`, the type check to reuse.
- `src/teams_recorder/adapters/outbound/llm_schema.py:23-33`: `trivial_analysis`, the local empty analysis.
- `src/teams_recorder/container.py:132-136,214-285`: `Container.transcribe_meeting()` (`:132`), and `build_container` (`:214`) with the first-pass transcriber, `build_language_detector` (`:254`) and `build_retry_transcriber` (`:265`).
- `src/teams_recorder/config.py:50-61,81-146,280-315`: `find_tool`, the `Settings` VAD paths, and the `[transcription]` parsing, with `vad` at `:287` and `retry_vad` at `:310`.
- `src/teams_recorder/adapters/inbound/cli.py:81-130,197-230,241-335,472-512`: `status`, the language line helpers, `doctor` / `_check_transcript_health`, and `transcribe`.
- `src/teams_recorder/messages.py`, `src/teams_recorder/constants.py`: where every new text and constant goes.
- `scripts/config_tool.py:25`: `vad_path`, which the installers use to download the VAD model.
- `tests/fixtures/fake_whisper_cli.py`, `tests/fakes/__init__.py`: the stand-in and fake patterns.
- `docs/tasks/language-detection/_tests.md` › G1, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 "Language detection per meeting": the origin of this spec.

### Design and Analysis Sources

- `docs/tasks/language-detection/`: the gate results (G1 per meeting, G2 transcripts) the Evidence section extends.

## Assumptions and Defaults

- Thresholds: `min_speech_seconds = 2.0`, `min_sample_speech_seconds = 3.0`, `notify_min_audio_seconds = 60.0`, `SHORT_LINE_WORDS = 2`, `SHORT_LINE_RUN = 3`.
- VAD arguments: `Audio.VAD_ARGS` (`-vt 0.5 -vsd 300 -vp 150`), the same as the retry's.
- `speech_check = true` by default.
- The tool's name is `whisper-vad-speech-segments` (`Bin.WHISPER_VAD`). The output unit is centiseconds, verified on 2026-10-22: a 27.3 s file's last segment ends at `2067.00`.
- `Proc.SPEECH_CHECK_TIMEOUT = 300` s per command (conversion and VAD).
- The notification is sent from `TranscribeMeeting` through the container's notifier: a desktop notification in the daemon; in headless CLI runs, an info-level line from `LogNotifier` that the CLI does not show.
- A no-speech transcript's `language` is the fallback language. `trec status` prints no language marker for it, whatever the fallback, so a recording in which nobody spoke never shows `· en`.

## Architecture Decision Records

- [ADR-001: Whole-audio VAD with whisper.cpp's tool before transcription](adrs/adr-001.md): one Silero VAD run per meeting decides "no speech", feeds the language samples and measures the audio, instead of VAD on whisper's first pass, an ffmpeg volume threshold, or VAD only in the language detector.
