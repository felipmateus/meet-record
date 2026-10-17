"""SpeakerObserver via the Swift `teams-speakers` helper, run as its own launchd job.

Why a job and not a child process of the daemon: macOS holds the process that started a program responsible for its
Accessibility permission, so a helper spawned by the daemon's Python is judged by the Python's grant (missing), while
a job launchd starts itself is judged by the helper's own grant (measured on 2026-10-17, docs/tasks/speaker-attribution
task_03). So each recording gets a job definition under `<data_dir>/run/`, booted in the user's GUI domain; stopping
boots it out. Every launchctl call goes through the injected `runner`, so tests never touch the real launchd.
"""
from __future__ import annotations

import logging
import plistlib
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from teams_recorder.adapters.outbound import process_control
from teams_recorder.adapters.outbound.launchd import JobState, Runner, job_domain, parse_print, run_launchctl
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.constants import Files, Launchd, Proc, Speakers
from teams_recorder.domain import SpeakerReason, SpeakersUnavailable
from teams_recorder.messages import Err, Log

log = logging.getLogger(__name__)

PLIST_SUFFIX = ".plist"
BOOTSTRAP_RETRIES = 5       # right after a bootout launchd may answer "Input/output error" for a moment
BOOTSTRAP_RETRY_DELAY = 0.5


