---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 193
severity: high
author: claude-code
provider_ref:
---

# Issue 002: Lines typed in the box are silently dropped when the box is rewritten

## Review Comment

Since `_dx.md:106-107` and US-003 EC-1 (`_user_stories.md:89`) the user may type lines inside the box, and the promise is "it is not lost: the next pass moves it into the right section and the box is rewritten". The pipeline cannot keep that promise as written:

- `box_lines` reach the curator from the snapshot F that is read before the LLM call (`CuratorInput.box_lines`, `_spec.md:207`). Moving them out of the box is left entirely to the model ("Move `<box_lines>` into the right section", Principle 1, `_spec.md:360`).
- After the call, code runs `render_box(W, focus, ...)` on the re-read document W (`_spec.md:134`). This rewrites the box and *returns* the lines the user had typed in the old box (`_spec.md:193-194`). Nothing says what `CurateMeetings` does with that return value. It is not written anywhere, not put in the pass record, and not checked.
- The box is outside the body. So it is outside the open-line invariant (`_spec.md:54`, "box and link block excluded") and outside Safety Invariant 4 ("text no op targets is preserved byte for byte" applies to body ops only).

Two concrete loss paths follow:
1. The user types `- [ ] Ligar para o João` in the box *during* a pass. That pass can last minutes: the lock is held through a call with a 900 s timeout, `_spec.md:375,451`. The line is not in the curator's `box_lines`, because it was typed after the snapshot. `render_box` on F' drops it. Nothing fails, nothing is notified, and the line exists only in `versions/<ts>_before.md`.
2. The model leaves out a box line before the pass (a prompt-level miss). `render_box` drops it the same way.

Either way, a user-written open item disappears from the document without archiving or notice. Goal 2 and US-007 forbid exactly that.

Suggested fix: make `CurateMeetings` responsible in code for the lines `render_box` returns. Any returned line that does not appear in the resulting body (after the ops) is re-inserted right below the box. Use a fixed `messages.ActivityDoc` heading, or put it at the top of `## Minhas ações` with a 💬 `movido da caixa` sub-line. The next pass then handles it as a normal user line. State this in Safety Invariants, for example "11. A line typed in the box is never discarded", and add tests: a box line typed between snapshot and apply survives; a box line the curator did not move survives.

## Triage

- Decision: `VALID`
- Notes: Valid. `render_box` returns the user's box lines and nothing consumed them; the box sits outside the body, so neither the open-line rule nor Safety Invariant 4 covered it. A line typed after the snapshot, or one the model skipped, was dropped silently.
- Verified: rule "Typed in the box", `rescue_box_lines` (Core Interfaces), Safety Invariant 11, `PassRecord.box_rescued`, UT-027/047/048, IT-016. A line typed during a pass now appears twice in the next `<user_edits>`; tracked separately as reviews-002/issue_005.

### Resolution

Fixed. New business rule "Typed in the box" (Part I) and Safety Invariant 11. New pure `rescue_box_lines(document, lines)` (Core Interfaces): any line `render_box` returned that is not a line of the resulting body is put, unchanged, at the top of `## Minhas ações` (heading created after the box if missing); `PassRecord.box_rescued` counts them; the prompt tells the model to copy box lines verbatim and that leftovers are rescued by the app. Fixed differently from the suggestion in one detail: no code-written 💬 sub-line is added to the rescued line, because the line must stay a plain user line (a sub-line the code wrote would be read next pass as user text); the rescued lines are excluded from `base.md` so the next diff shows them as the user's (see issue 006). Companions: US-003 EC-1, US-012 AC-4, `_dx.md` file description. Tests: UT-027, UT-047 (typed after snapshot), UT-048 (moved line not duplicated, unmoved rescued), IT-016.

