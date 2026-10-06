"""Daemon: watches the detector and triggers recording → transcription → analysis without intervention.

Simple state machine with hysteresis: starts recording after N consecutive positive
readings and stops after M negative ones (config [detector]). Post-processing runs in
a thread so detection of the next call can continue immediately.

When the container has a RecordingConfirmation, the daemon asks whether to keep each
recording it starts. Recording begins at once so the start of the meeting is never lost;
"discard" cancels it and the rest of that call is ignored, and no answer keeps it. If the
call ends before the answer, the capture stops at hang-up and post-processing waits for
the answer before transcribing.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from teams_recorder.application.ports import ActiveRecording, CallState, ConfirmAnswer
from teams_recorder.constants import Confirm, Detector, Proc
from teams_recorder.container import Container
from teams_recorder.domain import Meeting, TeamsRecorderError, derive_status
from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Err, Log

log = logging.getLogger(__name__)


@dataclass
class _Question:
    """A keep-recording question in flight; `done` is set once `answer` is final."""
    done: threading.Event = field(default_factory=threading.Event)
    answer: ConfirmAnswer = ConfirmAnswer.NO_ANSWER


@dataclass
class Daemon:
    container: Container
    poll_seconds: float = Detector.POLL_SECONDS
    start_after: int = Detector.START_AFTER
    stop_after: int = Detector.STOP_AFTER
    sleep: Callable[[float], None] = time.sleep
    run_in_background: Callable[[Callable[[], None]], None] | None = None  # None = thread
    confirm_wait: float = Confirm.TIMEOUT_SECONDS + Confirm.WAIT_MARGIN  # max wait for an answer after hang-up

    active: ActiveRecording | None = None
    positives: int = 0
    negatives: int = 0
    warned_dead: set[str] = field(default_factory=set)
    stop_event: threading.Event = field(default_factory=threading.Event)
    workers: list[threading.Thread] = field(default_factory=list)
    questions: dict[str, _Question] = field(default_factory=dict)   # meeting id -> keep-recording question
    ignoring_call: bool = False   # the user discarded this call's recording; wait until it ends

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
        self._apply_answer()
        if self.active is not None:
            self._watch_capturers()
        if state == CallState.UNKNOWN:
            return  # reading failed; counts for neither side
        if state == CallState.IN_CALL:
            self.positives += 1
            self.negatives = 0
            if self.active is None and not self.ignoring_call and self.positives >= self.start_after:
                self._start_call(detector.teams_pid())
        else:
            self.negatives += 1
            self.positives = 0
            if self.ignoring_call and self.negatives >= self.stop_after:
                self.ignoring_call = False
                log.info(Log.IGNORED_CALL_ENDED)
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
            return
        self._ask_to_keep(self.active.meeting)
        self._apply_answer()

    # --- keep-recording question ---------------------------------------------
    def _ask_to_keep(self, meeting: Meeting) -> None:
        confirmation = self.container.confirmation
        if confirmation is None:
            return
        question = _Question()
        self.questions[meeting.id] = question

        def job() -> None:
            try:
                question.answer = confirmation.ask(meeting)
            except Exception:  # noqa: BLE001 - a broken dialog must not cost the recording
                log.exception(Log.CONFIRM_FAILED, meeting.id)
            log.info(Log.CONFIRM_ANSWER, meeting.id, question.answer.value)
            question.done.set()

        self._background(job)

    def _apply_answer(self) -> None:
        """During the call: cancel the active recording if the user chose to discard it."""
        if self.active is None:
            return
        question = self.questions.get(self.active.meeting.id)
        if question is None or not question.done.is_set():
            return
        del self.questions[self.active.meeting.id]
        if question.answer is ConfirmAnswer.DISCARD:
            active, self.active = self.active, None
            self.container.cancel_recording().execute(active)
            self.ignoring_call = True
            log.info(Log.DISCARDED_DURING_CALL, active.meeting.id)

    def _finish_call(self) -> None:
        active, self.active = self.active, None
        if active is None:
            return
        log.info(Log.CALL_ENDED, active.meeting.id)
        pipeline = self.container.pipeline()
        question = self.questions.pop(active.meeting.id, None)

        def job() -> None:
            try:
                if question is None:
                    meeting = pipeline.run_after_call(active)
                elif question.done.is_set() and question.answer is ConfirmAnswer.DISCARD:
                    self.container.cancel_recording().execute(active)   # answered in the same tick the call ended
                    return
                else:
                    # Stop capturing at hang-up, then wait for the answer before spending time on it.
                    meeting = self.container.stop_recording().execute(active)
                    question.done.wait(self.confirm_wait)
                    if question.answer is ConfirmAnswer.DISCARD:
                        self.container.cancel_recording().discard(meeting.id)
                        log.info(Log.DISCARDED_AFTER_CALL, meeting.id)
                        return
                    pipeline.process(meeting.id)
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
