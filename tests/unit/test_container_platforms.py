"""The container wires the right adapters for each platform without touching OS APIs."""
from dataclasses import replace
from pathlib import Path

from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_wasapi import WasapiMicCapture, WasapiTapCapture
from teams_recorder.adapters.outbound.confirm_macos import DialogRecordingConfirmation
from teams_recorder.adapters.outbound.confirm_windows import MessageBoxRecordingConfirmation
from teams_recorder.adapters.outbound.detector_pmset import PmsetCallDetector
from teams_recorder.adapters.outbound.detector_windows import MicUsageCallDetector
from teams_recorder.adapters.outbound.energy_ffmpeg import FfmpegEnergyMeter
from teams_recorder.adapters.outbound.notifier_macos import LogNotifier, MacOSNotifier
from teams_recorder.adapters.outbound.notifier_windows import ToastNotifier
from teams_recorder.adapters.outbound.speakers_ax import AxSpeakerObserver
from teams_recorder.config import load_settings
from teams_recorder.constants import Files, Platform, Stories, StoryDestination
from teams_recorder.container import build_container, build_retry_transcriber, build_story_publishers, teams_speakers_binary, teams_tap_binary
from teams_recorder.domain.status import TAP_STATS
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


def test_ut060_macos_builds_the_observer_only_when_speakers_are_enabled(tmp_path: Path):
    s = load_settings(tmp_path, platform=Platform.MACOS)
    observer = build_container(s).speakers
    assert isinstance(observer, AxSpeakerObserver)
    assert observer.binary == teams_speakers_binary(tmp_path.resolve()) == tmp_path.resolve() / "native/teams-speakers/.build/release/teams-speakers"
    assert observer.run_dir == s.data_dir / "run" and observer.log_path == s.data_dir / "log" / "speakers.log"

    (tmp_path / "config.toml").write_text("[speakers]\nenabled = false\n")
    assert build_container(load_settings(tmp_path, platform=Platform.MACOS)).speakers is None


def test_ut060_windows_passes_no_observer_even_when_enabled(tmp_path: Path):
    s = load_settings(tmp_path, platform=Platform.WINDOWS)
    assert s.speakers_enabled and build_container(s).speakers is None


def test_both_platforms_get_the_energy_meter(tmp_path: Path):
    for platform in Platform:
        meter = build_container(load_settings(tmp_path, platform=platform)).energy
        assert isinstance(meter, FfmpegEnergyMeter)


def test_the_recording_use_cases_receive_the_observer_and_the_energy_meter(tmp_path: Path):
    c = build_container(load_settings(tmp_path, platform=Platform.MACOS))
    assert c.start_recording().speakers is c.speakers is not None
    assert c.cancel_recording().speakers is c.speakers
    stop = c.stop_recording()
    assert stop.speakers is c.speakers and stop.energy is c.energy is not None
    assert c.pipeline().stop.speakers is c.speakers

    windows = build_container(load_settings(tmp_path, platform=Platform.WINDOWS))
    assert windows.start_recording().speakers is None and windows.stop_recording().speakers is None
    assert windows.stop_recording().energy is windows.energy is not None


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
    assert c.draft_stories_from_tags().dedup_days == 9


