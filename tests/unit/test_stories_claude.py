from datetime import date
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.stories_claude import (
    ClaudeStoryWriter,
    CriterionOut,
    SkippedOut,
    StoriesOut,
    StoryOut,
    build_user_message,
)
from teams_recorder.domain import (
    SUGGESTION,
    Action,
    ActionKind,
    Analysis,
    AnalysisError,
    Criterion,
    Decision,
    Priority,
    TaggedBlock,
    UserStory,
)
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


def _blocks() -> list[TaggedBlock]:
    return [
        TaggedBlock("b1", ("- [ ] **Criar exportação de horas** · [Daily 09/10][m1] #história", "  - falta o formato"), ("m1",)),
        TaggedBlock("b2", ("- [ ] **Validar filtros do relatório** [Revisão][m2] #história",), ("m2",)),
        TaggedBlock("b3", ("- [ ] Mandar e-mail para o cliente #história",), ()),
        TaggedBlock("b4", ("- [ ] Revisar contrato #história",), ()),
    ]


def test_draft_keeps_traceability_honest(guide: Path):
    out = StoriesOut(
        stories=[
            StoryOut(title=" Exportar horas por projeto ", narrative="Como gestor, quero exportar, para fechar o mês.",
                     acceptance_criteria=[CriterionOut(text="Dado x, quando y, então z ", source="[00:03:10]"),
                                          CriterionOut(text=" ", source="00:00:01"),
                                          CriterionOut(text="Exportar também em PDF", source="(sugestão)")],
                     details="**Contexto:** fechamento", open_questions=["Qual formato?"], block="b1",
                     kind=ActionKind.FEATURE, priority=Priority.HIGH, due="2026-10-12T00:00:00"),
            StoryOut(title="História inventada", narrative="...", block="b9", kind=ActionKind.BUG),
            StoryOut(title="  ", narrative="sem título", block="b4", kind=ActionKind.BUG),
        ],
        skipped=[SkippedOut(ref="b3", reason=" não é trabalho de produto ")],
    )
    transport = FakeTransport(out)
    writer = ClaudeStoryWriter(transport, guide, system_prompt="SYS")

    drafts = writer.draft_from_blocks(DAY, _blocks(), [], [])

    assert drafts.day == DAY and len(drafts.stories) == 1
    story = drafts.stories[0]
    assert story.title == "Exportar horas por projeto"
    assert story.source_text == "- [ ] **Criar exportação de horas** · [Daily 09/10][m1] #história\n  - falta o formato"   # the block, verbatim
    assert story.source_meetings == ["m1"] and story.source_action_ids == []
    assert (story.kind, story.priority, story.due) == (ActionKind.FEATURE, Priority.HIGH, date(2026, 10, 12))   # as the writer set them
    assert story.acceptance_criteria == [Criterion("Dado x, quando y, então z", "00:03:10"),   # brackets dropped, blank removed
                                         Criterion("Exportar também em PDF", SUGGESTION)]      # anything but a time: a suggestion
    assert [(k.action_id, k.reason, k.source_line) for k in drafts.skipped] == [
        ("b2", StoryDoc.NOT_ADDRESSED, "- [ ] **Validar filtros do relatório** [Revisão][m2] #história"),   # left out by the model, never mentioned
        ("b3", "não é trabalho de produto", "- [ ] Mandar e-mail para o cliente #história"),
        ("b4", StoryDoc.NOT_ADDRESSED, "- [ ] Revisar contrato #história"),                                  # its only story had no title
    ]


def test_the_kind_priority_and_due_are_the_writers_or_empty(guide: Path):
    out = StoriesOut(stories=[
        StoryOut(title="Estimar", narrative="", block="b1", kind=ActionKind.TECHNICAL),
        StoryOut(title="Deploy", narrative="", block="b2", kind=ActionKind.OPERATION, due="not a date"),
    ])
    drafts = ClaudeStoryWriter(FakeTransport(out), guide, system_prompt="SYS").draft_from_blocks(DAY, _blocks()[:2], [], [])
    assert [(s.kind, s.priority, s.due, s.is_task_card, s.verification) for s in drafts.stories] == [
        (ActionKind.TECHNICAL, None, None, True, None), (ActionKind.OPERATION, None, None, True, None)]


def test_a_block_of_another_nature_is_a_skip_with_the_reason(guide: Path):
    out = StoriesOut(
        stories=[StoryOut(title="Alinhar com o time", narrative="", block="b1", kind=ActionKind.MANAGEMENT),
                 StoryOut(title="Mandar o e-mail", narrative="", block="b2", kind=ActionKind.COMMUNICATION)],
        skipped=[SkippedOut(ref="b2", reason="só um e-mail")])
    drafts = ClaudeStoryWriter(FakeTransport(out), guide, system_prompt="SYS").draft_from_blocks(DAY, _blocks()[:2], [], [])
    assert drafts.stories == []
    assert [(k.action_id, k.reason) for k in drafts.skipped] == [
        ("b1", StoryDoc.OTHER_KIND.format(kind=StoryDoc.KIND_LABELS["management"])), ("b2", "só um e-mail")]   # the model's own reason wins


