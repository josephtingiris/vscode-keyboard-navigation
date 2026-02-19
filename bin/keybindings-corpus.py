#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Generate a deterministic JSONC array of keybinding objects for keyboard-navigation development, debugging, and testing.

Usage:
    ./bin/keybindings-corpus.py

Examples:
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
from typing import List, Tuple
from collections import Counter
import hashlib
import inspect

# MODIFIERS

MODIFIERS_SINGLE = [
    "alt",
    "ctrl",
]

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
LEFT, DOWN, UP, RIGHT = ARROW_GROUP

# letter-key navigation groups (tuples MUST use the same directional order as ARROW_GROUP)
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

# letter-key groups are injected at runtime by `init_directional_groups` based on the selected `--navigation-group`
LEFT_GROUP = set(PUNCTUATION_LEFT_GROUP)
DOWN_GROUP = set(FOUR_PACK_DOWN_GROUP)
UP_GROUP = set(FOUR_PACK_UP_GROUP)
RIGHT_GROUP = set(PUNCTUATION_RIGHT_GROUP)

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

# comment tag/token order
TAG_ORDER = [
    "(down)", "(left)", "(right)", "(up)",
    "(horizontal)", "(vertical)",
    "(arrow)", "(emacs)", "(kbm)", "(vi)",
    "(juke)", "(split)",
    "(debug)", "(action)", "(extension)",
]


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


def hex4(rng: Random) -> str:
    return f"{rng.randint(0, 0xFFFF):04x}"