def test_story_publishers_keep_the_configured_order(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("teams_recorder.container._PUBLISHERS", {"first": lambda s: FakeStoryPublisher("first"),
                                                                 "second": lambda s: FakeStoryPublisher("second")})
    settings = replace(load_settings(tmp_path), story_destinations=("second", "first"))
    assert [p.destination for p in build_story_publishers(settings)] == ["second", "first"]


def test_every_destination_has_a_publisher_and_backlog_md_gets_its_settings(tmp_path: Path):
    from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher
    from teams_recorder.container import _PUBLISHERS

    assert set(_PUBLISHERS) == set(StoryDestination)
    (tmp_path / "config.toml").write_text('[stories]\ndestinations = ["backlog-md"]\n[stories.backlog_md]\nproject_dir = "."\nstatus = "Inbox"\n')
    settings = load_settings(tmp_path)
    [publisher] = build_story_publishers(settings)
    assert isinstance(publisher, BacklogMdPublisher)
    assert publisher.project_dir == tmp_path.resolve() and publisher.status == "Inbox"
    assert publisher.drafts_dir == settings.data_dir / "plans" and publisher.destination == StoryDestination.BACKLOG_MD


def _models(tmp_path: Path, config: str = "", vad_model: bool = True):
    (tmp_path / "models").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.toml").write_text(f'[transcription]\nmodels_dir = "{tmp_path / "models"}"\n' + config)
    if vad_model:
        (tmp_path / "models" / "ggml-silero-v5.1.2.bin").write_bytes(b"\x00")
    return load_settings(tmp_path)


def test_first_pass_gets_max_context_and_the_retry_adds_vad(tmp_path: Path):
    c = build_container(_models(tmp_path), headless=True)
    assert c.transcriber.max_context == 0 and c.transcriber.vad_model_path is None
    retry = c.retry_transcriber
    assert retry is not None and retry.max_context == 0 and retry.vad_model_path == tmp_path / "models" / "ggml-silero-v5.1.2.bin"
    use_case = c.transcribe_meeting()
    assert use_case.retry is retry and use_case.notifier is c.notifier and use_case.max_loop_share == 0.10
    assert use_case.clock is c.clock and use_case.user_name == c.settings.user_name   # the speaker labels and their daily notice


def test_no_retry_when_it_would_repeat_the_first_pass(tmp_path: Path):
    assert build_retry_transcriber(_models(tmp_path, "retry_on_loop = false\n")) is None
    assert build_retry_transcriber(_models(tmp_path, "retry_vad = false\n")) is None          # -mc 0 already, nothing to add
    assert build_retry_transcriber(_models(tmp_path, "vad = true\n")) is None                # VAD already on the first pass
    assert build_retry_transcriber(_models(tmp_path / "novad", vad_model=False)) is None       # VAD model missing


def test_retry_without_vad_when_the_first_pass_keeps_text_context(tmp_path: Path):
    retry = build_retry_transcriber(_models(tmp_path, "max_context = -1\nretry_vad = false\n"))
    assert retry is not None and retry.max_context == 0 and retry.vad_model_path is None


def test_the_macos_tap_writes_its_counters_next_to_the_track(tmp_path: Path):
    c = build_container(load_settings(tmp_path, platform=Platform.MACOS))
    tap = c.process_capture.command(1, tmp_path / "m" / "tap.wav")
    assert tap[tap.index("--stats") + 1] == str(tmp_path / "m" / TAP_STATS)


def test_the_verifier_runs_on_its_own_smaller_model_and_logs_usage_like_the_rest(tmp_path: Path, monkeypatch):
    from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport
    from teams_recorder.adapters.outbound.verifier_claude import ClaudeClaimVerifier
    from teams_recorder.constants import Effort
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text('[llm]\nprovider = "claude-code"\n[user]\nname = "Felipe"\n')
    c = build_container(load_settings(tmp_path), headless=True)
    verifier = c.verifier
    assert isinstance(verifier, ClaudeClaimVerifier) and isinstance(verifier.transport, ClaudeCodeTransport)
    assert verifier.transport.model == "sonnet" and verifier.transport.effort is Effort.MEDIUM
    assert verifier.transport.usage_log == c.settings.usage_log and verifier.user_name == "Felipe"
    assert verifier.prompt_path == c.settings.prompts_dir / Files.VERIFY_PROMPT
    step = c.analyze_meeting().verify
    assert step is not None and step.verifier is verifier and step.user_name == "Felipe"   # both need the name (task 3.0 note)

    (tmp_path / "config.toml").write_text('[llm]\nprovider = "api"\n')
    api = build_container(load_settings(tmp_path), headless=True).verifier
    assert isinstance(api, ClaudeClaimVerifier) and isinstance(api.transport, ApiTransport)
    assert api.transport.model == "claude-sonnet-5-5" and api.transport.effort is Effort.MEDIUM


def test_verification_off_keeps_only_the_code_checks(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text("[verification]\nenabled = false\n")
    c = build_container(load_settings(tmp_path), headless=True)
    step = c.analyze_meeting().verify
    assert c.verifier is None and step is not None and step.verifier is None   # no model call; PRD decision 11


def test_ut108_the_container_builds_the_curator_the_store_and_the_use_case_from_the_activities_settings(tmp_path: Path, monkeypatch):
    from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
    from teams_recorder.adapters.outbound.curator_claude import ClaudeCurator
    from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport
    from teams_recorder.application.use_cases.activities import CurateMeetings, UndoLastPass, doc_format
    from teams_recorder.constants import Effort
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text(
        '[llm]\nprovider = "claude-code"\ncli_model = "sonnet"\neffort = "high"\n[user]\nname = "Felipe"\n'
        '[activities]\ncli_model = "opus"\nnotify = false\nkeep_versions = 7\n')
    c = build_container(load_settings(tmp_path), headless=True)

    curator = c.curator
    assert isinstance(curator, ClaudeCurator) and isinstance(curator.transport, ClaudeCodeTransport)
    assert curator.transport.model == "opus" and curator.transport.effort is Effort.MEDIUM   # its own model and effort, not the analyzer's
    assert curator.transport.usage_log == c.settings.usage_log and curator.prompt_path == c.settings.prompts_dir / Files.CURATE_PROMPT
    assert curator.transport is not c.verifier.transport   # type: ignore[union-attr]
    store = c.activity_store
    assert isinstance(store, FsActivityStore) and store.fmt == doc_format() and store.keep_versions == 7
    assert store.path() == c.settings.data_dir / "activities" / "atividades.md"
    use = c.curate_meetings()
    assert isinstance(use, CurateMeetings)
    assert (use.repo, use.store, use.curator, use.notifier, use.clock) == (c.repo, store, curator, c.notifier, c.clock)
    assert use.user_name == "Felipe" and use.notify is False
    summary = c.activities_summary()
    assert (summary.repo, summary.store) == (c.repo, store) and isinstance(summary.curate, CurateMeetings) and summary.curate.store is store
    undo = c.undo_last_pass()
    assert isinstance(undo, UndoLastPass) and (undo.store, undo.clock) == (store, c.clock)

    (tmp_path / "config.toml").write_text('[llm]\nprovider = "api"\nmodel = "claude-sonnet-5-5"\n[activities]\neffort = "low"\n')
    api = build_container(load_settings(tmp_path), headless=True).curator
    assert isinstance(api, ClaudeCurator) and isinstance(api.transport, ApiTransport)
    assert api.transport.model == "claude-sonnet-5-5" and api.transport.effort is Effort.LOW   # [activities] model defaults to the analyzer's


def test_ut108_activities_disabled_only_switches_off_the_automatic_triggers_the_use_case_is_still_built(tmp_path: Path):
    (tmp_path / "config.toml").write_text("[activities]\nenabled = false\n")
    c = build_container(load_settings(tmp_path), headless=True)
    assert c.settings.activities_enabled is False
    assert c.curate_meetings().store is c.activity_store and c.curator is not None   # `trec activities curate` still works


def test_ut108_pipeline_takes_the_after_analysis_hook(tmp_path: Path):
    c = build_container(load_settings(tmp_path), headless=True)

    def hook(meeting_id: str) -> None:
        pass

    assert c.pipeline(after_analysis=hook).after_analysis is hook
    assert c.pipeline(hook).after_analysis is hook
    assert c.pipeline().after_analysis is None
