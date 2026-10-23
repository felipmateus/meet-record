---
provider: manual
pr:
round: 1
round_created_at: 2026-10-23T14:43:57Z
status: resolved
file: docs/tasks/speech-check/_spec.md
line: 89
severity: medium
author: claude-code
provider_ref:
---

# Issue 002: Recovery path leaves the empty analysis and curator pass behind

## Review Comment

The mitigation for a false "no speech" is "`speech_check = false` and `trec transcribe <id>`" (`_spec.md:89`, `:102`, `:470`; `_user_stories.md:151` US-008.AC-2; the `_dx.md:26` WARNING text). In the daemon the flow continues (user decision), so by the time the user sees the notification the meeting is already `analyzed`:
- `Pipeline.process` (`pipeline.py:49-59`) runs `AnalyzeMeeting`, which writes the local empty `analysis.json` and `minutes.md`;
- the curator then logs a `skipped_empty` pass (`use_cases/activities.py:299-303`, `has_content` false). `pending()` treats `skipped_empty` as a successful pass (`activities.py:404-410`).

`trec transcribe <id>` replaces only `transcript.json`/`.txt` (`repository_fs.py:189-192`). `derive_status` still returns `ANALYZED` because analysis takes precedence (`status.py:37-49`). The CLI then prints `Cli.ANALYZE_HINT` "Analyze with `trec analyze`." (`cli.py:513`). But `trec analyze` with no id picks only `TRANSCRIBED` meetings (`cli.py:536-541`), so it does nothing for this one. The result is a real transcript under minutes that say "Empty transcript: no speech recognized.", and the meeting never reaches `atividades.md`. Only `trec analyze <id>` (which also curates, `cli.py:567-568`) repairs it, and no artefact says so.

A second problem: `speech_check = false` is global. Until the user flips it back, every daemon transcription after the next `trec agent restart` skips the check.

Suggested fix: make the recovery a contract. The WARNING line, US-008.AC-2 and the troubleshooting doc should name `trec transcribe <id>` then `trec analyze <id>`, and say to turn the check back on. Alternatively, add a per-run override (for example `trec transcribe <id> --no-speech-check`) so the config does not have to change. Add a UT/E2E that redoes a no-speech meeting that was already analyzed and asserts the analysis is rebuilt.


## Triage

- Decision: `VALID`
- Notes: Valid. `trec analyze` with no id picks only `transcribed` meetings (`cli.py:536-541`), and the daemon has already analyzed the meeting.
- Verified: `cli.py:527-570`; `load_settings` is called once per process (`cli.py:55`), so the daemon keeps its config until a restart.
- Round 2 (2026-10-23): the 3-step contract is consistent in Business Rules (`_spec.md:91-95`), User Experience (`:103`, `:109`), `_dx.md:27,85,88`, US-008.AC-2/EC-3, the docs row (`:399`), ADR-001 `:88` and E2E-001 steps 6–7 (`Cli.NO_PENDING_ANALYSIS` exists, `messages.py:329`). Reopened for one stale line: Known Risks `_spec.md:493` still says "`speech_check = false` and `trec transcribe <id>` redo it". That is the old two-step recovery, with no `trec analyze <id>` and no switching back on. Point it to Business Rules › Redoing a wrong verdict.

### Resolution

The recovery is a contract: set the check off, run `trec transcribe <id>` and `trec analyze <id>`, then set it back on. It is in Business Rules, User Experience, the `_dx.md` WARNING line and note, US-008.AC-2 (analysis, minutes and curator rebuilt) and new EC-3, the troubleshooting docs row and the ADR risks. No per-run override is added (no new public surface). E2E-001 gains steps 6–7: `trec analyze` without an id does nothing, and `trec analyze <id>` rebuilds the analysis.

Round 2 leftover fixed (2026-10-23): Known Risks now gives the three-step recovery.
