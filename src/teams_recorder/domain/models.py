"""Domain entities and value objects. No I/O, no external dependencies."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

from .language import LanguageDetection

MEETING_ID_FORMAT = "%Y-%m-%d_%H-%M-%S"


def meeting_id_for(started_at: datetime) -> str:
    return started_at.strftime(MEETING_ID_FORMAT)


def _new_action_id() -> str:
    return uuid4().hex[:8]


@dataclass
class Meeting:
    id: str
    started_at: datetime
    ended_at: datetime | None = None
    pid: int | None = None
    title: str | None = None

    @classmethod
    def start(cls, started_at: datetime, pid: int | None = None, title: str | None = None) -> "Meeting":
        return cls(id=meeting_id_for(started_at), started_at=started_at, pid=pid, title=title)

    @property
    def day(self) -> date:
        return self.started_at.date()

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None   # display name of who said it, when known (domain/speakers.label_segments)


_WORD = re.compile(r"\w+")
_ANNOTATION = re.compile(r"^[\[(*♪].*[\])*♪]$")   # whisper's non-speech markers: [BLANK_AUDIO], (música), *risos*, ♪


def is_speech(text: str) -> bool:
    """Whether a segment carries spoken words: not empty, and not a non-speech marker such as [BLANK_AUDIO]."""
    stripped = text.strip()
    return bool(_WORD.search(stripped)) and not _ANNOTATION.match(stripped)


@dataclass(frozen=True)
class LabelSummary:
    """What speaker labelling did to a transcript (domain/speakers.label_segments); absent on transcripts made before it."""

    labelled: int              # eligible segments that got a label
    eligible: int              # segments with speech text and a positive duration
    reason: str | None = None  # a SpeakerReason when labelled == 0, else None

    @property
    def share(self) -> float | None:
        """Labelled over eligible; None when no segment was eligible."""
        return self.labelled / self.eligible if self.eligible else None


@dataclass(frozen=True)
class CaptureStats:
    """What teams-tap counted while recording a track (tap.stats.json)."""

    written_seconds: float
    padded_seconds: float          # silence written where no audio arrived
    short_padded_seconds: float    # the part of it in pads too short to be logged as gaps (under 0.5 s)
    gaps: int                      # pads logged as gaps
    device_rates: tuple[float, ...] = ()   # rates the device ran at, in order (empty: written before 2026-10-14)

    @property
    def short_padding_share(self) -> float:
        return self.short_padded_seconds / self.written_seconds if self.written_seconds > 0 else 0.0


RETRY_KEEP_SHARE = 0.85   # a pass that is not degraded wins when it keeps this share of a degraded pass's minutes with text


@dataclass(frozen=True)
class TranscriptHealth:
    """How usable a transcript is (see domain/health.py, which computes it)."""

    loop_share: float        # share of segments inside repetition loops, 0..1
    covered_minutes: int     # minutes with speech text outside the loops
    total_minutes: int
    degraded: bool           # loop_share above the configured maximum
    uncovered: tuple[tuple[int, int], ...] = ()  # minutes without text, as half-open [start, end) runs
    retried: bool = False    # a second pass with the anti-loop settings ran (the healthier of the two was kept)
    rate_mismatch: bool = False        # the Teams track was recorded at the wrong sample rate (see domain/health.py)
    short_padding_share: float = 0.0   # share of the Teams track padded in short pads, the evidence for rate_mismatch

    @property
    def untrusted(self) -> bool:
        """Whether the transcript cannot serve as evidence: still degraded after the retry, or made from a Teams track
        recorded at the wrong sample rate. Hallucinated text reads as fluent speech, so checking a claim against it
        would confirm what was invented (PRD decision 4)."""
        return self.degraded or self.rate_mismatch

    def is_healthier_than(self, other: "TranscriptHealth") -> bool:
        """Which of two passes of the same audio to keep (both measured against the same duration).

        A pass that is not degraded (loop share at most max_loop_share) beats a degraded one when it keeps at
        least RETRY_KEEP_SHARE of the other's minutes with text: a minute counts as covered by any line outside a
        loop, so a pass mostly in loops can still look as if it covers more (2026-10-14_15-00-56: 69% of segments
        in loops and 35 of 37 minutes, against a retry with no loops and 31). A pass that loses more than that
        never wins, so an empty or cut-short retry never replaces a first pass with usable text. Otherwise: more
        minutes with text, then fewer loops.
        """
        if self.degraded != other.degraded:
            clean, looped = (other, self) if self.degraded else (self, other)
            clean_wins = clean.covered_minutes >= RETRY_KEEP_SHARE * looped.covered_minutes
            return clean_wins == (clean is self)
        return (-self.covered_minutes, self.loop_share) < (-other.covered_minutes, other.loop_share)

    def uncovered_ranges(self) -> list[str]:
        """The minutes without text as transcript times, e.g. ["00:00:00–00:59:00"]."""
        return [f"{clock_time(start * 60)}–{clock_time(end * 60)}" for start, end in self.uncovered]


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)
    language: str = "pt"
    health: TranscriptHealth | None = None  # None: transcribed before the health check existed
    roster: tuple[str, ...] = ()            # names seen in the Teams meeting window, in order of first appearance
    user_label: str | None = None           # the label the recording owner's lines carry, when labelling ran
    labels: LabelSummary | None = None      # None: labelling never ran (transcripts made before speaker attribution)
    language_detection: LanguageDetection | None = None   # how `language` was chosen; None: a fixed language, or made before detection existed

    @property
    def text(self) -> str:
        return "\n".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def duration_seconds(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    @property
    def speakers(self) -> list[str]:
        """Distinct speaker labels, in order of first appearance."""
        return list(dict.fromkeys(s.speaker for s in self.segments if s.speaker))

    def as_timestamped_text(self) -> str:
        """One line per segment: "[HH:MM:SS] text", or "[HH:MM:SS] Name: text" when the segment has a speaker."""
        return "\n".join(timestamped_line(s) for s in self.segments)


def timestamped_line(segment: Segment) -> str:
    """A transcript line as transcript.txt and the model messages show it."""
    speaker = f"{segment.speaker}: " if segment.speaker else ""
    return f"[{clock_time(segment.start)}] " + speaker + segment.text.strip()


def clock_time(seconds: float) -> str:
    """A transcript time as HH:MM:SS, the format of transcript.txt and of every `at` in an analysis."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class ActionStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    OVERDUE = "overdue"   # decode only: files written before the planner was removed may hold it; nothing sets it any more


