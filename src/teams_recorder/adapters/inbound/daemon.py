"""Daemon: watches the detector and triggers recording → transcription → analysis without intervention.

Simple state machine with hysteresis: starts recording after N consecutive positive
readings and stops after M negative ones (config [detector]). Post-processing runs in
a thread so detection of the next call can continue immediately.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from teams_recorder.application.ports import ActiveRecording, CallState
from teams_recorder.constants import Detector, Proc
from teams_recorder.container import Container
from teams_recorder.domain import TeamsRecorderError, derive_status
from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Err, Log

log = logging.getLogger(__name__)


@dataclass
class Daemon:
    container: Container
    poll_seconds: float = Detector.POLL_SECONDS
    start_after: int = Detector.START_AFTER
    stop_after: int = Detector.STOP_AFTER
    sleep: Callable[[float], None] = time.sleep
    run_in_background: Callable[[Callable[[], None]], None] | None = None  # None = thread

    active: ActiveRecording | None = None
    positives: int = 0
    negatives: int = 0
    warned_dead: set[str] = field(default_factory=set)
    stop_event: threading.Event = field(default_factory=threading.Event)
    workers: list[threading.Thread] = field(default_factory=list)

    # --- lifecycle --------------------------------------------------------
    def run(self) -> None:
        log.info(Log.DAEMON_STARTED, self.poll_seconds, self.start_after, self.stop_after)
        log.info(Log.WARMUP, Log.WARMUP_OK if self.container.process_capture.warmup() else Log.WARMUP_FAILED)
        self.recover()
        self._background(self._resume_pending)
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the loop never dies because of one bad iteration
                log.exception(Log.CYCLE_ERROR)
            self.sleep(self.poll_seconds)
        self.shutdown()

    def request_stop(self) -> None:
        self.stop_event.set()

    def shutdown(self) -> None:
        if self.active is not None:
            log.info(Log.FINISHING_BEFORE_EXIT)
            self._finish_call()
        for t in self.workers:
            t.join(timeout=Proc.WORKER_JOIN_TIMEOUT)
        log.info(Log.DAEMON_STOPPED)

    # --- one iteration ----------------------------------------------------
    def tick(self) -> None:
        detector = self.container.detector
        if detector is None:
            raise TeamsRecorderError(Err.NO_DETECTOR)
        state = detector.poll()
        if self.active is not None:
            self._watch_capturers()
        if state == CallState.UNKNOWN:
            return  # reading failed; counts for neither side
        if state == CallState.IN_CALL:
            self.positives += 1
            self.negatives = 0
            if self.active is None and self.positives >= self.start_after:
                self._start_call(detector.teams_pid())
        else:
            self.negatives += 1
            self.positives = 0
            if self.active is not None and self.negatives >= self.stop_after:
                self._finish_call()

    def _watch_capturers(self) -> None:
        """Warn (once per capturer) if a capture process died during the call."""
        assert self.active is not None
        checks = (
            (Log.CAPTURER_TAP, self.container.process_capture, self.active.process_handle),
            (Log.CAPTURER_MIC, self.container.mic_capture, self.active.mic_handle),
        )
        for name, capture, handle in checks:
            key = f"{self.active.meeting.id}:{name}"
            if key in self.warned_dead:
                continue
            if not capture.is_running(handle):
                self.warned_dead.add(key)
                log.warning(Log.CAPTURER_DIED, name, handle.pid, self.active.meeting.id, self.container.settings.capture_log)

    def _start_call(self, pid: int | None) -> None:
        if pid is None:
            log.warning(Log.CALL_WITHOUT_PID)
            return
        if self.container.repo.load_active() is not None:
            log.info(Log.ALREADY_ACTIVE)
            self.active = self.container.repo.load_active()
            return
        try:
            self.active = self.container.start_recording().execute(pid)
            log.info(Log.RECORDING_STARTED, self.active.meeting.id, pid)
        except TeamsRecorderError:
            log.exception(Log.START_FAILED)

    def _finish_call(self) -> None:
        active, self.active = self.active, None
        if active is None:
            return
        log.info(Log.CALL_ENDED, active.meeting.id)
        pipeline = self.container.pipeline()

        def job() -> None:
            try:
                meeting = pipeline.run_after_call(active)
                status = derive_status(self.container.repo.files(meeting.id))
                log.info(Log.PROCESSED, meeting.id, status.value)
            except Exception:  # noqa: BLE001
                log.exception(Log.POSTPROCESS_FAILED, active.meeting.id)

        self._background(job)

    # --- recovery ---------------------------------------------------------
    def recover(self) -> None:
        """If the daemon crashed in the middle of a recording, close whatever can be closed."""
        repo = self.container.repo
        active = repo.load_active()
        if active is None:
            return
        files = repo.files(active.meeting.id)
        if TAP_TRACK in files or MIC_TRACK in files:
            log.warning(Log.ORPHAN_FOUND, active.meeting.id)
            try:
                self.container.stop_recording().execute(active)
            except TeamsRecorderError:
                log.exception(Log.ORPHAN_DISCARDED)
                self.container.cancel_recording().execute(active)
        else:
            repo.clear_active()

    def _resume_pending(self) -> None:
        try:
            results = self.container.pipeline().resume_pending()
            if results:
                log.info(Log.RESUMED, results)
        except Exception:  # noqa: BLE001
            log.exception(Log.RESUME_FAILED)

    def _background(self, fn: Callable[[], None]) -> None:
        if self.run_in_background is not None:
            self.run_in_background(fn)
            return
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        self.workers = [w for w in self.workers if w.is_alive()] + [t]
