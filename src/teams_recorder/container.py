"""Composition root: the only place that instantiates concrete adapters."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from teams_recorder.adapters.outbound.activities_fs import FsActivityStore
from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_wasapi import WasapiMicCapture, WasapiTapCapture
from teams_recorder.adapters.outbound.capture_mic_coreaudio import CoreAudioMicCapture
from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture
from teams_recorder.adapters.outbound.clock import SystemClock
from teams_recorder.adapters.outbound.curator_claude import ClaudeCurator
from teams_recorder.adapters.outbound.confirm_macos import DialogRecordingConfirmation
from teams_recorder.adapters.outbound.confirm_windows import MessageBoxRecordingConfirmation
from teams_recorder.adapters.outbound.detector_windows import MicUsageCallDetector
from teams_recorder.adapters.outbound.disk_space import DataDirDiskSpace
from teams_recorder.adapters.outbound.energy_ffmpeg import FfmpegEnergyMeter
from teams_recorder.adapters.outbound.detector_pmset import PmsetCallDetector
from teams_recorder.adapters.outbound.language_whispercpp import WhisperCppLanguageDetector
from teams_recorder.adapters.outbound.llm_claude import ClaudeAnalyzer
from teams_recorder.adapters.outbound.minutes_markdown import MarkdownMinutesRenderer
from teams_recorder.adapters.outbound.llm_transport import ApiTransport, ClaudeCodeTransport, StructuredTransport
from teams_recorder.adapters.outbound.mixer_ffmpeg import FfmpegMixer
from teams_recorder.adapters.outbound.notifier_macos import LogNotifier, MacOSNotifier
from teams_recorder.adapters.outbound.notifier_windows import ToastNotifier
from teams_recorder.adapters.outbound.publisher_backlogmd import BacklogMdPublisher
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.speakers_ax import AxSpeakerObserver
from teams_recorder.adapters.outbound.speech_whispercpp import WhisperCppSpeechDetector
from teams_recorder.adapters.outbound.stories_claude import ClaudeStoryWriter
from teams_recorder.adapters.outbound.stories_markdown import MarkdownStoryRenderer
from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber
from teams_recorder.adapters.outbound.verifier_claude import ClaudeClaimVerifier
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.ports import (
    ActivityCurator,
    ActivityStore,
    AudioMixer,
    CallDetector,
    ClaimVerifier,
    Clock,
    DiskSpace,
    EnergyMeter,
    LanguageDetector,
    MeetingAnalyzer,
    MeetingRepository,
    MicCapture,
    MinutesRenderer,
    Notifier,
    ProcessAudioCapture,
    RecordingConfirmation,
    SpeakerObserver,
    SpeechDetector,
    StoryPublisher,
    StoryRenderer,
    StoryWriter,
    Transcriber,
)
from teams_recorder.application.use_cases import (
    AnalyzeMeeting,
    CancelRecording,
    DraftStoriesFromTags,
    PublishUserStories,
    PurgeOldAudio,
    stories_waiting,
    RenderMinutes,
    StartRecording,
    StopRecording,
    TranscribeMeeting,
    VerifyAnalysis,
)
from teams_recorder.application.use_cases.activities import ActivitiesSummary, CurateMeetings, UndoLastPass, doc_format
from teams_recorder.config import Settings, find_tool
from teams_recorder.constants import Bin, Effort, Files, LlmProvider, MicBackend, Platform, StoryDestination, Transcription
from teams_recorder.domain import UserStory


def teams_tap_binary(project_dir: Path, platform: Platform = Platform.MACOS) -> Path:
    return project_dir / (Files.NATIVE_BINARY_WINDOWS if platform is Platform.WINDOWS else Files.NATIVE_BINARY)


def teams_speakers_binary(project_dir: Path) -> Path:
    return project_dir / Files.SPEAKERS_BINARY


@dataclass
class _PlatformAdapters:
    notifier: Notifier
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    detector: CallDetector
    confirmation: RecordingConfirmation | None
    speakers: SpeakerObserver | None   # None: Windows, or [speakers] enabled = false


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
    detector: CallDetector
    minutes: MinutesRenderer
    story_writer: StoryWriter
    story_renderer: StoryRenderer
    story_publishers: list[StoryPublisher]
    curator: ActivityCurator
    activity_store: ActivityStore
    confirmation: RecordingConfirmation | None = None   # None: never ask whether to keep a recording
    disk: DiskSpace | None = None
    retry_transcriber: Transcriber | None = None   # anti-loop pass for a degraded transcript; None: no retry
    verifier: ClaimVerifier | None = None   # checks each analysis's claims against the transcript; None: [verification] off (code checks only)
    speakers: SpeakerObserver | None = None   # reads who speaks from the Teams window; None: Windows, or [speakers] enabled = false
    energy: EnergyMeter | None = None   # level of each raw track per 100 ms, for the user's own lines
    language_detector: LanguageDetector | None = None   # decides each meeting's language; None: [transcription] language is a code ("detector" is the Teams call detector)
    speech_detector: SpeechDetector | None = None   # measures the speech of a recording before it is transcribed; None: [transcription] speech_check = false

    def start_recording(self) -> StartRecording:
        return StartRecording(self.repo, self.process_capture, self.mic_capture, self.notifier, self.clock, self.settings.mic_device, self.disk,
                              self.settings.raw_bytes_per_hour, self.speakers)

    def stop_recording(self) -> StopRecording:
        return StopRecording(self.repo, self.process_capture, self.mic_capture, self.mixer, self.notifier, self.clock, self.speakers, self.energy)

    def cancel_recording(self) -> CancelRecording:
        return CancelRecording(self.repo, self.process_capture, self.mic_capture, self.notifier, self.speakers)

    def transcribe_meeting(self) -> TranscribeMeeting:
        # `language` is the fallback, never settings.language: in detection mode that is "auto", and whisper must never get it
        return TranscribeMeeting(self.repo, self.transcriber, self.settings.fallback_language, self.settings.max_loop_share,
                                 self.retry_transcriber, self.notifier, clock=self.clock, user_name=self.settings.user_name,
                                 language_detector=self.language_detector, languages=self.settings.languages, speech_detector=self.speech_detector)

    def analyze_meeting(self) -> AnalyzeMeeting:
        # Without a verifier ([verification] off) the two code checks still run: they need no model call (PRD decision 11).
        return AnalyzeMeeting(self.repo, self.analyzer, self.minutes, VerifyAnalysis(self.verifier, self.settings.user_name))

    def render_minutes(self) -> RenderMinutes:
        return RenderMinutes(self.repo, self.minutes)

    def curate_meetings(self) -> CurateMeetings:
        """The activities curator's pass. `[activities] enabled` is not read here: it switches off only the automatic triggers
        (the daemon's worker, `trec analyze`), never the explicit `trec activities` commands."""
        return CurateMeetings(self.repo, self.activity_store, self.curator, self.notifier, self.clock,
                              user_name=self.settings.user_name, notify=self.settings.activities_notify)

    def activities_summary(self) -> ActivitiesSummary:
        return ActivitiesSummary(self.repo, self.activity_store, self.curate_meetings())

    def undo_last_pass(self) -> UndoLastPass:
        return UndoLastPass(self.activity_store, self.clock)

    def pipeline(self, after_analysis: Callable[[str], None] | None = None) -> Pipeline:
        return Pipeline(self.repo, self.notifier, self.stop_recording(), self.transcribe_meeting(), self.analyze_meeting(), after_analysis)

    def draft_stories_from_tags(self) -> DraftStoriesFromTags:
        return DraftStoriesFromTags(self.repo, self.activity_store, self.story_writer, self.story_renderer, self.clock,
                                    self.settings.story_dedup_days)

    def stories_waiting(self) -> list[UserStory]:
        destinations = [p.destination for p in self.story_publishers]
        return stories_waiting(self.repo, self.clock.now().date(), self.settings.story_dedup_days, destinations)

    def publish_user_stories(self) -> PublishUserStories:
        return PublishUserStories(self.repo, self.story_publishers, self.story_renderer, self.notifier, self.clock,
                                  self.settings.story_dedup_days)

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
        speakers=build_speaker_observer(settings),
    )


