#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Generate a deterministic JSONC array of keybinding objects for keyboard navigation development, debugging, and testing.

Usage
    ./bin/keybindings-corpus.py [OPTIONS]

Options
    -n, --navigation-group {emacs,kbm,vi,none,all}  Select the active letter-key navigation group (default: none).
    -c, --comments FILE|none                        Inject canonical comments into an existing JSONC <FILE>, or use 'none' to emit a pure JSON corpus (no comments).

Examples
    ./bin/keybindings-corpus.py > references/keybindings-corpus.jsonc
    ./bin/keybindings-corpus.py --navigation-group vi --comments references/keybindings-corpus-vi.jsonc

Behavior
    - Emits a comprehensive, canonical JSONC array of unique keybinding objects to stdout.
    - Every tag sequence is computed so directional, letter-group, and chord tags stay deterministic.
    - Optionally, inject `[keynav]` annotations into valid keybindings JSONC content read from other files.
    - Uses a fixed hash for reproducible output and never mutates files in place.

Inputs / Outputs
    stdout: JSONC array of keybinding objects encoded as UTF-8 (or modified JSONC file when --comments is supplied).

Exit codes
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
import os
import io
import re

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

# mapping of navigation group name -> tuple (single source of truth)
LETTER_GROUPS = {
    "emacs": EMACS_GROUP,
    "kbm": KBM_GROUP,
    "vi": VI_GROUP,
}

# four pack groups for jukes, moves, jumps, etc.
FOUR_PACK_DOWN_GROUP = {"end", "pagedown"}
FOUR_PACK_UP_GROUP = {"home", "pageup"}
FOUR_PACK_GROUP = FOUR_PACK_DOWN_GROUP | FOUR_PACK_UP_GROUP

# punctuation groups for jukes, moves, jumps, etc.
PUNCTUATION_LEFT_GROUP = {"[", "{", ";", ","}
PUNCTUATION_RIGHT_GROUP = {"]", "}", "'", "."}
PUNCTUATION_GROUP = PUNCTUATION_LEFT_GROUP | PUNCTUATION_RIGHT_GROUP

# based on the `--navigation-group`, letter-keys are injected at runtime by `init_directional_groups`
LEFT_GROUP = set(PUNCTUATION_LEFT_GROUP)
DOWN_GROUP = set(FOUR_PACK_DOWN_GROUP)
UP_GROUP = set(FOUR_PACK_UP_GROUP)
RIGHT_GROUP = set(PUNCTUATION_RIGHT_GROUP)

# map directional tags for groups that always use that direction; index corresponds to ARROW_GROUP order
DIRECTIONAL_GROUP_TAGS = [
    ("(left)", 0, PUNCTUATION_LEFT_GROUP),
    ("(down)", 1, FOUR_PACK_DOWN_GROUP),
    ("(up)", 2, FOUR_PACK_UP_GROUP),
    ("(right)", 3, PUNCTUATION_RIGHT_GROUP),
]

# map directional tags to all of the directional keys
DIRECTIONAL_KEY_TAGS = {
    tag: {ARROW_GROUP[idx]} | extra_keys | {
        group[idx] for group in LETTER_GROUPS.values() if idx < len(group)
    }
    for tag, idx, extra_keys in DIRECTIONAL_GROUP_TAGS
}

# juke group
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

# FIN tag mapping: modifier -> (color-tag, (meta-tags...))
FIN_TAGS = {
    "alt": ("(gold)", ("(self)", "(0)", "(gold)", "(X)")),
    "shift+alt": ("(red)", ("(move)", "(1)", "(red)", "(A)")),
    "ctrl+alt": ("(blue)", ("(jump)", "(2)", "(blue)", "(B)")),
    "ctrl+alt+meta": ("(black)", ("(warp)", "(3)", "(black)", "(C)")),
    "ctrl+shift+alt": ("(yellow)", ("(change)", "(!)", "(yellow)", "(+)")),
}

# order of tags for deterministic output
TAG_ORDER = [
    # D(irection, Heading, or Intent)
    "(down)", "(left)", "(right)", "(up)",
    "(horizontal)", "(vertical)",

    # A(ction/Key Group)

    "(arrow)", "(emacs)", "(kbm)", "(vi)",
    "(juke)", "(split)",
    "(move)", "(jump)", "(warp)", "(change)", "(assign)",
    "(!)",

    # F(ocus)
    "(0)", "(1)", "(2)", "(3)",
    "(self)",

    # C(olors, Characters, Chords, and/or Coordinates)
    "(gold)", "(red)", "(blue)", "(black)", "(yellow)",

    "(X)", "(A)", "(B)", "(C)",
    "(+)",

    "(debug)", "(action)", "(extension)",
    "(chord)",

    "(primary)", "(secondary)", "(panel)",
    "(editor)", "(terminal)", "(explorer)",

    # D(etails)
    "(readonly)",
]

