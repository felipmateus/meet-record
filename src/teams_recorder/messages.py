"""Every user-facing string in one place: CLI output and help, notifications, errors, logs.

Templates use `str.format` placeholders; call `.format(...)` at the use site. Log templates
(`Log`) keep printf-style `%s` because the logging module formats them lazily.
Changing a wording here changes it everywhere; tests assert on these same constants.
"""
from __future__ import annotations

# Reason texts shared by the daily notice (`Notify`) and the CLI lines (`Cli`): the two coincide for these.
_SPEAKERS_NO_WINDOW = "no Teams meeting window was read during the call"
_SPEAKERS_OBSERVER_DIED = "the observer died before reading a Teams window"


class Notify:
    RECORDING_STARTED = "Recording started"
    RECORDING_STARTED_BODY = "Meeting {meeting_id}"
    RECORDING_STOPPED = "Recording stopped"
    RECORDING_STOPPED_BODY = "{minutes} min. Transcribing…"
    LOW_DISK = "Low disk space"
    LOW_DISK_BODY = "{free:.1f} GB free: about {hours:.1f} h of recording"
    DISK_CRITICAL = "Disk almost full"
    DISK_CRITICAL_BODY = "{free:.1f} GB free; the recording may stop. Free up space now."
    RECORDING_CANCELLED = "Recording cancelled"
    RECORDING_CANCELLED_BODY = "Meeting {meeting_id} discarded"
    STEP_FAILED = "{step} failed"                       # step: "Transcription" / "Analysis"
    STEP_FAILED_BODY = "Meeting {meeting_id}: {error}"
    ACTIVITIES_UPDATED = "Activities updated"            # body: the curator's one-line summary
    ACTIVITIES_FAILED = "Activity curation failed"
    ACTIVITIES_FAILED_BODY = "{title} ({meeting_id}): {error}. It will be retried; or run trec activities curate {meeting_id}."
    STORIES_FAILED = "User story drafts failed"
    STORIES_FAILED_BODY = "Stories {day}: {error}"
    STORIES_PUBLISHED = "User stories published"
    STORIES_PUBLISHED_BODY = "{count} story(ies) sent to the board for review"
    PUBLISH_FAILED = "Publishing user stories failed"
    PUBLISH_ERROR_BODY = "Stories of {day}: {error}"
    PUBLISH_FAILED_BODY = "{failed} failure(s), {published} published; run `trec publish` again after fixing it"
    TRANSCRIPT_DEGRADED = "Degraded transcript"
    TRANSCRIPT_DEGRADED_BODY = "Meeting {meeting_id}: {loop:.0%} of the transcript is one line repeated by whisper{gaps}. The minutes may be incomplete."
    NO_TEXT_IN = "; no text in {ranges}"
    RANGES_MORE = "{shown} and {more} more"
    RATE_MISMATCH = "Teams audio recorded at the wrong rate"
    RATE_MISMATCH_BODY = ("Meeting {meeting_id}: {share:.0%} of the Teams track is silence padding, so the other participants' speech "
                          "is garbled and their part of the transcript is unreliable.")
    NO_SPEAKER_LABELS = "Speaker labels unavailable"
    NO_SPEAKER_LABELS_BODY = "Meeting {meeting_id}: {reason}"
    # The body per notifying reason (domain.SpeakerReason values); no-match and no-observer never notify.
    NO_SPEAKER_LABELS_REASON = {
        "binary-missing": "teams-speakers is not built. Run scripts/build-native.sh.",
        "permission-missing": "Accessibility permission missing for teams-speakers. Run trec doctor.",
        "start-failed": "the observer failed to start. See data/log/speakers.log.",
        "observer-died": f"{_SPEAKERS_OBSERVER_DIED}. See data/log/speakers.log.",
        "no-window": f"{_SPEAKERS_NO_WINDOW}. Keep a Teams window visible.",
    }


class Ask:
    """The question shown when a call starts (keep or discard the recording)."""

    TITLE = "Teams call detected"
    BODY = "The call is being recorded. Keep this recording?"
    KEEP = "Keep recording"
    DISCARD = "Discard"
    # Windows message boxes only offer Yes/No; the body explains them.
    BODY_WINDOWS = "The call is being recorded. Keep this recording?\n\nYes: keep it\nNo: discard it"


class Step:
    MIXING = "mixing"
    TRANSCRIPTION = "transcription"
    ANALYSIS = "analysis"


