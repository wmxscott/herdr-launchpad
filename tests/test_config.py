from __future__ import annotations

import tomllib
from pathlib import Path

import launchpad
import pytest
from conftest import ROOT
from launchpad import ConfigError, Entry, parse_config


def entry(**fields) -> dict:
    return {"id": "tool", "command": ["tool"], **fields}


def test_example_config_parses():
    config = parse_config(tomllib.loads((ROOT / "examples/config.toml").read_text()))
    assert [e.id for e in config.entries] == ["lazygit", "nvim", "gh-dash", "btop", "shell"]
    assert config.slot(1).id == "lazygit"
    assert config.entry("shell").command == 'exec "${SHELL:-sh}"'


def test_defaults():
    config = parse_config({"entries": [entry()]})
    assert config.theme == "auto"
    assert config.picker_width is None
    assert config.entries == (Entry(id="tool", title="tool", command=("tool",)),)
    tool = config.entries[0]
    assert (tool.icon, tool.color, tool.width, tool.height) == ("•", "blue", "80%", "80%")
    assert tool.slot is None and tool.env == {} and not tool.requires_session


def test_every_field():
    config = parse_config(
        {
            "theme": "light",
            "picker": {"width": 50, "height": "40%"},
            "entries": [
                entry(
                    title="The tool",
                    command="tool --flag | less",
                    icon="T",
                    colour="#A1b2C3",
                    width=120,
                    height="50%",
                    slot=9,
                    key="alt+t",
                    env={"TOOL_MODE": "fast"},
                    session_env="TOOL_SESSION",
                    requires_session=True,
                )
            ],
        }
    )
    assert (config.theme, config.picker_width, config.picker_height) == ("light", 50, "40%")
    assert config.entries[0] == Entry(
        id="tool",
        title="The tool",
        command="tool --flag | less",
        icon="T",
        color="#A1b2C3",
        width=120,
        height="50%",
        slot=9,
        key="alt+t",
        env={"TOOL_MODE": "fast"},
        session_env="TOOL_SESSION",
        requires_session=True,
    )


def test_empty_config_has_no_entries():
    assert parse_config({}).entries == ()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"colour_scheme": "dark"}, "unknown setting 'colour_scheme'"),
        ({"theme": "blue"}, "theme must be"),
        ({"picker": {"width": 0}}, "[picker] width must be"),
        ({"picker": {"depth": 3}}, "[picker]: unknown setting 'depth'"),
        ({"entries": {"id": "x"}}, "entries must be an array"),
        ({"entries": [{"command": ["x"]}]}, "entry 1: id is required"),
        ({"entries": [entry(id="has.dot")]}, "entry 1: id is required"),
        ({"entries": [entry(colr="red")]}, "entry 'tool': unknown setting 'colr'"),
        ({"entries": [entry(command=[])]}, "command is required"),
        ({"entries": [entry(command="  ")]}, "command is required"),
        ({"entries": [entry(command=["tool", 3])]}, "command is required"),
        ({"entries": [{"id": "tool"}]}, "command is required"),
        ({"entries": [entry(title="")]}, "title must be a non-empty string"),
        ({"entries": [entry(color="chartreuse")]}, "color must be"),
        ({"entries": [entry(color="#12345")]}, "color must be"),
        ({"entries": [entry(color="red", colour="blue")]}, "not both"),
        ({"entries": [entry(width="80")]}, "width must be"),
        ({"entries": [entry(width="0%")]}, "width must be"),
        ({"entries": [entry(height="101%")]}, "height must be"),
        ({"entries": [entry(height=True)]}, "height must be"),
        ({"entries": [entry(slot=0)]}, "slot must be a number from 1 to 9"),
        ({"entries": [entry(slot=10)]}, "slot must be a number from 1 to 9"),
        ({"entries": [entry(slot=True)]}, "slot must be a number from 1 to 9"),
        ({"entries": [entry(env={"A": 1})]}, "env must be a table of strings"),
        ({"entries": [entry(env={"1A": "x"})]}, "env must be a table of strings"),
        ({"entries": [entry(session_env="NOT VALID")]}, "session_env must be"),
        ({"entries": [entry(requires_session="yes")]}, "requires_session must be true or false"),
        ({"entries": [entry(), entry()]}, "two entries have id 'tool'"),
        (
            {"entries": [entry(slot=2), entry(id="other", slot=2)]},
            "entries 'tool' and 'other' both use slot 2",
        ),
    ],
)
def test_rejects(data, message):
    with pytest.raises(ConfigError) as err:
        parse_config(data)
    assert message in str(err.value)


def test_load_config_missing_file_says_where(sandbox):
    with pytest.raises(ConfigError) as err:
        launchpad.load_config()
    assert str(sandbox.config_dir / "config.toml") in str(err.value)
    assert "no config file yet" in str(err.value)


def test_load_config_reports_toml_errors_with_path(sandbox):
    path = sandbox.write_config("[[entries]\n")
    with pytest.raises(ConfigError) as err:
        launchpad.load_config()
    assert str(err.value).startswith(f"{path}: ")


def test_load_config_reports_bad_values_with_path(sandbox):
    path = sandbox.write_config('[[entries]]\nid = "x"\n')
    with pytest.raises(ConfigError) as err:
        launchpad.load_config()
    assert str(err.value) == f"{path}: entry 'x': " + (
        'command is required, as ["argv", "list"] or a "shell string"'
    )


def test_config_path_prefers_herdr_plugin_config_dir(sandbox, monkeypatch, tmp_path):
    monkeypatch.setenv("HERDR_PLUGIN_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert launchpad.config_path() == tmp_path / "elsewhere" / "config.toml"


def test_config_path_falls_back_to_xdg(sandbox, monkeypatch, tmp_path):
    monkeypatch.delenv("HERDR_PLUGIN_CONFIG_DIR")
    monkeypatch.setenv("HERDR_PLUGIN_ID", "renamed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert launchpad.config_path() == tmp_path / "xdg/herdr/plugins/config/renamed/config.toml"


def test_config_path_without_xdg_uses_home(sandbox, monkeypatch):
    monkeypatch.delenv("HERDR_PLUGIN_CONFIG_DIR")
    monkeypatch.delenv("HERDR_PLUGIN_ID")
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert launchpad.config_path() == (
        sandbox.home / ".config/herdr/plugins/config/launchpad/config.toml"
    )


def test_herdr_config_path(sandbox, monkeypatch, tmp_path):
    assert launchpad.herdr_config_path() == sandbox.herdr_config
    monkeypatch.setenv("HERDR_CONFIG_PATH", str(tmp_path / "custom.toml"))
    assert launchpad.herdr_config_path() == tmp_path / "custom.toml"
    monkeypatch.delenv("HERDR_CONFIG_PATH")
    monkeypatch.delenv("HERDR_PLUGIN_CONFIG_DIR")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert launchpad.herdr_config_path() == Path(tmp_path) / "herdr" / "config.toml"