def build_speaker_observer(settings: Settings) -> SpeakerObserver | None:
    """The helper's observer; None when [speakers] enabled is false. macOS only: the Windows adapters pass None."""
    if not settings.speakers_enabled:
        return None
    return AxSpeakerObserver(teams_speakers_binary(settings.project_dir), settings.data_dir / Files.RUN_DIR, log_path=settings.speakers_log)


def _windows_adapters(settings: Settings, headless: bool) -> _PlatformAdapters:
    binary = teams_tap_binary(settings.project_dir, Platform.WINDOWS)
    stop_dir = settings.data_dir / Files.RUN_DIR
    return _PlatformAdapters(
        notifier=LogNotifier() if headless else ToastNotifier(),
        process_capture=WasapiTapCapture(binary, stop_dir, log_path=settings.capture_log, bit_depth=settings.bit_depth),
        mic_capture=WasapiMicCapture(binary, stop_dir, log_path=settings.capture_log, bit_depth=settings.bit_depth),   # audio.mic_backend is macOS-only
        detector=MicUsageCallDetector(settings.teams_process_name),
        confirmation=MessageBoxRecordingConfirmation(settings.confirm_timeout_seconds) if settings.confirm_recording and not headless else None,
        speakers=None,   # the helper reads the macOS Accessibility API
    )


