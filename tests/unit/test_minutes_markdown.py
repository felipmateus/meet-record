"""minutes.md rendering from a structured analysis (skill meeting-notes structure)."""
import json
from datetime import datetime
from pathlib import Path

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
from teams_recorder.domain import Analysis, Meeting

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _meeting(title=None):
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title=title)
    m.ended_at = datetime(2026, 10, 6, 14, 45, 0)
    return m


def _analysis():
    return codec.analysis_from_dict(json.loads((FIXTURES / "sample_analysis_v2.json").read_text()))


def test_full_minutes_structure():
    md = MarkdownMinutesRenderer("Felipe").render(_meeting(), _analysis())
    lines = md.splitlines()
    assert lines[0] == "# Ata: Revisão da sprint de integração"
    assert "📅 **Data:** 06/10/2026, 14:00–14:45 (45 min)" in md
    assert "👥 **Participantes:** Felipe, Mariana" in md
    assert "🏷️ **Tipo:** Revisão de projeto" in md
    assert "🎯 **Objetivo:** Definir as entregas" in md
    # sections in the skill's order
    order = ["### 📋 Resumo", "### 💡 Tópicos", "### ✅ Decisões", "### 📌 Ações", "### ⚠️ Riscos e bloqueios", "### ❓ Perguntas em aberto", "### 🔜 Próximos passos"]
    assert [md.index(h) for h in order] == sorted(md.index(h) for h in order)
    assert "1. **Relatório de integração**" in md and "   - Depende do escopo do SAP" in md
    assert "- Relatório de integração será entregue até quarta-feira. `[00:00:03]`" in md
    # action table: user's name, Brazilian date, priority label, timestamp; unassigned flagged
    assert "| 1 | Enviar relatório de integração | Felipe (você) | 07/10/2026 | 🔴 Alta | 00:00:03 |" in md
    assert "| 2 | Agendar reunião com o cliente | Felipe (você) | — | — | 00:00:09 |" in md
    assert "| 3 | Confirmar o escopo do SAP | ⚠️ sem responsável | — | 🟡 Média | — |" in md
    assert "- Relatório de integração — 07/10/2026 · Felipe (você)" in md
    assert md.rstrip().endswith("antes de compartilhar._")


def test_empty_sections_are_omitted_and_title_falls_back():
    a = Analysis(meeting_id="m", summary="Teste de áudio, sem pauta.")
    md = MarkdownMinutesRenderer().render(_meeting(title="Daily"), a)
    assert md.startswith("# Ata: Daily")
    assert "Nenhuma ação registrada." in md and "não identificados" in md and "🏷️ **Tipo:** Reunião" in md
    for header in ("Tópicos", "Decisões", "Riscos", "Perguntas", "Próximos passos", "Objetivo"):
        assert header not in md
    assert MarkdownMinutesRenderer().render(_meeting(), a).startswith(f"# Ata: {_meeting().id}")


def test_owner_without_user_name_and_pipes_escaped():
    a = _analysis()
    a.my_actions[0].description = "Enviar A | B"
    md = MarkdownMinutesRenderer().render(_meeting(), a)
    assert "| 1 | Enviar A / B | você |" in md


def test_short_meeting_shows_under_a_minute():
    m = Meeting.start(datetime(2026, 10, 5, 18, 54, 22)); m.ended_at = datetime(2026, 10, 5, 18, 55, 0)
    assert "18:54–18:55 (<1 min)" in MarkdownMinutesRenderer().render(m, Analysis(meeting_id="m", summary="s"))


def test_degraded_transcript_puts_a_banner_under_the_title():
    from teams_recorder.domain import TranscriptHealth
    health = TranscriptHealth(0.668, 28, 86, True, ((0, 14), (15, 59)))
    lines = MarkdownMinutesRenderer().render(_meeting(), _analysis(), health).splitlines()
    assert lines[0] == "# Ata: Revisão da sprint de integração" and lines[1] == ""
    assert lines[2].startswith("> ⚠️ **Transcrição degradada:** 67% dos trechos são uma mesma frase repetida")
    assert ", e não há texto em 00:00:00–00:14:00, 00:15:00–00:59:00." in lines[2]
    assert lines[3] == "" and lines[4].startswith("📅 **Data:**")


def test_degraded_without_gaps_and_healthy_transcripts():
    from teams_recorder.domain import TranscriptHealth
    md = MarkdownMinutesRenderer().render(_meeting(), _analysis(), TranscriptHealth(0.2, 45, 45, True))
    assert "20% dos trechos" in md and "não há texto" not in md
    healthy = MarkdownMinutesRenderer().render(_meeting(), _analysis(), TranscriptHealth(0.0, 45, 45, False))
    assert "Transcrição degradada" not in healthy
    assert healthy == MarkdownMinutesRenderer().render(_meeting(), _analysis())   # same as before the check existed


def test_a_track_recorded_at_the_wrong_rate_puts_its_own_banner_under_the_title():
    from teams_recorder.domain import TranscriptHealth
    health = TranscriptHealth(0.0, 12, 12, False, rate_mismatch=True, short_padding_share=0.669)
    lines = MarkdownMinutesRenderer().render(_meeting(), _analysis(), health).splitlines()
    assert lines[2].startswith("> ⚠️ **Áudio do Teams gravado com a taxa errada:** 67% da faixa do Teams")
    assert lines[3] == "" and lines[4].startswith("📅 **Data:**")
    both = MarkdownMinutesRenderer().render(_meeting(), _analysis(), TranscriptHealth(0.3, 5, 12, True, rate_mismatch=True, short_padding_share=0.5))
    assert both.index("Transcrição degradada") < both.index("taxa errada")
