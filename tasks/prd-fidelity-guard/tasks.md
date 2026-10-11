# Implementation task summary for the fidelity guard

> Requirements: [prd.md](./prd.md) · Design: [techspec.md](./techspec.md) · Status: draft for approval (2026-10-11)
> Each task ships with its own tests and leaves `pytest` and `mypy` green. Changing the daemon's behavior needs `trec agent restart`, only with the user's approval.

## Tasks

- [ ] 1.0 Transcript health: `-mc 0` by default, `transcript_health()`, a VAD retry when still degraded, `degraded` marking, notification and banner (P0; validates G1 on the real 2026-10-08 audio)
- [ ] 2.0 Verification in the domain and persistence: `Verification`, optional fields, codec defaults for old analyses
- [ ] 3.0 Claim verifier port, Sonnet adapter with transcript windows, the two code checks, the `VerifyAnalysis` pipeline step
- [ ] 4.0 Downstream use of the marks: minutes ⚠️, planner input "a confirmar", story sources limited to confirmed actions
- [ ] 5.0 Provenance in the stories: `Criterion(text, source)`, the writer rule, timestamp validation in `to_drafts`, display in the drafts document and the Backlog.md task
- [ ] 6.0 Analysis prompt fixes (owners only when named or self-assigned, participants who speak, tentative ≠ decided, no sensitive data) — merges the two follow-up tasks filed on 2026-10-10
- [ ] 7.0 Configuration, container wiring, `trec doctor` and `trec status` lines, usage logging
- [ ] 8.0 Validation: gates G2 and G3 on the synthetic stories corpus, G4 with the user on a week of real drafts; documentation (PRD pages 02, 03, 08; requirements §10; README; AGENTS ports table)

## Dependencies

1.0 is independent and the most urgent (a broken transcript invalidates everything after it). 2.0 → 3.0 → 4.0 → 5.0; 6.0 can run in parallel with 2.0–5.0 but its effect is measured in 8.0; 7.0 follows 3.0 and 5.0.
