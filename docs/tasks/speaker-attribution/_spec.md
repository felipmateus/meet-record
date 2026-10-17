# Spec: Speaker attribution from the Teams window

> Slug `speaker-attribution` · Date 2026-10-16 · Status: draft for approval
> Requirements: [docs/tasks/speaker-attribution/prd.md](prd.md) (approved direction, four user decisions recorded there)
> Evidence: [docs/SPEAKER-ATTRIBUTION.md](../../SPEAKER-ATTRIBUTION.md) (investigation and eight spike runs)
> Companions: [user stories](_user_stories.md) · [developer experience](_dx.md) · [tests](_tests.md) · [ADR-001](adrs/adr-001.md) · [ADR-002](adrs/adr-002.md)

---

# Part I — Product

## Overview

- **Motivating Problem**: the transcript of a Teams meeting does not say who said each line, so the analysis guesses owners and participants from the words alone: 22 of the 57 wrong claims measured in the fidelity evaluation had the wrong owner and 14 listed as a participant someone only mentioned, and one wrong owner reached six daily plans. The simplest end-to-end behavior that solves it: after a recorded meeting, `transcript.txt` shows the display name of the person who said each line whenever Teams showed who was speaking, the user's own lines carry the user's name, and the minutes' action table names owners taken from those lines.
- **Who it is for**: the single user of teams-recorder, who attends several Teams meetings a day and reads the minutes, the daily plan and the story drafts built from them.
- **Why it is valuable**: owners, participants and titles stop being guesses. No voice is modelled and no voiceprint is kept, so people who come and go between meetings cost nothing; everything stays on the Mac.

## Goals

- After this ships, the user reads a transcript where each line names its speaker when Teams showed one, instead of inferring speakers from context.
- The system guarantees that a commitment made on a labelled line is attributed to that person in the analysis, and that the user's own commitments are attributed to the user without the first-person heuristic.
- The minutes list the people who were in the meeting window, and an automatic recording gets the meeting's subject as its title, so inventing titles and participants becomes unnecessary.
- A recording never waits for or fails because of the labels; when they cannot be read, the pipeline behaves as today and says so once a day.

## User Stories

