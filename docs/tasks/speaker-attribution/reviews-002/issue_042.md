---
provider: manual
pr:
round: 2
round_created_at: 2026-10-17T14:01:36Z
status: resolved
file: native/teams-speakers/Sources/teams-speakers/main.swift
line: 505
severity: low
author: claude-code
provider_ref:
---

# Issue 042: Helper log lines differ from the texts _dx.md promises

## Review Comment

`_dx.md` › Errors and › CLI › `teams-speakers` quote the helper's log lines. Users and agents grep `data/log/speakers.log` for those texts, and the README Troubleshooting points there. Two of the lines differ from what the helper writes:

- **No window.** `_dx.md` › Errors, row "No Teams window read", promises the helper log `no Teams meeting window found; waiting` once a minute. The helper writes `no call window with tiles for N s` (main.swift, the `lastNoWindowLog` branch of the run loop, line 505). Grepping for the documented text finds nothing.
- **Tile seen.** `_dx.md` › CLI shows `teams-speakers: tile seen: Felipe Mateus de Carvalho (me)`. The helper appends the window kind: `tile seen: Felipe Mateus de Carvalho (me) (main)` (the `log("tile seen: …")` call in `apply`). That is harmless, but it differs from the contract.

Every other quoted line matches the code: the Teams not running line, `window found (main): …`, the start line, the stopping summary, and the `--check` texts with their exit codes.

Suggested fix: pick one text and align both sides. Either change the helper's message to the documented `no Teams meeting window found; waiting`, or amend `_dx.md` (Errors table and CLI sample) to the shipped texts, including the `(main)`/`(compact)` suffix. Then pin the no-window text with the UT-076-style source grep in `tests/unit/test_native_sources.py`, so they cannot drift again.

## Triage

- Decision: `VALID`
- Notes: Valid; the code's wording is the better contract for the tile line, the documented wording for the no-window line.

Fix: helper now logs `no Teams meeting window found; waiting (N s without a call window with tiles)` (documented prefix plus the duration); _dx.md amended: the tile seen sample lines carry the `(main)` suffix the helper writes, the Errors row quotes the new no-window text, and a note describes the frozen/heartbeat log and events. Pinned in tests/unit/test_native_sources.py (helper source and _dx.md both contain the texts).

Tests: tests/unit/test_native_sources.py.
- Verified: (round 3, 2026-10-17) The helper logs `no Teams meeting window found; waiting (N s without a call window with tiles)` (main.swift:565). `_dx.md` quotes that text in the Errors table (line 232) and shows the `tile seen: … (main)` suffix in the CLI sample (lines 115-116). test_the_helper_logs_the_no_window_text_the_dx_contract_quotes and test_the_dx_contract_shows_the_tile_seen_line_with_its_window_suffix pin both sides and pass.
