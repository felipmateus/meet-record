# Run log: why the language-detection spec has no prd.md

Request (in Portuguese), through `/cy-create-spec`: "por que a spec que foi criada agora de language-detection não tem prd?" ("why does the language-detection spec that was just created have no PRD?").

## Skills run

- `cy-create-spec`: used only to answer a question about its output format. No spec file was created or changed.

## Questions asked and answers given

No question was asked of the user, so no answer was given.

## Outcome

- Answer: `cy-create-spec` does not produce a separate `prd.md`. The product requirements are Part I of `_spec.md` (Overview, Goals, Core Features, Business Rules, User Experience, Non-Goals, Open Questions), with the stories in `_user_stories.md`. The standalone `prd.md` + `techspec.md` + `tasks.md` layout belongs to the older workflow (`prd-fidelity-guard`, `prd-llm-wiki`, `prd-story-publishing`). `speaker-attribution/prd.md` exists because that PRD was written before the spec and kept. `activities-curator` and `speaker-attribution-windows` have no `prd.md` either.
- The project-wide PRD (`docs/prd/pages/02-transcription.md`) is listed in the spec's Impact Analysis as a document to update in task 6. It is not changed yet because nothing has been implemented.
- Nothing committed. No file changed except this run log.