- US-001 to US-003: labelled lines (remote speakers, the user's own lines, unlabelled fallbacks).
- US-004 to US-006: what the analysis does with labels (owners, participants from the roster, the meeting title).
- US-007 to US-009: operation (recording never depends on the observer, the daily notice, diagnostics in `trec doctor`, `trec status` and `trec transcribe`).
- US-010 to US-011: installation, permission and compatibility with existing meetings.
- [Full user stories](_user_stories.md)

## Core Features

- **Speaker observer.** During every recording, a helper reads the Teams meeting windows and records who is speaking, moment by moment, together with the names it saw, the user's own display name and the meeting subject. Requirements: it runs for the whole recording; it samples at least twice per second; it records the main meeting window and the compact view; it records when a window is found or lost; it never changes anything in Teams.
- **The user's own lines.** The two recorded tracks already separate the user from everyone else; before the raw tracks are deleted, the level of each is measured over time so a line said by the user can be told apart later.
- **Labelling at transcription.** Each transcript line gets the remote participant who was speaking during it, else the user when the microphone dominated, else no label. Labels are visible in the transcript file and in what the model reads.
- **Analysis on labels.** Owners come from labelled lines; the participants list is the roster when it was read; the recording's title is the window's subject when the recording had none; the claim verifier knows labels are reliable attribution.
- **Fail-soft operation and diagnostics.** The observer can be missing, unauthorised, blind or dead without the recording noticing; `trec doctor` shows its state and how to grant the permission; `trec transcribe` and `trec status` show how much of each transcript is labelled; a day's first unlabelled meeting raises one notification with the reason; the helper and the pipeline log what a bug report needs.

Interaction: the observer and the level measurement produce two inputs; labelling consumes both and writes the transcript; the analysis and the verifier read the labelled transcript; the minutes and the status read the labelled transcript's share and the roster.

## Business Rules

- A line is attributed to a remote participant when their speaking interval covers at least 30% of the line; among several, the largest overlap wins.
- A line is the user's when no remote participant qualifies and, over the line, the microphone track is at least 6 dB louder than the Teams track and above −50 dBFS.
- A line with neither evidence has no label and is treated as today.
- The user's label is the configured user name; without one, the display name of the user's own tile; without either, "Você".
- A participant is speaking when either Teams window (main or compact) shows them speaking; a window that disappears ends the speaking state of its tiles.
- When the roster was read, the minutes' participants are exactly the names seen in the meeting window; the model adds nobody. Without a roster, the current rule (people who speak or are addressed) applies.
- The meeting subject read from the window becomes the title only when the recording has no title; the analysis's title is used only when neither exists.
- Thresholds (30%, 6 dB, −50 dBFS) are fixed constants in this delivery; changing them is a code change recorded in the PRD.
- A line is eligible for a label only when its text is speech (whisper's non-speech markers are not) and its duration is positive; a remote turn qualifies only with a positive overlap; among equal overlaps the turn that started first wins.
- The energy comparison uses the power mean of each track's levels over the windows whose midpoint falls inside the line (silence windows count as near-zero power); a line with no window inside it gets no energy label.
- The roster, the user's label and a labelling summary (lines labelled, lines eligible, the reason when none) are stored with the transcript, so the analysis, the verification, `trec status` and `trec transcribe` read them from there.
- A participant in the roster who never spoke is not flagged by the participant code check; the verifier receives the roster as evidence of presence and decides.
- The first meeting transcribed on a calendar day (the day the transcription runs) whose transcript has zero labels and whose observer was wired (the events file exists) raises one notification naming the reason, for these reasons: helper not built, permission missing, failed to start, died before reading a window, no window read. "Events found but no line matched" only logs. Meetings without observer data (feature off, Windows, recorded before this feature) never notify. Later unlabelled meetings that day only log.
- The observer's absence or failure never raises an error for the recording, the mixing, the transcription or the analysis.
- The observer never sets any accessibility attribute on Teams; it only reads.
- Events and levels are kept with the meeting and deleted with it; they name nothing the transcript does not already name.

## User Experience

- **Persona: the user** (owner of the Mac and the Teams account). Journey: builds the helper with the existing native build script, grants the Accessibility permission once (the installer and `trec doctor` tell how), keeps a Teams window visible during meetings as they already do, and reads transcripts and minutes with names. Nothing else to do per meeting.
- **Persona: the operator** (the same person maintaining the install). Journey: `trec doctor` says whether the helper is built and authorised; after a Teams update, `speakers.log` and the events file show what the helper saw; `trec status` shows which meetings got labels.
- Accessibility: the helper is itself an assistive-technology client; it needs the Accessibility permission and nothing from the user during meetings.
- Discoverability: the installer names the third permission; `trec doctor` names the exact command that requests it; the README explains the visible-window constraint.

## High-Level Technical Constraints

- Integrates with the existing recording flow (two tracks aligned to the meeting start) and the file-based meeting state; no database, no network.
- Privacy: nothing leaves the Mac; the observer only reads the Teams windows; names appear only where the transcript already carries them.
- Performance from the user's view: Teams stays responsive with the observer attached; the helper averages under 10% of one CPU core.
- Manageability: `trec doctor` for the permission and build, `trec status` and `trec transcribe` for coverage, logs for everything else; no graphical interface.
- Platform: macOS only in this delivery; Windows keeps recording without labels.

## Non-Goals (Out of Scope)

- Voice identification (a voiceprint per person): the premise of the PRD.
- Voice clustering as a fallback when the window cannot be read: considered after gates G1–G2 of the PRD measure the window's coverage.
- Windows parity (reading the Teams window through UI Automation): a follow-up after the macOS behaviour settles.
- Reading the live captions pane, Teams' own transcript or a media bot.
- Driving Teams in any way (focusing, pinning the compact view, switching to "active speaker only").
- A "said by" column in the minutes: the owner column already carries the attribution (PRD Q3, proposal adopted).

## Open Questions

- None blocking on the product side. The PRD's three open questions were adopted with their proposed answers: the daily notification carries only the reason; the observer runs for manual recordings too; the minutes gain no "said by" column.
- One technical question is open after the first live run (task_02, 2026-10-17): whether the helper must ask Chromium for its accessibility tree (the `AXEnhancedUserInterface` request the spike probe made and invariant 4 forbids). It is settled by repeating the live run after Teams restarts, without the probe; if the tiles do not appear, invariant 4 needs the user's decision.
- Settled on 2026-10-17 (task_03): the daemon starts the helper as its own launchd job, the only context in which the helper's own Accessibility grant applies.

---

# Part II — Technical

## Executive Summary

A new native helper, `teams-speakers`, polls the Teams meeting windows through the macOS Accessibility API during each recording and appends JSON lines describing who is speaking (the speaking state is the `vdi-frame-occlusion` class set on a participant tile's frame element; ADR-001). Before the raw tracks are deleted, an ffmpeg pass measures each track's level per 100 ms (ADR-002). At transcription, a pure domain function labels every whisper segment from those two inputs; the label is a new optional field on `Segment`, rendered as `[HH:MM:SS] Name: text` everywhere the transcript is shown or sent to a model; the roster, the user's label and a labelling summary travel on the `Transcript` itself, so the analyzer, the verifier and the status read them without new port parameters. Everything is additive: old transcripts, active-recording pointers and analyses load unchanged, and every new path fails soft with a log line.

## MVP Boundary

MVP = tasks 1–5 of the task breakdown (domain and files; the helper; ports, adapters and wiring; recording and transcription use cases; the prompts and the transcript rendering). Slice 1 ships the Motivating Problem: a recorded meeting whose `transcript.txt` names the speaker of each labelled line and whose analysis takes owners from those lines. Post-MVP, in the same spec: the roster as participants, the title from the window, `trec doctor`/`status`/`transcribe` lines, the daily notification, installer and documentation. Out of scope: voice clustering, Windows parity, captions, Graph (PRD §4).

## Developer Experience

- [Developer experience contract](_dx.md) — the helper's command line and exit codes; the per-meeting files `speakers.jsonl` and `energy.json`; the `[speakers]` config key; the `trec doctor`, `trec status` and `trec transcribe` lines; the transcript line format; the notification; the error surface.
- No `_uiux.md`: the product has no graphical interface.

## System Architecture

```
teams-tap (Teams audio) ──┐
teams-tap --mic ──────────┼─► raw tracks ─► StopRecording.finalize ─► EnergyMeter ─► energy.json ─► mix ─► audio.m4a
teams-speakers (new) ─────┘   speakers.jsonl (events, roster, me, subject)                     (tracks deleted)
                                                                                                       │
whisper ─► Transcript ─► label_segments(transcript, SpeakerLog, energy) ─► Segment.speaker ─► transcript.json/txt
                                                                                  │
                                            analyzer / verifier messages ◄────────┘  (names on labelled lines, roster in the header)
```

- **`teams-speakers`** (`native/teams-speakers`, Swift): finds the Teams application, polls its windows, identifies participant tiles and their frame element, writes events. Read-only on Teams. Logs to stderr, which the spawner redirects to `data/log/speakers.log`.
- **`speakers_ax.AxSpeakerObserver`** (adapter): spawns and stops the helper like `capture_coreaudio` does for `teams-tap`; checks the permission with `--check`; reports problems for `trec doctor`.
- **`energy_ffmpeg.FfmpegEnergyMeter`** (adapter): one ffmpeg pass per track producing the RMS level per 100 ms window.
- **`domain/speakers.py`**: events → speaking turns; turns + energy → segment labels; roster, user label and subject extraction. Pure.
- **Use cases**: `StartRecording` starts the observer after both recorders (fail-soft); `StopRecording` stops it, measures energy before deleting the tracks, applies the window subject as the title; `CancelRecording` stops it; `TranscribeMeeting` labels after whisper and raises the daily notice.
- **Downstream**: `Transcript.as_timestamped_text` renders labels; `llm_schema.build_user_message` adds the roster and the user-label note from the transcript; `verifier_claude.user_message` adds the roster as evidence of presence and `transcript_for` renders labels; `participant_heard` accepts a labelled speaker or a roster name; `minutes_markdown` unchanged (the analysis's participants are already the roster when it was read).
- **CLI**: `trec doctor` line; `trec transcribe` and `trec status` coverage lines.

## Architectural Boundaries

- Import direction stays `domain ← application ← adapters/container`. The domain gains `domain/speakers.py` (pure, no I/O) and fields on `Segment`/`Transcript`; `domain/status.py` gains the two file names.
- New ports in `application/ports.py`: `SpeakerObserver`, `EnergyMeter`. New adapters: `adapters/outbound/speakers_ax.py`, `adapters/outbound/energy_ffmpeg.py`. The repository gains the loaders/savers for the two files and the daily-notice marker; the codec gains the parsers. Adapters do not import each other (the pattern of `codec` ← `repository_fs` is kept).
- `container.build_container` is the only place that instantiates `AxSpeakerObserver` (macOS, `[speakers] enabled`) and `FfmpegEnergyMeter`; `_windows_adapters` passes `speakers=None`.
- The helper is a separate Swift package (`native/teams-speakers/Package.swift`), built by `scripts/build-native.sh` next to `teams-tap`; it shares no code with `teams-tap`.
- Strings: every user-facing text in `messages.py`, identifiers and defaults in `constants.py` (`Speakers` class), file names in `domain/status.py`; enforced by `tests/unit/test_no_hardcoded_strings.py`.

## Implementation Design

### Core Interfaces

```python
# application/ports.py
@runtime_checkable
class SpeakerObserver(Protocol):
    def start(self, out: Path, epoch: float) -> CaptureHandle:
        """Starts reading the Teams windows into `out` (JSON lines). Raises SpeakersUnavailable(reason) when it cannot."""
    def stop(self, handle: CaptureHandle) -> Path: ...
    def stop_stale(self) -> None:
        """Boots out the fixed-label job left with no handle to name it (a start that crashed between the bootstrap and the
        persisting of the handle); nothing when none is. Review round 2, issue 041."""
    def is_running(self, handle: CaptureHandle) -> bool: ...
    def problems(self) -> list[str]:
        """What keeps it from running (binary missing, permission missing); empty when ready. Shown by `trec doctor`."""

@runtime_checkable
class EnergyMeter(Protocol):
    def measure(self, track: Path) -> EnergyTimeline:
        """RMS level per fixed step over the whole track. Raises CaptureError on failure."""

@dataclass
class ActiveRecording:
    meeting: Meeting
    process_handle: CaptureHandle
    mic_handle: CaptureHandle
    speakers_handle: CaptureHandle | None = None   # None: the observer did not start (reason in speakers.jsonl)

# domain/models.py
@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None   # display name of who said it, when known

@dataclass(frozen=True)
class LabelSummary:
    """What labelling did to a transcript; absent on transcripts made before this feature."""
    labelled: int                    # eligible segments that got a label
    eligible: int                    # segments with speech text and a positive duration
    reason: str | None               # a Speakers.Reason code when labelled == 0, else None

class Transcript:
    segments: list[Segment]
    language: str
    health: TranscriptHealth | None
    roster: tuple[str, ...] = ()          # names seen in the meeting window, in order of first appearance (empty: none read)
    user_label: str | None = None         # the label the user's lines carry, when labelling ran
    labels: LabelSummary | None = None    # None: labelling never ran (old transcripts)
    def as_timestamped_text(self) -> str: ...   # "[HH:MM:SS] Name: text" when speaker is set
    @property
    def speakers(self) -> list[str]: ...        # distinct labels, in order of first appearance

def is_speech(text: str) -> bool: ...   # moved from domain/health.py (which re-exports it): whisper's non-speech markers are not speech

# domain/speakers.py
@dataclass(frozen=True)
class SpeakerEvent:
    at: float          # seconds since the recording start (converted from wall-clock by the codec)
    name: str
    speaking: bool
    window: str = ""   # "main" | "compact"

@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    name: str

@dataclass(frozen=True)
class SpeakerLog:
    """What the observer left for one meeting."""
    turns: tuple[SpeakerTurn, ...]
    roster: tuple[str, ...]          # names seen, in order of first appearance, the user's own tile included
    me: str | None                   # the user's own display name, from the "Vídeo de mim mesmo" tile
    subject: str | None              # the meeting subject read from the window title
    ended: bool                      # a "stop" event was read (the helper stopped normally)
    unavailable: str | None = None   # reason code when the observer never ran (see Speakers.Reason)

@dataclass(frozen=True)
class EnergyTimeline:
    step: float                      # seconds per window (0.1)
    levels: tuple[float, ...]        # dBFS per window; Speakers.SILENCE_DB (-120.0) for digital silence

@dataclass(frozen=True)
class LabelRules:
    min_overlap: float = 0.30        # share of the segment a remote turn must cover
    user_margin_db: float = 6.0      # microphone over Teams track
    user_floor_db: float = -50.0     # microphone must be above this

def turns_from_events(events: Iterable[SpeakerEvent], end: float) -> tuple[SpeakerTurn, ...]: ...
def label_segments(transcript: Transcript, log: SpeakerLog | None, mic: EnergyTimeline | None,
                   tap: EnergyTimeline | None, user_label: str, rules: LabelRules = LabelRules()) -> Transcript:
    """A copy with `speaker` on the labelled segments and `roster`, `user_label` and `labels` filled in."""
def user_label(configured_name: str, log: SpeakerLog | None, fallback: str) -> str: ...
def no_label_reason(log: SpeakerLog | None, labelled: int) -> str | None:
    """Total over every state of the events file: no file → "no-observer"; an `unavailable` line → its code; no roster and
    not ended → "observer-died"; no roster and ended → "no-window"; a roster but labelled == 0 → "no-match"; else None."""

# application/ports.py — MeetingRepository additions (the fake in tests/fakes mirrors them)
class MeetingRepository(Protocol):
    def write_speakers_unavailable(self, meeting_id: str, reason: str) -> None:
        """Replaces speakers.jsonl atomically with the single `unavailable` line (the helper is not running by then)."""
    def load_speaker_log(self, meeting_id: str, fallback_epoch: float, end: float) -> SpeakerLog | None:
        """None when the file is absent; RepositoryError when unreadable. Times are made relative to the `start` event's
        epoch, or to `fallback_epoch` (the meeting's start) when that event is missing. An `unavailable` line wins over
        anything else in the file."""
    def save_energy(self, meeting_id: str, energy: dict[str, EnergyTimeline]) -> None: ...   # atomic write of energy.json
    def load_energy(self, meeting_id: str) -> dict[str, EnergyTimeline]:
        """{} when absent; RepositoryError when unreadable or of the wrong shape."""
    def last_notice_day(self, key: str) -> date | None:
        """The day stored for a notice key (<data_dir>/notices/<key>); None when absent or unreadable."""
    def save_notice_day(self, key: str, day: date) -> None: ...   # atomic rewrite

# application/use_cases/processing.py
@dataclass
class TranscribeMeeting:
    ...                       # existing fields unchanged
    clock: Clock | None = None       # the day of the daily notice (clock.now().date() at transcription); None: no notice
    user_name: str = ""              # [user] name: the user's label when set

# domain/errors.py
class SpeakersUnavailable(CaptureError):
    """The observer cannot run; `reason` is a Speakers.Reason code (binary-missing, permission-missing, start-failed)."""
```

```swift
// native/teams-speakers — command line (the contract the adapter builds)
// teams-speakers --out <speakers.jsonl> --epoch <unix s> [--interval 0.5] [--bundle com.microsoft.teams2] [--verbose]
// teams-speakers --check [--prompt]        exit 0 granted, 3 missing
// Exit codes: 0 ok · 2 usage (--epoch and --out are required) · 3 Accessibility permission missing · 4 output not writable
// Every JSON line is flushed as it is written. Stops on SIGTERM/SIGINT; writes a "stop" event last.
// Read-only: the source contains no AXUIElementSetAttributeValue call (checked by a unit test that greps the sources).
```

### Data Models

Per-meeting files (the state is the files; `domain/status.py` owns the names):

| Field | Shape | Purpose |
| --- | --- | --- |
| `speakers.jsonl` | one JSON object per line, append-only, written by the helper (or one `unavailable` line by the use case) | the observer's record: events, roster, me, subject, counters |
| `energy.json` | `{"step_seconds": 0.1, "tracks": {"tap.wav": [dBFS…], "mic.wav": [dBFS…]}}` | levels of each raw track before deletion |
| `transcript.json` › `segments[].speaker` | string or absent | the label; absent on segments without one and on every transcript written before this feature |
| `transcript.json` › `speakers` | `{"roster": [names], "user_label": string or null, "labelled": int, "eligible": int, "reason": code or null}` or absent | the labelling summary; absent on transcripts made before this feature, present (possibly with `labelled: 0`) on every transcript labelling ran on, so `trec status` can tell drift from an old meeting |
| `current_recording.json` › `speakers_handle` | `{"pid": int, "out": path}` or absent | lets `trec stop` in another process stop the helper |
| `<data_dir>/notices/speaker-labels` | one line, ISO date | the day (of the transcription) of the last "no labels" notification (FR7's once a day); unreadable = absent |

Events in `speakers.jsonl` (`t` is Unix seconds as a float; `version` 1):

| Field | Shape | Purpose |
| --- | --- | --- |
| `event: "start"` | `epoch` (float, required: the recording's start instant the adapter passed), `interval`, `teams_pid`, `version` | the time origin for every event (the meeting's start instant is only the fallback when this event is missing) and diagnostics |
| `event: "window"` | `kind` (`main`/`compact`), `state` (`found`/`lost`/`frozen`), `title` | which windows were read and when; `frozen` when the window's call timer (`#call-duration-custom`) has not changed for 3 s while present (a covered window stops rendering, run 6): its open turns close with `speaking: false` first, and a later change of the timer counts as `found` again |
| `event: "title"` | `subject` | the meeting subject (first title segment; second for the compact view) |
| `event: "seen"` | `name`, `me` (bool), `window` | a participant tile seen for the first time in that window |
| `event: "speaking"` | `name`, `speaking` (bool), `window` | the frame class set appeared or disappeared on that tile |
| `event: "heartbeat"` | (`t` only), every 5 s | proof the helper was alive: a turn without a closing event ends at the last event of the file, so a dead helper credits nobody with the lines after its last heartbeat (review round 2, issue 001) |
| `event: "stop"` | `reason`, `passes`, `transitions`, `ax_errors`, `slow_passes` | how the run ended and what it cost |
| `event: "unavailable"` | `reason` (`binary-missing`/`permission-missing`/`start-failed`) | written by `StartRecording` (through the repository, as an atomic replace of the file) when the helper could not start; the only line the Python side writes, and it wins on read |

Reason codes (`domain.SpeakerReason`, a `StrEnum` whose `notifies` says whether the daily notice fires; in the domain because the domain imports nothing outside itself), derived by `no_label_reason`, and what each one does:

| Field | Shape | Purpose |
| --- | --- | --- |
| `binary-missing` | from the `unavailable` line | the helper is not built; notifies |
| `permission-missing` | from the `unavailable` line (`--check` exit 3 before spawning) | notifies |
| `start-failed` | from the `unavailable` line (any early exit after `--check` passed) | notifies |
| `observer-died` | file without `stop` and without `seen` | the helper died before reading a window; notifies |
| `no-window` | `stop` present, no `seen` | no Teams window was read during the call; notifies |
| `no-match` | `seen` present, zero labels | tiles were read but no line matched (drift, or a very short meeting); logs only |
| `no-observer` | no `speakers.jsonl` | feature off, Windows, or a meeting recorded before this feature; never notifies |

Side-table vs JSON, in this project's terms: there is no database, and matchable state lives on the entity that is matched. The labels are therefore a field of each `Segment` in `transcript.json` (the transcript is what the analysis, the verifier and the status read), while the raw events stay an opaque JSON-lines log that only the labeller and a human reading a bug report consume. The roster and the subject are not duplicated into `meta.json`: the subject becomes `Meeting.title` (existing field) when applicable, and the roster, the user's label and the summary are written once into `transcript.json` by the labelling step, which is where the analyzer's and the verifier's messages read them (no port gains a parameter).

Config (`config.toml`, loaded into `Settings.speakers_enabled: bool = True`):

| Field | Shape | Purpose |
| --- | --- | --- |
| `[speakers] enabled` | bool, default `true` | start the observer with each recording on macOS; `false` = no helper, no window labels (the user's lines are still labelled from the microphone track) |

### Label rules (pure functions)

- `turns_from_events`: per `(window, name)`, a `speaking: true` opens a turn and the next `speaking: false` closes it; a `window … lost` or `frozen` event closes that window's open turns; a turn still open at the end of the events closes at the time of the **last event of the file** (a `stop`, a `heartbeat` or any other), never at the meeting's end, so a helper that died or a window that froze credits nobody with later lines; turns of the same name from both windows are merged by union.
- Eligibility: a segment is labelled and counted only when `is_speech(text)` and `end > start`; segments inside a hallucination loop are treated like any other (labels do not depend on health).
- `label_segments`, per eligible segment: overlap of each remote name's turns with `[start, end]`; a name qualifies when its overlap is positive and ≥ `min_overlap × duration`; the largest overlap wins, ties broken by the earliest turn start, then by name. Else, with both timelines present, the **power mean** of each track over the windows whose midpoint lies in `[start, end]` (`10·log10(mean(10^(level/10)))`, so a −120 dBFS silence window weighs almost nothing and a half-silent remote burst still reads near its speaking level): `mic − tap ≥ user_margin_db` and `mic ≥ user_floor_db` → `user_label`. No window inside the segment → no energy label. Else `speaker=None`. The user's own name never comes from turns (the own tile exposes no frame).
- The copy returned carries `roster = log.roster` (or `()`), `user_label`, and `labels = LabelSummary(labelled, eligible, no_label_reason(log, labelled))`.
- `user_label`: `configured_name` if not empty, else `log.me`, else `fallback` (`Minutes.SPEAKER_USER_FALLBACK = "Você"`). When it is not the configured name, the analyzer's message says which label marks the recording owner, so the `usuário` literal still applies to those lines.

### API Endpoints

Not applicable: no network surface. The command-line surface is in `_dx.md`.

## Integration Points

- **Microsoft Teams, through the macOS Accessibility API** (read-only): roles, titles, descriptions, `AXDOMClassList`. Failure handling: an AX error on an element skips it and counts; no window with tiles for 30 s logs once a minute; Teams gone → keep polling until stopped. Retry: none needed, the next pass is 0.5 s away.
- **ffmpeg** (existing dependency) for the energy pass: `-af aresample=16000,asetnsamples=n=1600,astats=metadata=1:reset=1,ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-`; a non-zero exit, a timeout or unparsable output is a `CaptureError` caught by `finalize`, which logs and continues without `energy.json`.
- **macOS TCC** for the Accessibility permission: `AXIsProcessTrustedWithOptions` with the prompt only under `--check --prompt`; the helper carries an embedded `Info.plist` (bundle id `local.teams-recorder.teams-speakers`) like `teams-tap`. **The helper runs as its own launchd job** (measured on 2026-10-17, task_03; decided by the user the same day): spawned by the daemon's Python, the helper's `--check` reports the permission missing even with the helper granted, because macOS holds the daemon's Python responsible; started as its own LaunchAgent job it reports it granted. So, for every recording, the observer adapter writes a per-recording job definition (label `local.teams-recorder.speakers`, `ProgramArguments` = the helper with `--out` and `--epoch`, `RunAtLoad`, no `KeepAlive`, `ProcessType` Background, stderr appended to `data/log/speakers.log`) into `<data_dir>/run/`, boots out any stale job with that label, bootstraps it in the user's GUI domain, and reads its pid from `launchctl print`. Stopping boots the job out (launchd sends SIGTERM and waits) and falls back to SIGTERM by pid. The permission check runs the same way, as a short-lived job (`local.teams-recorder.speakers-check`, `--check`), because a `--check` run from a terminal or from the daemon reports the permission of that context instead. The Accessibility list needs the helper added by hand (the `+` button and its path): a background job's request shows no entry. The helper is signed ad hoc, so rebuilding it can drop the grant; `trec doctor` tells.

## Impact Analysis

| Component | Impact Type | Description and Risk | Required Action |
| --- | --- | --- | --- |
| `domain/models.py` (`Segment`, `Transcript`), `domain/speakers.py`, `domain/errors.py`, `domain/status.py` | modified / new | optional `speaker` field, rendering with names, pure labelling; low risk, additive | codec defaults; tests on old shapes |
| `application/ports.py`, `use_cases/recording.py`, `use_cases/processing.py` | modified | two ports, observer lifecycle, energy before deletion, labelling after whisper, daily notice; medium risk (recording path) | fail-soft on every new call; tests on fakes |
| `adapters/outbound/codec.py`, `repository_fs.py` | modified | events/energy/notice persistence, `speakers_handle` in the pointer; low risk | backward-compatible readers |
| `adapters/outbound/speakers_ax.py`, `energy_ffmpeg.py` | new | process spawning like `capture_coreaudio`; ffmpeg parsing | scripted stand-ins in tests |
| `native/teams-speakers` | new | Swift helper; Teams UI drift is the main risk | diagnostics in events and log; the probe stays for re-discovery |
| `prompts/analyze_system.md`, `prompts/verify_system.md`, `llm_schema.py`, `verifier_claude.py`, `domain/verification.py` | modified | labels, the roster and the user-label note in the model's input, read from the transcript; `participant_heard` accepts roster names; pinned sentences change | update the prompt-pin tests; fidelity gate later |
| `tests/unit/test_verifier_claude.py:151-166` (the shipped verifier prompt equals the measured prototype up to two replacements) | modified | the label sentence is a third allowed replacement; the §14.3 numbers predate it (decision below) | add the replacement; re-measure in the fidelity gate |
| `MeetingAnalyzer`, `ClaimVerifier`, `AnalyzeMeeting`, `VerifyAnalysis`, `FakeAnalyzer` | unchanged | the roster and the user label travel on the `Transcript`, so no signature changes | none |
| `adapters/inbound/cli.py`, `daemon.py`, `container.py`, `config.py`, `messages.py`, `constants.py` | modified | doctor/status/transcribe lines, watch the helper, wiring, `[speakers]` | tests for config and CLI helpers |
| `scripts/build-native.sh`, `scripts/install.sh`, README, PRD pages, requirements §10, AGENTS.md | modified | second binary, third permission | documentation task |

Compatibility (project policy: files are the state; readers tolerate older files):
- **User state migrates losslessly:** nothing is rewritten. `transcript.json` without `speaker`, `current_recording.json` without `speakers_handle`, meetings without `speakers.jsonl`/`energy.json` all load and behave as today. A `speakers_handle` written by the new code and read by old code is ignored (old readers take only the two handles).
- **Public surfaces:** `transcript.txt` gains `Name: ` after the timestamp on labelled lines only; consumers that parse `[HH:MM:SS] ` prefixes keep working. CLI lines are added, none removed. No shim needed: nothing is removed or renamed.
- **Delete targets:** none. The spike script `scripts/ax-speaker-probe.swift` stays as a diagnostic tool (hard cut only if the helper gains a `--probe` mode later; not in this spec).
- **No fallback / no compat shim / no placeholder** for internal code: the observer is wired in the container or not at all (Windows passes `None`); there is no stub observer.

## Extensibility Integration Plan

Not applicable: the project exposes no extension surface (checked: no plugin, hook or MCP surface exists in the repository).

## Agent Manageability Plan

Operated through the CLI only (there is no UI): `trec doctor` (helper build and permission, with the request command), `trec status` (share of labelled lines per meeting), `trec transcribe` (share and reason after each transcription), the helper's own `--check` exit code (0 granted, 3 missing). Structured records: `speakers.jsonl` events and `speakers.log`. Deterministic errors are in `_dx.md` › Errors.

## Config Lifecycle

- Added: `[speakers] enabled` (default `true`, bool). Read in `config.load_settings`; `Settings.speakers_enabled`. Unknown or non-bool values follow the existing `bool(...)` coercion of the other flags.
- Changed: none. Removed: none.
- Documented in `config.toml` (comment block), README (permissions and configuration tables), `docs/prd/pages/01-manual-recording.md` and `02-transcription.md`.
- Tests: `tests/unit/test_config.py` (default and override).

## Testing Approach

- Unit tests on the pure domain (`label_segments`, `turns_from_events`, rendering), the codec (events, energy, old shapes), the adapters' command shapes and parsers, and the use cases on fakes (`FakeSpeakerObserver`, `FakeEnergyMeter` in `tests/fakes`). Fakes sit at the process and file boundaries only.
- Integration tests with scripted stand-ins (`tests/fixtures/fake_speakers.py`, the existing `fake_recorder.py` pattern with a readiness file) for spawning, stopping and `--check`; real ffmpeg on a generated two-tone WAV for the energy meter (skipped when ffmpeg is missing).
- The Swift helper is checked by `swiftc -typecheck` in the build and by a manual run during a real meeting (PRD gates G1–G2); no automated Teams UI test is possible.
- Concrete cases: [tests](_tests.md).

## Development Sequencing

### Build Order

0. Permission identity spike — done 2026-10-17 (task_03): the helper runs as its own launchd job (Integration Points › macOS TCC).
1. Domain and persistence: `Segment.speaker`, `Transcript` fields and rendering, `LabelSummary`, `is_speech` in `models.py`, `domain/speakers.py`, `SpeakersUnavailable`, file names, codec parsers/writers (origin from the `start` event, `unavailable` wins), repository loaders/savers and the notice marker. Gate: unit tests on old and new shapes.
2. The helper: `native/teams-speakers` package, `--check`, event stream with per-line flush and a mandatory `--epoch`, build script (which also greps the sources for `AXUIElementSetAttributeValue` and fails if found). Gate: `swiftc -typecheck`, a run against a live Teams call writes the documented events.
3. Ports, adapters, config and wiring: `SpeakerObserver`, `EnergyMeter`, `speakers_ax`, `energy_ffmpeg`, `[speakers]`, container, fakes. Gate: adapter tests with the stand-ins; real ffmpeg test.
4. Use cases: observer lifecycle in `StartRecording`/`StopRecording`/`CancelRecording`, energy before deletion, the title from the subject, labelling in `TranscribeMeeting`, the daemon watching the helper, the daily notice. Gate: use-case tests on fakes.
5. Model input and rendering: prompts, `build_user_message` roster header, `transcript_for` labels, `participant_heard`. Gate: prompt-pin tests.
6. CLI and notification lines, installer, README, PRD pages, requirements §10, AGENTS.md. Gate: CLI helper tests, `trec doctor` on the dev Mac.

Slices for the task breakdown: slice 1 = steps 0–5 minus the roster/title parts (labelled transcripts reaching the analyzer); slice 2 = roster, title, coverage lines, notification, docs.

### Technical Dependencies

- Xcode command line tools (already required for `teams-tap`); macOS 14.2+ (the package platform of `teams-tap`).
- The Accessibility permission granted on the user's Mac to whichever identity task 0 determines (user action, outside the code); the spike itself needs the user's approval to run from the installed daemon.
- `trec agent restart` after the Python changes, with the user's approval (AGENTS.md).

## Monitoring and Observability

- `data/log/speakers.log` (helper stderr): start arguments, permission state, Teams pid, window found/lost, tile seen/lost, each state change, passes slower than 1 s with their element count, accessibility error counts per minute, exit reason.
- Daemon/pipeline log (`Log` templates): `SPEAKERS_STARTED`, `SPEAKERS_UNAVAILABLE` (reason), `SPEAKERS_STOP_FAILED`, `SPEAKERS_DIED` (watched like the recorders), `ENERGY_MEASURED` (per track, seconds, windows), `ENERGY_FAILED`, `TITLE_FROM_WINDOW`, `SPEAKERS_LABELLED` (labelled, total, names), `SPEAKERS_LABEL_FAILED`, `NO_SPEAKER_LABELS` (reason, notified or not).
- Per-meeting counters in the `stop` event: passes, transitions, ax_errors, slow_passes.
- No alerting beyond the daily notification; `trec status` is the dashboard.

## Technical Considerations

### Key Decisions

- **Polling, not AX notifications.** `AXObserver` notifications for attribute changes on web content are unreliable in Chromium; a 0.5 s poll of ~1,200 elements measured at ~1 pass/s in the spike and is simple. Trade-off: 0.5–1 s resolution, acceptable for whisper segments of several seconds.
- **Frame class, not text** (ADR-001).
- **Energy, not the own tile, for the user** (ADR-002).
- **Separate helper binary** rather than a mode of `teams-tap`: different permission, different lifecycle risks, and `teams-tap` stays the audio-critical path.
- **Labels computed at transcription, not during the call**: the transcript does not exist during the call; keeping the raw events makes relabelling possible when the rules change.
- **Reason codes, not messages, in the events file**: the notification and the CLI render them from `messages.py`; the file stays language-neutral.
- **Daily notice marker in `data/log`**, not per meeting: the rule is per day.

### Known Risks

- **Teams UI drift** (likely over months): the class name or the tile structure changes and labels disappear silently. Mitigation: the `stop` counters and `seen`-without-`speaking` patterns are visible in `trec status` (0% labelled) and the daily notice fires; the probe script re-discovers the structure.
- **Covered window**: labels thin out when every Teams window is hidden. Mitigation: documented; the compact view covers the common case; coverage is reported.
- **Permission identity**: settled by task_03 (the helper as its own launchd job). A `--check` typed in a terminal reports the terminal's permission, so `trec doctor` runs the check as a launchd job, and also compares it with the last recording's observer outcome and warns on a mismatch. After rebuilds macOS may forget the grant: the doctor tells; the build script prints a reminder.
- **Energy false positives** when the user is unmuted and someone else speaks loudly through speakers: the Teams track carries it louder than the microphone, so the 6 dB margin holds; measured in G1.
- **Chromium accessibility mode cost in Teams**: more memory while attached. Mitigation: measure in G5; the observer can be switched off.

## Safety Invariants

1. The observer starts only after both audio recorders started, and its failure to start never raises out of `StartRecording`; the recording proceeds and `speakers.jsonl` holds one `unavailable` line with the reason.
2. At most one observer runs per recording; its handle is persisted in `current_recording.json` before the recording is reported started, so a `trec stop` from another process stops it.
3. `StopRecording.stop_capture` stops the observer before the recorders and tolerates its absence or death; `CancelRecording` does the same.
4. The helper performs no action on the Teams UI: it reads attributes only and never sets focus, attributes or values; its sources contain no `AXUIElementSetAttributeValue` call (the spike showed the screen-reader hint is unnecessary), and a unit test greps them.
5. `speakers.jsonl` has one authoritative writer per meeting: the helper while it runs; when the start fails, the use case replaces the file atomically with the single `unavailable` line (the helper is dead by then), and a reader that finds an `unavailable` line ignores anything else in the file.
6. Energy is measured in `finalize` before any raw track is deleted, and `energy.json` is written atomically or not at all; a measurement failure deletes nothing extra and blocks nothing.
7. Labelling is a pure function of (transcript, events, energy, rules): re-running `trec transcribe` on the same inputs yields the same labels; a labelling failure keeps the unlabelled transcript and logs.
8. Speaking state is tracked per `(window, name)`; a window lost or frozen closes its open turns; a turn never closed ends at the last event of the file; the merged state of a name is the union of its windows' turns.
9. The daily-notice marker is written only after the notification was sent, keyed by the local calendar day of the transcription (`clock.now().date()` in `TranscribeMeeting`); no notice fires for a meeting without an events file.
10. Event times are made relative to the epoch the helper echoes in its `start` event (the instant the adapter passed, the same both tracks use); the meeting's stored start is only the fallback when that event is missing. The helper flushes every line as it writes it, so events survive a SIGKILL after the stop timeout and are readable the moment `stop_capture` returns.
11. The helper always runs as its own launchd job with the fixed label `local.teams-recorder.speakers`, at most one at a time: a start boots out a stale job with that label first, and `stop_capture`, `CancelRecording` and the daemon's recovery boot it out (the job definition in `<data_dir>/run/` is removed with it). They do so also when no handle was persisted (a crash or an interrupted start during the startup grace): the label is fixed, so `stop_stale()` boots the job out whatever the pointer says, and a failed start does the same. Every `launchctl` call the adapter makes has a timeout (5 s for `print`, which the daemon asks on every tick, 20 s for the others); a timeout is a failed call, and the daemon isolates the observer's health check so nothing it raises or costs reaches the call-end detection (review round 2, issue 003).

## File References

### Repo Files

- `docs/tasks/speaker-attribution/prd.md` — the requirements, gates and the user's four decisions this spec serves.
- `docs/SPEAKER-ATTRIBUTION.md:§6` — the spike runs: tile structure, the frame class set, the covered-window freeze, the compact view.
- `scripts/ax-speaker-probe.swift` — the working AX walk (window detection, tile text, `AXDOMClassList`, transitions) the helper is derived from.
- `native/teams-tap/Package.swift`, `native/teams-tap/Sources/teams-tap/Info.plist`, `native/teams-tap/Sources/teams-tap/main.swift:1-100` — the package layout, the embedded `Info.plist` for TCC identity, argument parsing and logging style to mirror.
- `scripts/build-native.sh` — builds `teams-tap`; gains the second package.
- `src/teams_recorder/adapters/outbound/capture_coreaudio.py` — the spawn/stop/is_running pattern (`process_control.spawn`, `terminate`) the observer adapter follows.
- `src/teams_recorder/adapters/outbound/process_control.py` — `spawn` with log redirection and the startup grace; `terminate` by pid for other processes.
- `src/teams_recorder/application/ports.py:28-75` — `CaptureHandle`, `ActiveRecording`, the capture ports.
- `src/teams_recorder/application/use_cases/recording.py` — `StartRecording.execute`, `StopRecording.stop_capture/finalize`, `CancelRecording`: where the observer and the energy meter are wired.
- `src/teams_recorder/application/use_cases/processing.py:35-110` — `TranscribeMeeting`: where labelling runs after whisper and the retry.
- `src/teams_recorder/application/pipeline.py` — `after_stop`/`process`: unchanged, but the failure isolation the new steps must respect.
- `src/teams_recorder/adapters/inbound/daemon.py:118-134` — `_watch_capturers`: the observer is watched the same way.
- `src/teams_recorder/adapters/outbound/repository_fs.py:154-190,213-245` — the active-recording pointer and the artifact loaders the new files follow (atomic writes, `_decoded`).
- `src/teams_recorder/adapters/outbound/codec.py:70-125` — transcript/health codec: `speaker` is added here with a default for old files.
- `src/teams_recorder/domain/models.py:45-120` — `Segment`, `Transcript`, `clock_time`.
- `src/teams_recorder/domain/verification.py:119-140` — `participant_heard`, extended to accept a labelled speaker or a roster name.
- `src/teams_recorder/application/use_cases/verification.py:30-72` — `VerifyAnalysis`: the code checks only lower a verdict; the roster reaches the verifier through the transcript.
- `src/teams_recorder/domain/health.py:42-45` — `is_speech`, the eligibility predicate, moved to `models.py` and re-exported here (health imports models, so the share cannot import health).
- `tests/unit/test_verifier_claude.py:151-166` and `scripts/fidelity_eval.py` (`VERIFY_SYSTEM`) — the pin that the shipped verifier prompt equals the measured prototype up to two replacements; the label sentence becomes the third (the §14.3 numbers predate it).
- `docs/prd/appendix/integrations.md:21` — records that the Microphone grant went to the daemon's Python, the evidence behind task 0.
- `src/teams_recorder/adapters/outbound/process_control.py:48-66` — `spawn` raises on an exit inside the startup grace; the observer adapter runs `--check` before spawning so an early exit is `start-failed`.
- `src/teams_recorder/adapters/outbound/llm_schema.py:116-127` — `build_user_message`: the roster header goes here.
- `src/teams_recorder/adapters/outbound/verifier_claude.py:77-103` — `transcript_for`: renders lines with labels.
- `prompts/analyze_system.md:5-7,14,20` — the input description, the participants rule and the owner rule that change.
- `prompts/verify_system.md:1` — "it has no speaker labels" changes.
- `src/teams_recorder/adapters/inbound/cli.py:155-210` — `doctor`; `status` and `transcribe` output lines.
- `src/teams_recorder/container.py:95-160` — `Container`, `_macos_adapters`, `_windows_adapters`, `build_container`.
- `src/teams_recorder/config.py:60-110,220-290` — `Settings` and `load_settings` for `[speakers]`.
- `src/teams_recorder/constants.py`, `src/teams_recorder/messages.py` — where every new identifier and text goes (`Speakers`, `Files`, `Bin`, `Err`, `Log`, `Cli`, `Notify`, `Prompt`, `Minutes`).
- `tests/fakes/__init__.py`, `tests/fixtures/fake_recorder.py`, `tests/unit/test_recording_use_cases.py`, `tests/unit/test_processing_use_cases.py`, `tests/unit/test_llm_claude.py:149-160`, `tests/unit/test_no_hardcoded_strings.py` — the fakes, stand-ins and pinned tests to extend.
- `scripts/install.sh:20-22,228-240`, `README.md:196-205`, `AGENTS.md` (ports table, commands), `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10, `docs/prd/pages/01-manual-recording.md`, `docs/prd/pages/02-transcription.md` — documentation targets.

### External References

- None vendored. Chromium's accessibility behaviour (tree exposed on first read; DOM class list attribute) is cited by concept in `docs/SPEAKER-ATTRIBUTION.md` — no path in this repo.

### Design and Analysis Sources

- `docs/SPEAKER-ATTRIBUTION.md` — options A–F, the recommendation and the spike log that feed ADR-001 and ADR-002.
- `docs/tasks/prd-llm-wiki/evaluation.md` §14 — the owner/participant error counts that motivate the feature.

## Assumptions and Defaults

- Teams keeps rendering participant tiles as `AXMenuItem` elements whose text starts with the display name, with an empty last-child frame element whose class list carries `vdi-frame-occlusion` while speaking (observed on Teams 26261.303 on 2026-10-16); the helper also records the tile text so drift is diagnosable.
- The own tile exposes no frame; the user's lines come from energy only.
- Sampling interval 0.5 s; a pass is "slow" above 1 s.
- `LabelRules` defaults 0.30 / 6 dB / −50 dBFS; energy step 0.1 s; silence floor −120 dBFS.
- `[speakers] enabled = true` on macOS; Windows has no observer.
- The user's label is `[user] name` when set (today "Felipe"), else the own tile's name, else "Você".
- The helper's launchd job definition lives in `<data_dir>/run/local.teams-recorder.speakers.plist` (the folder the Windows stop files already use); its stderr is appended to `data/log/speakers.log`.
- The daily notice is keyed by the local calendar day of the transcription, stored in `<data_dir>/notices/speaker-labels`; it never fires for a meeting without an events file.
- The helper waits indefinitely for a Teams window (logging once a minute) rather than exiting: a recording may start before the meeting window is up.
- Transcript times are seconds since the recording's start instant; the observer's events are made relative to the epoch its `start` event echoes (the adapter passes `--epoch`, mandatory), with `meeting.started_at.timestamp()` only as the fallback.
- The verifier prompt's pin test gains a third allowed replacement (the label sentence); the fidelity evaluation's §14.3 numbers describe the prompt before it, and the fidelity gate re-measures with the shipped prompt.
- The energy comparison is a power mean; the window next to each tone edge reads a finite level (about −85 dBFS in the real ffmpeg run), not the silence floor.

## Architecture Decision Records

- [ADR-001: Speaking state from the tile frame's class set, read through Accessibility](adrs/adr-001.md) — the Teams window is the only local source of who is speaking; the frame's `vdi-frame-occlusion` class set is the signal.
- [ADR-002: The user's own lines from the two tracks' energy](adrs/adr-002.md) — the microphone track against the Teams track, with a margin; no voice model, no own-tile frame.
