#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Unit tests for vscode_keynav.debug (standalone script for tests/ Makefile).

This script performs lightweight assertions and exits non-zero on failure.
"""

from __future__ import annotations

import io
import os
import sys

from vscode_keynav import debug as _debug


#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "references", "keybindings.surface.all.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "references", "keybindings.surface.vi.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")

#
# functions
#


def _run_unit_tests() -> None:
    # apply numeric level and target/category parsing
    _debug._apply_settings(["2", "target=can"], color="never")
    assert _debug._DEBUG_LEVEL == 2
    assert _debug._DEBUG_TARGET_CATEGORY == "can"

    # apply when filter
    _debug._apply_settings(["when=foo"], color="never")
    assert _debug._DEBUG_TARGET_WHEN == "foo"

    # echo prints at or below level
    buf = io.StringIO()
    real_stderr = sys.stderr
    try:
        sys.stderr = buf
        _debug._apply_settings(["2"], color="never")
        _debug._echo(2, "can", "foo", "hello")
        out = buf.getvalue()
        assert "[DEBUG:2:can] hello" in out

        # higher level should not print
        buf.truncate(0)
        buf.seek(0)
        _debug._apply_settings(["1"], color="never")
        _debug._echo(2, "can", "foo", "nope")
        assert buf.getvalue() == ""
    finally:
        sys.stderr = real_stderr

    # color formatting when COLOR = 'always'
    _debug._COLOR = "always"
    colored = _debug._color("x", 2)
    assert "\x1b[" in colored


#
# main
#


if __name__ == "__main__":
    try:
        _run_unit_tests()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise
    print("OK")
