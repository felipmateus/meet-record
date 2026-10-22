# Review round 2: language-detection (spec)

- Round: 2 · Created: 2026-10-22T00:02:17Z · Reviewer: claude-code · Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md`, `adrs/adr-001.md`, checked against the current source (no code for this feature exists yet).
- Recommendation: approve after the fixes below. No blocking (critical or high) issues.
- New issues: 3 (critical 0, high 0, medium 1, low 2): `issue_001.md`, `issue_002.md`, `issue_003.md`.
- Round 1: 11 of 11 verified. None set back to `pending`. No round-1 status was changed.

## Round-1 verification

| Issue | Result | Evidence in the current spec files |
|---|---|---|
| 001 fallback single source | verified | `_spec.md:229-241` (`language` is the fallback and never `"auto"`; `__post_init__`; container passes `settings.fallback_language`), `:297`, `:319`, Safety Invariant 6 `:400`; `_tests.md` UT-040, UT-044, UT-045, and the UT-007–012 preamble passing `fallback="pt"`. Still positional: `container.py:130`. Moving it to the keywords that `_spec.md:241` names is what keeps the new fields from taking `max_loop_share` and the others; UT-040 and mypy would catch a shift. |
| 002 WHISPER_NO_LANGUAGE | verified | `_spec.md:191, 265, 307, 371`; `_dx.md:163`; US-003.EC-2 (`_user_stories.md:72`); UT-016, IT-002; ADR Implementation Notes. `LANGUAGE_NO_ANSWER` appears in none of the five files (grep). |
| 003 purge and lock wording | verified | `_spec.md:83, 381`; Safety Invariant 4 (`:398`) no longer claims the lock protects the audio; `retention.py` in File References `:424`. |
| 004 timing | verified | `_spec.md:68, 108, 326, 380`; US-001.EC-3; ADR `:25, :67`. All agree: about 0.6 s plus about 2 s per sample, about 25 s at 12. |
| 005 FakeMinutesRenderer and RenderMinutes | verified | `_spec.md:324, 358, 422`; UT-073; matrix row US-006.AC-3/AC-4. |
| 006 codec isinstance and RepositoryError | verified | `_spec.md:290` (isinstance, `Err.BAD_LANGUAGE_DETECTION`, `ValueError` for an unknown reason, `_decode` mapping, `AttributeError` hole); UT-043 goes through `FsMeetingRepository.load_transcript` with three shapes. |
| 007 curator wording | verified | `_spec.md:37` no longer says the curator is told the language. The plan is still incomplete in a separate way: the curator's `<task>` block contradicts the new rule (new issue 001). |
| 008 `language_detector` naming | verified | `_spec.md:150, 230, 241`; `_tests.md:7, 114, 115, 167` (E2E-001 patches `language_detector` and leaves the call `detector` alone; exactly one `--log` line). |
| 009 golden-path minutes and Language slot | verified | `_dx.md:35-43, 73`; US-005.EC-1; E2E-002 (`--loop-always`). |
| 010 `too-few-votes` | verified | Present everywhere reasons are listed: `_spec.md:48` (Business Rules), `:189` (Core Interfaces), `:276` (Data Models table); `_dx.md:87, 144`; US-003.EC-1, US-005.AC-6; UT-012, UT-062a; matrix "six forms". |
| 011 basename regex | verified | `_spec.md:264, 266`; ADR Implementation Notes; UT-015a. The apostrophe case now works (checked with Python `re`). A gap remains for bare names (new issue 002). |

## Areas round 1 did not reach

- **(a) `test_no_hardcoded_strings.py`: no trip.** The guard flags only literals with a space (`_is_prose`: longer than 3 characters, contains a space, does not start with `-`) outside `constants.py`, `messages.py` and `domain/status.py`. The `LanguageReason` values (`"no-usable-sample"` and the others) have no space, the same as `SpeakerReason` in `domain/speakers.py:25-32`, which already passes. The two `Parse` regexes are in `constants.py`, an allowed module. Nothing more needs to be in the spec for the guard. One note on AGENTS.md:110-113 and :133, which the guard does not check because the words have no space: the language-name maps (`en` → `English` for the prompt header, `en` → `inglês` for the minutes) belong in `messages.Prompt` and `messages.Minutes`, because Portuguese is allowed only there. The spec does not say where they live (Assumptions `:437`).
- **(b) Curator, story writer, excerpts.** `domain/excerpts.py` does not depend on the language (it uses timestamps and windows). The story writer sees tagged blocks and the analyses' context fields, never the transcript, and `prompts/stories_system.md:24` already asks for Portuguese. The curator gets English excerpts and quotes, but its message ends with `Prompt.CURATE_TASK` step 7 "Write all content in Brazilian Portuguese", and the plan does not touch it (issue 001).
- **(c) mypy** (`pyproject.toml`: `check_untyped_defs`, `no_implicit_optional`, not strict). The planned signatures type-check. `LanguageRules()` as a function default has a precedent in `LabelRules()` (`domain/speakers.py:193`). As a dataclass field default in `TranscribeMeeting` it is allowed, because a frozen dataclass with `eq` is hashable. `Sequence` from `typing` matches `domain/excerpts.py`. `@runtime_checkable` matches every port in `ports.py`. `ports.py` imports from `teams_recorder.domain`, so the new names need to be re-exported in `domain/__init__.py`; that is a detail for the tasks. `domain/models.py` importing `domain/language.py` creates no import cycle, as long as `language.py` imports nothing from `models`.

## Well done

- The fallback now has one source, and both a test and an invariant guard it: whisper can no longer get `-l auto`.
- The fail-soft path is consistent in every file: the adapter raises, the use case logs and records `detection-failed`, and no `error.txt` is written.
- The arithmetic in the tests checks out: UT-001, UT-005, the golden path (52.3 min gives 11 samples) and E2E-001 (3 min gives 3 samples) follow from the offset rule.

Next step: dispatch the `fixer` with `issue_001.md`–`issue_003.md`, or run `/cy-fix-reviews language-detection`.

## Fix status (2026-10-21)

The three findings were triaged `VALID` and resolved in `_spec.md`, `_tests.md` and `_dx.md`, following the user's choice to apply every review finding. The language-name maps the review asked about (area a) are now stated in `_spec.md` › Data Models: `messages.Prompt.LANGUAGE_NAMES` and `messages.Minutes.LANGUAGE_NAMES`. This round's run log moved to `docs/run-logs/`.
