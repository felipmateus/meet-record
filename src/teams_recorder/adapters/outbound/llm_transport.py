"""Generic transport for structured calls to Claude: API or headless Claude Code.

Used by the planner (phase 6). The phase 4 analyzers have the same logic embedded;
unifying them in this module is technical debt recorded in docs/REQUISITOS-E-ARQUITETURA.md.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from teams_recorder.adapters.outbound.llm_claude import FALLBACK_BETA, _strict_schema
from teams_recorder.adapters.outbound.llm_claude_cli import claude_code_env
from teams_recorder.domain import AnalysisError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class StructuredTransport(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: type[T], *, tag: str) -> T: ...


def _log_usage(path: Path | None, entry: dict[str, Any]) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        log.warning("could not record LLM usage", exc_info=True)


@dataclass
class ApiTransport:
    model: str = "claude-opus-5-5"
    effort: str = "high"
    max_tokens: int = 16000
    usage_log: Path | None = None
    client: Any = None
    use_fallbacks: bool = True
    name: str = "api"

    def _client(self) -> Any:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()
        return self.client

    def complete(self, system: str, user: str, schema: type[T], *, tag: str) -> T:
        import anthropic

        client = self._client()
        kwargs: dict[str, Any] = dict(
            model=self.model, max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": _strict_schema(schema)}},
        )
        try:
            if self.use_fallbacks:
                response = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                response = client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise AnalysisError("invalid or missing API key (ANTHROPIC_API_KEY in .env)") from exc
        except anthropic.RateLimitError as exc:
            raise AnalysisError(f"rate limit reached; try again shortly ({exc.message})") from exc
        except anthropic.APIStatusError as exc:
            raise AnalysisError(f"API error ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AnalysisError(f"no connection to the API: {exc}") from exc
        u = getattr(response, "usage", None)
        _log_usage(self.usage_log, {"tag": tag, "provider": "api", "model": getattr(response, "model", self.model),
                                    "input": getattr(u, "input_tokens", None), "output": getattr(u, "output_tokens", None),
                                    "cache_read": getattr(u, "cache_read_input_tokens", None), "cache_write": getattr(u, "cache_creation_input_tokens", None),
                                    "stop": response.stop_reason, "request_id": getattr(response, "_request_id", None)})
        if response.stop_reason == "refusal":
            raise AnalysisError(f"the API refused the request ({tag})")
        if response.stop_reason == "max_tokens":
            raise AnalysisError(f"response truncated at {self.max_tokens} tokens; increase llm.max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AnalysisError("response has no text block")
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            raise AnalysisError(f"output does not match the schema: {exc.errors()[:3]}") from exc


@dataclass
class ClaudeCodeTransport:
    model: str = "opus"
    effort: str = "high"
    claude_bin: str = "claude"
    timeout: float = 900.0
    usage_log: Path | None = None
    name: str = "claude-code"

    def command(self, system: str, schema: type[BaseModel]) -> list[str]:
        return [
            self.claude_bin, "-p", "--output-format", "json", "--no-session-persistence", "--restricted", "--tools", "",
            "--model", self.model, "--effort", self.effort, "--system-prompt", system,
            "--json-schema", json.dumps(_strict_schema(schema), ensure_ascii=False),
        ]

    def complete(self, system: str, user: str, schema: type[T], *, tag: str) -> T:
        if shutil.which(self.claude_bin) is None and not Path(self.claude_bin).exists():
            raise AnalysisError(f"Claude Code not found ({self.claude_bin})")
        try:
            result = subprocess.run(self.command(system, schema), input=user, capture_output=True, text=True, timeout=self.timeout, check=False, env=claude_code_env())
        except subprocess.TimeoutExpired as exc:
            raise AnalysisError(f"Claude Code did not respond within {self.timeout:.0f}s") from exc
        if result.returncode != 0 and not result.stdout.strip():
            raise AnalysisError(f"Claude Code failed (code {result.returncode}): {result.stderr.strip()[-500:]}")
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"Claude Code response is not JSON: {result.stdout[:200]!r}") from exc
        usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
        model_usage = envelope.get("modelUsage") if isinstance(envelope.get("modelUsage"), dict) else {}
        _log_usage(self.usage_log, {"tag": tag, "provider": "claude-code", "model": ",".join(model_usage.keys()) or self.model,
                                    "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
                                    "cache_read": usage.get("cache_read_input_tokens"), "cache_write": usage.get("cache_creation_input_tokens"),
                                    "cost_usd_equiv": envelope.get("total_cost_usd"), "stop": envelope.get("subtype"), "session_id": envelope.get("session_id")})
        if envelope.get("is_error") or envelope.get("subtype") != "success":
            raise AnalysisError(f"Claude Code returned an error ({envelope.get('subtype')}): {str(envelope.get('result', ''))[:300]}")
        data = envelope.get("structured_output")
        if data is None:
            try:
                data = json.loads(envelope.get("result") or "")
            except json.JSONDecodeError as exc:
                raise AnalysisError("Claude Code did not return structured output") from exc
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise AnalysisError(f"output does not match the schema: {exc.errors()[:3]}") from exc
