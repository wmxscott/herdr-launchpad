from __future__ import annotations

from launchpad import Entry, key_label, slot_keys

HERDR_CONFIG = """
[keys]
prefix = "ctrl+a"

[[keys.command]]
key = "prefix+G"
type = "plugin_action"
command = "launchpad.slot-1"

[[keys.command]]
key = "prefix+V"
type = "plugin_action"
command = "slot-2"

[[keys.command]]
key = "prefix+x"
type = "plugin_action"
command = "launchpad.slot-1"

[[keys.command]]
key = "prefix+o"
type = "plugin_action"
command = "other-plugin.slot-3"

[[keys.command]]
key = "prefix+s"
type = "shell"
command = "launchpad.slot-4"

[[keys.command]]
key = "ctrl+L"
type = "plugin_action"
command = "launchpad.open"
"""


def test_slot_keys_reads_plugin_action_bindings(sandbox):
    sandbox.write_herdr_config(HERDR_CONFIG)
    assert slot_keys() == {1: "prefix+G", 2: "prefix+V"}


def test_slot_keys_follows_the_plugin_id(sandbox, monkeypatch):
    sandbox.write_herdr_config(HERDR_CONFIG)
    monkeypatch.setenv("HERDR_PLUGIN_ID", "other-plugin")
    assert slot_keys() == {2: "prefix+V", 3: "prefix+o"}


def test_slot_keys_tolerates_missing_or_broken_config(sandbox):
    assert slot_keys() == {}
    sandbox.write_herdr_config("[[keys.command]\n")
    assert slot_keys() == {}
    sandbox.write_herdr_config('keys = "nope"\n')
    assert slot_keys() == {}


def test_key_label():
    keys = {1: "prefix+G"}
    assert key_label(Entry("a", "a", ("a",), slot=1), keys) == "prefix+G"
    assert key_label(Entry("a", "a", ("a",), slot=1, key="F5"), keys) == "F5"
    assert key_label(Entry("a", "a", ("a",), slot=2), keys) == ""
    assert key_label(Entry("a", "a", ("a",)), keys) == ""
