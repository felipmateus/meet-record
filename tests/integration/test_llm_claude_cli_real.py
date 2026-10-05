"""Real analysis via headless Claude Code. Opt-in: TREC_REAL_CLAUDE_CLI=1 (uses the subscription)."""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.llm_claude import ClaudeAnalyzer
from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
from teams_recorder.config import load_settings

PROJECT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ready = os.environ.get("TREC_REAL_CLAUDE_CLI") == "1" and shutil.which("claude")

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not ready, reason="set TREC_REAL_CLAUDE_CLI=1 (requires a logged-in Claude Code)")]


def test_real_cli_analysis_extracts_actions(tmp_path: Path):
    from teams_recorder.domain import Meeting

    settings = load_settings(PROJECT)
    transcript = codec.transcript_from_dict(json.loads((FIXTURES / "sample_transcript.json").read_text()))
    meeting = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title="Revisão da sprint")
    meeting.ended_at = datetime(2026, 10, 6, 14, 30, 0)

    analysis = ClaudeAnalyzer(
        ClaudeCodeTransport(model=settings.llm_cli_model, effort="medium", usage_log=tmp_path / "usage.jsonl"),
        prompt_path=settings.prompts_dir / "analyze_system.md",
    ).analyze(transcript, meeting)

    assert analysis.summary
    descriptions = " ".join(a.description.lower() for a in analysis.my_actions)
    assert "relatório" in descriptions
    # the sample meeting is on a Tuesday (2026-10-06); "até quarta-feira" (by Wednesday) = 2026-10-07
    assert any(a.due and a.due.isoformat() == "2026-10-07" for a in analysis.my_actions), analysis.my_actions


def test_real_cli_rich_meeting_fills_new_fields(tmp_path: Path):
    """Richer meeting: title, type, participants, topics, risks, timestamps and priority."""
    from teams_recorder.adapters.outbound.llm_claude import ClaudeAnalyzer
    from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
    from teams_recorder.domain import Meeting, Priority

    settings = load_settings(PROJECT)
    transcript = codec.transcript_from_dict(json.loads((FIXTURES / "sample_meeting_rich.json").read_text()))
    meeting = Meeting.start(datetime(2026, 10, 6, 14, 0, 0))
    analysis = ClaudeAnalyzer(
        ClaudeCodeTransport(model=settings.llm_cli_model, effort="medium"),
        prompt_path=settings.prompts_dir / "analyze_system.md", user_name="Felipe",
    ).analyze(transcript, meeting)

    assert analysis.title and analysis.purpose
    assert {"Mariana", "Rodrigo"} <= set(analysis.participants)
    assert analysis.topics and analysis.risks
    assert all(a.at for a in analysis.my_actions) and all(d.at for d in analysis.decisions)
    assert any(a.priority is Priority.HIGH for a in analysis.my_actions)  # "É urgente"
    assert not any("nuvem" in d.text.lower() for d in analysis.decisions)  # "talvez... pensar depois" is not a decision
