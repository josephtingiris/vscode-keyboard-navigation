#!/usr/bin/env python3
"""
Merge two JSONC keybindings files while preserving comments and raw items.

Usage:
    python3 bin/keybindings-merge.py [--prefer {left,right}] [--base {left,right}] left.json right.json [--out merged.json]

Examples:
    python3 bin/keybindings-merge.py fileA.json fileB.json
    python3 bin/keybindings-merge.py --prefer left --base right a.json b.json --out merged.json

Behavior / Notes:
    - Requires Python 3.7 or newer.
    - Does not remove or alter comments; merged output keeps original item text and spacing.
    - Use `--prefer` to choose which file wins for duplicate key+when entries
      (default: `right`). Use `--base` to choose which file supplies the
      wrapper/prefix/suffix (default: `left`).
    - Writes output to `--out` (default: `merged-keybindings.json`).
    - Prints warnings for any items that could not be parsed.

Inputs / Outputs:
    left.json, right.json: Input JSONC files.
    stdout / `--out`: Merged JSONC text (written to `--out`).

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""

# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any
from collections import OrderedDict

# ---- Python version check ----
if sys.version_info < (3, 7):
    sys.stderr.write("Error: this script requires Python 3.7 or newer. Please upgrade your Python installation.\n")
    sys.exit(2)

# ---- Helpers: robust scanning that respects strings and comments ----

def find_top_level_array_bounds(text: str) -> Tuple[int, int]:
    """
    Find the indices of the '[' and its matching ']' for the top-level array.
    Returns (index_of_open_bracket, index_of_matching_close_bracket).
    Raises ValueError if not found.
    """
    i = 0
    n = len(text)
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    depth = 0
    first_bracket = -1

    while i < n:
        ch = text[i]
        next2 = text[i:i+2] if i+2 <= n else ''
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
        # not in string/comment
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
            if first_bracket == -1:
                first_bracket = i
                depth = 1
                i += 1
                break
            else:
                depth += 1
        i += 1

    if first_bracket == -1:
        raise ValueError("No top-level '[' found in file (is this a keybindings.json array?)")

    # find matching ]
    while i < n:
        ch = text[i]
        next2 = text[i:i+2] if i+2 <= n else ''
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
                return first_bracket, i
        i += 1

    raise ValueError("Matching ']' for top-level '[' not found")

def split_top_level_array_items(array_inner: str) -> List[str]:
    """
    Given the string inside the top-level [ ... ] (excluding the brackets),
    split into item raw text pieces, preserving comments and spacing around items.
    """
    items: List[str] = []
    i = 0
    n = len(array_inner)
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    brace_depth = 0
    bracket_depth = 0
    last_split = 0

    while i < n:
        ch = array_inner[i]
        next2 = array_inner[i:i+2] if i+2 <= n else ''
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
        # not in string/comment
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
        # track nested braces/brackets to detect commas at top-level of the array
        if ch == '{':
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
        elif ch == '[':
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1
        elif ch == ',' and brace_depth == 0 and bracket_depth == 0:
            # top-level comma separating items
            item = array_inner[last_split:i]
            items.append(item)
            last_split = i+1  # skip comma
        i += 1

    # final piece
    final = array_inner[last_split:]
    if final.strip() != '':
        items.append(final)
    else:
        # if final is whitespace/comments, attach to previous item if exists, otherwise keep it as an empty item
        if items:
            items[-1] = items[-1] + final
        elif final.strip() != '':
            items.append(final)
    # Strip nothing: keep items' raw text as-is so comments remain attached exactly where they were.
    return items

# ---- Light-weight comment remover and trailing-comma cleaner used only for parsing items ----
# NOTE: these functions are used only to produce a parseable JSON string for json.loads.
# They DO NOT alter the original raw item text that will be preserved in the final output.

def remove_comments_from_string(s: str) -> str:
    """Remove // and /* */ comments while respecting quoted strings."""
    out_chars: List[str] = []
    i = 0
    n = len(s)
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = s[i]
        next2 = s[i:i+2] if i+2 <= n else ''
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
                out_chars.append(ch)
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
            out_chars.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        # not in string/comment
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
            out_chars.append(ch)
            i += 1
            continue
        out_chars.append(ch)
        i += 1
    return ''.join(out_chars)

