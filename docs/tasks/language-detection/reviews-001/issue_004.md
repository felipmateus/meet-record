---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 68
severity: low
author: claude-code
provider_ref:
---

# Issue 004: Detection timing claims are wrong: the encoder dominates, not model load

## Review Comment

`_spec.md:68` says "3 samples in one call took 7 s, mostly loading the model once". `_spec.md:373` says "about 20 s for 12 samples, instead of about 35 s". US-001.EC-3 (`_user_stories.md:40`) says "detection time stays near 20 s", and `adrs/adr-001.md:67` says about 20 s.

Measured with the spec's own command (whisper.cpp 1.9.4, `large-v3-turbo-q5_0`, M1, 3 scratch clips in one `-dl` call, exit 0, `real 7.03`):

```
whisper_print_timings:     load time =   558.52 ms
whisper_print_timings:   encode time =  6175.35 ms /     3 runs (  2058.45 ms per run)
whisper_print_timings:    total time =  6903.41 ms
```

The model load is about 0.56 s. Each sample costs about 2.06 s of encoder time. 12 samples therefore come to roughly 0.56 + 12 × 2.06 ≈ 25-26 s plus 12 ffmpeg cuts. One call per sample costs about 12 × 2.9 ≈ 35 s, so a single call saves about 10 s, not 15. The multi-file call is still the right choice. The numbers and the rationale are what is wrong. The same arithmetic matters for Windows CPU-only whisper against the 300 s timeout (`_spec.md:383`): the cost scales with the number of samples, not with the model load. That margin is untested and needs verification there.

Suggested fix: restate the cost as "about 0.6 s plus about 2 s per sample on the M1 (about 25 s for 12)" in `_spec.md:68`, `:373`, US-001.EC-3 and the ADR. Note that Windows timing is unmeasured.

## Triage

- Decision: `VALID`
- Notes: Valid. The encoder (about 2 s per sample) dominates, not the model load (0.56 s).
- Verified: The reviewer's `whisper_print_timings` on the 3-clip call; spec arithmetic.

### Resolution

Cost restated as about 0.6 s plus about 2 s per sample, about 25 s at the 12-sample cap, about 10 s saved by one call: High-Level Constraints, Evidence bullet (with whisper's own timings), Key Decisions, the eval-scripts impact row, US-001.EC-3, ADR Decision and Negative consequences. Windows marked unmeasured.
