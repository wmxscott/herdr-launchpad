"""Checks herdr-plugin.toml against the rules herdr applies when it links a plugin."""

from __future__ import annotations

import os
import re
import tomllib

import launchpad
import pytest
from conftest import ROOT

MANIFEST = tomllib.loads((ROOT / "herdr-plugin.toml").read_text())
PLUGIN_ID_RE = re.compile(r"[A-Za-z0-9:._-]{1,120}")
LOCAL_ID_RE = re.compile(r"[A-Za-z0-9:_-]{1,120}")
SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
PLATFORMS = {"linux", "macos", "windows"}
PLACEMENTS = {"overlay", "popup", "split", "tab", "zoomed"}
# Popup plugin panes and the CLI's --placement popup, --width and --height.
OLDEST_SUPPORTED_HERDR = (0, 7, 4)


def version_tuple(value):
    match = SEMVER_RE.fullmatch(value)
    assert match, value
    return tuple(int(part) for part in match.groups())


def test_metadata():
    assert PLUGIN_ID_RE.fullmatch(MANIFEST["id"])
    assert MANIFEST["id"] == launchpad.DEFAULT_PLUGIN_ID
    assert MANIFEST["name"].strip()
    assert MANIFEST["description"].strip()
    assert set(MANIFEST["platforms"]) <= PLATFORMS


def test_versions_agree():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert MANIFEST["version"] == launchpad.VERSION == pyproject["project"]["version"]
    version_tuple(MANIFEST["version"])
    assert version_tuple(MANIFEST["min_herdr_version"]) == OLDEST_SUPPORTED_HERDR


@pytest.mark.parametrize("kind", ["actions", "panes"])
def test_local_ids_are_valid_and_unique(kind):
    ids = [item["id"] for item in MANIFEST[kind]]
    assert all(LOCAL_ID_RE.fullmatch(i) for i in ids)
    assert len(ids) == len(set(ids))


def test_actions():
    actions = {action["id"]: action for action in MANIFEST["actions"]}
    assert set(actions) == {"open"} | {f"slot-{n}" for n in launchpad.SLOTS}
    assert actions["open"]["command"] == ["sh", "bin/launchpad", "open"]
    for n in launchpad.SLOTS:
        assert actions[f"slot-{n}"]["command"] == ["sh", "bin/launchpad", "slot", str(n)]
    for action in actions.values():
        assert action["title"].strip()
        assert action["contexts"] == ["workspace"]


def test_panes():
    panes = {pane["id"]: pane for pane in MANIFEST["panes"]}
    assert set(panes) == {"picker", "run"}
    for pane in panes.values():
        assert pane["title"].strip()
        assert pane["placement"] in PLACEMENTS
        for size in ("width", "height"):
            launchpad._size(pane[size], size)
    assert panes["picker"]["command"] == ["sh", "bin/launchpad", "picker"]
    assert panes["run"]["command"] == ["sh", "bin/launchpad", "run"]


def test_commands_point_at_shipped_files():
    for item in MANIFEST["actions"] + MANIFEST["panes"]:
        assert (ROOT / item["command"][1]).is_file()
    assert os.access(ROOT / "bin/launchpad", os.X_OK)


def test_no_unknown_manifest_fields():
    top = {"id", "name", "version", "min_herdr_version", "description", "platforms"}
    assert set(MANIFEST) <= top | {"actions", "panes"}
    for action in MANIFEST["actions"]:
        assert set(action) <= {"id", "title", "description", "contexts", "platforms", "command"}
    for pane in MANIFEST["panes"]:
        assert set(pane) <= {
            "id",
            "title",
            "description",
            "platforms",
            "placement",
            "width",
            "height",
            "command",
        }


def test_readme_documents_every_entry_setting():
    readme = (ROOT / "README.md").read_text()
    for key in launchpad.ENTRY_KEYS - {"colour"}:
        assert f"| `{key}` |" in readme, key
