---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 204
severity: low
author: claude-code
provider_ref:
---

# Issue 015: Transcript excerpts have no layer that can build them

## Review Comment

`CuratorInput.meetings` carries `MeetingContext` items described as "meeting, analysis, health, excerpts" (`_spec.md:204`). The windowing helper `transcript_window` is to be adapted from `verifier_claude.transcript_for`, an outbound adapter (`_spec.md:384`, `:489`). Architectural Boundaries let `curator_claude.py` import `verifier_claude.transcript_window` (`_spec.md:151`). These three statements leave the excerpts with no workable home:

- If `CurateMeetings` (application) builds the excerpts, it cannot import the adapter helper. The import rule is `domain ← application ← adapters` (AGENTS.md).
- If `ClaudeCurator` builds them, it needs the `Transcript`, but `MeetingContext` does not carry one, and the port gives the adapter no way to load it.

Separately, `curator_claude → verifier_claude` is a new cross-adapter import outside the LLM-stack exception that AGENTS.md lists (`llm_schema` and `llm_transport` only). `MeetingContext`, `TaggedBlock`, `RemovedItem`, `IgnoredRef`, `PassKind`, `PassResult`, `UndoPreview`, `UndoResult`, `TagDraftResult`, `CuratorBusy` and `NothingToUndo` are used but never defined.

Suggested fix: move the pure windowing (segment lines within ±window of a list of times, merged, with gap markers) to the domain, for example `domain/transcript.excerpt_window(transcript, times, window)` next to `timestamped_line`. Let `CurateMeetings` fill `MeetingContext.excerpts`. `transcript_for` then reuses it. Define the missing types in Core Interfaces, even as one-line field lists.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: `transcript_for` is in an outbound adapter, `domain/models.py` holds `timestamped_line`, `MeetingContext` had no transcript, and the curator→verifier import is outside the LLM-stack exception; several types were used but never defined.
- Verified: `domain/excerpts.excerpt_window` shared by `verifier_claude.transcript_for` and `CurateMeetings`; `MeetingContext.excerpts` built in the application layer; no adapter-to-adapter import; the missing types are defined in Core Interfaces; UT-028/053.

### Resolution

Fixed as suggested (module name differs: no `domain/transcript.py` exists, so the pure function is `domain/excerpts.excerpt_window(transcript, times, window, gap, head_chars=0)`). `CurateMeetings` loads transcripts through the repository and fills `MeetingContext.excerpts`; `verifier_claude.transcript_for` reuses the same function; `curator_claude.py` imports only the LLM-stack modules. Core Interfaces now define `MeetingContext`, `TaggedBlock`, `RemovedItem`, `IgnoredRef`, `PassKind`, `PendingTag`, `PassResult`, `NotCurated`, `UndoPreview`/`UndoResult` (field lists in comments), `TagDraftResult`, `ActivitiesStatus`, `CuratorBusy`, `NothingToUndo`, `UndoStale`. Tests: UT-028, UT-053 (rewritten: same output after the move).

