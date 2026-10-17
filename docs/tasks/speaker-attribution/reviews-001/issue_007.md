---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 259
severity: medium
author: claude-code
provider_ref:
---

# Issue 007: label_segments arithmetic and segment eligibility are underspecified

## Review Comment

The pure labelling contract (`_spec.md:198,259`) leaves four choices open that change labels:

1. **Mean of dBFS.** The spec does not say whether the mean is an arithmetic mean of dB values or a power mean. Digital silence is stored as −120 dBFS, so an arithmetic dB mean is dominated by that arbitrary floor. Example segment: a remote speaker talks half the time at −25 dBFS on the tap track (−120 in the pauses), so the tap mean is −72.5. Speaker leakage on the mic at −40/−55 gives a mic mean of −47.5. Then mic − tap = 25 ≥ 6 and mic ≥ −50, so the line is labelled as the user. That is exactly the false positive ADR-002 says the margin prevents. A power mean gives tap ≈ −28 dB and no label.
2. **"Windows inside [start, end]".** Partial edge windows are not defined. Segments shorter than 0.1 s, or zero-length ones (whisper emits start == end), select no window, so the mean is undefined (empty mean, division by zero).
3. **Zero-duration overlap rule.** "Largest overlap ≥ min_overlap × duration" becomes 0 ≥ 0 when the duration is 0, so any name with no overlap at all qualifies. The tie-break between equal overlaps is also undefined.
4. **Eligibility.** Part II labels and counts "segments with text" (`_spec.md:170,259`), but US-003.EC-1 and UT-016 exclude non-speech markers such as `[BLANK_AUDIO]`. The existing predicate is `domain/health.is_speech` (`health.py:42-45`). `health.py` imports `models.py` (`health.py:22`), so `Transcript.label_share` cannot import it without a cycle. Whether segments inside a hallucination loop get labels is also unstated.

Suggested fix: specify the power mean, or exclude windows at the floor. Define window selection (overlap-weighted, or midpoint in range). Give no energy label when no window falls inside, and no label at all when the duration is 0 or less. Require overlap > 0 and a deterministic tie-break. Name `is_speech` as the eligibility rule and move it into `models.py`, or compute the share in `speakers.py`. Add a unit test for each rule.

## Triage

- Decision: `VALID`
- Notes: Fixed: power mean, windows by midpoint, no energy label without a window, zero-duration segments ineligible, positive overlap required, deterministic tie-break, `is_speech` moved to `models.py` and re-exported by `health.py` (UT-008, UT-012b, UT-013b, UT-016, UT-016b). (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: Label rules now specify the power mean, midpoint selection, no energy label without a window, zero-duration ineligible, positive overlap and the tie-break; `domain/speakers.py` implements them and `is_speech` moved to `domain/models.py` (re-exported by `health.py`). UT-008, UT-012b, UT-013b, UT-016, UT-016b pass in `tests/unit/test_speakers.py`. (review round 2, reviewer A)
