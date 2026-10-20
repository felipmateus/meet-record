---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_dx.md
line: 14
severity: low
author: claude-code
provider_ref:
---

# Issue 016: Per-pass CLI counts have no data source in CuratorOutput

## Review Comment

`_dx.md` prints per-pass counts: `ok (+4 yours, 2 waiting, 3 context)` and `ok (+1 yours, 1 suggestion, 1 date changed)` (`_dx.md:14,16,159`). `CuratorOutput` carries only `ops`, `user_removed`, `focus`, `summary`, `notify` and `ignored` (`_spec.md:214-220`). `PassRecord` stores `ops_applied` and `ignored` counts (`_spec.md:223-238`). And the spec says code "never parses item lines" (`_spec.md:107`, ADR-001). Refs could give "+N yours / waiting / context" if each op's `refs` were mapped by prefix (`a`, `o`, `d/q/r`), though inserts that only add a 💬 also carry `u` refs. But "1 suggestion" and "1 date changed" cannot be derived from either source without reading the op text. An implementer has to invent a source or drop the format.

The same question applies to `trec activities` `Open: 7 yours · 3 waiting on others · 2 agenda · 5 context` (`_dx.md:29`, UT-082). That needs a per-section count by heading, which is acceptable as plumbing, but the spec should say so.

The bootstrap prompt says "using your Claude subscription" (`_dx.md:13,169`), which is wrong when `llm.provider = "api"`, where it spends API credit.

Suggested fix: either add a small `counts` object to `CuratorOut` (`added_mine`, `added_waiting`, `added_context`, `suggestions`, `date_changes`), stored in `PassRecord` and printed as is, or reduce the CLI line to `ok (<n> edits) — <summary>`. State that `trec activities` counts open checkboxes per `messages.ActivityDoc` heading. Pick the confirmation wording by provider.

## Triage

- Decision: `VALID`
- Notes: Valid. `CuratorOut` has no per-kind counts, `PassRecord` stores totals only, and ADR-001 forbids parsing item lines, so "+4 yours, 2 waiting", "1 suggestion", "1 date changed" had no source; the confirmation text said "subscription" regardless of provider.
- Verified: per-pass line `ok (<n> edits) — <summary>`, counts by `messages.ActivityDoc` heading (`ActivitiesStatus.counts`), provider-specific confirmation and `Activities.EST_SECONDS_PER_PASS`; `_dx.md` golden path and curate section; UT-082/088/110.

### Resolution

Fixed with the second suggested option. Per-pass line is `ok (<n> edits) — <summary>` with `n = ops_applied` and the curator's own one-line summary (Portuguese LLM content, like the existing analyze summary line); `trec activities` counts come from the document by `messages.ActivityDoc` heading (open checkboxes; plain lines for agenda and context; a renamed heading is omitted), stated as plumbing; the bootstrap confirmation follows `llm.provider` (subscription vs API credit) and the estimate is passes × `Activities.EST_SECONDS_PER_PASS` (160 s, new default). `_dx.md` golden path, curate and activities sections; Assumptions. Tests: UT-082 (counts by heading), UT-088 (wording by provider), UT-110.

