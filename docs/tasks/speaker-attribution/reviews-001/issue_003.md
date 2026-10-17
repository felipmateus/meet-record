---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 270
severity: high
author: claude-code
provider_ref:
---

# Issue 003: Accessibility grant identity unverified; doctor may check the terminal

## Review Comment

The spec assumes the Accessibility grant attaches to the `teams-speakers` binary through its embedded `Info.plist`, "like teams-tap" (`_spec.md:270,329`). The `_dx.md` golden path and doctor lines say "Allow teams-speakers under ... Accessibility", and PRD decision 1 says "as it already does for the audio permission".

Evidence in the repo points the other way:
- `prd/appendix/integrations.md:21` records that the Microphone permission goes to "the responsible process (the daemon's python / Claude in manual use)". Yet the microphone is recorded by `teams-tap --mic`, the same binary with the same embedded plist. So the plist did not give the binary its own TCC identity for that service.
- Every spike run used Accessibility granted to the terminal (`docs/SPEAKER-ATTRIBUTION.md` run 1; `scripts/ax-speaker-probe.swift:100`: "Grant it to your terminal"). No run spawned a helper from the LaunchAgent.

The likely consequence: `teams-speakers --check` run by `trec doctor` from a terminal checks whichever process TCC holds responsible. On the dev Mac that is the terminal, which already holds the grant from the spike. The daemon-spawned helper inherits the daemon's responsibility instead. The doctor can then print `[ok ] ... permission granted` while every recording writes `unavailable: permission-missing`. The other way out is granting Accessibility to the daemon's Python interpreter, which is a broad grant. UT-061/IT-005 use stand-ins and cannot catch this.

Not verified at runtime: it needs a LaunchAgent run and TCC changes, which AGENTS.md reserves for the user's approval.

Suggested fix: add a gate before tasks 2–3. Spawn the built helper from the installed daemon, with the user's approval. Record which TCC entry appears and what `--check` returns there and from a terminal. Then specify:
- which identity receives the grant (the helper's own LaunchAgent, disclaimed responsibility, or the daemon);
- the context of the doctor's check, for example also reporting the last observer start result from the latest `speakers.jsonl`;
- the matching installer and README text.

## Triage

- Decision: `VALID`
- Notes: Accepted: task 0 (permission identity spike, with the user's approval) added to the build order with the three candidate designs; `trec doctor` reports its own `--check` and the last recording's observer outcome and warns on a mismatch (UT-065, IT-007); installer/README text depends on task 0; PRD FR10/decision 1 note added. (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: Task 0 ran (task_03, 2026-10-17) and the spec records the decision (Integration Points › macOS TCC: the helper as its own launchd job; the doctor's `--check` as the short-lived job `local.teams-recorder.speakers-check`, plus the last-recording mismatch warning). `speakers_ax.AxSpeakerObserver.problems()` boots the check job; UT-065 is in `tests/unit/test_cli_speakers.py`. The doctor and docs details are reviewer B's round-2 scope. (review round 2, reviewer A)
