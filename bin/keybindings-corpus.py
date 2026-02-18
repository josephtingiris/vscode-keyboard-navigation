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
    "left", "down", "up", "right",
    "b", "n", "p", "f",
    "a", "s", "w", "d",
    "h", "j", "k", "l",
    "end", "home", "pageup", "pagedown",
    "[", "]", ";", "'", ",", ".",
    "-", "_", "=", "+", "\\", "|",
    "x",
]

# DAFC

ARROW_GROUP = {"left", "down", "up", "right"}
EMACS_GROUP = {"b", "n", "p", "f"}
KBM_GROUP = {"a", "s", "w", "d"}
VI_GROUP = {"h", "j", "k", "l"}

JUKE_GROUP = {"end", "home", "pageup",
              "pagedown", "[", "]", ";", "'", ",", "."}
SPLIT_GROUP = {"-", "_", "=", "+", "\\", "|"}

LEFT_GROUP = {"h", "[", ";", ",", "left"}
DOWN_GROUP = {"end", "j", "down", "pagedown"}
UP_GROUP = {"home", "k", "up", "pageup"}
RIGHT_GROUP = {"l", "]", "'", ".", "right"}

ACTION_GROUP = {"a"}

DEBUG_GROUP = {"d"}

EXTENSION_GROUP = {"x"}

TAG_ORDER = [
    "(down)", "(left)", "(right)", "(up)",
    "(arrow)", "(emacs)", "(kbm)", "(vi)",
    "(juke)", "(split)",
    "(debug)", "(action)", "(native)",
]


def hex4(rng: Random) -> str:
    return f"{rng.randint(0, 0xFFFF):04x}"


def tags_for(key):
    tags = []
    if key in DOWN_GROUP:
        tags.append("(down)")
    if key in LEFT_GROUP:
        tags.append("(left)")
    if key in RIGHT_GROUP:
        tags.append("(right)")
    if key in UP_GROUP:
        tags.append("(up)")
    if key in ARROW_GROUP:
        tags.append("(arrow)")
    if key in EMACS_GROUP and key in globals().get("ALLOWED_LETTER_KEYS", set()):
        tags.append("(emacs)")
    if key in KBM_GROUP and key in globals().get("ALLOWED_LETTER_KEYS", set()):
        tags.append("(kbm)")
    if key in VI_GROUP and key in globals().get("ALLOWED_LETTER_KEYS", set()):
        tags.append("(vi)")
    if key in JUKE_GROUP:
        tags.append("(juke)")
    if key in SPLIT_GROUP:
        tags.append("(split)")
    if key in DEBUG_GROUP:
        tags.append("(debug)")
    if key in ACTION_GROUP:
        tags.append("(action)")
    if key in EXTENSION_GROUP:
        tags.append("(extension)")

    tags_sorted = [t for t in TAG_ORDER if t in tags]
    return tags_sorted


def when_for(key):
    parts = ["config.keyboardNavigation.enabled"]
    seen = set()

    def _add(cond: str) -> None:
        if cond not in seen:
            parts.append(cond)
            seen.add(cond)

    if key in ARROW_GROUP:
        _add("config.keyboardNavigation.keys.arrows")
    if key in EMACS_GROUP and key in globals().get("ALLOWED_LETTER_KEYS", set()):
        _add("config.keyboardNavigation.keys.letters == 'emacs'")
    if key in KBM_GROUP and key in globals().get("ALLOWED_LETTER_KEYS", set()):
        _add("config.keyboardNavigation.keys.letters == 'kbm'")
    if key in VI_GROUP and key in globals().get("ALLOWED_LETTER_KEYS", set()):
        _add("config.keyboardNavigation.keys.letters == 'vi'")
    if key in DEBUG_GROUP:
        _add("config.keyboardNavigation.chords.debug")
    if key in ACTION_GROUP:
        _add("config.keyboardNavigation.chords.action")
    if key in EXTENSION_GROUP:
        _add("config.keyboardNavigation.chords.extension")

    return " && ".join(parts)


