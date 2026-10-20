---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 160
severity: medium
author: claude-code
provider_ref:
---

# Issue 004: domain/activities.py needs labels it is not allowed to import

## Review Comment

Architectural Boundaries say `domain/activities.py` "imports only the standard library and `domain` types" (`_spec.md:160`). The current domain follows that: no `src/teams_recorder/domain/*.py` imports `messages` or `constants`. The same section (`_spec.md:165`) puts the "Portuguese document labels in `messages.ActivityDoc`" and the "regexes … in `constants.py` (`Parse`)". `tests/unit/test_no_hardcoded_strings.py` fails on any prose literal (a string with a space) outside `constants.py`, `messages.py` and `domain/status.py` (`ALLOWED_MODULES`).

Several pure functions specified in `domain/activities.py` must write or recognise exactly those strings:

- `render_box` writes `<!-- curador:início (reescrito a cada passada; escreva fora desta caixa) -->`, `**Atualizado …** · após …` and `**Foco**`.
- `render_links` writes `<!-- links:início (gerado automaticamente) -->`.
- `rescue_box_lines` creates `## Minhas ações` when it is missing.
- `calendar_strip` writes Portuguese weekdays and `(hoje)`.
- `body_span` needs the markers.
- `open_count` and `ticked_count` need the checkbox regexes.

None of their signatures takes these values: `render_box(document, focus, meetings, now)`, `calendar_strip(today, days)`, `rescue_box_lines(document, lines)`. As specified, an implementer has three options, each of which breaks a stated rule:
- import `messages`/`constants` into the domain, which breaks the boundary;
- hardcode the strings, which turns the gate red;
- add `domain/activities.py` to `ALLOWED_MODULES`, which breaks AGENTS.md "Strings … never inline".

Suggested fix: pick one rule and write it down. For example, a frozen `DocFormat` value object (markers, headings, weekday names, regex patterns) built in the application layer from `messages.ActivityDoc` and `constants.Parse`, and passed to the domain functions (add it to their signatures). Or declare explicitly that `domain/activities.py` may import `messages.ActivityDoc` and `constants.Parse`, and add that exception to AGENTS.md's import-direction text and to the AGENTS.md row of Impact Analysis.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: no `domain/*.py` imports `messages`/`constants`, `test_no_hardcoded_strings` rejects prose literals outside the allowed modules, and none of `render_box`, `render_links`, `rescue_box_lines`, `calendar_strip`, `body_span`, `open_count` took the labels or patterns they need.
- Verified (round 3): `DocFormat` is the first argument of every domain function that writes or recognises document text. `doc_format()` lives in the application layer, and the Architectural Boundaries bar `messages`/`constants` from the domain. UT-116 adds an AST import check and a round-trip test. One field is still missing (the folder of the link target); that is tracked in reviews-003/issue_001.

### Resolution

Fixed with the first option: a frozen `DocFormat` (markers, headings, header labels, weekday names, `(hoje)`, checkbox regexes) built by `doc_format()` in `application/use_cases/activities.py` from `messages.ActivityDoc` and `constants.Parse` and passed as the first argument to the domain functions. No domain import exception, no `ALLOWED_MODULES` entry, no AGENTS.md change. Updated Core Interfaces (all signatures), Architectural Boundaries, Components; new UT-116 (AST import check and round-trip).

