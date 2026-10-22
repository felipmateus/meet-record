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


class StoryDestination(StrEnum):
    BACKLOG_MD = "backlog-md"  # a local Backlog.md project (Markdown kanban); see [stories.backlog_md]


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
    TEAMS_SPEAKERS = "teams-speakers"   # the Accessibility reader of the Teams window (native/teams-speakers)
    POWERSHELL = "powershell"     # Windows PowerShell 5.1, present on every Windows 10/11
    SCHTASKS = "schtasks"
    DOTNET = "dotnet"
    BACKLOG = "backlog"           # Backlog.md CLI (npm i -g backlog.md / brew install backlog-md)
    GIT = "git"
    OPEN = "open"                 # macOS: opens a file with its default application


# --- files and folders -------------------------------------------------------
class Files:
    LOCAL_DATA_DIR = "data"          # data dir inside the project, used only outside iCloud/TCC folders
    CONFIG = "config.toml"
    DOTENV = ".env"
    PROMPTS_DIR = "prompts"
    ANALYZE_PROMPT = "analyze_system.md"
    STORIES_PROMPT = "stories_system.md"
    VERIFY_PROMPT = "verify_system.md"
    CURATE_PROMPT = "curate_system.md"
    STORY_GUIDE = "user_story_guide.md"  # default guide, in the prompts dir; [stories] guide overrides it
    RECORDINGS_DIR = "recordings"
    PLANS_DIR = "plans"
    TMP_SUFFIX = ".tmp"               # atomic writes: <name>.tmp then os.replace
    MODELS_DIR = "models"
    LOG_DIR = "log"
    DEBUG_DIR = "debug"              # raw tracks kept on mixing anomalies
    ACTIVE_RECORDING = "current_recording.json"
    DAEMON_LOG = "teams-recorder.log"
    CAPTURE_LOG = "capture.log"
    LLM_USAGE_LOG = "llm_usage.jsonl"
    NATIVE_BINARY = Path("native") / "teams-tap" / ".build" / "release" / "teams-tap"
    SPEAKERS_BINARY = Path("native") / "teams-speakers" / ".build" / "release" / "teams-speakers"
    SPEAKERS_LOG = "speakers.log"                     # in the log dir: the helper's stderr
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
    AGENT_OUT_LOG = "{name}.out.log"                   # name: last label segment (daemon / speakers)
    AGENT_ERR_LOG = "{name}.err.log"
    STORIES_MARKDOWN = "{day}.stories.md"              # user story drafts of that day
    STORIES_JSON = "{day}.stories.json"
    STORIES_GLOB = "????-??-??.stories.json"         # every saved set of story drafts
    NOTICES_DIR = "notices"                          # in the data dir: one file per once-a-day notice, holding the day it last fired
    ACTIVITIES_DIR = "activities"                    # in the data dir: the curated document, its archive and the curator's own state
    ACTIVITIES_DOC = "atividades.md"
    ARCHIVE_DIR = "arquivo"                          # in the activities dir: append-only, one file per month
    ARCHIVE_MONTH = "{month}.md"                     # month: YYYY-MM
    CURATOR_DIR = ".curator"                         # in the activities dir: lock, base.md and the versions
    CURATOR_LOCK = "lock"                            # flock target, always empty
    CURATOR_BASE = "base.md"                         # the document as the last pass left it
    VERSIONS_DIR = "versions"                        # in the curator dir
    VERSION_FILE = "{version}_{part}"                # part: a VersionPart value
    ACTIVITIES_LOG = "activities.jsonl"              # in the log dir: one PassRecord per line, the commit point of a pass


class VersionPart(StrEnum):
    """The files a pass leaves in `.curator/versions/` (named `<version>_<part>`)."""

    BEFORE = "before.md"      # the document the pass read
    AFTER = "after.md"        # the document the pass wrote
    BASE = "base.md"          # base.md after the pass; absent when the pass left none
    PREVBASE = "prevbase.md"  # base.md as the pass found it; absent when there was none
    PASS = "pass.json"        # the PassRecord, with the archive sizes