def emit_record(key_str, command_str, when_str, comment_tags):
    parts = []
    parts.append("  {")
    if comment_tags:
        parts.append("    // " + " ".join(comment_tags))
    parts.append(f'    "key": {json.dumps(key_str)},')
    parts.append(f'    "command": {json.dumps(command_str)},')
    parts.append(f'    "when": {json.dumps(when_str)}')
    parts.append("  }")
    return "\n".join(parts)


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description="Generate a deterministic JSONC array of unique keybinding objects for keyboard navigation development, debugging, and testing.",
        epilog="Example: %(prog)s > references/keybindings-corpus.jsonc",
    )

    # parse CLI args (only show help when -h/--help is provided)
    parser.add_argument(
        "-n",
        "--navigation-group",
        choices=["emacs", "kbm", "vi", "none"],
        default="none",
        help=(
            "Select the active letter-key navigation group (default: none)."
        ),
    )
    args = parser.parse_args(argv)

    # initialize RNG locally so other code can't affect the sequence
    rng = Random(0)

    LETTER_GROUPS = {
        "emacs": EMACS_GROUP,
        "kbm": KBM_GROUP,
        "vi": VI_GROUP,
    }
    selected = args.navigation_group
    if selected == "none":
        # exclude all letter-key groups
        allowed_letter_keys = set()
    else:
        allowed_letter_keys = set(LETTER_GROUPS[selected])

    # adapt the action key based on the selected letter-key group.
    action_key_default = "a"
    action_key = action_key_default
    contains_a = "a" in allowed_letter_keys
    contains_l = "l" in allowed_letter_keys
    if contains_a and not contains_l:
        action_key = "l"
    elif contains_a and contains_l:
        YELLOW = "\x1b[33m"
        RESET = "\x1b[0m"
        print(f"{YELLOW}Warning: both 'a' and 'l' present in selected navigation group; using default 'a'.{RESET}", file=sys.stderr)

    globals()["ACTION_GROUP"] = {action_key}

    # expose allowed letter keys for helper functions
    globals()["ALLOWED_LETTER_KEYS"] = allowed_letter_keys

    # Adapt the debug key similar to the action key: prefer 'j' when 'd' conflicts with an included letter-key; warn if both present.
    debug_key_default = "d"
    debug_key = debug_key_default
    contains_d = "d" in allowed_letter_keys
    contains_j = "j" in allowed_letter_keys
    if contains_d and not contains_j:
        debug_key = "j"
    elif contains_d and contains_j:
        YELLOW = "\x1b[33m"
        RESET = "\x1b[0m"
        print(f"{YELLOW}Warning: both 'd' and 'j' present in selected navigation group; using default 'd'.{RESET}", file=sys.stderr)

    globals()["DEBUG_GROUP"] = {debug_key}

    keys_to_emit = set()
    keys_to_emit.update(ARROW_GROUP)
    keys_to_emit.update(JUKE_GROUP)
    keys_to_emit.update(SPLIT_GROUP)
    keys_to_emit.update(DEBUG_GROUP)
    keys_to_emit.update(EXTENSION_GROUP)
    keys_to_emit.update(ACTION_GROUP)
    keys_to_emit.update(allowed_letter_keys)

    keys_ordered = sorted(keys_to_emit)

    # generate records
    records = []
    all_mods = MODIFIERS_SINGLE + MODIFIERS_MULTI
    for key in keys_ordered:
        for mod in all_mods:
            key_str = f"{mod}+{key}"
            base_when = when_for(key)
            tags = tags_for(key)
            comment_tags = tags if tags else []

            cmd_base = f"(corpus) {key_str} {hex4(rng)}"
            records.append((key_str, cmd_base, base_when, comment_tags))

            EXTRA_WHENS = [
                # "config.keyboardNavigation.terminal",
                # "!config.keyboardNavigation.terminal",
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
                    cmd_extra = f"(corpus) {key_str} {hex4(rng)}"
                    records.append(
                        (key_str, cmd_extra, combined_when, comment_tags))

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
