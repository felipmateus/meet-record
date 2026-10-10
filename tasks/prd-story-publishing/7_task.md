# Task 7.0: Real-data validation and documentation

## Overview

Prove the whole flow on real inputs (a real plan, the real model, a real Backlog.md project), let the user judge the stories on the board and tune the guide, switch publishing on in the repository's configuration, and bring every document in line with the new behavior. Delivers the success criteria of the PRD (§7).

<skills>
### Skills compliance

- `verification-before-completion`: evidence from real runs before declaring the feature done.
- `testing-patterns`: opt-in end-to-end test behind environment variables.
- `prompt-engineering-patterns`: guide adjustments from the user's review.
</skills>

<requirements>
- An opt-in end-to-end test (`-m slow`, `TREC_REAL_CLAUDE_CLI=1` and `TREC_REAL_BACKLOG=1`) over a fixture plan where the same topic appears on two days: the second day produces no duplicate story, and the first day's stories land in Triagem of a temporary Backlog.md project.
- Manual validation with the user on the plan of 2026-10-09, only with the user's approval (it uses the Claude Code subscription and real meeting content): draft, publish, review on the board (`backlog board` or `backlog browser`), adjust `prompts/user_story_guide.md` until the user accepts the quality.
- After the user's OK, `config.toml` switches publishing on (`publish = true`, `destinations = ["backlog-md"]`, `project_dir = "."`).
- Documentation in sync per AGENTS.md: `prd/pages/08-user-stories.md` (publishing section), `prd/README.md` (module status), `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 notes, `README.md` (one-time Backlog.md setup and `trec publish`), `AGENTS.md` (ports table with `StoryPublisher` / `BacklogMdPublisher`, the `TREC_REAL_BACKLOG` command), `docs/COMMITS.md` (wave row).
- The full suite and `mypy` clean; nothing under `backlog/` tracked by Git.
</requirements>

## Subtasks

- [ ] 7.1 Add the fixture plans and the opt-in end-to-end test.
- [ ] 7.2 Run the manual validation with the user and record the outcome (and any guide changes) in §10 of the requirements document.
- [ ] 7.3 Switch publishing on in `config.toml` after the user's OK.
- [ ] 7.4 Update the documents listed above.
- [ ] 7.5 Run `pytest`, the opt-in tests and `mypy`; check `git status` for `backlog/`.

## Implementation details

See PRD §7 (success criteria), techspec §12 (test matrix) and §13 (order). The commit wave follows `docs/COMMITS.md` and needs the user's approval (AGENTS.md).

## Success criteria

- The opt-in end-to-end test passes and shows one story for the repeated topic.
- The user reviews the 2026-10-09 stories in the Triagem column and accepts them (or the guide changes that made them acceptable are recorded).
- A rerun of `trec publish` for that day creates no new tasks.
- All listed documents describe the shipped behavior; `pytest`, `mypy` and the hardcoded-strings guard are clean.

## Task tests

- [ ] Unit tests — none new; the full suite must stay green.
- [ ] Integration tests — the full integration suite, plus the 5.0 opt-in real Backlog.md test.
- [ ] E2E tests — `tests/integration/test_story_publishing_e2e_real.py` (opt-in, real model and real Backlog.md), and the manual run on the plan of 2026-10-09.

## Relevant files

- `tests/fixtures/` (fixture plans and analyses), `tests/integration/test_story_publishing_e2e_real.py` (new)
- `prompts/user_story_guide.md`, `config.toml`
- `prd/pages/08-user-stories.md`, `prd/README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md`, `README.md`, `AGENTS.md`, `docs/COMMITS.md`