def init_directional_groups(selected: str, letter_groups: dict) -> None:
    """ensure LEFT_GROUP/DOWN_GROUP/UP_GROUP/RIGHT_GROUP globals include
    the arrow literal and the corresponding letter from the selected
    navigation group (if any). This centralizes startup mutation so
    helpers can continue to read globals.
    """
    direction_to_var = {
        "left": "LEFT_GROUP",
        "down": "DOWN_GROUP",
        "up": "UP_GROUP",
        "right": "RIGHT_GROUP",
    }

    for i, direction_name in enumerate(ARROW_GROUP):
        var_name = direction_to_var[direction_name]
        current = set(globals().get(var_name, set()))
        # always include the arrow literal (e.g., "left")
        current.add(direction_name)
        # include the corresponding letter from the selected letter group
        if selected != "none" and selected in letter_groups:
            group = letter_groups[selected]
            if i < len(group):
                current.add(group[i])
        globals()[var_name] = current


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic JSONC array of unique keybinding "
            "objects for keyboard navigation development, debugging, "
            "and testing."
        ),
        epilog="Example: %(prog)s > references/keybindings-corpus.jsonc",
    )

    parser.add_argument(
        "-n",
        "--navigation-group",
        choices=["emacs", "kbm", "vi", "none", "all"],
        default="none",
        help=(
            "Select the active letter-key navigation group (default: none)."
        ),
    )
    args = parser.parse_args(argv)

    LETTER_GROUPS = {
        "emacs": EMACS_GROUP,
        "kbm": KBM_GROUP,
        "vi": VI_GROUP,
    }
    selected = args.navigation_group
    # expose letter-groups and selected mode for helper functions
    globals()["LETTER_GROUPS"] = LETTER_GROUPS
    globals()["SELECTED_NAV_GROUP"] = selected
    if selected == "none" or selected == "all":
        allowed_letter_keys = set()
    else:
        allowed_letter_keys = set(LETTER_GROUPS[selected])

    globals()["ALLOWED_LETTER_KEYS"] = allowed_letter_keys

    init_directional_groups(selected, LETTER_GROUPS)
    # preserve the original (base) chord groups so per-mode mutation does
    # not affect later mode processing when we select adaptive keys.
    BASE_ACTION_GROUP = set(ACTION_GROUP)
    BASE_DEBUG_GROUP = set(DEBUG_GROUP)
    BASE_EXTENSION_GROUP = set(EXTENSION_GROUP)

    def generate_records_for_mode(mode: str) -> List[Tuple[str, str, List[str]]]:
        globals()["SELECTED_NAV_GROUP"] = mode
        if mode == "none":
            globals()["ALLOWED_LETTER_KEYS"] = set()
        else:
            globals()["ALLOWED_LETTER_KEYS"] = set(LETTER_GROUPS.get(mode, ()))
        init_directional_groups(mode, LETTER_GROUPS)

        def _select_adaptive_key(primary_group: set, alternate_key: str, label: str) -> str:
            primary_key = sorted(primary_group)[0]
            contains_primary = primary_key in globals().get("ALLOWED_LETTER_KEYS", set())
            contains_alternate = alternate_key in globals().get("ALLOWED_LETTER_KEYS", set())

            # Correct selection logic:
            # - If primary conflicts with allowed letters and alternate is free -> use alternate
            # - If both conflict -> warn and keep primary
            # - Otherwise -> keep primary
            if contains_primary and not contains_alternate:
                return alternate_key
            if contains_primary and contains_alternate:
                YELLOW = "\x1b[33m"
                RESET = "\x1b[0m"
                allowed = sorted(globals().get("ALLOWED_LETTER_KEYS", set()))
                primary_group_sorted = sorted(primary_group)
                frame = inspect.currentframe()
                if frame is not None:
                    lineno = inspect.getframeinfo(frame).lineno
                else:
                    lineno = -1
                loc = f"{__file__}:{lineno}"
                msg = (
                    f"{YELLOW}Warning ({loc}): mode={mode!r} chord={label!r}: both primary '{primary_key}' (group={primary_group_sorted})"
                    f" and alternate '{alternate_key}' present in allowed letters {allowed}; using default '{primary_key}'.{RESET}"
                )
                print(msg, file=sys.stderr)
                return primary_key

            return primary_key

        # apply adaptive selection for chord keys for this mode
        globals()["ACTION_GROUP"] = {
            _select_adaptive_key(
                BASE_ACTION_GROUP, ALTERNATE_ACTION_KEY, "action")
        }
        globals()["DEBUG_GROUP"] = {
            _select_adaptive_key(
                BASE_DEBUG_GROUP, ALTERNATE_DEBUG_KEY, "debug")
        }
        globals()["EXTENSION_GROUP"] = {
            _select_adaptive_key(BASE_EXTENSION_GROUP,
                                 ALTERNATE_EXTENSION_KEY, "extension")
        }

        keys_to_emit = set()
        keys_to_emit.update(ARROW_GROUP)
        keys_to_emit.update(JUKE_GROUP)
        keys_to_emit.update(SPLIT_GROUP)
        keys_to_emit.update(globals()["DEBUG_GROUP"])
        keys_to_emit.update(globals()["EXTENSION_GROUP"])
        keys_to_emit.update(globals()["ACTION_GROUP"])
        keys_to_emit.update(globals()["ALLOWED_LETTER_KEYS"])

        keys_ordered = sorted(keys_to_emit)

        recs: List[Tuple[str, str, List[str]]] = []
        local_seen: set = set()
        all_mods = MODIFIERS_SINGLE + MODIFIERS_MULTI
        for key in keys_ordered:
            for mod in all_mods:
                key_str = f"{mod}+{key}"

                # do not compute tags yet; compute them afterwards to avoid race/ordering effects
                comment_tags: List[str] = []

                mode_when = when_for(key, mod)

                SELECTED_NAV_GROUP_state = globals().get("SELECTED_NAV_GROUP")
                ALLOWED_LETTER_KEYS_state = globals().get("ALLOWED_LETTER_KEYS")

                LEFT_GROUP_state = set(globals().get("LEFT_GROUP", set()))
                DOWN_GROUP_state = set(globals().get("DOWN_GROUP", set()))
                UP_GROUP_state = set(globals().get("UP_GROUP", set()))
                RIGHT_GROUP_state = set(globals().get("RIGHT_GROUP", set()))

                ACTION_GROUP_state = set(globals().get("ACTION_GROUP", set()))
                DEBUG_GROUP_state = set(globals().get("DEBUG_GROUP", set()))
                EXTENSION_GROUP_state = set(globals().get("EXTENSION_GROUP", set()))

                globals()["SELECTED_NAV_GROUP"] = "none"
                globals()["ALLOWED_LETTER_KEYS"] = set()
                # clear chord groups so generic_when is just the root enabled condition
                globals()["ACTION_GROUP"] = set()
                globals()["DEBUG_GROUP"] = set()
                globals()["EXTENSION_GROUP"] = set()

                init_directional_groups("none", LETTER_GROUPS)
                generic_when = when_for(key, mod)

                # restore selected / letter / directional groups
                globals()["SELECTED_NAV_GROUP"] = SELECTED_NAV_GROUP_state
                globals()["ALLOWED_LETTER_KEYS"] = ALLOWED_LETTER_KEYS_state
                globals()["LEFT_GROUP"] = LEFT_GROUP_state
                globals()["DOWN_GROUP"] = DOWN_GROUP_state
                globals()["UP_GROUP"] = UP_GROUP_state
                globals()["RIGHT_GROUP"] = RIGHT_GROUP_state
                # restore chord state
                globals()["ACTION_GROUP"] = ACTION_GROUP_state
                globals()["DEBUG_GROUP"] = DEBUG_GROUP_state
                globals()["EXTENSION_GROUP"] = EXTENSION_GROUP_state

                # emit generic first if different, then the mode-qualified when
                emitted_whens = []
                if generic_when != mode_when:
                    emitted_whens.append(generic_when)
                emitted_whens.append(mode_when)

                EXTRA_WHENS: List[str] = [
                    # "config.keyboardNavigation.terminal",
                    # "!config.keyboardNavigation.terminal",
                ]
                m = len(EXTRA_WHENS)

                for base_when in emitted_whens:
                    pair = (key_str, base_when)
                    if pair not in local_seen:
                        local_seen.add(pair)
                        recs.append((key_str, base_when, comment_tags))

                    for r in range(1, m + 1):
                        for combo in combinations(EXTRA_WHENS, r):
                            conflict = False
                            seen = {}
                            for extra in combo:
                                base = extra[1:] if extra.startswith(
                                    "!") else extra
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
                            pair = (key_str, combined_when)
                            if pair not in local_seen:
                                local_seen.add(pair)
                                recs.append((key_str, combined_when, comment_tags))

        return recs

    # build records for either a single selected mode or all modes
    modes: List[str]
    if selected == "all":
        modes = ["none", "emacs", "kbm", "vi"]
    else:
        modes = [selected]

    seen_pairs = set()
    records: List[Tuple[str, str, List[str]]] = []
    for mode in modes:
        for rec in generate_records_for_mode(mode):
            pair = (rec[0], rec[1])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            records.append(rec)

    # compute deterministic per-record ids using SHA-256(key||when)
    id_fulls = [hashlib.sha256(f"{k}||{w}".encode()).hexdigest()
                for (k, w, _) in records]
    n = len(id_fulls)
    assigned: List[str | None] = [None] * n

    # assign the shortest unique prefix, starting at 4 chars, up to 12
    for L in range(4, 13):
        prefixes = [h[:L] for h in id_fulls]
        counts = Counter(prefixes)
        for i, p in enumerate(prefixes):
            if assigned[i] is None and counts[p] == 1:
                assigned[i] = p

    # finalize any remaining by using 12-char prefix
    for i in range(n):
        if assigned[i] is None:
            assigned[i] = id_fulls[i][:12]

    # build final objects with assigned ids
    # compute comment tags now that records are final: set globals based on
    # each record's when-clause and recompute adaptive chord groups so
    # tags reflect the final emitted conditionals
    for idx, (k, w, _) in enumerate(records):
        # split modifier(s) from key literal
        try:
            mod, key = k.rsplit("+", 1)
        except ValueError:
            mod = ""
            key = k

        # determine selected navigation group from when-clause
        sel = None
        if "config.keyboardNavigation.keys.letters == 'emacs'" in w:
            sel = 'emacs'
        elif "config.keyboardNavigation.keys.letters == 'kbm'" in w:
            sel = 'kbm'
        elif "config.keyboardNavigation.keys.letters == 'vi'" in w:
            sel = 'vi'
        else:
            sel = 'none'

        # set ALLOWED_LETTER_KEYS and directional groups for tag calculation
        globals()["SELECTED_NAV_GROUP"] = sel
        if sel == 'none':
            globals()["ALLOWED_LETTER_KEYS"] = set()
        else:
            globals()["ALLOWED_LETTER_KEYS"] = set(LETTER_GROUPS.get(sel, ()))
        init_directional_groups(sel, LETTER_GROUPS)

        # recompute adaptive chord groups for this selection
        def _select_adaptive_key_local(primary_group: set, alternate_key: str) -> str:
            primary_key = sorted(primary_group)[0]
            contains_primary = primary_key in globals().get("ALLOWED_LETTER_KEYS", set())
            contains_alternate = alternate_key in globals().get("ALLOWED_LETTER_KEYS", set())
            if contains_primary and not contains_alternate:
                return alternate_key
            return primary_key

        globals()["ACTION_GROUP"] = {_select_adaptive_key_local(BASE_ACTION_GROUP, ALTERNATE_ACTION_KEY)}
        globals()["DEBUG_GROUP"] = {_select_adaptive_key_local(BASE_DEBUG_GROUP, ALTERNATE_DEBUG_KEY)}
        globals()["EXTENSION_GROUP"] = {_select_adaptive_key_local(BASE_EXTENSION_GROUP, ALTERNATE_EXTENSION_KEY)}

        tags = tags_for(key, mod)
        comment_tags = tags if tags else []
        records[idx] = (k, w, comment_tags)

    out_lines = ["["]
    for i, (k, w, tags) in enumerate(records):
        cmd = f"(corpus) {k} {assigned[i]}"
        obj = emit_record(k, cmd, w, tags)
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


