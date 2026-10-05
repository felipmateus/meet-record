"""Composition root: the only place that instantiates concrete adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_mic_coreaudio import CoreAudioMicCapture
from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture
from teams_recorder.adapters.outbound.clock import SystemClock
from teams_recorder.adapters.outbound.detector_pmset import PmsetCallDetector
from teams_recorder.adapters.outbound.llm_claude import ClaudeAnalyzer
from teams_recorder.adapters.outbound.llm_claude_cli import ClaudeCliAnalyzer
from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport, StructuredTransport
from teams_recorder.adapters.outbound.planner_claude import ClaudePlanner
from teams_recorder.adapters.outbound.mixer_ffmpeg import FfmpegMixer
from teams_recorder.adapters.outbound.notifier_macos import LogNotifier, MacOSNotifier
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber
from teams_recorder.application.ports import (
    AudioMixer,
    CallDetector,
    Clock,
    MeetingAnalyzer,
    MeetingRepository,
    MicCapture,
    Notifier,
    Planner,
    ProcessAudioCapture,
    Transcriber,
)
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.use_cases import (
    AnalyzeMeeting,
    BuildDailyPlan,
    CancelRecording,
    PurgeOldAudio,
    StartRecording,
    StopRecording,
    TranscribeMeeting,
)
from teams_recorder.config import Settings


def teams_tap_binary(project_dir: Path) -> Path:
    return project_dir / "native" / "teams-tap" / ".build" / "release" / "teams-tap"


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
    detector: CallDetector | None = None

    def start_recording(self) -> StartRecording:
        return StartRecording(self.repo, self.process_capture, self.mic_capture, self.notifier, self.clock, self.settings.mic_device)

    def stop_recording(self) -> StopRecording:
        return StopRecording(self.repo, self.process_capture, self.mic_capture, self.mixer, self.notifier, self.clock)

    def cancel_recording(self) -> CancelRecording:
        return CancelRecording(self.repo, self.process_capture, self.mic_capture, self.notifier)

    def transcribe_meeting(self) -> TranscribeMeeting:
        return TranscribeMeeting(self.repo, self.transcriber, self.settings.language)

    def analyze_meeting(self) -> AnalyzeMeeting:
        return AnalyzeMeeting(self.repo, self.analyzer)

    def pipeline(self) -> Pipeline:
        return Pipeline(self.repo, self.notifier, self.stop_recording(), self.transcribe_meeting(), self.analyze_meeting())

    def build_daily_plan(self) -> BuildDailyPlan:
        return BuildDailyPlan(self.repo, self.planner, self.notifier)

    def purge_old_audio(self) -> PurgeOldAudio:
        return PurgeOldAudio(self.repo, self.clock, self.settings.retention_days)


def build_container(settings: Settings, *, headless: bool = False) -> Container:
    capture_log = settings.data_dir / "log" / "capture.log"
    return Container(
        settings=settings,
        repo=FsMeetingRepository(settings.data_dir),
        clock=SystemClock(),
        notifier=LogNotifier() if headless else MacOSNotifier(),
        process_capture=CoreAudioTapCapture(teams_tap_binary(settings.project_dir), log_path=capture_log),
        mic_capture=(FfmpegMicCapture(log_path=capture_log) if settings.mic_backend == "ffmpeg"
                     else CoreAudioMicCapture(teams_tap_binary(settings.project_dir), log_path=capture_log)),
        mixer=FfmpegMixer(bitrate_kbps=settings.bitrate_kbps, denoise=settings.denoise),
        transcriber=WhisperCppTranscriber(settings.whisper_model_path, threads=settings.whisper_threads, vad_model_path=settings.vad_model_path),
        analyzer=build_analyzer(settings),
        planner=ClaudePlanner(build_transport(settings), prompt_path=settings.prompts_dir / "plan_system.md"),
        detector=PmsetCallDetector(settings.teams_process_name),
    )


def build_transport(settings: Settings) -> StructuredTransport:
    if settings.llm_provider == "claude-code":
        return ClaudeCodeTransport(model=settings.llm_cli_model, effort=settings.llm_effort, usage_log=settings.usage_log)
    return ApiTransport(model=settings.llm_model, effort=settings.llm_effort, max_tokens=settings.llm_max_tokens, usage_log=settings.usage_log)


def build_analyzer(settings: Settings) -> MeetingAnalyzer:
    prompt = settings.prompts_dir / "analyze_system.md"
    if settings.llm_provider == "claude-code":
        return ClaudeCliAnalyzer(prompt_path=prompt, model=settings.llm_cli_model, effort=settings.llm_effort, usage_log=settings.usage_log)
    return ClaudeAnalyzer(
        prompt_path=prompt,
        model=settings.llm_model,
        effort=settings.llm_effort,
        max_tokens=settings.llm_max_tokens,
        usage_log=settings.usage_log,
    )