class Err:
    # recording
    RECORDING_IN_PROGRESS = "a recording is already in progress; use `trec stop` or `trec cancel`"
    TEAMS_CAPTURE_START = "failed to start the Teams capture: {error}"
    MIC_START = "failed to start the microphone: {error}"
    NO_AUDIO_FILE = "meeting {meeting_id} has no {filename}"
    BINARY_MISSING = "teams-tap binary not found at {path}. Build it with: {script}"
    EXEC_FAILED = "could not execute {command}: {error}"
    EXITED_EARLY = "{name} exited right after starting (code {code}). {tail}"
    NO_USABLE_TRACK = "no usable audio track to mix: {tracks}"
    MIX_FAILED = "ffmpeg failed to mix: {error}"
    MIX_FAILED_CODE = "ffmpeg failed to mix (code {code}): {tail}"
    # speaker observer and energy meter
    SPEAKERS_BINARY_MISSING = "teams-speakers binary not found at {path}. Build it with: {script}"
    SPEAKERS_PERMISSION_MISSING = "Accessibility permission missing for teams-speakers (exit code {code}). {tail}"
    SPEAKERS_START_FAILED = "teams-speakers did not start as launchd job {label}: {detail}"
    SPEAKERS_LAUNCHD = "launchctl {args} failed ({code}): {stderr}"   # the detail of a failed bootstrap
    SPEAKERS_EXITED = "it exited with code {code}. {tail}"
    SPEAKERS_NOT_RUNNING = "it was not running after {seconds:.1f} s"
    SPEAKERS_CHECK_HUNG = "it did not finish within {seconds:.0f} s"
    # What `problems()` returns for `trec doctor` (the doctor adds the "speaker labels:" prefix and the level).
    SPEAKERS_PROBLEM_NOT_BUILT = "teams-speakers not built → {script}"
    SPEAKERS_PROBLEM_PERMISSION = (
        "Accessibility permission missing → run `{binary} --check --prompt` and allow teams-speakers "
        "(add it with the + button: {binary}) under System Settings > Privacy & Security > Accessibility"
    )
    SPEAKERS_PROBLEM_CHECK = "the Accessibility permission could not be checked: {detail}"
    ENERGY_FAILED = "ffmpeg could not measure the level of {track}: {error}"
    ENERGY_FAILED_CODE = "ffmpeg could not measure the level of {track} (code {code}): {tail}"
    ENERGY_NO_LEVELS = "ffmpeg printed no levels for {track}"
    # transcription
    MODEL_MISSING = "model not found at {path}. Download it with {script}"
    AUDIO_MISSING = "audio not found: {path}"
    EXECUTABLE_MISSING = "{what}: executable not found ({command}). Install with: brew install whisper-cpp"
    TIMED_OUT = "{what}: timed out after {seconds:.0f}s"
    STEP_FAILED_CODE = "{what} failed (code {code}): {tail}"
    WHISPER_NO_JSON = "whisper-cli finished without producing the JSON output"
    WHISPER_BAD_JSON = "invalid whisper JSON: {error}"
    STEP_CONVERT_WAV = "conversion to 16 kHz WAV"
    # LLM
    SCHEMA_MISMATCH = "output does not match the schema: {errors}"
    API_KEY_INVALID = "invalid or missing API key (ANTHROPIC_API_KEY in .env)"
    RATE_LIMIT = "rate limit reached; try again shortly ({message})"
    API_ERROR = "API error ({status}): {message}"
    NO_CONNECTION = "no connection to the API: {error}"
    REFUSED = "the API refused the request ({tag}){why}"
    REFUSED_WHY = " ({category}: {explanation})"
    TRUNCATED = "response truncated at {max_tokens} tokens; increase llm.max_tokens"
    NO_TEXT_BLOCK = "response has no text block"
    CLAUDE_CODE_MISSING_HINT = "Claude Code not found ({binary}); install it or set llm.provider = \"api\""
    CLAUDE_CODE_MISSING = "Claude Code not found ({binary})"
    CLAUDE_CODE_TIMEOUT = "Claude Code did not respond within {seconds:.0f}s"
    CLAUDE_CODE_FAILED = "Claude Code failed (code {code}): {tail}"
    CLAUDE_CODE_NOT_JSON = "Claude Code response is not JSON: {text!r}"
    CLAUDE_CODE_BAD_FORMAT = "Claude Code response has an unexpected format"
    CLAUDE_CODE_ERROR = "Claude Code returned an error ({subtype}): {result}"
    CLAUDE_CODE_NO_STRUCTURED = "Claude Code did not return structured output"
    PROMPT_MISSING = "prompt not found: {path}"
    NO_SYSTEM_PROMPT = "{who} has no system prompt (system_prompt or prompt_path)"
    EMPTY_TRANSCRIPT = "Empty transcript: no speech recognized."
    SHORT_TRANSCRIPT = "Transcript too short ({words} words) to analyze: \"{text}\""
    STORY_GUIDE_MISSING = "user story guide not found: {path} (set [stories] guide in config.toml)"
    STORY_GUIDE_EMPTY = "user story guide is empty: {path}"
    BACKLOG_BINARY_MISSING = "Backlog.md CLI ({binary}) not found; install it with `brew install backlog-md` or `npm i -g backlog.md`"
    BACKLOG_PROJECT_UNSET = "no Backlog.md project set; fill [stories.backlog_md] project_dir in config.toml"
    BACKLOG_PROJECT_MISSING = "Backlog.md project folder not found: {path}; fix [stories.backlog_md] project_dir in config.toml"
    BACKLOG_NOT_INITIALIZED = "{path} is not a Backlog.md project; run there: backlog init \"teams-recorder\" --no-git --defaults --integration-mode none"
    BACKLOG_STATUS_MISSING = "{status!r} is not a column of the board; add it to `statuses` in {config}"
    BACKLOG_GIT_ON = "{config} lets Backlog.md commit or reach remotes; set auto_commit and remote_operations to false"
    BACKLOG_NOT_IGNORED = "{path} would be versioned by Git; add it to .gitignore (stories carry meeting content)"
    BACKLOG_IGNORE_UNKNOWN = "could not confirm with git that {path} is git-ignored; publishing stays off until `git check-ignore {path}` works"
    BACKLOG_SHIM = "{binary} is a Windows command shim, which can cut multi-line text and drop options; point to the backlog executable itself"
    BACKLOG_LABEL_SEPARATOR = "label {label!r} contains a comma, which Backlog.md would split; fix [stories.backlog_md] labels"
    BACKLOG_FAILED = "Backlog.md failed (code {code}): {tail}"
    BACKLOG_TIMEOUT = "Backlog.md did not answer within {seconds:.0f}s"
    BACKLOG_EXEC = "could not run Backlog.md ({binary}): {error}"
    BACKLOG_NO_ID = "Backlog.md did not report the new task id: {tail}"
    STORIES_MISSING = "no story drafts for {day}; tag items #história in the activities document and run `trec stories`"
    NO_ACTIVITIES_DOCUMENT = "No activities document yet: {path}"
    INVALID_STORY_NUMBER = "there is no story {number} in the drafts of {day} (they have {count})"
    # repository
    FILE_MISSING = "file not found: {path}"
    CURATION_FAILED = "Activity curation failed: {reason}"   # content of curation_error.txt
    CURATION_NO_MATCH = "{count} edits did not match the document ({target}…)"   # reason inside CURATION_FAILED
    CURATION_BREAKS_RULE = "an edit would change a checkbox without archiving: {target}"   # reason inside CURATION_FAILED
    CURATOR_BUSY = "the curator is working; try again in a few minutes"
    NOTHING_TO_UNDO = "No pass to undo."
    UNDO_STALE = "A new pass ran while you were deciding; run trec activities undo again."
    ACTIVITY_COMMIT_INCOMPLETE = ("the activities pass {version} replaced the document but could not finish ({step}: {error}); "
                                  "the next pass completes it")
    ACTIVITY_STORE_IO = "the activities files could not be read or written ({error}); check the free disk space and the folder's permissions"
    ACTIVITY_LOG_LINE = "line {line} of the pass log is not a pass record"   # detail inside BAD_JSON
    BAD_JSON = "invalid JSON in {path}: {error}"
    BAD_VERIFICATION = "a verification must be an object, not {value!r}"         # detail inside BAD_JSON
    BAD_REASON = "verification reason must be text, not {value!r}"               # detail inside BAD_JSON
    BAD_PARTICIPANT_CHECKS = "participant_checks must be an object, not {value!r}"  # detail inside BAD_JSON
    FILE_UNREADABLE = "cannot read {path}: {error}"
    BAD_SPEAKERS = "the speakers summary must be an object, not {value!r}"   # detail inside BAD_JSON
    BAD_TEXT = "expected text or null, not {value!r}"                       # detail inside BAD_JSON
    BAD_ENERGY = "energy levels must be a list of numbers per track (track {value!r})"   # detail inside BAD_JSON
    BAD_ENERGY_STEP = "the energy step must be a positive number of seconds, not {value!r}"   # detail inside BAD_JSON
    BAD_ENERGY_LEVEL = "energy levels must be finite dBFS values of at most {limit:g}, not {value!r} (track {track!r})"   # detail inside BAD_JSON
    BAD_CRITERION = "a criterion needs text and a source of HH:MM:SS or suggestion, not {value!r}"  # detail inside BAD_JSON
    MEETING_EXISTS = "meeting already exists: {meeting_id}"
    MEETING_LOCKED = "meeting {meeting_id} is already being processed"
    STEP_ERROR = "{step}: {error}"                      # content of error.txt
    # launchd / config / daemon
    LAUNCHCTL_FAILED = "launchctl {args} failed ({code}): {stderr}"
    LAUNCHCTL_TIMED_OUT = "launchctl {args} did not answer within {seconds:g} s"   # stderr of a call reported as failed
    SCHTASKS_FAILED = "schtasks {args} failed ({code}): {stderr}"
    INVALID_PROVIDER = "invalid llm.provider: {value!r}; use one of {options}"
    INVALID_BIT_DEPTH = "invalid audio.bit_depth: {value!r} (use one of {options})"
    INVALID_MIC_BACKEND = "invalid audio.mic_backend: {value!r}; use one of {options}"
    INVALID_EFFORT = "invalid llm.effort: {value!r}; use one of {options}"
    INVALID_VERIFY_EFFORT = "invalid verification.effort: {value!r}; use one of {options}"
    INVALID_ACTIVITIES_EFFORT = "invalid activities.effort: {value!r}; use one of {options}"
    INVALID_KEEP_VERSIONS = "invalid activities.keep_versions: {value!r}; use a whole number of at least 1"
    INVALID_DESTINATION = "invalid stories.destinations value: {value!r}; use one of {options}"
    INVALID_LOOP_SHARE = "invalid transcription.max_loop_share: {value!r}; use a fraction above 0 and up to 1 (e.g. 0.10)"
    NO_DETECTOR = "daemon without a configured detector"
    # pipeline: content of error.txt (step: "transcription" / "analysis")


