"""Project-wide constants and enumerations: names, paths, binaries, environment variables.

Single place to change an identifier that the code repeats: a file or folder name, an
external command, a LaunchAgent label, an environment variable, a default value.
User-facing text lives in `messages.py`; meeting file names in `domain/status.py`.
"""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path

APP_NAME = "teams-recorder"
CLI_NAME = "trec"


# --- enumerations ----------------------------------------------------------
class LlmProvider(StrEnum):
    API = "api"                  # Claude API with ANTHROPIC_API_KEY (prepaid credit)
    CLAUDE_CODE = "claude-code"  # Claude Code headless (`claude -p`, subscription)


class MicBackend(StrEnum):
    COREAUDIO = "coreaudio"  # teams-tap --mic (AVAudioEngine); survives device reconfiguration
    FFMPEG = "ffmpeg"        # avfoundation; stalled when Teams opened the microphone


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


# --- environment variables ---------------------------------------------------
class Env:
    PROJECT_DIR = "TEAMS_RECORDER_DIR"
    LLM_PROVIDER = "TREC_LLM_PROVIDER"
    TEAMS_PROCESS = "TREC_TEAMS_PROCESS"
    API_KEY = "ANTHROPIC_API_KEY"
    ANTHROPIC_PREFIX = "ANTHROPIC_"
    COVERAGE_PREFIX = "COV_CORE_"
    REAL_WHISPER = "TREC_REAL_WHISPER"
    REAL_CLAUDE = "TREC_REAL_CLAUDE"
    REAL_CLAUDE_CLI = "TREC_REAL_CLAUDE_CLI"


# --- external binaries -------------------------------------------------------
class Bin:
    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"
    WHISPER_CLI = "whisper-cli"
    CLAUDE = "claude"
    PMSET = "pmset"
    PGREP = "pgrep"
    OSASCRIPT = "osascript"
    LAUNCHCTL = "launchctl"
    SWIFT = "swift"
    TEAMS_TAP = "teams-tap"


# --- files and folders -------------------------------------------------------
class Files:
    LOCAL_DATA_DIR = "data"          # data dir inside the project, used only outside iCloud/TCC folders
    CONFIG = "config.toml"
    DOTENV = ".env"
    PROMPTS_DIR = "prompts"
    ANALYZE_PROMPT = "analyze_system.md"
    PLAN_PROMPT = "plan_system.md"
    RECORDINGS_DIR = "recordings"
    PLANS_DIR = "plans"
    PLAN_GLOB = "????-??-??.json"     # every saved plan (see PLAN_JSON below)
    TMP_SUFFIX = ".tmp"               # atomic writes: <name>.tmp then os.replace
    MODELS_DIR = "models"
    LOG_DIR = "log"
    DEBUG_DIR = "debug"              # raw tracks kept on mixing anomalies
    OPEN_ACTIONS = "open_actions.json"
    ACTIVE_RECORDING = "current_recording.json"
    DAEMON_LOG = "teams-recorder.log"
    CAPTURE_LOG = "capture.log"
    LLM_USAGE_LOG = "llm_usage.jsonl"
    NATIVE_BINARY = Path("native") / "teams-tap" / ".build" / "release" / "teams-tap"
    BUILD_NATIVE_SCRIPT = "scripts/build-native.sh"
    DOWNLOAD_MODEL_SCRIPT = "scripts/download-model.sh"
    APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
    ICLOUD_MARKER = "Mobile Documents"
    TCC_PROTECTED_FOLDERS = ("Documents", "Desktop", "Downloads")
    PLIST_SUBDIR = Path("Library") / "LaunchAgents"   # relative to the home dir (resolved at call time so tests can fake it)
    PLIST_DIR = Path.home() / PLIST_SUBDIR
    VENV_TREC = Path(".venv") / "bin" / CLI_NAME       # relative to the project dir
    AGENT_OUT_LOG = "{name}.out.log"                   # name: last label segment (daemon / planner)
    AGENT_ERR_LOG = "{name}.err.log"
    PLAN_MARKDOWN = "{day}.md"                         # day: ISO date
    PLAN_JSON = "{day}.json"


def ggml_model_file(name: str) -> str:
    return f"ggml-{name}.bin"


