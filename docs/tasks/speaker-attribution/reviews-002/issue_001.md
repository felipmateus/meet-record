---
provider: manual
pr:
round: 2
round_created_at: 2026-10-17T14:01:36Z
status: resolved
file: src/teams_recorder/adapters/outbound/codec.py
line: 216
severity: high
author: claude-code
provider_ref:
---

# Issue 001: A turn left open by a dead helper is credited to the meeting end

## Review Comment

`speaker_log_from_lines` (`codec.py:216`) calls `turns_from_events(events, end)` with `end` set to the meeting duration (`processing.py:84`, `TranscribeMeeting._label`). `turns_from_events` closes every turn still open at that `end` (`domain/speakers.py:115-116`). It does this even when the log has no `stop` event (`ended is False`), which means the helper died or was killed mid-call.

The helper writes nothing after it dies. So a participant who was speaking at that moment keeps an open turn until the end of the recording. Every later line is then covered 100% by that turn and labelled with their name. The remote rule runs before the energy rule (`label_segments`, `speakers.py:204`), so this also overrides the user's own lines.

Runtime reproduction, run through the real codec and labeller (`scratchpad/repro.py`):

```
lines: start(epoch E), seen Lucas, speaking Lucas=true at E+600; no stop (helper died at ~600 s)
speaker_log_from_lines(lines, E, 3600.0).turns -> (SpeakerTurn(start=600.0, end=3600.0, name='Lucas'),)  ended: False
label_segments on segments at 605 s, 2000 s ("eu faço o deploy amanhã", mic 40 dB over tap), 3500 s
-> [(605, 'Lucas'), (2000, 'Lucas'), (3500, 'Lucas')]
```

The user's commitment at 2000 s goes to Lucas. This is the failure the feature exists to remove (Motivating Problem: wrong owners). It is now worse than before, because the prompts tell both models that a labelled line is "reliable" attribution (`prompts/analyze_system.md:7`, `prompts/verify_system.md:1`). The `_dx.md` Errors table ("Helper dies mid-call": recording proceeds, daemon log once) and the daemon's death warning (`daemon.py:_watch_capturers`) both expect the death. Neither bounds the labels it leaves behind.

The covered-window freeze has the same root cause. A fully covered Teams window stops updating its accessibility tree (`docs/SPEAKER-ATTRIBUTION.md` run 6; `native/teams-speakers/Sources/teams-speakers/main.swift:13`). If someone is speaking when the window gets covered, their frame class stays set, no `speaking: false` arrives, and their turn spans the whole covered stretch. US-001.EC-1 says the opposite: lines in that stretch get no name from the window. No test covers either case. UT-002 tests only the intended close at `end`.

Suggested fix (needs a spec decision; the rule "a turn still open at `end` closes there" is literal in `_spec.md` Label rules):
- When the log did not end (`ended is False`), close open turns at the last record's time, the helper's last sign of life, instead of at the meeting end. A periodic heartbeat line from the helper (for example the pass counter every N seconds) would make that time precise.
- For the frozen tree, have the helper detect a window whose tree stopped changing (the call timer text the spike used in runs 6–7) and emit `window … lost` or a `frozen` state so the codec closes its turns. That part is in reviewer B's helper scope.
- Add unit tests: a log without `stop` and with an open turn labels nothing after the last event; a frozen-then-lost window does not label the frozen stretch.

## Triage

- Decision: `VALID`
- Notes: Valid. Root cause: speaker_log_from_lines passed the meeting length to turns_from_events, so a turn left open by a dead helper or a frozen window ran to the meeting end and, since the remote rule precedes the energy rule, also overrode the user's own lines. Reproduced by the reviewer; reproduced again as UT-028.

Fix (decision of 2026-10-17 in _spec.md, _dx.md, _tests.md UT-028/UT-029): codec.speaker_log_from_lines now closes open turns at the time of the last event of the file (any event kind; garbage lines do not count) and treats window state `frozen` like `lost`; heartbeat events are no longer counted as skipped. The Swift helper (native/teams-speakers/Sources/teams-speakers/main.swift) writes a `heartbeat` every 5 s, tracks the call timer (DOM id call-duration-custom, element or its static-text child) per window, marks the window `frozen` after 3 s without change (open speaking states close with speaking:false first, tiles are not read while frozen), emits `found` again when the timer moves and reads tiles again from the next pass. `end` stays in the signature as the repository port's contract. Constants: Speakers.HEARTBEAT_EVENT, WINDOW_LOST, WINDOW_FROZEN.

Tests: tests/unit/test_speakers_codec.py (test_ut028_*, test_ut029_*, heartbeat not skipped), tests/unit/test_native_sources.py (helper source pins for heartbeat/frozen/timer id/cadence). Helper behavior itself is verified by swiftc -typecheck and a release build in a scratch path only; no live Teams run (not allowed here).
- Verified: (round 3, 2026-10-17) `codec.speaker_log_from_lines` now passes the time of the last event of the file to `turns_from_events` (codec.py:236), and `frozen` closes a window like `lost`. Rerun of the original repro through the real codec: a log with no `stop`, Lucas speaking from 600 s and a heartbeat at 605 s gives `SpeakerTurn(600.0, 605.0, Lucas)` (it used to run to 3600 s); a `frozen` main window at 700 s followed by heartbeats and `stop` at 3600 s gives `SpeakerTurn(600.0, 700.0, Lucas)`. The helper emits `heartbeat` every 5 s (main.swift:573-576) and `frozen` after 3 s without a timer change, closing open states with `speaking:false` first (main.swift:431-436), as the `_spec.md` decision says. test_ut028_*, test_ut029_*, the heartbeat-not-skipped test and the helper source pins pass; `xcrun swiftc -typecheck` exits 0. Limit: the helper was not rebuilt or run against a live Teams.