class Cli:
    APP_HELP = "Records, transcribes and analyzes Microsoft Teams meetings."
    AGENT_HELP = "Installs, removes and inspects the LaunchAgent that keeps the daemon running."
    ERROR_PREFIX = "error: {message}"
    VERSION = "teams-recorder {version}"
    # command help (shown by --help)
    VERSION_CMD_HELP = "Show the version."
    STATUS_CMD_HELP = "List meetings, the status of each one, and the Activities line (open and waiting items, last pass)."
    DOCTOR_CMD_HELP = "Check external dependencies and permissions."
    START_CMD_HELP = "Start recording (Teams audio + microphone). Stop with `trec stop`."
    STOP_CMD_HELP = "Stop the recording in progress, mix the tracks and produce audio.m4a."
    TRANSCRIBE_CMD_HELP = "Transcribe the audio of a meeting (or of all pending ones) locally with whisper.cpp."
    CANCEL_CMD_HELP = "Discard the recording in progress without producing a file."
    ANALYZE_CMD_HELP = "Extract summary, decisions, actions and deadlines from the transcript with Claude, and write minutes.md."
    MINUTES_CMD_HELP = "Render minutes.md from an existing analysis (no LLM call). Without an argument: analyzed meetings that have no minutes yet."
    MINUTES_ARG_HELP = "Meeting ID. Without an argument: every analyzed meeting without minutes.md."
    MINUTES_ALL_HELP = "Re-render minutes for every analyzed meeting, even if minutes.md already exists."
    NO_PENDING_MINUTES = "No analyzed meeting without minutes."
    MINUTES_WRITTEN = "Minutes: {path}"
    DAEMON_CMD_HELP = "Watch Teams and record, transcribe and analyze meetings automatically. Used by the LaunchAgent."
    AGENT_INSTALL_CMD_HELP = "Register the daemon with launchd: starts at login and restarts if it dies."
    AGENT_UNINSTALL_CMD_HELP = "Stop the daemon and remove the LaunchAgent."
    AGENT_RESTART_CMD_HELP = "Restart the daemon (for example after changing config.toml)."
    AGENT_STATUS_CMD_HELP = "Show whether the daemon is loaded and running."
    STORIES_CMD_HELP = ("Draft a user story for each item of the activities document tagged #história, following the story guide "
                        "(stories.guide in config.toml), and replace the tag with a link to the draft; publish them when stories.publish is on.")
    PUBLISH_CMD_HELP = "Send a day's story drafts to the configured boards (stories.destinations). Stories already there are skipped."
    PURGE_CMD_HELP = "Delete audio of already transcribed meetings older than N days (config: audio.retention_days)."
    # status
    DATA_DIR = "Data dir: {path}"
    API_KEY = "API key: {state}"
    CONFIGURED, MISSING = "configured", "MISSING"
    MEETINGS = "Meetings: {count}"
    MEETING_LINE = "  {meeting_id}{title}  [{status}]{next}{health}"
    MEETING_DEGRADED = "  ⚠ degraded transcript ({loop:.0%} in repetition loops)"
    MEETING_UNREADABLE = "  {meeting_id}  [unreadable: {error}]"
    ACTIVE_UNREADABLE = "Recording in progress: unreadable ({error})"
    ACTIVITIES_STATUS_UNREADABLE = "Activities: unreadable ({error})"
    STORIES_WAITING_UNREADABLE = "Stories waiting to be published: unreadable ({error})"
    DEGRADED_TRANSCRIPTS = "Degraded transcripts: {count}"
    MEETING_RATE_MISMATCH = "  ⚠ Teams audio recorded at the wrong sample rate ({share:.0%} short padding)"
    RATE_MISMATCH_TRANSCRIPTS = "Teams tracks recorded at the wrong sample rate: {count}"
    MEETING_UNCONFIRMED = "  ⚠ {count} unconfirmed claim(s)"
    UNCONFIRMED_CLAIMS = "Unconfirmed claims: {claims} in {meetings} meeting(s)"
    MEETING_TITLE = " {title}"
    MEETING_SPEAKERS = "  · speakers {share:.0%}"
    MEETING_SPEAKERS_NONE = "  · speakers 0% ({reason})"
    NEXT_STEP = " → next: {step}"
    RECORDING_IN_PROGRESS = "Recording in progress: {meeting_id} (recorder PIDs {tap_pid}, {mic_pid})"
    ACTIVITIES_STATUS = "Activities: {counts}{last}"
    ACTIVITIES_STATUS_LAST = " (last pass {when})"
    ACTIVITIES_STATUS_NO_COUNTS = "document has no actions or waiting sections"
    ACTIVITIES_STATUS_NONE = "Activities: not created yet (trec activities curate --since YYYY-MM-DD)"
    # doctor
    DOCTOR_ACTIVITIES = "[{mark}] Activities document: {path} ({state})"
    DOCTOR_ACTIVITIES_OK = "ok, last pass {when}"
    DOCTOR_ACTIVITIES_OK_NO_PASS = "ok, no pass recorded"
    DOCTOR_ACTIVITIES_NONE = "not created yet (trec activities curate --since YYYY-MM-DD)"
    DOCTOR_ACTIVITIES_NOT_CURATED = "{count} meetings not curated (trec activities)"
    DOCTOR_ACTIVITIES_NOT_CURATED_ONE = "1 meeting not curated (trec activities)"
    DOCTOR_ACTIVITIES_UNREADABLE = "[{mark}] Activities document: unreadable ({error})"
    CHECK = "[{mark}] {name}: {value}"
    DISK_LINE = "[{mark}] free disk: {free:.1f} GB (about {hours:.1f} h of recording) in {path}"
    OK, MISSING_MARK, INFO, WARNING = "ok ", "MISSING", "info", "WARNING"
    NOT_FOUND = "not found"
    CLAUDE_CLI_LINE = "[{mark}] claude (Claude Code CLI): {value}  → current provider: {provider}"
    WHISPER_MODEL_LINE = "[{mark}] whisper model: {path}{hint}"
    WHISPER_MODEL_HINT = "  → {script}"
    VAD_MODEL_LINE = "[{mark}] VAD model: {path}{hint}"
    VAD_MODEL_HINT = "  → {script} {model} (without it transcription runs without VAD)"
    TRANSCRIPTION_LINE = "[{mark}] transcription: whisper -mc {max_context}; a transcript is degraded above {share:.0%} of its segments in repetition loops"
    RETRY_LINE = "[{mark}] retry of a degraded transcript: {state}{hint}"
    RETRY_ON_VAD = "on (-mc 0 with VAD: {path})"
    RETRY_ON = "on (-mc 0 without VAD)"
    RETRY_OFF = "off ([transcription] retry_on_loop = false)"
    RETRY_SAME = "off (it would only repeat the first pass)"
    RETRY_VAD_MISSING = "; VAD model missing at {path}  → {script} {model}"
    VERIFICATION_LINE = "[{mark}] claim verification: {state}"
    VERIFICATION_ON = "on, model {model} ({provider}), effort {effort}"
    VERIFICATION_OFF = "off ([verification] enabled = false): analyses are not checked against the transcript"
    VERIFICATION_NO_PROMPT = "{state}; prompt missing at {path}"
    API_KEY_LINE = "[{mark}] ANTHROPIC_API_KEY in .env{hint}"
    API_KEY_NOT_REQUIRED = " (not required with provider = claude-code)"
    SPEAKERS_LINE = "[{mark}] speaker labels: {state}"
    SPEAKERS_AT = "teams-speakers at {path}; {detail}"
    SPEAKERS_GRANTED = "Accessibility permission granted"
    SPEAKERS_LAST_RECORDING = "; last recording {meeting_id}: {outcome}"
    SPEAKERS_OBSERVER_RAN = "observer ran, {share:.0%} of lines labelled"
    SPEAKERS_OFF = "off ([speakers] enabled = false); only your own lines are labelled, from the microphone track"
    SPEAKERS_PROBLEMS_SEPARATOR = "; "
    SPEAKERS_MISMATCH = ("Accessibility permission granted to teams-speakers now, but the last recording {meeting_id} reported it missing "
                         "→ record again to confirm; if it still reports it missing, add teams-speakers again "
                         "(add it with the + button: {binary})")
    ENV_PERMISSIONS = "[WARNING] .env permissions {mode}; recommended: chmod 600 .env"
    DATA_IN = "[info] data in {path}"
    STORY_GUIDE_LINE = "[{mark}] user story guide: {path}{hint}"
    # start / stop / cancel
    START_PID_HELP = "PID of the process to capture. Default: the running Microsoft Teams."
    START_TITLE_HELP = "Meeting title, used in the name and in the status."
    TEAMS_NOT_RUNNING = "process {name} is not running; open Teams or pass --pid"
    RECORDING_MEETING = "Recording meeting {meeting_id} (target PID {pid})."
    TRACK_TEAMS = "  Teams:       {path}  (recorder PID {pid})"
    TRACK_MIC = "  Microphone:  {path}  (recorder PID {pid})"
    TRACK_SPEAKERS = "  Speakers:    {path}  (observer PID {pid})"
    TRACK_SPEAKERS_OFF = "  Speakers:    not running ({reason}; {pointer})"
    # The reason the observer did not start, for the line above (the transcribe table says more once there is a transcript).
    SPEAKERS_NOT_STARTED = {
        "binary-missing": "teams-speakers not built",
        "permission-missing": "Accessibility permission missing",
        "start-failed": "it failed to start",
    }
    SPEAKERS_SEE_DOCTOR, SPEAKERS_SEE_LOG = "see trec doctor", "see data/log/speakers.log"
    STOP_HINT = "Stop with `trec stop` or discard with `trec cancel`."
    NO_RECORDING = "no recording in progress"
    STOPPED = "Meeting {meeting_id} stopped after {minutes:.1f} min."
    AUDIO_PATH = "  Audio: {path}"
    TRANSCRIBE_HINT = "Transcribe with `trec transcribe {meeting_id}`."
    DISCARDED = "Recording {meeting_id} discarded."
    # transcribe / analyze
    TRANSCRIBE_ARG_HELP = "Meeting ID. Without an argument: all recorded meetings not yet transcribed."
    ANALYZE_ARG_HELP = "Meeting ID. Without an argument: all transcribed meetings not yet analyzed."
    MEETING_MISSING = "meeting {meeting_id} does not exist"
    NO_PENDING_TRANSCRIPTION = "No meeting pending transcription."
    NO_PENDING_ANALYSIS = "No meeting pending analysis."
    TRANSCRIBING = "Transcribing {meeting_id}…"
    ANALYZING = "Analyzing {meeting_id}…"
    FAILED = " FAILED: {error}"
    TRANSCRIBED_OK = " ok ({segments} segments, {minutes:.1f} min)"
    SPEAKERS_LABELLED = "  Speakers: {share:.0%} of {eligible} lines labelled ({names})"
    SPEAKERS_NO_LABELS = "  Speakers: no labels ({reason})"
    SPEAKER_NAMES_SEPARATOR = ", "
    # Why a transcript has no label (SpeakerReason values), as `trec transcribe` prints it and as `trec status` shows it.
    SPEAKERS_REASON = {
        "binary-missing": "the observer did not run: teams-speakers not built",
        "permission-missing": "the observer did not run: Accessibility permission missing",
        "start-failed": "the observer did not run: it failed to start; see data/log/speakers.log",
        "observer-died": f"{_SPEAKERS_OBSERVER_DIED}; see data/log/speakers.log",
        "no-window": _SPEAKERS_NO_WINDOW,
        "no-match": "speaker events found but no line matched them",
        "no-observer": "no observer data for this meeting",
    }
    TRANSCRIPT_HEALTH = "  Health: {loop:.0%} of segments in repetition loops, text in {covered} of {total} min{retried}"
    RETRIED = " (after a second pass with the anti-loop settings)"
    TRANSCRIPT_DEGRADED = "  WARNING: degraded transcript{gaps}. The analysis still runs on it and the minutes will say so."
    TRANSCRIPT_RATE_MISMATCH = ("  WARNING: the Teams track was recorded at the wrong sample rate ({share:.0%} of it is short silence padding): "
                                "the other participants' speech is sped up and chopped, and their part of the transcript is unreliable.")
    NO_TEXT_IN = "; no text in {ranges}"
    TEXT_PATH = "  Text: {path}"
    ANALYZE_HINT = "Analyze with `trec analyze`."
    API_KEY_MISSING = "ANTHROPIC_API_KEY missing from .env (or set llm.provider = \"claude-code\")"
    CLAUDE_CLI_MISSING = "Claude Code (`claude`) not found in PATH"
    PROVIDER = "Provider: {provider} ({model})"
    ANALYZED_OK = " ok ({decisions} decisions, {mine} actions of yours, {others} of others)"
    SUMMARY = "  Summary: {summary}"
    ACTION_LINE = "  • {description}{due}"
    ACTION_DUE = " by {due}"
    FILE_PATH = "  File: {path}"
    MINUTES_PATH = "  Minutes: {path}"
    TITLE_LINE = "  Title: {title}"
    # activities (the document the curator keeps) and the curation step of `trec analyze`
    ACTIVITIES_HELP = "The activities document: where it stands, rerun the curator for a meeting, bootstrap it from past meetings."
    ACTIVITIES_OPEN_HELP = "Also open the document with the default application."
    CURATE_CMD_HELP = "Rerun the activities curator for analyzed meetings, or build the document from the meetings since a date."
    CURATE_ARG_HELP = "Meeting IDs to curate (analyzed meetings)."
    CURATE_SINCE_HELP = "Curate every analyzed meeting held on or after this day (YYYY-MM-DD), a pass per day (up to 4 meetings)."
    CURATE_YES_HELP = "Do not ask for confirmation (with --since)."
    CURATE_NEEDS_TARGET = "give meeting IDs or --since YYYY-MM-DD"
    CURATE_ONE_TARGET = "give meeting IDs or --since, not both"
    CURATE_NOT_ANALYZED = "Meeting {meeting_id} is {state}, not analyzed: run trec analyze {meeting_id} first."
    CURATE_CONFIRM = "Curate {meetings} meetings in {passes} passes {via} (~{minutes} min)?"
    CURATE_VIA = {
        "claude-code": "using your Claude subscription",
        "api": "using the Anthropic API (spends API credit)",
    }
    CURATE_DECLINED = "Nothing curated."
    CURATE_NOTHING_SINCE = "No analyzed meeting since {since}."
    CURATE_WAITING = "waiting for the curator…"
    CURATING = "Curating {meetings}…"
    CURATING_MEETING = "{title} ({day:%d/%m})"
    CURATING_SEPARATOR = ", "
    CURATED_OK = " ok ({edits} edits)"
    CURATED_SUMMARY = " — {summary}"
    CURATION_FAILED = " failed: {reason}"
    CURATION_UNFINISHED = "The document was updated, but the pass could not be fully recorded: {reason}"
    CURATION_DEFERRED = "Deferred {meeting}: an earlier pass is unfinished; it will be curated at the next pass."
    ACTIVITIES_NO_DOCUMENT = "No activities document yet. Build it from past meetings: trec activities curate --since YYYY-MM-DD"
    ACTIVITIES_DOCUMENT = "Document: {path}"
    ACTIVITIES_UPDATED = "Updated {when}{after}"
    ACTIVITIES_AFTER = " after {titles}"
    ACTIVITIES_FOCUS = "Focus:"
    ACTIVITIES_FOCUS_LINE = "  {line}"
    ACTIVITIES_OPEN = "Open: {counts}"
    ACTIVITIES_COUNT_ACTIONS = "{count} yours"
    ACTIVITIES_COUNT_WAITING = "{count} waiting on others"
    ACTIVITIES_COUNT_AGENDA = "{count} agenda"
    ACTIVITIES_COUNT_CONTEXT = "{count} context"
    ACTIVITIES_COUNT_SEPARATOR = " · "
    ACTIVITIES_LAST_PASS = "Last pass: {when}{summary}"
    ACTIVITIES_NO_PASS = "Last pass: none recorded"
    ACTIVITIES_NOT_CURATED = "Not curated:"
    ACTIVITIES_NOT_CURATED_LINE = "  {meeting_id}{title}: {reason} → trec activities curate {meeting_id}"
    ACTIVITIES_NOT_CURATED_TITLE = " ({title})"
    ACTIVITIES_NOT_ATTEMPTED = "not attempted yet"
    ACTIVITIES_OPEN_FAILED = "could not open {path}: {error}"
    UNDO_CMD_HELP = "Restore the activities document to before the last pass (showing what changes first)."
    UNDO_YES_HELP = "Do not ask for confirmation."
    UNDO_LAST_PASS = "Last pass: {when}{after}{summary}"
    UNDO_SUMMARY = " ({summary})"
    UNDO_DIFF_NOW = "--- now"
    UNDO_DIFF_BEFORE = "+++ before the pass"
    UNDO_EDITED_AFTER = "This also discards {count} lines you edited after the pass."
    UNDO_EDITED_AFTER_ONE = "This also discards 1 line you edited after the pass."
    UNDO_CONFIRM = "Restore the document to before this pass?"
    UNDO_DECLINED = "Nothing restored."
    UNDO_RESTORED = "Restored. Run trec activities curate {meeting_ids} to curate {that} again."
    UNDO_THAT_ONE = "that meeting"
    UNDO_THOSE = "those meetings"
    UNDO_ARCHIVE_CHANGED = "The archive changed after this pass; its entries were left in place."
    UNDO_BUSY = "The curator is working; try again in a few minutes."
    STARTFILE = "startfile"   # the os function that opens a file on Windows
    WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    WHEN = "{weekday} {at:%d/%m %H:%M}"
    # daemon / agent
    DAEMON_ONCE_HELP = "Run a single detection iteration and exit (diagnostics)."
    DETECTOR_STATE = "detector ({name}): {state}; pid={pid}"
    DAEMON_WATCHING = "daemon watching {name}; log at {path}"
    AGENT_ENV_HELP = "Extra variable for the daemon, in KEY=VALUE format (e.g. TREC_LLM_PROVIDER=claude-code). Repeatable."
    AGENT_ENV_INVALID = "--env expects KEY=VALUE, got {item!r}"
    AGENT_INSTALLED = "LaunchAgent installed and started: {path}"
    PERMISSIONS_HINT = "On the first recording macOS will ask for Microphone and System Audio Recording permissions."
    PERMISSIONS_HINT_WINDOWS = "Allow microphone access for desktop apps: Settings > Privacy & security > Microphone."
    TASK_INSTALLED = "Scheduled task installed and started: {path}"
    AGENT_ENV_UNSUPPORTED = "--env is not supported on Windows; set the variables in config.toml or the user environment"
    AGENT_REMOVED, AGENT_NOT_INSTALLED = "LaunchAgent removed.", "No daemon LaunchAgent installed."
    LEGACY_PLANNER_REMOVED = "Removed the old daily planner job ({name})."
    LEGACY_PLANNER_REMOVE_FAILED = "warning: could not remove the old daily planner job ({name}): {error}. Continuing; remove it by hand if it is still there."
    DAEMON_RESTARTED = "daemon restarted."
    PLIST_LINE = "plist: {path} ({state})"
    TASK_LINE = "task definition: {path} ({state})"
    EXISTS, MISSING_FILE = "exists", "missing"
    LOADED_LINE = "loaded: {state}{details}"
    YES, NO = "yes", "no"
    LOADED_DETAILS = "  pid={pid}  state={state}"
    # dates
    INVALID_DATE = "invalid date: {value!r} (use YYYY-MM-DD)"
    DRAFTING_TAGGED = "Drafting {count} tagged items…"
    DRAFTING_TAGGED_ONE = "Drafting 1 tagged item…"
    STORIES_OK = " ok ({parts})"
    STORIES_PARTS_SEPARATOR = ", "
    STORIES_COUNT, STORIES_COUNT_ONE = "{count} stories", "1 story"
    TASK_CARDS_COUNT, TASK_CARDS_COUNT_ONE = "{count} task cards", "1 task card"
    STORIES_EXIST, STORIES_EXIST_ONE = "{count} already exist", "1 already exists"
    STORIES_SKIPPED_COUNT = "{count} skipped"
    STORY_LINE = "  {title}"
    STORIES_SKIPPED_LINE = "  Skipped: {line} — {reason}"
    STORIES_EXISTS_REASON = 'already exists ("{title}")'
    STORIES_PATH = "Drafts: {path}"
    STORIES_NOTHING_TAGGED = "Nothing tagged {tag} in {path}."
    STORIES_NO_DOCUMENT = "No activities document yet: {path}"
    STORIES_DEFERRED = "The curator is working; the drafts are saved. Run trec stories again later to replace the tags."
    STORIES_EDITED, STORIES_EDITED_ONE = "{count} tagged lines were edited meanwhile; their tags stay.", "1 tagged line was edited meanwhile; its tag stays."
    STORIES_REPLACED, STORIES_REPLACED_ONE = "Replaced {count} tags in {path}.", "Replaced 1 tag in {path}."
    PUBLISH_DATE_HELP = "Day whose story drafts are published (YYYY-MM-DD). Default: today."
    PUBLISH_ONLY_HELP = "Only these story numbers of the drafts document, comma-separated (e.g. 1,3)."
    INVALID_ONLY = "invalid --only value: {value!r} (use story numbers such as 1,3)"
    NO_DESTINATIONS = "no story destinations configured; set stories.destinations in config.toml"
    PUBLISHING = "Publishing the stories of {day}…"
    PUBLISHED_LINE = "  • {title} → {destination} {ref}"
    ALREADY_PUBLISHED = "  {count} already published (skipped)"
    PUBLISH_FAILURE_LINE = "  ✗ {title} → {destination}: {error}"
    NOTHING_TO_PUBLISH = "  nothing new to publish"
    STORIES_WAITING = "Stories waiting to be published: {count}"
    DESTINATION_LINE = "[{mark}] story destination {destination}: {state}"
    DESTINATION_READY, DESTINATION_NOT_READY = "ready", "not ready"
    DESTINATION_PROBLEM = "      {problem}"
    PURGED = "Audio files removed: {count}"
    PURGED_LINE = "  {meeting_id}"


