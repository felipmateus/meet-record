# Test Specification: Speaker attribution from the Teams window

Canonical test contract for speaker attribution. Companion to `_spec.md`. Derived from `_user_stories.md` (behavior), `_spec.md` Part II (components) and `_dx.md` (CLI and file contracts).

## Strategy

- Frameworks and harnesses: pytest, the project's fakes in `tests/fakes` (one per port; new `FakeSpeakerObserver`, `FakeEnergyMeter`), scripted stand-ins in `tests/fixtures` for spawned processes (`fake_recorder.py` reused for the observer's lifecycle; new `fake_speakers.py` for `--check` exit codes and event writing, with a readiness file). Real ffmpeg for the energy meter on a generated WAV, skipped when ffmpeg is absent. mypy stays clean.
- Execution: `pytest` (fast suite); the real-ffmpeg case lives in the fast suite because ffmpeg is a hard dependency of the product; the Swift helper is type-checked by `swiftc -typecheck` in the build and exercised manually in a live call (PRD gates G1–G2), which no automated test replaces.
- Conventions: one behavior per test, names say the rule (`test_a_line_covered_30_percent_by_a_turn_takes_that_name`), fixtures `repo`, `clock`, `notifier`, `meeting` from `tests/conftest.py`; no two pytest sessions at once (AGENTS.md).

## Coverage Matrix

| Source | Behavior | Unit | Integration | E2E |
| --- | --- | --- | --- | --- |
| US-001 | remote lines labelled from the window | UT-001–UT-005, UT-020 | IT-001 | E2E-001 |
| US-001.EC-1 | covered window → no window labels in that stretch | UT-006 | — | — |
| US-001.EC-2 | window lost closes turns | UT-004 | — | — |
| US-001.EC-3 | same display name twice → one name | UT-007 | — | — |
| US-001.EC-5 | sub-0.5 s turn still a turn | UT-003 | — | — |
| US-002 | the user's lines from energy | UT-010–UT-014 | IT-002 | E2E-001 |
| US-002.EC-1 | speaker leakage louder on the Teams track → not the user | UT-012 | — | — |
| US-002.EC-3 | energy missing → no user labels | UT-013 | — | — |
| US-002.EC-4 | overlap vs energy precedence | UT-011 | — | — |
| US-003 | unlabelled lines unchanged | UT-015, UT-021 | — | — |
| US-003.EC-1 | non-speech markers never labelled nor counted | UT-016 | — | — |
| US-003.EC-2 | labelling failure keeps the transcript | UT-040 | — | — |
| US-004 | owners from labels (prompt and verifier) | UT-050–UT-052 | — | PRD gate G3 (manual) |
| US-005 | roster as participants; code check does not flag roster names; the verifier gets the roster | UT-053–UT-056 | — | PRD gate G1 (manual) |
| US-006 | title from the subject | UT-030–UT-032 | — | — |
| US-007 | recording never depends on the observer | UT-033–UT-039 | IT-003, IT-004 | — |
| US-007.EC-1 | `[speakers] enabled = false` → no helper, no `unavailable` line | UT-060, UT-037 | — | — |
| US-007.EC-2 | energy failure → mixing continues | UT-036 | — | — |
| US-007.AC-2 | helper died before reading a window → reason `observer-died` | UT-046 | — | — |
| US-007.EC-3 | daemon recovery stops the observer | UT-039 | — | — |
| US-008 | one notification per day with the reason, only for notifying reasons and wired observers | UT-041–UT-047 | — | — |
| US-008.EC-1 | marker unreadable → notify once, rewrite | UT-044 | — | — |
| US-009 | doctor / status / transcribe lines, 0% with reason, the permission mismatch warning | UT-061–UT-065 | IT-005 | — |
| US-010 | build script, `--check`, the permission identity | UT-076 | IT-006 | IT-007 (manual spike, task 0) |
| US-011 | old files load and render unchanged | UT-021–UT-024 | existing `tests/integration/test_repository_fs.py` | — |
| `domain/speakers.turns_from_events` | events → turns | UT-001–UT-005 | — | — |
| `codec` events/energy | parse and write, time origin, `unavailable` wins | UT-020–UT-027 | — | — |
| `speakers_ax.AxSpeakerObserver` | command, `--check`, lifecycle | UT-070–UT-072 | IT-003, IT-004 | — |
| `energy_ffmpeg.FfmpegEnergyMeter` | command, parser, real run | UT-073–UT-075 | IT-002 | — |
| `test_no_hardcoded_strings` | new modules carry no inline prose | existing guard | — | — |
| Safety invariant 4 | the helper never sets an accessibility attribute | UT-076 | — | — |
| `label_segments` arithmetic (issue 007) | power mean, window selection, zero duration, ties | UT-008, UT-012b, UT-013b, UT-016b | — | — |