# patterns that start and end with '/' are treated as regular expressions
WHEN_TAG_SELECTORS = [
    ("auxiliarBarFocus", "(secondary)"),
    ("editorFocus", "(editor)"),
    ("editorTextFocus", "(editor)"),
    ("panelFocus", "(panel)"),
    ("sideBarFocus", "(primary)"),
    ("terminalFocus", "(terminal)"),
    ("/Readonly/", "(readonly)"),
    # ("explorerViewletVisible", "(explorer)"),
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
    subordinates can continue to read globals.
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
        choices=list(LETTER_GROUPS.keys()) + ["none", "all"],
        default="none",
        help=(
            "Select the active letter-key navigation group (default: none)."
        ),
    )
    parser.add_argument(
        "-c",
        "--comments",
        metavar='FILE|none',
        help=("Inject canonical comments into an existing JSONC <FILE>, or use 'none' to emit a pure JSON corpus (no comments)."),
    )
    args = parser.parse_args(argv)

    # determine selected letter-group from a when-clause
    def sel_from_when(when_val: str) -> str:
        for name in LETTER_GROUPS.keys():
            if f"config.keyboardNavigation.keys.letters == '{name}'" in when_val:
                return name
        return 'none'

    # comments mode: None (default) | 'none' | filename
    comments_arg = args.comments

    if comments_arg and comments_arg != 'none':
        fname = comments_arg
        if not os.path.exists(fname) or not os.access(fname, os.R_OK):
            print(
                f"error: comments file '{fname}' does not exist or is not readable", file=sys.stderr)
            return 2

        original_text = None
        try:
            with open(fname, 'r', encoding='utf-8') as fh:
                original_text = fh.read()
        except Exception as e:
            print(f"error: failed to read '{fname}': {e}", file=sys.stderr)
            return 2

        # strip JSONC comments safely (state-machine)
        def strip_jsonc(text: str) -> str:
            out = []
            i = 0
            n = len(text)
            in_string = False
            string_char = ''
            esc = False
            in_line = False
            in_block = False
            while i < n:
                ch = text[i]
                nxt2 = text[i:i+2] if i+2 <= n else ''
                if in_line:
                    if ch == '\n':
                        out.append(ch)
                        in_line = False
                    i += 1
                    continue
                if in_block:
                    if nxt2 == '*/':
                        i += 2
                        in_block = False
                    else:
                        i += 1
                    continue
                if in_string:
                    out.append(ch)
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == string_char:
                        in_string = False
                    i += 1
                    continue
                # default
                if nxt2 == '//':
                    in_line = True
                    i += 2
                    continue
                if nxt2 == '/*':
                    in_block = True
                    i += 2
                    continue
                if ch == '"' or ch == "'":
                    in_string = True
                    string_char = ch
                    out.append(ch)
                    i += 1
                    continue
                out.append(ch)
                i += 1
            return ''.join(out)

        def _extract_preamble_postamble(text: str):
            i = 0
            n = len(text)
            in_string = False
            string_char = ''
            esc = False
            in_line_comment = False
            in_block_comment = False
            start = -1

            while i < n:
                ch = text[i]
                nxt2 = text[i:i+2] if i+2 <= n else ''

                if in_line_comment:
                    if ch == '\n':
                        in_line_comment = False
                    i += 1
                    continue
                if in_block_comment:
                    if nxt2 == '*/':
                        i += 2
                        in_block_comment = False
                    else:
                        i += 1
                    continue
                if nxt2 == '//':
                    in_line_comment = True
                    i += 2
                    continue
                if nxt2 == '/*':
                    in_block_comment = True
                    i += 2
                    continue
                if ch == '"' or ch == "'":
                    in_string = True
                    string_char = ch
                    i += 1

                    # enter string state and skip until close
                    while i < n:
                        c = text[i]
                        if c == '\\':
                            i += 2
                            continue
                        if c == string_char:
                            i += 1
                            break
                        i += 1
                    continue
                if ch == '[':
                    start = i
                    break
                i += 1

            if start == -1:
                return None

            # find matching ]
            depth = 1
            i = start + 1
            in_string = False
            string_char = ''
            in_line_comment = False
            in_block_comment = False
            while i < n:
                ch = text[i]
                nxt2 = text[i:i+2] if i+2 <= n else ''
                if in_line_comment:
                    if ch == '\n':
                        in_line_comment = False
                    i += 1
                    continue
                if in_block_comment:
                    if nxt2 == '*/':
                        i += 2
                        in_block_comment = False
                    else:
                        i += 1
                    continue
                if ch == '"' or ch == "'":
                    in_string = True
                    string_char = ch
                    i += 1
                    while i < n:
                        c = text[i]
                        if c == '\\':
                            i += 2
                            continue
                        if c == string_char:
                            i += 1
                            break
                        i += 1
                    continue
                if nxt2 == '//':
                    in_line_comment = True
                    i += 2
                    continue
                if nxt2 == '/*':
                    in_block_comment = True
                    i += 2
                    continue
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i
                        preamble = text[:start]
                        array_text = text[start+1:end]
                        postamble = text[end+1:]
                        return preamble, array_text, postamble
                i += 1
            return None

        def _group_objects_with_comments(array_text: str):
            groups = []
            comments_buf = ''
            obj_buf = ''
            depth = 0
            in_obj = False
            for line in array_text.splitlines(keepends=True):
                stripped = line.strip()
                if not in_obj:
                    if stripped.startswith('//') or stripped.startswith('/*'):
                        comments_buf += line
                        continue
                    if '{' in line:
                        in_obj = True
                        obj_buf = line
                        # if line contains '}' too, handle short objects
                        if '}' in line and line.index('}') > line.index('{'):
                            groups.append((comments_buf, obj_buf))
                            comments_buf = ''
                            obj_buf = ''
                            in_obj = False
                        continue
                    # ignore blank or comma lines
                    if stripped == '' or stripped == ',':
                        continue
                    # fallback: accumulate as comments
                    comments_buf += line
                else:
                    obj_buf += line
                    if '}' in line:
                        # crude close detection; rely on JSON parse later for exactness
                        groups.append((comments_buf, obj_buf))
                        comments_buf = ''
                        obj_buf = ''
                        in_obj = False
            trailing = comments_buf
            return groups, trailing

        ACTION_GROUP_ORIG = set(ACTION_GROUP)
        DEBUG_GROUP_ORIG = set(DEBUG_GROUP)
        EXTENSION_GROUP_ORIG = set(EXTENSION_GROUP)

        # remove trailing commas (safe)
        def _strip_trailing_commas(text: str) -> str:
            return re.sub(r',\s*([}\]])', r"\1", text)

        # parse the JSONC into JSON
        try:
            stripped = strip_jsonc(original_text)
            stripped = _strip_trailing_commas(stripped)
            parsed = json.loads(stripped)
        except Exception as e:
            print(
                f"error: failed to parse JSONC from '{fname}': {e}", file=sys.stderr)
            return 2

        if not isinstance(parsed, list):
            print(
                f"error: top-level JSON value in '{fname}' is not an array", file=sys.stderr)
            return 2

        preamble_res = _extract_preamble_postamble(original_text)
        if not preamble_res:
            print(
                f"error: could not locate top-level array in '{fname}'", file=sys.stderr)
            return 2
        preamble, array_text, postamble = preamble_res
        groups, trailing_comments = _group_objects_with_comments(array_text)
        if len(groups) != len(parsed):
            print(
                f"error: mismatch between parsed array length ({len(parsed)}) and detected object groups ({len(groups)}) in '{fname}'", file=sys.stderr)
            return 2

        # compute comment lines for each object
        comments_lines = []
        for idx, obj in enumerate(parsed):
            if not isinstance(obj, dict):
                print(
                    f"error: array element {idx} in '{fname}' is not an object", file=sys.stderr)
                return 2
            key_val = obj.get('key')
            when_val = obj.get('when')
            if not isinstance(key_val, str) or not isinstance(when_val, str):
                print(
                    f"error: object at index {idx} missing 'key' or 'when' (or not strings) in '{fname}'", file=sys.stderr)
                return 2

            try:
                mod, literal_key = key_val.rsplit('+', 1)
            except ValueError:
                mod = ''
                literal_key = key_val

            sel = sel_from_when(when_val)

            globals()["SELECTED_NAV_GROUP"] = sel
            if sel == 'none':
                globals()["ALLOWED_LETTER_KEYS"] = set()
            else:
                globals()["ALLOWED_LETTER_KEYS"] = set(
                    LETTER_GROUPS.get(sel, ()))
            init_directional_groups(sel, LETTER_GROUPS)

            # recompute adaptive chord groups
            def _select_adaptive_key_local(primary_group: set, alternate_key: str) -> str:
                primary_key = sorted(primary_group)[0]
                contains_primary = primary_key in globals().get("ALLOWED_LETTER_KEYS", set())
                contains_alternate = alternate_key in globals().get("ALLOWED_LETTER_KEYS", set())
                if contains_primary and not contains_alternate:
                    return alternate_key
                return primary_key

            globals()["ACTION_GROUP"] = {_select_adaptive_key_local(ACTION_GROUP_ORIG, ALTERNATE_ACTION_KEY)}
            globals()["DEBUG_GROUP"] = {_select_adaptive_key_local(DEBUG_GROUP_ORIG, ALTERNATE_DEBUG_KEY)}
            globals()["EXTENSION_GROUP"] = {_select_adaptive_key_local(EXTENSION_GROUP_ORIG, ALTERNATE_EXTENSION_KEY)}

            tags = tags_for(literal_key, mod, when_val)
            if tags:
                comment_line = "// " + " ".join(tags)
            else:
                comment_line = ''
            comments_lines.append(comment_line)

        # inject comments into original text (in-memory) and print to stdout
        out_text = original_text
        offset = 0
        search_pos = original_text.find('[')
        for (comments_blob, obj_text), comment_line, obj in zip(groups, comments_lines, parsed):
            if not comment_line:
                continue

            obj_index = out_text.find(obj_text, search_pos)
            if obj_index == -1:
                # fallback: try to locate by key only
                k = obj.get('key')
                key_marker = f'"key": "{k}"'
                key_pos = out_text.find(key_marker, search_pos)
                if key_pos == -1:
                    print(
                        f"warning: could not locate object for key {k!r}; skipping injection", file=sys.stderr)
                    continue

                brace_pos = out_text.rfind('{', 0, key_pos)
                if brace_pos == -1:
                    print(
                        f"warning: could not find object brace for key {k!r}; skipping injection", file=sys.stderr)
                    continue
                obj_start = brace_pos
                obj_end = out_text.find('}', obj_start)
                if obj_end == -1:
                    print(
                        f"warning: could not find object end for key {k!r}; skipping injection", file=sys.stderr)
                    continue
                obj_fragment = out_text[obj_start:obj_end+1]
            else:
                obj_start = obj_index
                obj_end = obj_start + len(obj_text) - 1
                obj_fragment = out_text[obj_start:obj_end+1]

            # if exact comment exists anywhere in the object (compare stripped lines) then skip
            exists = False
            for line in obj_fragment.splitlines():
                if line.strip() == comment_line.strip():
                    exists = True
                    break
            if exists:
                search_pos = obj_end + 1
                continue

            # find the first occurrence of "key" attribute inside this object text
            m = re.search(r'"key"\s*:\s*', obj_fragment)
            if not m:
                print(
                    f"warning: could not find 'key' attribute inside object for key {obj.get('key')!r}; skipping", file=sys.stderr)
                search_pos = obj_end + 1
                continue
            key_pos_in_fragment = m.start()
            key_pos = obj_start + key_pos_in_fragment

            # find start of the line containing key_pos
            line_start = out_text.rfind('\n', 0, key_pos)
            if line_start == -1:
                insert_pos = 0
            else:
                insert_pos = line_start + 1

            # determine indentation of the key line
            indentation = ''
            if insert_pos < len(out_text):
                indentation = out_text[insert_pos:key_pos]
                indentation = re.match(r'[ \t]*', indentation).group(0)

            insert_text = indentation + comment_line + '\n'
            out_text = out_text[:insert_pos] + \
                insert_text + out_text[insert_pos:]

            # advance search position past this object to avoid matching earlier duplicates
            search_pos = obj_end + len(insert_text) + 1

        # print modified text to stdout
        sys.stdout.write(out_text)
        return 0

    selected = args.navigation_group

    # expose letter-groups and selected mode for subordinates
    globals()["LETTER_GROUPS"] = LETTER_GROUPS
    globals()["SELECTED_NAV_GROUP"] = selected
    if selected == "none" or selected == "all":
        allowed_letter_keys = set()
    else:
        allowed_letter_keys = set(LETTER_GROUPS[selected])

    globals()["ALLOWED_LETTER_KEYS"] = allowed_letter_keys

    init_directional_groups(selected, LETTER_GROUPS)

    # preserve the original chord groups
    ACTION_GROUP_ORIG = set(ACTION_GROUP)
    DEBUG_GROUP_ORIG = set(DEBUG_GROUP)
    EXTENSION_GROUP_ORIG = set(EXTENSION_GROUP)

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

        # apply adaptive chord key selection based on mode
        globals()["ACTION_GROUP"] = {
            _select_adaptive_key(
                ACTION_GROUP_ORIG, ALTERNATE_ACTION_KEY, "action")
        }
        globals()["DEBUG_GROUP"] = {
            _select_adaptive_key(
                DEBUG_GROUP_ORIG, ALTERNATE_DEBUG_KEY, "debug")
        }
        globals()["EXTENSION_GROUP"] = {
            _select_adaptive_key(EXTENSION_GROUP_ORIG, ALTERNATE_EXTENSION_KEY, "extension")
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

                SELECTED_NAV_GROUP_STATE = globals().get("SELECTED_NAV_GROUP")
                ALLOWED_LETTER_KEYS_STATE = globals().get("ALLOWED_LETTER_KEYS")

                LEFT_GROUP_STATE = set(globals().get("LEFT_GROUP", set()))
                DOWN_GROUP_STATE = set(globals().get("DOWN_GROUP", set()))
                UP_GROUP_STATE = set(globals().get("UP_GROUP", set()))
                RIGHT_GROUP_STATE = set(globals().get("RIGHT_GROUP", set()))

                ACTION_GROUP_STATE = set(globals().get("ACTION_GROUP", set()))
                DEBUG_GROUP_STATE = set(globals().get("DEBUG_GROUP", set()))
                EXTENSION_GROUP_STATE = set(
                    globals().get("EXTENSION_GROUP", set()))

                globals()["SELECTED_NAV_GROUP"] = "none"
                globals()["ALLOWED_LETTER_KEYS"] = set()

                globals()["ACTION_GROUP"] = set()
                globals()["DEBUG_GROUP"] = set()
                globals()["EXTENSION_GROUP"] = set()

                init_directional_groups("none", LETTER_GROUPS)
                generic_when = when_for(key, mod)

                # restore selected / letter / directional groups
                globals()["SELECTED_NAV_GROUP"] = SELECTED_NAV_GROUP_STATE
                globals()["ALLOWED_LETTER_KEYS"] = ALLOWED_LETTER_KEYS_STATE
                globals()["LEFT_GROUP"] = LEFT_GROUP_STATE
                globals()["DOWN_GROUP"] = DOWN_GROUP_STATE
                globals()["UP_GROUP"] = UP_GROUP_STATE
                globals()["RIGHT_GROUP"] = RIGHT_GROUP_STATE

                # restore chord state
                globals()["ACTION_GROUP"] = ACTION_GROUP_STATE
                globals()["DEBUG_GROUP"] = DEBUG_GROUP_STATE
                globals()["EXTENSION_GROUP"] = EXTENSION_GROUP_STATE

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

                for this_when in emitted_whens:
                    pair = (key_str, this_when)
                    if pair not in local_seen:
                        local_seen.add(pair)
                        recs.append((key_str, this_when, comment_tags))

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

                            combined_when = this_when + \
                                " && " + " && ".join(combo)
                            pair = (key_str, combined_when)
                            if pair not in local_seen:
                                local_seen.add(pair)
                                recs.append(
                                    (key_str, combined_when, comment_tags))

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

    # if comments_arg == 'none', emit pure JSON (no comments) and exit.
    if comments_arg == 'none':
        out_list = []
        for i, (k, w, _) in enumerate(records):
            cmd = f"(corpus) {k} {assigned[i]}"
            out_list.append({"key": k, "command": cmd, "when": w})
        sys.stdout.write(json.dumps(
            out_list, indent=2, ensure_ascii=False) + "\n")
        return 0

    for idx, (k, w, _) in enumerate(records):
        # split modifier(s) from key literal
        try:
            mod, key = k.rsplit("+", 1)
        except ValueError:
            mod = ""
            key = k

        sel = sel_from_when(w)

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

        globals()["ACTION_GROUP"] = {_select_adaptive_key_local(ACTION_GROUP_ORIG, ALTERNATE_ACTION_KEY)}
        globals()["DEBUG_GROUP"] = {_select_adaptive_key_local(DEBUG_GROUP_ORIG, ALTERNATE_DEBUG_KEY)}
        globals()["EXTENSION_GROUP"] = {_select_adaptive_key_local(EXTENSION_GROUP_ORIG, ALTERNATE_EXTENSION_KEY)}

        tags = tags_for(key, mod, w)
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


def tags_for(key: str, mod: str = "", when_clause: str | None = None) -> List[str]:
    if not when_clause or "config.keyboardNavigation.enabled" not in when_clause:
        return []

    ordered_tags: List[str] = ["[keynav]"]
    dynamic_tags: set[str] = set()

    nav_group_clauses = {
        name
        for name in LETTER_GROUPS
        if f"config.keyboardNavigation.keys.letters == '{name}'" in when_clause
    }

    for tag, keys in DIRECTIONAL_KEY_TAGS.items():
        if key not in keys:
            continue
        if key in ARROW_GROUP or key in PUNCTUATION_GROUP:
            dynamic_tags.add(tag)
            continue
        if any(key in LETTER_GROUPS[name] for name in nav_group_clauses):
            dynamic_tags.add(tag)

    if "config.keyboardNavigation.keys.arrows" in when_clause:
        dynamic_tags.add("(arrow)")

    for name in LETTER_GROUPS:
        clause = f"config.keyboardNavigation.keys.letters == '{name}'"
        if clause in when_clause:
            dynamic_tags.add(f"({name})")

    if key in JUKE_GROUP:
        dynamic_tags.add("(juke)")
    if key in SPLIT_GROUP:
        dynamic_tags.add("(split)")
    if key in SPLIT_HORIZONTAL_GROUP:
        dynamic_tags.add("(horizontal)")
    if key in SPLIT_VERTICAL_GROUP:
        dynamic_tags.add("(vertical)")

    if "config.keyboardNavigation.chords.debug" in when_clause:
        dynamic_tags.add("(debug)")
    if "config.keyboardNavigation.chords.action" in when_clause:
        dynamic_tags.add("(action)")
    if "config.keyboardNavigation.chords.extension" in when_clause:
        dynamic_tags.add("(extension)")

    fin_entry = FIN_TAGS.get(mod)
    if fin_entry:
        color_tag, meta_tags = fin_entry
        if color_tag:
            dynamic_tags.add(color_tag)
        if meta_tags:
            for t in meta_tags:
                dynamic_tags.add(t)

    if when_clause and "config.keyboardNavigation.chords." in when_clause:
        dynamic_tags.add("(chord)")

    # context-based tags: map substrings or regexes in the when-clause to tags
    if when_clause:
        for pattern, tag in WHEN_TAG_SELECTORS:
            if pattern.startswith("/") and pattern.endswith("/"):
                regex = pattern[1:-1]
                try:
                    if re.search(regex, when_clause):
                        dynamic_tags.add(tag)
                except re.error:
                    # ignore bad regexes; should probably emit a warning here ...
                    pass
            else:
                # avoid matching negated occurrences like '!editorFocus'
                try:
                    # search for whole-word occurrence not immediately preceded by '!'
                    regex = rf"(?<!\!)\b{re.escape(pattern)}\b"
                    if re.search(regex, when_clause):
                        dynamic_tags.add(tag)
                except re.error:
                    # fallback to simple substring match on regex error
                    if pattern in when_clause:
                        dynamic_tags.add(tag)

    ordered_tags.extend([tag for tag in TAG_ORDER if tag in dynamic_tags])

    # append any remaining dynamic tags not listed in TAG_ORDER, sorted alphabetically
    remaining = sorted(t for t in dynamic_tags if t not in TAG_ORDER)
    ordered_tags.extend(remaining)

    return ordered_tags


def when_for(key, mod: str = ""):
    parts = ["config.keyboardNavigation.enabled"]
    seen = set()

    def _add(cond: str) -> None:
        if cond not in seen:
            parts.append(cond)
            seen.add(cond)

    if key in ARROW_GROUP:
        _add("config.keyboardNavigation.keys.arrows")

    for name, group in LETTER_GROUPS.items():
        if key in group and key in globals().get("ALLOWED_LETTER_KEYS", set()):
            _add(f"config.keyboardNavigation.keys.letters == '{name}'")

    # qualify a chord when it's a valid combination defined in MODIFIERS_SINGLE or MODIFIERS_MULTI
    def _qualify_chord(chord_set, chord_name: str) -> None:
        allowed_mods = set(MODIFIERS_SINGLE) | set(MODIFIERS_MULTI)
        if mod not in allowed_mods:
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
