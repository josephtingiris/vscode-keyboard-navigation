#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Generate a deterministic JSONC array of keybinding objects used as a structural baseline for keyboard-navigation development, debugging, and testing.

Usage:
    ./bin/keybindings-corpus.py

Examples:
    # write corpus to a reference file
    ./bin/keybindings-corpus.py > references/keybindings-corpus.jsonc

Behavior:
    - Writes a JSONC array of keybinding objects to stdout.
    - Uses a fixed PRNG seed for reproducible output.
    - Does not modify files on disk.

Inputs / Outputs:
    stdout: JSONC array of keybinding objects encoded as UTF-8

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""
from __future__ import annotations

import json
import sys
import argparse
from random import Random
from itertools import combinations
from typing import List

# Included modifiers: `alt+ ctrl+ ctrl+alt+ shift+alt+ ctrl+alt+meta+ ctrl+shift+alt+ shift+alt+meta+ ctrl+shift+alt+meta+`

MODIFIERS_SINGLE = ["alt", "ctrl"]
MODIFIERS_MULTI = [
    "ctrl+alt",
    "shift+alt",
    "ctrl+alt+meta",
    "ctrl+shift+alt",
    "shift+alt+meta",
    "ctrl+shift+alt+meta",
]

KEYS = [
    "-", "=", "[", "]", ";", "'", ",", ".",
    "a", "d", "h", "j", "k", "l",
    "end", "home", "pageup", "pagedown", "left", "down", "up", "right",
]

VI_KEYS = {"h", "j", "k", "l"}
ARROW_KEYS = {"end", "home", "pageup",
              "pagedown", "left", "down", "up", "right"}

# key groups for comments
LEFT_GROUP = {"h", "[", ";", ",", "left"}
DOWN_GROUP = {"j", "down", "pagedown"}
UP_GROUP = {"k", "up", "pageup"}
RIGHT_GROUP = {"l", "]", "'", ".", "right"}

TAG_ORDER = ["(down)", "(left)", "(right)", "(up)", "(arrow)", "(vi)"]


def hex4(rng: Random) -> str:
    return f"{rng.randint(0, 0xFFFF):04x}"


def tags_for(key):
    tags = []
    if key in ARROW_KEYS:
        tags.append("(arrow)")
    if key in DOWN_GROUP:
        tags.append("(down)")
    if key in LEFT_GROUP:
        tags.append("(left)")
    if key in RIGHT_GROUP:
        tags.append("(right)")
    if key in UP_GROUP:
        tags.append("(up)")
    if key in VI_KEYS:
        tags.append("(vi)")
    # Sort tags according to TAG_ORDER
    tags_sorted = [t for t in TAG_ORDER if t in tags]
    return tags_sorted


def when_for(key):
    if key in ARROW_KEYS:
        return "config.keyboardNavigation.enabled && config.keyboardNavigation.arrows"
    if key in VI_KEYS:
        return "config.keyboardNavigation.enabled && config.keyboardNavigation.vi"
    return "config.keyboardNavigation.enabled"


def emit_record(key_str, command_str, when_str, comment_tags):
    parts = []
    parts.append("  {")
    if comment_tags:
        parts.append("    // " + " ".join(comment_tags))
    parts.append(f'    "key": "{key_str}",')
    parts.append(f'    "command": "{command_str}",')
    parts.append(f'    "when": "{when_str}"')
    parts.append("  }")
    return "\n".join(parts)


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description="Generate a deterministic JSONC array of keybinding objects used as a structural baseline for keyboard-navigation development, debugging, and testing.",
        epilog="Example: %(prog)s > references/keybindings-corpus.jsonc",
    )

    # only show help when -h/--help is provided
    parser.parse_args(argv)

    # initialize RNG locally so other code can't affect the sequence
    rng = Random(0)

    # generate records
    records = []
    all_mods = MODIFIERS_SINGLE + MODIFIERS_MULTI
    for key in KEYS:
        for mod in all_mods:
            key_str = f"{mod}+{key}"
            base_when = when_for(key)
            tags = tags_for(key)
            comment_tags = tags if tags else []

            cmd_base = f"(model) {key_str} {hex4(rng)}"
            records.append((key_str, cmd_base, base_when, comment_tags))

            EXTRA_WHENS = [
                "config.keyboardNavigation.terminal",
                "!config.keyboardNavigation.terminal",
                "config.keyboardNavigation.wrap",
                "!config.keyboardNavigation.wrap",
            ]
            n = len(EXTRA_WHENS)
            for r in range(1, n + 1):
                for combo in combinations(EXTRA_WHENS, r):
                    conflict = False
                    seen = {}
                    for extra in combo:
                        base = extra[1:] if extra.startswith("!") else extra
                        neg = extra.startswith("!")
                        if base in seen:
                            if seen[base] != neg:
                                conflict = True
                                break
                        else:
                            seen[base] = neg
                    if conflict:
                        continue

                    combined_when = base_when + " && " + " && ".join(combo)
                    cmd_extra = f"(model) {key_str} {hex4(rng)}"
                    records.append((key_str, cmd_extra, combined_when, comment_tags))

    out_lines = []
    out_lines.append("[")
    for i, (k, c, w, tags) in enumerate(records):
        obj = emit_record(k, c, w, tags)
        comma = "," if i < len(records) - 1 else ""
        if comma:
            obj = obj + comma
        out_lines.append(obj)
    out_lines.append("]")

    sys.stdout.write("\n".join(out_lines) + "\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
