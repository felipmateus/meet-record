# Run log: cy-create-spec and cy-spec-preflight, activities-curator

Skills run: `cy-create-spec` (slug `activities-curator`) and `cy-spec-preflight` on the result. The design was settled earlier in the same session through a conversation and a designer/critic loop; the questions below are every question asked to the user in that session and the answers they gave, in order.

## Questions asked and answers given

1. Q: What do you suggest to unify my scattered task files into one, as another step of the flow? A: (the request itself; the user said the app's main idea is organizing daily tasks).
2. Q: Are only the app's generated files scattered, or do tasks also live elsewhere (Obsidian, a TODO file, Microsoft To Do, Reminders)? A: Only the app's generated files; tasks from previous days are not listed even though unfinished, so the user loses visibility.
3. Q: Confirm the diagnosis against your data first, or go straight to a spec? A: Send a subagent to review the solution and look for gaps.
4. Q: Open the spec with these decisions, or review a point first? A: Send another subagent to review the plan; then, send a subagent to look for a better solution.
5. Q: Stopgap first or straight to the spec? A: (user) What does "relief in days" mean? (explained: a ~1 h fix usable the next day vs weeks for the full solution).
6. Q: Five decisions (drop the per-day plan file; where to record ingested meetings; model-suggested completions; cross-meeting fuzzy merge; sync before listing). A: 1 yes; 2 asked what "ingested" means; 3 completion is the user's, marked with an x, a UI later; 4 asked what fuzzy merge is; 5 did not understand.
7. Q: (after explanations) Confirm: marker in the meeting folder; no fuzzy matching; reanalysis does not re-insert, `reingest` replaces untouched items? A: 2 yes, insert into the list right after the meeting; 4 no use case for fuzzy if reading is deterministic and nothing is read twice.
8. A: (user) After all questions, check whether a better solution exists; solve more with code than with repeated LLM review to reduce error propagation.
9. Q: Accept losing the daily prose (code-ranked focus, per-meeting fragments)? A: Did not like it; go back to the previous solution and draw a flowchart.
10. Q: Will the 18:00 plan stay? A: (asked) — explained it would only write the focus. Then the user redesigned: not every activity is a task or a story; keep the analysis after recording (maybe a specialized agent); remove the flow after it; explain the last solution without code, since deterministic code would worsen the result.
11. Q: What enters the document? Stories: on demand or removed? A: Everything; stories on demand via a command; remove the analysis from the 18:00 flow.
12. A: (user) Run a loop to find the ideal solution. (Two designer/critic rounds; round 2 had no blocking issue.)
13. Q: Where will you read the file? Where to start the document? A: VS Code first, Obsidian later; follow the recommendation (curate the last 10 working days with confirmation). Approved opening the spec.

## Outcome

Created `docs/tasks/activities-curator/`: `_spec.md`, `_user_stories.md` (US-001 to US-019), `_dx.md`, `_tests.md` (UT/IT/E2E plus quality evaluations Q-001 to Q-003), `adrs/adr-001.md` (edits + one invariant over rewrite or a task store), `adrs/adr-002.md` (planner removed, no scheduled pass, stories on demand). Preflight: Part I leak check clean; markers 1, 2, 4, 5, 6 present after adding a data-field table; every story appears in the test coverage matrix. No code was changed. The spec awaits the user's approval.
