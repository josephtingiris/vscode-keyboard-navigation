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

# DAFC

# arrow-key navigational group (ordered tuple; index also corresponds to letter-group positions)
ARROW_GROUP = ("left", "down", "up", "right")

# destructure for consistency and clarity; the order of the directional keys dictates
LEFT, DOWN, UP, RIGHT = ARROW_GROUP

# letter-key navigation groups (MUST use the same directional order as ARROW_GROUP)
EMACS_GROUP = ("b", "n", "p", "f")
KBM_GROUP = ("a", "s", "w", "d")
VI_GROUP = ("h", "j", "k", "l")

# directional groups for jukes and moves

FOUR_PACK_DOWN_GROUP = {"end", "pagedown"}
FOUR_PACK_UP_GROUP = {"home", "pageup"}
FOUR_PACK_GROUP = FOUR_PACK_DOWN_GROUP | FOUR_PACK_UP_GROUP

PUNCTUATION_LEFT_GROUP = {"[", "{", ";", ","}
PUNCTUATION_RIGHT_GROUP = {"]", "}", "'", "."}
PUNCTUATION_GROUP = PUNCTUATION_LEFT_GROUP | PUNCTUATION_RIGHT_GROUP

LEFT_GROUP = {"h", "left"} | PUNCTUATION_LEFT_GROUP
DOWN_GROUP = {"j", "down"} | FOUR_PACK_DOWN_GROUP
UP_GROUP = {"k", "up"} | FOUR_PACK_UP_GROUP
RIGHT_GROUP = {"l", "right"} | PUNCTUATION_RIGHT_GROUP

JUKE_GROUP = PUNCTUATION_GROUP | FOUR_PACK_GROUP

# split groups for panes/windows

SPLIT_HORIZONTAL_GROUP = {"-", "_"}
SPLIT_VERTICAL_GROUP = {"=", "+", "\\", "|"}
SPLIT_GROUP = SPLIT_HORIZONTAL_GROUP | SPLIT_VERTICAL_GROUP

# chord groups for additional functionality

ACTION_GROUP = {"a"}
ALTERNATE_ACTION_KEY = 'l'

DEBUG_GROUP = {"d"}
ALTERNATE_DEBUG_KEY = 'j'

EXTENSION_GROUP = {"x"}
ALTERNATE_EXTENSION_KEY = 'n'

# comments

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

    # expose allowed letter keys for helper functions
    globals()["ALLOWED_LETTER_KEYS"] = allowed_letter_keys

    def _select_adaptive_key(primary_group: set, alternate_key: str, label: str) -> str:
        primary_key = sorted(primary_group)[0]
        contains_primary = primary_key in allowed_letter_keys
        contains_alternate = alternate_key in allowed_letter_keys
        if contains_primary and not contains_alternate:
            # primary conflicts with included letter keys => use alternate
            return alternate_key
        if contains_primary and contains_alternate:
            YELLOW = "\x1b[33m"
            RESET = "\x1b[0m"
            print(f"{YELLOW}Warning: both '{primary_key}' and '{alternate_key}' present in selected navigation group; using default '{primary_key}'.{RESET}", file=sys.stderr)
            return primary_key
        return primary_key

    # ACTION_GROUP
    action_selected = _select_adaptive_key(ACTION_GROUP, ALTERNATE_ACTION_KEY, "action")
    globals()["ACTION_GROUP"] = {action_selected}

    # DEBUG_GROUP
    debug_selected = _select_adaptive_key(DEBUG_GROUP, ALTERNATE_DEBUG_KEY, "debug")
    globals()["DEBUG_GROUP"] = {debug_selected}

    # EXTENSION_GROUP
    extension_selected = _select_adaptive_key(EXTENSION_GROUP, ALTERNATE_EXTENSION_KEY, "extension")
    globals()["EXTENSION_GROUP"] = {extension_selected}

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