class Log:
    DAEMON_STARTED = "daemon started (poll=%ss, start_after=%s, stop_after=%s)"
    WARMUP = "recorder warm-up: %s"
    WARMUP_OK, WARMUP_FAILED = "ok", "failed (continuing anyway)"
    CYCLE_ERROR = "error in daemon cycle"
    FINISHING_BEFORE_EXIT = "finishing recording in progress before exiting"
    DAEMON_STOPPED = "daemon stopped"
    CAPTURER_DIED = "capturer %s (pid %s) died during call %s; see %s"
    CAPTURER_TAP, CAPTURER_MIC, CAPTURER_SPEAKERS = "teams-tap", "microphone", "teams-speakers"   # names used in CAPTURER_DIED
    SPEAKERS_STARTED = "speaker observer started for %s (pid %s)"
    SPEAKERS_UNAVAILABLE = "speaker observer unavailable for %s: %s (%s)"
    SPEAKERS_UNAVAILABLE_NOT_RECORDED = "the reason the speaker observer was unavailable for %s could not be recorded: %s"
    SPEAKERS_STOP_FAILED = "speaker observer (pid %s) could not be stopped: %s"
    ENERGY_MEASURED = "energy of %s measured: %.1f s in %d windows"
    ENERGY_FAILED = "energy of %s could not be measured: %s; the user's lines will not be labelled"
    ENERGY_NOT_SAVED = "energy of %s could not be saved: %s; the user's lines will not be labelled"
    TITLE_FROM_WINDOW = "meeting %s titled from the Teams window: %s"
    TITLE_FROM_WINDOW_FAILED = "the Teams window subject of %s could not be read: %s; the meeting stays untitled"
    CALL_WITHOUT_PID = "call detected but no Teams PID; waiting"
    ALREADY_ACTIVE = "a recording is already active (manual?); daemon will not start another"
    RECORDING_STARTED = "recording started: %s (target pid %s)"
    START_FAILED = "failed to start recording"
    CALL_ENDED = "call ended; finalizing %s"
    PROCESSED = "meeting %s processed: %s"
    POSTPROCESS_FAILED = "post-processing of %s failed"
    ORPHAN_FOUND = "orphan recording found (%s); trying to finalize"
    ORPHAN_DISCARDED = "could not finalize the orphan recording; discarding"
    CONFIRM_ANSWER = "keep-recording answer for %s: %s"
    CONFIRM_FAILED = "could not ask whether to keep %s; keeping it"
    CONFIRM_DIALOG_FAILED = "keep-recording dialog failed: %s"
    DISCARDED_DURING_CALL = "recording %s discarded by the user; ignoring this call until it ends"
    DISCARDED_AFTER_CALL = "recording %s discarded by the user after the call ended"
    IGNORED_CALL_ENDED = "the ignored call ended; the next call will be recorded"
    RESUMED = "pending work resumed: %s"
    STOPPED_NOT_MIXED = "meeting %s was stopped but not mixed; mixing it now"
    MIX_TIMEOUT = "mixing %s s of audio with a %.0f s time limit"
    RESUME_FAILED = "failed to resume pending work"
    PURGE_DONE = "audio retention: %s audio file(s) removed"
    PURGE_FAILED = "audio retention failed; it runs again on the first tick of tomorrow"
    AFTER_ANALYSIS_FAILED = "the after-analysis hook failed for meeting %s"
    WORKER_STARTED = "activities curator worker started"
    WORKER_STOPPING = "activities curator worker told to stop; a pass in flight is not awaited"
    WORKER_STOPPED = "activities curator worker stopped"
    WORKER_QUEUE = "activities curator: %d meeting(s) to curate (%d queued, %d pending): %s"
    WORKER_QUEUE_PENDING_FAILED = "activities curator: pending meetings could not be listed: %s"
    WORKER_QUEUE_FILTER_FAILED = "activities curator: the queued meetings could not be checked against the pass log: %s"
    WORKER_QUEUE_DONE = "activities curator: %d queued meeting(s) already curated, dropped: %s"
    WORKER_PASS_START = "activities curator pass %d/%d: %s"
    WORKER_LOCK_WAIT = "activities curator pass %s waits for the document lock"
    WORKER_PASS_END = "activities curator pass %s done: %d curated, %d failed, %d deferred, %d edit(s)"
    WORKER_PASS_FAILED = "activities curator pass %s raised"
    WORKER_PENDING_ENQUEUED = "activities curator: %d meeting(s) without a pass queued at start: %s"
    WORKER_PENDING_FAILED = "activities curator: the meetings without a pass could not be queued: %s"
    STEP_FAILED = "%s failed for meeting %s"
    NOTIFICATION_FAILED = "notification failed: %s"
    LOG_NOTIFICATION = "[%s] %s"
    USAGE_LOG_FAILED = "could not record LLM usage"
    EXEC_RETRY = "exec of %s failed (%s); attempt %d/%d"
    IO_RETRY = "file access %s failed (%s); attempt %d/%d"
    WARMUP_BINARY_FAILED = "warm-up of %s failed: %s"
    SIGKILL = "process %s did not exit within %.0fs; SIGKILL"
    FORCED_STOP = "recorder %s did not stop within %.0fs of its stop file; terminating it"
    TRACK_INFO = "track %s: %.1f MB, %.1f s, mean %s dB, peak %s dB"
    TRACK_DISCARDED = "track %s: %.1f MB (discarded)"
    TRACK_ANOMALY = "track anomaly (%s); raw copies kept in %s"
    TRANSCRIPT_DEGRADED = "transcript of %s is degraded: %.0f%% of segments in repetition loops, text in %s of %s min"
    TRANSCRIPT_RETRY = "transcribing %s again with the anti-loop settings"
    TRANSCRIPT_RETRY_RESULT = "retry of %s: %.0f%% of segments in loops, text in %s of %s min; keeping the %s pass"
    PASS_FIRST, PASS_RETRY = "first", "retry"   # names used in TRANSCRIPT_RETRY_RESULT
    TRANSCRIPT_RETRY_FAILED = "retry of %s failed; keeping the first pass: %s"
    TRANSCRIPT_RETRY_SKIPPED = "no retry for %s: its Teams track was recorded at the wrong sample rate, which a second pass cannot repair"
    VERIFY_FAILED = "verification of %s failed; its claims stay unverified (the code checks still apply): %s"
    VERIFIED = "verification of %s: %d claims confirmed, %d unconfirmed"
    VERIFY_SKIPPED = ("verification of %s skipped: its transcript cannot be trusted (degraded: %s, wrong sample rate: %s), so the "
                      "verifier would confirm what the analysis took from it; its claims stay unverified (the code checks still apply)")
    RATE_MISMATCH = ("Teams track of %s was likely recorded at the wrong sample rate: %.0f%% of it padded in short pads "
                     "(%.0f of %.0f s, device rate(s) %s); its transcript is unreliable")
    CAPTURE_STATS_UNREADABLE = "capture stats of %s unreadable; skipping the sample-rate check: %s"
    SPEAKERS_LABELLED = "speaker labels of %s: %d of %d lines labelled (%s)"
    SPEAKERS_LABEL_FAILED = "speaker labels of %s could not be computed: %s; transcript saved without labels"
    NO_SPEAKER_LABELS = "no speaker labels for %s: %s"
    SPEAKERS_NOTICE_FAILED = "the speaker-labels notice for %s could not be recorded: %s"
    SPEAKERS_BOOTOUT_FAILED = "launchctl bootout of %s failed (%s); stopping pid %d directly"
    SPEAKERS_STALE_STOPPED = "booted out the speaker observer job %s that no recording owned (pid %s)"
    SPEAKERS_CHECK_FAILED = "speaker observer check of %s failed: %s; the recording goes on (not logged again for this call)"
    ACTIVITIES_ROLLED_FORWARD = "activities pass %s was interrupted after it replaced the document; completed it"
    ACTIVITIES_ROLLED_BACK = "activities pass %s was interrupted before it replaced the document; rolled it back"
    ACTIVITIES_COMMIT_RETRY = "activities pass %s: %s failed (%s); attempt %d/%d"
    ACTIVITIES_LOG_TORN = "the last line of the activities pass log %s is cut short; ignoring it"
    ACTIVITIES_ARCHIVE_CHANGED = "archive %s is no longer the size the pass left (%d, now %d); its entries stay in place"
    CURATE_PASS_DONE = "activities pass %s committed: %d edit(s)%s"
    CURATE_PASS_UNFINISHED = "activities pass %s replaced the document but is not fully recorded: %s"
    CURATE_RETRIED = " after one repair round"
    CURATE_PASS_EMPTY = "activities pass %s: nothing to curate in %s"
    CURATE_PASS_FAILED = "activities pass %s failed: %s"
    CURATE_ISOLATING = "activities pass of %d meetings failed; running them one at a time"
    CURATE_WAITING = "the activities curator is busy; waiting for it"
    CURATE_STEP_FAILED = "activities pass %s: could not %s: %s"
    CURATE_STEP_LOG = "log the failed pass"
    CURATE_STEP_ERROR_FILE = "write the curation error of %s"
    CURATE_STEP_CLEAR = "clear the curation error of %s"
    CURATE_STEP_NOTIFY = "send the notification"
    CURATE_SKIP_DAMAGED = "meeting %s has no readable meta.json; it is left out of the curation window: %s"
    ACTIVITIES_ROTATE_FAILED = "old activities versions in %s could not be removed: %s"


