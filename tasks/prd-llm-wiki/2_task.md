# Task 2.0: Domain, persistence and configuration

## Overview

Give the domain the wiki's vocabulary and rules (page types and layout, slug and edit validation, frontmatter, index and log rendering, lint), the meeting folder a record of each ingest (`wiki.json`) and of a failed one (`wiki_error.txt`) without touching the meeting status, and the configuration a `[wiki]` section. This is the foundation every later task builds on; nothing calls the model yet.

<skills>
### Skills compliance

- `domain-driven-design`: value objects and pure functions; the layout is a domain rule like `status.py`; no I/O.
- `python-pro`: frozen dataclasses, `StrEnum`, typing kept `mypy`-clean.
- `python-testing-patterns`: round trips, boundaries and rejection cases.
</skills>

<requirements>
- `domain/wiki.py` as in techspec §3: `PageType`, `FOLDERS`, file names, `SLUG`/`MAX_SLUG`, `PageRef.path`, `PageMeta`, `PageEdit`, `IngestPlan`, `WikiSource`, `PageWrite`, `RejectedEdit`, `WikiIngest`, `validate_edits`, `render_frontmatter` / `parse_frontmatter` (JSON scalar and array values, no YAML dependency), `render_index`, `render_log_entry`, `wikilinks`, `lint`; exported from `domain/__init__.py`. `WikiError` in `domain/errors.py`.
- `status.py`: `WIKI = "wiki.json"`, `WIKI_ERROR = "wiki_error.txt"`; `derive_status` unchanged (a test proves both files leave the status alone).
- `codec`: `wiki_ingest_to_dict` / `wiki_ingest_from_dict`. `MeetingRepository` and `FsMeetingRepository`: `save_wiki_ingest`, `load_wiki_ingest`, `mark_wiki_failed`, `clear_wiki_failed`; the same four on `InMemoryMeetingRepository`.
- `config`: `[wiki] enabled, dir, send_transcript, git` → `Settings.wiki_enabled`, `wiki_dir` (empty = `<data_dir>/wiki`; relative = against the data dir; absolute kept), `wiki_send_transcript`, `wiki_git`, `wiki_schema_path`; defaults in `constants.Wiki`; file names in `constants.Files`; `Env.REAL_WIKI`. `config.toml` gains the commented section of techspec §6 with `enabled = false`.
- Labels of the generated documents in `messages.WikiDoc` (Portuguese), everything else in English in `messages` / `constants`; the hardcoded-strings guard stays green.
</requirements>

## Subtasks

- [ ] 2.1 Write `domain/wiki.py` (types, layout, validation, frontmatter, rendering, lint) and `WikiError`; export from `domain/__init__.py`.
- [ ] 2.2 Add `WIKI` / `WIKI_ERROR` to `status.py` with the status test.
- [ ] 2.3 Extend `codec` and the repository port, `FsMeetingRepository` and the in-memory fake with the four methods.
- [ ] 2.4 Add `constants.Wiki`, `Files.WIKI_*`, `Env.REAL_WIKI`, `messages.WikiDoc` and the `Err.WIKI_*` messages the domain raises.
- [ ] 2.5 Add the `[wiki]` section to `config.py`, `config.toml` and the Settings tests.
- [ ] 2.6 Write the tests below.

## Implementation details

`validate_edits` is the only place that decides what the model may write: keep every rule there with a reason string from `messages.Err` so the CLI and the log show why an edit was rejected. `parse_frontmatter` must accept files written by `render_frontmatter` only; anything else (a hand-edited page with unquoted values) raises `WikiError` naming the key, which lint reports. `render_index` groups by type in a fixed order and sorts pages by title inside each group so the index is stable across runs (small diffs in the wiki's Git history).

## Success criteria

- A `WikiIngest` survives save → load unchanged; `wiki_error.txt` is written and cleared; neither file changes `derive_status`.
- `validate_edits` rejects: meeting type, invalid slug (`João`, `Joao_Silva`, 61 chars), empty title or body, oversize body, duplicate ref, overflow past `max_pages`; accepts the rest and strips a frontmatter block from a body.
- Frontmatter round-trips titles containing `:`, `#`, quotes and accents.
- `load_settings` resolves `dir = ""`, `dir = "kb"` and an absolute path as specified; `pytest`, `mypy` and the strings guard clean.

## Task tests

- [ ] Unit tests — `tests/unit/test_wiki_domain.py` (paths, slugs, validation, frontmatter, index, log, wikilinks, lint); `tests/unit/test_status.py` (wiki files ignored); `tests/unit/test_config.py` (`[wiki]` keys and path resolution).
- [ ] Integration tests — `tests/integration/test_repository_fs.py` (wiki.json round trip, legacy folder without it, `wiki_error.txt` mark and clear).
- [ ] E2E tests — not applicable.

## Relevant files

- `src/teams_recorder/domain/wiki.py` (new), `domain/status.py`, `domain/errors.py`, `domain/__init__.py`
- `src/teams_recorder/application/ports.py`, `adapters/outbound/codec.py`, `adapters/outbound/repository_fs.py`
- `src/teams_recorder/config.py`, `constants.py`, `messages.py`, `config.toml`
- `tests/fakes/__init__.py`, `tests/unit/test_wiki_domain.py` (new), `tests/unit/test_status.py`, `tests/unit/test_config.py`, `tests/integration/test_repository_fs.py`