class AxSpeakerObserver:
    def __init__(
        self,
        binary: Path,
        run_dir: Path,
        log_path: Path | None = None,
        interval: float = Speakers.INTERVAL,
        runner: Runner = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
        startup_grace: float = Speakers.STARTUP_GRACE,
        stop_timeout: float = Speakers.STOP_TIMEOUT,
        check_timeout: float = Speakers.CHECK_TIMEOUT,
        terminate: Callable[..., None] = process_control.terminate,
        alive: Callable[[int], bool] = process_control.is_running,
    ) -> None:
        self.binary = Path(binary)
        self.run_dir = Path(run_dir)    # <data_dir>/run: the job definitions
        self.log_path = log_path        # the helper's stderr (data/log/speakers.log)
        self.interval = interval
        self.runner = runner
        self.sleep = sleep
        self.startup_grace = startup_grace
        self.stop_timeout = stop_timeout
        self.check_timeout = check_timeout
        self._terminate = terminate     # SIGTERM by pid, escalating to SIGKILL; the fallback when launchctl cannot stop the job
        self._alive = alive

    # --- job definitions ------------------------------------------------------------------------------------------

    def command(self, out: Path, epoch: float) -> list[str]:
        """The helper's command line; `--epoch` is mandatory: every event time is relative to it."""
        return [str(self.binary), "--out", str(out), "--epoch", f"{epoch:.3f}", "--interval", str(self.interval)]

    def job(self, out: Path, epoch: float) -> dict[str, Any]:
        """The launchd job of one recording: runs once at load, never restarted (a dead helper stays dead and is logged)."""
        return self._job(Launchd.SPEAKERS_LABEL, self.command(out, epoch))

    def check_job(self) -> dict[str, Any]:
        return self._job(Launchd.SPEAKERS_CHECK_LABEL, [str(self.binary), "--check"])

    def _job(self, label: str, arguments: list[str]) -> dict[str, Any]:
        definition: dict[str, Any] = {"Label": label, "ProgramArguments": arguments, "RunAtLoad": True, "ProcessType": "Background"}
        if self.log_path is not None:
            definition["StandardErrorPath"] = str(self.log_path)
        return definition

    def plist_path(self, label: str = Launchd.SPEAKERS_LABEL) -> Path:
        return self.run_dir / f"{label}{PLIST_SUFFIX}"

    # --- the SpeakerObserver port ---------------------------------------------------------------------------------

    def start(self, out: Path, epoch: float) -> CaptureHandle:
        if not self.binary.exists():
            raise SpeakersUnavailable(
                SpeakerReason.BINARY_MISSING, Err.SPEAKERS_BINARY_MISSING.format(path=self.binary, script=Files.BUILD_NATIVE_SCRIPT))
        label = Launchd.SPEAKERS_LABEL
        failure: str | SpeakersUnavailable | None = self._boot(label, self.job(out, epoch))
        if failure is None:
            state = self._watch(label)
            if state.running:
                assert state.pid is not None
                return CaptureHandle(pid=state.pid, out=out)
            failure = self._exit_failure(state)
        self._cleanup(label)
        if isinstance(failure, SpeakersUnavailable):
            raise failure
        raise SpeakersUnavailable(SpeakerReason.START_FAILED, Err.SPEAKERS_START_FAILED.format(label=label, detail=failure))

    def stop(self, handle: CaptureHandle) -> Path:
        self._bootout(Launchd.SPEAKERS_LABEL, handle.pid)
        return handle.out

    def stop_stale(self) -> None:
        """Boots out the helper's job when one was left behind, with no handle to name it: a crash or an interrupted start
        between the bootstrap and the persisting of the handle (safety invariant 11: the label is fixed, at most one job).
        The job definition is written before the bootstrap and removed only with the job, so no definition means no job
        and nothing is asked of launchd."""
        label = Launchd.SPEAKERS_LABEL
        if not self.plist_path(label).exists():
            return
        pid = self._state(label).pid
        log.info(Log.SPEAKERS_STALE_STOPPED, label, pid)
        self._bootout(label, pid)

    def _bootout(self, label: str, pid: int | None) -> None:
        """Boots the job out and removes its definition; waits for the helper `pid` to leave (stopped by pid when launchctl refuses)."""
        result = self._launchctl("bootout", self._target(label))
        self.plist_path(label).unlink(missing_ok=True)
        if pid is None:
            return
        if result.returncode == 0:
            self._wait_gone(pid)
        elif self._alive(pid):
            log.warning(Log.SPEAKERS_BOOTOUT_FAILED, label, result.stderr.strip(), pid)
            self._terminate(pid, signal.SIGTERM, self.stop_timeout, {})

    def is_running(self, handle: CaptureHandle) -> bool:
        result = self._launchctl("print", self._target(Launchd.SPEAKERS_LABEL))
        if result.returncode == 0:
            return parse_print(result.stdout).running
        return self._alive(handle.pid)

    def problems(self) -> list[str]:
        """What keeps the observer from running; the permission is checked by running `--check` as its own short-lived job."""
        if not self.binary.exists():
            return [Err.SPEAKERS_PROBLEM_NOT_BUILT.format(script=Files.BUILD_NATIVE_SCRIPT)]
        label = Launchd.SPEAKERS_CHECK_LABEL
        failure = self._boot(label, self.check_job())
        try:
            if failure is not None:
                return [Err.SPEAKERS_PROBLEM_CHECK.format(detail=failure)]
            state = self._wait_exit(label)
        finally:
            self._cleanup(label)
        if state.last_exit == Speakers.EXIT_GRANTED:
            return []
        if state.last_exit == Speakers.EXIT_PERMISSION:
            return [Err.SPEAKERS_PROBLEM_PERMISSION.format(binary=self.binary)]
        detail = Err.SPEAKERS_EXITED.format(code=state.last_exit, tail=self._log_tail()).strip() if state.last_exit is not None else \
            Err.SPEAKERS_CHECK_HUNG.format(seconds=self.check_timeout)
        return [Err.SPEAKERS_PROBLEM_CHECK.format(detail=detail)]

    # --- launchd ----------------------------------------------------------------------------------------------------

    @staticmethod
    def _target(label: str) -> str:
        return f"{job_domain()}/{label}"

    def _launchctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Every call is time-bounded: the daemon asks for the job's state on every tick, so a stalled launchctl must not stall it."""
        timeout = Speakers.LAUNCHCTL_PRINT_TIMEOUT if args[0] == "print" else Speakers.LAUNCHCTL_TIMEOUT  # literal-ok: launchctl subcommand
        return run_launchctl(self.runner, *args, timeout=timeout)

    def _state(self, label: str) -> JobState:
        result = self._launchctl("print", self._target(label))
        return parse_print(result.stdout) if result.returncode == 0 else JobState()

    def _boot(self, label: str, definition: dict[str, Any]) -> str | None:
        """Writes the definition, boots out a stale job with that label and bootstraps the new one; the failure text, or None."""
        plist = self.plist_path(label)
        try:
            plist.parent.mkdir(parents=True, exist_ok=True)
            with plist.open("wb") as fh:
                plistlib.dump(definition, fh)
        except OSError as exc:
            return str(exc)
        self._launchctl("bootout", self._target(label))
        last: subprocess.CompletedProcess[str] | None = None
        for _ in range(BOOTSTRAP_RETRIES):
            last = self._launchctl("bootstrap", job_domain(), str(plist))
            if last.returncode == 0:
                return None
            self.sleep(BOOTSTRAP_RETRY_DELAY)
        assert last is not None
        return Err.SPEAKERS_LAUNCHD.format(args="bootstrap", code=last.returncode, stderr=last.stderr.strip())

    def _cleanup(self, label: str) -> None:
        self._launchctl("bootout", self._target(label))
        self.plist_path(label).unlink(missing_ok=True)

    def _watch(self, label: str) -> JobState:
        """Reads the job through the startup grace; stops at the first exit. A running state at the end means it started."""
        state = JobState()
        for _ in range(max(1, round(self.startup_grace / Speakers.STARTUP_POLL))):
            self.sleep(Speakers.STARTUP_POLL)
            state = self._state(label)
            if state.last_exit is not None and not state.running:
                break
        return state

    def _wait_exit(self, label: str) -> JobState:
        state = JobState()
        for _ in range(max(1, round(self.check_timeout / Speakers.CHECK_POLL))):
            self.sleep(Speakers.CHECK_POLL)
            state = self._state(label)
            if state.last_exit is not None and not state.running:
                break
        return state

    def _exit_failure(self, state: JobState) -> SpeakersUnavailable | str:
        """Why a job that is not running after the grace did not start: exit 3 is the missing permission, anything else a failure."""
        if state.last_exit == Speakers.EXIT_PERMISSION:
            return SpeakersUnavailable(
                SpeakerReason.PERMISSION_MISSING,
                Err.SPEAKERS_PERMISSION_MISSING.format(code=state.last_exit, tail=self._log_tail()).strip())
        if state.last_exit is not None:
            return Err.SPEAKERS_EXITED.format(code=state.last_exit, tail=self._log_tail()).strip()
        return Err.SPEAKERS_NOT_RUNNING.format(seconds=self.startup_grace)

    def _wait_gone(self, pid: int) -> None:
        """After a bootout launchd waits for the helper; a straggler is stopped by pid (SIGKILL after the timeout)."""
        for _ in range(max(1, round(self.stop_timeout / Proc.STOP_POLL))):
            if not self._alive(pid):
                return
            self.sleep(Proc.STOP_POLL)
        self._terminate(pid, signal.SIGKILL, self.stop_timeout, {})

    def _log_tail(self) -> str:
        if self.log_path is None or not self.log_path.exists():
            return ""
        try:
            return " | ".join(self.log_path.read_text(errors="replace").splitlines()[-Speakers.TAIL_LINES:])
        except OSError:
            return ""