def remove_trailing_commas(s: str) -> str:
    """
    Remove trailing commas before } or ] at the same syntactic level.
    This works with the assumption that comments have already been removed.
    """
    out_chars: List[str] = []
    i = 0
    n = len(s)
    in_string = False
    string_char = ''
    esc = False
    stack: List[str] = []  # track { and [ for nesting, to know when comma is trailing
    while i < n:
        ch = s[i]
        if in_string:
            out_chars.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            out_chars.append(ch)
            i += 1
            continue
        if ch == '{' or ch == '[':
            stack.append(ch)
            out_chars.append(ch)
            i += 1
            continue
        if ch == '}' or ch == ']':
            # look back: if the last non-space char in out_chars is a comma, remove that comma
            j = len(out_chars) - 1
            while j >= 0 and out_chars[j].isspace():
                j -= 1
            if j >= 0 and out_chars[j] == ',':
                # remove the comma
                out_chars.pop(j)
            if stack:
                stack.pop()
            out_chars.append(ch)
            i += 1
            continue
        out_chars.append(ch)
        i += 1
    return ''.join(out_chars)

def parse_item_to_object(item_raw: str) -> Any:
    """
    Try to parse an item (which is raw JSONC text for an object).
    Returns the parsed object on success, raises ValueError on parse failure.
    """
    cleaned = remove_comments_from_string(item_raw)
    cleaned = remove_trailing_commas(cleaned)
    # Strip leading/trailing whitespace so json.loads doesn't choke if there's surrounding newlines
    cleaned = cleaned.strip()
    if not cleaned:
        raise ValueError("empty item after removing comments")
    return json.loads(cleaned)

# ---- Merge logic preserving raw item text ----

def make_key_from_obj(obj: Any) -> str:
    # only objects (dict) are expected; for non-dict return a synthetic key
    if isinstance(obj, dict):
        key = obj.get('key', '') or ''
        when = obj.get('when', '') or ''
        return f"{key}|{when}"
    return "__NON_OBJECT__"

def merge_keybinding_files(left_text: str, right_text: str, prefer: str, base: str = 'left') -> Tuple[str, List[str]]:
    """
    Merge two JSONC keybinding files.
    prefer: 'left' or 'right'  (which file's binding wins on duplicates)
    base: 'left' or 'right'   (which file provides the wrapper/prefix/suffix)
    Returns (merged_text, warnings)
    """
    # find array bounds in both files
    left_l, left_r = find_top_level_array_bounds(left_text)
    right_l, right_r = find_top_level_array_bounds(right_text)

    left_prefix = left_text[:left_l+1]   # include '['
    left_inner = left_text[left_l+1:left_r]
    left_suffix = left_text[left_r:]     # include ']' and rest

    right_prefix = right_text[:right_l+1]
    right_inner = right_text[right_l+1:right_r]
    right_suffix = right_text[right_r:]

    left_items_raw = split_top_level_array_items(left_inner)
    right_items_raw = split_top_level_array_items(right_inner)

    mapping: "OrderedDict[str, str]" = OrderedDict()
    warnings: List[str] = []
    left_keys_seen: set = set()
    right_keys_seen: set = set()

    # process left items
    for idx, raw in enumerate(left_items_raw):
        raw_stripped = raw.rstrip()
        if raw_stripped == '':
            # preserve blank/whitespace-only fragments
            synthetic_key = f"__LEFT_BLANK_{idx}__"
            mapping[synthetic_key] = raw
            continue
        try:
            obj = parse_item_to_object(raw)
            if isinstance(obj, dict):
                k = make_key_from_obj(obj)
            else:
                # non-object (e.g., a primitive), preserve as unique entry
                k = f"__LEFT_NONOBJ_{idx}__"
            mapping.setdefault(k, raw)
            left_keys_seen.add(k)
        except Exception as e:
            # preserve raw but mark as unparsable; give it a unique key so we don't try to dedupe it
            synthetic = f"__LEFT_UNPARSED_{idx}__"
            mapping[synthetic] = raw
            warnings.append(f"Warning: left file item #{idx} could not be parsed as JSON: {e}")

    # process right items
    for idx, raw in enumerate(right_items_raw):
        raw_stripped = raw.rstrip()
        if raw_stripped == '':
            synthetic_key = f"__RIGHT_BLANK_{idx}__"
            mapping[synthetic_key] = mapping.get(synthetic_key, raw)
            continue
        try:
            obj = parse_item_to_object(raw)
            if isinstance(obj, dict):
                k = make_key_from_obj(obj)
            else:
                k = f"__RIGHT_NONOBJ_{idx}__"
            right_keys_seen.add(k)
            if k in mapping:
                # conflict
                if prefer == 'right':
                    # replace but keep insertion order (OrderedDict preserves key positions on assignment to existing key)
                    mapping[k] = raw
                else:
                    # prefer left: keep existing
                    pass
            else:
                # new: append at end
                mapping[k] = raw
        except Exception as e:
            synthetic = f"__RIGHT_UNPARSED_{idx}__"
            mapping[synthetic] = raw
            warnings.append(f"Warning: right file item #{idx} could not be parsed as JSON: {e}")

    # Build final text using chosen base's wrapper (prefix/suffix)
    if base == 'left':
        prefix = left_prefix
        suffix = left_suffix
    else:
        prefix = right_prefix
        suffix = right_suffix

    # join items with commas between them. Do not alter item raw text.
    merged_items = []
    for raw in mapping.values():
        # keep raw exactly as in source
        merged_items.append(raw.rstrip())

    if merged_items:
        joined = ',\n'.join(item for item in merged_items)
        merged_inner = '\n' + joined + '\n'
    else:
        merged_inner = '\n'

    merged_text = prefix + merged_inner + suffix
    return merged_text, warnings

