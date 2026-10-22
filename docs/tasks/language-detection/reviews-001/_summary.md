# Review round 1: language-detection spec

Scope: `_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md` and `adrs/adr-001.md` (spec only; no code exists yet). No previous rounds.

Recommendation: approve after fixes. No critical or high findings. Issues 001-003 should be fixed before tasks are cut.

| ID | Severity | Target | Defect |
|---|---|---|---|
| 001 | medium | `_spec.md:228` | Two sources for the fallback; `container.py:130` would pass `"auto"` to whisper on a detection failure |
| 002 | medium | `_spec.md:364` | `LANGUAGE_NO_ANSWER` needs the meeting id and the whisper tail, which no single layer has; a format change is reported as unclear audio |
| 003 | medium | `_spec.md:374` | The meeting lock does not protect against `trec purge` (`retention.py` ignores it) |
| 004 | low | `_spec.md:68` | Timing: the encoder takes about 2 s per sample and the model load about 0.6 s, so 12 samples take about 25 s, not 20 |
| 005 | low | `_spec.md:316` | The renderer port change omits `FakeMinutesRenderer` and the `RenderMinutes` transcript read |
| 006 | low | `_spec.md:282` | The codec raises no `RepositoryError`; a decoder without isinstance checks crashes with `AttributeError` |
| 007 | low | `_spec.md:37` | The spec says the curator is told the language; no component does it |
| 008 | low | `_tests.md:161` | `detector` collides with `Container.detector: CallDetector` |
| 009 | low | `_dx.md:34` | The golden-path `sed -n 1,4p` and the `Language:` line slot do not match the real output |
| 010 | low | `_user_stories.md:71` | One counted vote prints "no majority among 1 counted samples" |
| 011 | low | `_spec.md:258` | The regex breaks on an apostrophe in the temp path (needs verification on Windows) |

Verified correct:
- `sample_offsets` arithmetic in UT-001/002/005/006.
- Meeting durations: 2185 s (vans) and 5165 s (MARTA), from `meta.json`.
- 27 stored transcripts, all `pt`.
- The vans evidence, recomputed with `transcript_health` from the scratch JSON: en first pass 69.1% loops, text in 32/37 min; retry 10.4%, 35/37 min, top repeat "Okay." x9, `is_healthier_than` true.
- whisper 1.9.4: `-np` hides the answer line; several `-f` load the model once; the line format matches (stderr).
- An unreadable clip is skipped with exit 0.
- ffmpeg with a seek past the end exits 0 with a 78-byte WAV, so IT-003 can be written.
- File-reference line ranges match, except `constants.py:188-262`, which stops before `Parse` (line 265).

Not reviewed (the round was cut short): `test_no_hardcoded_strings` heuristics for the new `LanguageReason` literals in `domain/`, curator and story-writer message builders, mypy implications.

## Fix status (2026-10-21)

All 11 findings triaged `VALID` and resolved in their owning files (`_spec.md`, `_user_stories.md`, `_dx.md`, `_tests.md`, `adrs/adr-001.md`), at the user's choice to apply every finding. Each issue file records what was verified and the resolution. The spec preflight markers and the test-ID consistency check pass after the fixes. Verification of the fixes, and the three areas this round did not reach, are left to round 2.