class Priority(StrEnum):
    """Urgency stated (or clearly implied) in the meeting; absent when nobody said it."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionKind(StrEnum):
    """What kind of work an action is. A tagged item the story writer classes as feature or bug becomes a user story,
    one it classes as technical or operation becomes a task card; any other kind is not drafted."""

    FEATURE = "feature"              # a change in how the product behaves → user story
    BUG = "bug"                      # something that should work and does not → user story (bug)
    TECHNICAL = "technical"          # engineering work without direct user value: estimate, spike, mock → task card
    OPERATION = "operation"          # deploy, access, infrastructure, environment → task card
    MANAGEMENT = "management"        # process, reports, metrics, prioritisation → no story
    COMMUNICATION = "communication"  # e-mail, meeting, follow-up, review → no story


class VerificationStatus(StrEnum):
    CONFIRMED = "confirmed"      # the transcript supports the claim
    UNCONFIRMED = "unconfirmed"  # it does not, or the check could not tell: shown as unconfirmed, never deleted


@dataclass(frozen=True)
class Verification:
    """Whether a claim of the analysis (decision, action, deadline, participant) was confirmed against the
    transcript, and why. A claim without one was not verified (analyses made before the fidelity guard)."""

    status: VerificationStatus
    reason: str = ""


class ClaimKind(StrEnum):
    """The claims of an analysis that are verified against the transcript."""

    DECISION = "decision"
    ACTION = "action"
    DEADLINE = "deadline"
    PARTICIPANT = "participant"
    STATUS_UPDATE = "status_update"


@dataclass(frozen=True)
class ClaimRef:
    """Which claim of an analysis a verification belongs to: an action by its id, a decision or deadline by its
    position in the analysis, a participant by name."""

    kind: ClaimKind
    key: str


@dataclass(frozen=True)
class Claim:
    """A verifiable statement of an analysis, with the fields a reader would trust (see verification.claims)."""

    ref: ClaimRef
    text: str
    owner: str | None = None   # as written in the analysis, including Llm's "usuário" / "indefinido" markers
    due: date | None = None
    at: str | None = None      # HH:MM:SS where it was said, when the analysis gave it


class MeetingType(StrEnum):
    STANDUP = "standup"
    CLIENT = "client"
    PROJECT_REVIEW = "project_review"
    ONE_ON_ONE = "one_on_one"
    OTHER = "other"


@dataclass
class Action:
    description: str
    owner: str
    source_meeting: str
    due: date | None = None
    status: ActionStatus = ActionStatus.OPEN
    id: str = field(default_factory=_new_action_id)
    priority: Priority | None = None
    at: str | None = None  # transcript timestamp (HH:MM:SS) where it was said, for verification
    kind: ActionKind | None = None  # None: extracted before actions were classified
    verification: Verification | None = None  # None: not verified
    for_whom: str | None = None  # who receives or waits for the result, when the meeting said so


@dataclass(frozen=True)
class Decision:
    text: str
    at: str | None = None  # transcript timestamp (HH:MM:SS) where it was decided
    verification: Verification | None = None  # None: not verified


@dataclass(frozen=True)
class Topic:
    title: str
    points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Deadline:
    what: str
    when: date | None
    who: str
    verification: Verification | None = None  # None: not verified


class StatusChange(StrEnum):
    """What a meeting said happened to work that already existed."""

    DONE = "done"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DELAYED = "delayed"
    DUE_CHANGED = "due_changed"
    REASSIGNED = "reassigned"
    CANCELLED = "cancelled"


@dataclass
class StatusUpdate:
    """Progress reported in a meeting on work that existed before it. The analyzer does not know which item of the
    activities document it concerns: `about` is in the meeting's words and the curator matches it."""

    about: str
    change: StatusChange
    who: str                       # Llm.OWNER_SELF, a name, or Llm.OWNER_UNKNOWN
    evidence: str                  # literal quote, at most 20 words, hedges kept
    at: str | None = None          # HH:MM:SS where it was said
    new_due: date | None = None    # for due_changed and delayed
    new_owner: str | None = None   # for reassigned
    verification: Verification | None = None  # None: not verified