def raw_bytes_per_hour(bit_depth: int) -> int:
    """Disk used per hour by both raw tracks before mixing (1.04 GB at 16-bit, 2.07 GB at 32-bit)."""
    return Audio.SAMPLE_RATE * Audio.RAW_CHANNELS * (bit_depth // 8) * 3600


def ggml_model_file(name: str) -> str:
    return f"ggml-{name}.bin"


# --- launchd ---------------------------------------------------------------------
class Launchd:
    DAEMON_LABEL = f"local.{APP_NAME}.daemon"
    SPEAKERS_LABEL = f"local.{APP_NAME}.speakers"              # the helper, one job per recording (at most one at a time)
    SPEAKERS_CHECK_LABEL = f"local.{APP_NAME}.speakers-check"  # its short-lived `--check` job, run by the doctor
    PATH = ":".join(["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin"), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    THROTTLE_SECONDS = 10
    BOOTSTRAP_RETRIES = 10
    BOOTSTRAP_RETRY_DELAY = 1.0
    BOOTOUT_TIMEOUT = 15.0
    BOOTOUT_POLL_SECONDS = 0.5
    DOMAIN = "gui/{uid}"            # launchctl target domain for the logged-in user
    TIMEOUT_EXIT = 124              # the exit code a launchctl call that timed out is reported with (the `timeout(1)` convention)
    DAEMON_ARGS = ("daemon",)       # `trec` arguments run by each agent


# --- LLM -------------------------------------------------------------------------
class Llm:
    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    DEFAULT_API_MODEL = "claude-opus-5-5"
    DEFAULT_CLI_MODEL = "opus"
    DEFAULT_MAX_TOKENS = 16000
    MIN_WORDS = 20                  # below this an LLM call is not worth it
    OWNER_SELF = "usuário"          # data contract with the prompts: the recording owner
    OWNER_UNKNOWN = "indefinido"    # data contract with the prompts: unknown owner
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
    RETENTION_DAYS = 30             # delete audio.m4a of transcribed meetings older than this ([audio] retention_days)
    DEFAULT_LANGUAGE = "pt"
    DEFAULT_WHISPER_MODEL = "large-v3-turbo-q5_0"
    DEFAULT_WHISPER_THREADS = 0     # 0 = let whisper-cli decide
    DEFAULT_VAD_MODEL = "silero-v5.1.2"
    VAD_ARGS = ["-vt", "0.5", "-vsd", "300", "-vp", "150"]
    MIN_LANGUAGE_CLIP_SECONDS = 1.0  # a language sample holding less audio than this (an offset past a truncated end) is not sent to whisper
    MIX_TIMEOUT_FACTOR = 2.0        # mixing may take up to 2x the meeting length (never less than Proc.FFMPEG_TIMEOUT)
    PARTIAL_INFIX = ".partial"      # mixing writes audio.partial.m4a and renames it only on success
    BIT_DEPTHS = (16, 32)           # raw WAV sample format: 16-bit integer or 32-bit float
    DEFAULT_BIT_DEPTH = 16          # enough for speech and transcription; 32 doubles the size
    RAW_CHANNELS = 3                # Teams track (stereo) + microphone (mono)
    WAV_CODECS = {16: "pcm_s16le", 32: "pcm_f32le"}   # ffmpeg microphone backend
    LOW_DISK_HOURS = 2.0            # warn at recording start when less than this much recording fits
    CRITICAL_DISK_BYTES = 1_000_000_000  # warn once during a call below this
    # Rate-mismatch check on teams-tap's counters (domain/health.rate_mismatch): healthy Teams tracks pad under
    # 3% of their length in short pads; a 16 kHz device written as 48 kHz pads 67%, a 44.1 kHz one 8%.
    MAX_SHORT_PAD_SHARE = 0.05
    RATE_CHECK_MIN_SECONDS = 60.0


class VerdictSupport(StrEnum):
    """How far the transcript supports a claim (the claim verifier's answer; only `supported` confirms it)."""

    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"


class Verify:
    """Claim verification (docs/tasks/prd-fidelity-guard, tasks 3.0 and 7.0). The patterns are data about meetings held in
    Brazilian Portuguese (SENSITIVE) or in Portuguese and English (ADDRESS), matched against normalized text (lower
    case, no accents); taken from the prototype in scripts/fidelity_eval.py (SENSITIVE, the participant check),
    measured in evaluation §14.3."""

    ENABLED = True                   # [verification] enabled: one extra call per analyzed meeting (PRD decision 11)
    DEFAULT_API_MODEL = "claude-sonnet-5-5"   # [verification] model, with provider = "api"
    DEFAULT_CLI_MODEL = "sonnet"     # [verification] cli_model, with provider = "claude-code"
    DEFAULT_EFFORT = Effort.MEDIUM   # Sonnet at medium effort caught every injected error in the evaluation (PRD decision 1)
    WINDOW_SECONDS = 60              # a long transcript is cut to the lines within this of each claim's timestamp...
    MAX_TRANSCRIPT_CHARS = 200_000   # ...when longer than this (about 4 h of speech); below it the model reads it whole
    SENSITIVE = (
        r"cardiolog", r"coracao", r"consulta medica", r"\bmedic[oa]s?\b", r"exames? (de rotina|do coracao|de sangue|medicos?)",
        r"doenc", r"\bdoente\b", r"atestado", r"problemas? de saude", r"gravid", r"terapia", r"psicolog", r"religi", r"igreja",
        r"orientacao sexual", r"\bgay\b", r"partido politico", r"sindicat",
    )
    NAME_PARTICLES = ("da", "de", "do", "das", "dos", "dr", "dra", "e")   # not names: "Paula de Souza"
    ADDRESS = (   # someone addressed by name; {name} is a normalized, escaped name token
        r"\b(bom dia|boa tarde|boa noite|obrigad[oa]|oi|ola|hi|hello|hey|thanks|thank you),? (o |a )?{name}\b",
        r"\b{name},",
    )


class Transcription:
    """Defaults of [transcription] that guard against whisper hallucination loops (docs/tasks/prd-fidelity-guard)."""

    # whisper -mc: text tokens of the previous window kept as context. 0 = none, so a hallucinated line
    # cannot carry over into the next window: on a real 86-minute meeting it removed a loop that covered
    # 70% of the lines, and it left Portuguese accuracy unchanged (evaluation §14.7). -1 = whisper's default.
    MAX_CONTEXT = 0
    ANTI_LOOP_MAX_CONTEXT = 0       # the retry of a degraded transcript always runs without text context
    MAX_LOOP_SHARE = 0.10           # above this share of segments in loops the transcript is degraded
    RETRY_ON_LOOP = True            # transcribe a degraded transcript once more with the anti-loop settings
    RETRY_VAD = True                # with Silero VAD on that retry (skips silence, where whisper hallucinates)
    RANGES_IN_NOTIFICATION = 3      # time ranges without text listed in a notification or a CLI line
    AUTO = "auto"                   # [transcription] language: detect each meeting's language (docs/tasks/language-detection)
    LANGUAGES = ("pt", "en")        # [transcription] languages: the languages detection may choose, the fallback first
    LANGUAGE_CODE = r"^[a-z]{2,3}$"  # what a fixed language, or an entry of `languages`, must look like


# --- output formats of external tools (parsing) -------------------------------------
class Parse:
    FFMPEG_DURATION = r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)"
    FFMPEG_MEAN_VOLUME = r"mean_volume: (-?[\d.]+) dB"
    FFMPEG_MAX_VOLUME = r"max_volume: (-?[\d.]+) dB"
    LAUNCHCTL_PID = "pid = "
    LAUNCHCTL_STATE = "state = "
    LAUNCHCTL_LAST_EXIT = "last exit code = "    # "(never exited)" while the job has not exited
    LAUNCHCTL_RUNNING = "running"                # the `state` of a job whose process is alive
    ENERGY_TIME = r"pts_time:(\d+(?:\.\d+)?)"     # ametadata prints integers without decimals (pts_time:1)
    ENERGY_LEVEL = r"lavfi\.astats\.Overall\.RMS_level=(-?inf|-?\d+(?:\.\d+)?)"
    OSASCRIPT_NOTIFY = 'display notification "{body}" with title "{title}" subtitle "{subtitle}"'
    OSASCRIPT_CONFIRM = (
        'display dialog "{body}" with title "{title}" buttons {{"{discard}", "{keep}"}} '
        'default button "{keep}" giving up after {timeout} with icon note'
    )
    STORY_NUMBER = r"\s*[0-9]+\s*"              # one `--only` item (ASCII digits only)
    TIMESTAMP = r"\[?\s*(\d{2}:\d{2}:\d{2})\s*\]?"   # a criterion's cited source, with or without brackets
    CLOCK = r"\d{2}:\d{2}:\d{2}"                           # a stored criterion source
    BACKLOG_TASK_ID = r"^Task (\S+) - "            # `backlog task create --plain`: "Task TASK-7 - <title>"
    BACKLOG_STATUS = r"^statuses:.*[\[,]\s*[\"']?{status}[\"']?\s*[,\]]"   # status: re.escape'd column name
    BACKLOG_UNSAFE = (r"^auto_commit:\s*true", r"^remote_operations:\s*true")
    DIALOG_BUTTON = "button returned:"   # osascript output: "button returned:Keep, gave up:false"
    DIALOG_GAVE_UP = "gave up:true"
    WHISPER_PROCESSING = r"processing '(?:.*[\\/])?(c\d+\.wav)' \("    # whisper-cli -dl opens a file: `main: processing '<path>' (`; group 1 is its basename
    WHISPER_LANGUAGE = r"auto-detected language: ([a-z]+) \(p = ([0-9.]+)\)"   # and answers it: `auto-detected language: en (p = 0.99)`
    ACTIVITY_OPEN = r"^\s*[-*+] \[ \] "            # an open checkbox line of the activities document
    ACTIVITY_TICKED = r"^\s*[-*+] \[[xX]\] "       # a ticked one
    ACTIVITY_LABEL = r"\]\[([^\]\s]+)\]"            # the label of a reference link: `[text][label]`
    ACTIVITY_ITEM_PREFIX = r"^\s*[-*+]\s+(?:\[[ xX]\]\s+)?"   # the list marker and checkbox that open an item line
    ACTIVITY_TITLE_END = r" [—·] "                    # what follows an item's title on its line: ` — p/ Carla`, ` · sex 16/10`
    ACTIVITY_LINK = r"\[([^\]]*)\]\[[^\]\s]+\]"        # a reference link `[text][label]`; group 1 is its text


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
    TASK_FOLDER = APP_NAME           # Task Scheduler folder: \teams-recorder\daemon
    TASK_DAEMON = "daemon"
    TASK_STATE_SCRIPT = "(Get-ScheduledTask -TaskPath '\\{folder}\\' -TaskName '{name}' -ErrorAction Stop).State"
    TASK_RUNNING, TASK_DISABLED = "Running", "Disabled"
    TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
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
    LANGUAGE_DETECT_TIMEOUT = 300.0  # cutting the language samples and one whisper-cli -dl call over all of them
    IO_RETRIES = 12                 # file reads/writes blocked transiently by TCC
    IO_RETRY_DELAY = 0.5
    SPAWN_RETRIES = 12
    SPAWN_RETRY_DELAY = 0.5
    STOP_TIMEOUT = 10.0
    STOP_POLL = 0.1                 # seconds between the checks that a stopped process is gone
    WARMUP_TIMEOUT = 15.0
    NOTIFY_TIMEOUT = 5.0
    WORKER_JOIN_TIMEOUT = 30.0      # daemon waits this long for post-processing threads on shutdown


# --- logging ---------------------------------------------------------------------
class Logging:
    FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ROTATE_WHEN = "midnight"
    BACKUP_COUNT = 30


class Legacy:
    """What an older version installed and this one removes. Used only to build the agent whose `uninstall()` removes it."""

    PLANNER_LABEL = f"local.{APP_NAME}.planner"   # macOS LaunchAgent that ran `trec plan --purge` at 18:00
    PLANNER_TASK = "planner"                      # Windows scheduled task of the same job (folder \\teams-recorder\\)


class BacklogMd:
    """The Backlog.md CLI and project layout (checked against Backlog.md 1.53.0, techspec §9)."""

    TASKS_DIR = "backlog"
    ROOT_CONFIG = "backlog.config.yml"     # a config at the project root; the tasks still live in ./backlog
    CONFIG_FILES = (Path(TASKS_DIR) / "config.yml", Path(".backlog") / "config.yml", Path(ROOT_CONFIG))
    CREATE = ("task", "create")
    DESC, STATUS, LABEL, PRIORITY, AC, PLAIN = "--desc", "-s", "-l", "--priority", "--ac", "--plain"
    END_OF_OPTIONS = "--"                  # the title goes after it, so a title starting with "-" is not a flag
    LABEL_SEPARATOR = ","                  # the CLI splits -l values at commas
    SHIM_SUFFIXES = (".cmd", ".bat")       # Windows shims run under cmd.exe, which cuts multi-line arguments
    GIT_MARKER = ".git"                    # a folder (or file, in worktrees) that marks a Git work tree
    GIT_DIR = "-C"
    GIT_CHECK_IGNORE = ("check-ignore", "-q")
    GIT_IGNORED, GIT_NOT_IGNORED = 0, 1    # `git check-ignore -q` exit codes; anything else is an error
    TIMEOUT = 60.0
    TAIL_LINES = 3


class Speakers:
    """Speaker attribution from the Teams window (docs/tasks/speaker-attribution)."""

    NOTICE_KEY = "speaker-labels"   # the once-a-day "no labels" notification, under Files.NOTICES_DIR
    EVENTS_VERSION = 1              # version of the speakers.jsonl format the helper writes
    ENABLED = True                  # [speakers] enabled
    INTERVAL = 0.5                  # seconds between the helper's passes over the Teams windows (--interval)
    ENERGY_STEP = 0.1               # seconds per level of an energy timeline (asetnsamples n=1600 at 16 kHz)
    ENERGY_FILTER = ("aresample=16000,asetnsamples=n=1600,astats=metadata=1:reset=1,"
                     "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-")
    STARTUP_GRACE = 1.5             # seconds the helper's job is watched after bootstrap; an exit inside it fails the start
    STARTUP_POLL = 0.1              # seconds between the `launchctl print` reads of that watch
    CHECK_TIMEOUT = 10.0            # seconds the `--check` job gets to exit
    CHECK_POLL = 0.1
    STOP_TIMEOUT = 10.0             # seconds the helper gets to leave after its job was booted out
    EXIT_PERMISSION = 3             # the helper's exit code when the Accessibility permission is missing
    EXIT_GRANTED = 0
    TAIL_LINES = 3                  # lines of the helper's log quoted in a start failure
    WINDOW_LOST = "lost"            # `window` event states that close the window's open turns (the helper writes `found` too)
    WINDOW_FROZEN = "frozen"
    HEARTBEAT_EVENT = "heartbeat"   # the helper's proof of life, every 5 s
    MAX_LEVEL_DB = 100.0            # a level above this is a damaged energy.json (real RMS levels never exceed a few dB over 0)
    LAUNCHCTL_PRINT_TIMEOUT = 5.0   # seconds a `launchctl print` may take: the daemon asks on every tick, so it must stay short
    LAUNCHCTL_TIMEOUT = 20.0        # seconds the other launchctl calls get (bootout waits for the helper to leave)


class Activities:
    ENABLED = True                       # [activities] enabled: the daemon's worker and the curation step of `trec analyze`
    DEFAULT_CLI_MODEL = "opus"           # [activities] cli_model, with provider = "claude-code" ([activities] model defaults to the analyzer's)
    DEFAULT_EFFORT = Effort.MEDIUM       # [activities] effort
    NOTIFY = True                        # [activities] notify
    WORKER_DRAIN = 3                     # ids the daemon's worker takes from its queue after the one it woke up for (one batch in all)
    SKELETON_STAMP = "00000000-000000"   # the stamp in the closing marker of the skeleton's box; no pass version equals it
    KEEP_VERSIONS = 50                   # passes whose version files are kept for undo
    ARCHIVE_LINK_UP = "../"              # the archive sits one folder below the document: its link targets go one level further up
    ARCHIVE_ENTRY_LIMIT = 60             # recent archive entries shown to the curator
    COMMIT_ATTEMPTS = 3                  # tries of base.md and the pass-log line once the document has been replaced
    LOCK_POLL = 0.1                      # seconds between tries of the Windows lock
    DATE_FORMAT = "%d/%m/%Y"             # date in an archive entry's heading
    MONTH_FORMAT = "%Y-%m"               # archive file name
    VERSION_FORMAT = "%Y%m%d-%H%M%S"     # a pass's version: its version files' name and the stamp in the box's closing marker
    BATCH_SIZE = 4                       # meetings curated by one pass (oldest first)
    MAX_ATTEMPTS = 2                     # failed passes a meeting curated alone may cost before the daemon stops retrying it
    RETRY_WORKING_DAYS = 2               # `pending()` looks this many working days back (today is day 0)
    LISTING_WORKING_DAYS = 10            # `not_curated()` (the `trec activities` listing) looks this many working days back
    EXCERPT_WINDOW = 60                  # seconds of transcript kept before and after each status update
    TARGET_CHARS = 60                    # characters of an edit's target quoted in a failure message
    EST_SECONDS_PER_PASS = 160           # the bootstrap's time estimate per pass (`trec activities curate --since`)
    ESTIMATE_STEP_MINUTES = 5            # the estimate is rounded up to a multiple of this


class Curator:
    """The curator's call: tags of its user message and the letters of its refs (the data contract with
    prompts/curate_system.md), the usage tags, and the formats of the dates it is shown."""

    DOCUMENT = "document"
    MEETING = "meeting"
    EXCERPTS = "excerpts"
    EXCERPT = "excerpt"
    CALENDAR = "calendar"
    USER_EDITS = "user_edits"
    BOX_LINES = "box_lines"
    LAST_PASS = "last_pass"
    RECENT_ARCHIVE = "recent_archive"
    TASK = "task"
    FAILED_EDITS = "failed_edits"
    REF_MY_ACTION = "a"       # refs are `<meeting n>.<letter><i>`: 1.a1, 1.o2, ...
    REF_OTHERS_ACTION = "o"
    REF_STATUS = "u"
    REF_DEADLINE = "p"
    REF_NEXT_MEETING = "n"
    REF_DECISION = "d"
    REF_QUESTION = "q"
    REF_RISK = "r"
    TAG = "curate"            # llm_usage.jsonl tag: curate:<first meeting id>
    REPAIR_TAG = "curate-repair"
    DATE_FORMAT = "%d/%m/%Y"
    TIME_FORMAT = "%H:%M"
    HEALTH_SEPARATOR = ", "


class Stories:
    DEDUP_DAYS = 30   # stories of this many previous days are shown to the writer to avoid duplicates
    PUBLISH = False   # without [stories] publish = true, drafts are published only with `trec publish`
    BLOCK_REF = "b{n}"                    # the ref a tagged block has in one call to the writer, numbered from 1
    DRAFTS_LINK = "../{folder}/{name}"    # from the activities document to a drafts document (the tag's replacement)
    LINK_DATE_FORMAT = "%d/%m"
    BACKLOG_STATUS = "Triagem"            # Backlog.md column where new stories wait for review
    BACKLOG_LABELS = ("teams-recorder",)
    # Analysis fields sent as context with the candidate actions (the user's own actions go separately).
    CONTEXT_FIELDS = ("meeting_id", "title", "purpose", "meeting_type", "participants", "summary", "topics",
                      "decisions", "my_actions", "others_actions", "deadlines", "open_questions", "risks")
    # Story fields the writer sees for each recent story, to recognise an action it already covers.
    EXISTING_FIELDS = ("id", "title", "narrative")
