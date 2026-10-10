# Implementation task summary for Story publishing (Backlog.md)

> Requirements: [prd.md](./prd.md) · Design: [techspec.md](./techspec.md) · Approved on 2026-10-10
> Each task ships with its own unit and integration tests and leaves `pytest` and `mypy` green.

## Tasks

- [x] 1.0 Publication state and story persistence
- [x] 2.0 Duplicate check across days and the redraft lock
- [ ] 3.0 Publisher port and the publish use case
- [ ] 4.0 Destinations switch: configuration and registry
- [ ] 5.0 Backlog.md spike, in-repository setup and the Backlog.md publisher
- [ ] 6.0 CLI: `trec publish`, publishing after drafts, `doctor` and `status`
- [ ] 7.0 Real-data validation and documentation

## Dependencies

1.0 → 2.0 → 3.0 → 4.0 → 5.0 → 6.0 → 7.0 (each task depends on the previous ones; 2.0 and 3.0 only share 1.0 and could run in either order).
