# task_04 memory

- Status: implemented and verified (pytest 1293 passed / 10 skipped; mypy clean).
- Files: `adapters/outbound/llm_schema.py` (`language_line(code)`, header line in `build_user_message`), `adapters/outbound/verifier_claude.py` (same line after the owner/date lines, before the roster), `messages.py` (`Prompt.TRANSCRIPT_LANGUAGE`, `CURATE_TASK` step 7), `constants.py` (`Verify.ADDRESS` + docstring), `prompts/analyze_system.md`, `verify_system.md`, `curate_system.md`; tests in `test_llm_claude.py`, `test_verifier_claude.py`, `test_curator_prompt.py`, `test_verification.py`.
- "Portuguese" is `Audio.DEFAULT_LANGUAGE` ("pt"): the header line is skipped when `transcript.language` equals it.
- `test_the_shipped_prompt_is_the_measured_prototype_prompt` pins `verify_system.md` to the prototype plus listed deviations. The language rule went in as ONE added paragraph (starts with "When the message has a `Transcript language:` line"), and the pin now strips it like the `status_update` paragraph. That edit to an existing test is unavoidable: the spec requires a verifier prompt change.
- The curator prompt line numbers (1, 34, 43, 281) did not shift; UT-053 finds the lines by content, not number.
- Remaining: gate G3 (task 6) re-measures Portuguese output with the changed prompts; the real-call suites for US-004.AC-2/AC-4 were not run (they spend the subscription).
