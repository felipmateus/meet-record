---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_dx.md
line: 34
severity: low
author: claude-code
provider_ref:
---

# Issue 009: Golden path output does not match the renderer and CLI line order

## Review Comment

Two examples in the public contract would not hold as written:

1. `_dx.md:34-38` shows `sed -n 1,4p minutes.md` printing title, date, language and participants. `MarkdownMinutesRenderer.render` emits the title and then an empty line (`src/teams_recorder/adapters/outbound/minutes_markdown.py:85`), plus banners for degraded or rate-mismatched transcripts (`:86-94`), so lines 1-4 are title, blank, date, language. Use `sed -n 3,5p`, or show the block without the `sed`.
2. The `Language:` line is "after `Health:` and before `Speakers:`" (`_dx.md:69`), and US-005.EC-1 says "after its `Health:` line" (`_user_stories.md:110`). `trec transcribe` prints the `WARNING: degraded transcript…` and `WARNING: … wrong sample rate…` lines between them (`src/teams_recorder/adapters/inbound/cli.py:459-468`). Name the exact slot, for example "after the health block, its warnings included, and before `Speakers:`", and have E2E-002 assert it on a degraded meeting.

## Triage

- Decision: `VALID`
- Notes: Valid on both points.
- Verified: `minutes_markdown.py:85-101` (title, blank line, banners, then date); `cli.py:459-468` (WARNING lines after `Health:`).

### Resolution

`_dx.md` golden path: the minutes are shown in their own Markdown block (title, blank line, date, language, participants), noting there is no banner because the transcript is healthy, instead of a wrong `sed -n 1,4p`. The `Language:` slot is defined as after the health block (the `Health:` line and its `WARNING:` lines) and before `Speakers:` and `Text:` in `_dx.md` and US-005.EC-1. E2E-002 asserts it on a degraded meeting (`--loop-always`).
