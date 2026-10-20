"""Daemon: watches the detector and triggers recording → transcription → analysis without intervention.

Simple state machine with hysteresis: starts recording after N consecutive positive
readings and stops after M negative ones (config [detector]). Post-processing runs in
a thread so detection of the next call can continue immediately.

When the container has a RecordingConfirmation, the daemon asks whether to keep each
recording it starts. Recording begins at once so the start of the meeting is never lost;
"discard" cancels it and the rest of that call is ignored, and no answer keeps it. If the
call ends before the answer, the capture stops at hang-up and post-processing waits for
the answer before transcribing.

The daemon owns a CuratorWorker: a thread that, after each meeting reaches `analyzed`, updates the
activities document (CurateMeetings). The pipeline hands it the meeting ids; the worker batches them,
adds the meetings still pending from the last working days, and is never awaited on shutdown.

The first tick of each calendar day also schedules the audio retention (`PurgeOldAudio`) in the background; the tick
never runs it inline, the day is recorded before it is scheduled, and a failure is logged and not retried that day.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import date, datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from teams_recorder.application.ports import ActiveRecording, CallDetector, CallState, CaptureHandle, ConfirmAnswer
from teams_recorder.application.use_cases.activities import CurateMeetings, batches
from teams_recorder.constants import Activities, Audio, Confirm, Detector, Proc
from teams_recorder.container import Container
from teams_recorder.domain import Meeting, TeamsRecorderError, derive_status
from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Err, Log, Notify

log = logging.getLogger(__name__)


class _Watchable(Protocol):
    def is_running(self, handle: CaptureHandle) -> bool: ...


@dataclass
class _Question:
    """A keep-recording question in flight; `done` is set once `answer` is final."""
    done: threading.Event = field(default_factory=threading.Event)
    answer: ConfirmAnswer = ConfirmAnswer.NO_ANSWER


class CuratorWorker:
    """One daemon thread that curates the meetings the pipeline hands it. `enqueue` never blocks; a round takes the id the
    thread woke up for, up to `Activities.WORKER_DRAIN` more, and the meetings `CurateMeetings.pending()` finds (analyzed in
    the last working days, no pass yet, fewer than two failed attempts), and runs them in passes of four, oldest first. A queued
    id the pass log already shows as curated is dropped when its round starts (`pending()` of an earlier round may have run it
    while it waited in the queue), so no meeting is curated twice. The queue lives in memory: a restart loses it, and
    `pending()` rebuilds it (the daemon enqueues it at start).

    `request_stop()` sets a flag and wakes an idle thread; a pass in flight is never awaited (it can take 900 s), and what it
    leaves unfinished is rebuilt by `pending()` at the next start."""

    def __init__(self, curate: CurateMeetings) -> None:
        self.curate = curate
        self._queue: queue.Queue[str | None] = queue.Queue()   # None is the stop sentinel
        self._stopping = threading.Event()
        self.thread: threading.Thread | None = None

    # --- called by the pipeline and the daemon ----------------------------------------------------------------------
    def enqueue(self, meeting_id: str) -> None:
        """Queues a meeting for the next round; ignored once the worker was told to stop."""
        if not self._stopping.is_set():
            self._queue.put(meeting_id)

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="curator-worker", daemon=True)
        self.thread.start()

    def request_stop(self) -> None:
        log.info(Log.WORKER_STOPPING)
        self._stopping.set()
        self._queue.put(None)

    @property
    def stopping(self) -> bool:
        return self._stopping.is_set()

    # --- the thread -------------------------------------------------------------------------------------------------
    def run(self) -> None:
        log.info(Log.WORKER_STARTED)
        while self.step():
            pass
        log.info(Log.WORKER_STOPPED)

    def step(self) -> bool:
        """One round: waits for an id, curates it with what else is queued or pending. False once the worker must stop."""
        first = self._queue.get()
        if first is None or self._stopping.is_set():
            return False
        queued = self._uncurated([first] + self._drain())
        try:
            pending = self.curate.pending()
        except Exception as exc:  # noqa: BLE001 - the queued meetings are curated whatever the listing did
            log.warning(Log.WORKER_QUEUE_PENDING_FAILED, exc)
            pending = []
        passes = batches(queued + pending)
        log.info(Log.WORKER_QUEUE, sum(len(b) for b in passes), len(queued), len(pending), ", ".join(m for b in passes for m in b))
        for n, ids in enumerate(passes, 1):
            if self._stopping.is_set():
                return False
            self._run_pass(n, len(passes), ids)
        return True

    def _uncurated(self, queued: list[str]) -> list[str]:
        """`queued` without the ids that already have a successful pass; all of them when the pass log cannot be read."""
        try:
            wanted = self.curate.uncurated(queued)
        except Exception as exc:  # noqa: BLE001 - the queued meetings are curated whatever the check did
            log.warning(Log.WORKER_QUEUE_FILTER_FAILED, exc)
            return queued
        dropped = [meeting_id for meeting_id in queued if meeting_id not in wanted]
        if dropped:
            log.info(Log.WORKER_QUEUE_DONE, len(dropped), ", ".join(dropped))
        return wanted

    def _drain(self) -> list[str]:
        ids: list[str] = []
        while len(ids) < Activities.WORKER_DRAIN:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:   # the stop sentinel: leave the loop; the flag is already set
                break
            ids.append(item)
        return ids

    def _run_pass(self, n: int, total: int, ids: list[str]) -> None:
        label = ", ".join(ids)
        log.info(Log.WORKER_PASS_START, n, total, label)
        try:
            result = self.curate.execute(ids, wait=True, on_wait=lambda: log.info(Log.WORKER_LOCK_WAIT, label))
        except Exception:  # noqa: BLE001 - the thread outlives one bad pass
            log.exception(Log.WORKER_PASS_FAILED, label)
            return
        log.info(Log.WORKER_PASS_END, label, len(result.curated), len(result.failed), len(result.deferred), result.edits)


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
    disk_warned: set[str] = field(default_factory=set)   # meetings already warned about a nearly full disk
    purge_day: date | None = None   # the day the audio retention was last scheduled; None until the first tick
    curator_worker: CuratorWorker | None = field(init=False, default=None)   # None: [activities] enabled = false, or a container without the curator

    def __post_init__(self) -> None:
        self.curator_worker = self._build_curator_worker()

    def _build_curator_worker(self) -> CuratorWorker | None:
        """The curator's worker, built from the container's `curate_meetings()`; the daemon owns it because the container
        never imports this module. A container without the builder (the test doubles) or `[activities] enabled = false`
        means no worker, and nothing is enqueued."""
        build = getattr(self.container, "curate_meetings", None)
        if build is None or not self.container.settings.activities_enabled:
            return None
        return CuratorWorker(build())

    def _after_analysis(self) -> Callable[[str], None] | None:
        """The hook the pipeline calls with each meeting that reaches `analyzed`."""
        return self.curator_worker.enqueue if self.curator_worker is not None else None

    # --- lifecycle --------------------------------------------------------
    def run(self) -> None:
        log.info(Log.DAEMON_STARTED, self.poll_seconds, self.start_after, self.stop_after)
        log.info(Log.WARMUP, Log.WARMUP_OK if self.container.process_capture.warmup() else Log.WARMUP_FAILED)
        self.recover()
        if self.curator_worker is not None:
            self.curator_worker.start()
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
        if self.curator_worker is not None:
            self.curator_worker.request_stop()   # never joined: a pass in flight can take 900 s; pending() rebuilds it at the next start
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
            self._watch_disk()
        self._handle_state(detector, state)
        self._schedule_purge()
        if self.active is not None:
            self._watch_observer()   # last: whatever it does or costs, the call state above was already handled

    def _schedule_purge(self) -> None:
        """On the first tick of each day, runs the audio retention in the background (never inline: the tick has a call to follow).
        The day is recorded before the work is scheduled, so a purge that fails is not retried until tomorrow."""
        today = self.container.clock.now().date()
        if self.purge_day == today:
            return
        self.purge_day = today
        self._background(self._purge)

    def _purge(self) -> None:
        try:
            purged = self.container.purge_old_audio().execute()
        except Exception:  # noqa: BLE001 - the retention is housekeeping: its failure never reaches the detector
            log.exception(Log.PURGE_FAILED)
            return
        log.info(Log.PURGE_DONE, len(purged))

    def _handle_state(self, detector: CallDetector, state: CallState) -> None:
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

    def _watch_disk(self) -> None:
        """Warn once per call when the disk is about to fill: the rest of the recording would be lost."""
        assert self.active is not None
        disk = getattr(self.container, "disk", None)
        meeting_id = self.active.meeting.id
        if disk is None or meeting_id in self.disk_warned:
            return
        free = disk.free_bytes()
        if free is not None and free < Audio.CRITICAL_DISK_BYTES:
            self.disk_warned.add(meeting_id)
            self.container.notifier.notify(Notify.DISK_CRITICAL, Notify.DISK_CRITICAL_BODY.format(free=free / 1e9))

    def _watch_capturers(self) -> None:
        """Warn (once per capturer) if a capture process died during the call."""
        assert self.active is not None
        settings = self.container.settings
        checks: list[tuple[str, _Watchable, CaptureHandle, Path]] = [
            (Log.CAPTURER_TAP, self.container.process_capture, self.active.process_handle, settings.capture_log),
            (Log.CAPTURER_MIC, self.container.mic_capture, self.active.mic_handle, settings.capture_log),
        ]
        for name, capture, handle, log_path in checks:
            self._warn_if_dead(name, capture, handle, log_path)

    def _watch_observer(self) -> None:
        """Warn (once) if the speaker observer died during the call. The observer is an extra: its check asks launchd (a
        subprocess), so nothing it raises may reach the tick, which has the call's end to detect. An error is logged once per
        call and the check is tried again on the next tick."""
        assert self.active is not None
        speakers = getattr(self.container, "speakers", None)   # absent on the Windows container and in test doubles
        handle = self.active.speakers_handle
        if speakers is None or handle is None:
            return
        try:
            self._warn_if_dead(Log.CAPTURER_SPEAKERS, speakers, handle, self.container.settings.speakers_log)
        except Exception as exc:  # noqa: BLE001 - see above
            key = f"{self.active.meeting.id}:{Log.CAPTURER_SPEAKERS}:{Log.SPEAKERS_CHECK_FAILED}"
            if key not in self.warned_dead:
                self.warned_dead.add(key)
                log.warning(Log.SPEAKERS_CHECK_FAILED, self.active.meeting.id, exc)

    def _warn_if_dead(self, name: str, capture: _Watchable, handle: CaptureHandle, log_path: Path) -> None:
        assert self.active is not None
        key = f"{self.active.meeting.id}:{name}"
        if key in self.warned_dead:
            return
        if not capture.is_running(handle):
            self.warned_dead.add(key)
            log.warning(Log.CAPTURER_DIED, name, handle.pid, self.active.meeting.id, log_path)

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
        pipeline = self.container.pipeline(after_analysis=self._after_analysis())
        question = self.questions.pop(active.meeting.id, None)
        if question is not None and question.done.is_set() and question.answer is ConfirmAnswer.DISCARD:
            self.container.cancel_recording().execute(active)   # answered in the same tick the call ended
            return
        # Stop the recorders and release the active pointer here, in the detector loop: a call that
        # starts while the previous one is still mixing must be recorded, not taken for it.
        try:
            meeting = self.container.stop_recording().stop_capture(active)
        except Exception:  # noqa: BLE001
            log.exception(Log.POSTPROCESS_FAILED, active.meeting.id)
            return

        def job() -> None:
            try:
                if question is not None and not question.done.is_set():
                    question.done.wait(self.confirm_wait)   # wait for the answer before spending time on it
                if question is not None and question.answer is ConfirmAnswer.DISCARD:
                    self.container.cancel_recording().discard(meeting.id)
                    log.info(Log.DISCARDED_AFTER_CALL, meeting.id)
                    return
                pipeline.after_stop(meeting)
                status = derive_status(self.container.repo.files(meeting.id))
                log.info(Log.PROCESSED, meeting.id, status.value)
            except Exception:  # noqa: BLE001
                log.exception(Log.POSTPROCESS_FAILED, meeting.id)

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
            # Only stop and release here; mixing (minutes for a long meeting) is left to
            # resume_pending in the background so detection starts at once.
            ended_at = self._last_write(active)
            try:
                self.container.stop_recording().stop_capture(active, ended_at=ended_at)
            except TeamsRecorderError:
                log.exception(Log.ORPHAN_DISCARDED)
                self.container.cancel_recording().execute(active)
        else:
            self._stop_leftover_observer(active)
            repo.clear_active()

    def _stop_leftover_observer(self, active: ActiveRecording) -> None:
        """A recording that left no track still may have left the observer's launchd job running, with or without the
        handle: a crash during the observer's startup grace leaves the job and no persisted handle."""
        speakers = getattr(self.container, "speakers", None)
        if speakers is None:
            return
        handle = active.speakers_handle
        try:
            if handle is None:
                speakers.stop_stale()
            else:
                speakers.stop(handle)
        except Exception as exc:  # noqa: BLE001 - recovery goes on
            log.warning(Log.SPEAKERS_STOP_FAILED, handle.pid if handle is not None else None, exc)

    def _last_write(self, active: ActiveRecording) -> datetime | None:
        """When the recorders last wrote: the real end of a call the daemon did not see end."""
        times: list[float] = []
        for track in (TAP_TRACK, MIC_TRACK):
            try:
                times.append(self.container.repo.path(active.meeting.id, track).stat().st_mtime)
            except OSError:
                continue
        return datetime.fromtimestamp(max(times)) if times else None

    def _resume_pending(self) -> None:
        self._enqueue_pending()
        try:
            results = self.container.pipeline(after_analysis=self._after_analysis()).resume_pending()
            if results:
                log.info(Log.RESUMED, results)
        except Exception:  # noqa: BLE001
            log.exception(Log.RESUME_FAILED)

    def _enqueue_pending(self) -> None:
        """Rebuilds the curator's queue, which a restart loses: the analyzed meetings of the last working days that have no
        pass yet. The worker lists them again at every round; this one wakes it."""
        worker = self.curator_worker
        if worker is None:
            return
        try:
            ids = worker.curate.pending()
            for meeting_id in ids:
                worker.enqueue(meeting_id)
            if ids:
                log.info(Log.WORKER_PENDING_ENQUEUED, len(ids), ", ".join(ids))
        except Exception as exc:  # noqa: BLE001 - resuming the pipeline goes on
            log.warning(Log.WORKER_PENDING_FAILED, exc)

    def _background(self, fn: Callable[[], None]) -> None:
        if self.run_in_background is not None:
            self.run_in_background(fn)
            return
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        self.workers = [w for w in self.workers if w.is_alive()] + [t]
