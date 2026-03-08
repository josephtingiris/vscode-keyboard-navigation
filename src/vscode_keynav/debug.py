"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common debug functions.
"""

from __future__ import annotations

import sys

from typing import Iterable, List


#
# globals & constants
#


_COLOR: str = "auto"

_DEBUG_LEVEL: int = 0
_DEBUG_TARGET_CATEGORY: str | None = None
_DEBUG_TARGET_WHEN: str = ""


#
# functions
#


def _apply_settings(debug_specs: Iterable[str] | None, color: str = "auto") -> None:
    """Configure module-level debug filters and color mode from spec strings."""

    global _COLOR, _DEBUG_LEVEL, _DEBUG_TARGET_CATEGORY, _DEBUG_TARGET_WHEN

    _COLOR = color

    _DEBUG_LEVEL = 0
    _DEBUG_TARGET_CATEGORY = None
    _DEBUG_TARGET_WHEN = ""

    if not debug_specs:
        return

    max_level = 0
    for spec in debug_specs:
        s = spec.strip()
        if not s:
            continue
        if s.isdigit():
            max_level = max(max_level, int(s))
        elif s.startswith("target="):
            _DEBUG_TARGET_CATEGORY = s.split("=", 1)[1]
        elif s.startswith("when="):
            _DEBUG_TARGET_WHEN = s.split("=", 1)[1]

    _DEBUG_LEVEL = max_level


def _color(text: str, level: int) -> str:
    """Wrap text with ANSI color codes for a given debug level when enabled."""

    if not _color_enabled():
        return text
    colors = {1: "\x1b[33m", 2: "\x1b[36m", 3: "\x1b[35m", 4: "\x1b[34m"}
    code = colors.get(level, "\x1b[37m")
    return f"{code}{text}\x1b[0m"


def _color_enabled() -> bool:
    """Return True when ANSI coloring should be enabled based on `_COLOR` and stderr TTY status."""

    if _COLOR == "never":
        return False
    if _COLOR == "always":
        return True
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


def _echo(level: int, category: str, when_val: str | None, msg: str) -> None:
    """Conditionally output a debug message to stderr according to configured filters and level."""

    if _DEBUG_LEVEL <= 0:
        return
    if level > _DEBUG_LEVEL:
        return
    if _DEBUG_TARGET_CATEGORY and _DEBUG_TARGET_CATEGORY != "all" and category != _DEBUG_TARGET_CATEGORY:
        return
    if _DEBUG_TARGET_WHEN and when_val:
        if _DEBUG_TARGET_WHEN not in when_val:
            return

    out = f"[DEBUG:{level}:{category}] {msg}"
    out = _color(out, level)
    try:
        print(out, file=sys.stderr)
    except Exception:
        pass
