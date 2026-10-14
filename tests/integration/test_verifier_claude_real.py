"""Real claim verification via headless Claude Code (Sonnet, medium effort, as the PRD decided).
Opt-in: TREC_REAL_CLAUDE_CLI=1 (uses the subscription)."""
import os
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.llm_transport import ClaudeCodeTransport
from teams_recorder.adapters.outbound.verifier_claude import ClaudeClaimVerifier
from teams_recorder.config import load_settings
from teams_recorder.constants import Files
from teams_recorder.domain import Action, Analysis, ClaimKind, ClaimRef, Decision, Meeting, Segment, Transcript, VerificationStatus

ready = os.environ.get("TREC_REAL_CLAUDE_CLI") == "1" and shutil.which("claude")
pytestmark = [pytest.mark.slow, pytest.mark.skipif(not ready, reason="set TREC_REAL_CLAUDE_CLI=1 (requires a logged-in Claude Code)")]


def test_real_verifier_confirms_what_was_said_and_flags_an_invented_decision_and_a_wrong_owner(tmp_path: Path):
    # Portuguese on purpose: the meetings are in Brazilian Portuguese
    meeting = Meeting.start(datetime(2026, 10, 12, 9, 0, 0))
    transcript = Transcript([
        Segment(0, 4, "Bom dia, Ana. Bom dia, Bruno."),
        Segment(5, 12, "Então fica decidido: vamos usar o Mapbox no aplicativo."),
        Segment(13, 20, "Bruno, você manda o cronograma do piloto até quarta-feira?"),
        Segment(21, 25, "Mando sim, pode deixar."),
    ])
    analysis = Analysis(
        meeting_id=meeting.id, summary="s",
        decisions=[Decision("Usar o Mapbox no aplicativo", "00:00:05"), Decision("Cancelar o piloto em Pelotas")],
        others_actions=[Action("Enviar o cronograma do piloto", "Ana", meeting.id, due=date(2026, 10, 14), at="00:00:13", id="a1")],
        participants=["Ana", "Bruno"],
    )
    settings = load_settings(Path(__file__).resolve().parents[2])
    verifier = ClaudeClaimVerifier(ClaudeCodeTransport(model="sonnet", effort="medium", usage_log=tmp_path / "usage.jsonl"),
                                   prompt_path=settings.prompts_dir / Files.VERIFY_PROMPT, user_name="Felipe")

    result = verifier.verify(meeting, analysis, transcript)

    assert result[ClaimRef(ClaimKind.DECISION, "0")].status is VerificationStatus.CONFIRMED, result
    assert result[ClaimRef(ClaimKind.DECISION, "1")].status is VerificationStatus.UNCONFIRMED   # nobody said it
    assert result[ClaimRef(ClaimKind.ACTION, "a1")].status is VerificationStatus.UNCONFIRMED    # Bruno took it, not Ana
    assert all(v.reason for v in result.values())
    assert (tmp_path / "usage.jsonl").exists()   # FR8: the call is logged like the others
