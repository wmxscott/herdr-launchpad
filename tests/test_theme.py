from __future__ import annotations

import sys

import launchpad
from launchpad import resolve_theme

REAL_MACOS_APPEARANCE = launchpad.macos_appearance


def write_trigger(base, value):
    path = base / "theme-monitor" / "theme-change.trigger"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n")


def test_pinned_theme_wins(sandbox):
    write_trigger(sandbox.home / ".local/share", "dark")
    assert resolve_theme("light") == "light"
    assert resolve_theme("dark") == "dark"


def test_theme_monitor_trigger(sandbox):
    write_trigger(sandbox.home / ".local/share", "light")
    assert resolve_theme() == "light"


def test_xdg_data_home_trigger_comes_first(sandbox, monkeypatch, tmp_path):
    write_trigger(sandbox.home / ".local/share", "light")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    write_trigger(tmp_path / "data", "dark")
    assert resolve_theme() == "dark"


def test_unreadable_trigger_falls_back_to_macos(sandbox, monkeypatch):
    write_trigger(sandbox.home / ".local/share", "sepia")
    monkeypatch.setattr(launchpad, "macos_appearance", lambda: "light")
    assert resolve_theme() == "light"


def test_falls_back_to_dark(sandbox):
    assert resolve_theme() == "dark"


def fake_defaults(sandbox, stdout, code):
    path = sandbox.bin / "defaults"
    path.write_text(f"#!/bin/sh\nprintf '{stdout}'\nexit {code}\n")
    path.chmod(0o755)


def test_macos_appearance_dark(sandbox, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_defaults(sandbox, "Dark\\n", 0)
    assert REAL_MACOS_APPEARANCE() == "dark"


def test_macos_appearance_light_when_key_missing(sandbox, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_defaults(sandbox, "", 1)
    assert REAL_MACOS_APPEARANCE() == "light"


def test_macos_appearance_elsewhere(sandbox, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert REAL_MACOS_APPEARANCE() is None
