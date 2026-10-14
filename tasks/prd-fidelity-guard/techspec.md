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
  - As built (task 2.0): `Verification(status, reason="")` is a frozen value; `participant_checks` is keyed by the name as written in `participants`. The codec writes `verification` and `participant_checks` only when present, so unverified analyses, plans and `open_actions.json`, and the JSON sent to the planner and the story writer, are unchanged until 3.0 verifies something; how the prompts use the marks is task 4.0. A verification that does not parse (unknown status, missing key, a reason that is not text, a `verification` or `participant_checks` that is neither absent, `null`, `{}` nor an object) makes the file a `RepositoryError`, as now for every JSON file the repository decodes (`meta.json`, the active-recording pointer, transcripts, analyses, plans, open actions, drafts).
- `Criterion(text, source: str | None)` replaces plain strings in `UserStory.acceptance_criteria` (old drafts: `source=None`, shown as today); `source` is `hh:mm:ss` or `sugestao`.
  - As built (task 5.0):
    - **Criterion:** `Criterion(text, source)` with `SUGGESTION = "sugestao"`.
    - **The writer:** its schema has `{text, source}` per criterion. Code turns any source that is not `HH:MM:SS` (brackets allowed) into a suggestion. `prompts/stories_system.md` carries the prototype's citation rule (`CITE_RULE`, measured in §14.5), adapted to the structured field. Detail lines keep the textual rule ("[hh:mm:ss]" or "(sugestão)" at the end), as in the prototype, with no check in code. The prompt also forbids citing an unconfirmed claim and allows raising it as an open question.
    - **The check:** a cited timestamp must be a line of the story's source meetings' transcripts (`domain.said_at` / `checked_criteria`), else it becomes a suggestion. A meeting whose transcript cannot be read confirms nothing. This runs in `DraftUserStories`, which has the repository, not in `to_drafts` as first written.
    - **Display:** the drafts show `` `[hh:mm:ss]` `` or "_(sugestão)_". Each board `--ac` ends with " [hh:mm:ss]" or " (sugestão)", the form the evaluation judged.
    - **Old drafts:** criteria saved as plain strings load as `Criterion(text, None)`, are shown as before and are written back as strings.
    - **Evaluation:** `scripts/fidelity_eval.py story_claims` reads the new format with the source appended, so G3 measures what ships.
- Pure code checks moved from the prototype: `sensitive_data(text)`, `participant_confirmed(name, transcript)`.

## 3. Application

- Port: `ClaimVerifier.verify(meeting, analysis, transcript) -> dict[ClaimRef, Verification]`.
  - As built (task 3.0):
    - **Claims:** `ClaimRef(kind, key)` names a claim: an action by its id, a decision or deadline by its position, a participant by name. `domain/verification.py` lists the claims (`claim_refs`), combines verdicts (`combine`: unconfirmed wins, reasons joined) and writes them into a copy of the analysis (`with_verifications`).
    - **Code checks:** `sensitive_data(text, patterns)` and `participant_heard(name, transcript, user_name, particles, address)` take their Portuguese patterns from `constants.Verify` and can only lower a verdict.
    - **The step:** `VerifyAnalysis` runs inside `AnalyzeMeeting` (an optional `verify`), between the analyzer and saving `analysis.json` and the minutes, rather than as a pipeline state of its own: a meeting is still "analyzed" when `analysis.json` exists. A verifier failure is logged and leaves its claims unverified; the code checks still apply.
