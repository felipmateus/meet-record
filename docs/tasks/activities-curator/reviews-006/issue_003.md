---
provider: manual
pr:
round: 6
round_created_at: 2026-10-20T12:34:07Z
status: resolved
file: src/teams_recorder/domain/activities.py
line: 449
severity: medium
author: claude-code
provider_ref:
---

# Issue 003: Box lines shaped like focus lines are silently discarded

## Review Comment

`render_box` decides which box lines the user typed with `_is_generated`. Any line matching `> <n>. `, `> **Atualizado…` or `> **Foco**`, and any blank or bare `>` line, counts as app-written and is dropped. The box is a numbered focus list, so the natural way for the user to add an item of their own is to type the next number, e.g. `> 2. Ligar para o João amanhã`. That line never reaches `box_lines`, is not rescued, and is gone after the next pass. It is not in the archive either. This breaks Safety Invariant 11 ("A line typed in the box is never discarded") and US-003.EC-1.

Repro (real `doc_format()` and `skeleton()`):

```
doc, _ = render_box(fmt, skeleton(fmt), ["**Enviar** cronograma"], ["Daily"], ..., "20261020-090000")
# user inserts "> 2. Ligar para o João amanhã" under "> 1. …"
new, typed = render_box(fmt, user_doc, ["**Revisar** PR"], ["Daily"], ..., "20261020-110000")
typed == []            # not surfaced
"João" in new == False # gone
```

UT-011 only checks a `- [ ] Ligar X` line, so nothing catches this.

Suggested fix: recognise generated lines by comparing them with what the previous `render_box` wrote. The stored focus (`box_focus` of the base, or the last record) and the header are known. Any other line, numbered or not, goes to `typed`. At minimum, a numbered line whose text is not one of the base's focus lines must be treated as typed. Add a UT-011 case with a numbered user line.

## Triage

- Decision: `VALID`
- Notes: Root cause: `_is_generated` treated every `> <n>. ` line as app-written. Fix: `render_box(..., base=None)` takes the document as the last pass left it; its focus lines (`box_focus(base)`) are the numbered lines the app wrote, each matching one box line once, and any other numbered line is returned as typed (rescued into `## Minhas ações`, shown to the curator in `box_lines`). Without a base (first pass) the old rule stays (no numbered line can exist then). `CurateMeetings` passes `base` at both `render_box` calls. Spec signature and UT-011 updated. Regression tests: `tests/unit/test_activities_render.py` (`test_a_numbered_line_the_user_typed_in_the_box_is_returned_not_dropped`, `test_only_the_focus_lines_the_last_pass_wrote_are_generated_and_each_matches_once`, `test_without_a_base_...`) and `tests/unit/test_curate_meetings.py::test_a_numbered_line_typed_in_the_box_reaches_the_curator_and_is_rescued_not_deleted`.
- Verified (round 7): probe `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/38833900-8373-4b20-8322-07dcc789a48c/scratchpad/r7_probes.py` (real `FMT`/`SKELETON`). A numbered line the user added (`> 3. Minha linha`) is returned as typed, also in a CRLF document. A focus line the user *edited* (`> 2. Revisar PR` → `> 2. Revisar PR do Joao ate 14h`) no longer matches the base's focus, so it is returned as typed and rescued, not discarded. That is the conservative outcome Safety Invariant 11 wants. Unedited focus lines still count as generated, once each (`Counter`). `CurateMeetings._curate` passes `base` at both calls. Full suite green.
