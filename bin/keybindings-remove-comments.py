#!/usr/bin/env python3
"""
Remove comments from JSONC read from stdin and write strict JSON to stdout.

Usage:
    ./bin/keybindings-remove-comments.py < keybindings.json

Examples:
    ./bin/keybindings-remove-comments.py < references/keybindings.json > tmp.json

Behavior:
    - Removes single-line `//` and block `/* ... */` comments while respecting
      quoted string literals.
    - Preserves line breaks for most single-line comments; strips block
      comments using a non-greedy DOTALL approach.
    - Prints cleaned JSON to stdout; does not modify input files.

Inputs / Outputs:
    stdin:  JSONC text encoded as UTF-8
    stdout: JSON text encoded as UTF-8

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""

# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

from __future__ import annotations

import re
import sys
import os


def usage(prog: str | None = None) -> None:
    if prog is None:
        prog = os.path.basename(sys.argv[0])
    msg = (
        f"Usage: {prog} < keybindings.json>\n\n"
        "Options:\n  -h, --help    Show this usage message and exit\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(1)


def strip_comments(jsonc_string: str) -> str:
    """Return `jsonc_string` with // and /* */ comments removed.

    This simple implementation preserves line breaks for most single-line
    comments and strips block comments using a non-greedy DOTALL regex.
    """
    # Remove comments while respecting quoted strings. This avoids stripping
    # comment-like sequences inside string literals.
    def _replacer(match: re.Match) -> str:
        token = match.group(0)
        # If token starts with / it's a comment; drop it. Otherwise keep string.
        if token.startswith('/'):
            return ''
        return token

    pattern = r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)'
    no_comments = re.sub(pattern, _replacer, jsonc_string,
                         flags=re.DOTALL | re.MULTILINE)
    # Remove any now-empty lines that came from full-line comments so there are no blank lines in the output.
    no_blank_lines = re.sub(r'(?m)^[ \t]*\n+', '', no_comments)
    return no_blank_lines.strip()


def main() -> None:
    prog = os.path.basename(sys.argv[0])
    if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
        usage(prog)
    # Read from stdin and write the cleaned JSON to stdout
    jsonc_string = sys.stdin.read()
    json_string = strip_comments(jsonc_string)
    print(json_string)


if __name__ == "__main__":
    main()
