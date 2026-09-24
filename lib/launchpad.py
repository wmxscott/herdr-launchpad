"""Launchpad: an icon picker and keybindings that open your own tools in herdr popups.

herdr plugin manifests are static, so the manifest declares one generic popup
pane (`run`) and nine numbered actions (`slot-1` .. `slot-9`). What each of
those opens comes from the user's config file in the plugin config directory.

Subcommands, each wired up in herdr-plugin.toml:

  open         action: open the picker popup, sized to fit the entries
  slot N       action: open the entry with `slot = N`
  picker       pane:   the fzf icon picker
  run          pane:   exec the entry named by LAUNCHPAD_ENTRY
  launch ID    helper: open entry ID once the picker's popup has closed
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "0.1.0"
DEFAULT_PLUGIN_ID = "launchpad"
CONFIG_NAME = "config.toml"
SLOTS = range(1, 10)
ENTRY_ENV = "LAUNCHPAD_ENTRY"
README = "https://github.com/wmxscott/herdr-launchpad#configuration"

ID_RE = re.compile(r"[A-Za-z0-9_-]+")
ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
HEX_RE = re.compile(r"#([0-9a-fA-F]{6})")

# Catppuccin Latte and Macchiato.
LATTE = {
    "text": (76, 79, 105),
    "overlay0": (156, 160, 176),
    "rosewater": (220, 138, 120),
    "flamingo": (221, 120, 120),
    "pink": (234, 118, 203),
    "mauve": (136, 57, 239),
    "red": (210, 15, 57),
    "maroon": (230, 69, 83),
    "peach": (254, 100, 11),
    "yellow": (223, 142, 29),
    "green": (64, 160, 43),
    "teal": (23, 146, 153),
    "sky": (4, 165, 229),
    "sapphire": (32, 159, 181),
    "blue": (30, 102, 245),
    "lavender": (114, 135, 253),
}
MACCHIATO = {
    "text": (202, 211, 245),
    "overlay0": (110, 115, 141),
    "rosewater": (244, 219, 214),
    "flamingo": (240, 198, 198),
    "pink": (245, 189, 230),
    "mauve": (198, 160, 246),
    "red": (237, 135, 150),
    "maroon": (238, 153, 160),
    "peach": (245, 169, 127),
    "yellow": (238, 212, 159),
    "green": (166, 218, 149),
    "teal": (139, 213, 202),
    "sky": (145, 215, 227),
    "sapphire": (125, 196, 228),
    "blue": (138, 173, 244),
    "lavender": (183, 189, 248),
}
COLOR_NAMES = frozenset(LATTE) - {"text", "overlay0"}

RESET = "\x1b[0m"
KEY_GAP = 8
PICKER_CHROME_WIDTH = 5  # popup border (2), terminal scrollbar column (1), fzf gutter (2)
PICKER_CHROME_HEIGHT = 5  # popup border (2), prompt, separator, header
PICKER_MIN_WIDTH = 36
PICKER_MIN_HEIGHT = 8
POPUP_RETRY_SECONDS = 3.0

ENTRY_KEYS = {
    "id",
    "title",
    "command",
    "icon",
    "color",
    "colour",
    "width",
    "height",
    "slot",
    "key",
    "env",
    "session_env",
    "requires_session",
}
TOP_KEYS = {"theme", "picker", "entries"}
PICKER_KEYS = {"width", "height"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    command: tuple[str, ...] | str
    icon: str = "•"
    color: str = "blue"
    width: int | str = "80%"
    height: int | str = "80%"
    slot: int | None = None
    key: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    session_env: str | None = None
    requires_session: bool = False


@dataclass(frozen=True)
class Config:
    entries: tuple[Entry, ...] = ()
    theme: str = "auto"
    picker_width: int | str | None = None
    picker_height: int | str | None = None

    def entry(self, entry_id: str) -> Entry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def slot(self, number: int) -> Entry | None:
        return next((e for e in self.entries if e.slot == number), None)


# --- paths -----------------------------------------------------------------


def plugin_id() -> str:
    return os.environ.get("HERDR_PLUGIN_ID") or DEFAULT_PLUGIN_ID


def herdr_config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "herdr"


def config_path() -> Path:
    plugin_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if plugin_dir:
        return Path(plugin_dir) / CONFIG_NAME
    return herdr_config_home() / "plugins" / "config" / plugin_id() / CONFIG_NAME


def herdr_config_path() -> Path:
    explicit = os.environ.get("HERDR_CONFIG_PATH")
    if explicit:
        return Path(explicit)
    plugin_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if plugin_dir:
        # <herdr config dir>/plugins/config/<plugin id>
        return Path(plugin_dir).parents[2] / "config.toml"
    return herdr_config_home() / "config.toml"


# --- config ----------------------------------------------------------------


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"no config file yet. Create {path}\nSee {README}") from None
    except OSError as err:
        raise ConfigError(f"can't read {path}: {err.strerror}") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{path}: {err}") from None
    try:
        return parse_config(data)
    except ConfigError as err:
        raise ConfigError(f"{path}: {err}") from None


def parse_config(data: dict) -> Config:
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise ConfigError(f"unknown setting {unknown[0]!r}")

    theme = data.get("theme", "auto")
    if theme not in ("auto", "dark", "light"):
        raise ConfigError('theme must be "auto", "dark" or "light"')

    picker = data.get("picker", {})
    if not isinstance(picker, dict):
        raise ConfigError("[picker] must be a table")
    unknown = sorted(set(picker) - PICKER_KEYS)
    if unknown:
        raise ConfigError(f"[picker]: unknown setting {unknown[0]!r}")
    picker_width = _size(picker["width"], "[picker] width") if "width" in picker else None
    picker_height = _size(picker["height"], "[picker] height") if "height" in picker else None

    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ConfigError("entries must be an array of tables: [[entries]]")
    entries = [_entry(raw, index) for index, raw in enumerate(raw_entries, 1)]

    seen_ids: set[str] = set()
    seen_slots: dict[int, str] = {}
    for entry in entries:
        if entry.id in seen_ids:
            raise ConfigError(f"two entries have id {entry.id!r}")
        seen_ids.add(entry.id)
        if entry.slot is not None:
            if entry.slot in seen_slots:
                other = seen_slots[entry.slot]
                raise ConfigError(f"entries {other!r} and {entry.id!r} both use slot {entry.slot}")
            seen_slots[entry.slot] = entry.id

    return Config(
        entries=tuple(entries),
        theme=theme,
        picker_width=picker_width,
        picker_height=picker_height,
    )


def _entry(raw: object, index: int) -> Entry:
    where = f"entry {index}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a table")
    entry_id = raw.get("id")
    if isinstance(entry_id, str) and ID_RE.fullmatch(entry_id):
        where = f"entry {entry_id!r}"
    else:
        raise ConfigError(f"{where}: id is required and may use letters, digits, - and _")

    unknown = sorted(set(raw) - ENTRY_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown setting {unknown[0]!r}")

    kwargs: dict = {"id": entry_id}
    kwargs["title"] = _string(raw.get("title", entry_id), f"{where}: title")
    kwargs["command"] = _command(raw.get("command"), where)

    if "icon" in raw:
        kwargs["icon"] = _string(raw["icon"], f"{where}: icon")
    if "color" in raw and "colour" in raw:
        raise ConfigError(f"{where}: set color or colour, not both")
    color = raw.get("color", raw.get("colour"))
    if color is not None:
        kwargs["color"] = _color(color, where)
    if "width" in raw:
        kwargs["width"] = _size(raw["width"], f"{where}: width")
    if "height" in raw:
        kwargs["height"] = _size(raw["height"], f"{where}: height")

    if "slot" in raw:
        slot = raw["slot"]
        if isinstance(slot, bool) or not isinstance(slot, int) or slot not in SLOTS:
            raise ConfigError(f"{where}: slot must be a number from 1 to 9")
        kwargs["slot"] = slot
    if "key" in raw:
        kwargs["key"] = _string(raw["key"], f"{where}: key")

    env = raw.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and ENV_NAME_RE.fullmatch(k) and isinstance(v, str)
        for k, v in env.items()
    ):
        raise ConfigError(f'{where}: env must be a table of strings, like {{ NAME = "value" }}')
    kwargs["env"] = dict(env)

    if "session_env" in raw:
        name = raw["session_env"]
        if not isinstance(name, str) or not ENV_NAME_RE.fullmatch(name):
            raise ConfigError(f"{where}: session_env must be an environment variable name")
        kwargs["session_env"] = name
    if "requires_session" in raw:
        if not isinstance(raw["requires_session"], bool):
            raise ConfigError(f"{where}: requires_session must be true or false")
        kwargs["requires_session"] = raw["requires_session"]

    return Entry(**kwargs)


def _string(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{what} must be a non-empty string")
    return value


def _command(value: object, where: str) -> tuple[str, ...] | str:
    if isinstance(value, str) and value.strip():
        return value
    if (
        isinstance(value, list)
        and value
        and all(isinstance(arg, str) for arg in value)
        and value[0].strip()
    ):
        return tuple(value)
    raise ConfigError(f'{where}: command is required, as ["argv", "list"] or a "shell string"')


def _color(value: object, where: str) -> str:
    if isinstance(value, str) and (value in COLOR_NAMES or HEX_RE.fullmatch(value)):
        return value
    names = ", ".join(sorted(COLOR_NAMES))
    raise ConfigError(f'{where}: color must be "#rrggbb" or one of {names}')


def _size(value: object, what: str) -> int | str:
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535:
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"(\d{1,3})%", value)
        if match and 1 <= int(match[1]) <= 100:
            return value
    raise ConfigError(f'{what} must be a number of cells or a percentage like "80%"')


# --- key labels ------------------------------------------------------------


def slot_keys(herdr_config: Path | None = None, pid: str | None = None) -> dict[int, str]:
    """Slot number -> the key herdr's config.toml binds to that slot's action."""
    herdr_config = herdr_config or herdr_config_path()
    pid = pid or plugin_id()
    try:
        data = tomllib.loads(herdr_config.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}
    keys = data.get("keys", {})
    commands = keys.get("command", []) if isinstance(keys, dict) else []
    pattern = re.compile(rf"(?:{re.escape(pid)}\.)?slot-([1-9])")
    labels: dict[int, str] = {}
    for command in commands if isinstance(commands, list) else []:
        if not isinstance(command, dict) or command.get("type") != "plugin_action":
            continue
        match = pattern.fullmatch(str(command.get("command", "")))
        key = command.get("key")
        if match and isinstance(key, str):
            labels.setdefault(int(match[1]), key)
    return labels


def key_label(entry: Entry, keys: dict[int, str]) -> str:
    if entry.key is not None:
        return entry.key
    if entry.slot is not None:
        return keys.get(entry.slot, "")
    return ""


# --- theme -----------------------------------------------------------------


def theme_trigger_paths() -> list[Path]:
    paths = []
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        paths.append(Path(xdg) / "theme-monitor" / "theme-change.trigger")
    paths.append(Path.home() / ".local" / "share" / "theme-monitor" / "theme-change.trigger")
    return paths


def macos_appearance() -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # The key only exists in dark mode.
    return "dark" if result.stdout.strip().lower() == "dark" else "light"


def resolve_theme(setting: str = "auto") -> str:
    if setting in ("dark", "light"):
        return setting
    for path in theme_trigger_paths():
        try:
            value = path.read_text(encoding="utf-8").strip().lower()
        except (OSError, UnicodeDecodeError):
            continue
        if value in ("dark", "light"):
            return value
    return macos_appearance() or "dark"


def palette_for(theme: str) -> dict[str, tuple[int, int, int]]:
    return MACCHIATO if theme == "dark" else LATTE


# --- rendering -------------------------------------------------------------


def sgr(rgb: tuple[int, int, int], bold: bool = False, dim: bool = False) -> str:
    attrs = []
    if bold:
        attrs.append("1")
    if dim:
        attrs.append("2")
    attrs.append(f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}")
    return f"\x1b[{';'.join(attrs)}m"


def color_rgb(color: str, palette: dict[str, tuple[int, int, int]]) -> tuple[int, int, int]:
    match = HEX_RE.fullmatch(color)
    if match:
        value = match[1]
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return palette[color]


def cell_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def row_layout(entries: list[Entry], keys: dict[int, str]) -> tuple[int, int, int]:
    """Column widths: (icon, title, key)."""
    icon = max((cell_width(e.icon) for e in entries), default=1)
    title = max((cell_width(e.title) for e in entries), default=0)
    key = max((cell_width(key_label(e, keys)) for e in entries), default=0)
    return icon, title, key


def render_rows(
    entries: list[Entry],
    keys: dict[int, str],
    palette: dict[str, tuple[int, int, int]],
    color: bool = True,
) -> list[str]:
    """One fzf input line per entry: the visible row, a tab, then the entry id."""
    icon_w, title_w, _ = row_layout(entries, keys)
    rows = []
    for entry in entries:
        icon = entry.icon + " " * (icon_w - cell_width(entry.icon))
        pad = " " * (title_w - cell_width(entry.title) + KEY_GAP)
        key = key_label(entry, keys)
        if color:
            icon = f"{sgr(color_rgb(entry.color, palette), bold=True)}{icon}{RESET}"
            title = f"{sgr(palette['text'], bold=True)}{entry.title}{RESET}"
            key = f"{sgr(palette['overlay0'], dim=True)}{key}{RESET}" if key else ""
        else:
            title = entry.title
        rows.append(f"{icon} {title}{pad}{key}".rstrip() + f"\t{entry.id}")
    return rows


def picker_size(
    config: Config, keys: dict[int, str], entries: list[Entry] | None = None
) -> tuple[int | str, int | str]:
    entries = list(config.entries) if entries is None else entries
    icon_w, title_w, key_w = row_layout(entries, keys)
    content = icon_w + 1 + title_w + KEY_GAP + key_w
    width = max(PICKER_MIN_WIDTH, content + PICKER_CHROME_WIDTH)
    height = max(PICKER_MIN_HEIGHT, len(entries) + PICKER_CHROME_HEIGHT)
    return config.picker_width or width, config.picker_height or height


# --- herdr -----------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def herdr(*args: str, timeout: float = 5) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [herdr_bin(), *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as err:
        return subprocess.CompletedProcess([herdr_bin(), *args], 127, "", str(err))


def plugin_context() -> dict:
    try:
        context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    except ValueError:
        return {}
    return context if isinstance(context, dict) else {}


def agent_session(context: dict) -> str | None:
    """The session id of the agent in the pane that had focus when herdr ran us.

    A popup leaves herdr's plugin context on the tiled pane underneath it, so
    this works from the picker and run popups as well as from actions.
    """
    pane_id = context.get("focused_pane_id")
    if not pane_id or not context.get("focused_pane_agent"):
        return None
    result = herdr("agent", "list")
    if result.returncode != 0:
        return None
    try:
        agents = json.loads(result.stdout)["result"]["agents"]
    except (ValueError, KeyError, TypeError):
        return None
    for agent in agents:
        if isinstance(agent, dict) and agent.get("pane_id") == pane_id:
            session = agent.get("agent_session") or {}
            value = session.get("value") if isinstance(session, dict) else None
            return value or None
    return None


def open_popup(
    entrypoint: str,
    width: int | str,
    height: int | str,
    env: dict[str, str] | None = None,
    wait: float = 0.0,
) -> tuple[bool, str]:
    """Open one of this plugin's panes as a popup.

    herdr allows one popup at a time, so with `wait` this keeps retrying
    while another popup, such as the picker that asked for this one, closes.
    """
    args = [
        "plugin",
        "pane",
        "open",
        "--plugin",
        plugin_id(),
        "--entrypoint",
        entrypoint,
        "--placement",
        "popup",
        "--width",
        str(width),
        "--height",
        str(height),
        "--focus",
    ]
    for name, value in (env or {}).items():
        args += ["--env", f"{name}={value}"]
    deadline = time.monotonic() + wait
    while True:
        result = herdr(*args)
        if result.returncode == 0:
            return True, ""
        message = (result.stderr or result.stdout).strip()
        if "popup already open" not in message or time.monotonic() >= deadline:
            return False, message
        time.sleep(0.05)


def notify(message: str) -> None:
    print(f"launchpad: {message}", file=sys.stderr)
    herdr("notification", "show", "launchpad", "--body", message)


# --- commands --------------------------------------------------------------


def wait_for_key() -> None:
    if not sys.stdin.isatty():
        return
    print("\npress any key to close", end="", flush=True)
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            os.read(fd, 1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    except (ImportError, OSError):
        sys.stdin.readline()


def fail_in_popup(message: str) -> int:
    print(f"launchpad: {message}", file=sys.stderr)
    wait_for_key()
    return 1


def visible_entries(config: Config, context: dict) -> list[Entry]:
    if not any(e.requires_session for e in config.entries):
        return list(config.entries)
    has_session = agent_session(context) is not None
    return [e for e in config.entries if has_session or not e.requires_session]


def cmd_open() -> int:
    try:
        config = load_config()
        entries = visible_entries(config, plugin_context())
        width, height = picker_size(config, slot_keys(), entries)
    except ConfigError:
        # The picker shows the problem.
        width, height = 72, 10
    ok, message = open_popup("picker", width, height)
    if not ok:
        notify(f"couldn't open the picker: {message}")
        return 1
    return 0


def cmd_slot(number: str) -> int:
    if not number.isdigit() or int(number) not in SLOTS:
        notify(f"no such slot: {number}")
        return 2
    try:
        config = load_config()
    except ConfigError as err:
        notify(str(err))
        return 1
    entry = config.slot(int(number))
    if entry is None:
        notify(f"no entry has slot = {number} in {config_path()}")
        return 1
    if entry.requires_session and agent_session(plugin_context()) is None:
        notify(f"{entry.title} needs a pane running an agent session")
        return 1
    return launch(entry)


def launch(entry: Entry, wait: float = 0.0) -> int:
    ok, message = open_popup("run", entry.width, entry.height, {ENTRY_ENV: entry.id}, wait=wait)
    if not ok:
        notify(f"couldn't open {entry.title}: {message}")
        return 1
    return 0


def cmd_launch(entry_id: str) -> int:
    try:
        config = load_config()
    except ConfigError as err:
        notify(str(err))
        return 1
    entry = config.entry(entry_id)
    if entry is None:
        notify(f"no entry has id = {entry_id!r}")
        return 1
    return launch(entry, wait=POPUP_RETRY_SECONDS)


def cmd_picker() -> int:
    try:
        config = load_config()
    except ConfigError as err:
        return fail_in_popup(str(err))

    entries = visible_entries(config, plugin_context())
    if not entries:
        return fail_in_popup(f"no entries to show. Add some to {config_path()}")

    color = not os.environ.get("NO_COLOR")
    palette = palette_for(resolve_theme(config.theme))
    rows = render_rows(entries, slot_keys(), palette, color=color)

    fzf_args = [
        "fzf",
        "--delimiter",
        "\t",
        "--with-nth",
        "1",
        "--prompt",
        "> ",
        "--header",
        "select a tool (esc to cancel)",
        "--layout",
        "reverse",
        "--border=none",
        "--height",
        "100%",
        "--no-info",
    ]
    if color:
        fzf_args.insert(1, "--ansi")
    try:
        fzf = subprocess.run(
            fzf_args,
            input="\n".join(rows) + "\n",
            stdout=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return fail_in_popup("the picker needs fzf on PATH: https://github.com/junegunn/fzf")

    selection = fzf.stdout.strip()
    if not selection:
        return 0
    entry_id = selection.rsplit("\t", 1)[-1]
    if config.entry(entry_id) is None:
        return 0

    # This popup has to close before herdr will open the next one, so hand
    # the launch to a detached helper that outlives it.
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "launch", entry_id],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return 0


def run_environment(entry: Entry, context: dict, base: dict[str, str]) -> dict[str, str]:
    env = {
        name: value
        for name, value in base.items()
        if not name.startswith("HERDR_PLUGIN_") and name != ENTRY_ENV
    }
    for name, key in (
        ("HERDR_ACTIVE_WORKSPACE_ID", "workspace_id"),
        ("HERDR_ACTIVE_TAB_ID", "tab_id"),
        ("HERDR_ACTIVE_PANE_ID", "focused_pane_id"),
        ("HERDR_ACTIVE_PANE_CWD", "focused_pane_cwd"),
    ):
        if context.get(key):
            env[name] = str(context[key])
    env.update(entry.env)
    if entry.session_env:
        session = agent_session(context)
        if session:
            env[entry.session_env] = session
    return env


def run_directory(context: dict) -> str | None:
    for key in ("focused_pane_cwd", "workspace_cwd"):
        path = context.get(key)
        if isinstance(path, str) and os.path.isdir(path):
            return path
    return None


def cmd_run() -> int:
    entry_id = os.environ.get(ENTRY_ENV, "")
    try:
        config = load_config()
    except ConfigError as err:
        return fail_in_popup(str(err))
    entry = config.entry(entry_id)
    if entry is None:
        return fail_in_popup(f"no entry has id = {entry_id!r}")

    context = plugin_context()
    env = run_environment(entry, context, dict(os.environ))
    cwd = run_directory(context)
    if cwd:
        os.chdir(cwd)
        env["PWD"] = cwd

    argv = ["sh", "-c", entry.command] if isinstance(entry.command, str) else list(entry.command)
    try:
        os.execvpe(argv[0], argv, env)
    except OSError as err:
        return fail_in_popup(f"can't run {argv[0]}: {err.strerror}")
    return 1  # not reached


USAGE = """usage: launchpad <command>

herdr runs these for you; see herdr-plugin.toml.

  open        open the picker popup
  slot N      open the entry with slot = N (1-9)
  picker      the picker itself (runs inside the popup)
  run         run the entry named by $LAUNCHPAD_ENTRY (runs inside the popup)
  launch ID   open entry ID once the current popup closes
  config      print the config file's path
"""


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    match args:
        case ["open"]:
            return cmd_open()
        case ["slot", number]:
            return cmd_slot(number)
        case ["picker"]:
            return cmd_picker()
        case ["run"]:
            return cmd_run()
        case ["launch", entry_id]:
            return cmd_launch(entry_id)
        case ["config"]:
            print(config_path())
            return 0
        case ["--version"]:
            print(f"launchpad {VERSION}")
            return 0
        case ["-h"] | ["--help"]:
            print(USAGE, end="")
            return 0
    print(USAGE, end="", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
