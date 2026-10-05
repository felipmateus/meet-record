"""CLI `trec`. Comandos de fases futuras existem, mas informam que ainda não estão disponíveis."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer

from teams_recorder import __version__
from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.config import ENV_PROJECT_DIR, load_settings
from teams_recorder.container import build_container, teams_tap_binary
from teams_recorder.domain import MeetingStatus, TeamsRecorderError, derive_status, next_step

app = typer.Typer(
    name="trec",
    help="Grava, transcreve e analisa reuniões do Microsoft Teams.",
    no_args_is_help=True,
    add_completion=False,
)

PHASES = {
    "daemon": 5,
    "plan": 6,
}


def _settings():
    env = os.environ.get(ENV_PROJECT_DIR)
    return load_settings(Path(env) if env else None)


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"erro: {message}", err=True)
    raise typer.Exit(code=code)


def _not_yet(command: str) -> None:
    typer.echo(f"`trec {command}` chega na fase {PHASES[command]}. Veja docs/REQUISITOS-E-ARQUITETURA.md, seção 10.")
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Mostra a versão."""
    typer.echo(f"teams-recorder {__version__}")


@app.command()
def status() -> None:
    """Lista reuniões, status de cada uma e ações abertas."""
    settings = _settings()
    c = build_container(settings, headless=True)
    meetings = c.repo.list_meetings()
    typer.echo(f"Dados em: {settings.data_dir}")
    typer.echo(f"Chave da API: {'configurada' if settings.has_api_key else 'AUSENTE'}")
    typer.echo(f"Reuniões: {len(meetings)}")
    for m in meetings:
        st = derive_status(c.repo.files(m.id))
        nxt = next_step(st)
        extra = f" → próximo: {nxt}" if nxt else ""
        title = f" {m.title}" if m.title else ""
        typer.echo(f"  {m.id}{title}  [{st.value}]{extra}")
    active = c.repo.load_active()
    if active:
        typer.echo(f"Gravação em andamento: {active.meeting.id} (gravadores PID {active.process_handle.pid}, {active.mic_handle.pid})")
    open_actions = c.repo.load_open_actions()
    typer.echo(f"Ações abertas: {len(open_actions)}")


@app.command()
def doctor() -> None:
    """Verifica dependências externas e permissões."""
    settings = _settings()
    checks = {
        "ffmpeg": shutil.which("ffmpeg"),
        "whisper-cli": shutil.which("whisper-cli"),
        "swift": shutil.which("swift"),
        "osascript": shutil.which("osascript"),
        "teams-tap": _teams_tap_path(settings.project_dir),
    }
    ok = True
    for name, found in checks.items():
        mark = "ok " if found else "FALTA"
        ok = ok and bool(found)
        typer.echo(f"[{mark}] {name}: {found or 'não encontrado'}")
    model_ok = settings.whisper_model_path.exists()
    ok = ok and model_ok
    typer.echo(f"[{'ok ' if model_ok else 'FALTA'}] modelo whisper: {settings.whisper_model_path}" + ("" if model_ok else "  → scripts/download-model.sh"))
    typer.echo(f"[{'ok ' if settings.has_api_key else 'FALTA'}] ANTHROPIC_API_KEY no .env")
    env_file = settings.project_dir / ".env"
    if env_file.exists():
        mode = env_file.stat().st_mode & 0o777
        if mode & 0o077:
            typer.echo(f"[AVISO] .env com permissão {oct(mode)}; recomendado: chmod 600 .env")
    typer.echo(f"[info] dados em {settings.data_dir}")
    raise typer.Exit(code=0 if ok and settings.has_api_key else 1)


@app.command()
def start(
    pid: int | None = typer.Option(None, help="PID do processo a capturar. Padrão: o Microsoft Teams em execução."),
    title: str | None = typer.Option(None, help="Título da reunião, usado no nome e no status."),
) -> None:
    """Inicia a gravação (áudio do Teams + microfone). Encerre com `trec stop`."""
    settings = _settings()
    c = build_container(settings)
    target = pid or find_pid(settings.teams_process_name)
    if target is None:
        _fail(f"processo {settings.teams_process_name} não está em execução; abra o Teams ou informe --pid")
    try:
        active = c.start_recording().execute(target, title)  # type: ignore[arg-type]
    except TeamsRecorderError as exc:
        _fail(str(exc))
    typer.echo(f"Gravando reunião {active.meeting.id} (PID alvo {target}).")
    typer.echo(f"  Teams:      {active.process_handle.out}  (gravador PID {active.process_handle.pid})")
    typer.echo(f"  Microfone:  {active.mic_handle.out}  (gravador PID {active.mic_handle.pid})")
    typer.echo("Encerre com `trec stop` ou descarte com `trec cancel`.")


