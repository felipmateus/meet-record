"""Claim verification after the analysis (tasks/prd-fidelity-guard, task 3.0)."""
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
    claim_refs,
    combine,
    participant_heard,
    sensitive_data,
    with_verifications,
)
from teams_recorder.messages import Log, Minutes

log = logging.getLogger(__name__)

_UNCONFIRMED = VerificationStatus.UNCONFIRMED


@dataclass
class VerifyAnalysis:
    """Marks each decision, action, deadline and participant confirmed or unconfirmed, never deleting any.

    Two sources: the verifier (a model reading the transcript) and two checks done in code, kept because they
    caught errors without rejecting correct claims (PRD decision 3): sensitive personal data in a claim, and a
    participant who neither speaks nor is addressed. A code check can only make a claim unconfirmed. When the
    verifier fails, its claims stay unverified and the code checks still apply; verification never fails the
    analysis.
    """

    verifier: ClaimVerifier | None = None
    user_name: str = ""

    def execute(self, meeting: Meeting, analysis: Analysis, transcript: Transcript) -> Analysis:
        verdicts: dict[ClaimRef, Verification] = {}
        if self.verifier is not None and claim_refs(analysis):
            try:
                verdicts = dict(self.verifier.verify(meeting, analysis, transcript))
            except Exception as exc:  # noqa: BLE001 - verification is advisory: it never blocks the analysis
                log.warning(Log.VERIFY_FAILED, meeting.id, exc)
        for ref, flag in self._code_checks(analysis, transcript).items():
            verdicts[ref] = combine(verdicts.get(ref), flag) or flag
        verified = with_verifications(analysis, verdicts)
        statuses = [v.status for v in verdicts.values()]
        log.info(Log.VERIFIED, meeting.id, statuses.count(VerificationStatus.CONFIRMED), statuses.count(_UNCONFIRMED))
        return verified

    def _code_checks(self, analysis: Analysis, transcript: Transcript) -> dict[ClaimRef, Verification]:
        flags: dict[ClaimRef, Verification] = {}
        texts = [
            *((ClaimRef(ClaimKind.DECISION, str(i)), d.text) for i, d in enumerate(analysis.decisions)),
            *((ClaimRef(ClaimKind.ACTION, a.id), a.description) for a in analysis.all_actions),
            *((ClaimRef(ClaimKind.DEADLINE, str(i)), d.what) for i, d in enumerate(analysis.deadlines)),
        ]
        for ref, text in texts:
            if sensitive_data(text, Verify.SENSITIVE):
                flags[ref] = Verification(_UNCONFIRMED, Minutes.REASON_SENSITIVE)
        for name in analysis.participants:
            if not participant_heard(name, transcript, self.user_name, Verify.NAME_PARTICLES, Verify.ADDRESS):
                flags[ClaimRef(ClaimKind.PARTICIPANT, name)] = Verification(_UNCONFIRMED, Minutes.REASON_NOT_HEARD)
        return flags
