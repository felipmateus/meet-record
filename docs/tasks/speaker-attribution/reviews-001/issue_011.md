---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 364
severity: medium
author: claude-code
provider_ref:
---

# Issue 011: Invariant 4 allows a write to Teams that the PRD forbids

## Review Comment

Safety invariant 4 (`_spec.md:364`) contradicts itself. It says the helper "never sets focus, attributes or values", then allows "the only `set` is the `AXEnhancedUserInterface` hint on the application element".

The approved PRD has no such exception:
- FR9: "it writes nothing to Teams";
- decision 5: "The helper is read-only";
- §4: "the observer only reads".

The spike showed the set is unnecessary. Teams answers `kAXErrorNotImplemented` (-25208), and Chromium exposes the tree as soon as it is read (`docs/SPEAKER-ATTRIBUTION.md` runs 1 and 7). Neither ADR-001 nor the Implementation Design needs the set. No test or design element owns this invariant either: the helper cannot be tested automatically, and the gates do not check it.

If Teams ever implements the attribute, the set could switch the web view into full screen-reader mode. That would change Teams' behaviour and cost without the user knowing.

Suggested fix: drop the exception, so the helper performs no AX set at all. Add the rule to the helper's review checklist or manual gate, for example "no `AXUIElementSetAttributeValue` in `native/teams-speakers`", checked by a grep in the build script or a test.

## Triage

- Decision: `VALID`
- Notes: Fixed: invariant 4 drops the exception; the helper sets no accessibility attribute; a unit test greps the sources and the build script runs the same check (UT-076); ADR-001 implementation notes updated; PRD FR9 note added. (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: Invariant 4 has no exception; `grep -rn AXUIElementSetAttributeValue native/teams-speakers/Sources` finds no call in the helper sources, and UT-076 (`tests/unit/test_native_sources.py`) passes. The open question about `AXEnhancedUserInterface` is recorded in the spec's Open Questions for the user's decision, not as an allowed write. (review round 2, reviewer A)
