#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Remove objects from a JSONC `keybindings.json` array by attribute match.

Usage:
    keybindings-remove.py <attribute> <search_string> < keybindings.json

Examples:
    # remove objects where the 'command' contains 'example'
    keybindings-remove.py command example < keybindings.json > keybindings-noexample.json
    # remove any object that contains the literal 'TODO' anywhere in the object
    keybindings-remove.py any TODO < keybindings.json > keybindings-noTODO.json

Behavior:
    - Removes matching objects and correctly handles trailing commas so the resulting JSONC remains syntactically valid.
    - Preserves comments and whitespace before the opening `[` and after the closing `]`, as well as comments inside and around each object.
    - Special attribute: use `any` or `*` as the <attribute> to match the <search_string> anywhere inside the object's raw text (including attribute names, attribute values, and comments embedded inside the object). This check is a simple substring match (case-sensitive).
    - Prints the modified content to stdout; does not write files in-place.
    - Set `KEYBINDINGS_REMOVE_DEBUG=1` to enable debug logging to stderr when parsing or matching issues occur.

Inputs / Outputs:
    stdin:  JSONC text (VS Code keybindings array)
    stdout: Modified JSONC text encoded as UTF-8

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""

import sys
import os
import re
import json
import argparse
from typing import Any


# prefer json5 libraries
_json5 = None
try:
    import json5 as _json5  # type: ignore
    JSON_FLAVOR = "JSON5"
except Exception:
    JSON_FLAVOR = "JSONC"