@dataclass
class Analysis:
    meeting_id: str
    summary: str
    decisions: list[Decision] = field(default_factory=list)
    my_actions: list[Action] = field(default_factory=list)
    others_actions: list[Action] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_meetings: list[str] = field(default_factory=list)
    title: str = ""
    purpose: str = ""
    meeting_type: MeetingType = MeetingType.OTHER
    participants: list[str] = field(default_factory=list)  # people who speak or are addressed (no diarization yet)
    topics: list[Topic] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    participant_checks: dict[str, Verification] = field(default_factory=dict)  # by name, as in `participants`; absent: not verified
    status_updates: list[StatusUpdate] = field(default_factory=list)  # progress on earlier work, in the order it was said

    @property
    def all_actions(self) -> list[Action]:
        return [*self.my_actions, *self.others_actions]


@dataclass(frozen=True)
class Publication:
    """Where a story was published: the destination and the destination's id for the item."""

    destination: str
    ref: str
    published_at: datetime


SUGGESTION = "suggestion"   # Criterion.source of a criterion nobody said in the meetings: the writer proposes it


@dataclass(frozen=True)
class Criterion:
    """An acceptance criterion and where it comes from (fidelity guard, FR6): the transcript timestamp (HH:MM:SS) of
    what was said, or SUGGESTION when the story writer proposes it. None: drafted before provenance existed."""

    text: str
    source: str | None = None

    @property
    def suggested(self) -> bool:
        return self.source == SUGGESTION


@dataclass
class UserStory:
    """A user story (or a task card) drafted from an item of the activities document. A draft until the user publishes it."""

    title: str
    narrative: str  # "As a <persona>, I want <capability>, so that <benefit>", in the user's language
    acceptance_criteria: list[Criterion] = field(default_factory=list)
    details: str = ""  # other sections the user's story guide asks for, in Markdown
    open_questions: list[str] = field(default_factory=list)
    source_action_ids: list[str] = field(default_factory=list)  # planner-era drafts only; a block story has none
    source_meetings: list[str] = field(default_factory=list)
    priority: Priority | None = None  # set by the story writer from the item and its meetings' analyses
    due: date | None = None           # likewise
    id: str = field(default_factory=_new_action_id)
    publications: list[Publication] = field(default_factory=list)
    kind: ActionKind | None = None   # feature/bug for stories, technical/operation for task cards; None if unclassified
    verification: Verification | None = None   # a planner-era task card's: its action's, so an unconfirmed card is published marked
    source_text: str | None = None   # the tagged block verbatim, its first line the tagged line; None on planner-era drafts

    def publication(self, destination: str) -> Publication | None:
        return next((p for p in self.publications if p.destination == destination), None)

    @property
    def is_task_card(self) -> bool:
        return self.kind in (ActionKind.TECHNICAL, ActionKind.OPERATION)


@dataclass(frozen=True)
class SkippedAction:
    """A tagged block (or, on a planner-era draft, an action) that did not become a story, and why."""

    action_id: str  # the per-run block ref (`b1`) for a block, never looked up after the call; the action's id on planner-era drafts
    reason: str
    duplicate_of: str | None = None  # id of an existing story that already covers it
    source_line: str | None = None   # the block's tagged line verbatim: what a later render and a later run read; None on planner-era entries


@dataclass
class StoryDrafts:
    """The user story drafts of one day; each story records where it was published."""

    day: date
    stories: list[UserStory] = field(default_factory=list)
    skipped: list[SkippedAction] = field(default_factory=list)

    @property
    def has_publications(self) -> bool:
        return any(story.publications for story in self.stories)
