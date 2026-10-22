"""ClaudeClaimVerifier with a fake transport: the claims and transcript it sends, and how verdicts become statuses."""
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.llm_schema import load_prompt, strict_schema
from teams_recorder.adapters.outbound.verifier_claude import (
    ClaudeClaimVerifier,
    VerdictOut,
    VerifyOut,
    claims_of,
    to_verification,
    transcript_for,
)
from teams_recorder.config import load_settings
from teams_recorder.constants import Files
from teams_recorder.domain import (
    Action,
    AnalysisError,
    Analysis,
    ClaimKind,
    ClaimRef,
    Deadline,
    Decision,
    Meeting,
    Segment,
    Transcript,
    Verification,
    VerificationStatus,
)
from teams_recorder.messages import Minutes, Prompt

MEETING = Meeting.start(datetime(2026, 10, 12, 9, 0, 0))   # a Monday
ANALYSIS = Analysis(
    meeting_id=MEETING.id, summary="s",
    decisions=[Decision("Usar o Mapbox", "00:00:05")],
    my_actions=[Action("Enviar o cronograma", "usuário", MEETING.id, due=date(2026, 10, 15), at="00:00:10", id="a1")],
    others_actions=[Action("Revisar o mapa", "indefinido", MEETING.id, id="a2")],
    deadlines=[Deadline("Piloto", date(2026, 10, 30), "Ana")],
    participants=["Ana"],
)
TRANSCRIPT = Transcript([Segment(0, 4, "Bom dia, Ana."), Segment(5, 9, "Vamos usar o Mapbox."), Segment(10, 14, "Eu mando o cronograma na quarta.")])


def verdict(id_: str, support: str = "supported", owner: bool | None = None, date_said: bool | None = None,
            tentative: bool = False, sensitive: bool = False, reason: str = "dito na reunião") -> VerdictOut:
    return VerdictOut(id=id_, support=support, owner_evident=owner, date_said=date_said, tentative=tentative, sensitive=sensitive, reason=reason)


@dataclass
class FakeTransport:
    out: VerifyOut
    name: str = "fake"
    calls: list[dict] = field(default_factory=list)

    def complete(self, system, user, schema, *, tag, extra=None):
        self.calls.append({"system": system, "user": user, "schema": schema, "tag": tag, "extra": extra})
        return self.out


def test_claims_get_short_ids_and_readable_owners():
    claims = claims_of(ANALYSIS, user_name="Felipe")
    assert [(c.id, c.ref) for c in claims] == [
        ("c1", ClaimRef(ClaimKind.DECISION, "0")), ("c2", ClaimRef(ClaimKind.ACTION, "a1")), ("c3", ClaimRef(ClaimKind.ACTION, "a2")),
        ("c4", ClaimRef(ClaimKind.DEADLINE, "0")), ("c5", ClaimRef(ClaimKind.PARTICIPANT, "Ana")),
    ]
    assert claims[1].owner == "Felipe" and claims[1].due == "2026-10-15" and claims[1].at == "00:00:10"   # named, as the prototype did
    assert claims[2].owner is None   # "indefinido": no owner to check
    assert claims_of(ANALYSIS)[1].owner == "the user"


def test_the_message_has_the_meeting_date_the_whole_transcript_and_every_claim():
    transport = FakeTransport(VerifyOut(verdicts=[]))
    ClaudeClaimVerifier(transport, system_prompt="SYS", user_name="Felipe").verify(MEETING, ANALYSIS, TRANSCRIPT)

    call = transport.calls[0]
    assert call["system"] == "SYS" and call["schema"] is VerifyOut
    assert call["tag"] == f"verify:{MEETING.id}" and call["extra"] == {"meeting": MEETING.id}
    user = call["user"]
    assert user.startswith("User (recording owner): Felipe\nMeeting date: 2026-10-12 (Monday)")
    assert Prompt.VERIFY_TRANSCRIPT in user and "[00:00:10] Eu mando o cronograma na quarta." in user
    assert "[c2] (action) Enviar o cronograma | owner: Felipe | date: 2026-10-15 | cited at 00:00:10" in user   # the prototype's format
    assert "\n\n## Transcript\n[00:00:00] Bom dia, Ana." in user and "\n\n## Claims\n[c1] (decision) Usar o Mapbox | cited at 00:00:05" in user
    assert "[c5] (participant) Ana" in user


def test_a_long_transcript_is_cut_to_its_start_and_the_lines_around_each_claim():
    segments = [Segment(i * 10.0, i * 10.0 + 8, f"fala {i} da reunião longa") for i in range(600)]   # 100 minutes
    claims = claims_of(Analysis(meeting_id="m", summary="s", decisions=[Decision("x", "01:00:00")]))

    text, excerpt = transcript_for(Transcript(segments), claims, max_chars=300, window=30)

    lines = text.splitlines()
    assert excerpt and lines[0] == "[00:00:00] fala 0 da reunião longa"
    assert Prompt.EXCERPT_GAP in lines and lines.count(Prompt.EXCERPT_GAP) == 2   # after the start, after the window
    window = [line for line in lines if line.startswith("[00:59") or line.startswith("[01:00")]
    assert window == ["[00:59:30] fala 357 da reunião longa", "[00:59:40] fala 358 da reunião longa", "[00:59:50] fala 359 da reunião longa",
                      "[01:00:00] fala 360 da reunião longa", "[01:00:10] fala 361 da reunião longa", "[01:00:20] fala 362 da reunião longa",
                      "[01:00:30] fala 363 da reunião longa"]
    assert transcript_for(TRANSCRIPT, claims)[1] is False   # a short one goes whole


