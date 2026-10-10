import pytest
import typer

from teams_recorder.adapters.inbound.cli import _story_numbers


def test_story_numbers():
    assert _story_numbers(None) is None
    assert _story_numbers("1,3") == [1, 3]
    assert _story_numbers(" 2 , 2") == [2, 2]          # duplicates are dropped by the use case


@pytest.mark.parametrize("value", ["", "a", "1,,3", "0", "-1", "1;2"])
def test_invalid_story_numbers_stop_the_command(value):
    with pytest.raises(typer.Exit):
        _story_numbers(value)


@pytest.mark.parametrize("value", ["1_0", "+1", "١"])
def test_story_numbers_are_plain_ascii_digits(value):
    with pytest.raises(typer.Exit):
        _story_numbers(value)


def test_destination_problems_fail_the_doctor_only_with_auto_publish(tmp_path, monkeypatch, capsys):
    from teams_recorder.adapters.inbound.cli import _check_destinations
    from teams_recorder.config import load_settings
    from teams_recorder.messages import Cli

    (tmp_path / "config.toml").write_text('[stories]\ndestinations = ["backlog-md"]\npublish = false\n[stories.backlog_md]\nproject_dir = "nope"\n')
    assert _check_destinations(load_settings(tmp_path)) is True
    assert Cli.DESTINATION_LINE.format(mark=Cli.INFO, destination="backlog-md", state=Cli.DESTINATION_NOT_READY) in capsys.readouterr().out
    (tmp_path / "config.toml").write_text('[stories]\ndestinations = ["backlog-md"]\npublish = true\n[stories.backlog_md]\nproject_dir = "nope"\n')
    assert _check_destinations(load_settings(tmp_path)) is False
    assert Cli.MISSING_MARK in capsys.readouterr().out
