from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import launchpad
import pytest
from conftest import ROOT

CONFIG = """
theme = "dark"

[[entries]]
id = "lazygit"
title = "lazygit"
command = ["lazygit"]
width = "95%"
height = "90%"
slot = 1

[[entries]]
id = "prs"
title = "pull requests"
command = ["prs"]
width = "100%"
height = "80%"
slot = 2
session_env = "PR_TRACKER_SESSION_ID"
requires_session = true

[[entries]]
id = "shell"
title = "shell"
command = "exec sh"
"""

AGENT_CONTEXT = {
    "workspace_id": "w1",
    "tab_id": "w1:t1",
    "focused_pane_id": "w1:p2",
    "focused_pane_agent": "claude",
    "focused_pane_cwd": "/",
    "workspace_cwd": "/",
}
AGENTS = [
    {"pane_id": "w1:p1", "agent_session": {"value": "someone-else"}},
    {"pane_id": "w1:p2", "agent_session": {"source": "hook", "value": "session-123"}},
]


def pane_opens(sandbox):
    """Pane opens, with the one-off rows file path replaced by ROWS."""
    calls = [call for call in sandbox.herdr_calls() if call[:3] == ["plugin", "pane", "open"]]
    return [
        ["LAUNCHPAD_ROWS=ROWS" if arg.startswith("LAUNCHPAD_ROWS=") else arg for arg in call]
        for call in calls
    ]


def rows_file(sandbox):
    [call] = sandbox.herdr_calls()
    [path] = [arg.split("=", 1)[1] for arg in call if arg.startswith("LAUNCHPAD_ROWS=")]
    return Path(path)


def popup(entrypoint, width, height, *env):
    args = ["plugin", "pane", "open", "--plugin", "launchpad", "--entrypoint", entrypoint]
    args += ["--placement", "popup", "--width", str(width), "--height", str(height), "--focus"]
    for item in env:
        args += ["--env", item]
    return args


def test_open_sizes_the_picker(sandbox):
    sandbox.write_config(CONFIG)
    assert launchpad.main(["open"]) == 0
    assert pane_opens(sandbox) == [
        popup("picker", 36, 8, "LAUNCHPAD_SESSION=", "LAUNCHPAD_ROWS=ROWS")
    ]


def test_open_renders_the_rows_before_the_popup_opens(sandbox, monkeypatch):
    sandbox.write_config(CONFIG)
    monkeypatch.setenv("NO_COLOR", "1")
    assert launchpad.main(["open"]) == 0
    rows = rows_file(sandbox).read_text().splitlines()
    assert rows == ["• lazygit\tlazygit", "• shell\tshell"]
    assert rows_file(sandbox).parent == sandbox.state_dir


def test_open_only_asks_for_a_session_when_an_entry_uses_one(sandbox, monkeypatch):
    sandbox.write_config('[[entries]]\nid = "a"\ncommand = ["a"]\n')
    sandbox.spec(agents=AGENTS)
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps(AGENT_CONTEXT))
    assert launchpad.main(["open"]) == 0
    assert pane_opens(sandbox) == [popup("picker", 36, 8, "LAUNCHPAD_ROWS=ROWS")]


def test_open_hands_the_session_to_the_picker(sandbox, monkeypatch):
    sandbox.write_config(CONFIG)
    sandbox.spec(agents=AGENTS)
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps(AGENT_CONTEXT))
    assert launchpad.main(["open"]) == 0
    assert pane_opens(sandbox) == [
        popup("picker", 36, 8, "LAUNCHPAD_SESSION=session-123", "LAUNCHPAD_ROWS=ROWS")
    ]


def test_open_without_config_still_opens_the_picker(sandbox):
    assert launchpad.main(["open"]) == 0
    assert sandbox.herdr_calls() == [popup("picker", 72, 10)]


def test_open_reports_failures(sandbox):
    sandbox.spec(busy=1)
    assert launchpad.main(["open"]) == 1
    assert sandbox.herdr_calls()[-1][:3] == ["notification", "show", "launchpad"]


