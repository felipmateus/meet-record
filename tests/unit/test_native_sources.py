"""Native helper sources: docs/tasks/speaker-attribution/_tests.md UT-076 (safety invariant 4)."""
from __future__ import annotations

from pathlib import Path

SOURCES = Path(__file__).resolve().parents[2] / "native" / "teams-speakers" / "Sources"
SETTER = "AXUIElementSetAttributeValue"  # literal-ok: the call the read-only helper must never contain


def test_ut076_the_helper_sources_never_set_an_accessibility_attribute():
    swift_files = sorted(SOURCES.rglob("*.swift"))
    assert swift_files, f"no Swift sources under {SOURCES}"
    offenders = [f"{path.relative_to(SOURCES)}:{number}" for path in swift_files
                 for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if SETTER in line]
    assert offenders == []


# --- review round 2: the texts and event names the helper and the docs must agree on -------------------------------------

HELPER = SOURCES / "teams-speakers" / "main.swift"
DX = Path(__file__).resolve().parents[2] / "docs" / "tasks" / "speaker-attribution" / "_dx.md"
NO_WINDOW_LOG = "no Teams meeting window found; waiting"   # literal-ok: the helper's log line _dx.md › Errors promises
TILE_SEEN_LOG = 'log("tile seen: \\(tile.name)\\(tile.me ? " (me)" : "") (\\(kind))")'   # literal-ok: the source line, quoted


def test_the_helper_logs_the_no_window_text_the_dx_contract_quotes():
    assert NO_WINDOW_LOG in HELPER.read_text(encoding="utf-8")
    assert NO_WINDOW_LOG in DX.read_text(encoding="utf-8")


def test_the_dx_contract_shows_the_tile_seen_line_with_its_window_suffix():
    assert TILE_SEEN_LOG in HELPER.read_text(encoding="utf-8")
    assert "tile seen: Lucas Huguenin Gurgel de Moura (main)" in DX.read_text(encoding="utf-8")   # literal-ok: the _dx.md sample line


def test_the_helper_writes_the_heartbeat_and_frozen_events_the_codec_reads():
    from teams_recorder.constants import Speakers

    source = HELPER.read_text(encoding="utf-8")
    assert f'emit("{Speakers.HEARTBEAT_EVENT}")' in source and "let heartbeatSeconds = 5.0" in source   # literal-ok: pins the cadence the spec states
    assert f'.s("{Speakers.WINDOW_FROZEN}")' in source and f'.s("{Speakers.WINDOW_LOST}")' in source
    assert "let frozenAfterSeconds = 3.0" in source and 'let callTimerDomId = "call-duration-custom"' in source   # literal-ok: the spec's numbers


def test_the_generic_video_marker_words_only_match_images():
    """A chat message or a file name such as "Vídeo de treinamento.mp4" must not make a window look like the call."""
    source = HELPER.read_text(encoding="utf-8")
    generic = next(line for line in source.splitlines() if line.startswith("let callMarkers"))
    assert "vídeo de " not in generic and "video of " not in generic
    assert 'role == "AXImage" && imageCallMarkers' in source
