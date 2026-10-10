from datetime import date
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.stories_claude import (
    ClaudeStoryWriter,
    SkippedOut,
    StoriesOut,
    StoryOut,
    build_user_message,
)
from teams_recorder.domain import Action, ActionKind, Analysis, AnalysisError, Decision, Priority, UserStory
from teams_recorder.messages import Prompt, StoryDoc

DAY = date(2026, 10, 9)


class FakeTransport:
    name = "fake"

    def __init__(self, out: StoriesOut):
        self.out = out
        self.calls: list[tuple[str, str, type, str]] = []

    def complete(self, system, user, schema, *, tag, extra=None):
        self.calls.append((system, user, schema, tag))
        return self.out


@pytest.fixture
def guide(tmp_path: Path) -> Path:
    path = tmp_path / "guide.md"
    path.write_text("# Guia\nUse 'Como <persona>, quero <capacidade>, para <benefício>.'\n")
    return path


def _actions() -> list[Action]:
    return [
        Action("Criar exportação de horas", "usuário", "m1", id="a1", due=date(2026, 10, 15), priority=Priority.MEDIUM, at="00:03:10"),
        Action("Validar filtros do relatório", "usuário", "m2", id="a2", due=date(2026, 10, 12), priority=Priority.HIGH),
        Action("Mandar e-mail para o cliente", "usuário", "m1", id="a3"),
        Action("Revisar contrato", "usuário", "m1", id="a4"),
    ]


def test_draft_keeps_traceability_honest(guide: Path):
    out = StoriesOut(
        stories=[
            StoryOut(title=" Exportar horas por projeto ", narrative="Como gestor, quero exportar, para fechar o mês.",
                     acceptance_criteria=["Dado x, quando y, então z", " "], details="**Contexto:** fechamento",
                     open_questions=["Qual formato?"], source_action_ids=["a1", "a2", "a1", "inventado"]),
            StoryOut(title="História inventada", narrative="...", source_action_ids=["nao-existe"]),
            StoryOut(title="  ", narrative="sem título", source_action_ids=["a4"]),
        ],
        skipped=[SkippedOut(action_id="a3", reason=" não é trabalho de produto ")],
    )
    transport = FakeTransport(out)
    writer = ClaudeStoryWriter(transport, guide, system_prompt="SYS")

    drafts = writer.draft(DAY, _actions(), [], [])

    assert drafts.day == DAY and len(drafts.stories) == 1
    story = drafts.stories[0]
    assert story.title == "Exportar horas por projeto"
    assert story.source_action_ids == ["a1", "a2"]         # duplicates and invented ids dropped
    assert story.source_meetings == ["m1", "m2"]
    assert story.priority == Priority.HIGH                  # strongest of the sources
    assert story.due == date(2026, 10, 12)                  # earliest of the sources
    assert story.acceptance_criteria == ["Dado x, quando y, então z"]
    skipped = {k.action_id: k.reason for k in drafts.skipped}
    assert skipped == {"a3": "não é trabalho de produto", "a4": StoryDoc.NOT_ADDRESSED}


def test_guide_is_always_in_the_system_prompt(guide: Path, tmp_path: Path):
    prompt = tmp_path / "stories_system.md"
    prompt.write_text("RULES\n")
    transport = FakeTransport(StoriesOut())
    writer = ClaudeStoryWriter(transport, guide, prompt_path=prompt)

    writer.draft(DAY, _actions(), [], [])
    guide.write_text("# Guia novo\n")                       # edits apply on the next call
    writer.draft(DAY, _actions(), [], [])

    first, second = transport.calls[0][0], transport.calls[1][0]
    assert first.startswith("RULES") and "# User story guide" in first and "Como <persona>" in first
    assert second.endswith("# Guia novo")
    assert transport.calls[0][2] is StoriesOut and transport.calls[0][3] == "stories:2026-10-09"