@app.command()
def stop() -> None:
    """Encerra a gravação em andamento, mixa as trilhas e gera audio.m4a."""
    c = build_container(_settings())
    active = c.repo.load_active()
    if active is None:
        _fail("nenhuma gravação em andamento")
    try:
        meeting = c.stop_recording().execute(active)  # type: ignore[arg-type]
    except TeamsRecorderError as exc:
        _fail(str(exc))
    minutes = (meeting.duration_seconds or 0) / 60
    typer.echo(f"Reunião {meeting.id} encerrada após {minutes:.1f} min.")
    typer.echo(f"  Áudio: {c.repo.path(meeting.id, 'audio.m4a')}")
    typer.echo(f"Transcreva com `trec transcribe {meeting.id}`.")


@app.command()
def transcribe(
    meeting_id: str | None = typer.Argument(None, help="ID da reunião. Sem argumento: todas as gravadas e ainda não transcritas."),
) -> None:
    """Transcreve o áudio de uma reunião (ou de todas as pendentes) com whisper.cpp, localmente."""
    c = build_container(_settings(), headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(f"reunião {meeting_id} não existe")
        targets = [meeting_id]
    else:
        targets = [m.id for m in c.repo.list_meetings() if derive_status(c.repo.files(m.id)) == MeetingStatus.RECORDED]
        if not targets:
            typer.echo("Nenhuma reunião pendente de transcrição.")
            return
    use_case = c.transcribe_meeting()
    failures = 0
    for mid in targets:
        typer.echo(f"Transcrevendo {mid}…", nl=False)
        try:
            transcript = use_case.execute(mid)
        except TeamsRecorderError as exc:
            failures += 1
            c.repo.mark_failed(mid, f"transcrição: {exc}")
            typer.echo(f" FALHOU: {exc}")
            continue
        c.repo.clear_failed(mid)
        typer.echo(f" ok ({len(transcript.segments)} segmentos, {transcript.duration_seconds/60:.1f} min)")
        typer.echo(f"  Texto: {c.repo.path(mid, 'transcript.txt')}")
    if failures:
        raise typer.Exit(code=1)
    typer.echo("Analise com `trec analyze`.")


@app.command()
def cancel() -> None:
    """Descarta a gravação em andamento sem gerar arquivo."""
    c = build_container(_settings())
    active = c.repo.load_active()
    if active is None:
        _fail("nenhuma gravação em andamento")
    c.cancel_recording().execute(active)  # type: ignore[arg-type]
    typer.echo(f"Gravação {active.meeting.id} descartada.")  # type: ignore[union-attr]


@app.command()
def analyze(
    meeting_id: str | None = typer.Argument(None, help="ID da reunião. Sem argumento: todas as transcritas e ainda não analisadas."),
) -> None:
    """Extrai resumo, decisões, ações e prazos da transcrição com a Claude API."""
    settings = _settings()
    if not settings.has_api_key:
        _fail("ANTHROPIC_API_KEY ausente no .env")
    c = build_container(settings, headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(f"reunião {meeting_id} não existe")
        targets = [meeting_id]
    else:
        targets = [m.id for m in c.repo.list_meetings() if derive_status(c.repo.files(m.id)) == MeetingStatus.TRANSCRIBED]
        if not targets:
            typer.echo("Nenhuma reunião pendente de análise.")
            return
    use_case = c.analyze_meeting()
    failures = 0
    for mid in targets:
        typer.echo(f"Analisando {mid}…", nl=False)
        try:
            analysis = use_case.execute(mid)
        except TeamsRecorderError as exc:
            failures += 1
            c.repo.mark_failed(mid, f"análise: {exc}")
            typer.echo(f" FALHOU: {exc}")
            continue
        c.repo.clear_failed(mid)
        typer.echo(f" ok ({len(analysis.decisions)} decisões, {len(analysis.my_actions)} ações suas, {len(analysis.others_actions)} de terceiros)")
        typer.echo(f"  Resumo: {analysis.summary}")
        for a in analysis.my_actions:
            due = f" até {a.due.isoformat()}" if a.due else ""
            typer.echo(f"  • {a.description}{due}")
        typer.echo(f"  Arquivo: {c.repo.path(mid, 'analysis.json')}")
    if failures:
        raise typer.Exit(code=1)


@app.command()
def purge() -> None:
    """Apaga áudio de reuniões já transcritas com mais de N dias (config: planner.retention_days)."""
    c = build_container(_settings(), headless=True)
    purged = c.purge_old_audio().execute()
    typer.echo(f"Áudios removidos: {len(purged)}")
    for mid in purged:
        typer.echo(f"  {mid}")


def _teams_tap_path(project_dir: Path) -> str | None:
    candidate = teams_tap_binary(project_dir)
    return str(candidate) if candidate.exists() else None


for _cmd in PHASES:
    def _make(name: str):
        def _impl() -> None:
            _not_yet(name)
        _impl.__name__ = name
        _impl.__doc__ = f"(fase {PHASES[name]}) ainda não disponível."
        return _impl
    app.command(name=_cmd)(_make(_cmd))


if __name__ == "__main__":
    app()
