---
provider: manual
pr:
round: 1
round_created_at: 2026-10-21T22:15:25Z
status: resolved
file: docs/tasks/language-detection/_spec.md
line: 282
severity: low
author: claude-code
provider_ref:
---

# Issue 006: Damaged language_detection: codec raises no RepositoryError; AttributeError hole

## Review Comment

`_spec.md:282` says a damaged object "raises the codec's usual `RepositoryError`, like a damaged `health`". The codec raises no `RepositoryError` at all. `health_from_dict` raises `KeyError`/`TypeError`/`ValueError` (`src/teams_recorder/adapters/outbound/codec.py:98-108`). `FsMeetingRepository._decode` turns exactly those three into `RepositoryError(Err.BAD_JSON…)` (`repository_fs.py:60-73`), and its docstring says `AttributeError` is deliberately not caught: "the codec indexes or checks a value before calling a method on it". That is why `transcript_from_dict` checks `isinstance(speakers, dict)` before calling `.get` (`codec.py:139-141`).

A decoder written in the style the spec implies, `d.get("language_detection").get(...)` or `s.get("at")` on a sample that is a string, would raise `AttributeError` on a damaged file and crash `trec status` and `trec analyze` instead of reporting the file. UT-043 (`_tests.md:117`) can see `RepositoryError` only through `FsMeetingRepository.load_transcript`, not through `codec.transcript_from_dict` directly.

Suggested fix: state that the decoder must check the object and each sample with `isinstance(..., dict)` (raising `TypeError(Err.BAD_LANGUAGE_DETECTION…)`), mirroring `speakers`. Rewrite UT-043 to load through `FsMeetingRepository`, with three damaged shapes: a non-dict object, an unknown `reason`, and a non-dict sample. Each asserts `RepositoryError` naming the file.

## Triage

- Decision: `VALID`
- Notes: Valid. The codec raises `KeyError`/`TypeError`/`ValueError`; `FsMeetingRepository._decode` makes them `RepositoryError` and lets `AttributeError` through.
- Verified: `repository_fs.py:58-73`, `codec.py:136-150`.

### Resolution

Data Models: the decoder checks the object and each sample with `isinstance(…, dict)`, raising `TypeError(Err.BAD_LANGUAGE_DETECTION…)` (text given) like `speakers`; an unknown reason raises `ValueError`; the repository turns them into `RepositoryError(Err.BAD_JSON…)`. UT-043 rewritten through `FsMeetingRepository.load_transcript` with three damaged shapes and no `AttributeError`.