def extract_preamble_postamble(text):
    """
    Find the top-level JSON array brackets, skipping any brackets that appear
    inside comments or strings in the preamble/postamble.
    """

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
        next2 = text[i:i + 2] if i + 2 <= n else ''

        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == '*/':
                in_block_comment = False
                i += 2
            else:
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

        if next2 == '//':
            in_line_comment = True
            i += 2
            continue
        if next2 == '/*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == '[':
            start = i
            break
        i += 1

    if start == -1:
        return '', '', text

    depth = 1
    i = start + 1
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    end = -1

    while i < n:
        ch = text[i]
        next2 = text[i:i + 2] if i + 2 <= n else ''

        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == '*/':
                in_block_comment = False
                i += 2
            else:
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

        if next2 == '//':
            in_line_comment = True
            i += 2
            continue
        if next2 == '/*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1

    if end == -1:
        return '', '', text

    preamble = text[:start]
    postamble = text[end + 1:]
    array_text = text[start + 1:end]  # exclude [ and ]
    return preamble, array_text, postamble


def split_units(array_text: str):
    units = []
    n = len(array_text)
    i = 0

    def consume_ws_comments(pos: int) -> int:
        while pos < n:
            if array_text[pos].isspace():
                pos += 1
                continue
            if array_text.startswith('//', pos):
                nl = array_text.find('\n', pos)
                if nl == -1:
                    return n
                pos = nl + 1
                continue
            if array_text.startswith('/*', pos):
                end = array_text.find('*/', pos + 2)
                if end == -1:
                    return n
                pos = end + 2
                continue
            break
        return pos

    while i < n:
        lead_start = i

        in_string = False
        string_char = ''
        esc = False
        in_line_comment = False
        in_block_comment = False
        obj_start = -1
        while i < n:
            ch = array_text[i]
            next2 = array_text[i:i + 2] if i + 2 <= n else ''

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                i += 1
                continue
            if in_block_comment:
                if next2 == '*/':
                    in_block_comment = False
                    i += 2
                else:
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

            if next2 == '//':
                in_line_comment = True
                i += 2
                continue
            if next2 == '/*':
                in_block_comment = True
                i += 2
                continue
            if ch == '"' or ch == "'":
                in_string = True
                string_char = ch
                i += 1
                continue
            if ch == '{':
                obj_start = i
                break
            i += 1

        if obj_start == -1:
            break

        leading = array_text[lead_start:obj_start]

        depth = 1
        i = obj_start + 1
        in_string = False
        string_char = ''
        esc = False
        in_line_comment = False
        in_block_comment = False
        obj_end = -1
        while i < n:
            ch = array_text[i]
            next2 = array_text[i:i + 2] if i + 2 <= n else ''

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                i += 1
                continue
            if in_block_comment:
                if next2 == '*/':
                    in_block_comment = False
                    i += 2
                else:
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

            if next2 == '//':
                in_line_comment = True
                i += 2
                continue
            if next2 == '/*':
                in_block_comment = True
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
                    obj_end = i
                    i += 1
                    break
            i += 1

        if obj_end == -1:
            break

        obj_text = array_text[obj_start:obj_end + 1]

        trivia_before_start = i
        i = consume_ws_comments(i)
        trivia_before = array_text[trivia_before_start:i]

        if i < n and array_text[i] == ',':
            i += 1

        trivia_after_start = i
        i = consume_ws_comments(i)
        trivia_after = array_text[trivia_after_start:i]

        trailing = trivia_before + trivia_after

        units.append((leading, obj_text, trailing))

    return units


def strip_json_comments(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ''
        return s
    pattern = r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)'  # string or comment
    return re.sub(pattern, replacer, text, flags=re.DOTALL | re.MULTILINE)


def strip_trailing_commas(text):
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def parse_object_text(obj_str: str) -> dict[str, Any]:
    parsed: Any
    if _json5 is not None:
        parsed = _json5.loads(obj_str)
    else:
        clean = strip_json_comments(obj_str)
        clean = strip_trailing_commas(clean)
        parsed = json.loads(clean)

    if not isinstance(parsed, dict):
        raise ValueError("object text did not parse to a JSON object")
    return parsed


def should_remove(obj_text, attr, val, unit_text=None):
    if attr in ('any', '*'):
        haystack = unit_text if unit_text is not None else obj_text
        return val in haystack

    start = obj_text.find('{')
    end = obj_text.rfind('}')
    if start == -1 or end == -1 or end < start:
        return False
    obj_str = obj_text[start:end + 1]
    try:
        obj = parse_object_text(obj_str)

        attr_val = obj.get(attr, '')
        contains = val in str(attr_val)

        # debug output to stderr when KEYBINDINGS_REMOVE_DEBUG env var set
        if os.environ.get('KEYBINDINGS_REMOVE_DEBUG'):
            print('DEBUG: obj=', obj, file=sys.stderr)
            print(f"DEBUG: attr={attr!r} attr_val={attr_val!r} contains={contains}", file=sys.stderr)
        return contains
    except Exception:
        # debug info when parsing fails
        if os.environ.get('KEYBINDINGS_REMOVE_DEBUG'):
            print(f"DEBUG: failed to parse object text: {obj_str}", file=sys.stderr)
        return False


def main(argv: list | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Remove objects from a JSONC keybindings.json array by attribute match.",
        epilog="Example: %(prog)s command example < keybindings.json > keybindings-noexample.json",
    )
    parser.add_argument('attribute', help="An attribute name to match (e.g., 'command'), or use 'any' to match the search string anywhere inside the object.")
    parser.epilog = "Use attribute name 'any' or '*' to match the search string anywhere inside the object (attributes, values, or comments)."
    parser.add_argument('search_string', help='Substring to search for in the attribute value')

    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    attr, val = args.attribute, args.search_string
    raw = sys.stdin.read()
    preamble, array_text, postamble = extract_preamble_postamble(raw)
    units = split_units(array_text)

    sys.stdout.write(preamble)
    sys.stdout.write('[')
    kept_units = []
    for comments, obj, trailing in units:
        unit_text = comments + obj
        if should_remove(obj, attr, val, unit_text=unit_text):
            continue
        kept_units.append((comments, obj, trailing))

    for idx, (comments, obj, trailing) in enumerate(kept_units):
        sys.stdout.write(comments)
        sys.stdout.write(obj)
        if idx < len(kept_units) - 1:
            sys.stdout.write(',')
        sys.stdout.write(trailing)
    sys.stdout.write(']')
    sys.stdout.write(postamble)
    if not postamble.endswith('\n'):
        sys.stdout.write('\n')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
