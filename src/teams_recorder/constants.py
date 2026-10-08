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
class Platform(StrEnum):
    MACOS = "darwin"     # sys.platform values
    WINDOWS = "win32"


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
    WINDOWS_USER = "USERNAME"
    WINDOWS_DOMAIN = "USERDOMAIN"


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
    POWERSHELL = "powershell"     # Windows PowerShell 5.1, present on every Windows 10/11
    SCHTASKS = "schtasks"
    DOTNET = "dotnet"


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
    NATIVE_BINARY_WINDOWS = Path("native") / "teams-tap-win" / "bin" / "Release" / "net8.0" / "win-x64" / "publish" / "teams-tap.exe"
    BUILD_NATIVE_SCRIPT_WINDOWS = r"scripts\build-native-windows.ps1"
    DOWNLOAD_MODEL_SCRIPT_WINDOWS = r"scripts\download-model.ps1"
    RUN_DIR = "run"                                    # in the data dir: stop files for the Windows recorders
    STOP_FILE = "{meeting_id}.{track}.stop"            # track: the WAV file stem
    TOOLS_DIR = "tools"                                # in the project: tools the Windows installer downloads (whisper.cpp)
    TASKS_DIR = "tasks"                                # in the data dir: Task Scheduler definitions written on install
    TASK_XML = "{name}.xml"
    VENV_PYTHONW = Path(".venv") / "Scripts" / "pythonw.exe"   # Windows: runs without a console window
    CLI_MODULE = "teams_recorder.adapters.inbound.cli"
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


def raw_bytes_per_hour(bit_depth: int) -> int:
    """Disk used per hour by both raw tracks before mixing (1.04 GB at 16-bit, 2.07 GB at 32-bit)."""
    return Audio.SAMPLE_RATE * Audio.RAW_CHANNELS * (bit_depth // 8) * 3600


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
    MIX_TIMEOUT_FACTOR = 2.0        # mixing may take up to 2x the meeting length (never less than Proc.FFMPEG_TIMEOUT)
    PARTIAL_INFIX = ".partial"      # mixing writes audio.partial.m4a and renames it only on success
    BIT_DEPTHS = (16, 32)           # raw WAV sample format: 16-bit integer or 32-bit float
    DEFAULT_BIT_DEPTH = 16          # enough for speech and transcription; 32 doubles the size
    RAW_CHANNELS = 3                # Teams track (stereo) + microphone (mono)
    WAV_CODECS = {16: "pcm_s16le", 32: "pcm_f32le"}   # ffmpeg microphone backend
    LOW_DISK_HOURS = 2.0            # warn at recording start when less than this much recording fits
    CRITICAL_DISK_BYTES = 1_000_000_000  # warn once during a call below this


# --- output formats of external tools (parsing) -------------------------------------
class Parse:
    FFMPEG_DURATION = r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)"
    FFMPEG_MEAN_VOLUME = r"mean_volume: (-?[\d.]+) dB"
    FFMPEG_MAX_VOLUME = r"max_volume: (-?[\d.]+) dB"
    LAUNCHCTL_PID = "pid = "
    LAUNCHCTL_STATE = "state = "
    OSASCRIPT_NOTIFY = 'display notification "{body}" with title "{title}" subtitle "{subtitle}"'
    OSASCRIPT_CONFIRM = (
        'display dialog "{body}" with title "{title}" buttons {{"{discard}", "{keep}"}} '
        'default button "{keep}" giving up after {timeout} with icon note'
    )
    DIALOG_BUTTON = "button returned:"   # osascript output: "button returned:Keep, gave up:false"
    DIALOG_GAVE_UP = "gave up:true"


# --- detection -------------------------------------------------------------------
class Detector:
    TEAMS_PROCESS = "MSTeams"            # macOS; see Windows.TEAMS_PROCESS
    POLL_SECONDS = 1     # pmset is cheap; 1 s keeps the start/stop lag at ~1-2 s / ~5 s
    START_AFTER = 1      # Teams' call assertion is reliable; short false starts are dropped by the 20-word cut
    STOP_AFTER = 5
    CALL_ASSERTIONS = ("PreventUserIdleDisplaySleep", "PreventUserIdleSystemSleep", "NoIdleSleepAssertion", "NoDisplaySleepAssertion")
    PMSET_TIMEOUT = 10.0


# --- Windows ---------------------------------------------------------------------
class Windows:
    TEAMS_PROCESS = "ms-teams.exe"   # new Teams; the root process of its tree is the capture target
    MIN_BUILD = 19041                # Windows 10 2004: first build with process loopback capture
    # Microphone usage per app, kept by Windows for the privacy indicator: LastUsedTimeStop is 0
    # while the app holds the microphone open.
    MIC_CONSENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
    NON_PACKAGED = "NonPackaged"
    TEAMS_PACKAGE_PREFIX = "MSTeams_"
    LAST_USED_START = "LastUsedTimeStart"
    LAST_USED_STOP = "LastUsedTimeStop"
    PATH_SEPARATOR = "#"             # NonPackaged keys are the exe path with "\" replaced by "#"
    CREATE_NO_WINDOW = 0x08000000
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    TH32CS_SNAPPROCESS = 0x2
    STOP_POLL_SECONDS = 0.2
    # MessageBoxTimeoutW: Yes/No, question icon, always on top, takes the foreground.
    MB_FLAGS = 0x4 | 0x20 | 0x40000 | 0x10000
    IDYES, IDNO, MB_TIMEDOUT = 6, 7, 32000
    # Toasts are shown under Windows PowerShell's app id, which every Windows has registered.
    TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
    TOAST_SCRIPT = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$n = $t.GetElementsByTagName('text'); "
        "$n.Item(0).AppendChild($t.CreateTextNode('{title}')) > $null; "
        "$n.Item(1).AppendChild($t.CreateTextNode('{body}')) > $null; "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show([Windows.UI.Notifications.ToastNotification]::new($t))"
    )
    POWERSHELL_ARGS = ("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command")
    TASK_FOLDER = APP_NAME           # Task Scheduler folder: \teams-recorder\daemon and \teams-recorder\planner
    TASK_DAEMON, TASK_PLANNER = "daemon", "planner"
    TASK_STATE_SCRIPT = "(Get-ScheduledTask -TaskPath '\\{folder}\\' -TaskName '{name}' -ErrorAction Stop).State"
    TASK_RUNNING, TASK_DISABLED = "Running", "Disabled"
    TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    TASK_START_DATE = "2026-01-01T{hour:02d}:00:00"
    TASK_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    TASK_RESTART_INTERVAL = "PT1M"
    TASK_RESTART_COUNT = 999


# --- keep-recording question ------------------------------------------------------
class Confirm:
    ENABLED = True
    TIMEOUT_SECONDS = 30   # without an answer the recording is kept
    WAIT_MARGIN = 10.0     # extra seconds beyond the dialog timeout before giving up on it


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
