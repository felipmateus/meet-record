"""Daemon: observa o detector e dispara gravação → transcrição → análise sem intervenção.

Máquina de estados simples com histerese: começa a gravar após N leituras positivas
consecutivas e para após M negativas (config [detector]). O pós-processamento roda em
uma thread para a detecção da próxima chamada continuar imediatamente.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from teams_recorder.application.ports import ActiveRecording, CallState
from teams_recorder.container import Container
from teams_recorder.domain import TeamsRecorderError, derive_status
from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK

log = logging.getLogger(__name__)


@dataclass
class Daemon:
    container: Container
    poll_seconds: float = 3.0
    start_after: int = 2
    stop_after: int = 5
    sleep: Callable[[float], None] = time.sleep
    run_in_background: Callable[[Callable[[], None]], None] | None = None  # None = thread

    active: ActiveRecording | None = None
    positives: int = 0
    negatives: int = 0
    warned_dead: set[str] = field(default_factory=set)
    stop_event: threading.Event = field(default_factory=threading.Event)
    workers: list[threading.Thread] = field(default_factory=list)

    # --- ciclo de vida ----------------------------------------------------
    def run(self) -> None:
        log.info("daemon iniciado (poll=%ss, start_after=%s, stop_after=%s)", self.poll_seconds, self.start_after, self.stop_after)
        self.recover()
        self._background(self._resume_pending)
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - o laço nunca morre por uma iteração ruim
                log.exception("erro no ciclo do daemon")
            self.sleep(self.poll_seconds)
        self.shutdown()

    def request_stop(self) -> None:
        self.stop_event.set()

    def shutdown(self) -> None:
        if self.active is not None:
            log.info("encerrando gravação em andamento antes de sair")
            self._finish_call()
        for t in self.workers:
            t.join(timeout=30)
        log.info("daemon encerrado")

    # --- uma iteração -----------------------------------------------------
    def tick(self) -> None:
        detector = self.container.detector
        if detector is None:
            raise TeamsRecorderError("daemon sem detector configurado")
        state = detector.poll()
        if self.active is not None:
            self._watch_capturers()
        if state == CallState.UNKNOWN:
            return  # leitura falhou; não conta para nenhum lado
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
        """Avisa (uma vez por gravador) se um processo de captura morreu durante a chamada."""
        assert self.active is not None
        checks = (("teams-tap", self.container.process_capture, self.active.process_handle), ("microfone", self.container.mic_capture, self.active.mic_handle))
        for name, capture, handle in checks:
            key = f"{self.active.meeting.id}:{name}"
            if key in self.warned_dead:
                continue
            if not capture.is_running(handle):
                self.warned_dead.add(key)
                log.warning("gravador %s (pid %s) morreu durante a chamada %s; veja data/log/capture.log", name, handle.pid, self.active.meeting.id)

    def _start_call(self, pid: int | None) -> None:
        if pid is None:
            log.warning("chamada detectada mas sem PID do Teams; aguardando")
            return
        if self.container.repo.load_active() is not None:
            log.info("já existe gravação ativa (manual?); daemon não inicia outra")
            self.active = self.container.repo.load_active()
            return
        try:
            self.active = self.container.start_recording().execute(pid)
            log.info("gravação iniciada: %s (pid alvo %s)", self.active.meeting.id, pid)
        except TeamsRecorderError:
            log.exception("falha ao iniciar gravação")

    def _finish_call(self) -> None:
        active, self.active = self.active, None
        if active is None:
            return
        log.info("chamada encerrada; finalizando %s", active.meeting.id)
        pipeline = self.container.pipeline()

        def job() -> None:
            try:
                meeting = pipeline.run_after_call(active)
                status = derive_status(self.container.repo.files(meeting.id))
                log.info("reunião %s processada: %s", meeting.id, status.value)
            except Exception:  # noqa: BLE001
                log.exception("falha no pós-processamento de %s", active.meeting.id)

        self._background(job)

    # --- recuperação ------------------------------------------------------
    def recover(self) -> None:
        """Se o daemon caiu no meio de uma gravação, fecha o que der para fechar."""
        repo = self.container.repo
        active = repo.load_active()
        if active is None:
            return
        files = repo.files(active.meeting.id)
        if TAP_TRACK in files or MIC_TRACK in files:
            log.warning("gravação órfã encontrada (%s); tentando finalizar", active.meeting.id)
            try:
                self.container.stop_recording().execute(active)
            except TeamsRecorderError:
                log.exception("não consegui finalizar a gravação órfã; descartando")
                self.container.cancel_recording().execute(active)
        else:
            repo.clear_active()

    def _resume_pending(self) -> None:
        try:
            results = self.container.pipeline().resume_pending()
            if results:
                log.info("pendências retomadas: %s", results)
        except Exception:  # noqa: BLE001
            log.exception("falha ao retomar pendências")

    def _background(self, fn: Callable[[], None]) -> None:
        if self.run_in_background is not None:
            self.run_in_background(fn)
            return
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        self.workers = [w for w in self.workers if w.is_alive()] + [t]
