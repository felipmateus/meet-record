from pathlib import Path

from teams_recorder.config import APP_SUPPORT_DIR, default_data_dir, is_icloud_synced, is_tcc_protected, load_settings
from teams_recorder.constants import Effort, LlmProvider, MicBackend


def test_load_settings_reads_toml_and_env(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config.toml").write_text(
        '[audio]\nmic_device = "USB Mic"\n[planner]\nretention_days = 7\n[llm]\neffort = "medium"\n'
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
    assert s.language == "pt" and s.plan_hour == 18 and s.retention_days == 30
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
    assert not defaults.stories_enabled
    assert defaults.story_guide_path == tmp_path.resolve() / "prompts" / "user_story_guide.md"

    (tmp_path / "config.toml").write_text('[stories]\nenabled = true\nguide = "docs/guia.md"\n')
    s = load_settings(tmp_path)
    assert s.stories_enabled and s.story_guide_path == tmp_path.resolve() / "docs" / "guia.md"

    (tmp_path / "config.toml").write_text('[stories]\nguide = "~/guia.md"\n')
    assert load_settings(tmp_path).story_guide_path == Path("~/guia.md").expanduser()