# --- launchd ---------------------------------------------------------------------
class Launchd:
    DAEMON_LABEL = f"local.{APP_NAME}.daemon"
    PLANNER_LABEL = f"local.{APP_NAME}.planner"
    PATH = ":".join(["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin"), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    THROTTLE_SECONDS = 10
    BOOTSTRAP_RETRIES = 10
    BOOTSTRAP_RETRY_DELAY = 1.0
    BOOTOUT_TIMEOUT = 15.0
    BOOTOUT_POLL_SECONDS = 0.5
    PLANNER_WEEKDAYS = range(1, 6)  # Monday..Friday in StartCalendarInterval
    DOMAIN = "gui/{uid}"            # launchctl target domain for the logged-in user
    DAEMON_ARGS = ("daemon",)       # `trec` arguments run by each agent
    PLANNER_ARGS = ("plan", "--purge")


# --- LLM -------------------------------------------------------------------------
class Llm:
    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    DEFAULT_API_MODEL = "claude-opus-5-5"
    DEFAULT_CLI_MODEL = "opus"
    DEFAULT_MAX_TOKENS = 16000
    MIN_WORDS = 20                  # below this an LLM call is not worth it
    OWNER_SELF = "usuário"          # data contract with the prompts: the recording owner
    OWNER_UNKNOWN = "indefinido"    # data contract with the prompts: unknown owner
    MAX_PREVIOUS_PLAN_CHARS = 6000
    CLAUDE_CODE_TIMEOUT = 900.0


# --- audio -----------------------------------------------------------------------
class Audio:
    SAMPLE_RATE = 48000
    WHISPER_SAMPLE_RATE = 16000
    DEFAULT_BITRATE_KBPS = 64
    MIN_TRACK_BYTES = 1024          # a WAV header is 44 bytes; under 1 KB is junk
    ANOMALY_RATIO = 0.5             # a track under half the longest one is an anomaly
    TRACK_FILTER = "highpass=f=80,afftdn=nf=-25:tn=1"
    MASTER_FILTER = "loudnorm=I=-18:TP=-2:LRA=11,alimiter=limit=0.891:level=0"
    WAIT_AUDIO_SECONDS = 20.0
    DEFAULT_MIC_DEVICE = "default"
    DEFAULT_LANGUAGE = "pt"
    DEFAULT_WHISPER_MODEL = "large-v3-turbo-q5_0"
    DEFAULT_WHISPER_THREADS = 0     # 0 = let whisper-cli decide
    DEFAULT_VAD_MODEL = "silero-v5.1.2"
    VAD_ARGS = ["-vt", "0.5", "-vsd", "300", "-vp", "150"]


# --- output formats of external tools (parsing) -------------------------------------
class Parse:
    FFMPEG_DURATION = r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)"
    FFMPEG_MEAN_VOLUME = r"mean_volume: (-?[\d.]+) dB"
    FFMPEG_MAX_VOLUME = r"max_volume: (-?[\d.]+) dB"
    LAUNCHCTL_PID = "pid = "
    LAUNCHCTL_STATE = "state = "
    OSASCRIPT_NOTIFY = 'display notification "{body}" with title "{title}" subtitle "{subtitle}"'


# --- detection -------------------------------------------------------------------
class Detector:
    TEAMS_PROCESS = "MSTeams"
    POLL_SECONDS = 1     # pmset is cheap; 1 s keeps the start/stop lag at ~1-2 s / ~5 s
    START_AFTER = 1      # Teams' call assertion is reliable; short false starts are dropped by the 20-word cut
    STOP_AFTER = 5
    CALL_ASSERTIONS = ("PreventUserIdleDisplaySleep", "PreventUserIdleSystemSleep", "NoIdleSleepAssertion", "NoDisplaySleepAssertion")
    PMSET_TIMEOUT = 10.0


# --- processes -------------------------------------------------------------------
class Proc:
    TAP_STARTUP_GRACE = 1.0         # seconds a recorder must survive before start() returns
    MIC_STARTUP_GRACE = 1.5
    FFMPEG_TIMEOUT = 600.0          # mixing / probing one meeting
    WHISPER_TIMEOUT = 3 * 3600.0
    IO_RETRIES = 12                 # file reads/writes blocked transiently by TCC
    IO_RETRY_DELAY = 0.5
    SPAWN_RETRIES = 12
    SPAWN_RETRY_DELAY = 0.5
    STOP_TIMEOUT = 10.0
    WARMUP_TIMEOUT = 15.0
    NOTIFY_TIMEOUT = 5.0
    WORKER_JOIN_TIMEOUT = 30.0      # daemon waits this long for post-processing threads on shutdown


# --- logging ---------------------------------------------------------------------
class Logging:
    FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ROTATE_WHEN = "midnight"
    BACKUP_COUNT = 30


class Planner:
    DEFAULT_HOUR = 18
    RETENTION_DAYS = 30
