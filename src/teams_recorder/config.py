"""Loads config.toml and .env into an immutable Settings object."""
from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv

from teams_recorder.constants import (
    Audio,
    Confirm,
    Detector,
    Effort,
    Env,
    Files,
    Llm,
    LlmProvider,
    MicBackend,
    Planner,
    Platform,
    Stories,
    Windows,
    ggml_model_file,
    raw_bytes_per_hour,
)
from teams_recorder.messages import Err

# Backwards-compatible names: the CLI and the tests import these from here.
ENV_PROJECT_DIR = Env.PROJECT_DIR
APP_SUPPORT_DIR = Files.APP_SUPPORT_DIR

E = TypeVar("E", bound=StrEnum)


def current_platform() -> Platform:
    return Platform.WINDOWS if sys.platform == Platform.WINDOWS else Platform.MACOS


def find_tool(name: str, project_dir: Path) -> str:
    """Full path of an external tool: on the PATH, else under <project>/tools (where the Windows
    installer unpacks whisper.cpp). Falls back to the bare name so errors still name it."""
    found = shutil.which(name)
    if found:
        return found
    tools = project_dir / Files.TOOLS_DIR
    if tools.is_dir():
        for candidate in sorted(tools.rglob(f"{name}*")):
            if candidate.is_file() and candidate.stem == name:
                return str(candidate)
    return name


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    data_dir: Path
    mic_device: str
    mic_backend: MicBackend
    teams_process_name: str
    bitrate_kbps: int
    bit_depth: int
    denoise: bool
    poll_seconds: int
    start_after_positive_polls: int
    stop_after_negative_polls: int
    whisper_model: str
    language: str
    models_dir: Path
    whisper_threads: int
    vad: bool
    vad_model: str
    llm_provider: LlmProvider
    llm_model: str
    llm_cli_model: str
    llm_effort: Effort
    llm_max_tokens: int
    plan_hour: int
    user_name: str
    confirm_recording: bool
    confirm_timeout_seconds: int
    retention_days: int
    anthropic_api_key: str | None
    platform: Platform = Platform.MACOS
    stories_enabled: bool = Stories.ENABLED
    story_guide: Path | None = None   # None: <project>/prompts/user_story_guide.md

    @property
    def raw_bytes_per_hour(self) -> int:
        return raw_bytes_per_hour(self.bit_depth)

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def whisper_model_path(self) -> Path:
        return self.models_dir / ggml_model_file(self.whisper_model)

    @property
    def vad_model_path(self) -> Path | None:
        return (self.models_dir / ggml_model_file(self.vad_model)) if self.vad else None

    @property
    def prompts_dir(self) -> Path:
        return self.project_dir / Files.PROMPTS_DIR

    @property
    def story_guide_path(self) -> Path:
        return self.story_guide or self.prompts_dir / Files.STORY_GUIDE

    @property
    def log_dir(self) -> Path:
        return self.data_dir / Files.LOG_DIR

    @property
    def usage_log(self) -> Path:
        return self.log_dir / Files.LLM_USAGE_LOG

    @property
    def daemon_log(self) -> Path:
        return self.log_dir / Files.DAEMON_LOG

    @property
    def capture_log(self) -> Path:
        return self.log_dir / Files.CAPTURE_LOG


def _parse_enum(kind: type[E], value: object, template: str) -> E:
    """Parse a config value into a StrEnum member; `template` is the Err message on failure."""
    try:
        return kind(str(value).strip().lower())
    except ValueError:
        options = tuple(member.value for member in kind)
        raise ValueError(template.format(value=value, options=options)) from None


def default_project_dir() -> Path:
    env = os.environ.get(Env.PROJECT_DIR)
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2]


def is_icloud_synced(path: Path) -> bool:
    """Heuristic: paths under ~/Library/Mobile Documents are synced with iCloud."""
    try:
        return Files.ICLOUD_MARKER in str(path.resolve())
    except OSError:
        return False


def is_tcc_protected(path: Path) -> bool:
    """True when the path is under ~/Documents, ~/Desktop or ~/Downloads.

    Background processes (launchd) touching files in these TCC-protected folders trigger
    permission prompts they cannot answer; observed as "[Errno 11] Resource deadlock
    avoided" when executing binaries and writing logs.
    """
    try:
        rel = path.resolve().relative_to(Path.home())
    except (ValueError, OSError):
        return False
    return bool(rel.parts) and rel.parts[0] in Files.TCC_PROTECTED_FOLDERS


def resolve_data_dir(project_dir: Path, configured: str | None, platform: Platform = Platform.MACOS) -> Path:
    """Explicit `paths.data_dir` wins; a relative value is resolved against the project dir."""
    if not configured:
        return default_data_dir(project_dir, platform)
    path = Path(configured).expanduser()
    return path if path.is_absolute() else project_dir / path