def test_slot_opens_the_entry(sandbox):
    sandbox.write_config(CONFIG)
    assert launchpad.main(["slot", "1"]) == 0
    assert sandbox.herdr_calls() == [popup("run", "95%", "90%", "LAUNCHPAD_ENTRY=lazygit")]


@pytest.mark.parametrize("slot", ["3", "0", "x"])
def test_slot_without_entry_notifies(sandbox, slot):
    sandbox.write_config(CONFIG)
    assert launchpad.main(["slot", slot]) != 0
    calls = sandbox.herdr_calls()
    assert len(calls) == 1
    assert calls[0][:3] == ["notification", "show", "launchpad"]


def test_slot_with_bad_config_notifies(sandbox):
    sandbox.write_config("theme = 3\n")
    assert launchpad.main(["slot", "1"]) == 1
    assert "theme must be" in sandbox.herdr_calls()[0][-1]


def test_session_entry_needs_an_agent(sandbox, monkeypatch):
    sandbox.write_config(CONFIG)
    sandbox.spec(agents=AGENTS)
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps({"focused_pane_id": "w1:p2"}))
    assert launchpad.main(["slot", "2"]) == 1
    assert "needs a pane running an agent session" in sandbox.herdr_calls()[-1][-1]


def test_session_entry_opens_from_an_agent_pane(sandbox, monkeypatch):
    sandbox.write_config(CONFIG)
    sandbox.spec(agents=AGENTS)
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps(AGENT_CONTEXT))
    assert launchpad.main(["slot", "2"]) == 0
    assert pane_opens(sandbox) == [
        popup("run", "100%", "80%", "LAUNCHPAD_ENTRY=prs", "LAUNCHPAD_SESSION=session-123")
    ]


def test_launch_uses_the_session_it_was_handed(sandbox, monkeypatch):
    sandbox.write_config(CONFIG)
    monkeypatch.setenv("LAUNCHPAD_SESSION", "from-picker")
    assert launchpad.main(["launch", "prs"]) == 0
    assert sandbox.herdr_calls() == [
        popup("run", "100%", "80%", "LAUNCHPAD_ENTRY=prs", "LAUNCHPAD_SESSION=from-picker")
    ]


def test_launch_waits_for_the_picker_to_close(sandbox):
    sandbox.write_config(CONFIG)
    sandbox.spec(busy=2)
    assert launchpad.main(["launch", "shell"]) == 0
    assert pane_opens(sandbox) == [popup("run", "80%", "80%", "LAUNCHPAD_ENTRY=shell")] * 3


def test_launch_unknown_entry(sandbox):
    sandbox.write_config(CONFIG)
    assert launchpad.main(["launch", "nope"]) == 1
    assert pane_opens(sandbox) == []


def test_agent_session(sandbox):
    sandbox.spec(agents=AGENTS)
    assert launchpad.agent_session(AGENT_CONTEXT) == "session-123"
    assert launchpad.agent_session({**AGENT_CONTEXT, "focused_pane_id": "w1:p9"}) is None


def test_agent_session_skips_herdr_without_an_agent(sandbox):
    assert launchpad.agent_session({"focused_pane_id": "w1:p2"}) is None
    assert sandbox.herdr_calls() == []


def test_agent_session_survives_herdr_failing(sandbox, monkeypatch):
    monkeypatch.setenv("HERDR_BIN_PATH", str(sandbox.bin / "missing"))
    assert launchpad.agent_session(AGENT_CONTEXT) is None


