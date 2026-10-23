---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 77
severity: medium
author: claude-code
provider_ref:
---

# Issue 004: After the filter, one speech sample decides a long meeting's language

## Review Comment

`choose_language` lowers the vote requirement to 1 "when the meeting has one sample": `needed = 1 if len(kept) == 1 else rules.min_votes` (`domain/language.py:87`). Here `kept` is the list passed in. The spec filters the samples before `detect` (`_spec.md:77-79`, step 7 at `:305`). After that, a long meeting with a single window holding 3 s of speech is decided by one vote. Before the filter, that rule only applied to meetings of 30 s or less, or of unknown length.

This is the failure G1 was about. In 2026-10-17_09-56-47 one sample heard `en` with p 0.75 (§10, language-detection G1). If the filter keeps only that window, a Portuguese meeting is transcribed with `-l en`. The Evidence table shows meetings near the edge: 2026-10-17_09-44-07 has per-window speech of `5 3 0`, and the `3` is rounded, so 1 or 2 samples survive depending on the real value. The spec, US-004 and UT-044/046 never say whether `min_votes` applies to the planned count or the kept count, and G2 only checks that results are unchanged on today's 26 recordings.

Suggested fix: make it a rule. For example, the one-vote exception applies only when `sample_offsets` planned a single sample, so `choose_language` needs the planned count, or the use case passes the filtered-out offsets as samples with no language. Add a UT: 8 planned, 1 kept hearing `en` → fallback with `too-few-votes`, or the opposite if that is the decision. Record the per-window seconds of 09-44-07 unrounded in G2.


## Triage

- Decision: `VALID`
- Notes: Valid. `needed = 1 if len(kept) == 1` (`language.py:87`) counts the samples passed, so after the filter one window could decide a long meeting.
- Verified: `domain/language.py:77-92`, `processing.py:112`.
- Verified (round 2, 2026-10-23): `planned: int | None = None` is consistent in `_spec.md:81,221,318,382,517`, US-004.EC-4, UT-008 and UT-055. Checked against `domain/language.py:77-92`: `planned=8` with one counted sample gives `TOO_FEW_VOTES` (`counted == 1`), and two `en` give `MAJORITY`. G2's pass clause on `too-few-votes` is a separate defect (round 2 issue 001).

### Resolution

The one-vote exception follows the planned count. `choose_language` gains `planned: int | None = None` (None: today's behavior), and `_language` passes `len(offsets)`. Several planned and one kept gives `too-few-votes` and the fallback. Updated: Business Rules › Language samples, Core Interfaces step 7, System Architecture, Impact Analysis, Known Risks, File References, US-004.EC-4. Tests: new UT-008 (domain) and UT-055 (use case). G2 passes on no `too-few-votes` loss and records the unrounded window seconds of 2026-10-17_09-44-07.
