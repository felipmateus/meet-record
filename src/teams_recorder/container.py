"""Composition root: único lugar que instancia adaptadores concretos.

Adaptadores ainda não implementados ficam como None; a CLI informa a fase em que chegam.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture
from teams_recorder.adapters.outbound.clock import SystemClock
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
from teams_recorder.application.use_cases import (
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
    detector: CallDetector | None = None
    analyzer: MeetingAnalyzer | None = None
    planner: Planner | None = None

    def start_recording(self) -> StartRecording:
        return StartRecording(self.repo, self.process_capture, self.mic_capture, self.notifier, self.clock, self.settings.mic_device)

    def stop_recording(self) -> StopRecording:
        return StopRecording(self.repo, self.process_capture, self.mic_capture, self.mixer, self.notifier, self.clock)

    def cancel_recording(self) -> CancelRecording:
        return CancelRecording(self.repo, self.process_capture, self.mic_capture, self.notifier)

    def transcribe_meeting(self) -> TranscribeMeeting:
        return TranscribeMeeting(self.repo, self.transcriber, self.settings.language)

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
        mic_capture=FfmpegMicCapture(log_path=capture_log),
        mixer=FfmpegMixer(bitrate_kbps=settings.bitrate_kbps),
        transcriber=WhisperCppTranscriber(settings.whisper_model_path, threads=settings.whisper_threads),
    )