@pytest.mark.parametrize("found, expected", [
    (verdict("c"), VerificationStatus.CONFIRMED),
    (verdict("c", support="partial"), VerificationStatus.UNCONFIRMED),
    (verdict("c", support="contradicted"), VerificationStatus.UNCONFIRMED),
    (verdict("c", owner=False), VerificationStatus.UNCONFIRMED),        # the owner is not evident
    (verdict("c", date_said=False), VerificationStatus.UNCONFIRMED),    # the date is not said
    (verdict("c", sensitive=True), VerificationStatus.UNCONFIRMED),
    (verdict("c", tentative=True), VerificationStatus.CONFIRMED),       # tentative only matters for decisions
])
def test_an_action_is_confirmed_only_when_every_check_passes(found, expected):
    action = claims_of(ANALYSIS, "Felipe")[1]   # has an owner and a date
    assert to_verification(action, found).status is expected


def test_owner_and_date_checks_only_apply_when_the_claim_has_them_and_tentative_only_to_decisions():
    decision, unowned = claims_of(ANALYSIS)[0], claims_of(ANALYSIS)[2]
    assert to_verification(decision, verdict("c1", tentative=True)).status is VerificationStatus.UNCONFIRMED
    assert to_verification(unowned, verdict("c3", owner=False, date_said=False)).status is VerificationStatus.CONFIRMED


def test_every_claim_gets_a_status_and_unknown_verdicts_are_ignored():
    out = VerifyOut(verdicts=[verdict("c1", reason=" o Mapbox foi escolhido "), verdict(" c2 ", support="unsupported", reason="ninguém disse"),
                              verdict("c99")])
    result = ClaudeClaimVerifier(FakeTransport(out), system_prompt="SYS").verify(MEETING, ANALYSIS, TRANSCRIPT)

    assert result[ClaimRef(ClaimKind.DECISION, "0")] == Verification(VerificationStatus.CONFIRMED, "o Mapbox foi escolhido")
    assert result[ClaimRef(ClaimKind.ACTION, "a1")] == Verification(VerificationStatus.UNCONFIRMED, "ninguém disse")
    assert result[ClaimRef(ClaimKind.PARTICIPANT, "Ana")] == Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_NO_VERDICT)
    assert len(result) == 5


def test_an_analysis_without_claims_makes_no_call():
    transport = FakeTransport(VerifyOut(verdicts=[]))
    assert ClaudeClaimVerifier(transport, system_prompt="SYS").verify(MEETING, Analysis(meeting_id="m", summary="s"), TRANSCRIPT) == {}
    assert transport.calls == []


def test_the_prompt_ships_with_the_project_and_the_schema_is_strict():
    settings = load_settings()
    assert "Brazilian Portuguese" in load_prompt(settings.prompts_dir / Files.VERIFY_PROMPT)
    schema = strict_schema(VerifyOut)["$defs"]["VerdictOut"]
    assert schema["additionalProperties"] is False and len(schema["required"]) == 7
    with pytest.raises(AnalysisError):
        ClaudeClaimVerifier(FakeTransport(VerifyOut(verdicts=[]))).verify(MEETING, ANALYSIS, TRANSCRIPT)   # no prompt configured


def test_the_shipped_prompt_is_the_measured_prototype_prompt():
    # The evaluation's numbers (§14.3) came from scripts/fidelity_eval.py VERIFY_SYSTEM. The product's prompt may
    # differ only where it must: the user's name comes in the message, the reason is written in Portuguese, and
    # the transcript may carry speaker labels and the roster (speaker attribution; the numbers predate the sentence),
    # and it holds one paragraph for the `status_update` kind (activities curator), which the prototype never checked,
    # and one for the transcript's language (language detection), which the prototype never saw.
    import ast
    script = Path(__file__).resolve().parents[2] / "scripts" / "fidelity_eval.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    measured = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", None) == "VERIFY_SYSTEM")
    shipped = load_prompt(load_settings().prompts_dir / Files.VERIFY_PROMPT)
    paragraph = [line for line in shipped.splitlines() if line.startswith("A claim of kind `status_update`")]
    assert len(paragraph) == 1   # an addition to the measured prompt
    shipped = shipped.replace(paragraph[0] + "\n", "")
    language = [line for line in shipped.splitlines() if line.startswith("When the message has a `Transcript language:` line")]
    assert len(language) == 1    # the other one
    shipped = shipped.replace(language[0] + "\n", "")
    expected = (measured
                .replace("The user who records the meetings is Felipe.",
                         "The message starts with the name of the user who records the meetings, when known, and the meeting date.")
                .replace("- reason: one short sentence.", "- reason: one short sentence, in Brazilian Portuguese.")
                .replace("it has no speaker labels and may contain recognition errors.",
                         "it may contain recognition errors. A name after a timestamp (\"[00:01:02] Ana: ...\") is the person who said "
                         "the line and is reliable attribution; a line without a name is unattributed. When the message lists the "
                         "participants seen in the meeting window, those people were present, even if they never speak."))
    assert shipped.strip() == expected.strip()


