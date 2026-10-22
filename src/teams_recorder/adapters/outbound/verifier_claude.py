"""ClaimVerifier backed by a StructuredTransport: one model call per meeting checks every claim of the analysis
against the transcript (docs/tasks/prd-fidelity-guard, task 3.0; prototype `verify_meeting` in scripts/fidelity_eval.py).

The model judges each claim on several axes (support, owner, date, tentative, sensitive); the mapping to a
single confirmed/unconfirmed status is done here, in code, as the prototype's `l1_flag` did.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel, Field

from teams_recorder.adapters.outbound.llm_schema import language_line, load_prompt
from teams_recorder.adapters.outbound.llm_transport import StructuredTransport
from teams_recorder.constants import Audio, Llm, VerdictSupport, Verify
from teams_recorder.domain import (
    Analysis,
    AnalysisError,
    ClaimKind,
    ClaimRef,
    Meeting,
    Transcript,
    Verification,
    VerificationStatus,
    claims,
    excerpt_window,
)
from teams_recorder.messages import Err, Minutes, Prompt


class VerdictOut(BaseModel):
    id: str = Field(description=Prompt.FIELD_VERDICT_ID)
    support: VerdictSupport = Field(description=Prompt.FIELD_SUPPORT)
    owner_evident: bool | None = Field(description=Prompt.FIELD_OWNER_EVIDENT)
    date_said: bool | None = Field(description=Prompt.FIELD_DATE_SAID)
    tentative: bool = Field(description=Prompt.FIELD_TENTATIVE)
    sensitive: bool = Field(description=Prompt.FIELD_SENSITIVE)
    reason: str = Field(description=Prompt.FIELD_REASON)


class VerifyOut(BaseModel):
    verdicts: list[VerdictOut]


@dataclass(frozen=True)
class Claim:
    """A claim as the model sees it: an id local to the call, the owner as a name, the date in ISO format."""

    id: str
    ref: ClaimRef
    text: str
    owner: str | None = None    # None: no owner, or unknown
    due: str | None = None      # ISO date
    at: str | None = None       # HH:MM:SS


def claims_of(analysis: Analysis, user_name: str = "") -> list[Claim]:
    """The analysis's claims (domain `claims`) with ids c1, c2, ...; the recording owner is named as the prototype
    did, so the model can match "Felipe, você manda..." to the action."""
    def owner(raw: str | None) -> str | None:
        if raw == Llm.OWNER_SELF:
            return user_name or Prompt.OWNER_SELF
        return None if not raw or raw == Llm.OWNER_UNKNOWN else raw

    return [Claim(f"c{n}", c.ref, c.text, owner(c.owner), c.due.isoformat() if c.due else None, c.at)
            for n, c in enumerate(claims(analysis), 1)]


def _seconds(at: str | None) -> int | None:
    parts = (at or "").strip().split(":")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    h, m, s = (int(p) for p in parts)
    return h * 3600 + m * 60 + s


def transcript_for(transcript: Transcript, claims: list[Claim], max_chars: int = Verify.MAX_TRANSCRIPT_CHARS,
                   window: int = Verify.WINDOW_SECONDS) -> tuple[str, bool]:
    """The transcript the model reads, and whether it is an excerpt.

    Whole when it fits in `max_chars`. Longer, it keeps the start (up to `max_chars`, for claims without a
    timestamp: deadlines, participants) plus the lines within `window` seconds of each claim's timestamp,
    in order, with a gap marker where lines were left out.
    """
    full = transcript.as_timestamped_text()
    if len(full) <= max_chars:
        return full, False
    times = [t for t in (_seconds(c.at) for c in claims) if t is not None]
    return excerpt_window(transcript, times, window, Prompt.EXCERPT_GAP, head_chars=max_chars), True


def describe(claim: Claim) -> str:
    line = Prompt.CLAIM_LINE.format(id=claim.id, kind=claim.ref.kind.value, text=claim.text)
    if claim.owner:
        line += Prompt.CLAIM_OWNER.format(owner=claim.owner)
    if claim.due:
        line += Prompt.CLAIM_DUE.format(due=claim.due)
    if claim.at:
        line += Prompt.CLAIM_AT.format(at=claim.at)
    return line


def to_verification(claim: Claim, verdict: VerdictOut | None) -> Verification:
    """One status per claim: unconfirmed when the transcript does not fully support it, when its owner or date
    is not evident, when a decision is only tentative, or when it carries sensitive data."""
    if verdict is None:
        return Verification(VerificationStatus.UNCONFIRMED, Minutes.REASON_NO_VERDICT)
    doubtful = (
        verdict.support is not VerdictSupport.SUPPORTED
        or (claim.owner is not None and verdict.owner_evident is False)
        or (claim.due is not None and verdict.date_said is False)
        or (claim.ref.kind is ClaimKind.DECISION and verdict.tentative)
        or verdict.sensitive
    )
    status = VerificationStatus.UNCONFIRMED if doubtful else VerificationStatus.CONFIRMED
    return Verification(status, " ".join(verdict.reason.split()))   # one line: it is shown in tables and lists


@dataclass
class ClaudeClaimVerifier:
    transport: StructuredTransport
    prompt_path: Path | None = None      # loaded on first use ...
    system_prompt: str | None = None     # ... or given directly (tests)
    user_name: str = ""
    max_transcript_chars: int = Verify.MAX_TRANSCRIPT_CHARS
    window_seconds: int = Verify.WINDOW_SECONDS

    def _system(self) -> str:
        if self.system_prompt is None:
            if self.prompt_path is None:
                raise AnalysisError(Err.NO_SYSTEM_PROMPT.format(who=type(self).__name__))
            self.system_prompt = load_prompt(self.prompt_path)
        return self.system_prompt

    def user_message(self, meeting: Meeting, claims: list[Claim], transcript: Transcript) -> str:
        text, excerpt = transcript_for(transcript, claims, self.max_transcript_chars, self.window_seconds)
        header = [Prompt.MEETING_DATE.format(date=meeting.started_at.date().isoformat(), weekday=Prompt.WEEKDAYS[meeting.started_at.weekday()])]
        if self.user_name:
            header.insert(0, Prompt.USER_NAME.format(name=self.user_name))
        if transcript.language != Audio.DEFAULT_LANGUAGE:
            header.append(language_line(transcript.language))
        if transcript.roster:
            header.append(Prompt.ROSTER.format(names=", ".join(transcript.roster)))
        return ("\n".join(header) + (Prompt.VERIFY_EXCERPTS if excerpt else Prompt.VERIFY_TRANSCRIPT) + text
                + Prompt.VERIFY_CLAIMS + "\n".join(describe(c) for c in claims))

    def verify(self, meeting: Meeting, analysis: Analysis, transcript: Transcript) -> dict[ClaimRef, Verification]:
        claims = claims_of(analysis, self.user_name)
        if not claims:
            return {}
        out = self.transport.complete(
            self._system(), self.user_message(meeting, claims, transcript), VerifyOut,
            tag=f"verify:{meeting.id}", extra={"meeting": meeting.id},
        )
        by_id = {v.id.strip(): v for v in out.verdicts}   # verdicts for ids that were not asked are ignored
        return {c.ref: to_verification(c, by_id.get(c.id)) for c in claims}
