"""MeetingAnalyzer via Claude Code in headless mode (`claude -p`).

Alternative to the API adapter: uses the Claude Code subscription instead of API
credits. Same prompt, same output schema and same domain conversion as
`llm_claude.py`; only the transport changes (subprocess instead of HTTP).

Limitations compared to the API: no refusal fallback, no cache control, depends on a
logged-in Claude Code session on the Mac (including when running under launchd).
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
from typing import Any

from pydantic import ValidationError

from teams_recorder.adapters.outbound.llm_claude import (
    MIN_WORDS,
    AnalysisOut,
    _strict_schema,
    build_user_message,
    load_prompt,
    to_domain,
    trivial_analysis,
)
from teams_recorder.domain import Analysis, AnalysisError, Meeting, Transcript

log = logging.getLogger(__name__)


def claude_code_env() -> dict[str, str]:
    """Environment for the `claude` subprocess: without ANTHROPIC_* variables.

    With ANTHROPIC_API_KEY in the environment (the .env is loaded into os.environ by
    config), Claude Code starts billing the API instead of using the subscription — that
    is what broke the analysis of the first real meeting with the claude-code provider.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}


@dataclass
class ClaudeCliAnalyzer:
    system_prompt: str | None = None
    prompt_path: Path | None = None
    model: str = "opus"
    effort: str = "high"
    claude_bin: str = "claude"
    timeout: float = 900.0
    usage_log: Path | None = None
    min_words: int = MIN_WORDS

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise AnalysisError("ClaudeCliAnalyzer has no system prompt (system_prompt or prompt_path)")
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def command(self) -> list[str]:
        return [
            self.claude_bin,
            "-p",
            "--output-format", "json",
            "--no-session-persistence",
            "--restricted",            # removes tools that execute code
            "--tools", "",             # no tools: text only → JSON
            "--model", self.model,
            "--effort", self.effort,
            "--system-prompt", self._system(),
            "--json-schema", json.dumps(_strict_schema(AnalysisOut), ensure_ascii=False),
        ]

    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis:
        trivial = trivial_analysis(transcript, meeting, self.min_words)
        if trivial is not None:
            return trivial
        if shutil.which(self.claude_bin) is None and not Path(self.claude_bin).exists():
            raise AnalysisError(f"Claude Code not found ({self.claude_bin}); install it or set llm.provider = \"api\"")
        envelope = self._run(build_user_message(transcript, meeting))
        self._log_usage(meeting.id, envelope)
        if envelope.get("is_error") or envelope.get("subtype") != "success":
            raise AnalysisError(f"Claude Code returned an error ({envelope.get('subtype')}): {str(envelope.get('result', ''))[:300]}")
        data = envelope.get("structured_output")
        if data is None:
            # fallback: some schema errors leave only the text in `result`
            try:
                data = json.loads(envelope.get("result") or "")
            except json.JSONDecodeError as exc:
                raise AnalysisError("Claude Code did not return structured output") from exc
        try:
            out = AnalysisOut.model_validate(data)
        except ValidationError as exc:
            raise AnalysisError(f"output does not match the schema: {exc.errors()[:3]}") from exc
        return to_domain(out, meeting)

    def _run(self, user_message: str) -> dict[str, Any]:
        try:
            result = subprocess.run(
                self.command(), input=user_message, capture_output=True, text=True, timeout=self.timeout, check=False,
                env=claude_code_env(),
            )
        except FileNotFoundError as exc:
            raise AnalysisError(f"Claude Code not found ({self.claude_bin})") from exc
        except subprocess.TimeoutExpired as exc:
            raise AnalysisError(f"Claude Code did not respond within {self.timeout:.0f}s") from exc
        if result.returncode != 0 and not result.stdout.strip():
            raise AnalysisError(f"Claude Code failed (code {result.returncode}): {result.stderr.strip()[-500:]}")
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"Claude Code response is not JSON: {result.stdout[:200]!r}") from exc
        if not isinstance(envelope, dict):
            raise AnalysisError("Claude Code response has an unexpected format")
        return envelope

    def _log_usage(self, meeting_id: str, envelope: dict[str, Any]) -> None:
        if not self.usage_log:
            return
        try:
            usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
            model_usage = envelope.get("modelUsage") if isinstance(envelope.get("modelUsage"), dict) else {}
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "meeting": meeting_id,
                "provider": "claude-code",
                "model": ",".join(model_usage.keys()) or self.model,
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
            log.warning("could not record Claude Code usage", exc_info=True)