## Unit Tests

### `domain/speakers.py` — turns (Spec: Label rules)

- **UT-001** (happy): `turns_from_events` — events `on@10.0, off@18.0` for "Lucas"/main → one turn `(10.0, 18.0, "Lucas")`.
- **UT-002** (boundary): an `on` with no `off` and `end=100.0` → the turn closes at `100.0`.
- **UT-003** (boundary): `on@10.0, off@10.3` → a turn of 0.3 s is kept (US-001.EC-5).
- **UT-004** (state): `on@10.0` in "compact", then the compact window is `lost@14.0` (a `window lost` event carries no name) → the turn closes at `14.0` (US-001.EC-2).
- **UT-005** (ordering): "Lucas" `on@10, off@20` in main and `on@15, off@25` in compact → merged turns `(10, 25)` for "Lucas" (union).
- **UT-007** (state): two tiles named "Ana" in two windows, overlapping turns → one name "Ana" with the union of turns (US-001.EC-3).

### `domain/speakers.py` — labels (Spec: Label rules)

- **UT-006** (happy): a segment `[30, 40]` with a "Lucas" turn `(32, 39)` → `speaker == "Lucas"`; a segment `[50, 60]` with no turn and no energy → `speaker is None` (US-001.AC-1, EC-1).
- **UT-008** (boundary): a turn covering exactly 30% of a 10 s segment (3.0 s) → labelled; covering 2.9 s → not labelled; a zero-duration segment (`end == start`) → never labelled and not counted as eligible; two names with equal overlap → the one whose turn started first, then the alphabetically first.
- **UT-009** (happy): turns "Lucas" 4 s and "Ana" 6 s over the same segment → "Ana" (largest overlap, US-001.AC-2).
- **UT-010** (happy): no turn; mic mean −30 dBFS, tap mean −45 → labelled with `user_label` (US-002.AC-1).
- **UT-011** (ordering): a turn covering 40% and mic dominating → the turn's name wins (US-002.EC-4).
- **UT-012** (error): mic −35, tap −28 (speaker leakage) → no label (US-002.EC-1).
- **UT-012b** (error): tap windows alternating −25 and −120 (a remote speaker talking half the time), mic windows −40 and −55 (leakage) → the power means are about −28 and −42, so no user label; an arithmetic mean would have labelled the user (the false positive ADR-002 rules out).
- **UT-013** (empty): `mic=None` or `tap=None` → the energy rule is skipped; turns still apply (US-002.EC-3).
- **UT-013b** (boundary): windows are selected by midpoint (window i covers `[0.1·i, 0.1·(i+1))`, midpoint `0.1·i + 0.05`): a segment `[0.31, 0.39]` contains the midpoint of window 3 (0.35) only, so window 3's levels decide; a segment `[0.36, 0.44]` contains no midpoint → no energy label.
- **UT-014** (boundary): mic exactly tap + 6.0 dB and exactly −50.0 → labelled; mic −50.1 → not.
- **UT-015** (happy): `label_segments(transcript, None, None, None, "Felipe")` → returns an equal transcript with every `speaker is None` (US-003.AC-2).
- **UT-016** (state): a segment whose text is `[BLANK_AUDIO]` with a covering turn → not labelled and not counted in `LabelSummary.eligible` (US-003.EC-1); `is_speech` is importable from `domain/models.py` and still from `domain/health.py`.
- **UT-016b** (happy): `label_segments` returns a copy whose `roster`, `user_label` and `labels` are filled: `LabelSummary(labelled=2, eligible=3, reason=None)` for two labelled of three eligible segments; `reason == "no-match"` when a roster exists and nothing was labelled.
- **UT-017** (happy): `user_label("Felipe", log_with_me="Felipe Mateus", "Você") == "Felipe"`; `user_label("", log_with_me, …) == "Felipe Mateus"`; `user_label("", None, "Você") == "Você"` (US-002.AC-2–4).
- **UT-018** (happy): `Transcript.speakers` → distinct labels in order of first appearance; `no_label_reason` over the states of the table in `_spec.md` (no log → `no-observer`; `unavailable` → its code; no roster and not ended → `observer-died`; no roster and ended → `no-window`; roster and zero labels → `no-match`; labelled > 0 → `None`).