def test_guide_is_always_in_the_system_prompt(guide: Path, tmp_path: Path):
    prompt = tmp_path / "stories_system.md"
    prompt.write_text("RULES\n")
    transport = FakeTransport(StoriesOut())
    writer = ClaudeStoryWriter(transport, guide, prompt_path=prompt)

    writer.draft_from_blocks(DAY, _blocks(), [], [])
    guide.write_text("# Guia novo\n")                       # edits apply on the next call
    writer.draft_from_blocks(DAY, _blocks(), [], [])

    first, second = transport.calls[0][0], transport.calls[1][0]
    assert first.startswith("RULES") and "# User story guide" in first and "Como <persona>" in first
    assert second.endswith("# Guia novo")
    assert transport.calls[0][2] is StoriesOut and transport.calls[0][3] == "stories:2026-10-09"


def test_missing_or_empty_guide_is_an_error(tmp_path: Path):
    transport = FakeTransport(StoriesOut())
    with pytest.raises(AnalysisError, match="guide not found"):
        ClaudeStoryWriter(transport, tmp_path / "nope.md", system_prompt="SYS").draft_from_blocks(DAY, _blocks(), [], [])
    empty = tmp_path / "empty.md"
    empty.write_text("  \n")
    with pytest.raises(AnalysisError, match="guide is empty"):
        ClaudeStoryWriter(transport, empty, system_prompt="SYS").draft_from_blocks(DAY, _blocks(), [], [])
    assert not transport.calls


def test_no_blocks_skips_the_model(tmp_path: Path):
    transport = FakeTransport(StoriesOut())
    drafts = ClaudeStoryWriter(transport, tmp_path / "unused.md", system_prompt="SYS").draft_from_blocks(DAY, [], [], [])
    assert drafts.stories == [] and drafts.skipped == [] and not transport.calls


def test_user_message_has_the_blocks_and_their_meetings_context():
    analysis = Analysis(meeting_id="m1", summary="Fechamento mensal", title="Status do contrato",
                        decisions=[Decision("Exportar em CSV")], my_actions=[Action("Enviar a planilha", "usuário", "m1", id="a1", due=date(2026, 10, 15),
                                                                                    priority=Priority.HIGH)])
    msg = build_user_message(DAY, _blocks()[:1], [analysis], [], user_name="Felipe")

    assert msg.startswith("User (recording owner): Felipe\nDate: 2026-10-09 (Friday)")
    assert Prompt.STORIES_BLOCKS in msg and '"ref": "b1"' in msg and "falta o formato" in msg and '"meetings": [\n   "m1"\n  ]' in msg
    assert Prompt.STORIES_MEETINGS in msg and "Exportar em CSV" in msg and "Status do contrato" in msg
    assert "Enviar a planilha" in msg and '"priority": "high"' in msg and "2026-10-15" in msg   # the writer reads priority and due there


def test_no_meetings_section_without_analyses_and_no_existing_section_without_stories():
    msg = build_user_message(DAY, _blocks()[:1], [], [])
    assert Prompt.STORIES_MEETINGS not in msg and Prompt.STORIES_EXISTING not in msg and "b1" in msg


def test_existing_stories_are_shown_and_duplicates_point_to_them(guide: Path):
    existing = [UserStory("Exportar horas por projeto", "Como gestor, quero exportar horas", id="s-old")]
    out = StoriesOut(skipped=[
        SkippedOut(ref="b1", reason="já coberto", duplicate_of="s-old"),
        SkippedOut(ref="b2", reason="já coberto", duplicate_of="inventada"),
    ])
    transport = FakeTransport(out)

    drafts = ClaudeStoryWriter(transport, guide, system_prompt="SYS").draft_from_blocks(DAY, _blocks()[:2], [], existing)

    user = transport.calls[0][1]
    assert Prompt.STORIES_EXISTING in user and '"s-old"' in user and "Exportar horas por projeto" in user
    assert "acceptance_criteria" not in user.split(Prompt.STORIES_EXISTING)[1]   # only the summary fields
    assert [(k.action_id, k.duplicate_of) for k in drafts.skipped] == [("b1", "s-old"), ("b2", None)]  # invented id dropped


def test_a_block_used_in_a_story_is_never_listed_as_skipped(guide: Path):
    out = StoriesOut(
        stories=[StoryOut(title="Exportar horas", narrative="n", block="b1", kind=ActionKind.FEATURE)],
        skipped=[SkippedOut(ref="b1", reason="contradição do modelo")],
    )
    drafts = ClaudeStoryWriter(FakeTransport(out), guide, system_prompt="SYS").draft_from_blocks(DAY, _blocks()[:1], [], [])
    assert [s.kind for s in drafts.stories] == [ActionKind.FEATURE] and drafts.skipped == []
