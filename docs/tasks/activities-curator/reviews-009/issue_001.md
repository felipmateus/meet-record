---
provider: manual
pr:
round: 9
round_created_at: 2026-10-20T16:08:59Z
status: resolved
file: src/teams_recorder/messages.py
line: 203
severity: low
author: claude-code
provider_ref:
---

# Issue 001: User-facing texts still describe the removed daily plan

## Review Comment

Task_14 removed the planner, `open_actions.json` and every `load_open_actions` path, and task_15 rewrote the docs. Three
texts still describe the old product:

1. `src/teams_recorder/messages.py:203`: `Cli.STATUS_CMD_HELP = "List meetings, the status of each one and open actions."`.
   `trec status` no longer lists open actions. It prints the meetings and the activities summary line
   (`cli.py:134`, `_activities_status_line(c.activities_summary().execute())`), and the repository has no open-actions
   list any more (`MeetingRepository.load_open_actions` was deleted from `application/ports.py`). `trec status --help` is
   therefore wrong.
2. `prompts/analyze_system.md:37`: "It decides where the action goes: features and bugs become user stories on the user's
   board, technical and operation work become task cards, and management and communication stay only in the daily plan."
   The analyzer prompt is re-read on every analysis, so the model is still told about a routing and a plan that no longer
   exist. After task_13, `kind` on an action decides nothing about stories: the story writer sets `kind` itself, from the
   `#história` block (`stories_claude.to_drafts`). The sentence should say what `kind` is used for now (for example,
   context for the curator and the minutes), or drop the routing clause.
3. `src/teams_recorder/messages.py:721`: the `Minutes` docstring justifies the Portuguese labels as the "same exception as
   the daily plan's section names". That exception no longer exists. AGENTS.md › English only now lists `Minutes`,
   `StoryDoc` and `ActivityDoc` instead.

Evidence: `grep -rn -i 'daily plan\|open actions' src prompts` returns these three lines (and `prompts/user_story_guide.md`,
which is the user's own guide and out of scope). Item 2 is the only one that reaches a model; none of them breaks a test.

Suggested fix: reword `STATUS_CMD_HELP` (for example, "List meetings, the status of each one and the activities
document."), fix the `kind` paragraph of `analyze_system.md` so it no longer mentions the daily plan or action routing, and
point the `Minutes` docstring at the AGENTS.md exception. Check `tests/unit/test_no_hardcoded_strings.py` and any test that
asserts on `STATUS_CMD_HELP`. A change to `analyze_system.md` affects the next analyses, so ask the user before relying on
it for the fidelity gates.

## Triage

- Decision: `VALID`
- Notes: all three texts were stale after the planner removal, and the reviewer's unfiled note was valid too: `cli._remove_legacy_planner()` called `_fail` when the legacy job's uninstall raised (`schtasks /Delete ... check=True` on Windows), so `trec agent restart`/`install` aborted before the daemon restarted.
  - `Cli.STATUS_CMD_HELP` now reads "List meetings, the status of each one, and the Activities line (open and waiting items, last pass)."
  - `prompts/analyze_system.md`: the `kind` sentence now says it is a classification and a hint for the story writer and the activities document, with no routing and no daily plan. The rest of the prompt and the schema are untouched. `prompts/user_story_guide.md` was not edited.
  - `Minutes` docstring now points at the AGENTS.md Portuguese exceptions.
  - `_remove_legacy_planner()` prints `Cli.LEGACY_PLANNER_REMOVE_FAILED` (a warning on stderr) and returns, so install, restart and uninstall carry on with the daemon.
  - A change to `analyze_system.md` affects the next analyses; the user should know before relying on it for the fidelity gates.
- Verified: `tests/integration/test_cli_agent.py::test_status_help_and_the_analyzer_prompt_no_longer_describe_the_daily_plan` and `::test_windows_a_failing_delete_of_the_old_planner_task_does_not_stop_the_daemon` (fake schtasks whose `/Delete` of the planner task fails; install, restart and uninstall exit 0, warn, and the daemon is still run, restarted or removed). Full `pytest -q` exit 0 and `mypy` clean (63 files), strings guard (`tests/unit/test_no_hardcoded_strings.py`) green.
