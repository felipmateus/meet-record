---
provider: manual
pr:
round: 1
round_created_at: 2026-10-20T00:12:39Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 145
severity: medium
author: claude-code
provider_ref:
---

# Issue 005: Container cannot build CuratorWorker: daemon.py imports container

## Review Comment

The spec places `CuratorWorker` in `adapters/inbound/daemon.py` (`_spec.md:144`). It then says `container.py` "builds curator, store, worker" and is "the only place that instantiates ... `CuratorWorker`" (`_spec.md:145`, `:153`). `daemon.py` already imports the container at module level: `from teams_recorder.container import Container` (`src/teams_recorder/adapters/inbound/daemon.py:25`). If `container.py` imports `daemon.py` to build the worker, the two modules import each other. It would also break the existing layering, where inbound adapters (CLI, daemon) consume the container and the container never builds inbound adapters. `Daemon` itself is built in `cli.daemon`, not in the container.

The wiring of the hook is also left open. `Container.pipeline()` returns a fresh `Pipeline` on every call (`src/teams_recorder/container.py:137-138`). The daemon calls it in `_finish_call` (`daemon.py:223`) and in `_resume_pending` (`daemon.py:301`). The spec does not say which object sets `after_analysis = worker.enqueue` on each of these instances, nor how the CLI path differs (see issue 004).

Suggested fix: keep `CuratorWorker` (a thread plus a queue, i.e. inbound runtime) owned by `Daemon`, built in `Daemon.__post_init__` or `run()` from `container.curate_meetings()`, a new factory like `analyze_meeting()`. Give `Container.pipeline()` an optional `after_analysis` parameter, which the daemon passes as `self.curator_worker.enqueue`. Update `_spec.md:145,153` to say the container builds `ClaudeCurator`, `FsActivityStore` and the `CurateMeetings` use case, and the daemon owns the worker thread.

## Triage

- Decision: `VALID`
- Notes: Valid. Verified: `daemon.py:25` imports `Container`; a container that built `CuratorWorker` from `daemon.py` would create an import cycle and invert the layering; `Container.pipeline()` returns a fresh `Pipeline` each call (container.py:137-138) and the spec did not say which object sets the hook.
- Verified: `Daemon` owns `CuratorWorker` built from `container.curate_meetings()`; `Container.pipeline(after_analysis=None)`; the two call sites the hook must reach are daemon.py:223 (`_finish_call`) and :301 (`_resume_pending`), both named; `container.py` never imports `daemon.py`; UT-107/108. Shutdown of the new thread is unspecified; tracked as reviews-002/issue_009.

### Resolution

Fixed as suggested. `Daemon` owns and starts `CuratorWorker`, built from `container.curate_meetings()`; `Container.pipeline(after_analysis=None)` takes the hook and the daemon passes `worker.enqueue` in `_finish_call` and `_resume_pending`; the container builds `ClaudeCurator`, `FsActivityStore` and `CurateMeetings` only and never imports `daemon.py`. Updated: Components, Architectural Boundaries, Core Interfaces (Pipeline/Container), System Architecture, Impact Analysis, Build Order step 5. With `[activities] enabled = false` no worker is built. Tests: UT-107, UT-108 (hook wiring and no container→daemon import).

