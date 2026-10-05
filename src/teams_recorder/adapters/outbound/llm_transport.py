"""Structured LLM calls over the Claude API or Claude Code headless.

Both transports take a system prompt, a user message and a Pydantic schema and return
a validated instance. They are the single place that knows the request shape, error
mapping and usage logging; the analyzer and the planner only build messages and map
results to the domain.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from teams_recorder.adapters.outbound.llm_schema import strict_schema
from teams_recorder.constants import Bin, Effort, Env, Llm, LlmProvider
from teams_recorder.domain import AnalysisError
from teams_recorder.messages import Err, Log

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = Llm.FALLBACK_BETA  # module alias kept for callers and tests


class StructuredTransport(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: type[T], *, tag: str, extra: dict[str, Any] | None = None) -> T: ...


def claude_code_env() -> dict[str, str]:
    """Environment for the `claude` subprocess: no ANTHROPIC_* variables.

    With ANTHROPIC_API_KEY in the environment (config loads .env into os.environ), Claude
    Code bills the API instead of using the subscription — that is what broke the analysis
    of the first real meeting with the claude-code provider.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith(Env.ANTHROPIC_PREFIX)}


def _log_usage(path: Path | None, entry: dict[str, Any]) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - usage logging never breaks a call
        log.warning(Log.USAGE_LOG_FAILED, exc_info=True)


def _validate(schema: type[T], data: Any, *, from_json: bool) -> T:
    try:
        return schema.model_validate_json(data) if from_json else schema.model_validate(data)
    except ValidationError as exc:
        raise AnalysisError(Err.SCHEMA_MISMATCH.format(errors=exc.errors()[:3])) from exc


@dataclass
class ApiTransport:
    """Claude API via the official SDK: structured output, cached system prompt, server-side fallback."""

    model: str = Llm.DEFAULT_API_MODEL
    effort: str = Effort.HIGH  # Effort is a StrEnum, so plain strings are accepted too
    max_tokens: int = Llm.DEFAULT_MAX_TOKENS
    usage_log: Path | None = None
    client: Any = None
    use_fallbacks: bool = True
    name: str = LlmProvider.API

    def _client(self) -> Any:
        if self.client is None:
            import anthropic  # lazy: ~1,900 modules; a cold import took 12 minutes on the dev Mac

            self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment (.env loaded by config)
        return self.client

    def complete(self, system: str, user: str, schema: type[T], *, tag: str, extra: dict[str, Any] | None = None) -> T:
        import anthropic

        client = self._client()
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": strict_schema(schema)}},
        )
        try:
            if self.use_fallbacks:
                response = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                response = client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise AnalysisError(Err.API_KEY_INVALID) from exc
        except anthropic.RateLimitError as exc:
            raise AnalysisError(Err.RATE_LIMIT.format(message=exc.message)) from exc
        except anthropic.APIStatusError as exc:
            raise AnalysisError(Err.API_ERROR.format(status=exc.status_code, message=exc.message)) from exc
        except anthropic.APIConnectionError as exc:
            raise AnalysisError(Err.NO_CONNECTION.format(error=exc)) from exc

        u = getattr(response, "usage", None)
        _log_usage(self.usage_log, {
            "tag": tag, **(extra or {}), "provider": self.name, "model": getattr(response, "model", self.model),
            "input": getattr(u, "input_tokens", None), "output": getattr(u, "output_tokens", None),
            "cache_read": getattr(u, "cache_read_input_tokens", None), "cache_write": getattr(u, "cache_creation_input_tokens", None),
            "stop": response.stop_reason, "request_id": getattr(response, "_request_id", None),
        })
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            why = Err.REFUSED_WHY.format(category=details.category, explanation=details.explanation) if details else ""
            raise AnalysisError(Err.REFUSED.format(tag=tag, why=why))
        if response.stop_reason == "max_tokens":
            raise AnalysisError(Err.TRUNCATED.format(max_tokens=self.max_tokens))
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AnalysisError(Err.NO_TEXT_BLOCK)
        return _validate(schema, text, from_json=True)


@dataclass
class ClaudeCodeTransport:
    """Claude Code in headless mode (`claude -p`): uses the user's subscription instead of API credit.

    Limitations versus the API: no refusal fallback, cache managed by Claude Code, and it
    depends on a logged-in Claude Code session on the Mac (relevant for the launchd daemon).
    """

    model: str = Llm.DEFAULT_CLI_MODEL
    effort: str = Effort.HIGH
    claude_bin: str = Bin.CLAUDE
    timeout: float = Llm.CLAUDE_CODE_TIMEOUT
    usage_log: Path | None = None
    name: str = LlmProvider.CLAUDE_CODE

    def command(self, system: str, schema: type[BaseModel]) -> list[str]:
        return [
            self.claude_bin, "-p", "--output-format", "json", "--no-session-persistence",
            "--restricted",            # removes the tools that run commands or code
            "--tools", "",             # no tools at all: text in, JSON out
            "--model", self.model, "--effort", self.effort,
            "--system-prompt", system,
            "--json-schema", json.dumps(strict_schema(schema), ensure_ascii=False),
        ]

    def complete(self, system: str, user: str, schema: type[T], *, tag: str, extra: dict[str, Any] | None = None) -> T:
        if shutil.which(self.claude_bin) is None and not Path(self.claude_bin).exists():
            raise AnalysisError(Err.CLAUDE_CODE_MISSING_HINT.format(binary=self.claude_bin))
        try:
            result = subprocess.run(
                self.command(system, schema), input=user, capture_output=True, text=True,
                timeout=self.timeout, check=False, env=claude_code_env(),
            )
        except FileNotFoundError as exc:
            raise AnalysisError(Err.CLAUDE_CODE_MISSING.format(binary=self.claude_bin)) from exc
        except subprocess.TimeoutExpired as exc:
            raise AnalysisError(Err.CLAUDE_CODE_TIMEOUT.format(seconds=self.timeout)) from exc
        if result.returncode != 0 and not result.stdout.strip():
            raise AnalysisError(Err.CLAUDE_CODE_FAILED.format(code=result.returncode, tail=result.stderr.strip()[-500:]))
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AnalysisError(Err.CLAUDE_CODE_NOT_JSON.format(text=result.stdout[:200])) from exc
        if not isinstance(envelope, dict):
            raise AnalysisError(Err.CLAUDE_CODE_BAD_FORMAT)

        raw_usage, raw_model_usage = envelope.get("usage"), envelope.get("modelUsage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        model_usage: dict[str, Any] = raw_model_usage if isinstance(raw_model_usage, dict) else {}
        _log_usage(self.usage_log, {
            "tag": tag, **(extra or {}), "provider": self.name, "model": ",".join(model_usage.keys()) or self.model,
            "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
            "cache_read": usage.get("cache_read_input_tokens"), "cache_write": usage.get("cache_creation_input_tokens"),
            "cost_usd_equiv": envelope.get("total_cost_usd"), "stop": envelope.get("subtype"), "session_id": envelope.get("session_id"),
        })
        if envelope.get("is_error") or envelope.get("subtype") != "success":
            raise AnalysisError(Err.CLAUDE_CODE_ERROR.format(subtype=envelope.get("subtype"), result=str(envelope.get("result", ""))[:300]))
        data = envelope.get("structured_output")
        if data is None:
            # some schema failures leave only the text in `result`
            try:
                data = json.loads(envelope.get("result") or "")
            except json.JSONDecodeError as exc:
                raise AnalysisError(Err.CLAUDE_CODE_NO_STRUCTURED) from exc
        return _validate(schema, data, from_json=False)