- `TranscribeMeeting`: computes health; when degraded and `[transcription] retry_on_loop`, transcribes again through the anti-loop transcriber and keeps the healthier result; saves health with the transcript; a still-degraded transcript notifies `Notify.TRANSCRIPT_DEGRADED`.
- `AnalyzeMeeting` → new `VerifyAnalysis` step in the pipeline (after analysis, before minutes): applies the verifier and the code checks; failures leave claims unverified and are logged, never `error.txt`.
- `BuildDailyPlan` passes verification to the planner; the plan prompt says unconfirmed actions are listed as "a confirmar".
- ~~`DraftUserStories`: candidate actions with `unconfirmed` status go to the writer marked "a confirmar" (owner unknown when the owner was the doubt); the writer's output schema gains `source` per criterion; `to_drafts` keeps a cited timestamp only if it exists in a source meeting's transcript, else turns it into `sugestao`.~~ (superseded by the task 4.0 note below)
  - As built (task 4.0):
    - **Plan:** the planner already receives the marks, because the codec writes `verification` on the analyses and actions it sends. `prompts/plan_system.md` says what they mean: keep unconfirmed items, write "(a confirmar)" with the reason, never present them as facts or priorities, and put the user's unconfirmed actions under "Conflitos e alertas".
    - **Stories (FR5):** `DraftUserStories` never gives the writer an unconfirmed feature or bug as a source. It lists it as left out with "não confirmada na transcrição: <reason>". A technical or operation action still becomes a task card that carries the action's verification (`UserStory.verification`, PRD decision 10). An action never verified (None) is handled as before.
    - **Plan-only actions:** an unconfirmed management or communication action keeps its "fica só no plano" reason in the drafts, with "(⚠️ não confirmada na transcrição: <reason>)" added (FR4).
    - **Reasons:** shown everywhere through `domain.unconfirmed_reason`, on one line (the verifier also flattens them), with Markdown's `_` and `*` escaped in the minutes, so a reason cannot break a table or a list.
    - **For task 5.0:** the story writer still sees unconfirmed decisions and other people's actions in its meeting context, and `prompts/stories_system.md` says nothing about the marks.
    - **Drafts banner:** `degraded_sources()` finds the source meetings whose transcript is degraded, both when drafting and when publishing re-renders the document, and the renderer shows a banner for each (PRD decision 9).

## 4. Adapters

- `transcriber_whispercpp`: optional `max_context` (`-mc`) and VAD flags; a second instance with the anti-loop settings is built in the container.
- `verifier_claude.ClaudeClaimVerifier` over a second `StructuredTransport` built with `[verification] model/effort` (Sonnet, medium); long transcripts are cut into ±60 s windows around each claim's `at`; claims without a timestamp use the whole transcript up to a size cap.
  - As built (task 3.0):
    - **The call:** one call per meeting, prompt `prompts/verify_system.md`. The prompt is the prototype's `VERIFY_SYSTEM` word for word except two lines: the user's name comes in the message, and the reason is written in Brazilian Portuguese. A test pins this. The message has the prototype's shape: claims with local ids (`c1`, `c2`, ...), `| owner: | date: | cited at`, and the owner named, not "the user". The claims are not shuffled per run as the prototype did. Task 8.0 must measure this verifier, not the prototype.
    - **Transcript:** the whole transcript up to `Verify.MAX_TRANSCRIPT_CHARS` (200,000 characters, about 4 h). Beyond that, its start up to the cap plus the lines within `Verify.WINDOW_SECONDS` (60 s) of each claim's timestamp, with `[...]` marking gaps.
    - **Verdicts:** the model judges support, owner, date, tentative and sensitive per claim, and the mapping to one status is in code (the prototype's `l1_flag`). A claim the answer leaves out is unconfirmed; verdicts for unknown ids are ignored. Reasons are written in Brazilian Portuguese, for the minutes.
    - **Wiring:** not done until task 7.0, so the daemon does not verify yet and no verdict reaches the planner or story-writer prompts before task 4.0 explains them.
    - **For 7.0:** the verifier and `VerifyAnalysis` both need `[user] name`. Without it the model sees "the user" and cannot match "Felipe, você manda...".
    - **For 4.0 and 7.0:** a verifier outage leaves claims unverified, which looks the same as "never verified" apart from a log warning. Consider recording that verification was attempted.
    - **Lock:** verification runs under the meeting lock before the analysis is saved, so a crash during the Sonnet call loses the analysis too. Re-verifying an old analysis needs a re-analysis until a separate command exists.
  - **The participant check** is the prototype's rule as measured: someone named at least twice passes even when only mentioned, and a common word used as a name ("Clara") can pass. Two differences from the first version, both fixed after the review:
    - segments are joined by spaces, so a greeting split across segments counts;
    - the owner counts by first name or full name.
- `prompts/stories_system.md`: the provenance rule (prototype: `CITE_RULE` in `scripts/fidelity_eval.py`).
- `minutes_markdown`: ⚠️ marks with the reason; banner for degraded transcripts. `stories_markdown`: each criterion with its timestamp or "(sugestão)".
- `publisher_backlogmd`: marks carried into the task description.
  - As built (task 4.0): `minutes_markdown` marks each unconfirmed decision, action, deadline and participant with " ⚠️ _a confirmar: <reason>_" (a pipe in a reason is replaced inside the action table) and adds a legend under the title; minutes without unconfirmed claims are unchanged. A marked task card starts its board description with "⚠️ **A confirmar na transcrição:** <reason>" and shows the same line in the drafts document.
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
