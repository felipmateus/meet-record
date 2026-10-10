"""The container wires the right adapters for each platform without touching OS APIs."""
from dataclasses import replace
from pathlib import Path

from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_wasapi import WasapiMicCapture, WasapiTapCapture
from teams_recorder.adapters.outbound.confirm_macos import DialogRecordingConfirmation
from teams_recorder.adapters.outbound.confirm_windows import MessageBoxRecordingConfirmation
from teams_recorder.adapters.outbound.detector_pmset import PmsetCallDetector
from teams_recorder.adapters.outbound.detector_windows import MicUsageCallDetector
from teams_recorder.adapters.outbound.notifier_macos import LogNotifier, MacOSNotifier
from teams_recorder.adapters.outbound.notifier_windows import ToastNotifier
from teams_recorder.config import load_settings
from teams_recorder.constants import Platform, Stories, StoryDestination
from teams_recorder.container import build_container, build_story_publishers, teams_tap_binary
from tests.fakes import FakeStoryPublisher


def test_windows_container(tmp_path: Path):
    s = load_settings(tmp_path, platform=Platform.WINDOWS)
    c = build_container(s)
    assert isinstance(c.process_capture, WasapiTapCapture) and isinstance(c.mic_capture, WasapiMicCapture)
    assert c.process_capture.binary == teams_tap_binary(tmp_path.resolve(), Platform.WINDOWS)
    assert c.process_capture.binary.name == "teams-tap.exe"
    assert c.process_capture.stop_dir == s.data_dir / "run"
    assert isinstance(c.detector, MicUsageCallDetector) and c.detector.process_name == "ms-teams.exe"
    assert isinstance(c.notifier, ToastNotifier)
    assert isinstance(c.confirmation, MessageBoxRecordingConfirmation)


def test_macos_container(tmp_path: Path):
    c = build_container(load_settings(tmp_path, platform=Platform.MACOS))
    assert isinstance(c.process_capture, CoreAudioTapCapture) and isinstance(c.detector, PmsetCallDetector)
    assert isinstance(c.notifier, MacOSNotifier) and isinstance(c.confirmation, DialogRecordingConfirmation)


def test_headless_has_no_dialog_on_either_platform(tmp_path: Path):
    for platform in Platform:
        c = build_container(load_settings(tmp_path, platform=platform), headless=True)
        assert isinstance(c.notifier, LogNotifier) and c.confirmation is None


def test_bit_depth_reaches_every_recorder(tmp_path: Path):
    (tmp_path / "config.toml").write_text("[audio]\nbit_depth = 32\n")
    for platform in Platform:
        c = build_container(load_settings(tmp_path, platform=platform))
        tap = c.process_capture.command(1, tmp_path / "m" / "tap.wav")
        mic = c.mic_capture.command("default", tmp_path / "m" / "mic.wav")
        assert tap[tap.index("--bits") + 1] == "32" and mic[mic.index("--bits") + 1] == "32"


def test_default_recorders_write_16_bit(tmp_path: Path):
    c = build_container(load_settings(tmp_path, platform=Platform.MACOS))
    tap = c.process_capture.command(1, tmp_path / "m" / "tap.wav")
    assert tap[tap.index("--bits") + 1] == "16"


def test_ffmpeg_microphone_codec_follows_bit_depth():
    from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture

    assert "pcm_s16le" in FfmpegMicCapture().command("0", Path("m.wav"))
    assert "pcm_f32le" in FfmpegMicCapture(bit_depth=32).command("0", Path("m.wav"))


def test_story_publishers_follow_the_configured_destinations(tmp_path: Path, monkeypatch):
    registry = {StoryDestination.BACKLOG_MD: lambda s: FakeStoryPublisher(f"board:{s.backlog_status}")}
    monkeypatch.setattr("teams_recorder.container._PUBLISHERS", registry)
    assert build_story_publishers(load_settings(tmp_path)) == []                      # none configured
    (tmp_path / "config.toml").write_text('[stories]\ndestinations = ["backlog-md"]\ndedup_days = 9\n')

    c = build_container(load_settings(tmp_path), headless=True)

    assert [p.destination for p in c.story_publishers] == [f"board:{Stories.BACKLOG_STATUS}"]
    publish = c.publish_user_stories()
    assert publish.publishers is c.story_publishers and publish.dedup_days == 9
    assert c.draft_user_stories().dedup_days == 9


def test_story_publishers_keep_the_configured_order(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("teams_recorder.container._PUBLISHERS", {"first": lambda s: FakeStoryPublisher("first"),
                                                                 "second": lambda s: FakeStoryPublisher("second")})
    settings = replace(load_settings(tmp_path), story_destinations=("second", "first"))
    assert [p.destination for p in build_story_publishers(settings)] == ["second", "first"]