def tags_for(key, mod: str = ""):
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
    if key in SPLIT_HORIZONTAL_GROUP:
        tags.append("(horizontal)")
    if key in SPLIT_VERTICAL_GROUP:
        tags.append("(vertical)")

    if key in DEBUG_GROUP:
        tags.append("(debug)")
    if key in ACTION_GROUP:
        tags.append("(action)")
    if key in EXTENSION_GROUP:
        tags.append("(extension)")

    tags_sorted = [t for t in TAG_ORDER if t in tags]
    return tags_sorted


def when_for(key, mod: str = ""):
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

    def _qualify_chord(chord_set, chord_name: str) -> None:
        # Only qualify chord when modifier includes Alt
        if "alt" not in mod.split("+"):
            return
        if key in chord_set:
            _add(f"config.keyboardNavigation.chords.{chord_name}")
            sel = globals().get("SELECTED_NAV_GROUP")
            if sel and sel != "none":
                _add(f"config.keyboardNavigation.keys.letters == '{sel}'")

    _qualify_chord(DEBUG_GROUP, 'debug')
    _qualify_chord(ACTION_GROUP, 'action')
    _qualify_chord(EXTENSION_GROUP, 'extension')

    return " && ".join(parts)


if __name__ == '__main__':
    raise SystemExit(main())
