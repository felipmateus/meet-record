"""VerifyAnalysis on fakes: the verifier's verdicts, the two code checks, failures, and the analysis step."""
from datetime import datetime

from teams_recorder.application.use_cases import AnalyzeMeeting, VerifyAnalysis
from teams_recorder.domain import (
    Action,
    Analysis,
    ClaimKind,
    ClaimRef,
    Decision,
    Meeting,
    Segment,
    Transcript,
    Verification,
    VerificationStatus,
)
from teams_recorder.domain.status import AUDIO
from teams_recorder.messages import Log, Minutes
from tests.fakes import FakeAnalyzer, FakeClaimVerifier, FakeMinutesRenderer

YES = Verification(VerificationStatus.CONFIRMED, "dito em 00:00:05")
NO = Verification(VerificationStatus.UNCONFIRMED, "ninguém disse isso")
MEETING = Meeting.start(datetime(2026, 10, 12, 9, 0, 0))
TRANSCRIPT = Transcript([Segment(0, 4, "Bom dia, Ana."), Segment(5, 9, "Vamos usar o Mapbox."), Segment(10, 14, "Ana, você revisa o mapa?")])


def _analysis() -> Analysis:
    return Analysis(
        meeting_id=MEETING.id, summary="s",
        decisions=[Decision("Usar o Mapbox", "00:00:05"), Decision("Ana está afastada por problemas de saúde")],
        others_actions=[Action("Revisar o mapa", "Ana", MEETING.id, id="a1")],
        participants=["Ana", "Marcos"],
    )


def test_the_verifiers_verdicts_are_written_and_code_checks_can_only_lower_them():
    verifier = FakeClaimVerifier({ClaimRef(ClaimKind.DECISION, "0"): YES, ClaimRef(ClaimKind.DECISION, "1"): YES,
                                  ClaimRef(ClaimKind.ACTION, "a1"): NO, ClaimRef(ClaimKind.PARTICIPANT, "Ana"): YES})

    verified = VerifyAnalysis(verifier, user_name="Felipe").execute(MEETING, _analysis(), TRANSCRIPT)

    assert verifier.calls[0][1].meeting_id == MEETING.id and verifier.calls[0][2] is TRANSCRIPT
    assert verified.decisions[0].verification == YES
    assert verified.decisions[1].verification == Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_SENSITIVE)
    assert verified.others_actions[0].verification == NO
    assert verified.participant_checks == {
        "Ana": YES,
        "Marcos": Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_NOT_HEARD),   # only mentioned: the code check
    }


def test_a_verifier_failure_leaves_its_claims_unverified_but_the_code_checks_still_apply(caplog):
    verified = VerifyAnalysis(FakeClaimVerifier(fail=RuntimeError("subscription window exhausted"))).execute(
        MEETING, _analysis(), TRANSCRIPT)

    assert verified.decisions[0].verification is None and verified.others_actions[0].verification is None
    assert verified.decisions[1].verification.status is VerificationStatus.UNCONFIRMED   # sensitive data, caught in code
    assert verified.participant_checks["Marcos"].status is VerificationStatus.UNCONFIRMED and "Ana" not in verified.participant_checks
    assert "subscription window exhausted" in caplog.text


def test_without_a_verifier_only_the_code_checks_run():
    verified = VerifyAnalysis(None).execute(MEETING, _analysis(), TRANSCRIPT)
    assert [d.verification is None for d in verified.decisions] == [True, False]
    assert list(verified.participant_checks) == ["Marcos"]


def test_an_analysis_without_claims_does_not_call_the_verifier():
    verifier = FakeClaimVerifier()
    assert VerifyAnalysis(verifier).execute(MEETING, Analysis(meeting_id=MEETING.id, summary="Teste de áudio."), TRANSCRIPT).participant_checks == {}
    assert verifier.calls == []


def test_the_analysis_step_saves_the_verified_analysis_and_renders_minutes_from_it(repo, meeting):
    repo.seed(meeting, {AUDIO}, transcript=TRANSCRIPT)
    verifier, renderer = FakeClaimVerifier({ClaimRef(ClaimKind.DECISION, "0"): NO}), FakeMinutesRenderer()

    result = AnalyzeMeeting(repo, FakeAnalyzer(), renderer, VerifyAnalysis(verifier)).execute(meeting.id)

    assert result.decisions[0].verification == NO   # FakeAnalyzer's "Go ahead with plan A"
    assert repo.load_analysis(meeting.id).decisions[0].verification == NO
    assert renderer.calls[0][1].decisions[0].verification == NO
    assert verifier.calls[0][1].meeting_id == meeting.id   # the verifier sees the analysis with its id set


def test_without_the_step_the_analysis_is_saved_unverified(repo, meeting):
    repo.seed(meeting, {AUDIO}, transcript=TRANSCRIPT)
    result = AnalyzeMeeting(repo, FakeAnalyzer()).execute(meeting.id)
    assert all(d.verification is None for d in result.decisions) and result.participant_checks == {}


def test_an_untrusted_transcript_is_not_given_to_the_verifier(caplog):
    """Task 7.0: a degraded transcript, or one from a track at the wrong rate, yields no confirmed claim (PRD decision 4)."""
    from dataclasses import replace
    from teams_recorder.domain import TranscriptHealth
    for health in (TranscriptHealth(0.4, 10, 30, True), TranscriptHealth(0.0, 30, 30, False, rate_mismatch=True, short_padding_share=0.66)):
        verifier = FakeClaimVerifier({ClaimRef(ClaimKind.DECISION, "0"): YES})

        verified = VerifyAnalysis(verifier).execute(MEETING, _analysis(), replace(TRANSCRIPT, health=health))

        assert verifier.calls == []
        assert verified.decisions[0].verification is None and verified.others_actions[0].verification is None   # unverified, not ⚠️
        assert verified.decisions[1].verification.status is VerificationStatus.UNCONFIRMED   # the code checks still apply
        assert "Marcos" in verified.participant_checks
    assert caplog.text.count(Log.VERIFY_SKIPPED.split("%s")[1]) == 2


def test_a_healthy_or_unchecked_transcript_is_verified():
    from dataclasses import replace
    from teams_recorder.domain import TranscriptHealth
    for health in (TranscriptHealth(0.05, 30, 30, False), None):
        verifier = FakeClaimVerifier({ClaimRef(ClaimKind.DECISION, "0"): YES})
        verified = VerifyAnalysis(verifier).execute(MEETING, _analysis(), replace(TRANSCRIPT, health=health))
        assert verifier.calls and verified.decisions[0].verification == YES


def test_an_untrusted_transcript_is_analyzed_unverified_and_its_minutes_say_so(repo, meeting):
    """End to end through the analysis step, with the real minutes renderer."""
    from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
    from teams_recorder.domain import TranscriptHealth
    degraded = Transcript(TRANSCRIPT.segments, health=TranscriptHealth(0.4, 10, 30, True))
    repo.seed(meeting, {AUDIO}, transcript=degraded)
    verifier = FakeClaimVerifier({ClaimRef(ClaimKind.DECISION, "0"): YES})

    result = AnalyzeMeeting(repo, FakeAnalyzer(), MarkdownMinutesRenderer(), VerifyAnalysis(verifier)).execute(meeting.id)

    assert verifier.calls == [] and result.decisions[0].verification is None
    assert Minutes.NOT_VERIFIED in repo.minutes[meeting.id]
