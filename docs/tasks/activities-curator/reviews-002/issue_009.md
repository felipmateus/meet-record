---
provider: manual
pr:
round: 2
round_created_at: 2026-10-20T00:44:21Z
status: resolved
file: docs/tasks/activities-curator/_spec.md
line: 155
severity: low
author: claude-code
provider_ref:
---

# Issue 009: CuratorWorker has no stop contract on daemon shutdown

## Review Comment

`CuratorWorker` is "one thread, `queue.Queue`, owned and started by `Daemon`" (`_spec.md:155`), and it loops on `queue.get()` (`_spec.md:128`). The spec does not say how it stops.

The existing shutdown path (`daemon.py` `run` → `shutdown`, triggered by SIGTERM in `cli.daemon`, cli.py:537-538) joins `self.workers` with `Proc.WORKER_JOIN_TIMEOUT` and returns. Either choice the implementer makes has a cost the spec leaves open:

- **Non-daemon thread.** A thread blocked in `queue.get()` keeps the interpreter alive after `run()` returns. `trec agent restart` / bootout then waits until launchd SIGKILLs the process. That kill can land inside a commit, which is the reconcile case in reviews-002/issue_001.
- **Daemon thread.** The pass is abandoned at exit. That is acceptable, because recovery re-queues it, but it should be stated.

UT-107 covers start-up only.

Suggested fix: specify that the worker is a daemon thread (or stops on a sentinel that `shutdown` enqueues), that `shutdown` does not wait for an in-flight LLM call, and that an abandoned pass is recovered by `pending()` at the next start. Add a UT: `request_stop` with the worker idle → `run()` returns and the worker thread ends or is a daemon thread.

## Triage

- Decision: `VALID`
- Notes: Valid. The worker's lifecycle was unspecified; a non-daemon thread blocked in `queue.get()` keeps the process alive past `shutdown`, inviting a launchd SIGKILL that can land inside a commit.
- Verified (round 3): `CuratorWorker` is a daemon thread with `request_stop()` (a flag plus a sentinel). The diagram, Components, Key Decisions and Invariant 13 all say that shutdown never waits for an in-flight call and that `pending()` rebuilds the abandoned pass. UT-120 covers an idle stop, an enqueue after the stop and an in-flight pass.

### Resolution

Fixed: `CuratorWorker` is a daemon thread with `request_stop()` (flag plus sentinel); an idle worker returns and no new pass starts; `Daemon.shutdown` never waits for an in-flight LLM call; the abandoned pass is rebuilt by `pending()` at the next start; a kill inside a commit is the reconcile case. Key Decisions, Components, diagram, Invariant 13, UT-120.

