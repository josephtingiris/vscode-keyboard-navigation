"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common io functions.
"""

from __future__ import annotations

from pathlib import Path

import re
import sys

from typing import Optional, Union


# NOTE: prefer adding more parsing/formatting helpers here rather than scattering regexes across multiple modules.

_RE_PATTERNS = {
    '_WHEN_LITERAL_RE': (r'("when"\s*:\s*\")((?:\\.|[^"\\])*)(\")', 0),
    '_WHITESPACE_RE': (r"\s+", 0),
    '_WHEN_SORTED_RE': (r'^\s*//\s*when-sorted:.*\n', re.MULTILINE),
    '_BLANK_LINES_RE': (r'(?m)^[ \t]*\n+', 0),
    '_LEADING_COMMA_RE': (r'^\s*,+', 0),
    '_STRIP_WS_RE': (r'^[ \t\r\n]+|[ \t\r\n]+$', 0),
    '_LEADING_NEWLINES_RE': (r'^\n+', 0),
    '_NUMBER_SPLIT_RE': (r"(\d+)", 0),
    '_WHEN_TERM_SPLIT_RE': (r"\s*&&\s*|\s*\|\|\s*", 0),
    '_COMMENT_RE': (r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)', re.DOTALL | re.MULTILINE),
    '_TRAILING_COMMA_RE': (r',\s*([}\]])', 0),
    '_OBJ_RE': (r'\{.*\}', re.DOTALL),
    '_KEY_EXTRACT_RE': (r'"key"\s*:\s*"((?:\\.|[^"\\])*)"', 0),
    '_WHEN_EXTRACT_RE': (r'"when"\s*:\s*"((?:\\.|[^"\\])*)"', 0),
}


def __getattr__(name: str):
    """Lazily compile and cache regex attributes on first access.

    This reduces import-time overhead by deferring regex compilation until used.
    """
    if name in _RE_PATTERNS:
        pattern, flags = _RE_PATTERNS[name]
        compiled = re.compile(pattern, flags)
        globals()[name] = compiled
        return compiled
    raise AttributeError(name)


def _read_input_text(path: Union[str, Path, None]) -> Optional[str]:
    """Read UTF-8 text from a file path or from piped stdin, returning None if no input."""

    if path:
        p = Path(path)
        return p.read_text(encoding="utf-8")
    # when stdin is not a tty, read from it
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def _write_output_text(path: Union[str, Path, None], text: str) -> None:
    """Write UTF-8 text to a file when `path` is provided, otherwise write to stdout."""

    if path:
        p = Path(path)
        p.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