def test_run_environment(sandbox):
    sandbox.spec(agents=AGENTS)
    config = launchpad.parse_config(
        {
            "entries": [
                {
                    "id": "prs",
                    "command": ["prs"],
                    "env": {"EXTRA": "1"},
                    "session_env": "PR_TRACKER_SESSION_ID",
                }
            ]
        }
    )
    base = {
        "PATH": "/bin",
        "HERDR_ENV": "1",
        "HERDR_SOCKET_PATH": "/tmp/fake.sock",
        "HERDR_PLUGIN_ID": "launchpad",
        "HERDR_PLUGIN_CONTEXT_JSON": "{}",
        "LAUNCHPAD_ENTRY": "prs",
        "LAUNCHPAD_SESSION": "session-123",
        "LAUNCHPAD_ROWS": "/tmp/rows",
    }
    env = launchpad.run_environment(config.entries[0], AGENT_CONTEXT, base, "session-123")
    assert env == {
        "PATH": "/bin",
        "HERDR_ENV": "1",
        "HERDR_SOCKET_PATH": "/tmp/fake.sock",
        "HERDR_ACTIVE_WORKSPACE_ID": "w1",
        "HERDR_ACTIVE_TAB_ID": "w1:t1",
        "HERDR_ACTIVE_PANE_ID": "w1:p2",
        "HERDR_ACTIVE_PANE_CWD": "/",
        "EXTRA": "1",
        "PR_TRACKER_SESSION_ID": "session-123",
    }


def run_plugin(sandbox, *args, **env):
    return subprocess.run(
        ["sh", str(ROOT / "bin/launchpad"), *args],
        cwd=ROOT,
        env=sandbox.env(**env),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )


RECORDER = (
    "import json, os, sys; "
    "json.dump({'cwd': os.getcwd(), 'argv': sys.argv[1:], 'env': dict(os.environ)}, "
    "open(os.environ['OUT'], 'w'))"
)


def test_run_execs_the_entry_in_the_focused_pane_directory(sandbox, tmp_path):
    workdir = tmp_path / "project"
    workdir.mkdir()
    out = tmp_path / "out.json"
    sandbox.write_config(
        "[[entries]]\n"
        'id = "rec"\n'
        f"command = [{json.dumps(sys.executable)}, '-c', {json.dumps(RECORDER)}, 'one arg']\n"
        f"env = {{ OUT = {json.dumps(str(out))} }}\n"
        'session_env = "PR_TRACKER_SESSION_ID"\n'
    )
    sandbox.spec(agents=AGENTS)
    context = {**AGENT_CONTEXT, "focused_pane_cwd": str(workdir)}
    result = run_plugin(
        sandbox, "run", LAUNCHPAD_ENTRY="rec", HERDR_PLUGIN_CONTEXT_JSON=json.dumps(context)
    )
    assert result.returncode == 0, result.stderr
    seen = json.loads(out.read_text())
    assert seen["cwd"] == str(workdir.resolve())
    assert seen["argv"] == ["one arg"]
    assert seen["env"]["PWD"] == str(workdir)
    assert seen["env"]["PR_TRACKER_SESSION_ID"] == "session-123"
    assert seen["env"]["HERDR_ACTIVE_PANE_ID"] == "w1:p2"
    assert not [name for name in seen["env"] if name.startswith("HERDR_PLUGIN_")]
    assert "LAUNCHPAD_ENTRY" not in seen["env"]


def test_run_shell_string(sandbox, tmp_path):
    out = tmp_path / "out.txt"
    sandbox.write_config(f'[[entries]]\nid = "s"\ncommand = \'echo "$0 ok" > {out}\'\n')
    context = {"workspace_cwd": str(tmp_path)}
    result = run_plugin(
        sandbox, "run", LAUNCHPAD_ENTRY="s", HERDR_PLUGIN_CONTEXT_JSON=json.dumps(context)
    )
    assert result.returncode == 0, result.stderr
    assert out.read_text() == "sh ok\n"


def test_run_unknown_entry(sandbox):
    sandbox.write_config(CONFIG)
    result = run_plugin(sandbox, "run", LAUNCHPAD_ENTRY="nope")
    assert result.returncode == 1
    assert "no entry has id = 'nope'" in result.stderr


