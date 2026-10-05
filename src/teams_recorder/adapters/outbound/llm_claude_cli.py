"""MeetingAnalyzer via Claude Code em modo headless (`claude -p`).

Alternativa ao adaptador de API: usa a assinatura do Claude Code em vez de créditos de
API. Mesmo prompt, mesmo esquema de saída e mesma conversão para o domínio do
`llm_claude.py`; muda só o transporte (subprocesso em vez de HTTP).

Limitações em relação à API: sem fallback de recusa, sem controle de cache, depende de
sessão do Claude Code logada no Mac (inclusive quando rodar pelo launchd).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from teams_recorder.adapters.outbound.llm_claude import (
    AnalysisOut,
    _strict_schema,
    build_user_message,
    load_prompt,
    to_domain,
)
from teams_recorder.domain import Analysis, AnalysisError, Meeting, Transcript

log = logging.getLogger(__name__)


@dataclass
class ClaudeCliAnalyzer:
    system_prompt: str | None = None
    prompt_path: Path | None = None
    model: str = "opus"
    effort: str = "high"
    claude_bin: str = "claude"
    timeout: float = 900.0
    usage_log: Path | None = None

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise AnalysisError("ClaudeCliAnalyzer sem prompt de sistema (system_prompt ou prompt_path)")
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def command(self) -> list[str]:
        return [
            self.claude_bin,
            "-p",
            "--output-format", "json",
            "--no-session-persistence",
            "--restricted",            # remove ferramentas que executam código
            "--tools", "",             # nenhuma ferramenta: só texto → JSON
            "--model", self.model,
            "--effort", self.effort,
            "--system-prompt", self._system(),
            "--json-schema", json.dumps(_strict_schema(AnalysisOut), ensure_ascii=False),
        ]

    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis:
        if not transcript.text.strip():
            return Analysis(meeting_id=meeting.id, summary="Transcrição vazia: nenhuma fala reconhecida.")
        if shutil.which(self.claude_bin) is None and not Path(self.claude_bin).exists():
            raise AnalysisError(f"Claude Code não encontrado ({self.claude_bin}); instale-o ou use llm.provider = \"api\"")
        envelope = self._run(build_user_message(transcript, meeting))
        self._log_usage(meeting.id, envelope)
        if envelope.get("is_error") or envelope.get("subtype") != "success":
            raise AnalysisError(f"Claude Code retornou erro ({envelope.get('subtype')}): {str(envelope.get('result', ''))[:300]}")
        data = envelope.get("structured_output")
        if data is None:
            # fallback: alguns erros de esquema deixam só o texto em `result`
            try:
                data = json.loads(envelope.get("result") or "")
            except json.JSONDecodeError as exc:
                raise AnalysisError("Claude Code não devolveu saída estruturada") from exc
        try:
            out = AnalysisOut.model_validate(data)
        except ValidationError as exc:
            raise AnalysisError(f"saída fora do esquema: {exc.errors()[:3]}") from exc
        return to_domain(out, meeting)

    def _run(self, user_message: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                self.command(), input=user_message, capture_output=True, text=True, timeout=self.timeout, check=False,
            )
        except FileNotFoundError as exc:
            raise AnalysisError(f"Claude Code não encontrado ({self.claude_bin})") from exc
        except subprocess.TimeoutExpired as exc:
            raise AnalysisError(f"Claude Code não respondeu em {self.timeout:.0f}s") from exc
        if result.returncode != 0 and not result.stdout.strip():
            raise AnalysisError(f"Claude Code falhou (código {result.returncode}): {result.stderr.strip()[-500:]}")
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"resposta do Claude Code não é JSON: {result.stdout[:200]!r}") from exc
        if not isinstance(envelope, dict):
            raise AnalysisError("resposta do Claude Code com formato inesperado")
        return envelope

    def _log_usage(self, meeting_id: str, envelope: dict[str, Any]) -> None:
        if not self.usage_log:
            return
        try:
            usage = envelope.get("usage") or {}
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "meeting": meeting_id,
                "provider": "claude-code",
                "model": ",".join((envelope.get("modelUsage") or {}).keys()) or self.model,
                "input": usage.get("input_tokens"),
                "output": usage.get("output_tokens"),
                "cache_read": usage.get("cache_read_input_tokens"),
                "cache_write": usage.get("cache_creation_input_tokens"),
                "cost_usd_equiv": envelope.get("total_cost_usd"),
                "stop": envelope.get("subtype"),
                "session_id": envelope.get("session_id"),
            }
            self.usage_log.parent.mkdir(parents=True, exist_ok=True)
            with self.usage_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            log.warning("não consegui registrar uso do Claude Code", exc_info=True)
