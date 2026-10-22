# Run log: cy-create-spec, language detection before transcription

Skill run: cy-create-spec (2026-10-21, finished 16:33). Output: `docs/tasks/language-detection/` (`_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md`, `adrs/adr-001.md`). No code was changed, nothing was committed, and no Claude credit was spent. Every measurement ran locally on scratch copies of the audio; nothing under `data/recordings/` was written.

## Questions asked and answers given

The user's request (in Portuguese): "I want to create a new feature that identifies the language before transcribing, to raise the transcription quality."

Asked once, before the skill ran, after the first detection measurements (one question round, three questions):

1. **Do your meetings mix languages within one call (for example, Portuguese with the team, then English when the client joins)?**
   Options: rare, one language per meeting (recommended); common, detect per stretch; dominant now, per stretch later.
   **Answer: "Rare: one language per meeting (recommended)".**
2. **Which languages may the detection choose?**
   Options: Portuguese and English (recommended); Portuguese, English and Spanish; any language.
   **Answer: "Portuguese and English (recommended)".**
3. **How do you want to run the delivery?**
   Options: spec + tasks first (recommended); implement directly here; only the plan for now.
   **Answer: "Spec + tasks first (recommended)".**

No question was asked during the skill run itself: the three answers above settled the product decisions the evidence could not.

## Evidence gathered during the run

- `whisper-cli -l auto -dl` on 30-second clips: the 2026-10-08 MARTA meeting `en` in 12 of 12 clips; the 2026-10-14 vans meeting `en` in 3 and `is` (Icelandic, a false answer on clipped audio) in 5; two Portuguese meetings `pt` in every clip (p ≥ 0.99).
- `-np` hides the detection line. Several `-f` in one call load the model once (3 clips in 7.1 s).
- The vans meeting re-transcribed in English: the first pass is still 69% loops; the anti-loop retry in English drops to 10.4% with text in 35 of 37 min and coherent content, against 69% in the stored Portuguese transcript.

## Open items left to the user

- Approve the spec, then the task breakdown (`cy-create-tasks`); optional independent peer review of the spec.
- Backfill of the two English meetings (re-transcribe and re-analyze; re-analysis spends the subscription and runs a curator pass). Their audio is purged after 2026-11-07 and 2026-11-13.
- Whether to exempt short backchannel lines ("Okay.") from the loop guard, decided after gate G2.
