# Run log: spec draft for speech-check

Request (in Portuguese): "pode apagar as duas reuniões ou manter para teste. Eu vou ter uma reunião na segunda feira em inglês para testar. Não conta como loop, pois pode aparecer em contextos sem loop. pode abrir" ("you can delete the two meetings or keep them for testing. I will have a meeting in English on Monday to test. It does not count as a loop, since it can appear in contexts without a loop. You can open it").

How the request was read:
- The recordings are kept, as test cases; nothing under `data/` was deleted.
- No backfill of the two English meetings; the user will test language detection on a live English meeting on Monday, 2026-10-26.
- Short backchannels must not count as loops.
- Open the speech-check spec, as offered earlier.

## Skills run

- `cy-create-spec`: wrote `docs/tasks/speech-check/` with `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md`.
- `cy-spec-preflight`: the marker check passed with all 5 required markers, the Part I leak check is OK, and every test ID and every story AC/EC appears in the coverage matrix.

## Evidence gathered (read-only, scripts in the session scratchpad, nothing written under `data/`)

- Silero VAD (`whisper-vad-speech-segments`, the project's VAD arguments) on all 28 stored recordings:
  - the two no-speech recordings measured 0.0 s of speech;
  - every other recording measured 7.3 s or more;
  - VAD took 19.0 s for the 86-minute meeting.
- Speech inside each planned language sample: the vans meeting has 5 of 8 samples with 0 s of speech.
- The loop rule on stored transcripts and the language-detection G2 transcripts, today and under two exemption variants. In the forced-`pt` vans transcript, whisper hallucinated "e aí" 6 times in a row.

## Questions asked and answers given

1. "Quando o VAD não acha fala numa gravação, o que o sistema faz?" ("When VAD finds no speech in a recording, what does the system do?")
   Answer: "Pula o whisper e segue (Recomendado)" ("Skip whisper and continue").
2. "Uma gravação sem fala deve gerar notificação?" ("Should a recording with no speech notify?")
   Answer: "Só se tiver ≥ 1 minuto (Recomendado)" ("Only if it is 1 minute or longer").
3. "Frases curtas como 'Okay.': elas deixam de contar como loop sempre, ou contam quando se repetem em sequência?" ("Short lines such as 'Okay.': do they never count as a loop, or count when repeated in a row?")
   Answer: "Não contam, salvo 3+ seguidas (Recomendado)" ("They do not count, except 3 or more in a row").

## Outcome

- The spec is a draft awaiting the user's approval. No tasks were created and no code was changed.
- One correction during authoring: notifications in `trec transcribe` go to the log (headless `LogNotifier`), not to the desktop. The spec, `_dx.md` and US-002 say so.
- Nothing was committed.