class Prompt:
    """Text the code adds around the data sent to the model (the system prompts live in prompts/*.md)."""

    USER_NAME = "User (recording owner): {name}"
    MEETING_DATE = "Meeting date: {date} ({weekday})"
    MEETING_START = "Start: {time}"
    MEETING_TITLE = "Title: {title}"
    MEETING_DURATION = "Duration: {minutes} min"
    ROSTER = "Participants seen in the meeting window: {names}"
    SPEAKER_LABELS = 'Speaker labels: the name after a timestamp is who said the line; "{label}" is the recording owner'
    TRANSCRIPT_HEADER = "\n\nTranscript (with timestamps):\n\n"
    WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    # JSON Schema field descriptions (part of the contract with the model)
    FIELD_ACTION_DESCRIPTION = "Task, starting with a verb in the infinitive"
    FIELD_DEADLINE_WHO = ("Who delivers it; '{self_owner}' for the recording owner (and for lines labelled with the owner's label); "
                          "another person only when the transcript makes it evident; '{unknown}' otherwise")
    FIELD_ACTION_OWNER = ("Owner; '{self_owner}' for the recording owner (and for lines labelled with the owner's label); "
                          "another person only when the transcript makes it evident (a name after the timestamp is who said the line); '{unknown}' otherwise")
    FIELD_DUE = "Due date in ISO format (YYYY-MM-DD) or null"
    FIELD_ISO_DATE = "ISO date or null"
    FIELD_AT = "Transcript timestamp (HH:MM:SS) of the line where it was said, or null"
    FIELD_ACTION_KIND = "feature, bug, technical, operation, management or communication (see the rules)"
    FIELD_PRIORITY = "high/medium/low only when urgency was stated or clearly implied; otherwise null"
    FIELD_TITLE = "Short meeting title (max 8 words), inferred from the content"
    FIELD_PURPOSE = "One sentence: why the meeting happened"
    FIELD_MEETING_TYPE = "standup, client, project_review, one_on_one or other"
    FIELD_PARTICIPANTS = ("Names of people who speak or are addressed directly in the meeting, not people only talked about (no guessing); "
                          "exactly the listed participants when the message lists participants seen in the meeting window")
    FIELD_TOPICS = "Main discussion topics in order, each with its key points"
    FIELD_RISKS = "Risks, blockers or issues raised"
    FIELD_FOR_WHOM = "Who receives the result or waits for it, when the meeting said so (a name, or 'the client'); otherwise null"
    FIELD_STATUS_UPDATES = ("What the meeting said about work that already existed before it: done, in progress, blocked, delayed, "
                            "new date, reassigned or cancelled; not new tasks and not intentions (see the rules)")
    FIELD_STATUS_ABOUT = "The work referred to, in the meeting's words, specific enough to be matched to a task later"
    FIELD_STATUS_CHANGE = "done, in_progress, blocked, delayed, due_changed, reassigned or cancelled (see the rules)"
    FIELD_STATUS_WHO = ("Whose work it is; '{self_owner}' for the recording owner (and for lines labelled with the owner's label); "
                        "another person only when the transcript makes it evident; '{unknown}' otherwise")
    FIELD_STATUS_EVIDENCE = "The literal words that say it, at most 20 words, hedges kept (acho que, quase)"
    FIELD_STATUS_NEW_DUE = "The new date in ISO format (YYYY-MM-DD) for due_changed and delayed when one was said; otherwise null"
    FIELD_STATUS_NEW_OWNER = "The person the work passes to, for reassigned; otherwise null"
    STORIES_DATE = "Date: {date} ({weekday})"
    STORIES_BLOCKS = "\n## Tagged items (JSON; cite each `ref` in `block` and in `skipped`)\n"
    STORIES_MEETINGS = "\n## Context: analyses of the meetings these items link to (JSON)\n"
    STORIES_EXISTING = "\n## Existing stories from recent days (JSON; never duplicate them: cite their id in duplicate_of)\n"
    STORY_GUIDE_HEADER = "\n\n# User story guide\n\nThe user's own rules. Follow them for format, style and what counts as a story.\n\n"
    FIELD_STORY_TITLE = "Short story title, as the guide asks"
    FIELD_STORY_NARRATIVE = "The story sentence in the guide's format (persona, capability, benefit)"
    FIELD_STORY_CRITERIA = "Acceptance criteria, one per item, checkable by someone who was not in the meeting"
    FIELD_CRITERION_TEXT = "The criterion, without its source"
    FIELD_CRITERION_SOURCE = "hh:mm:ss of the action or decision it comes from (an `at` you received), or suggestion when nobody said it"
    FIELD_STORY_DETAILS = "Other sections the guide asks for, in Markdown without top-level headings; empty if none"
    FIELD_STORY_QUESTIONS = "What must be answered before the story can start; empty if nothing"
    FIELD_STORY_BLOCK = "ref of the tagged item this story comes from, exactly as received"
    FIELD_STORY_KIND = "feature or bug for a user story, technical or operation for a task card; management or communication when the item is neither"
    FIELD_STORY_PRIORITY = "high/medium/low only when the item or its meetings stated or clearly implied the urgency; otherwise null"
    FIELD_STORY_DUE = "Due date in ISO format (YYYY-MM-DD) when the item or its meetings gave one; otherwise null"
    FIELD_SKIPPED_REF = "ref of the tagged item that is not a story, exactly as received"
    FIELD_SKIPPED_REASON = "Short reason why this item is not a story"
    FIELD_SKIPPED_DUPLICATE = "id of the existing story that already covers this item, or null"
    # The verifier's message keeps the prototype's shape (scripts/fidelity_eval.py verify_meeting, describe),
    # which the evaluation measured (§14.3).
    VERIFY_TRANSCRIPT = "\n\n## Transcript\n"
    VERIFY_EXCERPTS = "\n\n## Transcript (long meeting: its start and the lines around each claim's timestamp; [...] marks a gap)\n"
    VERIFY_CLAIMS = "\n\n## Claims\n"
    EXCERPT_GAP = "[...]"
    CLAIM_LINE = "[{id}] ({kind}) {text}"
    CLAIM_OWNER = " | owner: {owner}"
    CLAIM_DUE = " | date: {due}"
    CLAIM_AT = " | cited at {at}"
    OWNER_SELF = "the user"   # the recording owner, when their name is not configured
    FIELD_VERDICT_ID = "the claim's id, exactly as given in brackets"
    FIELD_SUPPORT = "supported, partial, unsupported or contradicted"
    FIELD_OWNER_EVIDENT = "for claims with an owner: true when the transcript makes clear that person will do it; null when there is no owner"
    FIELD_DATE_SAID = "for claims with a date: true when that date, or an expression resolving to it, is said; null when there is no date"
    FIELD_TENTATIVE = "true when the transcript presents it tentatively rather than as decided"
    FIELD_SENSITIVE = "true when the claim carries sensitive personal data or a personal judgment about someone"
    FIELD_REASON = "one short sentence in Brazilian Portuguese explaining the verdict"
    # The curator's message (adapters/outbound/curator_claude.py); prompts/curate_system.md explains every part of it.
    CURATE_OPEN = "<{name}{attrs}>"
    CURATE_CLOSE = "</{name}>"
    CURATE_ATTR = ' {name}="{value}"'
    CURATE_NOW = "Now: {weekday} {date} {time}"
    CURATE_WHEN = "{date} {time}"
    CURATE_NONE = "(none)"
    CURATE_HEALTH_DEGRADED = "degraded"
    CURATE_HEALTH_RATE = "wrong_sample_rate"
    CURATE_REF = "{n}.{kind}{i}"
    CURATE_LINE = "{ref} {text}"
    CURATE_STATUS = "{ref} {change}: {about}"
    CURATE_OWNER = " | owner: {owner}"
    CURATE_WHO = " | who: {who}"
    CURATE_DUE = " | due: {due}"
    CURATE_DATE = " | date: {date}"
    CURATE_PRIORITY = " | priority: {priority}"
    CURATE_FOR = " | for: {name}"
    CURATE_NEW_DATE = " | new date: {date}"
    CURATE_NEW_OWNER = " | new owner: {owner}"
    CURATE_QUOTE = ' | quote: "{evidence}"'
    CURATE_AT = " | at: {at}"
    CURATE_UNCONFIRMED = " | ⚠️ unconfirmed: {reason}"
    CURATE_UNCONFIRMED_NO_REASON = " | ⚠️ unconfirmed"
    CURATE_FAILURE = "[{index}] {error}{detail}\n{op}"
    CURATE_FAILURE_DETAIL = " ({detail})"
    CURATE_TASK = (
        "Do this pass, in order:\n"
        "1. Apply the user's edits and the box lines.\n"
        "2. Add or update the document from each ref of each meeting.\n"
        "3. Housekeeping: ticked items, past agenda entries, old context, 💤, the limit of two sub-lines.\n"
        "4. Account for every ref: it appears in the `refs` of an edit or in `ignored`.\n"
        "5. Copy every target and anchor exactly from `<document>`, from its body only (never the box or the link block).\n"
        "6. Remove or change no checkbox line except with `archive`; every reorder is a `move`.\n"
        "7. Write all content in Brazilian Portuguese."
    )
    CURATE_REPAIR_TASK = (
        "The edits in `<failed_edits>` of your previous answer did not apply. `<document>` is the text as it stands now, "
        "with the edits that did apply already in it. For each failed edit, return a corrected edit in `ops`: copy every "
        "target and anchor exactly from `<document>`, keep the `refs`, and respect the checkbox rule. Leave out an edit "
        "that no longer makes sense because its effect is already in the document. Return only `ops`."
    )
    # JSON Schema field descriptions of the curator's answer (part of the contract with the model)
    FIELD_CURATE_OPS = "Edits to the document, applied in order, each to the text the previous ones left"
    FIELD_OP_KIND = "replace, insert_after, move or archive"
    FIELD_OP_TARGET = ("Whole line or lines of the document body, copied character by character; for move and archive "
                       "the whole item (main line and sub-lines); for insert_after one line")
    FIELD_OP_TEXT = "replace and insert_after: the new text; an empty string in replace removes the lines; null for move and archive"
    FIELD_OP_REASON = "archive: the reason, in Brazilian Portuguese; null for the other edits"
    FIELD_OP_ANCHOR = "move: one whole line of the document body, after which the item is pasted; null for the other edits"
    FIELD_OP_REFS = "Refs of the meeting items this edit accounts for, for example 1.a1; empty when it accounts for none"
    FIELD_CURATE_REMOVED = "Items the user deleted from the document since the last pass; the app archives them as removed by the user"
    FIELD_REMOVED_TEXT = "The deleted item exactly as the user edits show it, main line and sub-lines"
    FIELD_REMOVED_NOTE = "One short note in Brazilian Portuguese for the archive entry"
    FIELD_CURATE_FOCUS = "3 to 5 lines in Brazilian Portuguese, without numbers: what to do next, items in bold, and why now"
    FIELD_CURATE_SUMMARY = "One line in Brazilian Portuguese saying what this pass changed"
    FIELD_CURATE_NOTIFY = "true when the pass added an action of the user's, added a 💬, changed a date of the user's, removed an item other than by a tick, or suspects an editor overwrite"
    FIELD_CURATE_IGNORED = "Refs that need no edit, each with the reason"
    FIELD_IGNORED_REF = "The ref, for example 1.o2"
    FIELD_IGNORED_WHY = "Why it needs no edit, in Brazilian Portuguese"


