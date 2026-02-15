#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Remove comments from JSONC read from stdin and write strict JSON to stdout.

Usage:
    ./bin/keybindings-remove-comments.py < keybindings.json

Examples:
    ./bin/keybindings-remove-comments.py < references/keybindings.json > tmp.json

Behavior:
    - Removes single-line `//` and block `/* ... */` comments while respecting quoted string literals.
    - Preserves line breaks for most single-line comments; strips block comments using a non-greedy DOTALL approach.
    - Prints cleaned JSON to stdout; does not modify input files.

Inputs / Outputs:
    stdin:  JSONC text encoded as UTF-8
    stdout: JSON text encoded as UTF-8

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""
from __future__ import annotations

import re
import sys
import os
import argparse
from typing import List


# usage is handled by argparse: only show help when -h/--help is provided


def strip_comments(jsonc_string: str) -> str:
    """Return `jsonc_string` with // and /* */ comments removed.

    This simple implementation preserves line breaks for most single-line
    comments and strips block comments using a non-greedy DOTALL regex.
    """
    # Robust scanner: iterate characters and remove comments while respecting
    # double-quoted strings and escapes. Preserves newline for single-line
    # comments so line count remains stable for diagnostics.
    out = []
    i = 0
    n = len(jsonc_string)
    in_string = False

    while i < n:
        ch = jsonc_string[i]

        if in_string:
            out.append(ch)
            if ch == '\\':
                # preserve escape and next char if present
                if i + 1 < n:
                    out.append(jsonc_string[i + 1])
                    i += 1
            elif ch == '"':
                in_string = False
            i += 1
            continue

        # not in a string
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        # possible comment
        if ch == '/' and i + 1 < n:
            nxt = jsonc_string[i + 1]
            if nxt == '/':
                # single-line comment: skip until end of line, preserve newline
                i += 2
                while i < n and jsonc_string[i] != '\n':
                    i += 1
                if i < n and jsonc_string[i] == '\n':
                    out.append('\n')
                    i += 1
                continue
            if nxt == '*':
                # block comment: skip until closing '*/'
                i += 2
                while i + 1 < n and not (jsonc_string[i] == '*' and jsonc_string[i + 1] == '/'):
                    i += 1
                if i + 1 < n:
                    i += 2
                continue

        # normal character
        out.append(ch)
        i += 1

    res = ''.join(out)
    # Remove any now-empty lines that came from full-line comments so there are no blank lines in the output.
    no_blank_lines = re.sub(r'(?m)^[ \t]*\n+', '', res)
    return no_blank_lines.strip()


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description="Remove comments from JSONC read from stdin and write strict JSON to stdout.",
        epilog="Example: %(prog)s < references/keybindings.json > tmp.json",
    )

    # no specific CLI options; argparse will print help and exit on -h/--help
    parser.parse_args(argv)

    # Read from stdin and write the cleaned JSON to stdout
    jsonc_string = sys.stdin.read()
    json_string = strip_comments(jsonc_string)
    print(json_string)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
