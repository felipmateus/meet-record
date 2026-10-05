"""MeetingAnalyzer via Claude API (SDK oficial `anthropic`).

Desenho:
- O esquema de saída (Pydantic) vive aqui e é convertido para o domínio; o domínio não
  conhece a API.
- O prompt de sistema é fixo (prompts/analyze_system.md) e marcado para cache; o conteúdo
  variável (metadados da reunião e transcrição) vai na mensagem do usuário.
- Fallback de servidor habilitado por padrão: uma recusa pontual dos classificadores
  de segurança reexecuta a requisição em outro modelo, em vez de derrubar o pipeline.
- Toda chamada registra uso de tokens em um arquivo JSONL para controle de custo (R7).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:  # o SDK é importado sob demanda: é grande e só o analyze precisa dele
    import anthropic

from teams_recorder.domain import Action, Analysis, AnalysisError, Deadline, Decision, Meeting, Transcript

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MIN_WORDS = 20  # abaixo disso não vale uma chamada à LLM (silêncio, ruído, alucinação do whisper)


def trivial_analysis(transcript: Transcript, meeting: Meeting, min_words: int = MIN_WORDS) -> Analysis | None:
    """Análise local para transcrições vazias ou curtas demais; None quando vale analisar."""
    words = len(transcript.text.split())
    if words == 0:
        return Analysis(meeting_id=meeting.id, summary="Transcrição vazia: nenhuma fala reconhecida.")
    if words < min_words:
        return Analysis(
            meeting_id=meeting.id,
            summary=f"Transcrição muito curta ({words} palavras) para análise: \"{transcript.text.strip()[:120]}\"",
        )
    return None


# --- esquema de saída -------------------------------------------------------
class ActionOut(BaseModel):
    description: str = Field(description="Tarefa, começando com verbo no infinitivo")
    owner: str = Field(description="Responsável; 'usuário' para o dono da gravação; 'indefinido' se não souber")
    due: str | None = Field(default=None, description="Prazo em ISO (AAAA-MM-DD) ou null")


class DeadlineOut(BaseModel):
    what: str
    when: str | None = Field(default=None, description="Data ISO ou null")
    who: str = "indefinido"


class AnalysisOut(BaseModel):
    summary: str
    decisions: list[str] = Field(default_factory=list)
    my_actions: list[ActionOut] = Field(default_factory=list)
    others_actions: list[ActionOut] = Field(default_factory=list)
    deadlines: list[DeadlineOut] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_meetings: list[str] = Field(default_factory=list)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def to_domain(out: AnalysisOut, meeting: Meeting) -> Analysis:
    def act(a: ActionOut, default_owner: str | None = None) -> Action:
        return Action(description=a.description.strip(), owner=(default_owner or a.owner).strip(), source_meeting=meeting.id, due=_parse_date(a.due))

    return Analysis(
        meeting_id=meeting.id,
        summary=out.summary.strip(),
        decisions=[Decision(d.strip()) for d in out.decisions if d.strip()],
        my_actions=[act(a, "usuário") for a in out.my_actions],
        others_actions=[act(a) for a in out.others_actions],
        deadlines=[Deadline(d.what.strip(), _parse_date(d.when), d.who.strip() or "indefinido") for d in out.deadlines],
        open_questions=[q.strip() for q in out.open_questions if q.strip()],
        next_meetings=[m.strip() for m in out.next_meetings if m.strip()],
    )


def build_user_message(transcript: Transcript, meeting: Meeting) -> str:
    header = [
        f"Data da reunião: {meeting.started_at.date().isoformat()} ({_weekday_pt(meeting.started_at)})",
        f"Início: {meeting.started_at.strftime('%H:%M')}",
    ]
    if meeting.title:
        header.append(f"Título: {meeting.title}")
    if meeting.duration_seconds:
        header.append(f"Duração: {int(meeting.duration_seconds // 60)} min")
    return "\n".join(header) + "\n\nTranscrição (com marcação de tempo):\n\n" + transcript.as_timestamped_text()


def _weekday_pt(dt: datetime) -> str:
    return ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"][dt.weekday()]


# --- adaptador --------------------------------------------------------------
@dataclass
class ClaudeAnalyzer:
    system_prompt: str | None = None            # texto pronto (testes) ...
    prompt_path: Path | None = None             # ... ou arquivo carregado na primeira análise
    model: str = "claude-opus-5-5"
    effort: str = "high"
    max_tokens: int = 16000
    usage_log: Path | None = None
    client: "anthropic.Anthropic | None" = None
    use_fallbacks: bool = True
    min_words: int = MIN_WORDS

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise AnalysisError("ClaudeAnalyzer sem prompt de sistema (system_prompt ou prompt_path)")
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def _client(self) -> Any:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente (.env carregado em config)
        return self.client

    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis:
        trivial = trivial_analysis(transcript, meeting, self.min_words)
        if trivial is not None:
            return trivial
        response = self._request(build_user_message(transcript, meeting))
        self._log_usage(meeting.id, response)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            why = f" ({details.category}: {details.explanation})" if details else ""
            raise AnalysisError(f"a API recusou analisar a reunião {meeting.id}{why}")
        if response.stop_reason == "max_tokens":
            raise AnalysisError(f"resposta truncada em {self.max_tokens} tokens; aumente llm.max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AnalysisError("resposta sem bloco de texto")
        try:
            out = AnalysisOut.model_validate_json(text)
        except ValidationError as exc:
            raise AnalysisError(f"saída fora do esquema: {exc.errors()[:3]}") from exc
        return to_domain(out, meeting)

    # Única função que conhece a forma da requisição; a saída estruturada garante JSON válido
    # conforme o esquema, e o Pydantic valida de novo do nosso lado.
    def _request(self, user_message: str) -> Any:
        import anthropic

        client = self._client()
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": self._system(), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_message}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": _strict_schema(AnalysisOut)},
            },
        )
        try:
            if self.use_fallbacks:
                return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            return client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise AnalysisError("chave da API inválida ou ausente (ANTHROPIC_API_KEY no .env)") from exc
        except anthropic.RateLimitError as exc:
            raise AnalysisError(f"limite de requisições atingido; tente de novo em instantes ({exc.message})") from exc
        except anthropic.APIStatusError as exc:
            raise AnalysisError(f"erro da API ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AnalysisError(f"sem conexão com a API: {exc}") from exc

    def _log_usage(self, meeting_id: str, response: Any) -> None:
        if not self.usage_log:
            return
        try:
            u = response.usage
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "meeting": meeting_id,
                "model": getattr(response, "model", self.model),
                "input": getattr(u, "input_tokens", None),
                "output": getattr(u, "output_tokens", None),
                "cache_read": getattr(u, "cache_read_input_tokens", None),
                "cache_write": getattr(u, "cache_creation_input_tokens", None),
                "stop": response.stop_reason,
                "request_id": getattr(response, "_request_id", None),
            }
            self.usage_log.parent.mkdir(parents=True, exist_ok=True)
            with self.usage_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - log de custo nunca derruba a análise
            log.warning("não consegui registrar uso de tokens", exc_info=True)


def _strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema do Pydantic com additionalProperties=false e todos os campos obrigatórios."""
    schema = model.model_json_schema()
    _tighten(schema)
    for d in schema.get("$defs", {}).values():
        _tighten(d)
    return schema


def _tighten(obj: dict[str, Any]) -> None:
    if obj.get("type") == "object" and "properties" in obj:
        obj["additionalProperties"] = False
        obj["required"] = list(obj["properties"].keys())
        for prop in obj["properties"].values():
            prop.pop("default", None)


def load_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise AnalysisError(f"prompt não encontrado: {path}") from exc
