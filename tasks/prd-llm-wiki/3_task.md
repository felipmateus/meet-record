# Task 3.0: Wiki store and Git history adapters

## Overview

Implement the two file-side adapters: `FsWikiStore`, which owns the wiki folder (initialization with `CLAUDE.md`, frontmatter-based page listing, atomic writes, a blocking lock, backup for rebuilds, readiness problems including the fail-closed Git-ignore check), and `GitWikiHistory`, which commits the wiki after each ingest into a local repository with no remote. The Git-ignore check moves out of the Backlog.md publisher into a module both adapters share.

<skills>
### Skills compliance

- `python-pro`: `retry_io` on every file access, atomic writes, context managers.
- `testing-patterns`: real `tmp_path` folders for the store, a scripted runner for Git plus one test with the real binary.
- `clean-code`: the extraction of `git_ignore` keeps the publisher's behavior and tests intact.
</skills>

<requirements>
- `adapters/outbound/git_ignore.py`: `GitIgnore` and `git_ignore_state(path, git_bin, runner)` moved from `publisher_backlogmd.py`, which imports them from there; its tests keep passing unchanged.
- `adapters/outbound/wiki_fs.FsWikiStore(root)` implementing `WikiStore` (techspec §4.1, §5.1): `initialize(schema)` creates `people/ projects/ topics/ meetings/`, empty `index.md` and `log.md` when missing, and writes `CLAUDE.md` whenever it differs from `schema`; `pages()` parses every page (skipping `*.tmp`), raising `WikiError` with the file name on a malformed one; `exists/read/write/write_index/append_log`; `lock(timeout)` polling every `Wiki.LOCK_POLL`, removing a lock whose PID is dead (macOS/Linux `os.kill(pid, 0)`; Windows through `winproc`), `WikiError(Err.WIKI_LOCKED)` on timeout; `backup()` renames the root to `<root>.bak-<timestamp>` and recreates it; `problems()` for an unwritable root, a root Git would version (or Git unable to answer) and a stale `CLAUDE.md` (info).
- `adapters/outbound/wiki_git.GitWikiHistory(root, git_bin, runner)` implementing `WikiHistory` (techspec §5.2): `init` with a local identity when `.git` is missing, `add -A`, `commit`, `False` when nothing changed, `WikiError` with the stderr tail on failure, timeout `Wiki.GIT_TIMEOUT`, arguments as a list with `cwd=root` and `NO_WINDOW`; `problems()` for a missing binary (info) and a configured remote (problem). Never adds a remote, pushes or fetches.
- Fakes: `FakeWikiStore` (in-memory pages, records writes and log entries, `locked` flag, scripted `problems`), `FakeWikiHistory` (records commits, can fail).
- Strings in `messages` / `constants`; `mypy` clean.
</requirements>

## Subtasks

- [ ] 3.1 Extract `git_ignore.py`; update the publisher's import; run its tests.
- [ ] 3.2 Implement `FsWikiStore` with the lock, backup and problems.
- [ ] 3.3 Implement `GitWikiHistory` with an injected runner.
- [ ] 3.4 Add `FakeWikiStore` and `FakeWikiHistory` to `tests/fakes/__init__.py`.
- [ ] 3.5 Write the tests below.

## Implementation details

The lock mirrors `FsMeetingRepository.lock` but waits instead of failing: the daemon runs post-processing in one thread per call, so two back-to-back meetings will race for the wiki. Stale-lock detection reuses the PID-alive check the recording code already has (`process_control` on macOS, `winproc` on Windows) rather than a new one. `backup()` only renames; it never deletes. The real-Git test runs in `tmp_path` with `HOME` pointed at an empty folder so a missing global identity is exercised.

## Success criteria

- `initialize` on an empty folder leaves the layout of techspec §8; a second call changes nothing; an edited schema rewrites `CLAUDE.md` only.
- `pages()` returns the metadata of pages written by the store and ignores `.tmp`; a malformed page names its file in the error.
- A held lock makes a second `lock()` wait and then proceed when released; a lock with a dead PID is taken at once; the timeout raises.
- `problems()` is non-empty for a root inside a tracked Git tree and empty for one under an ignored folder or outside any work tree.
- `GitWikiHistory.commit` creates the repository, commits, returns `False` on a clean tree; a remote is reported; the publisher's tests still pass.

## Task tests

- [ ] Unit tests — `tests/unit/test_wiki_git.py` (scripted runner: command shapes, identity on init, nothing to commit, failure mapping, remote problem, missing binary).
- [ ] Integration tests — `tests/integration/test_wiki_fs.py` (`tmp_path`: initialize, refresh, pages, malformed page, lock wait in a thread, stale lock, backup, problems with a real `git init` above the root); `tests/integration/test_wiki_git_real.py` (real `git`, `tmp_path`, empty `HOME`).
- [ ] E2E tests — not applicable.

## Relevant files

- `src/teams_recorder/adapters/outbound/git_ignore.py` (new), `publisher_backlogmd.py`
- `src/teams_recorder/adapters/outbound/wiki_fs.py` (new), `wiki_git.py` (new)
- `src/teams_recorder/messages.py`, `constants.py`
- `tests/fakes/__init__.py`, `tests/unit/test_wiki_git.py` (new), `tests/integration/test_wiki_fs.py` (new), `tests/integration/test_wiki_git_real.py` (new), `tests/unit/test_publisher_backlogmd.py`
