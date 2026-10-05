# Installation (phase 7 — pending)

> **Planned deliverables:** `scripts/install.sh`, installation README, `trec status` with the month's spend
> **Module:** Installation · **Generated:** 2026-10-05

## Goal
Install from scratch on another Mac, or for another user, with a single script, meeting non-functional requirement NFR10.

## Planned `install.sh` steps
1. Check macOS ≥ 14.2 and Apple Silicon or compatible Intel.
2. Homebrew: `ffmpeg`, `whisper-cpp`.
3. Python 3.11: venv and `pip install -e .`.
4. Swift (Command Line Tools): `scripts/build-native.sh`.
5. Models: `download-model.sh` (quantized whisper and Silero VAD).
6. `.env` from the example, permission 600; instructions for the key.
7. Detect an iCloud-synced folder → data in `~/Library/Application Support/teams-recorder` (already implemented in `config.py`).
8. `trec doctor`; `trec agent install`; guidance on the two macOS permissions.

## Acceptance criterion
A from-scratch installation for another user on the Mac works and `trec doctor` comes up green.
