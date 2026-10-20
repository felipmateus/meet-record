"""Task 5.0 of the fidelity guard: every acceptance criterion says where it comes from (FR6). Drafting checks the cited times in
tests/unit/test_stories_use_cases.py."""
import json
from datetime import date, datetime
from pathlib import Path

from teams_recorder.adapters.outbound import codec
from teams_recorder.adapters.outbound.llm_schema import strict_schema
from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher, criterion_text
from teams_recorder.adapters.outbound.stories_claude import StoriesOut
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.config import load_settings
from teams_recorder.constants import Files
from teams_recorder.domain import (
    SUGGESTION,
    Criterion,
    Segment,
    StoryDrafts,
    Transcript,
    UserStory,
    checked_criteria,
    said_at,
)

TRANSCRIPT = Transcript([Segment(5.0, 9.0, "Vamos exportar em CSV."), Segment(190.0, 195.0, "Só o mês fechado.")])


def test_a_cited_time_must_be_a_line_of_the_source_meetings():
    said = said_at(TRANSCRIPT)
    assert said == {"00:00:05", "00:03:10"}
    criteria = [Criterion("Exporta em CSV", "00:00:05"), Criterion("Só meses fechados", "00:03:11"),
                Criterion("Também em PDF", SUGGESTION), Criterion("Antigo", None)]
    assert checked_criteria(criteria, said) == [
        Criterion("Exporta em CSV", "00:00:05"),
        Criterion("Só meses fechados", SUGGESTION),   # a citation nobody can find must not look confirmed
        Criterion("Também em PDF", SUGGESTION),
        Criterion("Antigo", None),                    # drafted before provenance: shown as before
    ]
    assert Criterion("x", SUGGESTION).suggested and not Criterion("x", "00:00:05").suggested


def test_the_reviewer_sees_the_source_in_the_drafts_and_on_the_board(tmp_path: Path):
    story = UserStory("Exportar horas", "Como gestor, quero exportar.", acceptance_criteria=[
        Criterion("Exporta em CSV", "00:00:05"), Criterion("Também em PDF", SUGGESTION), Criterion("Antigo")])
    md = MarkdownStoryRenderer().render(StoryDrafts(date(2026, 10, 14), [story]), [])
    assert "- [ ] Exporta em CSV `[00:00:05]`" in md and "- [ ] Também em PDF _(sugestão)_" in md and "- [ ] Antigo\n" in md
    cmd = BacklogMdPublisher(tmp_path, "Triagem", ()).command(story, date(2026, 10, 14))
    assert [cmd[i + 1] for i, a in enumerate(cmd) if a == "--ac"] == ["Exporta em CSV [00:00:05]", "Também em PDF (sugestão)", "Antigo"]
    assert criterion_text(Criterion("x", SUGGESTION)) == "x (sugestão)"


def test_old_drafts_load_and_are_written_back_as_they_were():
    old = {"id": "s1", "title": "t", "narrative": "n", "acceptance_criteria": ["Dado x, então y"]}   # before 2026-10-14
    story = codec.story_from_dict(old)
    assert story.acceptance_criteria == [Criterion("Dado x, então y")]
    assert codec.story_to_dict(story)["acceptance_criteria"] == ["Dado x, então y"]
    cited = UserStory("t", "n", acceptance_criteria=[Criterion("a", "00:00:05"), Criterion("b", SUGGESTION)])
    assert codec.story_to_dict(cited)["acceptance_criteria"] == [{"text": "a", "source": "00:00:05"}, {"text": "b", "source": "suggestion"}]
    assert codec.story_from_dict(json.loads(json.dumps(codec.story_to_dict(cited)))) == cited


def test_the_writer_must_give_every_criterion_a_source_and_is_told_how():
    criterion = strict_schema(StoriesOut)["$defs"]["CriterionOut"]
    assert sorted(criterion["required"]) == ["source", "text"] and criterion["additionalProperties"] is False
    prompt = (load_settings().prompts_dir / Files.STORIES_PROMPT).read_text(encoding="utf-8")
    assert "Never present a proposal of yours without `suggestion`" in prompt   # the measured rule (fidelity_eval CITE_RULE)
    assert "`verification.status` is `unconfirmed`" in prompt and "never cite them as the source" in prompt




def test_a_damaged_criterion_is_an_error_not_a_citation():
    import pytest
    for bad in ({"text": "x", "source": "garbage"}, {"text": "x", "source": 5}, {"text": 5, "source": "00:00:05"}):
        with pytest.raises((TypeError, ValueError)):
            codec.criterion_from_value(bad)
    assert codec.criterion_from_value({"text": "x"}) == Criterion("x")   # no source: as before provenance