def build_container(settings: Settings, *, headless: bool = False) -> Container:
    transport = build_transport(settings)  # shared by the analyzer and the story writer
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
            threads=settings.whisper_threads, vad_model_path=settings.vad_model_path, max_context=settings.whisper_max_context,
        ),
        retry_transcriber=build_retry_transcriber(settings),
        verifier=build_verifier(settings),
        analyzer=ClaudeAnalyzer(transport, prompt_path=settings.prompts_dir / Files.ANALYZE_PROMPT, user_name=settings.user_name),
        detector=platform.detector,
        minutes=MarkdownMinutesRenderer(settings.user_name),
        story_writer=ClaudeStoryWriter(
            transport, settings.story_guide_path, prompt_path=settings.prompts_dir / Files.STORIES_PROMPT, user_name=settings.user_name,
        ),
        story_renderer=MarkdownStoryRenderer(),
        story_publishers=build_story_publishers(settings),
        curator=build_curator(settings),
        activity_store=build_activity_store(settings),
        confirmation=platform.confirmation,
        disk=DataDirDiskSpace(settings.data_dir),
        speakers=platform.speakers,
        energy=FfmpegEnergyMeter(ffmpeg=ffmpeg),
        language_detector=build_language_detector(settings),
        speech_detector=build_speech_detector(settings),
    )


def _uses_vad(model: Path | None) -> bool:
    return model is not None and model.exists()   # the transcriber leaves VAD out when its model is missing


def build_language_detector(settings: Settings) -> WhisperCppLanguageDetector | None:
    """Decides each meeting's language from samples of its audio, with the transcriber's model, whisper-cli, ffmpeg and threads.
    None when [transcription] language is a code: nothing is detected."""
    if not settings.detects_language:
        return None
    return WhisperCppLanguageDetector(
        settings.whisper_model_path, whisper_cli=find_tool(Bin.WHISPER_CLI, settings.project_dir),
        ffmpeg=find_tool(Bin.FFMPEG, settings.project_dir), threads=settings.whisper_threads,
    )


def build_speech_detector(settings: Settings) -> WhisperCppSpeechDetector | None:
    """Measures the speech of a recording before it is transcribed: Silero VAD (`settings.speech_model_path`, the `vad_model` the retry
    uses) run by whisper.cpp's `whisper-vad-speech-segments`, with ffmpeg and the transcriber's threads. None when
    [transcription] speech_check is false: nothing is checked."""
    model = settings.speech_model_path
    if model is None:
        return None
    return WhisperCppSpeechDetector(
        model, vad_tool=find_tool(Bin.WHISPER_VAD, settings.project_dir), ffmpeg=find_tool(Bin.FFMPEG, settings.project_dir),
        threads=settings.whisper_threads,
    )


