"""Real analysis against the Claude API. Opt-in: TREC_REAL_CLAUDE=1 (costs a few cents)."""
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.llm_claude import ClaudeAnalyzer, load_prompt
from teams_recorder.config import load_settings
from teams_recorder.domain import Meeting

PROJECT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_settings = load_settings(PROJECT)
ready = os.environ.get("TREC_REAL_CLAUDE") == "1" and _settings.has_api_key

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not ready, reason="set TREC_REAL_CLAUDE=1 and ANTHROPIC_API_KEY")]


def test_real_analysis_extracts_actions(tmp_path: Path):
    transcript = codec.transcript_from_dict(json.loads((FIXTURES / "sample_transcript.json").read_text()))
    meeting = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title="Revisão da sprint")
    meeting.ended_at = datetime(2026, 10, 6, 14, 30, 0)
    analyzer = ClaudeAnalyzer(
        system_prompt=load_prompt(_settings.prompts_dir / "analyze_system.md"),
        model=_settings.llm_model, effort="medium", usage_log=tmp_path / "usage.jsonl",
    )

    analysis = analyzer.analyze(transcript, meeting)

    assert analysis.summary
    descriptions = " ".join(a.description.lower() for a in analysis.my_actions)
    assert "relatório" in descriptions
    # the sample meeting is on a Tuesday (2026-10-06); "até quarta-feira" (by Wednesday) = 2026-10-07
    assert any(a.due and a.due.isoformat() == "2026-10-07" for a in analysis.my_actions), analysis.my_actions
    assert (tmp_path / "usage.jsonl").exists()
