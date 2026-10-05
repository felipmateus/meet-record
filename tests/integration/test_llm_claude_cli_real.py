"""Real analysis via headless Claude Code. Opt-in: TREC_REAL_CLAUDE_CLI=1 (uses the subscription)."""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.llm_claude_cli import ClaudeCliAnalyzer
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

    analysis = ClaudeCliAnalyzer(
        prompt_path=settings.prompts_dir / "analyze_system.md", model=settings.llm_cli_model, effort="medium",
        usage_log=tmp_path / "usage.jsonl",
    ).analyze(transcript, meeting)

    assert analysis.summary
    descriptions = " ".join(a.description.lower() for a in analysis.my_actions)
    assert "relatório" in descriptions
    # the sample meeting is on a Tuesday (2026-10-06); "até quarta-feira" (by Wednesday) = 2026-10-07
    assert any(a.due and a.due.isoformat() == "2026-10-07" for a in analysis.my_actions), analysis.my_actions
