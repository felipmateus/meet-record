# Task 4.0: Destinations switch: configuration and registry

## Overview

Make destinations a configuration switch: parse `[stories] publish`, `destinations`, `dedup_days` and `[stories.backlog_md]` into `Settings`, and build one publisher per configured destination through a registry in the composition root, the same pattern `build_transport` uses for `llm.provider`. Delivers FR7. The Backlog.md builder is registered in 5.0; here the registry is exercised with a test builder.

<skills>
### Skills compliance

- `architecture-patterns`: strategy selected by configuration, registry in the composition root.
- `python-pro`: frozen settings, `StrEnum` parsing, path resolution.
- `python-testing-patterns`: configuration fixtures in temporary projects.
</skills>

<requirements>
- `StoryDestination(StrEnum)` with `BACKLOG_MD = "backlog-md"`; `Bin.BACKLOG`; `Stories.PUBLISH`, `DEDUP_DAYS`, `BACKLOG_STATUS`, `BACKLOG_LABELS` — techspec §6.
- `Settings`: `stories_publish`, `story_destinations`, `story_dedup_days`, `backlog_project_dir` (relative to the project, `~` expanded, `"."` = the project), `backlog_status`, `backlog_labels`. Unknown destination → `ValueError(Err.INVALID_DESTINATION)`.
- Without the new keys nothing is published (defaults keep today's behavior).
- `_PUBLISHERS` registry, `build_story_publishers(settings)` in configured order, `Container.story_publishers`, `Container.publish_user_stories()`, and `dedup_days` from settings in `draft_user_stories()` — techspec §7.
- `config.toml` documents the new keys with publishing still off (`publish = false`); it is switched on in 7.0 after validation.
</requirements>

## Subtasks

- [ ] 4.1 Add the enum and constants.
- [ ] 4.2 Add the settings fields and their parsing (list of enums, paths, labels) in `config.py`.
- [ ] 4.3 Add `Err.INVALID_DESTINATION`.
- [ ] 4.4 Add the registry, `build_story_publishers` and the container fields and factory methods.
- [ ] 4.5 Document the keys in `config.toml` (publishing off).
- [ ] 4.6 Write the unit and integration tests below.

## Implementation details

See techspec §2 ("The switch"), §6 and §7.

## Success criteria

- `destinations = ["backlog-md"]` parses to `(StoryDestination.BACKLOG_MD,)`; `["trello"]` fails with a message listing the valid values.
- `project_dir = "."` resolves to the project folder; a relative path to a subfolder; `~` expands.
- With a test builder registered, the container builds publishers in the configured order; with no destinations the list is empty and `trec plan` behaves as today.
- `pytest` and `mypy` clean.

## Task tests

- [ ] Unit tests — `tests/unit/test_config.py`: defaults, every new key, invalid destination, path resolution; `tests/unit/test_container_platforms.py`: registry order and empty list (registry patched with a test builder).
- [ ] Integration tests — `tests/integration/test_cli.py`: a temporary project whose `config.toml` has an invalid destination makes `trec plan` fail with the configuration message; the repository's own `config.toml` still loads (`load_settings` on the project folder).
- [ ] E2E tests — not applicable.

## Relevant files

- `src/teams_recorder/constants.py`, `config.py`, `messages.py`, `container.py`
- `config.toml`
- `tests/unit/test_config.py`, `tests/unit/test_container_platforms.py`, `tests/integration/test_cli.py`
