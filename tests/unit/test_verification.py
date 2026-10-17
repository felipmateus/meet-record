"""Claim verification in the domain: claim references, combining verdicts, writing them back, the code checks."""
from datetime import date

from teams_recorder.constants import Verify
from teams_recorder.domain import (
    Action,
    Analysis,
    ClaimKind,
    ClaimRef,
    Deadline,
    Decision,
    Segment,
    Transcript,
    Verification,
    VerificationStatus,
    claim_refs,
    combine,
    participant_heard,
    sensitive_data,
    with_verifications,
)

YES = Verification(VerificationStatus.CONFIRMED, "dito em 00:01:10")
NO = Verification(VerificationStatus.UNCONFIRMED, "a transcrição não diz quem fará")


def _analysis() -> Analysis:
    return Analysis(
        meeting_id="m", summary="s",
        decisions=[Decision("Usar o Mapbox", "00:01:10"), Decision("Adiar o piloto")],
        my_actions=[Action("Enviar o cronograma", "usuário", "m", id="a1")],
        others_actions=[Action("Revisar o mapa", "Ana", "m", id="a2")],
        deadlines=[Deadline("Cronograma", date(2026, 10, 15), "usuário")],
        participants=["Felipe", "Ana"],
    )


def test_claims_are_listed_in_reading_order():
    assert claim_refs(_analysis()) == [
        ClaimRef(ClaimKind.DECISION, "0"), ClaimRef(ClaimKind.DECISION, "1"), ClaimRef(ClaimKind.ACTION, "a1"),
        ClaimRef(ClaimKind.ACTION, "a2"), ClaimRef(ClaimKind.DEADLINE, "0"), ClaimRef(ClaimKind.PARTICIPANT, "Felipe"),
        ClaimRef(ClaimKind.PARTICIPANT, "Ana"),
    ]


def test_unconfirmed_wins_and_reasons_of_the_same_status_are_joined():
    assert combine(YES, NO) == NO and combine(NO, YES) == NO
    assert combine(None, YES) == YES and combine(NO, None) == NO and combine(None, None) is None
    both = combine(NO, Verification(VerificationStatus.UNCONFIRMED, "contém dado pessoal sensível"))
    assert both == Verification(VerificationStatus.UNCONFIRMED, "a transcrição não diz quem fará; contém dado pessoal sensível")
    assert combine(NO, NO) == NO   # the same reason is not repeated


def test_verifications_are_written_into_a_copy():
    original = _analysis()
    verdicts = {ClaimRef(ClaimKind.DECISION, "1"): NO, ClaimRef(ClaimKind.ACTION, "a2"): YES,
                ClaimRef(ClaimKind.DEADLINE, "0"): NO, ClaimRef(ClaimKind.PARTICIPANT, "Ana"): YES,
                ClaimRef(ClaimKind.PARTICIPANT, "Marcos"): NO}   # not a participant of this analysis: ignored

    verified = with_verifications(original, verdicts)

    assert [d.verification for d in verified.decisions] == [None, NO]
    assert [a.verification for a in verified.all_actions] == [None, YES]
    assert verified.deadlines[0].verification == NO
    assert verified.participant_checks == {"Ana": YES}
    assert all(a.verification is None for a in original.all_actions) and original.participant_checks == {}   # untouched
    assert [a.id for a in verified.all_actions] == ["a1", "a2"]   # the same actions, copied


def test_sensitive_data_ignores_case_and_accents():
    assert sensitive_data("Ana está afastada por PROBLEMAS DE SAÚDE", Verify.SENSITIVE)
    assert sensitive_data("Bruno vai ao cardiologista na quinta", Verify.SENSITIVE)
    assert not sensitive_data("Enviar o cronograma do piloto", Verify.SENSITIVE)


def _transcript(*lines: str) -> Transcript:
    return Transcript([Segment(i * 5.0, i * 5.0 + 4, text) for i, text in enumerate(lines)])


def _heard(name: str, transcript: Transcript, user: str = "Felipe") -> bool:
    return participant_heard(name, transcript, user, Verify.NAME_PARTICLES, Verify.ADDRESS)


def test_a_participant_is_someone_who_speaks_or_is_addressed():
    meeting = _transcript("Bom dia, Ana.", "Carla, você consegue mandar até sexta?", "O Marcos pediu o relatório.",
                          "José falou que vai ver.", "O José confirmou ontem.")
    assert _heard("Ana", meeting)                   # greeted
    assert _heard("Carla Mendes", meeting)          # addressed by first name
    assert _heard("José Fontes", meeting)           # named twice, accents ignored
    assert not _heard("Marcos", meeting)            # only mentioned once
    assert _heard("Felipe", meeting)                # the recording's owner is always a participant
    assert not _heard("Felipe", meeting, user="")   # ...when the owner's name is known
    assert not _heard("de", meeting)                # nothing but particles


def test_a_greeting_split_across_segments_still_counts():
    # whisper often ends a segment right after "Bom dia,"
    assert _heard("Ana", Transcript([Segment(0, 2, "Bom dia,"), Segment(2, 5, "Ana tudo bem?")]))


def test_the_owner_counts_by_first_name_or_full_name():
    silent = _transcript("bom dia a todos")
    assert _heard("Felipe", silent, user="Felipe Mateus") and _heard("Felipe Mateus", silent, user="Felipe")
    assert not _heard("Ana", silent, user="Felipe Mateus")


def test_a_participant_listed_twice_is_one_claim():
    from teams_recorder.domain import claims
    analysis = Analysis(meeting_id="m", summary="s", participants=["Ana", "Ana", "Bruno"])
    assert [c.ref.key for c in claims(analysis)] == ["Ana", "Bruno"]


def test_a_labelled_speaker_or_a_roster_name_is_heard_even_when_never_said_in_the_text():
    """Speaker attribution UT-053: same token rule as the owner's name."""
    segments = [Segment(0, 4, "Bom dia a todos.", speaker="Ana Souza"), Segment(5, 9, "Vamos seguir.")]
    labelled = Transcript(segments, roster=("Felipe", "Ana Souza", "Lucas Huguenin Gurgel de Moura"))
    assert _heard("Ana", labelled)                                  # first name of a label
    assert _heard("Lucas Huguenin Gurgel de Moura", labelled)       # roster entry, never in the text
    assert _heard("Lucas", labelled)                                # a part of a roster entry
    assert not _heard("Marcos", labelled)                           # neither said nor seen
    assert not _heard("de", labelled)                               # particles do not count
    assert not _heard("Lucas", Transcript(segments))                # without the roster it is just a name nobody said
