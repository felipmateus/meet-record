---
provider: manual
pr:
round: 1
round_created_at: 2026-10-17T00:20:43Z
status: resolved
file: docs/tasks/speaker-attribution/_spec.md
line: 248
severity: high
author: claude-code
provider_ref:
---

# Issue 001: Roster and per-meeting user label never reach the analyzer or verifier

## Review Comment

The spec says "the roster is read from the events when the analysis message is built" (`_spec.md:248`), that `llm_schema.build_user_message` adds the roster header (`_spec.md:119`), and UT-051 tests `build_user_message` "when a roster is given". No component on that path can read the events:

- `AnalyzeMeeting.execute` calls `self.analyzer.analyze(transcript, meeting)` (`application/use_cases/processing.py:127`). The port is `MeetingAnalyzer.analyze(transcript, meeting)` (`application/ports.py:83-84`), and `ClaudeAnalyzer.analyze` calls `build_user_message(transcript, meeting, self.user_name)` (`adapters/outbound/llm_claude.py:43-51`, `llm_schema.py:116`). None of them has repository access.
- `VerifyAnalysis.execute(meeting, analysis, transcript)` (`application/use_cases/verification.py:47`) has the same problem, and UT-054 needs the roster there.
- Core Interfaces add no roster field to `Transcript` or `Meeting` and no port parameter. Impact Analysis leaves out `llm_claude.py`, `AnalyzeMeeting`, the `MeetingAnalyzer` port and `FakeAnalyzer` (`tests/fakes/__init__.py`, `analyze(transcript, meeting)`).

The user's label has the same gap. The header's owner line comes only from the static `[user] name` (`container.py:194`, `user_name=settings.user_name`). When the label falls back to the own tile's name or "Você" (`_spec.md:260`, US-002.AC-3/4), the model reads e.g. `Felipe Mateus de Carvalho: pode deixar comigo` and nothing tells it that this label is the recording owner. The prompt forbids writing the name instead of `usuário` (`prompts/analyze_system.md:47`), so US-004.AC-1 ("the recording owner literal when the label is the user's") cannot hold on the fallback paths.

Suggested fix: pick one carrier and write it into Core Interfaces. Options:
- `Transcript.roster: tuple[str, ...]` and `Transcript.user_label: str | None`, set by `TranscribeMeeting` and persisted in `transcript.json`. This also gives issue 008 its marker.
- An explicit `SpeakerContext` argument on `MeetingAnalyzer.analyze` and `VerifyAnalysis.execute`.

Also state that the header names the user label when labels exist. Add the touched files to Impact Analysis, and add a unit test for the `usuário` literal with a fallback label.

## Triage

- Decision: `VALID`
- Notes: Fixed in the spec: `Transcript` carries `roster`, `user_label` and a `LabelSummary`, persisted under `transcript.json › speakers`; `build_user_message` and the verifier's `user_message` read them (no port change); the analyzer header names the owner's label so the `usuário` literal still applies (UT-051, UT-051b, UT-052). (applied by the spec author on 2026-10-16; verification is the reviewer's in the next round)
- Verified: Spec Core Interfaces now give `Transcript.roster`, `user_label` and `labels` (`_spec.md` Core Interfaces, Data Models `transcript.json › speakers`); implemented in `domain/models.py`, persisted by `codec.transcript_to_dict/_from_dict`, read by `llm_schema.build_user_message` (ROSTER and SPEAKER_LABELS header lines) and `ClaudeClaimVerifier.user_message`; the owner-label sentence is in `prompts/analyze_system.md` (data contract). Pinned by UT-051/UT-051b tests in `tests/unit/test_llm_claude.py`; full suite green on 2026-10-17 (round 2). (review round 2, reviewer A)