class Minutes:
    """Labels of minutes.md. Portuguese on purpose: it is a document for the user, written from
    LLM content that is in Portuguese (one of the Portuguese exceptions in AGENTS.md, English only)."""

    TITLE = "# Ata: {title}"
    DEGRADED = ("> ⚠️ **Transcrição degradada:** {loop:.0%} dos trechos são uma mesma frase repetida pelo reconhecimento de voz{gaps}. "
                "Esta ata pode estar incompleta: ouça o áudio desses trechos antes de usá-la.")
    DEGRADED_GAPS = ", e não há texto em {ranges}"
    NOT_VERIFIED = "> Esta transcrição não serve de prova: nenhum item desta ata foi confirmado a partir dela."   # true whether verification ran or not
    UNCONFIRMED_LEGEND = "> ⚠️ Os itens marcados com ⚠️ não foram confirmados na transcrição; o motivo vem ao lado. Confira-os no áudio antes de usar."
    MARK = " ⚠️ _a confirmar: {reason}_"   # reason: one line, with Markdown's _ and * escaped
    MARK_NO_REASON = " ⚠️ _a confirmar_"
    RATE_MISMATCH = ("> ⚠️ **Áudio do Teams gravado com a taxa errada:** {share:.0%} da faixa do Teams é silêncio de preenchimento, "
                     "e a fala dos outros participantes saiu acelerada e picotada. A transcrição dessa parte não é confiável: "
                     "confirme com os participantes antes de usar esta ata.")
    DATE = "📅 **Data:** {date}, {start}–{end} ({minutes} min)"
    DATE_NO_END = "📅 **Data:** {date}, {start}"
    UNDER_A_MINUTE = "<1"
    PARTICIPANTS = "👥 **Participantes:** {names}"
    NO_PARTICIPANTS = "não identificados"
    TYPE = "🏷️ **Tipo:** {label}"
    PURPOSE = "🎯 **Objetivo:** {purpose}"
    SUMMARY = "### 📋 Resumo"
    TOPICS = "### 💡 Tópicos"
    TOPIC_LINE = "{n}. **{title}**"
    POINT_LINE = "   - {text}"
    DECISIONS = "### ✅ Decisões"
    DECISION_LINE = "- {text}{at}"
    ACTIONS = "### 📌 Ações"
    ACTIONS_HEADER = "| # | Ação | Responsável | Prazo | Prioridade | Dito em |\n|---|---|---|---|---|---|"
    ACTION_ROW = "| {n} | {description} | {owner} | {due} | {priority} | {at} |"
    NO_ACTIONS = "Nenhuma ação registrada."
    STATUS_UPDATES = "### 🔄 Andamento informado"
    STATUS_LINE = "- {who}: {change} — {about}{detail} · \"{evidence}\"{at}{mark}"
    STATUS_AT = " [{at}]"
    STATUS_NEW_DUE = " (nova data {date})"
    STATUS_NEW_OWNER = " (para {owner})"
    STATUS_WHO_SELF = "Você"
    STATUS_WHO_UNKNOWN = "Alguém"
    STATUS_MARK = " ⚠️ não confirmado: {reason}"
    STATUS_MARK_NO_REASON = " ⚠️ não confirmado"
    STATUS_CHANGE_LABELS = {
        "done": "concluído", "in_progress": "em andamento", "blocked": "bloqueado", "delayed": "atrasado",
        "due_changed": "prazo alterado", "reassigned": "reatribuído", "cancelled": "cancelado",
    }
    WEEKDAYS_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
    RISKS = "### ⚠️ Riscos e bloqueios"
    QUESTIONS = "### ❓ Perguntas em aberto"
    NEXT_STEPS = "### 🔜 Próximos passos"
    DEADLINE_LINE = "- {what}{when}{who}"
    BULLET = "- {text}"
    AT = " `[{at}]`"
    WHEN = " — {date}"
    WHO = " · {who}"
    DASH = "—"
    OWNER_SELF = "{name} (você)"
    OWNER_SELF_NO_NAME = "você"
    OWNER_UNKNOWN = "⚠️ sem responsável"
    SPEAKER_USER_FALLBACK = "Você"   # label of the user's lines when neither [user] name nor the user's own tile name is known
    FOOTER = "---\n_Gerada automaticamente a partir da transcrição. Confira cada item no horário indicado antes de compartilhar._"
    # Reasons stored with an unconfirmed claim and shown in these minutes (task 4.0); the verifier writes its own.
    REASON_SENSITIVE = "contém dado pessoal sensível"
    REASON_NOT_HEARD = "não fala nem é chamado(a) na transcrição; talvez só tenha sido mencionado(a)"
    REASON_NO_VERDICT = "a verificação não avaliou este item"
    TYPE_LABELS = {
        "standup": "Daily",
        "client": "Reunião com cliente",
        "project_review": "Revisão de projeto",
        "one_on_one": "1:1",
        "other": "Reunião",
    }
    PRIORITY_LABELS = {"high": "🔴 Alta", "medium": "🟡 Média", "low": "🟢 Baixa"}


