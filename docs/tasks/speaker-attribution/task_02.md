---
status: completed
title: "Task 2: The teams-speakers helper"
type: feature
complexity: high
---

# Task 2: The teams-speakers helper

## Overview

Builds the native helper that reads the Teams meeting windows through the macOS Accessibility API and writes the speaker events the pipeline consumes. After this task an operator can run it by hand during a call and watch names and speaking states appear in `speakers.jsonl`; the spike script's findings become a product binary.

## Shippable Outcome

- Outcome: `teams-speakers --out <file> --epoch <unix s>` appends the documented events (start, window, title, seen, speaking, stop) while a Teams call runs, flushing each line, and exits on SIGTERM with a `stop` event; `--check` reports the Accessibility permission with exit 0 or 3.
- Verify in this task: `swiftc -typecheck` (IT-006), the unit test that greps the sources for `AXUIElementSetAttributeValue` (UT-076), and a manual run during a Teams call with another participant talking, whose events file is attached to the task evidence.
- Integration verification: the lifecycle through the adapter is IT-003/IT-004 in task 4 (with a stand-in); the live gates are E2E-001 in task 9.

## Requirements

- Contract: `_spec.md` › Core Interfaces (the command line block: options, exit codes, flush, read-only) and `_dx.md` › CLI › `teams-speakers` (exact messages).
- Behaviour: `_spec.md` › Data Models (events and fields; `start.epoch` echoes the given `--epoch`; the subject is the first title segment, the second for the compact view), › Integration Points (AX errors skipped and counted; no window for 30 s logs once a minute; Teams gone → keep polling), › Monitoring (what `speakers.log` carries), safety invariants 4 and 10.
- Speaking state: a tile (`AXMenuItem` whose text starts with the display name; the own tile is the `AXImage` "Vídeo de mim mesmo, <name>, …", recorded with `me: true` and never given a speaking state) is speaking while any direct child's `AXDOMClassList` contains `vdi-frame-occlusion` (ADR-001). State is tracked per `(window kind, name)`; a lost window closes its states with `speaking: false` events.
- Package: `native/teams-speakers/Package.swift` mirroring `teams-tap` (macOS 14.2+, embedded `Info.plist` with bundle id `local.teams-recorder.teams-speakers`); `scripts/build-native.sh` builds both packages, prints both paths, greps the helper's sources for `AXUIElementSetAttributeValue` and fails if found, and prints the rebuild reminder about the permission.
- Logging: stderr with timestamps (the spawner redirects it to `data/log/speakers.log`): arguments, permission state, Teams pid, windows and tiles found/lost, each state change, passes slower than 1 s with their element count, accessibility error counts per minute, exit reason.
- No code shared with `teams-tap`; English only in sources and messages.

## Subtasks

- [x] 2.1 Create the package and `Info.plist`; port the window detection, tile identification, `AXDOMClassList` reading and transition tracking from `scripts/ax-speaker-probe.swift`, dropping the `AXEnhancedUserInterface` write.
- [x] 2.2 Implement the event writer (JSON lines, flush per line), the `start`/`window`/`title`/`seen`/`speaking`/`stop` events and the counters.
- [x] 2.3 Implement `--check [--prompt]` and the exit codes; SIGTERM/SIGINT handling; the waiting behaviour without Teams or without a call window.
- [x] 2.4 Extend `scripts/build-native.sh`; add the sources grep test (UT-076) and the opt-in typecheck test (IT-006).
- [x] 2.5 Run it by hand during a Teams call with another participant and keep the events file and `speakers.log` excerpt as evidence (names may be redacted in the task notes).

## Implementation Details

### Relevant Files

- `scripts/ax-speaker-probe.swift` — the working AX walk the helper derives from (window detection, tile text, class lists, transitions by element path).
- `native/teams-tap/Package.swift`, `native/teams-tap/Sources/teams-tap/Info.plist`, `native/teams-tap/Sources/teams-tap/main.swift:1-100` — package layout, embedded plist, argument parsing and logging style.
- `scripts/build-native.sh` — the build script to extend.
- `docs/SPEAKER-ATTRIBUTION.md` §6 — runs 7 and 8: the tile structure and the frame class set.
- `_dx.md` › Files and › CLI › `teams-speakers` — the exact lines and messages.

### Dependent Files

- `src/teams_recorder/adapters/outbound/speakers_ax.py` — task 4 builds the command this helper parses.
- `scripts/install.sh`, `README.md` — task 9 documents the permission and the build.

### Related ADRs

