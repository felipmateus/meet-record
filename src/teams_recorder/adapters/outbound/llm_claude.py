"""MeetingAnalyzer via the Claude API (official `anthropic` SDK).

Design:
- The output schema (Pydantic) lives here and is converted to the domain; the domain
  knows nothing about the API.
- The system prompt is fixed (prompts/analyze_system.md) and marked for caching; the
  variable content (meeting metadata and transcript) goes in the user message.
- Server-side fallback is enabled by default: a one-off refusal by the safety
  classifiers re-runs the request on another model instead of taking the pipeline down.
- Every call records token usage in a JSONL file for cost control (R7).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:  # the SDK is imported on demand: it is large and only analyze needs it
    import anthropic

from teams_recorder.domain import Action, Analysis, AnalysisError, Deadline, Decision, Meeting, Transcript

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MIN_WORDS = 20  # below this an LLM call is not worth it (silence, noise, whisper hallucination)


def trivial_analysis(transcript: Transcript, meeting: Meeting, min_words: int = MIN_WORDS) -> Analysis | None:
    """Local analysis for empty or too-short transcripts; None when it is worth analyzing."""
    words = len(transcript.text.split())
    if words == 0:
        return Analysis(meeting_id=meeting.id, summary="Empty transcript: no speech recognized.")
    if words < min_words:
        return Analysis(
            meeting_id=meeting.id,
            summary=f"Transcript too short ({words} words) to analyze: \"{transcript.text.strip()[:120]}\"",
        )
    return None


# --- output schema ----------------------------------------------------------
class ActionOut(BaseModel):
    description: str = Field(description="Task, starting with a verb in the infinitive")
    owner: str = Field(description="Owner; 'usuário' for the recording owner; 'indefinido' when unknown")
    due: str | None = Field(default=None, description="Due date in ISO format (YYYY-MM-DD) or null")


class DeadlineOut(BaseModel):
    what: str
    when: str | None = Field(default=None, description="ISO date or null")
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
        f"Meeting date: {meeting.started_at.date().isoformat()} ({_weekday(meeting.started_at)})",
        f"Start: {meeting.started_at.strftime('%H:%M')}",
    ]
    if meeting.title:
        header.append(f"Title: {meeting.title}")
    if meeting.duration_seconds:
        header.append(f"Duration: {int(meeting.duration_seconds // 60)} min")
    return "\n".join(header) + "\n\nTranscript (with timestamps):\n\n" + transcript.as_timestamped_text()


def _weekday(dt: datetime) -> str:
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][dt.weekday()]


# --- adapter ----------------------------------------------------------------
@dataclass
class ClaudeAnalyzer:
    system_prompt: str | None = None            # ready-made text (tests) ...
    prompt_path: Path | None = None             # ... or a file loaded on the first analysis
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
                raise AnalysisError("ClaudeAnalyzer has no system prompt (system_prompt or prompt_path)")
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def _client(self) -> Any:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment (.env loaded in config)
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
            raise AnalysisError(f"the API refused to analyze meeting {meeting.id}{why}")
        if response.stop_reason == "max_tokens":
            raise AnalysisError(f"response truncated at {self.max_tokens} tokens; increase llm.max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AnalysisError("response has no text block")
        try:
            out = AnalysisOut.model_validate_json(text)
        except ValidationError as exc:
            raise AnalysisError(f"output does not match the schema: {exc.errors()[:3]}") from exc
        return to_domain(out, meeting)

    # The only function that knows the request shape; structured output guarantees JSON valid
    # against the schema, and Pydantic validates it again on our side.
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
            raise AnalysisError("invalid or missing API key (ANTHROPIC_API_KEY in .env)") from exc
        except anthropic.RateLimitError as exc:
            raise AnalysisError(f"rate limit reached; try again shortly ({exc.message})") from exc
        except anthropic.APIStatusError as exc:
            raise AnalysisError(f"API error ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AnalysisError(f"no connection to the API: {exc}") from exc

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
        except Exception:  # noqa: BLE001 - cost logging never takes the analysis down
            log.warning("could not record token usage", exc_info=True)


def _strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON Schema with additionalProperties=false and every field required."""
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
        raise AnalysisError(f"prompt not found: {path}") from exc
