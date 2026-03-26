#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Generate a deterministic JSONC array of keybinding objects for keyboard navigation development, debugging, and testing.

Usage
    keybindings-corpus.py [OPTIONS]

Options
    -a, --add-context [WHEN]                        Add auto-derived context to emitted when clauses.
    -c, --comments FILE|none                        Inject canonical comments into an existing JSONC <FILE>, or use 'none' to emit a pure JSON corpus (no comments).
    -n, --navigation-group {emacs,kbm,vi,none,all}  Use the given letter-key navigation group (default: none).

Examples
    keybindings-corpus.py > references/keybindings-corpus.jsonc
    keybindings-corpus.py --navigation-group vi --comments references/keybindings-corpus-vi.jsonc
    keybindings-corpus.py --navigation-group vi --add-context --comments references/keybindings-corpus-vi.jsonc
    keybindings-corpus.py --add-context 'jjtIsHere && iWasCoding'
    keybindings-corpus.py --add-context "editorTextFocus && !inputFocus"

Behavior
    - Emits a comprehensive, canonical JSONC array of unique keybinding objects to stdout.
    - Every tag sequence is computed so directional, letter-group, and chord tags stay deterministic.
    - Optionally, inject `[keynav]` annotations into valid keybindings JSONC content read from other files.
    - Optionally, append feature-gate and caller-supplied when-context clauses to matching emitted objects.
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

from itertools import combinations
from typing import List, Tuple
from collections import Counter

import hashlib
import inspect
import os
import re

from vscode_keynav import io as _io
from vscode_keynav import corpus as _corpus
from vscode_keynav import keybindings as _keybindings


#
# function definitions
#


def _augment_when_clause(key: str, when_clause: str, extra_context: str | None = None) -> str:
    parts: List[str] = []
    seen: set[str] = set()

    def _add_many(values: List[str]) -> None:
        for value in values:
            if not value:
                continue
            v = value.strip()
            if not v:
                continue
            if v in seen:
                continue
            parts.append(v)
            seen.add(v)

    _add_many(_keybindings._split_when_contexts(when_clause))

    # always consider corpus selectors (e.g., juke/split/arrows)
    key_norm = _keybindings._normalize_key(key)
    for group, context in _corpus._WHEN_CONTEXT_SELECTORS:
        try:
            group_set = set(group)
        except Exception:
            group_set = {g for g in group}
        if key_norm in group_set:
            _add_many([context])

    # append caller-supplied extra contexts if present
    if extra_context is not None:
        _add_many(_keybindings._split_when_contexts(extra_context))

    return " && ".join(parts)


def _emit_record(key_str, command_str, when_str, comment_tags):
    parts = []
    parts.append("  {")
    if comment_tags:
        parts.append("    // " + " ".join(comment_tags))
    parts.append(f'    "key": {json.dumps(key_str)},')
    parts.append(f'    "command": {json.dumps(command_str)},')
    parts.append(f'    "when": {json.dumps(when_str)}')
    parts.append("  }")
    return "\n".join(parts)


def _init_directional_groups(selected: str, letter_groups: dict) -> None:
    """Ensure globals include the arrow literal and the corresponding letter from the selected navigation group (if any)."""

    direction_to_var = {
        "left": "_LEFT_GROUP",
        "down": "_DOWN_GROUP",
        "up": "_UP_GROUP",
        "right": "_RIGHT_GROUP",
    }

    for i, direction_name in enumerate(_corpus._ARROW_GROUP):
        var_name = direction_to_var[direction_name]
        current = set(globals().get(var_name, set()))

        # always include the arrow literal (e.g., "left")
        current.add(direction_name)

        if selected != "none" and selected in letter_groups:
            group = letter_groups[selected]
            if i < len(group):
                current.add(group[i])
        globals()[var_name] = current


#
# main
#