LABELLED = Transcript(
    [Segment(0, 4, "Bom dia.", speaker="Ana"), Segment(5, 9, "Vamos usar o Mapbox."), Segment(10, 14, "Eu mando.", speaker="Felipe")],
    roster=("Felipe", "Ana", "Lucas Huguenin Gurgel de Moura"), user_label="Felipe",
)


def test_the_verifier_prompt_treats_labels_as_attribution_and_no_longer_denies_them():
    """Speaker attribution UT-052 and UT-056: the pin above accepts exactly this sentence and nothing else."""
    shipped = load_prompt(load_settings().prompts_dir / Files.VERIFY_PROMPT)
    assert "no speaker labels" not in shipped
    assert "is the person who said the line and is reliable attribution" in shipped
    assert "participants seen in the meeting window, those people were present" in shipped


def test_labelled_lines_and_the_roster_reach_the_verifier():
    text, excerpt = transcript_for(LABELLED, [])
    assert not excerpt and text.splitlines() == ["[00:00:00] Ana: Bom dia.", "[00:00:05] Vamos usar o Mapbox.", "[00:00:10] Felipe: Eu mando."]

    transport = FakeTransport(VerifyOut(verdicts=[]))
    verifier = ClaudeClaimVerifier(transport, system_prompt="SYS", user_name="Felipe")
    verifier.verify(MEETING, ANALYSIS, LABELLED)
    user = transport.calls[0]["user"]
    assert "Meeting date: 2026-10-12 (Monday)\nParticipants seen in the meeting window: Felipe, Ana, Lucas Huguenin Gurgel de Moura\n\n## Transcript" in user
    assert "[00:00:10] Felipe: Eu mando." in user

    verifier.verify(MEETING, ANALYSIS, TRANSCRIPT)
    assert "Participants seen" not in transport.calls[1]["user"]   # no roster, no line: the message is what it was


# --- the transcript's language (docs/tasks/language-detection, UT-052, UT-053) ---------------------------------------
def _user_message(transcript: Transcript) -> str:
    verifier = ClaudeClaimVerifier(FakeTransport(VerifyOut(verdicts=[])), system_prompt="SYS", user_name="Felipe")
    return verifier.user_message(MEETING, claims_of(ANALYSIS, "Felipe"), transcript)


def test_the_verifier_message_names_an_english_transcript_and_says_nothing_for_a_portuguese_one():
    """UT-052: the same line as the analyzer's for `en`, none for `pt` (the message is what it was)."""
    english = Transcript(TRANSCRIPT.segments, language="en")
    line = Prompt.TRANSCRIPT_LANGUAGE.format(name="English")
    msg = _user_message(english)
    assert line == "Transcript language: English"
    assert msg.split(Prompt.VERIFY_TRANSCRIPT)[0].splitlines()[-1] == line   # in the header, before the transcript
    pt = _user_message(TRANSCRIPT)
    assert Transcript(TRANSCRIPT.segments).language == "pt" and "Transcript language" not in pt
    assert pt == _user_message(Transcript(TRANSCRIPT.segments, language="pt"))
    assert msg == pt.replace(Prompt.VERIFY_TRANSCRIPT, "\n" + line + Prompt.VERIFY_TRANSCRIPT, 1)   # nothing else changed
    assert Prompt.TRANSCRIPT_LANGUAGE.format(name="es") in _user_message(Transcript(TRANSCRIPT.segments, language="es"))


def test_the_language_line_reaches_the_transport_and_follows_the_roster_rule():
    transport = FakeTransport(VerifyOut(verdicts=[]))
    english = Transcript(TRANSCRIPT.segments, language="en", roster=("Felipe", "Ana"))
    ClaudeClaimVerifier(transport, system_prompt="SYS", user_name="Felipe").verify(MEETING, ANALYSIS, english)
    head = transport.calls[0]["user"].split("\n\n## Transcript")[0].splitlines()
    assert head[:2] == ["User (recording owner): Felipe", "Meeting date: 2026-10-12 (Monday)"]
    assert "Transcript language: English" in head and "Participants seen in the meeting window: Felipe, Ana" in head


def test_the_verifier_prompt_keeps_quotes_in_the_language_they_were_said_in():
    """UT-053 (verifier half): reasons stay Brazilian Portuguese; a quote is compared as it was said."""
    shipped = " ".join(load_prompt(load_settings().prompts_dir / Files.VERIFY_PROMPT).split())
    assert "When the message has a `Transcript language:` line, the transcript is in that language (without it, Portuguese)" in shipped
    assert "The quotes of the claims keep the language they were said in: compare them with the transcript as they are, never translated" in shipped
    assert "Your `reason` stays in Brazilian Portuguese whatever the language of the transcript" in shipped
