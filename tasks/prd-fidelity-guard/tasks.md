# Implementation task summary for the fidelity guard

> Requirements: [prd.md](./prd.md) · Design: [techspec.md](./techspec.md) · Status: draft for approval (2026-10-11)
> Each task ships with its own tests and leaves `pytest` and `mypy` green. Changing the daemon's behavior needs `trec agent restart`, only with the user's approval.

## Tasks

- [x] 1.0 Transcript health: `-mc 0` by default, `transcript_health()`, a VAD retry when still degraded, `degraded` marking, notification and banner (P0; validates G1 on the real 2026-10-08 audio) — done 2026-10-11; the loop is counted within 30 consecutive segments (see requirements §10 notes); the banner in the drafts document moves to 4.0; G1 met on the real meeting retranscribed by the product (text in 86 of 86 minutes, ~1% in loops); code-review findings fixed the same day
- [x] 2.0 Verification in the domain and persistence: `Verification`, optional fields, codec defaults for old analyses — done 2026-10-12; nothing is verified yet (3.0), and unverified claims are written exactly as before
- [x] 3.0 Claim verifier port, Sonnet adapter with transcript windows, the two code checks, the `VerifyAnalysis` pipeline step — done 2026-10-13, not wired into the container yet (7.0), so the daemon does not verify; a verifier failure leaves its claims unverified (FR3); 7.0 must give the verifier and `VerifyAnalysis` the same `[user] name`
- [x] 4.0 Downstream use of the marks: minutes ⚠️, planner input "a confirmar", story sources limited to confirmed actions; the degraded-transcript banner in the drafts document, per source meeting (moved from 1.0; PRD decision 9) — done 2026-10-14; the marks show once task 7.0 switches verification on, the degraded-transcript banner in the drafts already now
- [x] 5.0 Provenance in the stories: `Criterion(text, source)`, the writer rule, timestamp validation in `to_drafts`, display in the drafts document and the Backlog.md task; tasks with ⚠️ marks are published marked into Triagem (PRD decision 10) — done 2026-10-14; the cited timestamps are checked in `DraftUserStories` (it has the transcripts), not in `to_drafts`
- [x] 1.1 Retry choice and broken audio (from the 2026-10-14 wrong-sample-rate incident, PR #18): — done 2026-10-14
  - **The choice:** prefer a retry with no loops when it keeps most of the first pass's minutes with text (e.g. 85–90%). On 2026-10-14_15-00-56 the first pass (69% of segments in loops, text in 35 of 37 min) beat the retry (0%, 31 of 37), because a minute counts as covered by any line outside a loop.
  - **Skip the retry when the capture counters already show a wrong sample rate:** VAD cannot repair that audio, and it cost 4 minutes there.
  - **The drafts banner:** it also covers transcripts with `rate_mismatch`, not only `degraded`.
- [ ] 6.0 Analysis prompt fixes (owners only when named or self-assigned, participants who speak, tentative ≠ decided, no sensitive data) — merges the two follow-up tasks filed on 2026-10-10
- [ ] 7.0 Configuration, container wiring, `trec doctor` and `trec status` lines, usage logging; a transcript whose health is `rate_mismatch` or still `degraded` never yields confirmed claims. The verifier reads the same hallucinated text the analysis came from, so it would confirm what was invented (PRD decision 4): every claim is unconfirmed, with the reason, or verification is skipped and the banner explains why
- [ ] 8.0 Validation: gates G2 and G3 on the synthetic stories corpus (G2 must run the product's `ClaudeClaimVerifier`, not the prototype's own prompt in `scripts/fidelity_eval.py defend`), G4 with the user on a week of real drafts (meetings with a `rate_mismatch` transcript left out, and the drafts of 2026-10-13/14 reviewed, since they rest on garbled audio); documentation (PRD pages 02, 03, 08; requirements §10; README; AGENTS ports table)

## Dependencies

1.0 is independent and the most urgent (a broken transcript invalidates everything after it); 1.1 follows PR #18 (the `rate_mismatch` health field). 2.0 → 3.0 → 4.0 → 5.0; 6.0 can run in parallel with 2.0–5.0 but its effect is measured in 8.0; 7.0 follows 3.0 and 5.0.
