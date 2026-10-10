from datetime import date

from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.domain import Action, Priority, SkippedAction, StoryDrafts, UserStory

DAY = date(2026, 10, 9)


def test_renders_stories_sources_and_skipped_actions():
    actions = [
        Action("Criar exportação de horas", "usuário", "2026-10-09_10-00-00", id="a1", at="00:03:10"),
        Action("Mandar e-mail para o cliente", "usuário", "2026-10-09_10-00-00", id="a3"),
    ]
    story = UserStory(
        "Exportar horas por projeto", "Como gestor, quero exportar, para fechar o mês.",
        acceptance_criteria=["Dado x, quando y, então z"], details="**Contexto:** fechamento",
        open_questions=["Qual formato?"], source_action_ids=["a1"], source_meetings=["2026-10-09_10-00-00"],
        priority=Priority.HIGH, due=date(2026, 10, 12),
    )
    md = MarkdownStoryRenderer().render(StoryDrafts(DAY, [story], [SkippedAction("a3", "não é história")]), actions)

    assert md.startswith("# Rascunhos de user stories — 09/10/2026\n")
    assert "## 1. Exportar horas por projeto" in md
    assert "**Prioridade:** 🔴 Alta · **Prazo:** 12/10/2026 · **Reuniões:** 2026-10-09_10-00-00" in md
    assert "- [ ] Dado x, quando y, então z" in md
    assert "**Contexto:** fechamento" in md and "- Qual formato?" in md
    assert "- `a1` Criar exportação de horas (dito em 00:03:10)" in md
    assert "## Ações que não viraram história\n- `a3` Mandar e-mail para o cliente — não é história" in md


def test_empty_states():
    renderer = MarkdownStoryRenderer()
    assert "Nenhuma ação nova no plano deste dia." in renderer.render(StoryDrafts(DAY), [])
    only_skipped = renderer.render(StoryDrafts(DAY, [], [SkippedAction("a9", "x")]), [Action("a", "usuário", "m", id="a1")])
    assert "Nenhuma ação nova virou história." in only_skipped
    assert "- `a9` (ação fora do plano) — x" in only_skipped
    minimal = renderer.render(StoryDrafts(DAY, [UserStory("T", "N")]), [Action("a", "usuário", "m", id="a1")])
    assert "Prioridade" not in minimal and "Critérios" not in minimal and "Ações de origem" not in minimal
