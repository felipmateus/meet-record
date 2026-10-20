from datetime import date, datetime

from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.domain import ActionKind, Criterion, Priority, Publication, SkippedAction, StoryDrafts, UserStory
from teams_recorder.messages import StoryDoc

DAY = date(2026, 10, 9)
BLOCK = "- [ ] **Criar exportação de horas** · [Daily 09/10][2026-10-09_10-00-00] #história\n  - falta o formato"


def test_renders_a_block_story_with_its_source_and_the_skipped_blocks():
    story = UserStory(
        "Exportar horas por projeto", "Como gestor, quero exportar, para fechar o mês.",
        acceptance_criteria=[Criterion("Dado x, quando y, então z")], details="**Contexto:** fechamento",
        open_questions=["Qual formato?"], source_meetings=["2026-10-09_10-00-00"], priority=Priority.HIGH, due=date(2026, 10, 12),
        kind=ActionKind.FEATURE, source_text=BLOCK,
    )
    skipped = SkippedAction("b2", "não é história", source_line="- [ ] Mandar e-mail para o cliente #história")
    md = MarkdownStoryRenderer().render(StoryDrafts(DAY, [story], [skipped]), [])

    assert md.startswith("# Rascunhos de user stories — 09/10/2026\n")
    assert "## 1. Exportar horas por projeto" in md
    assert "**Tipo:** Feature · **Prioridade:** 🔴 Alta · **Prazo:** 12/10/2026 · **Reuniões:** 2026-10-09_10-00-00" in md
    assert "- [ ] Dado x, quando y, então z" in md
    assert "**Contexto:** fechamento" in md and "- Qual formato?" in md
    assert f"{StoryDoc.SOURCE_BLOCK}\n> - [ ] **Criar exportação de horas** · [Daily 09/10][2026-10-09_10-00-00] #história\n>   - falta o formato" in md
    assert "## Itens que não viraram história\n- `- [ ] Mandar e-mail para o cliente #história` — não é história" in md   # by its stored line, not its ref
    assert "`b2`" not in md


def test_empty_states():
    renderer = MarkdownStoryRenderer()
    assert "Nenhum item virou história." in renderer.render(StoryDrafts(DAY), [])
    only_skipped = renderer.render(StoryDrafts(DAY, [], [SkippedAction("a9", "x")]), [])
    assert "Nenhum item virou história." in only_skipped and "- `a9` — x" in only_skipped         # a planner-era skip: its id and reason
    minimal = renderer.render(StoryDrafts(DAY, [UserStory("T", "N")]), [])
    assert "Prioridade" not in minimal and "Critérios" not in minimal and StoryDoc.SOURCE_BLOCK not in minimal


def test_a_story_of_the_planner_shows_its_meetings_and_no_source_section():
    story = UserStory("Exportar horas", "n", source_action_ids=["a1"], source_meetings=["m1", "m2"])
    md = MarkdownStoryRenderer().render(StoryDrafts(DAY, [story]), [])
    assert "**Reuniões:** m1, m2" in md and StoryDoc.SOURCE_BLOCK not in md and "a1" not in md


def test_a_tagged_line_with_a_backtick_gets_a_longer_code_span():
    skipped = SkippedAction("b1", "x", source_line="- [ ] rodar `make` #história")
    assert "- `` - [ ] rodar `make` #história `` — x" in MarkdownStoryRenderer().render(StoryDrafts(DAY, [], [skipped]), [])


def test_duplicates_name_the_covering_story_among_earlier_and_todays_stories():
    drafts = StoryDrafts(DAY, [UserStory("Exportar das horas de hoje", "n", id="s-today")], [
        SkippedAction("b1", "já coberto", "s-old", "- [ ] a #história"),
        SkippedAction("b2", "já coberto", "s-today", "- [ ] b #história"),
        SkippedAction("b3", "já coberto", "s-gone", "- [ ] c #história")])
    md = MarkdownStoryRenderer().render(drafts, [UserStory("Exportar horas por projeto", "n", id="s-old")])
    assert "`- [ ] a #história` — já coberto" + StoryDoc.DUPLICATE_OF.format(title="Exportar horas por projeto") in md
    assert "`- [ ] b #história` — já coberto" + StoryDoc.DUPLICATE_OF.format(title="Exportar das horas de hoje") in md
    assert "`- [ ] c #história` — já coberto" + StoryDoc.DUPLICATE_OF.format(title="s-gone") in md   # unknown story: its id


def test_publications_are_listed_under_the_story():
    story = UserStory("Exportar horas", "n", publications=[Publication("backlog-md", "TASK-7", datetime(2026, 10, 9, 18, 5))])
    md = MarkdownStoryRenderer().render(StoryDrafts(DAY, [story]), [])
    assert "## 1. Exportar horas\n" + StoryDoc.PUBLISHED.format(destination="backlog-md", ref="TASK-7") in md


def test_the_kind_is_shown_with_the_story():
    md = MarkdownStoryRenderer().render(StoryDrafts(DAY, [UserStory("Deploy em PROD", "", kind=ActionKind.OPERATION)]), [])
    assert StoryDoc.KIND.format(label=StoryDoc.KIND_LABELS["operation"]) in md
