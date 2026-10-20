# Commit convention

The history is organized in **waves**: each phase of the implementation plan (section 10 of
`REQUIREMENTS-AND-ARCHITECTURE.md`) becomes a short sequence of commits, one per layer of the
hexagonal architecture, in dependency order:

1. `docs:` documents and decisions for the phase
2. `feat(domain):` entities and pure rules
3. `feat(application):` ports, use cases, pipeline
4. `feat(adapters):` outbound adapters (I/O)
5. `feat(native):` Swift code
6. `feat(cli):` composition root and commands
7. `test:` fakes, fixtures and tests for the wave

Messages are written in English, in the imperative mood, with the scope in parentheses
(e.g. `feat(adapters): add Core Audio microphone capture`). Each commit must leave the tree
importable; tests may only pass at the end of the wave.

Commit messages before 2026-10-05 are in Portuguese; the convention switched to English on
that date and the earlier history was not rewritten.

## Recorded waves

| Wave | Phase | Contents |
|------|-------|----------|
| 0 | — | Interview, requirements, architecture, conventions |
| 1 | 1 | Skeleton, domain, application, file-based repository, config, tests |
| 2 | 2 | teams-tap (Swift), capture and mixing, CLI start/stop/cancel, adapter tests |
| 3 | 3 | Transcription config, whisper.cpp transcriber and model download, CLI transcribe, tests, docs |
| 4 | 4 | Prompts, Claude analyzer with structured output, CLI analyze and pipeline in the container, tests, docs |
| 4b | 4 | Alternative provider via headless Claude Code, selection by config, tests, docs |
| 5 | 5 | pmset detector, daemon with hysteresis and recovery, LaunchAgent, CLI daemon/agent, audio wait in teams-tap, tests, docs |
| 5b | 5 | Fixes from the first real meetings: Teams helpers, Core Audio microphone, per-track diagnostics, noise/limiter, optional VAD |
| 6 | 6 | Structured transport, Claude planner, CLI plan, scheduled agent, tests, docs |
| W1 | — | Windows port of the capture binary: teams-tap.exe (C#, WASAPI process loopback and microphone), build scripts, docs |
| 7 | 7 | Installer (install.sh, install.command), uninstaller, docs |
| 7b | — | Keep-or-discard question when a call starts: port, osascript dialog, daemon logic, config, tests, docs |
| 7c | — | Long meetings and back-to-back calls: split stop/mix, scaled mix timeout, atomic audio, retry unmixed recordings, disk warnings, 16/32-bit raw tracks (`--bits`), tests, docs |
| W2 | — | Windows Python side: platform selection, WASAPI capture adapters with stop files, registry call detector, toast, message box, Task Scheduler, install.ps1, tests, docs |
| 8 | — | User story drafts from the daily plan: guide-driven Claude story writer, Markdown review document, `trec stories`, config, tests, docs |
| 8b | — | Story publishing to a Backlog.md board: publication state, duplicates across days and the redraft lock, publisher port and use case, destinations switch, Backlog.md publisher, `trec publish`, doctor/status lines, tests, docs (one layered set of commits per task of `docs/tasks/prd-story-publishing/`) |
| 8c | — | Action kinds: the analysis classifies every action (feature, bug, technical, operation, management, communication); stories only for features and bugs, task cards for technical and operation work, the rest stays in the plan; kind labels, bug format, tests, docs |
| 9a | — | Fidelity guard, task 1.0: whisper `-mc 0` by default, transcript health (repetition loops, minutes without text), one VAD retry of a degraded transcript, degraded marking with a notification and a minutes banner, doctor/status lines, scripted whisper stand-in, tests, docs |
| 9b | — | Code-review fixes for 9a: a retry that fails for any reason or comes back empty keeps the first pass, minutes with text rank first and are measured against the meeting's length, a 30-segment window for loops of up to 7 lines, non-speech markers are not text, damaged transcripts are a repository error, tests, docs and the review's run log |
| 9c | — | Fidelity guard, task 2.0: `Verification` on decisions, actions, deadlines and participants, written only when present; shape errors in every JSON the repository decodes (meta, pointer, transcripts, analyses, plans, open actions, drafts) become repository errors; `trec status` reports each damaged file on its own line; an orphan recording pointer is cleared before its handles are read; two rounds of review fixes, tests, docs |
| 9d | — | Fidelity guard, task 3.0: `ClaimRef`, verdict combination and the two code checks in the domain, `ClaimVerifier` port and `VerifyAnalysis` inside the analysis step, the Claude verifier with transcript windows and its prompt, tests (an opt-in real one), docs; review fixes (the prompt and message back to the measured prototype); not wired until task 7.0 |
| 9e | — | Fidelity guard, task 4.0: ⚠️ marks with reasons in the minutes, the planner told what unconfirmed means, unconfirmed features and bugs kept out of story sources, marked task cards on the board, the degraded-transcript banner in the drafts document, review fixes (one-line reasons, the full gap list, plan-only marks), tests, docs |
| 9f | — | Teams track at the wrong sample rate: teams-tap reads the aggregate device's real rate (listener, measured-rate check) and resamples to 48 kHz, capture counters in `tap.stats.json`, a `rate_mismatch` transcript flag with a notification, a minutes banner and status lines, a recovery script for affected meetings, code-review fixes, tests, docs and the review's run log |
| 9g | — | Fidelity guard, task 5.0: `Criterion(text, source)` with timestamp or suggestion, the writer's citation rule and schema, cited times checked against the source transcripts, sources shown in the drafts and on the board, old drafts unchanged, the evaluation reading the new format, review fixes (no stacked rules in the evaluation, an English stored value, a strict reader), tests, docs |
| 9h | — | Fidelity guard, task 1.1: a loop-free retry keeping 85% of the text wins, no retry for a Teams track at the wrong sample rate, the drafts banner for such tracks, tests, docs |
| 9i | — | Fidelity guard, task 7.0: `[verification]` settings, the claim verifier on its own Sonnet transport in the container, no verification of an untrusted transcript (degraded or wrong sample rate) with a note in the minutes banner, doctor and status lines, tests, docs |
| 9j | — | Fidelity guard, task 6.0: the analysis prompt's fidelity rules (evident owners only, participants who speak or are addressed, no tentative decisions, no sensitive data) and the schema descriptions to match, a test pinning them, docs |
| 10 | — | Speaker attribution from the Teams window: the investigation, the PRD and the spec under `docs/tasks/speaker-attribution/` (the older task folders moved under `docs/tasks/`), speaker labels and the labelling rules in the domain, the observer and energy ports, the observer and energy steps in recording and the labels at transcription with a once-a-day notice, the teams-speakers helper run as its own launchd job, the ffmpeg energy meter, labels and the roster in the model input, doctor/status/transcribe/start lines, the installer's Accessibility step, tests, docs and three review rounds |
| 11a | — | Activities curator, shadow slice (`docs/tasks/activities-curator/`, tasks 1–7 and 9–11): progress statements (`status_updates`, `for_whom`) in the analysis, verifier and minutes; the pure document functions and the Edit-shaped ops with the checkbox rule; the activity store (flock, versions, archive, stamp-based reconcile); the Claude curator and its prompt; `CurateMeetings` with one repair, isolation and recovery; the pipeline hook and the daemon's curator worker; `trec activities`, `curate`, `undo` and the curation step of `trec analyze`; doctor/status lines; tests, docs, the spec's five review rounds and three code review rounds. The 18:00 planner still runs until the user's go |
| 11b | — | Activities curator, slice 2 (`docs/tasks/activities-curator/`, tasks 12–15), after the user's go on 2026-10-20: stories drafted only from the items tagged `#história` (`trec stories` without a date, `DraftStoriesFromTags`, the writer's blocks mode that sets kind, priority and due, `StoryRenderer.render(drafts, existing, degraded)`, `ActivityStore.rewrite_document`, `MeetingRepository.story_drafts_path`, publishing from the stories file alone); the planner removed (`planner_claude`, `plan_system.md`, `use_cases/planning.py`, the `Planner` port, `DailyPlan`, `trec plan`, the 6 pm LaunchAgent and Windows task, `[planner] hour` and `[stories] enabled`) with `constants.Legacy` so `agent install`, `restart`, `uninstall` and the installers remove the old job; the audio retention in `use_cases/retention.py`, run once a day by the daemon, `[audio] retention_days` with the `[planner]` key as a one-release fallback; installer, `config_tool` and `fidelity_eval` changes; tests, and the docs of the removal (AGENTS.md, README, REQUIREMENTS §10, `docs/prd/`) |
