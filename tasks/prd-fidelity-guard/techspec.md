# Tech spec: Fidelity guard

> **Status:** draft for approval · **Date:** 2026-10-11 · **Requirements:** [prd.md](./prd.md) · **Evidence:** [../prd-llm-wiki/evaluation.md](../prd-llm-wiki/evaluation.md) §14
> **Prototype:** the verifier, the code checks, the marking and the provenance rule exist as evaluation code in `scripts/fidelity_eval.py` (`VERIFY_SYSTEM`, `l2_flags`, `l1_flag`, `L2_KEPT`, `mark_analysis`, `CITE_RULE`); this spec moves them into the product's layers. The story verifier there (`STORY_VERIFY_SYSTEM`) was tested and is not carried over.

## 1. Summary

Two checks and one rule, each ending in visible marks instead of deletions: a **transcript health check** after whisper (anti-loop decoding by default, one retry if still degraded), a **claim verifier** after the analysis, and **provenance** in the stories (the writer cites a timestamp or marks "(sugestão)" for every criterion). Downstream steps read the marks: the minutes show them, the planner and the story writer treat unconfirmed items as "a confirmar", and published tasks carry them.

```
audio → Transcriber ─▶ transcript_health() ─(degraded)─▶ Transcriber(anti-loop) ─▶ health again ─▶ transcript (+health)
      → Analyzer ─▶ ClaimVerifier + code checks ─▶ analysis.json with verified/unverified marks ─▶ minutes (⚠️)
      → Planner (unconfirmed = "a confirmar") → StoryWriter (confirmed sources; every criterion cites [hh:mm:ss] or "(sugestão)") ─▶ drafts ─▶ board
```

## 2. Domain

- `TranscriptHealth(loop_share: float, covered_minutes: int, total_minutes: int, degraded: bool, uncovered: list[tuple[int, int]])` and the pure function `transcript_health(transcript, max_loop_share, repeat_threshold=5)`; `Transcript.health: TranscriptHealth | None` (old transcripts: `None`).
  - As built (task 1.0): `uncovered` is a tuple of half-open minute ranges, `retried` records the second pass, and a loop is 5+ copies of a text **within 30 consecutive segments** (`domain/health.py`), because counting repeats over the whole meeting gave a healthy real meeting 9.8% from natural fillers. `transcript_health` also takes the meeting's length (`duration_seconds`), non-speech markers are not text, and `is_healthier_than` ranks minutes with text first.
- `Verification(status: VerificationStatus, reason: str)` with `VerificationStatus = confirmed | unconfirmed`; optional `verification` on `Decision`, `Action`, `Deadline`; `Analysis.participant_checks: dict[str, Verification]`. `None` means "not verified" (analyses made before this feature behave as today).
  - As built (task 2.0): `Verification(status, reason="")` is a frozen value; `participant_checks` is keyed by the name as written in `participants`. The codec writes `verification` and `participant_checks` only when present, so unverified analyses, plans and `open_actions.json`, and the JSON sent to the planner and the story writer, are unchanged until 3.0 verifies something; how the prompts use the marks is task 4.0. A verification that does not parse (unknown status, missing key, a reason that is not text, `participant_checks` that is not an object) makes the file a `RepositoryError`, as now for every JSON file the repository decodes (`meta.json`, the active-recording pointer, transcripts, analyses, plans, open actions, drafts).
- `Criterion(text, source: str | None)` replaces plain strings in `UserStory.acceptance_criteria` (old drafts: `source=None`, shown as today); `source` is `hh:mm:ss` or `sugestao`.
- Pure code checks moved from the prototype: `sensitive_data(text)`, `participant_confirmed(name, transcript)`.

## 3. Application

- Port: `ClaimVerifier.verify(meeting, analysis, transcript) -> dict[ClaimRef, Verification]`.
- `TranscribeMeeting`: computes health; when degraded and `[transcription] retry_on_loop`, transcribes again through the anti-loop transcriber and keeps the healthier result; saves health with the transcript; a still-degraded transcript notifies `Notify.TRANSCRIPT_DEGRADED`.
- `AnalyzeMeeting` → new `VerifyAnalysis` step in the pipeline (after analysis, before minutes): applies the verifier and the code checks; failures leave claims unverified and are logged, never `error.txt`.
- `BuildDailyPlan` passes verification to the planner; the plan prompt says unconfirmed actions are listed as "a confirmar".
- `DraftUserStories`: candidate actions with `unconfirmed` status go to the writer marked "a confirmar" (owner unknown when the owner was the doubt); the writer's output schema gains `source` per criterion; `to_drafts` keeps a cited timestamp only if it exists in a source meeting's transcript, else turns it into `sugestao`.

## 4. Adapters

- `transcriber_whispercpp`: optional `max_context` (`-mc`) and VAD flags; a second instance with the anti-loop settings is built in the container.
- `verifier_claude.ClaudeClaimVerifier` over a second `StructuredTransport` built with `[verification] model/effort` (Sonnet, medium); long transcripts are cut into ±60 s windows around each claim's `at`; claims without a timestamp use the whole transcript up to a size cap.
- `prompts/stories_system.md`: the provenance rule (prototype: `CITE_RULE` in `scripts/fidelity_eval.py`).
- `minutes_markdown`: ⚠️ marks with the reason; banner for degraded transcripts. `stories_markdown`: each criterion with its timestamp or "(sugestão)".
- `publisher_backlogmd`: marks carried into the task description.
- `codec`: new optional fields, defaults for old files.

## 5. Configuration

```toml
[transcription]
max_context = 0           # whisper -mc for every transcription (0 = no text context: loops cannot carry over; neutral on Portuguese)
max_loop_share = 0.10     # above this the transcript is degraded (segments repeated 5+ times)
retry_on_loop = true      # if still degraded, retranscribe once with VAD
retry_vad = true          # Silero VAD on the retry (skips silence, where whisper hallucinates)

[verification]
enabled = true
model = "sonnet"          # Claude Code alias or API model for both verifiers
effort = "medium"
```

Evaluation §14.7: `-mc 0` removed the loop on the real meeting (70% → 4% repeated segments, 28 → 86 minutes with text) and left Portuguese accuracy unchanged (2.9% → 2.8%), so it is the first pass; VAD (30% slower) is the retry.

## 6. Testing

- Unit: `transcript_health` on loops, silence and healthy transcripts; the code checks (moved tests from `tests/unit/test_eval_harness.py`); verification merge into the domain; renderers' marks; old JSON loading.
- Use cases on fakes: retry chosen only when healthier; verifier failure leaves claims unverified; unconfirmed actions never become story sources; marks reach the drafts and the publisher.
- Evaluation (opt-in, real model): `scripts/fidelity_eval.py` on the stories corpus — `defend`/`report`/`gate` for G2, `stories` (three runs of the shipped pipeline) for G3; G1 on the real 2026-10-08 audio (read-only).

## 7. Risks

- The verifier shares the subscription's five-hour window with the daemon: one extra Sonnet call per meeting and per drafted day; measure in `llm_usage.jsonl` during G4.
- False marks erode trust: the gate keeps unconfirmed-but-correct ≤ 10%; the user's review in G4 is the final check.
- A degraded transcript that cannot be repaired still produces an analysis: the banner and the notification are the safeguard.