def default_data_dir(project_dir: Path, platform: Platform = Platform.MACOS) -> Path:
    if platform is Platform.MACOS and (is_icloud_synced(project_dir) or is_tcc_protected(project_dir)):
        return Files.APP_SUPPORT_DIR
    return project_dir / Files.LOCAL_DATA_DIR


def _parse_bit_depth(value: object) -> int:
    try:
        bits = int(str(value))
    except ValueError:
        bits = 0
    if bits not in Audio.BIT_DEPTHS:
        raise ValueError(Err.INVALID_BIT_DEPTH.format(value=value, options=Audio.BIT_DEPTHS))
    return bits


def load_settings(project_dir: Path | None = None, platform: Platform | None = None) -> Settings:
    platform = platform or current_platform()
    project_dir = (project_dir or default_project_dir()).resolve()
    load_dotenv(project_dir / Files.DOTENV, override=False)

    cfg_path = project_dir / Files.CONFIG
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)

    paths = raw.get("paths", {})
    audio = raw.get("audio", {})
    detector = raw.get("detector", {})
    transcription = raw.get("transcription", {})
    llm = raw.get("llm", {})
    planner = raw.get("planner", {})
    user = raw.get("user", {})
    confirmation = raw.get("confirmation", {})
    stories = raw.get("stories", {})

    data_dir = resolve_data_dir(project_dir, paths.get("data_dir"), platform)
    teams_default = (
        str(audio.get("teams_process_name_windows", Windows.TEAMS_PROCESS)) if platform is Platform.WINDOWS
        else str(audio.get("teams_process_name", Detector.TEAMS_PROCESS))
    )

    return Settings(
        project_dir=project_dir,
        data_dir=data_dir,
        mic_device=str(audio.get("mic_device", Audio.DEFAULT_MIC_DEVICE)),
        mic_backend=_parse_enum(MicBackend, audio.get("mic_backend", MicBackend.COREAUDIO), Err.INVALID_MIC_BACKEND),
        teams_process_name=os.environ.get(Env.TEAMS_PROCESS) or teams_default,
        bitrate_kbps=int(audio.get("bitrate_kbps", Audio.DEFAULT_BITRATE_KBPS)),
        bit_depth=_parse_bit_depth(audio.get("bit_depth", Audio.DEFAULT_BIT_DEPTH)),
        denoise=bool(audio.get("denoise", True)),
        poll_seconds=int(detector.get("poll_seconds", Detector.POLL_SECONDS)),
        start_after_positive_polls=int(detector.get("start_after_positive_polls", Detector.START_AFTER)),
        stop_after_negative_polls=int(detector.get("stop_after_negative_polls", Detector.STOP_AFTER)),
        whisper_model=str(transcription.get("whisper_model", Audio.DEFAULT_WHISPER_MODEL)),
        language=str(transcription.get("language", Audio.DEFAULT_LANGUAGE)),
        models_dir=Path(transcription["models_dir"]).expanduser() if transcription.get("models_dir") else data_dir / Files.MODELS_DIR,
        whisper_threads=int(transcription.get("threads", Audio.DEFAULT_WHISPER_THREADS)),
        vad=bool(transcription.get("vad", False)),
        vad_model=str(transcription.get("vad_model", Audio.DEFAULT_VAD_MODEL)),
        llm_provider=_parse_enum(LlmProvider, os.environ.get(Env.LLM_PROVIDER) or llm.get("provider", LlmProvider.API), Err.INVALID_PROVIDER),
        llm_model=str(llm.get("model", Llm.DEFAULT_API_MODEL)),
        llm_cli_model=str(llm.get("cli_model", Llm.DEFAULT_CLI_MODEL)),
        llm_effort=_parse_enum(Effort, llm.get("effort", Effort.HIGH), Err.INVALID_EFFORT),
        llm_max_tokens=int(llm.get("max_tokens", Llm.DEFAULT_MAX_TOKENS)),
        plan_hour=int(planner.get("hour", Planner.DEFAULT_HOUR)),
        user_name=str(user.get("name", "")).strip(),
        confirm_recording=bool(confirmation.get("enabled", Confirm.ENABLED)),
        confirm_timeout_seconds=int(confirmation.get("timeout_seconds", Confirm.TIMEOUT_SECONDS)),
        retention_days=int(planner.get("retention_days", Planner.RETENTION_DAYS)),
        anthropic_api_key=os.environ.get(Env.API_KEY) or None,
        platform=platform,
        stories_enabled=bool(stories.get("enabled", Stories.ENABLED)),
        story_guide=_project_path(project_dir, stories.get("guide")),
    )


def _project_path(project_dir: Path, configured: str | None) -> Path | None:
    """A configured file path; a relative one is resolved against the project dir. Empty = None."""
    if not configured:
        return None
    path = Path(configured).expanduser()
    return path if path.is_absolute() else project_dir / path
