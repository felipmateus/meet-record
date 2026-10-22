import re
from pathlib import Path

import pytest

from teams_recorder.config import APP_SUPPORT_DIR, default_data_dir, is_icloud_synced, is_tcc_protected, load_settings
from teams_recorder.constants import Audio, Effort, LlmProvider, MicBackend, Stories, StoryDestination
from teams_recorder.messages import Err


def test_load_settings_reads_toml_and_env(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config.toml").write_text(
        '[audio]\nmic_device = "USB Mic"\nretention_days = 7\n[llm]\neffort = "medium"\n'
    )
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test-123\n")

    s = load_settings(tmp_path)

    assert s.project_dir == tmp_path.resolve()
    assert s.data_dir == tmp_path.resolve() / "data"
    assert s.mic_device == "USB Mic" and s.mic_backend == "coreaudio"
    assert s.retention_days == 7
    assert s.llm_effort == "medium"
    assert s.llm_model == "claude-opus-5-5"
    assert s.has_api_key and s.anthropic_api_key == "sk-test-123"


def test_load_settings_defaults_without_files(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = load_settings(tmp_path)
    assert s.language == "auto" and s.retention_days == Audio.RETENTION_DAYS == 30
    assert not s.has_api_key


def test_explicit_data_dir(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[paths]\ndata_dir = "~/other/place"\n')
    assert load_settings(tmp_path).data_dir == Path("~/other/place").expanduser()


def test_icloud_detection(tmp_path: Path):
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Documents" / "proj"
    icloud.mkdir(parents=True)
    assert is_icloud_synced(icloud)
    assert not is_icloud_synced(tmp_path)
    assert default_data_dir(icloud) == Path.home() / "Library" / "Application Support" / "teams-recorder"
    assert default_data_dir(tmp_path) == tmp_path / "data"


def test_llm_provider_from_toml_and_env(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text('[llm]\nprovider = "claude-code"\ncli_model = "sonnet"\n')
    s = load_settings(tmp_path)
    assert s.llm_provider == "claude-code" and s.llm_cli_model == "sonnet"
    monkeypatch.setenv("TREC_LLM_PROVIDER", "api")
    assert load_settings(tmp_path).llm_provider == "api"


def test_invalid_llm_provider(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text('[llm]\nprovider = "gemini"\n')
    import pytest
    with pytest.raises(ValueError, match="llm.provider"):
        load_settings(tmp_path)


def test_teams_process_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TREC_TEAMS_PROCESS", "python3.11")
    assert load_settings(tmp_path).teams_process_name == "python3.11"
    monkeypatch.delenv("TREC_TEAMS_PROCESS")
    assert load_settings(tmp_path).teams_process_name == "MSTeams"


def test_mic_backend_from_toml(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[audio]\nmic_backend = "ffmpeg"\n')
    assert load_settings(tmp_path).mic_backend == "ffmpeg"
    assert load_settings(tmp_path).mic_device == "default"


def test_settings_use_enums(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    s = load_settings(tmp_path)
    assert s.llm_provider is LlmProvider.API
    assert s.mic_backend is MicBackend.COREAUDIO
    assert s.llm_effort is Effort.HIGH


def test_invalid_mic_backend_and_effort(tmp_path: Path):
    import pytest
    (tmp_path / "config.toml").write_text('[audio]\nmic_backend = "pulseaudio"\n')
    with pytest.raises(ValueError, match="audio.mic_backend"):
        load_settings(tmp_path)
    (tmp_path / "config.toml").write_text('[llm]\neffort = "ultra"\n')
    with pytest.raises(ValueError, match="llm.effort"):
        load_settings(tmp_path)
    (tmp_path / "config.toml").write_text('[verification]\neffort = "ultra"\n')
    with pytest.raises(ValueError, match="verification.effort"):
        load_settings(tmp_path)


def test_denoise_and_vad_settings(tmp_path: Path):
    s = load_settings(tmp_path)
    assert s.denoise is True and s.vad is False and s.vad_model_path is None
    (tmp_path / "config.toml").write_text('[audio]\ndenoise = false\n[transcription]\nvad = true\n')
    s = load_settings(tmp_path)
    assert s.denoise is False and s.vad_model_path.name == "ggml-silero-v5.1.2.bin"


def test_tcc_protected_folders_get_app_support_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    docs = tmp_path / "Documents" / "proj"; docs.mkdir(parents=True)
    dev = tmp_path / "dev" / "proj"; dev.mkdir(parents=True)
    assert is_tcc_protected(docs) and not is_tcc_protected(dev)
    assert default_data_dir(dev) == dev / "data"
    # APP_SUPPORT_DIR was computed at import time with the real home; only the rule matters here
    assert default_data_dir(docs) == APP_SUPPORT_DIR


def test_relative_data_dir_is_resolved_against_project(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[paths]\ndata_dir = "data"\n')
    assert load_settings(tmp_path).data_dir == tmp_path.resolve() / "data"
    (tmp_path / "config.toml").write_text('[paths]\ndata_dir = "/abs/place"\n')
    assert load_settings(tmp_path).data_dir == Path("/abs/place")


def test_user_name(tmp_path: Path):
    assert load_settings(tmp_path).user_name == ""
    (tmp_path / "config.toml").write_text('[user]\nname = " Felipe "\n')
    assert load_settings(tmp_path).user_name == "Felipe"


def test_confirmation_settings(tmp_path: Path):
    s = load_settings(tmp_path)
    assert s.confirm_recording is True and s.confirm_timeout_seconds == 30
    (tmp_path / "config.toml").write_text("[confirmation]\nenabled = false\ntimeout_seconds = 10\n")
    s = load_settings(tmp_path)
    assert s.confirm_recording is False and s.confirm_timeout_seconds == 10


def test_windows_platform_settings(tmp_path: Path, monkeypatch):
    from teams_recorder.constants import Platform

    monkeypatch.delenv("TREC_TEAMS_PROCESS", raising=False)
    (tmp_path / "config.toml").write_text('[audio]\nteams_process_name = "MSTeams"\n')
    win = load_settings(tmp_path, platform=Platform.WINDOWS)
    mac = load_settings(tmp_path, platform=Platform.MACOS)
    assert win.platform is Platform.WINDOWS and win.teams_process_name == "ms-teams.exe"
    assert mac.teams_process_name == "MSTeams"
    (tmp_path / "config.toml").write_text('[audio]\nteams_process_name_windows = "Teams.exe"\n')
    assert load_settings(tmp_path, platform=Platform.WINDOWS).teams_process_name == "Teams.exe"


def test_windows_keeps_data_in_documents(tmp_path: Path, monkeypatch):
    """The macOS TCC fallback to Application Support does not apply on Windows."""
    from teams_recorder.constants import Platform

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    project = tmp_path / "Documents" / "teams-recorder"
    project.mkdir(parents=True)
    assert default_data_dir(project, Platform.WINDOWS) == project / "data"
    assert default_data_dir(project, Platform.MACOS) == APP_SUPPORT_DIR


def test_find_tool_looks_in_project_tools(tmp_path: Path, monkeypatch):
    from teams_recorder.config import find_tool

    monkeypatch.setenv("PATH", "")
    exe = tmp_path / "tools" / "whisper" / "Release" / "whisper-cli.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert find_tool("whisper-cli", tmp_path) == str(exe)
    assert find_tool("ffmpeg", tmp_path) == "ffmpeg"


def test_bit_depth_setting(tmp_path: Path):
    import pytest

    assert load_settings(tmp_path).bit_depth == 16
    (tmp_path / "config.toml").write_text("[audio]\nbit_depth = 32\n")
    s = load_settings(tmp_path)
    assert s.bit_depth == 32 and s.raw_bytes_per_hour == 2 * load_settings(tmp_path / "x").raw_bytes_per_hour
    (tmp_path / "config.toml").write_text("[audio]\nbit_depth = 24\n")
    with pytest.raises(ValueError, match="bit_depth"):
        load_settings(tmp_path)


def test_raw_bytes_per_hour():
    from teams_recorder.constants import raw_bytes_per_hour

    assert raw_bytes_per_hour(16) == 1_036_800_000      # 48 kHz x 3 channels x 2 bytes x 3600 s
    assert raw_bytes_per_hour(32) == 2_073_600_000


def test_stories_settings(tmp_path: Path):
    defaults = load_settings(tmp_path)
    assert defaults.story_guide_path == tmp_path.resolve() / "prompts" / "user_story_guide.md"

    (tmp_path / "config.toml").write_text('[stories]\nguide = "docs/guia.md"\n')
    s = load_settings(tmp_path)
    assert s.story_guide_path == tmp_path.resolve() / "docs" / "guia.md"

    (tmp_path / "config.toml").write_text('[stories]\nguide = "~/guia.md"\n')
    assert load_settings(tmp_path).story_guide_path == Path("~/guia.md").expanduser()


def test_retention_days_reads_audio_with_the_old_planner_key_as_fallback(tmp_path: Path):    # UT-092
    config = tmp_path / "config.toml"
    config.write_text("[planner]\nhour = 18\nretention_days = 10\n")
    assert load_settings(tmp_path).retention_days == 10                       # no [audio] key: the old one is read, `hour` is ignored
    config.write_text("[audio]\nretention_days = 45\n[planner]\nretention_days = 10\n")
    assert load_settings(tmp_path).retention_days == 45                       # both: [audio] wins
    config.write_text("[audio]\nmic_device = \"default\"\n")
    assert load_settings(tmp_path).retention_days == 30                       # neither: the default
    assert not hasattr(load_settings(tmp_path), "plan_hour")


def test_an_old_stories_enabled_key_loads_and_is_ignored(tmp_path: Path):     # UT-093
    (tmp_path / "config.toml").write_text('[stories]\nenabled = true\nguide = "docs/guia.md"\n')
    s = load_settings(tmp_path)
    assert s.story_guide_path == tmp_path.resolve() / "docs" / "guia.md" and not hasattr(s, "stories_enabled")


def test_publishing_settings_default_to_off(tmp_path: Path):
    s = load_settings(tmp_path)
    assert not s.story_auto_publish and s.story_destinations == () and s.story_dedup_days == Stories.DEDUP_DAYS
    assert s.backlog_project_dir is None and s.backlog_status == Stories.BACKLOG_STATUS and s.backlog_labels == Stories.BACKLOG_LABELS


def test_publishing_settings_from_toml(tmp_path: Path):
    (tmp_path / "config.toml").write_text(
        '[stories]\npublish = true\ndestinations = ["backlog-md"]\ndedup_days = 7\n'
        '[stories.backlog_md]\nproject_dir = "."\nstatus = "Inbox"\nlabels = ["work", "meetings"]\n'
    )
    s = load_settings(tmp_path)
    assert s.story_auto_publish and s.story_destinations == (StoryDestination.BACKLOG_MD,) and s.story_dedup_days == 7
    assert s.backlog_project_dir == tmp_path.resolve()          # "." = the project folder
    assert s.backlog_status == "Inbox" and s.backlog_labels == ("work", "meetings")


def test_backlog_project_dir_resolution(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[stories.backlog_md]\nproject_dir = "boards/work"\n')
    assert load_settings(tmp_path).backlog_project_dir == tmp_path.resolve() / "boards" / "work"
    (tmp_path / "config.toml").write_text('[stories.backlog_md]\nproject_dir = "~/boards"\n')
    assert load_settings(tmp_path).backlog_project_dir == Path("~/boards").expanduser()


def test_list_keys_accept_a_single_value_and_destinations_reject_unknown_ones(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[stories]\ndestinations = "backlog-md"\n[stories.backlog_md]\nlabels = "work"\n')
    s = load_settings(tmp_path)
    assert s.story_destinations == (StoryDestination.BACKLOG_MD,) and s.backlog_labels == ("work",)
    (tmp_path / "config.toml").write_text('[stories]\ndestinations = ["backlog-md", "trello"]\n')
    message = Err.INVALID_DESTINATION.format(value="trello", options=tuple(d.value for d in StoryDestination))
    with pytest.raises(ValueError, match=re.escape(message)):
        load_settings(tmp_path)


def test_the_repository_config_loads(tmp_path: Path):
    repo_config = Path(__file__).resolve().parents[2] / "config.toml"
    (tmp_path / "config.toml").write_text(repo_config.read_text(encoding="utf-8"))   # a copy: no .env loaded
    s = load_settings(tmp_path)
    assert s.backlog_project_dir == tmp_path.resolve()


def test_transcription_guard_defaults(tmp_path: Path):
    s = load_settings(tmp_path)
    assert s.whisper_max_context == 0 and s.max_loop_share == 0.10 and s.retry_on_loop and s.retry_vad
    assert s.vad_model_path is None   # VAD stays off on the first pass...
    assert s.retry_vad_model_path == s.models_dir / "ggml-silero-v5.1.2.bin"   # ...and is used by the retry


def test_transcription_guard_settings(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[transcription]\nmax_context = -1\nmax_loop_share = 0.25\nretry_on_loop = false\n')
    s = load_settings(tmp_path)
    assert s.whisper_max_context == -1 and s.max_loop_share == 0.25 and not s.retry_on_loop
    assert s.retry_vad_model_path is None
    (tmp_path / "config.toml").write_text('[transcription]\nretry_vad = false\n')
    assert load_settings(tmp_path).retry_vad_model_path is None


@pytest.mark.parametrize("value", ["0", "1.5", '"many"', "-0.1"])
def test_invalid_loop_share(tmp_path: Path, value: str):
    (tmp_path / "config.toml").write_text(f"[transcription]\nmax_loop_share = {value}\n")
    with pytest.raises(ValueError, match="max_loop_share"):
        load_settings(tmp_path)


def test_repository_config_turns_the_guard_on():
    s = load_settings(Path(__file__).resolve().parents[2])
    assert s.whisper_max_context == 0 and s.max_loop_share == 0.10 and s.retry_on_loop and s.retry_vad


def test_verification_defaults_and_settings(tmp_path: Path):
    s = load_settings(tmp_path)
    assert s.verify_enabled and s.verify_model == "claude-sonnet-5-5" and s.verify_cli_model == "sonnet" and s.verify_effort is Effort.MEDIUM
    (tmp_path / "config.toml").write_text('[verification]\nenabled = false\nmodel = "claude-opus-5-5"\ncli_model = "opus"\neffort = "HIGH"\n')
    s = load_settings(tmp_path)
    assert not s.verify_enabled and s.verify_model == "claude-opus-5-5" and s.verify_cli_model == "opus" and s.verify_effort is Effort.HIGH


def test_repository_config_turns_verification_on_with_sonnet():
    s = load_settings(Path(__file__).resolve().parents[2])
    assert s.verify_enabled and s.verify_cli_model == "sonnet" and s.verify_effort is Effort.MEDIUM


def test_ut060_speakers_are_on_by_default_and_the_flag_overrides(tmp_path: Path):
    assert load_settings(tmp_path).speakers_enabled is True
    (tmp_path / "config.toml").write_text("[speakers]\nenabled = false\n")
    assert load_settings(tmp_path).speakers_enabled is False
    assert load_settings(tmp_path).speakers_log == load_settings(tmp_path).log_dir / "speakers.log"


def test_the_repository_config_documents_the_speakers_section():
    s = load_settings(Path(__file__).resolve().parents[2])
    assert s.speakers_enabled is True
    assert "[speakers]" in (Path(__file__).resolve().parents[2] / "config.toml").read_text()


def test_a_config_without_activities_yields_the_documented_defaults(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[llm]\nmodel = "claude-sonnet-5-5"\n')
    s = load_settings(tmp_path)
    assert s.activities_enabled is True and s.activities_notify is True and s.activities_keep_versions == 50
    assert s.activities_cli_model == "opus" and s.activities_effort is Effort.MEDIUM
    assert s.activities_model == "claude-sonnet-5-5"   # the analyzer's model when [activities] sets none
    assert load_settings(tmp_path / "missing").activities_model == "claude-opus-5-5"


def test_every_activities_key_set_in_the_file_is_read(tmp_path: Path):
    (tmp_path / "config.toml").write_text(
        '[llm]\nmodel = "claude-sonnet-5-5"\n'
        '[activities]\nenabled = false\nmodel = "claude-opus-5-5"\ncli_model = "sonnet"\neffort = "HIGH"\nnotify = false\nkeep_versions = 7\n')
    s = load_settings(tmp_path)
    assert (s.activities_enabled, s.activities_model, s.activities_cli_model, s.activities_effort, s.activities_notify, s.activities_keep_versions) == (
        False, "claude-opus-5-5", "sonnet", Effort.HIGH, False, 7)


def test_an_activities_effort_outside_effort_is_rejected_like_the_other_sections(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[activities]\neffort = "ultra"\n')
    with pytest.raises(ValueError, match="activities.effort") as raised:
        load_settings(tmp_path)
    assert str(raised.value) == Err.INVALID_ACTIVITIES_EFFORT.format(value="ultra", options=tuple(e.value for e in Effort))


@pytest.mark.parametrize("value", ["0", "-3", '"many"'])
def test_keep_versions_must_be_a_whole_number_of_at_least_one(tmp_path: Path, value: str):
    (tmp_path / "config.toml").write_text(f"[activities]\nkeep_versions = {value}\n")
    with pytest.raises(ValueError, match="activities.keep_versions"):
        load_settings(tmp_path)


def test_the_repository_config_documents_the_activities_section_with_the_defaults():
    root = Path(__file__).resolve().parents[2]
    s = load_settings(root)
    assert "[activities]" in (root / "config.toml").read_text()
    assert (s.activities_enabled, s.activities_cli_model, s.activities_effort, s.activities_notify, s.activities_keep_versions) == (
        True, "opus", Effort.MEDIUM, True, 50)
    assert s.activities_model == s.llm_model


def test_config_tool_prints_the_activities_switch_and_writes_booleans_and_numbers(tmp_path: Path, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("config_tool", Path(__file__).resolve().parents[2] / "scripts" / "config_tool.py")
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    (tmp_path / "config.toml").write_text('[user]\nname = "Felipe"\n[activities]\nenabled = true\nkeep_versions = 50\nmodel = "x"\n')
    monkeypatch.setattr(tool, "PROJECT", tmp_path)

    tool.get()
    assert "activities_enabled=true" in capsys.readouterr().out.splitlines()
    tool.set_value("activities", "enabled", "false")
    tool.set_value("activities", "keep_versions", "20")
    tool.set_value("activities", "model", "claude-opus-5-5")
    tool.set_value("user", "name", "Ana")

    assert (tmp_path / "config.toml").read_text() == '[user]\nname = "Ana"\n[activities]\nenabled = false\nkeep_versions = 20\nmodel = "claude-opus-5-5"\n'
    s = load_settings(tmp_path)
    assert s.activities_enabled is False and s.activities_keep_versions == 20 and s.user_name == "Ana"
    tool.get()
    assert "activities_enabled=false" in capsys.readouterr().out.splitlines()


# language detection settings (docs/tasks/language-detection/_tests.md UT-020 to UT-026)
def test_ut020_language_defaults_to_auto_with_portuguese_and_english(tmp_path: Path):
    s = load_settings(tmp_path)
    assert s.language == "auto" and s.languages == ("pt", "en") and s.detects_language is True and s.fallback_language == "pt"


def test_ut021_a_fixed_language_turns_detection_off_and_is_its_own_fallback(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[transcription]\nlanguage = "en"\n')
    s = load_settings(tmp_path)
    assert s.detects_language is False and s.fallback_language == "en" and s.languages == ("pt", "en")


def test_ut022_the_fallback_is_the_first_of_languages(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[transcription]\nlanguages = ["en", "pt"]\n')
    assert load_settings(tmp_path).fallback_language == "en"


@pytest.mark.parametrize("value", ["pt-BR", "Portuguese", ""])
def test_ut023_an_invalid_language_stops_the_load_with_the_key_and_the_value(tmp_path: Path, value: str):
    (tmp_path / "config.toml").write_text(f'[transcription]\nlanguage = "{value}"\n')
    with pytest.raises(ValueError) as error:
        load_settings(tmp_path)
    assert str(error.value) == Err.INVALID_LANGUAGE.format(value=value)


@pytest.mark.parametrize("written", ["[]", '["auto"]', '["PT"]', "[1]"])
def test_ut024_an_invalid_languages_list_stops_the_load(tmp_path: Path, written: str):
    (tmp_path / "config.toml").write_text(f"[transcription]\nlanguages = {written}\n")
    with pytest.raises(ValueError) as error:
        load_settings(tmp_path)
    assert str(error.value) == Err.INVALID_LANGUAGES.format(value=eval(written))   # the value as written


def test_ut025_a_single_string_is_a_list_of_one_and_duplicates_keep_their_first_place(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[transcription]\nlanguages = "en"\n')
    assert load_settings(tmp_path).languages == ("en",)
    (tmp_path / "config.toml").write_text('[transcription]\nlanguages = ["pt", "en", "pt"]\n')
    assert load_settings(tmp_path).languages == ("pt", "en")


def test_ut025a_languages_is_validated_when_language_is_a_code_too(tmp_path: Path):
    (tmp_path / "config.toml").write_text('[transcription]\nlanguage = "pt"\nlanguages = []\n')
    with pytest.raises(ValueError) as error:
        load_settings(tmp_path)
    assert str(error.value) == Err.INVALID_LANGUAGES.format(value=[])


def test_ut026_the_repository_config_detects_between_portuguese_and_english():
    s = load_settings(Path(__file__).resolve().parents[2])
    assert s.language == "auto" and s.languages == ("pt", "en")
