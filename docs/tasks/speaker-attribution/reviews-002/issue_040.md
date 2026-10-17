---
provider: manual
pr:
round: 2
round_created_at: 2026-10-17T14:01:36Z
status: resolved
file: native/teams-speakers/Sources/teams-speakers/main.swift
line: 441
severity: medium
author: claude-code
provider_ref:
---

# Issue 040: A marker-only main window hides the meeting window behind it

## Review Comment

`scanPass` walks the Teams windows in `kAXWindows` order (front to back). It keeps the **first** non-compact window that has `scan.callMarker || !scan.tiles.isEmpty` as `found["main"]`, and skips every later window of that kind (`if found[kind] != nil { continue }`, line 441, with the condition on line 446). `callMarker` turns true on any element whose first text part contains one of `callMarkers` (line 34). That list includes the generic substrings `"vídeo de "` and `"video of "`, which are not specific to the call UI.

Failure mode. New Teams opens a meeting in its own window. While the user has the main chat/calendar window in front, and that window renders any text with "Vídeo de …" outside an `AXTable`/`AXRow` (a chat message, a file name such as "Vídeo de treinamento.mp4", a calendar item), that window wins the `main` slot. It has no tiles. As a result:
- the meeting window behind it is never walked during that pass, so no `seen` or `speaking` event is read from it;
- `apply("main", …)` runs with zero tiles, so every tile present until then counts as lost and its open turn closes (`setSpeaking(..., false)`). Turns get cut while the front window changes;
- the main state's title switches to the chat window's title, and `noteSubject` emits a `title` event. When the chat window is in front at the first pass, the first `window`/`title` event carries its title. `codec.py:208-211` keeps the first subject, so `StopRecording` can title an untitled meeting "Chat" (or whatever the first title part is).

`docs/SPEAKER-ATTRIBUTION.md:103` already logged the keyword filter matching chat rows and a chat message in the Calendar window during the spike. Skipping `AXTable`/`AXRow` and the 200-character limit narrow that problem but do not close it for short texts in other roles.

Only the compact view gets a second chance, because it is found by its title. A covered meeting window is already a known limit; a meeting window that is visible but placed behind a chat window that happens to mention "vídeo de" is a separate case that loses labels for no reason.

Suggested fix: walk every non-compact window. Prefer the one with tiles, then one with a call marker. Or keep a separate state per window instead of per kind. Also limit `"vídeo de "`/`"video of "` to the roles where the spike saw them (the tile images). Then add a case to the probe notes or a unit-level check of the selection rule, if the selection is moved into a pure function.

## Triage

- Decision: `VALID`
- Notes: Valid. Root cause: scanPass kept the first non-compact window with callMarker or tiles, and callMarkers held the generic 'vídeo de '/'video of ', so a chat window in front could take the main slot and hide the meeting window.

Fix (main.swift): every non-compact window is walked until one with tiles is found (it wins); a marker-only window is only a fallback when none has tiles; 'vídeo de '/'video of ' moved to imageCallMarkers and match only AXImage elements. Compact view handling unchanged.

Tests: the selection is Swift-only, so tests/unit/test_native_sources.py pins the marker split; verified with swiftc -typecheck and a release build in a scratch path. Not exercised against a live Teams.
- Verified: (round 3, 2026-10-17) `scanPass` (main.swift:486-517) keeps walking non-compact windows until one has tiles, and keeps a marker-only window only as a fallback when none does. `vídeo de `/`video of ` moved to `imageCallMarkers` and match only `AXImage` (main.swift:39, 327-328). The compact handling is unchanged. test_the_generic_video_marker_words_only_match_images passes and `xcrun swiftc -typecheck` exits 0. Limit: the selection rule is Swift-only, so it was checked by reading the code, not run against a live Teams.
