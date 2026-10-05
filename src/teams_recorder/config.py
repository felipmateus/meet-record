"""Loads config.toml and .env into an immutable Settings object."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_PROJECT_DIR = "TEAMS_RECORDER_DIR"
ENV_LLM_PROVIDER = "TREC_LLM_PROVIDER"
ENV_TEAMS_PROCESS = "TREC_TEAMS_PROCESS"   # for tests: simulate Teams with another process
LLM_PROVIDERS = ("api", "claude-code")
ICLOUD_MARKER = "Mobile Documents"
# Folders protected by macOS TCC: background processes (launchd) touching files in them
# trigger permission prompts they cannot answer; observed as "[Errno 11] Resource deadlock
# avoided" when executing binaries and writing logs.
PROTECTED_FOLDERS = ("Documents", "Desktop", "Downloads")
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "teams-recorder"


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    data_dir: Path
    mic_device: str
    mic_backend: str
    teams_process_name: str
    bitrate_kbps: int
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
    llm_provider: str
    llm_model: str
    llm_cli_model: str
    llm_effort: str
    llm_max_tokens: int
    plan_hour: int
    retention_days: int
    anthropic_api_key: str | None

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def whisper_model_path(self) -> Path:
        return self.models_dir / f"ggml-{self.whisper_model}.bin"

    @property
    def vad_model_path(self) -> Path | None:
        return (self.models_dir / f"ggml-{self.vad_model}.bin") if self.vad else None

    @property
    def prompts_dir(self) -> Path:
        return self.project_dir / "prompts"

    @property
    def usage_log(self) -> Path:
        return self.data_dir / "log" / "llm_usage.jsonl"

    @property
    def daemon_log(self) -> Path:
        return self.data_dir / "log" / "teams-recorder.log"


def _provider(value: object) -> str:
    v = str(value).strip().lower()
    if v not in LLM_PROVIDERS:
        raise ValueError(f"invalid llm.provider: {value!r}; use one of {LLM_PROVIDERS}")
    return v


def default_project_dir() -> Path:
    env = os.environ.get(ENV_PROJECT_DIR)
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2]


def is_icloud_synced(path: Path) -> bool:
    """Heuristic: paths under ~/Library/Mobile Documents are synced with iCloud."""
    try:
        return ICLOUD_MARKER in str(path.resolve())
    except OSError:
        return False


def is_tcc_protected(path: Path) -> bool:
    """True when the path is under ~/Documents, ~/Desktop or ~/Downloads."""
    try:
        rel = path.resolve().relative_to(Path.home())
    except (ValueError, OSError):
        return False
    return bool(rel.parts) and rel.parts[0] in PROTECTED_FOLDERS


def default_data_dir(project_dir: Path) -> Path:
    if is_icloud_synced(project_dir) or is_tcc_protected(project_dir):
        return APP_SUPPORT_DIR
    return project_dir / "data"


def load_settings(project_dir: Path | None = None) -> Settings:
    project_dir = (project_dir or default_project_dir()).resolve()
    load_dotenv(project_dir / ".env", override=False)

    cfg_path = project_dir / "config.toml"
    raw: dict = {}
    if cfg_path.exists():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)

    paths = raw.get("paths", {})
    audio = raw.get("audio", {})
    detector = raw.get("detector", {})
    transcription = raw.get("transcription", {})
    llm = raw.get("llm", {})
    planner = raw.get("planner", {})

    data_dir = Path(paths["data_dir"]).expanduser() if paths.get("data_dir") else default_data_dir(project_dir)

    return Settings(
        project_dir=project_dir,
        data_dir=data_dir,
        mic_device=str(audio.get("mic_device", "default")),
        mic_backend=str(audio.get("mic_backend", "coreaudio")),
        teams_process_name=os.environ.get(ENV_TEAMS_PROCESS) or str(audio.get("teams_process_name", "MSTeams")),
        bitrate_kbps=int(audio.get("bitrate_kbps", 64)),
        denoise=bool(audio.get("denoise", True)),
        poll_seconds=int(detector.get("poll_seconds", 3)),
        start_after_positive_polls=int(detector.get("start_after_positive_polls", 2)),
        stop_after_negative_polls=int(detector.get("stop_after_negative_polls", 5)),
        whisper_model=str(transcription.get("whisper_model", "large-v3-turbo-q5_0")),
        language=str(transcription.get("language", "pt")),
        models_dir=Path(transcription["models_dir"]).expanduser() if transcription.get("models_dir") else data_dir / "models",
        whisper_threads=int(transcription.get("threads", 0)),
        vad=bool(transcription.get("vad", False)),
        vad_model=str(transcription.get("vad_model", "silero-v5.1.2")),
        llm_provider=_provider(os.environ.get(ENV_LLM_PROVIDER) or llm.get("provider", "api")),
        llm_model=str(llm.get("model", "claude-opus-5-5")),
        llm_cli_model=str(llm.get("cli_model", "opus")),
        llm_effort=str(llm.get("effort", "high")),
        llm_max_tokens=int(llm.get("max_tokens", 16000)),
        plan_hour=int(planner.get("hour", 18)),
        retention_days=int(planner.get("retention_days", 30)),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
    )