def test_run_missing_command(sandbox):
    sandbox.write_config('[[entries]]\nid = "x"\ncommand = ["no-such-command-here"]\n')
    result = run_plugin(sandbox, "run", LAUNCHPAD_ENTRY="x")
    assert result.returncode == 1
    assert "can't run no-such-command-here" in result.stderr


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_picker_launches_the_selection(sandbox):
    sandbox.write_config(CONFIG)
    sandbox.spec(busy=1)
    result = run_plugin(sandbox, "picker", FAKE_FZF_PICK="1")
    assert result.returncode == 0, result.stderr
    # prs needs an agent session, so the list is lazygit then shell.
    rows = sandbox.fzf_input.read_text().splitlines()
    assert [row.rsplit("\t", 1)[1] for row in rows] == ["lazygit", "shell"]
    assert "--ansi" in sandbox.fzf_args.read_text().splitlines()
    expected = popup("run", "80%", "80%", "LAUNCHPAD_ENTRY=shell")
    assert wait_for(lambda: expected in pane_opens(sandbox)[1:])


def test_picker_shows_session_entries_in_agent_panes(sandbox):
    sandbox.write_config(CONFIG)
    sandbox.spec(agents=AGENTS)
    result = run_plugin(sandbox, "picker", HERDR_PLUGIN_CONTEXT_JSON=json.dumps(AGENT_CONTEXT))
    assert result.returncode == 0, result.stderr
    rows = sandbox.fzf_input.read_text().splitlines()
    assert [row.rsplit("\t", 1)[1] for row in rows] == ["lazygit", "prs", "shell"]
    assert pane_opens(sandbox) == []


def test_picker_no_color(sandbox):
    sandbox.write_config(CONFIG)
    sandbox.write_herdr_config(
        '[[keys.command]]\nkey = "prefix+G"\ntype = "plugin_action"\ncommand = "launchpad.slot-1"\n'
    )
    result = run_plugin(sandbox, "picker", NO_COLOR="1")
    assert result.returncode == 0, result.stderr
    assert "--ansi" not in sandbox.fzf_args.read_text().splitlines()
    assert sandbox.fzf_input.read_text().splitlines()[0] == (
        "• lazygit" + " " * 8 + "prefix+G\tlazygit"
    )


def test_picker_without_config(sandbox):
    result = run_plugin(sandbox, "picker")
    assert result.returncode == 1
    assert "no config file yet" in result.stderr


def test_picker_without_fzf(sandbox):
    sandbox.write_config(CONFIG)
    (sandbox.bin / "fzf").unlink()
    result = run_plugin(sandbox, "picker", PATH=f"{sandbox.bin}:{sys.prefix}/bin:/usr/bin:/bin")
    assert result.returncode == 1
    assert "needs fzf" in result.stderr


def test_cli_basics(sandbox, capsys):
    assert launchpad.main(["--version"]) == 0
    assert capsys.readouterr().out == f"launchpad {launchpad.VERSION}\n"
    assert launchpad.main(["config"]) == 0
    assert capsys.readouterr().out == f"{sandbox.config_dir / 'config.toml'}\n"
    assert launchpad.main(["bogus"]) == 2
    assert launchpad.main([]) == 2


def test_open_counts_only_the_entries_it_will_show(sandbox, monkeypatch):
    entries = "".join(
        f'[[entries]]\nid = "e{n}"\ncommand = ["x"]\nrequires_session = true\n' for n in range(6)
    )
    sandbox.write_config(entries)
    sandbox.spec(agents=AGENTS)
    assert launchpad.main(["open"]) == 0
    monkeypatch.setenv("HERDR_PLUGIN_CONTEXT_JSON", json.dumps(AGENT_CONTEXT))
    assert launchpad.main(["open"]) == 0
    assert pane_opens(sandbox) == [
        popup("picker", 36, 8, "LAUNCHPAD_SESSION=", "LAUNCHPAD_ROWS=ROWS"),
        popup("picker", 36, 11, "LAUNCHPAD_SESSION=session-123", "LAUNCHPAD_ROWS=ROWS"),
    ]


