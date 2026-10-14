# RUN_LOG — felipemateusdecarvalho — 2026-10-14 17:10

Skill run: `code-review`, by a sub-agent, on the uncommitted fix for the Teams track recorded at the wrong sample rate. That fix makes `teams-tap` resample from the output device's real rate, adds the `tap.stats.json` counters, the `rate_mismatch` transcript flag and `scripts/recover-rate-mismatch.sh`. The user's request: "envie um subagente fazer a revisão do código com uma skil de code review" (send a sub-agent to review the code with a code-review skill).

- Fixed point: HEAD (`eb4ea45`), plus the uncommitted working-tree changes (27 files, +539/-39) and the untracked `scripts/recover-rate-mismatch.sh`.
- Spec: the brief the parent session gave the session that did the fix (items 1–4: real device rate with an `AVAudioConverter`, a rate-mismatch warning surfaced to the transcript health, a rebuild and a test, an optional recovery script).
- Standards: `AGENTS.md` (`CLAUDE.md` points to it), plus the skill's code-smell baseline.
- Mode: read-only. Swift was built only into the session scratchpad; one pytest session and mypy were run. Nothing in the repository or under `data/` was changed by the review.
- The first hand-back carried only the Standards axis. The main session resumed the same sub-agent to finish the Spec axis.

## Questions asked to the user
The skill asked none. The sub-agent could not reach the user and took these defaults:

| # | Question the skill asked or would have asked | Default taken |
|---|---|---|
| 1 | What is the fixed point? | HEAD `eb4ea45`, including the working tree and the untracked script, as given in the brief |
| 2 | Where is the spec? (`docs/agents/issue-tracker.md` is missing) | The task brief given by the main session; no tracker was looked up |
| 3 | Which documents hold the coding standards? | `AGENTS.md`, plus the skill's code-smell baseline |

Questions the main session asked the user about this work, before and after the skill run:
- "May I restart the daemon so it uses the new rate check?" (`trec agent restart`): not answered yet.
- After the review: "Quer que eu corrija os achados?" (Should I fix the findings?), with two options: the main ones (S1, P1, P2, P6, the S2 docs and the cheap S3, S5, S8, S9), or only the two medium ones (S1 and P1).
- "Quer que eu faça o commit antes, para ele conseguir fazer rebase em cima?" (Should I commit first, so the other agent can rebase on top?): not answered yet.

## Answers given by the user
- "explique o bug para eu mandar para o agente que tá fazendo uma nova feature que está pela metade, provavelmente vai conflitar" (explain the bug so I can send it to the agent building a half-done feature that will probably conflict). The main session answered with a paste-ready summary of the bug and of the changed interfaces.
- "envie um subagente fazer a revisão do código com uma skil de code review": this run.
- "Sim: corrija S1, P1, P2 e P6, mais a documentação de S2 e os pontos baratos S3, S5, S8 e S9, com testes. Deixe P3, P4, P5, P7, S4, S6 e S7 para eu decidir." (Yes: fix S1, P1, P2 and P6, plus the S2 docs and the cheap S3, S5, S8 and S9, with tests. Leave P3, P4, P5, P7, S4, S6 and S7 for me to decide.)

## Outcome
pytest passed, mypy found no issues in 52 source files, and the Swift build succeeded (one warning, already present at HEAD). `ruff` is not installed. Layering, English-only, strings in `messages.py`/`constants.py`, fakes and docs were found clean.

In a scratch harness (120 s at 8, 16, 24, 44.1 and 48 kHz, interleaved and not, with an extra headset-mic buffer), the converter produced exact frame counts and dropped no frames. It never picked up mic data and leaked no buffer lists. It has not been tried with a real 16 kHz device.

Findings, most severe first:

| Id | Axis | Severity | Finding |
|---|---|---|---|
| S1 | Standards | Medium | The advisory stats check catches only `RepositoryError`. An `OSError` from `path.exists()` (outside `retry_io`) or a read that `retry_io` gives up on escapes. The check runs after whisper and before `save_transcript`, so the meeting fails and the finished transcription is lost. The main session confirmed by reading the code. |
| P1 | Spec | Medium | The recovery script's `silenceremove` (RMS detection) leaves part of the padding even when the padding is digital zeros. On a 0.1 s on / 0.2 s off gated tone, the main session measured 5.1 s of 10 s kept (ideal ≈3.3 s) and 4.4 s with `detection=peak`; the sub-agent measured 9.1 s. A failed run also leaves a partial output that blocks a rerun. |
| P2 | Spec | Low | `RateMeter` counts skipped Core Audio cycles under 0.5 s as time but not frames. About 6% loss in two windows in a row switches a healthy 48 kHz stream to 44.1 kHz (the snap picks the nearest rate) for about 4 s. The writer only pads, so the Teams track ends about 0.3 s behind the mic track. The arithmetic was confirmed by reading; whether real devices behave this way is plausible. |
| P3 | Spec | Low | The channel layout comes from `kAudioTapPropertyFormat`; the aggregate's input stream formats are never read. When there are extra buffers, the tap's buffer is guessed from its channel count. When there are exactly N buffers, they are used without a check. |
| P4 | Spec | Low | A stale starting rate or listener rate costs about 4 s at the wrong rate, too little to be flagged. |
| P5 | Spec | Low | `stats.gaps` is never used: "no logged gaps" is implemented as padding in short pads. This is defensible, but it is not the literal spec. |
| P6 | Spec | Low | In `stop()`, the `queue.sync` drain runs after the aggregate and the tap are destroyed; it should come right after `AudioDeviceDestroyIOProcID`. `stopped` is read across threads without synchronization (a benign race). |
| P7 | Spec | Low | Meetings recorded before the fix, and captures killed before `stop()`, have no stats and are never flagged. The mic path writes stats, but Python never asks for them. |
| S2 | Standards | Low | `AGENTS.md`'s `MinutesRenderer` row and architecture §5.3 do not mention the new banner and check. |
| S3 | Standards | Low | `CaptureStats.padded_seconds` and `gaps` are required but unused, so a stats file missing them skips the check. |
| S4 | Standards | Low | The 5% / 60 s rule is defined both in Swift and in Python. |
| S5 | Standards | Low | `trec status` counts degraded transcripts but not rate-mismatched ones; the `rate_mismatch` check is repeated at several sites. |
| S6 | Standards | Low | `TranscribeMeeting.max_short_pad_share` / `rate_check_min_seconds` are not wired to any config. |
| S7 | Standards | Low | The predicate `rate_mismatch()` has the same name as the field `TranscriptHealth.rate_mismatch`. |
| S8 | Standards | Low | The `kAudioDevicePropertyNominalSampleRate` address is built twice in Swift. |
| S9 | Standards | Low | The new container test asserts the literal `"tap.stats.json"` instead of `TAP_STATS`. |

No fixes were applied by the review itself.

## Fixes applied after the user's answer
- **S1:** `load_capture_stats` reads through `retry_io` and turns any `OSError` into `RepositoryError`; `TranscribeMeeting` also catches `OSError`. Tests: a permission error keeps and saves the transcript, and a directory in place of the file raises `RepositoryError`.
- **P1:** the recovery script uses peak detection (5 ms windows, 0.01 s) and writes through a temporary file. On the gated test tone it now keeps 4.0 s (it kept 5.2 s; 3.3 s is ideal). On 2026-10-14_15-38-49 it strips 273 of the 475 padded seconds (it stripped 16). A failing input leaves nothing behind.
- **P2:** `RateMeter` uses the device sample time and switches only near a standard rate. Harness: with 6% of IO cycles dropped, the stream stays at 48 kHz with and without sample time; a 10 s sample-clock jump is ignored; the 16 kHz and lying-property cases are unchanged. A window that is not near a standard rate is logged once.
- **P6 / S8:** `stop()` drains the queue right after the IOProc is destroyed and before the device and the tap are. A queue-confined `capturing` flag replaces the cross-thread read of `stopped`, and the listener address is defined once.
- **S3:** `padded_seconds` and `gaps` are optional.
- **S5:** `trec status` counts rate-mismatched transcripts.
- **S9:** the test uses `TAP_STATS`.
- **S2:** `AGENTS.md` and §5.3 updated, plus a review note in §10.

The binary was rebuilt with `scripts/build-native.sh` and smoke-tested. pytest passes and mypy is clean. Nothing is committed.
