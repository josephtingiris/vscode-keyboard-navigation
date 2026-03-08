"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common io functions.
"""

from __future__ import annotations

from pathlib import Path

import re
import sys

from typing import Optional, Union, Pattern

#
# globals & constants
#


# prefer adding more parsing/formatting regexes here rather than scattering them across multiple modules

_BLANK_LINES_RE = re.compile(r'(?m)^[ \t]*\n+', 0)
_COMMENT_RE = re.compile(r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)', re.DOTALL | re.MULTILINE)
_KEY_EXTRACT_RE = re.compile(r'"key"\s*:\s*"((?:\\.|[^"\\])*)"', 0)
_LEADING_COMMA_RE = re.compile(r'^\s*,+', 0)
_LEADING_NEWLINES_RE = re.compile(r'^\n+', 0)
_NUMBER_SPLIT_RE = re.compile(r"(\d+)", 0)
_OBJ_RE = re.compile(r'\{.*\}', re.DOTALL)
_STRIP_WS_RE = re.compile(r'^[ \t\r\n]+|[ \t\r\n]+$', 0)
_TRAILING_COMMA_RE = re.compile(r',\s*([}\]])', 0)
_WHEN_EXTRACT_RE = re.compile(r'"when"\s*:\s*"((?:\\.|[^"\\])*)"', 0)
_WHEN_LITERAL_RE = re.compile(r'("when"\s*:\s*\")(?:\\.|[^"\\])*(\")', 0)
_WHEN_SORTED_RE = re.compile(r'^\s*//\s*when-sorted:.*\n', re.MULTILINE)
_WHEN_TERM_SPLIT_RE = re.compile(r"\s*&&\s*|\s*\|\|\s*", 0)
_WHITESPACE_RE = re.compile(r"\s+", 0)


#
# functions
#


def _normalize_whitespace(text: str) -> str:
    """Return the input string with all whitespace collapsed to single spaces and trimmed."""

    return _WHITESPACE_RE.sub(' ', text).strip() if text else ''


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
