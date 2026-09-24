from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import launchpad  # noqa: E402

# A stand-in for `herdr`. It logs every call and answers from a JSON spec:
#   {"agents": [...], "busy": N}
# `agent list` returns the agents; `plugin pane open` fails with "popup already
# open" for the first N calls. Nothing here can reach a running herdr.
FAKE_HERDR = """#!{python}
import json, os, sys

args = sys.argv[1:]
log_path = os.environ["FAKE_HERDR_LOG"]
with open(log_path, "a") as log:
    log.write(json.dumps({{"args": args}}) + "\\n")
try:
    with open(os.environ["FAKE_HERDR_SPEC"]) as f:
        spec = json.load(f)
except (KeyError, OSError, ValueError):
    spec = {{}}

if args[:2] == ["agent", "list"]:
    print(json.dumps({{"id": "cli:agent:list", "result": {{"agents": spec.get("agents", [])}}}}))
elif args[:3] == ["plugin", "pane", "open"]:
    with open(log_path) as log:
        opens = sum(1 for line in log if '"open"' in line)
    if opens <= spec.get("busy", 0):
        sys.stderr.write(json.dumps({{"error": {{"code": "plugin_pane_open_failed",
                                                "message": "popup already open"}}}}) + "\\n")
        sys.exit(1)
    print(json.dumps({{"result": {{"type": "ok"}}}}))
elif args[:2] == ["notification", "show"]:
    print(json.dumps({{"result": {{"type": "ok"}}}}))
else:
    sys.stderr.write("fake herdr: unexpected " + " ".join(args) + "\\n")
    sys.exit(2)
"""

# A stand-in for `fzf` that records its input and picks line FAKE_FZF_PICK.
FAKE_FZF = """#!{python}
import os, sys

lines = sys.stdin.read().splitlines()
with open(os.environ["FAKE_FZF_INPUT"], "w") as f:
    f.write("\\n".join(lines))
with open(os.environ["FAKE_FZF_ARGS"], "w") as f:
    f.write("\\n".join(sys.argv[1:]))
pick = os.environ.get("FAKE_FZF_PICK", "")
if pick:
    print(lines[int(pick)])
"""


@dataclass
class Sandbox:
    home: Path
    bin: Path
    config_dir: Path
    herdr_config: Path
    herdr_log: Path
    herdr_spec: Path
    fzf_input: Path
    fzf_args: Path

    def write_config(self, text: str) -> Path:
        path = self.config_dir / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def write_herdr_config(self, text: str) -> None:
        self.herdr_config.write_text(text, encoding="utf-8")

    def spec(self, **spec) -> None:
        self.herdr_spec.write_text(json.dumps(spec))

    def herdr_calls(self) -> list[list[str]]:
        if not self.herdr_log.exists():
            return []
        return [json.loads(line)["args"] for line in self.herdr_log.read_text().splitlines()]

    def env(self, **extra: str) -> dict[str, str]:
        """A from-scratch environment for running the plugin as herdr would."""
        env = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "PATH": os.pathsep.join(
                [str(self.bin), str(Path(sys.executable).parent), "/usr/bin", "/bin"]
            ),
            "HERDR_BIN_PATH": str(self.bin / "herdr"),
            "HERDR_PLUGIN_ID": "launchpad",
            "HERDR_PLUGIN_ROOT": str(ROOT),
            "HERDR_PLUGIN_CONFIG_DIR": str(self.config_dir),
            "FAKE_HERDR_LOG": str(self.herdr_log),
            "FAKE_HERDR_SPEC": str(self.herdr_spec),
            "FAKE_FZF_INPUT": str(self.fzf_input),
            "FAKE_FZF_ARGS": str(self.fzf_args),
        }
        env.update(extra)
        return env


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    for name in list(os.environ):
        if name.startswith(("HERDR_", "XDG_", "FAKE_", "LAUNCHPAD_")) or name == "NO_COLOR":
            monkeypatch.delenv(name)

    home = tmp_path / "home"
    herdr_dir = home / ".config" / "herdr"
    config_dir = herdr_dir / "plugins" / "config" / "launchpad"
    config_dir.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in (("herdr", FAKE_HERDR), ("fzf", FAKE_FZF)):
        path = bin_dir / name
        path.write_text(script.format(python=sys.executable))
        path.chmod(0o755)

    box = Sandbox(
        home=home,
        bin=bin_dir,
        config_dir=config_dir,
        herdr_config=herdr_dir / "config.toml",
        herdr_log=tmp_path / "herdr.log",
        herdr_spec=tmp_path / "herdr-spec.json",
        fzf_input=tmp_path / "fzf-input.txt",
        fzf_args=tmp_path / "fzf-args.txt",
    )
    for name, value in box.env().items():
        if name != "PATH":
            monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(launchpad, "macos_appearance", lambda: None)
    return box
