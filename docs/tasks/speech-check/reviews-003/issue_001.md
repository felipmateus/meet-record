---
provider: manual
pr:
round: 3
round_created_at: 2026-10-23T16:25:44Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 516
severity: medium
author: claude-code
provider_ref:
---

# Issue 001: "Byte-for-byte whisper commands" contradicts the sample filter

## Review Comment

Several places promise that a recording with speech gets exactly the whisper commands it gets with the check off. None of them adds a condition:
- Safety Invariant 4 (`_spec.md:516`);
- the Goals (`:31`) and Business Rules (`:75`, "Everything else is unchanged");
- US-003.AC-1 and AC-2 (`_user_stories.md:67-68`, "every other key is as today");
- ADR-001 Positive (`adrs/adr-001.md:74`);
- Coverage Decisions (`_tests.md:247`).

Core Feature 2 and the duration stand-in change the input of that command on purpose. The whisper argv carries `-l <language>` (`transcriber_whispercpp.py:45-50`). In auto mode, which is the default, that language is `detection.language` (`processing.py:84-85`). With the check on, the use case does three new things:
- it drops samples without speech (`_spec.md:78`);
- it applies the planned-count rule (`:81`);
- it plans the offsets over the measured length when `meta.json` has no duration (`:80`).

Each can change the chosen language. Here are two examples from the code's own rules (`language.py:77-92`):
- Eight planned samples: five silent ones hear `en` at p >= 0.5 and three with speech hear `pt`. Check off: `en` wins 5 of 8 and whisper gets `-l en`. Check on: the three `pt` samples are kept, and whisper gets `-l pt`.
- One sample is kept of eight planned. Check off can pick a language by majority. Check on gives `too-few-votes` and the fallback.

`language_detection.samples` also differs, because it lists only the kept samples (`_spec.md:78`). So "every other key is as today" in US-003.AC-2 is false whenever a sample is dropped. When the duration is missing, `health.total_minutes` changes as well (UT-045).

This bites in two ways:
- An implementer who reads Safety Invariant 4 literally cannot ship the filter.
- A tester who writes the invariant's check with the default `language = "auto"` and a silent window gets different argv. The planned cases pass only because they never let the filter change the outcome: UT-043 and IT-004 run without a language detector, and E2E-002 keeps both of its windows (`sample_offsets(70.0)` gives `[10.0, 30.0]`, both inside `--segments 0:6000`).

Suggested fix: scope the promise to "the same whisper commands for the language and duration the use case chose". Equivalently: identical when the language is fixed, or when the filter drops no sample and `meta.json` has a duration. Add to US-003.AC-2 that `language_detection.samples` lists only the kept samples, and that the language may change by design (G2 measures this on the stored recordings). Make UT-043 say that it runs with a fixed language.

## Triage

- Decision: `VALID`
- Notes: Valid. In auto mode the filter, the planned-count rule and the duration stand-in can change `-l` and `language_detection` by design.
- Verified: `processing.py:84-85`, `language.py:77-92`.

### Resolution

The promise is scoped to "the language and duration the use case chose". It is byte-for-byte with a fixed language, and in auto mode only `-l` can differ. Updated: Goals, Business Rules › A recording with speech, Safety Invariant 4, US-003.AC-1/AC-2, ADR-001 Positive and Coverage Decisions. UT-043 now runs with a fixed language. New UT-056 is the auto-mode case where the filter turns `en` (5 of 8) into `pt` (3 of 3); its scripts are positional because `FakeLanguageDetector` answers by position.

- Round 4 (2026-10-23): reopened. The scoping landed in Business Rules (`_spec.md:75-79`), UT-043 (fixed language) and UT-056. UT-056 can be written against the real `FakeLanguageDetector` (`tests/fakes/__init__.py:200-222`, positional answers at p 0.99, two instances because both runs use the same audio path), and its arithmetic holds under `choose_language` (`language.py:77-91`): check off, 8 samples, `en` 5 of 8 → `5*2 > 8` and `5 >= 2` → `en`; check on, 3 kept of `planned=8`, so `needed = min_votes = 2`, `pt` 3 of 3 → `pt`. Two defects remain in the text the fix wrote:
  1. **The "only" clauses leave out the duration stand-in.** Safety Invariant 4 (`_spec.md:521`) says `-l` can differ "only through the language-sample filter and the planned-count rule". US-003.AC-1 (`_user_stories.md:67`) says it "can change only because samples without speech no longer vote". Goals (`_spec.md:31`) and ADR-001 Positive (`adrs/adr-001.md:74`) give the same single cause. But Business Rules (`_spec.md:76,79`) and Goal `:32` say that when `meta.json` has no duration, the stand-in changes the planned offsets. Today `sample_offsets(None)` is `[0.0]` and that one sample decides alone (`language.py:59-60,87`); with the check it is `sample_offsets(audio_seconds)`, several samples and `min_votes` 2. So `-l` can change with no sample dropped at all. Fix: name the three causes (the filter, the planned-count rule, the duration stand-in) in Invariant 4 and US-003.AC-1, or replace the "only" clause with "only through the language the use case chose (Business Rules › A recording with speech)". Goals and the ADR can say "the language samples change by design".
  2. **"Byte-for-byte today's" uses the wrong baseline.** `_spec.md:76` says that with a fixed language "the commands and every other key are byte-for-byte today's", and Invariant 4 (`:521`), Goals (`:31`) and the ADR (`:74`) say "today's" commands, first pass and retry. Rule B is not behind the check: it changes `health` for every new transcript (Impact row `domain/health.py`, Motivation "no longer … re-transcribed for nothing"), and the retry runs only when `health.degraded` (`processing.py:182`). So against today's code, `health` and the presence of the retry command can differ for a fixed-language meeting with speech. US-003.AC-1, UT-043 and E2E-002 already use the right baseline, a run with `speech_check = false` (or `speech_detector=None`). Fix: say "the same as with `speech_check = false`" in `_spec.md:31,76,521` and ADR `:74`, or list `health` (rule B) as an exception next to the two in US-003.AC-2.

Round 4 leftovers fixed (2026-10-23):
- Safety Invariant 4, US-003.AC-1 and ADR-001 Positive now name all three causes of a `-l` change: the sample filter, the planned-count rule and the duration stand-in. Goals mention the measured length.
- The baseline is the check-off run of the same code (`speech_check = false`), not "today's", in Goals, Business Rules, Invariant 4 and the ADR. Business Rules says why: rule B changes `health`, and the retry depends on it.

