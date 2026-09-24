from __future__ import annotations

from launchpad import (
    LATTE,
    MACCHIATO,
    Config,
    Entry,
    palette_for,
    picker_size,
    render_rows,
)

ENTRIES = [
    Entry("lazygit", "lazygit", ("lazygit",), icon="G", color="green", slot=1),
    Entry("gh-dash", "gh dash", ("gh", "dash"), icon="D", color="#102030", slot=2),
    Entry("shell", "scratch shell", "exec sh", icon="S", color="mauve", key="F5"),
]
KEYS = {1: "prefix+G"}


def test_plain_rows_align_and_carry_the_id():
    assert render_rows(ENTRIES, KEYS, LATTE, color=False) == [
        "G lazygit" + " " * 14 + "prefix+G\tlazygit",
        "D gh dash\tgh-dash",
        "S scratch shell" + " " * 8 + "F5\tshell",
    ]


def test_coloured_row():
    row = render_rows(ENTRIES[:1], KEYS, MACCHIATO)[0]
    assert row == (
        "\x1b[1;38;2;166;218;149mG\x1b[0m "
        "\x1b[1;38;2;202;211;245mlazygit\x1b[0m"
        + " " * 8
        + "\x1b[2;38;2;110;115;141mprefix+G\x1b[0m"
        + "\tlazygit"
    )


def test_hex_colour():
    row = render_rows(ENTRIES[1:2], {}, LATTE)[0]
    assert row.startswith("\x1b[1;38;2;16;32;48mD\x1b[0m ")


def test_wide_icons_keep_titles_aligned():
    entries = [Entry("a", "a", ("a",), icon="\U0001f680"), Entry("b", "b", ("b",), icon="b")]
    rows = render_rows(entries, {}, LATTE, color=False)
    assert rows == ["\U0001f680 a\ta", "b  b\tb"]


def test_palette_for():
    assert palette_for("dark") is MACCHIATO
    assert palette_for("light") is LATTE


def test_picker_size_fits_the_rows():
    width, height = picker_size(Config(entries=tuple(ENTRIES)), KEYS)
    # icon + space + "scratch shell" + gap + "prefix+G" + chrome
    assert width == 1 + 1 + 13 + 8 + 8 + 5
    assert height == 8


def test_picker_size_grows_with_entries():
    entries = tuple(Entry(f"e{i}", f"e{i}", ("x",)) for i in range(9))
    assert picker_size(Config(entries=entries), {}) == (36, 14)


def test_picker_size_override():
    config = Config(entries=tuple(ENTRIES), picker_width="50%", picker_height=30)
    assert picker_size(config, KEYS) == ("50%", 30)
