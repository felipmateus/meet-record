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
| 8b | — | Story publishing to a Backlog.md board: publication state, duplicates across days and the redraft lock, publisher port and use case, destinations switch, Backlog.md publisher, `trec publish`, doctor/status lines, tests, docs (one layered set of commits per task of `tasks/prd-story-publishing/`) |
