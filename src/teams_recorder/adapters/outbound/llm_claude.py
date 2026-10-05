"""MeetingAnalyzer backed by a StructuredTransport (Claude API or Claude Code headless).

The analyzer only builds the user message, short-circuits trivial transcripts and maps
the structured output to the domain. Request shape, error mapping and usage logging live
in `llm_transport.py`; the output schema and prompt helpers in `llm_schema.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from teams_recorder.adapters.outbound.llm_schema import (  # noqa: F401 - re-exported for callers/tests
    MIN_WORDS,
    ActionOut,
    AnalysisOut,
    DeadlineOut,
    build_user_message,
    load_prompt,
    strict_schema,
    to_domain,
    trivial_analysis,
)
from teams_recorder.adapters.outbound.llm_transport import FALLBACK_BETA, StructuredTransport  # noqa: F401
from teams_recorder.domain import Analysis, AnalysisError, Meeting, Transcript


@dataclass
class ClaudeAnalyzer:
    transport: StructuredTransport
    prompt_path: Path | None = None      # loaded on first use ...
    system_prompt: str | None = None     # ... or given directly (tests)
    min_words: int = MIN_WORDS

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise AnalysisError("ClaudeAnalyzer has no system prompt (system_prompt or prompt_path)")
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis:
        trivial = trivial_analysis(transcript, meeting, self.min_words)
        if trivial is not None:
            return trivial
        out = self.transport.complete(
            self._system(), build_user_message(transcript, meeting), AnalysisOut,
            tag=f"analyze:{meeting.id}", extra={"meeting": meeting.id},
        )
        return to_domain(out, meeting)
