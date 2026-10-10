"""Composition root: the only place that instantiates concrete adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_wasapi import WasapiMicCapture, WasapiTapCapture
from teams_recorder.adapters.outbound.capture_mic_coreaudio import CoreAudioMicCapture
from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture
from teams_recorder.adapters.outbound.clock import SystemClock
from teams_recorder.adapters.outbound.confirm_macos import DialogRecordingConfirmation
from teams_recorder.adapters.outbound.confirm_windows import MessageBoxRecordingConfirmation
from teams_recorder.adapters.outbound.detector_windows import MicUsageCallDetector
from teams_recorder.adapters.outbound.disk_space import DataDirDiskSpace
from teams_recorder.adapters.outbound.detector_pmset import PmsetCallDetector
from teams_recorder.adapters.outbound.llm_claude import ClaudeAnalyzer
from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport, StructuredTransport
from teams_recorder.adapters.outbound.mixer_ffmpeg import FfmpegMixer
from teams_recorder.adapters.outbound.notifier_macos import LogNotifier, MacOSNotifier
from teams_recorder.adapters.outbound.notifier_windows import ToastNotifier
from teams_recorder.adapters.outbound.planner_claude import ClaudePlanner
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.stories_claude import ClaudeStoryWriter
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.ports import (
    AudioMixer,
    CallDetector,
    Clock,
    DiskSpace,
    MeetingAnalyzer,
    MeetingRepository,
    MicCapture,
    MinutesRenderer,
    Notifier,
    Planner,
    ProcessAudioCapture,
    RecordingConfirmation,
    StoryRenderer,
    StoryWriter,
    Transcriber,
)
from teams_recorder.application.use_cases import (
    AnalyzeMeeting,
    BuildDailyPlan,
    CancelRecording,
    DraftUserStories,
    PurgeOldAudio,
    RenderMinutes,
    StartRecording,
    StopRecording,
    TranscribeMeeting,
)
from teams_recorder.config import Settings, find_tool
from teams_recorder.constants import Bin, Files, LlmProvider, MicBackend, Platform


def teams_tap_binary(project_dir: Path, platform: Platform = Platform.MACOS) -> Path:
    return project_dir / (Files.NATIVE_BINARY_WINDOWS if platform is Platform.WINDOWS else Files.NATIVE_BINARY)


@dataclass
class _PlatformAdapters:
    notifier: Notifier
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    detector: CallDetector
    confirmation: RecordingConfirmation | None


@dataclass
class Container:
    settings: Settings
    repo: MeetingRepository
    clock: Clock
    notifier: Notifier
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    mixer: AudioMixer
    transcriber: Transcriber
    analyzer: MeetingAnalyzer
    planner: Planner
    detector: CallDetector
    minutes: MinutesRenderer
    story_writer: StoryWriter
    story_renderer: StoryRenderer
    confirmation: RecordingConfirmation | None = None   # None: never ask whether to keep a recording
    disk: DiskSpace | None = None

    def start_recording(self) -> StartRecording:
        return StartRecording(self.repo, self.process_capture, self.mic_capture, self.notifier, self.clock, self.settings.mic_device, self.disk,
                              self.settings.raw_bytes_per_hour)

    def stop_recording(self) -> StopRecording:
        return StopRecording(self.repo, self.process_capture, self.mic_capture, self.mixer, self.notifier, self.clock)

    def cancel_recording(self) -> CancelRecording:
        return CancelRecording(self.repo, self.process_capture, self.mic_capture, self.notifier)

    def transcribe_meeting(self) -> TranscribeMeeting:
        return TranscribeMeeting(self.repo, self.transcriber, self.settings.language)

    def analyze_meeting(self) -> AnalyzeMeeting:
        return AnalyzeMeeting(self.repo, self.analyzer, self.minutes)

    def render_minutes(self) -> RenderMinutes:
        return RenderMinutes(self.repo, self.minutes)

    def pipeline(self) -> Pipeline:
        return Pipeline(self.repo, self.notifier, self.stop_recording(), self.transcribe_meeting(), self.analyze_meeting())

    def build_daily_plan(self) -> BuildDailyPlan:
        return BuildDailyPlan(self.repo, self.planner, self.notifier)

    def draft_user_stories(self) -> DraftUserStories:
        return DraftUserStories(self.repo, self.story_writer, self.story_renderer, self.notifier)

    def purge_old_audio(self) -> PurgeOldAudio:
        return PurgeOldAudio(self.repo, self.clock, self.settings.retention_days)


def _macos_adapters(settings: Settings, headless: bool) -> _PlatformAdapters:
    binary = teams_tap_binary(settings.project_dir, Platform.MACOS)
    capture_log = settings.capture_log
    mic_capture: MicCapture = (
        FfmpegMicCapture(ffmpeg=find_tool(Bin.FFMPEG, settings.project_dir), log_path=capture_log, bit_depth=settings.bit_depth)
        if settings.mic_backend is MicBackend.FFMPEG
        else CoreAudioMicCapture(binary, log_path=capture_log, bit_depth=settings.bit_depth)
    )
    return _PlatformAdapters(
        notifier=LogNotifier() if headless else MacOSNotifier(),
        process_capture=CoreAudioTapCapture(binary, log_path=capture_log, bit_depth=settings.bit_depth),
        mic_capture=mic_capture,
        detector=PmsetCallDetector(settings.teams_process_name),
        confirmation=DialogRecordingConfirmation(settings.confirm_timeout_seconds) if settings.confirm_recording and not headless else None,
    )


def _windows_adapters(settings: Settings, headless: bool) -> _PlatformAdapters:
    binary = teams_tap_binary(settings.project_dir, Platform.WINDOWS)
    stop_dir = settings.data_dir / Files.RUN_DIR
    return _PlatformAdapters(
        notifier=LogNotifier() if headless else ToastNotifier(),
        process_capture=WasapiTapCapture(binary, stop_dir, log_path=settings.capture_log, bit_depth=settings.bit_depth),
        mic_capture=WasapiMicCapture(binary, stop_dir, log_path=settings.capture_log, bit_depth=settings.bit_depth),   # audio.mic_backend is macOS-only
        detector=MicUsageCallDetector(settings.teams_process_name),
        confirmation=MessageBoxRecordingConfirmation(settings.confirm_timeout_seconds) if settings.confirm_recording and not headless else None,
    )


def build_container(settings: Settings, *, headless: bool = False) -> Container:
    transport = build_transport(settings)  # shared by analyzer and planner
    platform = (_windows_adapters if settings.platform is Platform.WINDOWS else _macos_adapters)(settings, headless)
    ffmpeg = find_tool(Bin.FFMPEG, settings.project_dir)
    return Container(
        settings=settings,
        repo=FsMeetingRepository(settings.data_dir),
        clock=SystemClock(),
        notifier=platform.notifier,
        process_capture=platform.process_capture,
        mic_capture=platform.mic_capture,
        mixer=FfmpegMixer(ffmpeg=ffmpeg, bitrate_kbps=settings.bitrate_kbps, denoise=settings.denoise),
        transcriber=WhisperCppTranscriber(
            settings.whisper_model_path, whisper_cli=find_tool(Bin.WHISPER_CLI, settings.project_dir), ffmpeg=ffmpeg,
            threads=settings.whisper_threads, vad_model_path=settings.vad_model_path,
        ),
        analyzer=ClaudeAnalyzer(transport, prompt_path=settings.prompts_dir / Files.ANALYZE_PROMPT, user_name=settings.user_name),
        planner=ClaudePlanner(transport, prompt_path=settings.prompts_dir / Files.PLAN_PROMPT, user_name=settings.user_name),
        detector=platform.detector,
        minutes=MarkdownMinutesRenderer(settings.user_name),
        story_writer=ClaudeStoryWriter(
            transport, settings.story_guide_path, prompt_path=settings.prompts_dir / Files.STORIES_PROMPT, user_name=settings.user_name,
        ),
        story_renderer=MarkdownStoryRenderer(),
        confirmation=platform.confirmation,
        disk=DataDirDiskSpace(settings.data_dir),
    )


def build_transport(settings: Settings) -> StructuredTransport:
    if settings.llm_provider is LlmProvider.CLAUDE_CODE:
        return ClaudeCodeTransport(model=settings.llm_cli_model, effort=settings.llm_effort, usage_log=settings.usage_log)
    return ApiTransport(model=settings.llm_model, effort=settings.llm_effort, max_tokens=settings.llm_max_tokens, usage_log=settings.usage_log)