### `domain/models.Transcript.as_timestamped_text` (Spec: Core Interfaces)

- **UT-019** (happy): a labelled segment renders `[00:03:12] Lucas Huguenin Gurgel de Moura: então eu subo o ambiente`; an unlabelled one renders `[00:03:30] a gente combina`, exactly as before.

### `adapters/outbound/codec.py` (Spec: Data Models)

- **UT-020** (happy): `speaker_log_from_lines(lines, fallback_epoch=1000.0, end=600.0)` on the `_dx.md` example → times relative to the `start` event's epoch (`1760655010.0`, not the fallback): the turn is `191.104`→`199.620`; `roster == ("Felipe Mateus de Carvalho", "Lucas Huguenin Gurgel de Moura")`, `me == "Felipe Mateus de Carvalho"`, `subject == "Planejamento da sprint"`, `ended is True`, `unavailable is None`.
- **UT-027** (boundary): the same lines without the `start` event → times relative to `fallback_epoch`; a file with `start` but no `stop` → `ended is False`.
- **UT-028** (state): a `speaking: true` with no closing event, followed by heartbeats up to `t0 + 40` and nothing else (the helper died) → the turn ends at `t0 + 40`, not at the meeting end; a later line at `t0 + 300` with the microphone dominating is labelled with the user, not the remote name (review round 2, issue 001).
- **UT-029** (state): a `window … frozen` event closes that window's open turns like `lost`; a `found` after it reopens nothing by itself.
- **UT-021** (happy): `transcript_from_dict` on a segment without `speaker` → `speaker is None`; `transcript_to_dict` omits `speaker` when `None` and writes it when set; round trip equal (US-011.AC-1).
- **UT-022** (error): a malformed line in `speakers.jsonl` (not JSON, or an unknown `event`) → skipped and counted; the rest parses.
- **UT-023** (happy): the single `unavailable` line → `SpeakerLog(turns=(), roster=(), me=None, subject=None, ended=False, unavailable="permission-missing")`; an `unavailable` line followed by stray `start`/`seen` lines → the same result (it wins).
- **UT-024** (happy): the compact-view title `Modo de exibição compacto da reunião | X | …` and the main title `X | …` both yield `subject == "X"`; the first subject read wins (US-006.EC-2).
- **UT-025** (happy): `energy_to_dict`/`energy_from_dict` round trip with `step_seconds` and two tracks; `-120.0` preserved.
- **UT-026** (error): `energy.json` with a non-list track → `RepositoryError` naming the file (the repository's `_decoded` rule).

### `application/use_cases/recording.py` (Spec: System Architecture)

- **UT-030** (happy): `StopRecording.stop_capture` on a recording whose `speakers.jsonl` has subject "Planejamento da sprint" and a meeting without title → `meeting.title == "Planejamento da sprint"` saved (US-006.AC-1).
- **UT-031** (state): the meeting already has a title → unchanged (US-006.AC-2).
- **UT-032** (empty): no subject in the events → title stays `None` (US-006.AC-3).
- **UT-033** (happy): `StartRecording` with a `FakeSpeakerObserver` → started after both captures with `out == path(SPEAKERS)` and the meeting epoch; `active.speakers_handle` set; `repo.load_active().speakers_handle` persisted (US-007.AC-4 prerequisite).
- **UT-034** (error): the observer raises `SpeakersUnavailable("permission-missing")` → the recording starts, `repo.write_speakers_unavailable` is called with that reason (the fake records it), a warning is logged, no exception (US-007.AC-1).
- **UT-035** (error): the observer raises any other exception → same as UT-034 with reason `start-failed`.
- **UT-036** (error): `FakeEnergyMeter(fail=True)` → `finalize` mixes and deletes the raw tracks as today, logs the failure, writes no `energy.json` (US-007.EC-2).
- **UT-037** (empty): `speakers=None` (feature off or Windows) → no observer call, no `unavailable` line, `speakers_handle is None` (US-007.EC-1).
- **UT-038** (happy): `StopRecording.stop_capture` and `CancelRecording.execute` stop the observer handle when present; a stop failure is logged and the recorders still stop.
- **UT-039** (state): `Daemon.recover` with a persisted `speakers_handle` → the observer is stopped with the recorders (US-007.EC-3); `_watch_capturers` logs `teams-speakers` death once.
- **UT-036b** (happy): `finalize` measures both tracks before deleting them and saves `energy.json` with `step_seconds == 0.1` and one entry per track; the order of calls is measure → mix → delete.

### `application/use_cases/processing.py` (Spec: System Architecture)

- **UT-040** (error): `repo.load_speaker_log` raises `RepositoryError` → the transcript is saved unlabelled (no summary), `Log.SPEAKERS_LABEL_FAILED` logged, `execute` returns (US-003.EC-2).
- **UT-041** (happy): a meeting with turns and energy → the saved transcript has the expected labels and `Log.SPEAKERS_LABELLED` reports `labelled/total` and the names.
- **UT-042** (happy): zero labels for reason `permission-missing`, an events file present, `repo.last_notice_day("speaker-labels")` is None → one notification `Notify.NO_SPEAKER_LABELS` with that reason's body (US-008.AC-1); `repo.save_notice_day` called with `clock.now().date()`.
- **UT-043** (idempotency): the marker already holds `clock.now().date()` → no notification, a log line (US-008.AC-2); a marker holding yesterday → notifies (the day is the transcription's, not the meeting's).
- **UT-044** (error): the marker is unreadable → treated as absent: one notification, the marker rewritten (US-008.EC-1).
- **UT-045** (happy): at least one label → no notification (US-008.AC-3).
- **UT-046** (happy): the reason table: `binary-missing`, `permission-missing`, `start-failed`, `observer-died`, `no-window` → notification sent; `no-match` → log only, no notification; `no-observer` (no file) → no notification and no log warning (US-007.AC-2, US-008.AC-4–5, US-011.AC-3).
- **UT-047** (empty): `clock=None` → no notification logic runs at all.

### Prompts, model input and verification (Spec: Downstream)

- **UT-050** (happy): `prompts/analyze_system.md` contains the label sentence (`A name after the timestamp is the person who said the line`) and keeps `the user speaks in the first person taking on a commitment` for unlabelled lines; the roster rule (`participants is exactly that list`) is present (US-004.AC-1–2, US-005.AC-1).
- **UT-051** (happy): `build_user_message` reads `transcript.roster` and `transcript.user_label`: with both it adds `Participants seen in the meeting window: Felipe Mateus de Carvalho, Lucas Huguenin Gurgel de Moura` and `Speaker labels: the name after a timestamp is who said the line; "Felipe Mateus de Carvalho" is the recording owner` to the header; with an empty roster and no label it adds nothing (the message is byte-for-byte today's).
- **UT-051b** (happy): `prompts/analyze_system.md` keeps the data-contract sentence that the recording owner is written as `usuário` and adds that this holds for lines labelled with the owner's label, whatever name it is.
- **UT-052** (happy): `prompts/verify_system.md` says labelled lines are reliable attribution and no longer says the transcript "has no speaker labels"; `verifier_claude.transcript_for` renders `[HH:MM:SS] Name: text` for labelled segments; `user_message` adds the roster line when `transcript.roster` is non-empty (US-004.AC-3, US-005.AC-3).
- **UT-056** (happy): `tests/unit/test_verifier_claude.py`'s prototype-prompt pin accepts the label sentence as its third replacement and still fails on any other difference.
- **UT-053** (happy): `participant_heard("Lucas Huguenin Gurgel de Moura", transcript, …)` → `True` when a segment's `speaker` matches or when the name is in `transcript.roster`, even if it is never in the text (US-005.AC-3).
- **UT-054** (happy): `VerifyAnalysis` on a transcript with a roster → the roster name never mentioned in the text is not marked unconfirmed by the code check; with a `FakeClaimVerifier` returning confirmed for it, the saved analysis shows it confirmed; with no verifier it stays unverified (US-005.AC-3, EC-2).
- **UT-055** (happy): the analysis schema description of `participants` mentions the roster rule.

### Config and container (Spec: Config Lifecycle, Architectural Boundaries)

- **UT-060** (happy): `load_settings` → `speakers_enabled` defaults to `True`; `[speakers] enabled = false` → `False`; the macOS container builds an `AxSpeakerObserver` only when enabled; the Windows container passes `speakers=None` (US-007.EC-1, EC-4).

### CLI helpers (Spec: Agent Manageability Plan)

- **UT-061** (happy): the doctor's speaker line for a ready observer (`problems() == []`) → `[ok ] speaker labels: … Accessibility permission granted` (US-009.AC-1).
- **UT-062** (happy): `problems()` naming the permission → `[info]` line with the `--check --prompt` command and the settings path; the doctor's exit code is unaffected (US-009.AC-2).
- **UT-063** (happy): binary missing → `[info] … not built → scripts/build-native.sh`; feature off → the off line (US-009.AC-3, EC-1).
- **UT-064** (happy): the status line for a transcript whose summary is `LabelSummary(167, 214, None)` → `· speakers 78%`; for `LabelSummary(0, 214, "no-window")` → `· speakers 0% (no Teams meeting window was read during the call)`; for an old transcript (`labels is None`) → no segment (US-009.AC-4, EC-2); the transcribe output line formats `78% of 214 lines labelled (names)` and the seven reasons of the `_dx.md` table.
- **UT-065** (happy): the doctor's speaker line appends the last recording's observer outcome from its transcript summary (`observer ran, 78% of lines labelled`), and prints the `[WARNING]` mismatch line when `--check` passes but the last summary's reason is `permission-missing` (US-009.AC-5).

### `adapters/outbound/speakers_ax.py` (Spec: Core Interfaces)

- **UT-070** (happy): `job(out, epoch)` → a launchd job definition with label `local.teams-recorder.speakers`, `ProgramArguments == [binary, "--out", str(out), "--epoch", "1760655010.000", "--interval", "0.5"]`, `RunAtLoad` true, no `KeepAlive`, stderr to `data/log/speakers.log`; `start` writes it under `<data_dir>/run/` and calls `launchctl bootout` (stale job) then `launchctl bootstrap gui/<uid> <plist>` through the injected runner, and returns the pid read from `launchctl print`.
- **UT-071** (error): binary missing → `start` raises `SpeakersUnavailable` with reason `binary-missing`; `problems()` returns the build hint.
- **UT-072** (error): the job is not running after the startup grace and `launchctl print` reports `last exit code = 3` → `start` raises `SpeakersUnavailable("permission-missing")` and boots the job out; any other early exit → `SpeakersUnavailable("start-failed")`; `problems()` runs the check as the short-lived job `local.teams-recorder.speakers-check` and, on exit 3, returns the permission hint naming the `+` button and the helper's path; `stop` boots the job out and removes its definition.
- **UT-070b** (happy): `command` always carries `--epoch`; `start` without an epoch is impossible by signature.

### `adapters/outbound/energy_ffmpeg.py` (Spec: Integration Points)

- **UT-073** (happy): `command(track)` → the documented ffmpeg filter chain with `aresample=16000,asetnsamples=n=1600` and `ametadata=mode=print:…:file=-`.
- **UT-074** (happy): `parse_levels(output)` on a captured ffmpeg 9 output (`frame:15   pts:24000   pts_time:1.5` then `lavfi.astats.Overall.RMS_level=-85.545672`; integer seconds print as `pts_time:1`; silence prints `-inf`) → `EnergyTimeline(step=0.1, levels=(…, -120.0, …))` with `-inf` mapped to the silence floor and the frames in `pts_time` order.
- **UT-075** (error): a non-zero exit or a timeout → `CaptureError` with the tail of stderr.

### Native sources (Spec: Safety Invariants 4)

- **UT-076** (state): the sources under `native/teams-speakers/Sources` contain no `AXUIElementSetAttributeValue` (a grep in a unit test; the build script runs the same check).

## Integration Tests

### Labelling end to end on files (Spec: Build Order 1)

- **IT-001**: `FsMeetingRepository` with the `_dx.md` `speakers.jsonl` and an `energy.json` written by the codec; `TranscribeMeeting` over a `FakeTranscriber` whose segments fall inside and outside the turns — expect `transcript.json` segments with the expected `speaker` values and `transcript.txt` lines with names (US-001.AC-1, AC-4).
- **IT-002**: two generated 3 s WAVs, `tap.wav` (stereo, a tone over 0–1.5 s, digital silence after) and `mic.wav` (mono, silence then a tone over 1.5–3 s), each measured by the real `FfmpegEnergyMeter` → 30 windows per track (a 3.05 s file gives 31, the last zero-padded); levels above −30 dBFS inside each tone, at or below −80 outside it (the window next to each edge reads a finite level, about −85 and −101 in the measured run, not the floor); `label_segments` on segments `[0, 1.4]` and `[1.6, 3.0]` with no turns gives `None` then `user_label` (US-002.AC-1). Skipped when ffmpeg is absent.

### Observer lifecycle with a stand-in (Spec: Core Interfaces)

- **IT-003**: `AxSpeakerObserver(binary=fake_speakers.py, runner=fake_launchctl)`, where the fake `launchctl` runs the job's `ProgramArguments` as a subprocess on `bootstrap`, reports its pid and state on `print` and sends SIGTERM on `bootout`, with `FAKE_SPEAKERS_TRUSTED=1` → `start` waits for the readiness file, `is_running` true, `stop` ends it with exit 0 and the stand-in's `stop` event is the last line of the file (US-007.AC-4 prerequisite).
- **IT-004**: the same with `FAKE_SPEAKERS_TRUSTED=0` → the stand-in exits 3, `start` raises `SpeakersUnavailable("permission-missing")`, and no process or job is left (US-007.AC-1).

### CLI (Spec: Agent Manageability Plan)

- **IT-005**: `trec doctor` through Typer's runner with a project whose helper path is a stand-in that exits 0 → the `[ok ] speaker labels` line; with a stand-in exiting 3 → the `[info]` line and the same exit code as without the feature (US-009.AC-1–2).

### Build (Spec: Technical Dependencies)

- **IT-006**: `swiftc -typecheck native/teams-speakers/Sources/teams-speakers/main.swift` succeeds (run in CI-like fashion by `scripts/build-native.sh`; in the test suite as a slow, opt-in check guarded by the presence of `swiftc`) (US-010.AC-1).
- **IT-007** (manual, task 0, with the user's approval): the built helper's `--check` run from a terminal and spawned from the installed daemon; the System Settings entry that appears and the two results are recorded in `_spec.md` › Integration Points, and the design chosen among the three candidates (US-010.AC-3).

## End-to-End Tests

### A labelled meeting (US-001, US-002)

- **E2E-001** (manual, PRD gates G1–G2): a real Teams meeting with at least two remote participants, a Teams window visible, the daemon recording → `trec transcribe` prints `Speakers: NN% of M lines labelled (names)` with NN ≥ 70 and a 30-line sample checked against the audio has ≥ 90% correct names. Recorded in the PRD's gate table, not automated.