def build_retry_transcriber(settings: Settings) -> WhisperCppTranscriber | None:
    """The second pass for a degraded transcript: no text context (-mc 0) and, with retry_vad, Silero VAD.

    None when [transcription] retry_on_loop is off, or when the retry would only repeat the first pass
    (max_context already 0 and no VAD to add: retry_vad off, VAD already on, or its model missing).
    """
    if not settings.retry_on_loop:
        return None
    vad = settings.retry_vad_model_path if _uses_vad(settings.retry_vad_model_path) else None
    adds_vad = vad is not None and not _uses_vad(settings.vad_model_path)
    if settings.whisper_max_context == Transcription.ANTI_LOOP_MAX_CONTEXT and not adds_vad:
        return None
    return WhisperCppTranscriber(
        settings.whisper_model_path, whisper_cli=find_tool(Bin.WHISPER_CLI, settings.project_dir), ffmpeg=find_tool(Bin.FFMPEG, settings.project_dir),
        threads=settings.whisper_threads, vad_model_path=vad, max_context=Transcription.ANTI_LOOP_MAX_CONTEXT,
    )


# Story destinations: a table from each [stories] destinations value to the builder of its
# publisher (configuration picks the adapter, as llm.provider does in build_transport).
# A new destination is a new adapter plus one entry here.
def _backlog_md(settings: Settings) -> StoryPublisher:
    return BacklogMdPublisher(
        settings.backlog_project_dir, settings.backlog_status, settings.backlog_labels,
        drafts_dir=settings.data_dir / Files.PLANS_DIR, binary=find_tool(Bin.BACKLOG, settings.project_dir),
    )


_PUBLISHERS: dict[StoryDestination, Callable[[Settings], StoryPublisher]] = {
    StoryDestination.BACKLOG_MD: _backlog_md,
}


def build_story_publishers(settings: Settings) -> list[StoryPublisher]:
    return [_PUBLISHERS[destination](settings) for destination in settings.story_destinations]


def build_transport(settings: Settings) -> StructuredTransport:
    return _transport(settings, settings.llm_model, settings.llm_cli_model, settings.llm_effort)


def build_verifier(settings: Settings) -> ClaimVerifier | None:
    """The claim verifier, on its own transport: [verification] picks a smaller model and effort than the analysis
    (Sonnet at medium, PRD decision 1), on the same provider. Its calls go to the same usage log, tagged verify:<id>.
    None when [verification] enabled is false; the code checks of VerifyAnalysis still run."""
    if not settings.verify_enabled:
        return None
    transport = _transport(settings, settings.verify_model, settings.verify_cli_model, settings.verify_effort)
    return ClaudeClaimVerifier(transport, prompt_path=settings.prompts_dir / Files.VERIFY_PROMPT, user_name=settings.user_name)


def build_curator(settings: Settings) -> ActivityCurator:
    """The activities curator, on its own transport: [activities] model (API) or cli_model (Claude Code) and effort, on the
    provider of [llm]. Its calls go to the same usage log, tagged curate:<id> and curate-repair:<id>."""
    transport = _transport(settings, settings.activities_model, settings.activities_cli_model, settings.activities_effort)
    return ClaudeCurator(transport, prompt_path=settings.prompts_dir / Files.CURATE_PROMPT)


def build_activity_store(settings: Settings) -> ActivityStore:
    """The activities document, its base, versions, archive and pass log under <data_dir>/activities."""
    return FsActivityStore(settings.data_dir, doc_format(), settings.activities_keep_versions)


def _transport(settings: Settings, model: str, cli_model: str, effort: Effort) -> StructuredTransport:
    if settings.llm_provider is LlmProvider.CLAUDE_CODE:
        return ClaudeCodeTransport(model=cli_model, effort=effort, usage_log=settings.usage_log)
    return ApiTransport(model=model, effort=effort, max_tokens=settings.llm_max_tokens, usage_log=settings.usage_log)