def test_picker_shows_the_rows_open_rendered(sandbox, monkeypatch):
    sandbox.write_config(CONFIG)
    monkeypatch.setenv("NO_COLOR", "1")
    assert launchpad.main(["open"]) == 0
    rows = rows_file(sandbox)
    sandbox.config_dir.joinpath("config.toml").unlink()
    result = run_plugin(sandbox, "picker", LAUNCHPAD_ROWS=str(rows), LAUNCHPAD_SESSION="")
    assert result.returncode == 0, result.stderr
    assert sandbox.fzf_input.read_text().splitlines() == ["• lazygit\tlazygit", "• shell\tshell"]
    assert not rows.exists()
    assert len(sandbox.herdr_calls()) == 1


def test_picker_passes_the_session_on(sandbox):
    sandbox.write_config(CONFIG)
    rows = sandbox.state_dir / "rows.txt"
    rows.write_text("p\tprs\n")
    result = run_plugin(
        sandbox, "picker", LAUNCHPAD_ROWS=str(rows), LAUNCHPAD_SESSION="s-9", FAKE_FZF_PICK="0"
    )
    assert result.returncode == 0, result.stderr
    expected = popup("run", "100%", "80%", "LAUNCHPAD_ENTRY=prs", "LAUNCHPAD_SESSION=s-9")
    assert wait_for(lambda: expected in pane_opens(sandbox))
    assert not [call for call in sandbox.herdr_calls() if call[:2] == ["agent", "list"]]


@pytest.mark.parametrize(("handed", "expected"), [("s-9", "s-9"), ("", None)])
def test_run_uses_the_session_it_was_handed(sandbox, tmp_path, handed, expected):
    out = tmp_path / "out.json"
    sandbox.write_config(
        "[[entries]]\n"
        'id = "rec"\n'
        f"command = [{json.dumps(sys.executable)}, '-c', {json.dumps(RECORDER)}]\n"
        f"env = {{ OUT = {json.dumps(str(out))} }}\n"
        'session_env = "PR_TRACKER_SESSION_ID"\n'
    )
    sandbox.spec(agents=AGENTS)
    result = run_plugin(
        sandbox,
        "run",
        LAUNCHPAD_ENTRY="rec",
        LAUNCHPAD_SESSION=handed,
        HERDR_PLUGIN_CONTEXT_JSON=json.dumps(AGENT_CONTEXT),
    )
    assert result.returncode == 0, result.stderr
    env = json.loads(out.read_text())["env"]
    assert env.get("PR_TRACKER_SESSION_ID") == expected
    assert "LAUNCHPAD_SESSION" not in env
    assert sandbox.herdr_calls() == []


def test_shim_caches_the_interpreter(sandbox, tmp_path):
    cache = sandbox.state_dir / "python"
    result = run_plugin(sandbox, "--version")
    assert result.returncode == 0, result.stderr
    cached = cache.read_text().strip()
    assert Path(cached).is_absolute()
    assert os.access(cached, os.X_OK)

    marker = tmp_path / "used-cache"
    wrapper = tmp_path / "python-wrapper"
    wrapper.write_text(f'#!/bin/sh\ntouch {marker}\nexec {cached} "$@"\n')
    wrapper.chmod(0o755)
    cache.write_text(f"{wrapper}\n")
    result = run_plugin(sandbox, "--version")
    assert result.stdout == f"launchpad {launchpad.VERSION}\n"
    assert marker.exists()


def test_shim_ignores_a_stale_cache(sandbox, tmp_path):
    cache = sandbox.state_dir / "python"
    cache.write_text(f"{tmp_path / 'gone'}\n")
    result = run_plugin(sandbox, "--version")
    assert result.stdout == f"launchpad {launchpad.VERSION}\n"
    assert cache.read_text().strip() != str(tmp_path / "gone")