class StoryDoc:
    NOT_VERIFIED = "> A transcrição da reunião {meeting} não serve de prova: nenhum item que veio dela foi confirmado."
    """Labels of plans/<day>.stories.md. Portuguese on purpose, like `Minutes`: a document for
    the user, built from LLM content that is in Portuguese."""

    TITLE = "# Rascunhos de user stories — {date}"
    INTRO = "_Gerados dos itens marcados com #história em {date}. Cada história publicada mostra abaixo do título o board e o id da tarefa; as demais ainda não saíram daqui._"
    NO_STORIES = "Nenhum item virou história."
    STORY_TITLE = "## {n}. {title}"
    PRIORITY = "**Prioridade:** {label}"
    PUBLISHED = "**Publicada em:** {destination} `{ref}`"
    DUE = "**Prazo:** {date}"
    MEETINGS = "**Reuniões:** {ids}"
    META_SEPARATOR = " · "
    CRITERIA = "**Critérios de aceite**"
    CRITERION = "- [ ] {text}"
    CRITERION_AT = " `[{at}]`"              # a criterion said in a meeting, at this transcript time
    CRITERION_SUGGESTION = " _(sugestão)_"  # a criterion the writer proposes
    BOARD_CRITERION_AT = " [{at}]"          # the same on the board, where criteria are plain text
    BOARD_SUGGESTION = " (sugestão)"
    QUESTIONS = "**Perguntas em aberto**"
    SOURCE_BLOCK = "**Item de origem**"
    QUOTE = "> {line}"
    BULLET = "- {text}"
    SKIPPED = "## Itens que não viraram história"
    SKIPPED_LINE = "- `{id}` — {reason}{covered_by}"           # a planner-era entry: only its action id is stored
    SKIPPED_BLOCK_LINE = "- {line} — {reason}{covered_by}"       # a block: its tagged line, in a code span
    CODE_SPAN = "`{text}`"
    LONG_CODE_SPAN = "`` {text} ``"                               # the text holds a backtick itself
    DUPLICATE_OF = " (já coberto por: {title})"
    BOARD_ORIGIN = "**Origem:** plano de {day} · reuniões {meetings} · ações {actions}"   # a planner-era story
    BOARD_ORIGIN_BLOCK = "**Origem:** atividades de {day} · reuniões {meetings}"          # a story drafted from a tagged item
    BOARD_DRAFTS = "**Rascunho:** `{path}`"
    ACTION_REF = "`{id}`"
    NOT_ADDRESSED = "o modelo não incluiu este item em nenhuma história"   # stored as the skip reason
    OTHER_KIND = "{kind}: não vira história nem card"                        # stored as the skip reason
    UNCONFIRMED = "⚠️ **A confirmar na transcrição:** {reason}"
    UNCONFIRMED_NO_REASON = "⚠️ **A confirmar na transcrição.**"
    DEGRADED = ("> ⚠️ **Transcrição degradada** na reunião {meeting}: {loop:.0%} dos trechos são uma mesma frase repetida "
                "pelo reconhecimento de voz{gaps}. O que veio dela pode estar incompleto.")   # gaps: Minutes.DEGRADED_GAPS
    RATE_MISMATCH = ("> ⚠️ **Áudio do Teams gravado com a taxa errada** na reunião {meeting}: {share:.0%} da faixa do Teams é "
                     "silêncio de preenchimento, e a fala dos outros participantes saiu acelerada e picotada. O que veio dela pode "
                     "ter sido inventado pelo reconhecimento de voz: confirme com os participantes antes de publicar.")
    KIND = "**Tipo:** {label}"
    KIND_LABELS = {
        "feature": "Feature", "bug": "Bug", "technical": "Tarefa técnica",
        "operation": "Operação", "management": "Gestão", "communication": "Comunicação",
    }
    FOOTER = "---\n_Rascunho gerado automaticamente seguindo o guia de user stories. Confira cada história antes de publicar._"