- [ADR-001: Speaking state from the tile frame's class set, read through Accessibility](adrs/adr-001.md) — the signal and its risks.

## Deliverables

- `native/teams-speakers/` (package, sources, plist), the extended build script, the two tests, the manual-run evidence.

## Tests

- [x] UT-076 — no `AXUIElementSetAttributeValue` in `native/teams-speakers/Sources` (grep test).
- [x] IT-006 — `swiftc -typecheck` of the helper (opt-in, guarded by the presence of `swiftc`).

## Success Criteria

- During a real call, the events file shows `seen` for every tile and `speaking` transitions for the remote participant who talks; the `stop` event carries the counters; `speakers.log` shows no accessibility errors in a normal call.
- The helper never writes to Teams: the grep test passes and the build script enforces it.

## Completion Notes (2026-10-16)

Status stays `in_progress`: subtask 2.5 and the first Success Criterion need a real Teams call with another participant talking, which an agent session cannot provide. Nothing was committed.

### Delivered

- `native/teams-speakers/` (`Package.swift`, `Sources/teams-speakers/main.swift`, `Info.plist` with bundle id `local.teams-recorder.teams-speakers`); `.gitignore` ignores `native/teams-speakers/.build/`.
- `scripts/build-native.sh` greps the helper's sources for `AXUIElementSetAttributeValue` first (exit 1 with a message, checked with a temporary file containing the string), then builds both packages, prints both `binary:` paths and the Accessibility rebuild note.
- Tests: `tests/unit/test_native_sources.py` (UT-076), `tests/integration/test_native_build.py` (IT-006, `slow`, skipped without `swiftc`).
- Decisions: the display name comes from the `AXStaticText` under the tile that the tile's text starts with (so names with a comma survive), falling back to the text up to the first comma; a window is declared lost after 3 consecutive passes without it (guards against tree churn), closing its speaking states with `speaking: false` first; a tile that disappears while speaking also gets `speaking: false`; the `start` event carries `"teams_pid": null` when Teams is not running yet; `seen` is emitted once per tile per window found (reset when the window is lost); the own tile is matched by the prefix `vídeo de mim mesmo` or `video of myself` (the English form is a guess, only the Portuguese one was observed); `AXUIElementSetMessagingTimeout` (2 s, a read-side client setting, not a write to Teams) caps a hung read.

### Verified

- `swiftc -typecheck native/teams-speakers/Sources/teams-speakers/main.swift`: exit 0 (IT-006 passes in the suite).
- `scripts/build-native.sh`: exit 0, both binaries built (`swift build -c release`, teams-speakers in 47 s); the embedded `__info_plist` section is present.
- `native/teams-speakers/.build/release/teams-speakers --check` in the agent's shell: prints the `_dx.md` "missing" line, exit 3 (the exit-3 path; this shell has no Accessibility grant). `--out ... --epoch ...` in the same shell: logs the missing-permission line to stderr, exit 3, no file created. No arguments, missing `--epoch`, bad `--interval`, `--prompt` without `--check`: usage on stderr, exit 2. `--help`: exit 0.
- `pytest`: 631 passed, 8 skipped (baseline 629 + UT-076 + IT-006); `mypy`: clean.

### Not verified (needs the user)

The event loop itself has not run: every AX read, the `start`/`window`/`title`/`seen`/`speaking`/`stop` events, the per-line flush and the SIGTERM exit are untested at runtime, because the helper refuses to run without the Accessibility permission (exit 3 above) and the agent must not change macOS permissions or request the prompt. Subtask 2.5 and the first Success Criterion are open.

Run this from a terminal that has Accessibility permission (System Settings > Privacy & Security > Accessibility; grant it to the terminal app), while a Teams call with another participant talking is on screen (a Teams window with tiles, or the compact view, must stay visible):

```
cd ~/Projetos/Pessoal/teams-recorder
scripts/build-native.sh
native/teams-speakers/.build/release/teams-speakers --check          # expect: Accessibility permission: granted (exit 0)
native/teams-speakers/.build/release/teams-speakers --out /tmp/speakers-run1.jsonl --epoch "$(date +%s)" --verbose 2> /tmp/speakers-run1.log &
# let the other participant talk for a minute or two, then:
kill -TERM %1; wait %1; echo "exit $?"
cat /tmp/speakers-run1.jsonl; tail -n 40 /tmp/speakers-run1.log
```

What to look for in `/tmp/speakers-run1.jsonl`: first line `start` with the epoch you passed and a `teams_pid`; a `window` `found` (`main` or `compact`) and a `title` with the meeting subject; a `seen` line for every tile, your own with `"me": true`; `speaking` true/false pairs for the remote participant in step with their speech and none for you; last line `stop` with `"reason": "signal"` and the counters, `ax_errors` 0 in a normal call, and exit status 0. In the log: `tile seen` lines, `speaking:` / `silent:` lines, no `accessibility errors` lines and few or no `slow pass` lines. Try once with only the compact view visible. Keep both files (names may be redacted) as the task evidence, then set `status: completed` here.


## Live run (2026-10-17, with the user)

- **Fix found by the live run:** the first two runs saw the meeting window and its subject but no tile. A tile's accessible text repeats its title and its description joined by " | ", which together pass 200 characters (219 and 255 in the 2026-10-16 spike), and the helper skipped any text over 200 characters before matching the markers. Markers are now matched on the first " | " part only (`walk` in `main.swift`). The tests and the build guard pass after the fix.
- **Test setup that works:** the phone has to join as someone else. The same account on two devices is one participant in Teams, so the phone gets no tile of its own. The phone joined as an unverified guest named "teste", which Teams labels `teste Não verificado`; the helper records the name exactly as Teams shows it.
- **Run 3** (meeting `teste sonda`, the user muted on the Mac, the guest talking in bursts, main window visible): `start` with the given epoch and the Teams pid; `window found (main)`; `title` "teste sonda"; `seen` for the user's tile (`me: true`) and the guest's; 7 `speaking` transitions for the guest in step with the bursts, none for the user; `stop` with `reason: signal`, 139 passes, 7 transitions, 0 accessibility errors, 0 slow passes; about 142 elements per pass. Files: `data/log/speakers-run3.jsonl` and `.log` (git-ignored).
- **Not covered:** the compact view alone was not exercised in this run (it was in the 2026-10-16 spike runs 7–8).
- **Open question for the spec:** whether the helper needs to ask Chromium for its accessibility tree. The spike probe (which does ask, through `AXEnhancedUserInterface`, refused with -25208) ran in the same Teams process before run 3, so run 3 cannot tell whether the tree would have been exposed without it. Repeat run 3 after Teams restarts, without running the probe first. If no tile appears, the helper needs that request, which safety invariant 4 currently forbids; that is the user's decision.
