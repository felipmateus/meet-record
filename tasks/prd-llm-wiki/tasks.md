# Implementation task summary for the LLM wiki of meetings

> Requirements: [prd.md](./prd.md) · Design: [techspec.md](./techspec.md) · Evaluation: [evaluation.md](./evaluation.md) · Status: draft for approval (2026-10-10)
> Each task ships with its own unit and integration tests and leaves `pytest` and `mypy` green. Runs on the real model or real meeting content need the user's approval first (AGENTS.md).

## Tasks

- [ ] 1.0 Spike: a manual LLM wiki over the existing meetings, the first schema, go/no-go (gate G1)
- [ ] 2.0 Domain, persistence and configuration
- [ ] 3.0 Wiki store and Git history adapters
- [ ] 4.0 Ports, the ingest use case and the pipeline post-step
- [ ] 5.0 Claude wiki writer and the ingest prompt
- [ ] 6.0 CLI: `trec wiki ingest|lint|rebuild`, `doctor`, `status`, container wiring
- [ ] 7.0 Evaluation harness: synthetic corpus, runner, judge, synthetic run (gate G2)
- [ ] 8.0 Real-data validation, schema tuning, switch-on decision and documentation (gates G3, G4)

## Dependencies

1.0 → 2.0 → 3.0 → 4.0 → 5.0 → 6.0 → 7.0 → 8.0. The corpus and questions of 7.0 (7.1–7.3) only need 1.0 and can be written while 2.0–6.0 are built; the runner (7.4) needs 6.0. 8.0 needs the user's time for the answer key, the labels and the review of the pages.

## Commit wave

Wave 9 in `docs/COMMITS.md`: one layered set of commits per task (`docs`, `feat(domain)`, `feat(application)`, `feat(adapters)`, `feat(cli)`, `test`), each commit leaving the tree importable, committed only with the user's approval.
