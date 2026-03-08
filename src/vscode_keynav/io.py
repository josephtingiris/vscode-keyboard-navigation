"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common io functions.
"""

from __future__ import annotations

from pathlib import Path

import sys

from typing import Optional, Union


def _read_input_text(path: Union[str, Path, None]) -> Optional[str]:
    """Read UTF-8 text from a path or from piped stdin.

    Returns the text or None when no input was provided (tty stdin and no path).
    """
    if path:
        p = Path(path)
        return p.read_text(encoding="utf-8")
    # when stdin is not a tty, read from it
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def _write_output_text(path: Union[str, Path, None], text: str) -> None:
    """Write UTF-8 text to a path or stdout when path is None."""
    if path:
        p = Path(path)
        p.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
