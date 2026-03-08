"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common debug functions.
"""

from __future__ import annotations

import sys

from typing import Iterable, List

# public configuration
COLOR: str = "auto"
DEBUG_LEVEL: int = 0
DEBUG_TARGET_CATEGORY: str | None = None
DEBUG_TARGET_WHEN: str = ""


def _apply_settings(debug_specs: Iterable[str] | None, color: str = "auto") -> None:
    """Configure module-level debug filters and color mode from spec strings."""

    global DEBUG_LEVEL, DEBUG_TARGET_CATEGORY, DEBUG_TARGET_WHEN, COLOR
    COLOR = color
    DEBUG_LEVEL = 0
    DEBUG_TARGET_CATEGORY = None
    DEBUG_TARGET_WHEN = ""

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
            DEBUG_TARGET_CATEGORY = s.split("=", 1)[1]
        elif s.startswith("when="):
            DEBUG_TARGET_WHEN = s.split("=", 1)[1]

    DEBUG_LEVEL = max_level


def _color(text: str, level: int) -> str:
    """Wrap text with ANSI color codes for a given debug level when enabled."""

    if not _color_enabled():
        return text
    colors = {1: "\x1b[33m", 2: "\x1b[36m", 3: "\x1b[35m", 4: "\x1b[34m"}
    code = colors.get(level, "\x1b[37m")
    return f"{code}{text}\x1b[0m"


def _color_enabled() -> bool:
    """Return True when ANSI coloring should be enabled based on `COLOR` and stderr TTY status."""

    if COLOR == "never":
        return False
    if COLOR == "always":
        return True
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


def _echo(level: int, category: str, when_val: str | None, msg: str) -> None:
    """Conditionally output a debug message to stderr according to configured filters and level."""

    if DEBUG_LEVEL <= 0:
        return
    if level > DEBUG_LEVEL:
        return
    if DEBUG_TARGET_CATEGORY and DEBUG_TARGET_CATEGORY != "all" and category != DEBUG_TARGET_CATEGORY:
        return
    if DEBUG_TARGET_WHEN and when_val:
        if DEBUG_TARGET_WHEN not in when_val:
            return

    out = f"[DEBUG:{level}:{category}] {msg}"
    out = _color(out, level)
    try:
        print(out, file=sys.stderr)
    except Exception:
        pass