# ---- CLI ----

def usage(prog: str | None = None) -> None:
    if prog is None:
        prog = sys.argv[0].split('/')[-1]
    msg = (
        f"Usage: {prog} left.json right.json [--prefer left|right] [--base left|right] [--out merged.json]\n\n"
        "Options:\n  --prefer left|right   Which file wins on duplicate key+when (default: right)\n"
        "  --base left|right     Which file supplies the wrapper/prefix/suffix (default: left)\n"
        "  --out PATH            Output file path (default: merged-keybindings.json)\n"
        "  -h, --help            Show this usage message and exit\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(1)


def main(argv: List[str] | None = None) -> int:
    raw_argv = argv if argv is not None else sys.argv[1:]
    if any(a in ('-h', '--help') for a in raw_argv):
        usage()
    parser = argparse.ArgumentParser(description="Merge two VS Code keybindings.json (JSONC) files while preserving comments.")
    parser.add_argument('left', type=Path, help='Left keybindings file (e.g., fileA.json)')
    parser.add_argument('right', type=Path, help='Right keybindings file (e.g., fileB.json)')
    parser.add_argument('--prefer', choices=['left', 'right'], default='right', help='Which file wins on duplicate key+when (default: right)')
    parser.add_argument('--base', choices=['left', 'right'], default='left', help='Which file supplies the surrounding wrapper/prefix/suffix (default: left)')
    parser.add_argument('--out', type=Path, default=Path('merged-keybindings.json'), help='Output file path')
    args = parser.parse_args(argv)

    try:
        left_text = args.left.read_text(encoding='utf8')
    except Exception as e:
        sys.stderr.write(f"Error reading left file '{args.left}': {e}\n")
        return 2
    try:
        right_text = args.right.read_text(encoding='utf8')
    except Exception as e:
        sys.stderr.write(f"Error reading right file '{args.right}': {e}\n")
        return 2

    try:
        merged_text, warnings = merge_keybinding_files(left_text, right_text, args.prefer, base=args.base)
    except Exception as e:
        sys.stderr.write(f"Error merging files: {e}\n")
        return 2

    try:
        args.out.write_text(merged_text, encoding='utf8')
    except Exception as e:
        sys.stderr.write(f"Error writing output file '{args.out}': {e}\n")
        return 2

    # Print summary
    print(f"Merged '{args.left}' + '{args.right}' -> '{args.out}'")
    print(f"Preference on duplicate key+when: {args.prefer}; base wrapper: {args.base}")
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(" -", w)
    else:
        print("No parse warnings.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())