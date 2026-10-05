# RUN_LOG — felipemateusdecarvalho — 2026-10-04 20:10

Activity: technical requirements interview and architecture definition for the teams-recorder project. Consolidated result in `docs/REQUIREMENTS-AND-ARCHITECTURE.md`.

## Round 1 — Fundamentals

| Question | User's answer |
|----------|---------------|
| Which folder on your Mac should the project live in? | ~/Documents/teams-recorder |
| Which languages should the project use? | Python + minimal Swift |
| How should the Teams participants' audio be captured? | Core Audio Process Tap |
| Which LLM will do the analysis and planning? | Claude API |

## Round 2 — Code architecture

| Question | User's answer |
|----------|---------------|
| How should the Python code be organized? | Hexagonal architecture |
| How should the stages communicate and store state? | Files only |
| Where should configuration and secrets be stored? | .env file |
| What level of automated testing? | pytest with fixtures (target 70%) |

## Round 3 — Functional requirements

| Question | User's answer |
|----------|---------------|
| How to detect that a Teams meeting started and ended? | System heuristic (pmset + microphone) |
| What to do with the audio after it is transcribed? | Delete audio after 30 days |
| Where should the activity plan be delivered? | Local Markdown |
| What language are the meetings in? | Portuguese only |

## Recorded notes
- The user chose `.env` over Keychain and `~/Documents` as the folder; risks R1 (iCloud) and R2 (key in plain text) documented with mitigations.
- Session moved to `~/Documents/teams-recorder` (folder created empty on this date).