class ActivityDoc:
    """Markers, headings and labels of data/activities/atividades.md. Portuguese on purpose, like `Minutes`: it is a
    document for the user, and the model writes its content in Portuguese."""

    BOX_START = "<!-- curador:início (reescrito a cada passada; escreva fora desta caixa) -->"
    BOX_END_PREFIX = "<!-- curador:fim"       # the closing marker is prefix + (" " + stamp) + suffix
    BOX_END_SUFFIX = " -->"
    LINKS_START = "<!-- links:início (gerado automaticamente) -->"
    LINKS_END = "<!-- links:fim -->"
    HEADING_ACTIONS = "## Minhas ações"
    HEADING_WAITING = "## Aguardando outros"
    HEADING_AGENDA = "## Agenda e prazos"
    HEADING_CONTEXT = "## Contexto recente"
    UPDATED = "Atualizado"
    AFTER = "após"
    FOCUS = "Foco"
    WEEKDAYS = Minutes.WEEKDAYS_SHORT
    TODAY = "(hoje)"
    TITLE = "# Atividades"
    REMOVED_BY_USER = "removido por você"      # archive reason of an item the user deleted
    ARCHIVE_PREFIX = "### "                    # an archive entry starts with this heading marker
    ARCHIVE_HEADER = ARCHIVE_PREFIX + "{date} — {reason}"
    LINK_DEFINITION = "[{label}]: {target}"
    EMPHASIS = "**"                            # bold marks around an item's title
    STORY_TAG = "#história"                    # written by the user on an item to ask for a story (`trec stories`)
    STORY_LINK = "história: [rascunho {date}]({target})"   # replaces the tag once the draft exists
    STORY_EXISTS = 'história: já existe ("{title}")'       # replaces the tag when the writer found the story already there