def _main(argv: List[str] | None = None) -> int:
    """Run the keybindings-corpus CLI and return an exit code."""

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
        "-a",
        "--add-context",
        nargs="?",
        const="",
        metavar="WHEN",
        help=(
            "Add auto-derived context to emitted when clauses."
        ),
    )

    parser.add_argument(
        "-c",
        "--comments",
        metavar='FILE|none',
        help=(
            "Inject canonical comments into an existing JSONC <FILE>, or use 'none' to emit a pure JSON corpus (no comments)."
        ),
    )

    parser.add_argument(
        "-n",
        "--navigation-group",
        choices=list(_corpus._LETTER_GROUPS.keys()) + ["none", "all"],
        default="none",
        help=(
            "Select the active letter-key navigation group (default: none)."
        ),
    )

    args = parser.parse_args(argv)

    # determine selected letter-group from a when-clause
    def _sel_from_when(when_val: str) -> str:
        """Return the selected navigation group name from a when-clause."""

        for name in _corpus._LETTER_GROUPS.keys():
            if f"config.keyboardNavigation.keys.letters == '{name}'" in when_val:
                return name
        return 'none'

    # comments mode: None (default) | 'none' | filename
    comments_arg = args.comments
    add_context_arg = args.add_context

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

        def _preview_for_error(obj, src_text: str | None = None, max_len: int = 1000) -> str:
            if src_text:
                text = src_text.strip()
            else:
                try:
                    text = json.dumps(obj, ensure_ascii=False)
                except Exception:
                    text = repr(obj)
            if len(text) > max_len:
                return text[:max_len] + "...<truncated>"
            return text

        ACTION_GROUP_ORIG = set(_corpus._ACTION_GROUP)
        DEBUG_GROUP_ORIG = set(_corpus._DEBUG_GROUP)
        EXTENSION_GROUP_ORIG = set(_corpus._EXTENSION_GROUP)

        # remove trailing commas (safe)
        def _strip_trailing_commas(text: str) -> str:
            """Delegate to package trailing-comma stripper."""
            return _keybindings._strip_trailing_commas(text)

        # parse the JSONC into JSON
        try:
            stripped = _keybindings._strip_json_comments(original_text)
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

        preamble_res = _keybindings._extract_preamble_postamble(original_text)
        if not preamble_res:
            print(
                f"error: could not locate top-level array in '{fname}'", file=sys.stderr)
            return 2
        preamble, array_text, postamble = preamble_res
        array_start_line = preamble.count('\n') + 1
        groups, trailing_comments = _keybindings._group_objects_with_comments(array_text, base_line=array_start_line)
        if len(groups) != len(parsed):
            print(f"error: mismatch between parsed array length ({len(parsed)}) and detected object groups ({len(groups)}) in '{fname}'", file=sys.stderr)
            return 2

        # compute transformed when values and comment lines for each object
        transformed_whens = []
        comments_lines = []
        for idx, obj in enumerate(parsed):
            src_line = groups[idx][2] if idx < len(groups) else None
            src_obj_text = groups[idx][1] if idx < len(groups) else None

            if not isinstance(obj, dict):
                line_suffix = f" at line {src_line}" if src_line is not None else ""
                preview = _preview_for_error(obj, src_obj_text)
                print(
                    f"error: array element {idx}{line_suffix} in '{fname}' is not an object\n"
                    f"offending value: {preview}",
                    file=sys.stderr,
                )
                return 2

            key_val = obj.get('key')
            when_val = obj.get('when')
            if not isinstance(key_val, str) or not isinstance(when_val, str):
                line_suffix = f" at line {src_line}" if src_line is not None else ""
                preview = _preview_for_error(obj, src_obj_text)
                print(
                    f"error: object at index {idx}{line_suffix} missing 'key' or 'when' (or not strings) in '{fname}'\n"
                    f"offending object: {preview}",
                    file=sys.stderr,
                )
                return 2

            try:
                mod, literal_key = key_val.rsplit('+', 1)
                # handle trailing '+' meaning the literal key is '+' (e.g., 'alt++')
                if literal_key == '':
                    mod = mod.rstrip('+')
                    literal_key = '+'
            except ValueError:
                mod = ''
                literal_key = key_val

            sel = _sel_from_when(when_val)

            globals()["_SELECTED_NAV_GROUP"] = sel
            if sel == 'none':
                globals()["_ALLOWED_LETTER_KEYS"] = set()
            else:
                globals()["_ALLOWED_LETTER_KEYS"] = set(
                    _corpus._LETTER_GROUPS.get(sel, ()))
            _init_directional_groups(sel, _corpus._LETTER_GROUPS)

            # recompute adaptive chord groups
            def _select_adaptive_key_local(primary_group: set, alternate_key: str) -> str:
                primary_key = sorted(primary_group)[0]
                contains_primary = primary_key in globals().get("_ALLOWED_LETTER_KEYS", set())
                contains_alternate = alternate_key in globals().get("_ALLOWED_LETTER_KEYS", set())
                if contains_primary and not contains_alternate:
                    return alternate_key
                return primary_key

            globals()["_ACTION_GROUP"] = {_select_adaptive_key_local(ACTION_GROUP_ORIG, _corpus._ALTERNATE_ACTION_KEY)}
            globals()["_DEBUG_GROUP"] = {_select_adaptive_key_local(DEBUG_GROUP_ORIG, _corpus._ALTERNATE_DEBUG_KEY)}
            globals()["_EXTENSION_GROUP"] = {_select_adaptive_key_local(EXTENSION_GROUP_ORIG, _corpus._ALTERNATE_EXTENSION_KEY)}

            if idx < len(groups):
                lead_comments, obj_text, _obj_line = groups[idx]
                existing_comments_blob = (lead_comments or "") + "\n" + (obj_text or "")
            else:
                existing_comments_blob = None

            effective_when = _augment_when_clause(
                literal_key,
                when_val,
                add_context_arg,
            )
            tags = _corpus._tags_for(
                literal_key,
                mod,
                effective_when,
                command=obj.get('command'),
                existing_comments=existing_comments_blob,
            )
            if tags:
                comment_line = "// " + " ".join(tags)
            else:
                comment_line = ''
            transformed_whens.append(effective_when)
            comments_lines.append(comment_line)

        # inject when updates and comments into original text (in-memory) and print to stdout
        out_text = original_text
        offset = 0
        search_pos = original_text.find('[')
        for (_comments_blob, obj_text, _obj_line), effective_when, comment_line, obj in zip(
            groups, transformed_whens, comments_lines, parsed
        ):
            if not comment_line:
                pass

            obj_index = out_text.find(obj_text, search_pos)
            if obj_index == -1:
                # fallback: locate by key only
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
                obj_fragment = out_text[obj_start:obj_end + 1]
            else:
                obj_start = obj_index
                obj_end = obj_start + len(obj_text) - 1
                obj_fragment = out_text[obj_start:obj_end + 1]

            when_match = re.search(r'("when"\s*:\s*)("(?:\\.|[^"\\])*")', obj_fragment)
            if when_match:
                serialized_when = json.dumps(effective_when)
                new_obj_fragment = (
                    obj_fragment[:when_match.start(2)]
                    + serialized_when
                    + obj_fragment[when_match.end(2):]
                )
                if new_obj_fragment != obj_fragment:
                    out_text = out_text[:obj_start] + new_obj_fragment + out_text[obj_end + 1:]
                    obj_fragment = new_obj_fragment
                    obj_end = obj_start + len(obj_fragment) - 1

            # if exact comment exists anywhere in the object (compare stripped lines) then skip
            exists = False
            for line in obj_fragment.splitlines():
                if line.strip() == comment_line.strip():
                    exists = True
                    break
            if exists or not comment_line:
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
            if insert_pos < len(out_text):
                m_indent = re.match(r'[ \t]*', out_text[insert_pos:key_pos])
                indentation = m_indent.group(0) if m_indent else ''
            else:
                indentation = ''

            insert_text = indentation + comment_line + '\n'
            out_text = out_text[:insert_pos] + \
                insert_text + out_text[insert_pos:]

            # advance search position past this object to avoid matching earlier duplicates
            search_pos = obj_end + len(insert_text) + 1

        # final corrective pass: ensure injected objects contain their computed when clauses
        def _find_matching_brace_in_text(text: str, start_idx: int) -> int:
            i = start_idx
            n = len(text)
            depth = 0
            in_string = False
            string_char = ''
            esc = False
            in_line = False
            in_block = False
            while i < n:
                ch = text[i]
                nxt2 = text[i:i + 2] if i + 2 <= n else ''
                if in_line:
                    if ch == '\n':
                        in_line = False
                    i += 1
                    continue
                if in_block:
                    if nxt2 == '*/':
                        i += 2
                        in_block = False
                        continue
                    i += 1
                    continue
                if in_string:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == string_char:
                        in_string = False
                    i += 1
                    continue
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
                    i += 1
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return i
                i += 1
            return -1

        # for each parsed object, verify the out_text fragment contains the expected effective_when
        search_pos = 0
        for (_comments_blob, obj_text, _obj_line), effective_when, comment_line, obj in zip(
            groups, transformed_whens, comments_lines, parsed
        ):
            obj_index = out_text.find(obj_text, search_pos)
            if obj_index == -1:
                # fallback to locate by key only
                k = obj.get('key')
                key_marker = f'"key": "{k}"'
                key_pos = out_text.find(key_marker, search_pos)
                if key_pos == -1:
                    continue
                brace_pos = out_text.rfind('{', 0, key_pos)
                if brace_pos == -1:
                    continue
                obj_start = brace_pos
            else:
                obj_start = obj_index
            obj_end = _find_matching_brace_in_text(out_text, obj_start)
            if obj_end == -1:
                continue
            obj_fragment = out_text[obj_start:obj_end + 1]

            # ensure _corpus._WHEN_CONTEXT_SELECTORS matching this key are present
            if add_context_arg is not None:
                # recompute literal key and normalize
                k_full = obj.get('key')
                try:
                    mmod, literal_key = k_full.rsplit('+', 1)
                    if literal_key == '':
                        mmod = mmod.rstrip('+')
                        literal_key = '+'
                except Exception:
                    mmod = ''
                    literal_key = k_full

                key_norm = _keybindings._normalize_key(literal_key)

                # collect missing contexts
                missing_ctxs: list = []
                for group, ctx in _corpus._WHEN_CONTEXT_SELECTORS:
                    if key_norm in {str(g) for g in group}:
                        if ctx not in effective_when:
                            missing_ctxs.append(ctx)

                if missing_ctxs:
                    # merge them into effective_when
                    if effective_when and effective_when.strip():
                        new_effective = effective_when + " && " + " && ".join(missing_ctxs)
                    else:
                        new_effective = " && ".join(missing_ctxs)
                    # attempt robust replacement of the "when" value
                    when_match = re.search(r'("when"\s*:\s*)("(?:\\.|[^"\\])*")', obj_fragment)
                    if when_match:
                        serialized_when = json.dumps(new_effective)
                        new_obj_fragment = (
                            obj_fragment[:when_match.start(2)]
                            + serialized_when
                            + obj_fragment[when_match.end(2):]
                        )
                        out_text = out_text[:obj_start] + new_obj_fragment + out_text[obj_end + 1:]
                        # advance search_pos to avoid reprocessing earlier objects
                        search_pos = obj_start + len(new_obj_fragment)
                        continue
            # advance search_pos if we didn't replace
            search_pos = obj_end + 1

        sys.stdout.write(out_text)
        return 0

    selected = args.navigation_group

    # expose selected mode for subordinates
    globals()["_SELECTED_NAV_GROUP"] = selected
    if selected == "none" or selected == "all":
        allowed_letter_keys = set()
    else:
        allowed_letter_keys = set(_corpus._LETTER_GROUPS[selected])

    globals()["_ALLOWED_LETTER_KEYS"] = allowed_letter_keys

    _init_directional_groups(selected, _corpus._LETTER_GROUPS)

    # preserve the original chord groups

    ACTION_GROUP_ORIG = set(_corpus._ACTION_GROUP)
    DEBUG_GROUP_ORIG = set(_corpus._DEBUG_GROUP)
    EXTENSION_GROUP_ORIG = set(_corpus._EXTENSION_GROUP)

    def _generate_records_for_mode(mode: str) -> List[Tuple[str, str, List[str]]]:
        """Generate corpus records for the given navigation mode."""
        globals()["_SELECTED_NAV_GROUP"] = mode
        if mode == "none":
            globals()["_ALLOWED_LETTER_KEYS"] = set()
        else:
            globals()["_ALLOWED_LETTER_KEYS"] = set(_corpus._LETTER_GROUPS.get(mode, ()))
        _init_directional_groups(mode, _corpus._LETTER_GROUPS)

        def _select_adaptive_key(primary_group: set, alternate_key: str, label: str) -> str:
            primary_key = sorted(primary_group)[0]
            contains_primary = primary_key in globals().get("_ALLOWED_LETTER_KEYS", set())
            contains_alternate = alternate_key in globals().get("_ALLOWED_LETTER_KEYS", set())

            if contains_primary and not contains_alternate:
                return alternate_key
            if contains_primary and contains_alternate:
                YELLOW = "\x1b[33m"
                RESET = "\x1b[0m"
                allowed = sorted(globals().get("_ALLOWED_LETTER_KEYS", set()))
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

        globals()["_ACTION_GROUP"] = {
            _select_adaptive_key(
                ACTION_GROUP_ORIG, _corpus._ALTERNATE_ACTION_KEY, "action")
        }

        globals()["_DEBUG_GROUP"] = {
            _select_adaptive_key(
                DEBUG_GROUP_ORIG, _corpus._ALTERNATE_DEBUG_KEY, "debug")
        }

        globals()["_EXTENSION_GROUP"] = {
            _select_adaptive_key(EXTENSION_GROUP_ORIG, _corpus._ALTERNATE_EXTENSION_KEY, "extension")
        }

        keys_to_emit = set()

        keys_to_emit.update(_corpus._ARROW_GROUP)
        keys_to_emit.update(_corpus._JUKE_GROUP)
        keys_to_emit.update(_corpus._SPLIT_GROUP)

        keys_to_emit.update(globals()["_DEBUG_GROUP"])
        keys_to_emit.update(globals()["_EXTENSION_GROUP"])
        keys_to_emit.update(globals()["_ACTION_GROUP"])
        keys_to_emit.update(globals()["_ALLOWED_LETTER_KEYS"])

        keys_ordered = sorted(keys_to_emit)

        recs: List[Tuple[str, str, List[str]]] = []
        local_seen: set = set()
        all_mods = _corpus._MODIFIERS_SINGLE + _corpus._MODIFIERS_MULTI
        for key in keys_ordered:
            for mod in all_mods:
                key_str = f"{mod}+{key}"

                # do not compute tags yet; compute them afterwards to avoid race/ordering effects
                comment_tags: List[str] = []

                mode_when = _augment_when_clause(
                    key,
                    _corpus._when_for(
                        key,
                        mod,
                        allowed_letter_keys=globals().get("_ALLOWED_LETTER_KEYS"),
                        selected_nav_group=globals().get("_SELECTED_NAV_GROUP"),
                        debug_group=globals().get("_DEBUG_GROUP"),
                        action_group=globals().get("_ACTION_GROUP"),
                        extension_group=globals().get("_EXTENSION_GROUP"),
                    ),
                    add_context_arg,
                )

                _SELECTED_NAV_GROUP_STATE = globals().get("_SELECTED_NAV_GROUP")
                _ALLOWED_LETTER_KEYS_STATE = globals().get("_ALLOWED_LETTER_KEYS")

                _LEFT_GROUP_STATE = set(globals().get("_LEFT_GROUP", set()))
                _DOWN_GROUP_STATE = set(globals().get("_DOWN_GROUP", set()))
                _UP_GROUP_STATE = set(globals().get("_UP_GROUP", set()))
                _RIGHT_GROUP_STATE = set(globals().get("_RIGHT_GROUP", set()))

                _ACTION_GROUP_STATE = set(globals().get("_ACTION_GROUP", set()))
                _DEBUG_GROUP_STATE = set(globals().get("_DEBUG_GROUP", set()))
                _EXTENSION_GROUP_STATE = set(globals().get("_EXTENSION_GROUP", set()))

                globals()["_SELECTED_NAV_GROUP"] = "none"
                globals()["_ALLOWED_LETTER_KEYS"] = set()

                globals()["_ACTION_GROUP"] = set()
                globals()["_DEBUG_GROUP"] = set()
                globals()["_EXTENSION_GROUP"] = set()

                _init_directional_groups("none", _corpus._LETTER_GROUPS)
                generic_when = _augment_when_clause(
                    key,
                    _corpus._when_for(
                        key,
                        mod,
                        allowed_letter_keys=set(),
                        selected_nav_group="none",
                        debug_group=set(),
                        action_group=set(),
                        extension_group=set(),
                    ),
                    add_context_arg,
                )

                # restore selected / letter / directional groups
                globals()["_SELECTED_NAV_GROUP"] = _SELECTED_NAV_GROUP_STATE
                globals()["_ALLOWED_LETTER_KEYS"] = _ALLOWED_LETTER_KEYS_STATE
                globals()["_LEFT_GROUP"] = _LEFT_GROUP_STATE
                globals()["_DOWN_GROUP"] = _DOWN_GROUP_STATE
                globals()["_UP_GROUP"] = _UP_GROUP_STATE
                globals()["_RIGHT_GROUP"] = _RIGHT_GROUP_STATE

                # restore chord state
                globals()["_ACTION_GROUP"] = _ACTION_GROUP_STATE
                globals()["_DEBUG_GROUP"] = _DEBUG_GROUP_STATE
                globals()["_EXTENSION_GROUP"] = _EXTENSION_GROUP_STATE

                # emit generic first if different, then the mode-qualified when
                emitted_whens = []
                if generic_when != mode_when:
                    emitted_whens.append(generic_when)
                emitted_whens.append(mode_when)

                _EXTRA_WHENS: List[str] = [
                    # "config.keyboardNavigation.terminal.enabled",
                    # "!config.keyboardNavigation.terminal.enabled",
                ]

                m = len(_EXTRA_WHENS)

                for this_when in emitted_whens:
                    pair = (key_str, this_when)
                    if pair not in local_seen:
                        local_seen.add(pair)
                        recs.append((key_str, this_when, comment_tags))

                    for r in range(1, m + 1):
                        for combo in combinations(_EXTRA_WHENS, r):
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
        for rec in _generate_records_for_mode(mode):
            pair = (rec[0], rec[1])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            records.append(rec)

    # compute deterministic per-record ids using SHA-256(key||when)

    if len(modes) == 1:
        augmented_records: List[Tuple[str, str, List[str]]] = []
        # avoid introducing exact duplicate (key,when) pairs when adding catch keys
        existing_pairs = {(k, w) for (k, w, _) in records}
        for (k, w, t) in records:
            augmented_records.append((k, w, t))
            if w and "config.keyboardNavigation.chords." in w:
                catch_pair = (k, "config.keyboardNavigation.enabled")
                if catch_pair not in existing_pairs:
                    augmented_records.append((k, "config.keyboardNavigation.enabled", t))
                    existing_pairs.add(catch_pair)
        records = augmented_records

    id_fulls = [hashlib.sha256(f"{k}||{w}".encode()).hexdigest()
                for (k, w, _) in records]
    n = len(id_fulls)

    #
    # preference: produce a 4-char hex id by taking the first
    # 4 hex chars of the SHA and, on collision, increment that 4-char
    # value (mod 0x10000) until an unused 4-char is found.
    #

    assigned: List[str | None] = [None] * n
    seen_prefixes: set[str] = set()

    for i, h in enumerate(id_fulls):
        base = int(h[:4], 16)
        found = False

        # try all 65536 4-char possibilities
        for delta in range(0x10000):
            cand = (base + delta) & 0xFFFF
            p = f"{cand:04x}"
            if p not in seen_prefixes:
                assigned[i] = p
                seen_prefixes.add(p)
                found = True
                break
        if not found:
            assigned[i] = None

    # fallback: original prefix-length algorithm (4..12) to resolve uniqueness
    if any(a is None for a in assigned):
        assigned2: List[str | None] = [None] * n
        for L in range(4, 13):
            prefixes = [h[:L] for h in id_fulls]
            counts = Counter(prefixes)
            for i, p in enumerate(prefixes):
                if assigned2[i] is None and counts[p] == 1:
                    assigned2[i] = p
        for i in range(n):
            if assigned2[i] is None:
                assigned2[i] = id_fulls[i][:12]
        assigned = assigned2

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
            # handle trailing '+' meaning the literal key is '+' (e.g., 'alt++')
            if key == "":
                mod = mod.rstrip('+')
                key = '+'
        except ValueError:
            mod = ""
            key = k

        sel = _sel_from_when(w)

        globals()["_SELECTED_NAV_GROUP"] = sel
        if sel == 'none':
            globals()["_ALLOWED_LETTER_KEYS"] = set()
        else:
            globals()["_ALLOWED_LETTER_KEYS"] = set(_corpus._LETTER_GROUPS.get(sel, ()))
        _init_directional_groups(sel, _corpus._LETTER_GROUPS)

        # recompute adaptive chord groups for this selection
        def _select_adaptive_key_local(primary_group: set, alternate_key: str) -> str:
            primary_key = sorted(primary_group)[0]
            contains_primary = primary_key in globals().get("_ALLOWED_LETTER_KEYS", set())
            contains_alternate = alternate_key in globals().get("_ALLOWED_LETTER_KEYS", set())
            if contains_primary and not contains_alternate:
                return alternate_key
            return primary_key

        globals()["_ACTION_GROUP"] = {_select_adaptive_key_local(ACTION_GROUP_ORIG, _corpus._ALTERNATE_ACTION_KEY)}
        globals()["_DEBUG_GROUP"] = {_select_adaptive_key_local(DEBUG_GROUP_ORIG, _corpus._ALTERNATE_DEBUG_KEY)}
        globals()["_EXTENSION_GROUP"] = {_select_adaptive_key_local(EXTENSION_GROUP_ORIG, _corpus._ALTERNATE_EXTENSION_KEY)}

        cmd = f"(corpus) {k} {assigned[idx]}"
        tags = _corpus._tags_for(key, mod, w, command=cmd)
        comment_tags = tags if tags else []
        records[idx] = (k, w, comment_tags)

    out_lines = ["["]
    for i, (k, w, tags) in enumerate(records):
        cmd = f"(corpus) {k} {assigned[i]}"
        obj = _emit_record(k, cmd, w, tags)
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
    raise SystemExit(_main())
