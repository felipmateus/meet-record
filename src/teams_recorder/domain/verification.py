"""Claim verification: which claims an analysis makes, the two checks done in code, and how verifications
are combined and written back. Pure functions; the patterns and labels come from the caller."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import Iterable

from .models import Action, Analysis, Claim, ClaimKind, ClaimRef, Transcript, Verification, VerificationStatus


def claims(analysis: Analysis) -> list[Claim]:
    """Every verifiable claim of an analysis, in reading order: decisions and deadlines by position, actions by id,
    participants by name. The one place that says which claims there are and how they are keyed."""
    return [
        *(Claim(ClaimRef(ClaimKind.DECISION, str(i)), d.text, at=d.at) for i, d in enumerate(analysis.decisions)),
        *(Claim(ClaimRef(ClaimKind.ACTION, a.id), a.description, a.owner, a.due, a.at) for a in analysis.all_actions),
        *(Claim(ClaimRef(ClaimKind.DEADLINE, str(i)), d.what, d.who, d.when) for i, d in enumerate(analysis.deadlines)),
        *(Claim(ClaimRef(ClaimKind.PARTICIPANT, name), name) for name in dict.fromkeys(analysis.participants)),
    ]


def claim_refs(analysis: Analysis) -> list[ClaimRef]:
    return [c.ref for c in claims(analysis)]


def unconfirmed(v: Verification | None) -> bool:
    """Checked and not confirmed. A claim never checked (None) is not unconfirmed: it is shown as before."""
    return v is not None and v.status is VerificationStatus.UNCONFIRMED


def unconfirmed_reason(v: Verification | None) -> str | None:
    """The reason to show next to an unconfirmed claim, on one line ("" when there is none); None when the claim is
    not unconfirmed. A reason written by the model may hold line breaks, which would break a Markdown table or list."""
    if v is None or not unconfirmed(v):
        return None
    return " ".join(v.reason.split())


def verifications(analysis: Analysis) -> list[Verification | None]:
    """The verification of every claim of an analysis (see `claims`), None where a claim was not verified."""
    found: list[Verification | None] = []
    for claim in claims(analysis):
        if claim.ref.kind is ClaimKind.PARTICIPANT:
            found.append(analysis.participant_checks.get(claim.text))
        else:
            found.append(_claim_verification(analysis, claim.ref))
    return found


def _claim_verification(analysis: Analysis, ref: ClaimRef) -> Verification | None:
    if ref.kind is ClaimKind.DECISION:
        return analysis.decisions[int(ref.key)].verification
    if ref.kind is ClaimKind.DEADLINE:
        return analysis.deadlines[int(ref.key)].verification
    return next((a.verification for a in analysis.all_actions if a.id == ref.key), None)


def combine(first: Verification | None, second: Verification | None) -> Verification | None:
    """Two verdicts on one claim: unconfirmed if either is, with both reasons; None only if neither checked it."""
    if first is None or second is None:
        return first or second
    if first.status is second.status:
        reason = "; ".join(r for r in dict.fromkeys((first.reason, second.reason)) if r)
        return Verification(first.status, reason)
    return first if first.status is VerificationStatus.UNCONFIRMED else second


def with_verifications(analysis: Analysis, verdicts: dict[ClaimRef, Verification]) -> Analysis:
    """A copy of the analysis with each claim's verification set from `verdicts`; claims not in it keep theirs.
    The analysis passed in is not changed (actions are copied, not edited)."""
    def get(kind: ClaimKind, key: str, current: Verification | None) -> Verification | None:
        return verdicts.get(ClaimRef(kind, key), current)

    def actions(items: list[Action]) -> list[Action]:
        return [replace(a, verification=get(ClaimKind.ACTION, a.id, a.verification)) for a in items]

    checks = dict(analysis.participant_checks)
    for name in analysis.participants:
        found = verdicts.get(ClaimRef(ClaimKind.PARTICIPANT, name))
        if found is not None:
            checks[name] = found
    return replace(
        analysis,
        decisions=[replace(d, verification=get(ClaimKind.DECISION, str(i), d.verification)) for i, d in enumerate(analysis.decisions)],
        my_actions=actions(analysis.my_actions),
        others_actions=actions(analysis.others_actions),
        deadlines=[replace(d, verification=get(ClaimKind.DEADLINE, str(i), d.verification)) for i, d in enumerate(analysis.deadlines)],
        participant_checks=checks,
    )


def normalized(text: str) -> str:
    """Lower case without accents, so "Saúde" and "saude" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def sensitive_data(text: str, patterns: Iterable[str]) -> bool:
    """Whether a claim carries sensitive personal data (health, religion, politics...), by regular expressions
    matched against the normalized text."""
    plain = normalized(text)
    return any(re.search(p, plain) for p in patterns)


def participant_heard(name: str, transcript: Transcript, user_name: str, particles: Iterable[str], address: Iterable[str]) -> bool:
    """Whether a participant is a person in the meeting rather than someone mentioned once: the recording's owner,
    a name said at least twice, or a name someone addresses (`address` templates with `{name}`, e.g. a greeting).

    The prototype's rule, measured in the evaluation; a person named twice passes even if only mentioned.
    """
    skip = set(particles)

    def tokens(text: str) -> list[str]:
        return [t for t in re.split(r"[\s()]+", normalized(text)) if len(t) >= 2 and t not in skip]

    names, user = tokens(name), set(tokens(user_name))
    if not names:
        return False
    if user and (user <= set(names) or set(names) <= user):   # "Felipe" and "Felipe Mateus" are the owner
        return True
    # segments joined by spaces, as the prototype did: whisper often splits right after "Bom dia,"
    text = " ".join(normalized(s.text.strip()) for s in transcript.segments)
    plain = " " + " ".join(re.findall(r"\w+", text)) + " "
    if max(plain.count(f" {n} ") for n in names) >= 2:
        return True
    return any(re.search(template.format(name=re.escape(n)), text) for n in names for template in address)
