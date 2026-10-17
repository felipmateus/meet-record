---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 353
severity: medium
author: claude-code
provider_ref:
---

# Issue 008: trec status cannot show 0% labelled, which the drift mitigation needs

## Review Comment

Two places rely on `trec status` showing 0% to reveal Teams UI drift:
- Known Risks (`_spec.md:353`): "visible in `trec status` (0% labelled)";
- ADR-001 Risks: "0% coverage visible in `trec status`".

The contracts make 0% invisible:
- `_dx.md:158-163` adds the speakers segment only "when the transcript has labels".
- US-009.EC-2 and UT-064 require no segment for transcripts made before the feature.
- A new zero-label `transcript.json` has no `speaker` key anywhere (`_spec.md:232`), which is the same shape as a pre-feature file. `label_share` returns 0.0 for both (`_spec.md:170`).

`trec status` already loads each transcript (`adapters/inbound/cli.py:91,137-142`), but it has nothing to tell the two cases apart. So drift to 0% looks exactly like an old meeting.

Suggested fix: when labelling ran, persist a marker in `transcript.json`, for example `"speakers": {"labelled": n, "total": m, "reason": "..."}`. Show `· speakers 0% (<reason>)` for those transcripts and keep no segment for files without the marker. This also gives `trec transcribe` its reason (issue 005). The alternative is to drop the claim from Known Risks and ADR-001.

## Triage

- Decision: `VALID`
- Notes: Fixed: the labelling summary persisted in `transcript.json` makes `0%` with the reason visible in `trec status` for transcripts labelling ran on, and nothing for pre-feature transcripts (UT-064, `_dx.md` status example). (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: The labelling summary is persisted under `transcript.json › speakers` for every transcript labelling ran on and is absent on older ones (`codec.transcript_to_dict`), so `trec status` can show `0% (<reason>)`; UT-064 is in `tests/unit/test_cli_speakers.py` (CLI is reviewer B's round-2 scope). (review round 2, reviewer A)
