# Review round 4: language-detection (spec)

- Round: 4 · Created: 2026-10-22T02:12:24Z · Reviewer: claude-code · Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`, checked against the current source. No code for this feature exists yet. `_tasks.md`, `task_01.md` and `task_02.md` are an interrupted draft and were left out on purpose.
- Recommendation: safe to approve with follow-ups. Nothing is critical or high. The round is **not clean**: two reviews-003 issues went back to `pending`, and there are two new low issues.
- New issues: 2 (critical 0, high 0, medium 0, low 2).
- Prior issues: 2 resolved (reviews-003 002, 004), 2 still open and set back to `pending` (reviews-003 001, 003).

| Issue | Severity | Target | Defect |
|---|---|---|---|
| 001 | low | `_spec.md:333` | The docs-sync row misses `docs/prd/README.md:65` ("Portuguese because the meetings are in Portuguese"), `docs/prd/pages/09-activities.md:14` and `docs/guide/activities-and-stories.md:15`. All three say activities content is all Portuguese, with no quote exception. |
| 002 | low | `_spec.md:347` | Config Lifecycle says `UT-020–UT-024`, which leaves out UT-025, UT-026 and UT-025a (the settled both-modes validation). The `domain/language.py` row says `UT-001–UT-012`, which leaves out UT-012a–c. |

## Reviews-003 verification

| Issue | Was | Now | Evidence |
|---|---|---|---|
| 001 prompts change with no regression gate | valid | **pending** | The prose fixes hold (`_spec.md:54, 390`; UT-053 now covers line 43). Gate G3(a) cannot measure the change. `fidelity_eval.py defend` sends its own inline `VERIFY_SYSTEM` (`:396, 431`) and never reads `prompts/verify_system.md`. It resumes from `l1.json`: on a scratch copy of `data/wiki-eval/fidelity-2026-10-11/`, 0 of 42 jobs were left, so no call is made. `gate` reads the stale `defense_metrics.json` that `report` writes. And `gate` with its default `--config "L1 + L2"` printed **FAIL** (18% false positives against the 10% cap) before any change, so the "prints PASS" criterion cannot be met as written. Details and fix options are in the issue's Triage. |
| 002 docs-sync list | valid | resolved | `_spec.md:333, 436` list all six locations plus `enum-dictionary.md`, with what changes in each. |
| 003 "see the log" | valid | **pending** | The wording holds in every file. UT-063's new assertion, "through `CliRunner` … stderr has the warning", fails under this project's pytest: the logging plugin attaches root handlers, so `logging.lastResort` never fires. A scratch typer test gave `stderr == ''` under pytest 9.1.1 and typer 0.27.3, and passed with `-p no:logging`. Fix: assert with `caplog`, or through a subprocess. |
| 004 `Verify.ADDRESS` | valid | resolved | Every listed place carries the fix. At runtime, `participant_heard` with the extended pattern turns all five UT-054 positives from false to true, and the negatives stay false. |

## Settled points (reviews-003 `_summary.md`)

- E2E-002 per-audio fakes: consistent. `_tests.md` Strategy (`FakeLanguageDetector` keyed by audio path, `FakeTranscriber.by_audio`) matches E2E-002, and so does US-005.EC-1. `FakeTranscriber` (`tests/fakes/__init__.py:176-191`) and `looped_transcript()` (`:194`) exist. `degraded` depends on loop share only (`models.py`), so meeting A's short fake transcript is not degraded, as E2E-002 needs.
- `languages` validated in both modes: consistent in `_spec.md:56`, `_dx.md` Config table and Errors table, US-008.EC-5, UT-025a, and UT-021 ("ignored", meaning not used). The one stale pointer is `_spec.md:347` (new issue 002).
- Doctor line after the retry line: consistent in the `_dx.md` golden path and `trec doctor` section, US-007.AC-4, UT-067 and the Coverage Matrix. In code, `_check_transcript_health` ends with `RETRY_LINE` (`cli.py:293`) and `doctor` calls `_check_verification` next (`cli.py:236`), so the slot exists.

## Checked and correct

- Test IDs: 70 defined in `_tests.md`. Every one is in the Coverage Matrix once ranges are expanded, with no duplicates. No other file references an undefined ID.
- `Verify.ADDRESS` / UT-054: `participant_heard` normalizes the text but keeps punctuation, matches per name token and applies the templates with `re.search`, so `Hey, John` and `thank you, John` match through `,?`. One more point: the fidelity script's L2 participant check has its own hard-coded greeting regex (`fidelity_eval.py` `l2_flags`), so G3 does not measure the `ADDRESS` change either way. The spec claims only that Portuguese results "do not change", which is plausible: `thanks Ana` in Portuguese text now confirms Ana, a rare and benign case.
- The CLI's stderr behavior in a real process (`_dx.md:93-99`, `_spec.md:378`): with no handler configured, the warning goes to stderr through the last-resort handler, and `typer.echo` flushes, so it lands after `Transcribing <id>…`. Confirmed with the plugin disabled.
- G3(b) (analyzer and curator before/after on a scratch data dir, user sign-off) can be run, and its criteria are checkable by the user. It does not say how to get the "old" prompts (for example a worktree at the base commit). That is a non-blocking clarification, not a finding.

## Not reached

Nothing material. The analysis covered the areas the caller named first (verification, G3, UT-054, UT-063, docs-sync row, test IDs), then the settled points. ADR-001 and the unchanged sections were spot-read only, since three earlier rounds already went through them.

Next step: send reviews-003 `issue_001.md` and `issue_003.md` (now `pending`) and reviews-004 `issue_001.md`–`issue_002.md` to the `fixer`, or run `/cy-fix-reviews language-detection`.
