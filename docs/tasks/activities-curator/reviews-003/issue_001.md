---
provider: manual
pr:
round: 3
round_created_at: 2026-10-20T01:04:08Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 207
severity: low
author: claude-code
provider_ref:
---

# Issue 001: DocFormat omits the link target folder render_links must write

## Review Comment

The round-2 fix for reviews-002/issue_004 makes `DocFormat` carry "every marker, heading, weekday name, `(hoje)`, header label and checkbox regex it writes or recognises" (`_spec.md:162`). UT-116 asserts the round-trip. `render_links(fmt, document, meeting_exists)` (`_spec.md:246`) is a domain function, and it writes link definitions of the form `[<id>]: ../recordings/<id>/minutes.md` (`_dx.md:98-103`, UT-012). `minutes.md` is `domain/status.MINUTES`, which the domain may import. The folder name is `constants.Files.RECORDINGS_DIR = "recordings"` (`src/teams_recorder/constants.py:90`), and the domain may not import `constants` (Architectural Boundaries; UT-116's AST check). `DocFormat` has no field for it.

An implementer must therefore hardcode `"recordings"` (or `"../recordings/"`) in `domain/activities.py`. `test_no_hardcoded_strings` will not catch that literal, because `_is_prose` requires a space (`tests/unit/test_no_hardcoded_strings.py:34-35`). The duplicate breaks AGENTS.md ("file/folder names in `constants.py` … Add to these modules instead of writing a new literal") without any failing test. If `RECORDINGS_DIR` ever changes, every link in `atividades.md` breaks.

A smaller problem in the same type: `box_end: str` is described as `"<!-- curador:fim" + optional " <stamp>" + " -->"` (`_spec.md:209`). One string cannot hold a prefix and a suffix around an optional stamp, which `box_stamp`, `render_box` and `body_span` all need (UT-117).

Suggested fix: add `link_target: str` to `DocFormat`, a template such as `"../{dir}/{id}/{minutes}"`, filled in `doc_format()` from `Files.RECORDINGS_DIR` and `status.MINUTES`. Model the closing marker as two fields (`box_end_prefix`, `box_end_suffix`), or state that `box_end` is the prefix. Extend UT-012/UT-116 so the link block is built from `DocFormat`.

## Triage

- Decision: `VALID`
- Notes: Confirmed by reading `_spec.md` Core Interfaces: `DocFormat` had no field for the link target folder and `box_end` was one string around an optional stamp. Root cause: the round-2 move of every written/recognised text into `DocFormat` stopped short of the link definitions `render_links` writes and of the two-part closing marker. Fix in `_spec.md`: `DocFormat` gains `link_target` (`"../recordings/{id}/minutes.md"`, filled by `doc_format()` from `Files.RECORDINGS_DIR` and `domain.status.MINUTES`) and `box_end` becomes `box_end_prefix` + `box_end_suffix` (marker = prefix + optional stamp + suffix); Architectural Boundaries and the `doc_format()` component line name the new sources and say the folder name is never a literal in the domain. `_tests.md`: UT-012 builds definitions from `fmt.link_target`; UT-116 round-trips the stamped and unstamped closing marker through prefix/suffix and adds an AST check that the module holds no literal containing the recordings folder name. Spec-only change; no source touched.
- Verified: (round 4) `_spec.md:207-211` now has `box_end_prefix`/`box_end_suffix` (marker = prefix + optional " " + stamp + suffix, unstamped form accepted by readers) and `link_target` (`"../recordings/{id}/minutes.md"`); Architectural Boundaries (`_spec.md:161`) and the `doc_format()` component line (`_spec.md:151`) name `Files.RECORDINGS_DIR` and `status.MINUTES` as sources; no `box_end` singular remains anywhere. `_tests.md` UT-012 builds definitions from `fmt.link_target` and varies it; UT-116 round-trips the stamped and unstamped marker and adds the AST check for the folder name. `_dx.md:62` example matches the format. Archive links (`../../recordings/`, `_spec.md:536`, UT-040) are built by the store adapter, which may import `constants`, so they do not need a `DocFormat` field.
