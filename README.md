# herdr-launchpad

[![CI](https://github.com/wmxscott/herdr-launchpad/actions/workflows/ci.yml/badge.svg)](https://github.com/wmxscott/herdr-launchpad/actions/workflows/ci.yml)

A [Herdr](https://herdr.dev) plugin that opens your terminal tools in popups: from an icon picker, or straight from a key.

You list the tools in a config file: lazygit, nvim, a dashboard, a script. Each one gets a title, an icon, a colour and a popup size. One key opens the picker, and up to nine more open a tool directly. The tool starts in the directory of the pane you were in, and the popup closes when it exits, leaving your panes as they were.

## Requirements

- Herdr 0.7.4 or newer, on macOS or Linux
- Python 3.11 or newer on `PATH`. macOS's own `/usr/bin/python3` is too old; Homebrew's `python` is fine. Launchpad looks for one the first time it runs and remembers its path in the file `python` in Herdr's state directory for the plugin, usually `~/.local/state/herdr/plugins/launchpad/`. Delete that file to make it look again
- [fzf](https://github.com/junegunn/fzf), for the picker
- Optionally, a [Nerd Font](https://www.nerdfonts.com) for the icons in the example config. Any character or emoji works as an icon

## Install

```sh
herdr plugin install wmxscott/herdr-launchpad
```

Herdr shows what the plugin will run and asks before installing; `--yes` skips that. Pin a version with `--ref <tag>`. There is no `herdr plugin update`: run the install again to update.

Then give it a config. Start from the example:

```sh
curl -fsSL https://raw.githubusercontent.com/wmxscott/herdr-launchpad/main/examples/config.toml \
  -o "$(herdr plugin config-dir launchpad)/config.toml"
```

And bind a key to the picker in Herdr's `config.toml`:

```toml
[[keys.command]]
key = "ctrl+L"
type = "plugin_action"
command = "launchpad.open"
description = "launchpad"
```

Run `herdr server reload-config`, or restart Herdr, to pick up new keys.

## Configuration

The config lives in the plugin's config directory, which `herdr plugin config-dir launchpad` prints. That's usually `~/.config/herdr/plugins/config/launchpad/config.toml`. Launchpad reads it each time it opens, so changes apply straight away. When the file is missing or has a mistake, the picker says what's wrong and where.

```toml
theme = "auto"

[picker]
width = 40
height = 12

[[entries]]
id = "lazygit"
title = "lazygit"
command = ["lazygit"]
icon = "\ue702"
color = "green"
width = "95%"
height = "95%"
slot = 1
```

### Top level

| Setting | Default | |
|---|---|---|
| `theme` | `"auto"` | Picker colours: `"auto"`, `"dark"` or `"light"`. See [Theme](#theme) |
| `[picker]` `width`, `height` | fits the entries | Picker popup size, in the same form as an entry's `width` and `height` |

### `[[entries]]`

One table per tool, shown in the picker in this order.

| Setting | Default | |
|---|---|---|
| `id` | *(required)* | Letters, digits, `-` and `_`. Unique |
| `command` | *(required)* | What to run. A list, like `["gh", "dash"]`, runs directly. A string runs with `sh -c`, so it can use pipes, `&&` and variables |
| `title` | the `id` | Name in the picker |
| `icon` | `"•"` | A character or emoji shown before the title. Write Nerd Font glyphs as escapes, like `"\ue702"` |
| `color` | `"blue"` | Icon colour: a Catppuccin accent name, or `"#rrggbb"`. `colour` works too |
| `width` | `"80%"` | Popup width, in terminal cells (`120`) or a percentage of the window (`"95%"`) |
| `height` | `"80%"` | Popup height, the same way |
| `slot` | *(none)* | `1` to `9`. Lets a key open this entry through the `launchpad.slot-<n>` action. See [Keybindings](#keybindings) |
| `key` | from Herdr's config | Key shown next to the entry in the picker. Normally read from Herdr's `config.toml`; set it to show something else |
| `env` | `{}` | Extra environment variables, like `{ LG_CONFIG_FILE = "/path/to/lazygit.yml" }` |
| `session_env` | *(none)* | Name of a variable to set to the agent session id of the focused pane. See [Agent sessions](#agent-sessions) |
| `requires_session` | `false` | Only offer the entry when the focused pane runs an agent with a session |

Colour names: `rosewater`, `flamingo`, `pink`, `mauve`, `red`, `maroon`, `peach`, `yellow`, `green`, `teal`, `sky`, `sapphire`, `blue`, `lavender`.

### What the tool gets

- **Directory:** the focused pane's working directory, or the workspace's when Herdr can't tell.
- **Environment:** Herdr's environment, plus `HERDR_ACTIVE_WORKSPACE_ID`, `HERDR_ACTIVE_TAB_ID`, `HERDR_ACTIVE_PANE_ID` and `HERDR_ACTIVE_PANE_CWD` for the pane underneath the popup, the names Herdr gives its own popup keybindings. The entry's `env` goes on top.
- **Terminal:** the whole popup, including Escape. The popup closes when the command exits.

## Keybindings

Herdr binds keys to plugin actions, and a plugin has to declare its actions in its manifest. So Launchpad has ten fixed ones:

| Action | Opens |
|---|---|
| `launchpad.open` | The picker |
| `launchpad.slot-1` … `launchpad.slot-9` | The entry with `slot = 1` … `slot = 9` |

Give an entry a slot, then bind a key to that slot in Herdr's `config.toml`:

```toml
[[keys.command]]
key = "prefix+G"
type = "plugin_action"
command = "launchpad.slot-1"
description = "lazygit"
```

The picker finds these bindings and shows each key next to its entry. Entries without a slot are still in the picker. `herdr plugin action list --plugin launchpad` lists the actions.

## Examples

A set to start from. [`examples/config.toml`](examples/config.toml) has most of them.

```toml
[[entries]]
id = "lazygit"
title = "lazygit"
command = ["lazygit"]
icon = "\ue702"
color = "green"
width = "95%"
height = "95%"
slot = 1

[[entries]]
id = "nvim"
title = "nvim"
command = ["nvim"]
icon = "\ue7c5"
color = "teal"
width = "95%"
height = "95%"
slot = 2

[[entries]]
id = "gh-dash"
title = "gh dash"
command = ["gh", "dash"]
icon = "\uf09b"
color = "blue"
width = "95%"
height = "95%"
slot = 3

[[entries]]
id = "shell"
title = "scratch shell"
command = 'exec "${SHELL:-sh}"'
icon = "\uf489"
color = "mauve"
width = "80%"
height = "60%"

[[entries]]
id = "brew-upgrade"
title = "brew upgrade"
command = 'brew upgrade; printf "\ndone, press enter"; read -r _'
icon = "\uf0fc"
color = "yellow"
width = "80%"
height = "45%"
```

With these keys in Herdr's `config.toml`:

```toml
[[keys.command]]
key = "ctrl+L"
type = "plugin_action"
command = "launchpad.open"
description = "launchpad"

[[keys.command]]
key = "prefix+G"
type = "plugin_action"
command = "launchpad.slot-1"
description = "lazygit"

[[keys.command]]
key = "prefix+V"
type = "plugin_action"
command = "launchpad.slot-2"
description = "nvim"

[[keys.command]]
key = "prefix+d"
type = "plugin_action"
command = "launchpad.slot-3"
description = "gh dash"
```

## Agent sessions

Some tools want to know which coding agent you were looking at. `session_env` passes the agent session id of the focused pane in an environment variable, and `requires_session` hides the entry when there isn't one. The id is whatever the agent reports to Herdr, such as a Claude Code session id.

For example, [pr-tracker](https://github.com/wmxscott/pr-tracker)'s picker shows the pull requests a session opened when `PR_TRACKER_SESSION_ID` is set:

```toml
[[entries]]
id = "prs"
title = "pull requests"
command = ["prs"]
icon = "\ue726"
color = "mauve"
width = "100%"
height = "80%"
slot = 4
session_env = "PR_TRACKER_SESSION_ID"
requires_session = true
```

Herdr keeps the pane underneath a popup as the focused one, so this works from the picker too.

## Theme

With `theme = "auto"`, the picker's colours follow, in order:

1. [theme-monitor](https://github.com/wmxscott/theme-monitor)'s trigger file, when it exists. theme-monitor tracks the macOS appearance in the background:

   ```sh
   brew install wmxscott/tap/theme-monitor && brew services start theme-monitor
   ```

2. The macOS appearance, read when the picker opens.
3. Dark.

The palettes are Catppuccin Latte for light and Macchiato for dark.

## Limits

- **Nine slots.** Herdr has no way for a plugin to add actions at runtime, so direct keys go through the nine `slot-<n>` actions. The picker can hold any number of entries.
- **One popup title.** Herdr takes a popup's title from the plugin manifest, so every tool's popup is titled "launchpad".
- **One popup at a time.** Herdr shows a single popup, and it gets every key while it's open. Choosing from the picker closes it, then opens the tool.

## Uninstall

```sh
herdr plugin uninstall launchpad
rm -r "$(herdr plugin config-dir launchpad)"
```

Then remove the `launchpad.*` bindings from Herdr's `config.toml`.

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format --check
```

To try a checkout in Herdr, uninstall any installed copy, then `herdr plugin link .` from the checkout. `herdr plugin unlink launchpad` removes it again.

The tests run the plugin the way Herdr does, through `bin/launchpad`, in a from-scratch environment: a throwaway `HOME`, no inherited `HERDR_*` variables, and stub `herdr` and `fzf` commands first on `PATH`. They never reach a running Herdr. The stub `herdr` records its arguments, so the tests check exactly which popups the plugin asks for.

`bin/launchpad` is a small `sh` script that finds Python 3.11 or newer and runs `lib/launchpad.py`, which does the work. The actions do the slow parts, reading the config and asking Herdr for the agent session, before they open a popup, and hand the results over in its environment. That way a popup's process only has to start fzf or the tool, and never shows an empty frame.

## License

[MIT](LICENSE)
