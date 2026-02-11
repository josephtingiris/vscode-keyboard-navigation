#!/usr/bin/env python3
"""
Generate a deterministic JSONC array of keybinding objects used as a structural
baseline for keyboard-navigation development, debugging, and testing.

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

# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

from __future__ import annotations

import json
import sys
from random import Random

# Deterministic RNG for reproducible outputs
rng = Random(0)


def usage(prog: str | None = None) -> None:
    if prog is None:
        prog = sys.argv[0].split('/')[-1]
    msg = (
        f"Usage: {prog}\n\n"
        "Options:\n  -h, --help    Show this usage message and exit\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(1)


# Respect -h/--help early so scripts invoking this file get the concise usage
if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
    usage()

# Include modifiers: `alt+ ctrl+ ctrl+alt+ shift+alt+ ctrl+alt+meta+ ctrl+shift+alt+ shift+alt+meta+ ctrl+shift+alt+meta+`

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

# Mapping groups for comments
LEFT_GROUP = {"h", "[", ";", ",", "left"}
DOWN_GROUP = {"j", "down", "pagedown"}
UP_GROUP = {"k", "up", "pageup"}
RIGHT_GROUP = {"l", "]", "'", ".", "right"}

TAG_ORDER = ["(down)", "(left)", "(right)", "(up)", "(arrow)", "(vi)"]


def hex4():
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


records = []

all_mods = MODIFIERS_SINGLE + MODIFIERS_MULTI

for key in KEYS:
    for mod in all_mods:
            key_str = f"{mod}+{key}"
            base_when = when_for(key)
            tags = tags_for(key)
            # only include comment if key belongs to at least one mapping group
            comment_tags = tags if tags else []

            # include the base when condition with its own unique id
            cmd_base = f"(model) {key_str} {hex4()}"
            records.append((key_str, cmd_base, base_when, comment_tags))

            # additional when-context variants to generate separate objects for
            EXTRA_WHENS = ["config.keyboardNavigation.wrap", "!config.keyboardNavigation.wrap"]
            for extra in EXTRA_WHENS:
                combined_when = f"{base_when} && {extra}"
                # generate a unique id for each extra variant
                cmd_extra = f"(model) {key_str} {hex4()}"
                records.append((key_str, cmd_extra, combined_when, comment_tags))

# Ouput JSONC array
out_lines = []
out_lines.append("[")
for i, (k, c, w, tags) in enumerate(records):
    obj = emit_record(k, c, w, tags)
    comma = "," if i < len(records) - 1 else ""
    # ensure comma is on same line as closing brace
    if comma:
        # append comma to last line of obj
        obj = obj + comma
    out_lines.append(obj)
out_lines.append("]")

sys.stdout.write("\n".join(out_lines) + "\n")
try:
    sys.stdout.flush()
except Exception:
    pass
