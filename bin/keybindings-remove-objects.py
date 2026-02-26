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

    # Find opening bracket, skipping comments and strings
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

        # Not in string/comment
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

    # Find matching closing bracket
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

        # Not in string/comment
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
    # Each unit: (comments/whitespace before, object, trailing comma, whitespace)
    units = []
    lines = array_text.splitlines(keepends=True)
    i = 0
    n = len(lines)
    while i < n:
        comments = ''
        # Gather comments/whitespace before object
        while i < n and '{' not in lines[i]:
            comments += lines[i]
            i += 1
        if i >= n:
            break
        # Gather object
        obj_lines = ''
        depth = 0
        started = False
        while i < n:
            line = lines[i]
            if '{' in line:
                started = True
                depth += line.count('{')
            if started:
                obj_lines += line
            if '}' in line:
                depth -= line.count('}')
                if depth == 0:
                    i += 1
                    break
            i += 1
        # Gather trailing comma and whitespace
        trailing = ''
        while i < n and (lines[i].strip().startswith(',') or lines[i].strip() == '' or lines[i].strip().startswith('//') or lines[i].strip().startswith('/*')):
            trailing += lines[i]
            i += 1
        units.append((comments, obj_lines, trailing))
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


def should_remove(obj_text, attr, val):
    # non-greedy match to extract the JSON object body
    obj_match = re.search(r'\{[\s\S]*?\}', obj_text)
    if not obj_match:
        return False
    obj_str = obj_match.group(0)
    # If attr is 'any' (or '*'), treat the search as matching anywhere
    # inside the object's raw text (attributes, values, or comments).
    if attr in ('any', '*'):
        return val in obj_str
    try:
        clean = strip_json_comments(obj_str)
        clean = strip_trailing_commas(clean)
        obj = json.loads(clean)
        # perform substring check (case-sensitive)
        attr_val = obj.get(attr, '')
        contains = val in str(attr_val)
        # debug output to stderr when KEYBINDINGS_REMOVE_DEBUG env var set
        if os.environ.get('KEYBINDINGS_REMOVE_DEBUG'):
            print('DEBUG: obj=', obj, file=sys.stderr)
            print(f"DEBUG: attr={attr!r} attr_val={attr_val!r} contains={contains}", file=sys.stderr)
        return contains
    except Exception:
        # Debug info when parsing fails
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
    # If invoked with no arguments, show full help (same as -h/--help) and exit success.
    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    attr, val = args.attribute, args.search_string
    raw = sys.stdin.read()
    preamble, array_text, postamble = extract_preamble_postamble(raw)
    units = split_units(array_text)
    # Output
    sys.stdout.write(preamble)
    sys.stdout.write('[')
    for comments, obj, trailing in units:
        if should_remove(obj, attr, val):
            continue
        sys.stdout.write(comments)
        sys.stdout.write(obj)
        sys.stdout.write(trailing)
    sys.stdout.write(']')
    sys.stdout.write(postamble)
    if not postamble.endswith('\n'):
        sys.stdout.write('\n')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
