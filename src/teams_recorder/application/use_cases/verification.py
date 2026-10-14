"""Claim verification after the analysis (tasks/prd-fidelity-guard, tasks 3.0 and 7.0)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from teams_recorder.application.ports import ClaimVerifier
from teams_recorder.constants import Verify
from teams_recorder.domain import (
    Analysis,
    ClaimKind,
    ClaimRef,
    Meeting,
    Transcript,
    Verification,
    VerificationStatus,
    claims,
    combine,
    participant_heard,
    sensitive_data,
    with_verifications,
)
from teams_recorder.messages import Log, Minutes

log = logging.getLogger(__name__)


@dataclass
class VerifyAnalysis:
    """Marks each decision, action, deadline and participant confirmed or unconfirmed, never deleting any.

    Two sources: the verifier (a model reading the transcript) and two checks done in code, kept because they
    caught errors without rejecting correct claims (PRD decision 3): sensitive personal data in a claim, and a
    participant who neither speaks nor is addressed. A code check can only make a claim unconfirmed. When the
    verifier fails, its claims stay unverified and the code checks still apply; verification never fails the
    analysis.

    A transcript that cannot be trusted (still degraded, or from a Teams track recorded at the wrong sample rate) is
    not given to the verifier: it would confirm what the analysis took from the same hallucinated text (PRD decision
    4). Its claims stay unverified, as when the verifier fails, so none is confirmed; the minutes and the drafts
    document say so under the transcript banners, and the meeting still produces stories (PRD decision 9).
    """

    verifier: ClaimVerifier | None = None
    user_name: str = ""

    def execute(self, meeting: Meeting, analysis: Analysis, transcript: Transcript) -> Analysis:
        verdicts: dict[ClaimRef, Verification] = {}
        health = transcript.health
        if health is not None and health.untrusted:
            log.warning(Log.VERIFY_SKIPPED, meeting.id, health.degraded, health.rate_mismatch)
        elif self.verifier is not None and claims(analysis):
            try:
                verdicts = dict(self.verifier.verify(meeting, analysis, transcript))
            except Exception as exc:  # noqa: BLE001 - verification is advisory: it never blocks the (paid) analysis
                log.exception(Log.VERIFY_FAILED, meeting.id, exc)   # with the traceback: a bug must not pass for an outage
        for ref, flag in self._code_checks(analysis, transcript).items():
            verdicts[ref] = combine(verdicts.get(ref), flag) or flag
        verified = with_verifications(analysis, verdicts)
        statuses = [v.status for v in verdicts.values()]
        log.info(Log.VERIFIED, meeting.id, statuses.count(VerificationStatus.CONFIRMED), statuses.count(VerificationStatus.UNCONFIRMED))
        return verified

    def _code_checks(self, analysis: Analysis, transcript: Transcript) -> dict[ClaimRef, Verification]:
        flags: dict[ClaimRef, Verification] = {}
        for claim in claims(analysis):
            if claim.ref.kind is ClaimKind.PARTICIPANT:
                if not participant_heard(claim.text, transcript, self.user_name, Verify.NAME_PARTICLES, Verify.ADDRESS):
                    flags[claim.ref] = Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_NOT_HEARD)
            elif sensitive_data(claim.text, Verify.SENSITIVE):
                flags[claim.ref] = Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_SENSITIVE)
        return flags