def test_missing_or_empty_guide_is_an_error(tmp_path: Path):
    transport = FakeTransport(StoriesOut())
    with pytest.raises(AnalysisError, match="guide not found"):
        ClaudeStoryWriter(transport, tmp_path / "nope.md", system_prompt="SYS").draft(DAY, _actions(), [], [])
    empty = tmp_path / "empty.md"
    empty.write_text("  \n")
    with pytest.raises(AnalysisError, match="guide is empty"):
        ClaudeStoryWriter(transport, empty, system_prompt="SYS").draft(DAY, _actions(), [], [])
    assert not transport.calls


def test_no_actions_skips_the_model(tmp_path: Path):
    transport = FakeTransport(StoriesOut())
    drafts = ClaudeStoryWriter(transport, tmp_path / "unused.md", system_prompt="SYS").draft(DAY, [], [], [])
    assert drafts.stories == [] and drafts.skipped == [] and not transport.calls


def test_user_message_has_actions_and_meeting_context():
    analysis = Analysis(meeting_id="m1", summary="Fechamento mensal", title="Status do contrato",
                        decisions=[Decision("Exportar em CSV")], my_actions=[Action("não repetir", "usuário", "m1", id="dup")])
    msg = build_user_message(DAY, _actions()[:1], [analysis], [], user_name="Felipe")

    assert msg.startswith("User (recording owner): Felipe\nPlan date: 2026-10-09 (Friday)")
    assert '"a1"' in msg and "Exportar em CSV" in msg and "Status do contrato" in msg
    assert '"dup"' not in msg                              # the user's own actions are sent once, as candidates


def test_existing_stories_are_shown_and_duplicates_point_to_them(guide: Path):
    existing = [UserStory("Exportar horas por projeto", "Como gestor, quero exportar horas", id="s-old")]
    out = StoriesOut(skipped=[
        SkippedOut(action_id="a1", reason="já coberta", duplicate_of="s-old"),
        SkippedOut(action_id="a2", reason="já coberta", duplicate_of="inventada"),
    ])
    transport = FakeTransport(out)

    drafts = ClaudeStoryWriter(transport, guide, system_prompt="SYS").draft(DAY, _actions()[:2], [], existing)

    user = transport.calls[0][1]
    assert Prompt.STORIES_EXISTING in user and '"s-old"' in user and "Exportar horas por projeto" in user
    assert "acceptance_criteria" not in user.split(Prompt.STORIES_EXISTING)[1]   # only the summary fields
    assert [(k.action_id, k.duplicate_of) for k in drafts.skipped] == [("a1", "s-old"), ("a2", None)]  # invented id dropped


def test_no_existing_section_without_existing_stories():
    assert Prompt.STORIES_EXISTING not in build_user_message(DAY, _actions()[:1], [], [])


def test_an_action_used_in_a_story_is_never_listed_as_skipped(guide: Path):
    out = StoriesOut(
        stories=[StoryOut(title="Exportar horas", narrative="n", source_action_ids=["a1"])],
        skipped=[SkippedOut(action_id="a1", reason="contradição do modelo")],
    )
    drafts = ClaudeStoryWriter(FakeTransport(out), guide, system_prompt="SYS").draft(DAY, _actions()[:1], [], [])
    assert [s.source_action_ids for s in drafts.stories] == [["a1"]] and drafts.skipped == []


def test_story_kind_comes_from_the_sources_and_candidates_carry_their_kind(guide: Path):
    actions = [Action("Corrigir data", "usuário", "m1", id="b1", kind=ActionKind.BUG),
               Action("Nova coluna", "usuário", "m1", id="f1", kind=ActionKind.FEATURE)]
    out = StoriesOut(stories=[StoryOut(title="Corrigir data no card", narrative="n", source_action_ids=["b1", "f1"]),
                              StoryOut(title="Nova coluna", narrative="n", source_action_ids=["f1"])])
    transport = FakeTransport(out)
    drafts = ClaudeStoryWriter(transport, guide, system_prompt="SYS").draft(DAY, actions, [], [])
    assert [s.kind for s in drafts.stories] == [ActionKind.BUG, ActionKind.FEATURE]
    assert '"kind": "bug"' in transport.calls[0][1]
