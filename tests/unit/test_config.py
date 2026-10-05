from pathlib import Path

from teams_recorder.config import default_data_dir, is_icloud_synced, load_settings


def test_load_settings_reads_toml_and_env(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config.toml").write_text(
        '[audio]\nmic_device = "USB Mic"\n[planner]\nretention_days = 7\n[llm]\neffort = "medium"\n'
    )
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test-123\n")

    s = load_settings(tmp_path)

    assert s.project_dir == tmp_path.resolve()
    assert s.data_dir == tmp_path.resolve() / "data"
    assert s.mic_device == "USB Mic"
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
    (tmp_path / "config.toml").write_text('[paths]\ndata_dir = "~/outro/lugar"\n')
    assert load_settings(tmp_path).data_dir == Path("~/outro/lugar").expanduser()


def test_icloud_detection(tmp_path: Path):
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Documents" / "proj"
    icloud.mkdir(parents=True)
    assert is_icloud_synced(icloud)
    assert not is_icloud_synced(tmp_path)
    assert default_data_dir(icloud) == Path.home() / "Library" / "Application Support" / "teams-recorder"
    assert default_data_dir(tmp_path) == tmp_path / "data"
