#!/usr/bin/env python3
"""Unit tests for vscode_keynav.debug (standalone script for tests/ Makefile).

This script performs lightweight assertions and exits non-zero on failure.
"""
from __future__ import annotations

import io
import sys

from vscode_keynav import debug


def run_unit_tests() -> None:
    # apply numeric level and target/category parsing
    debug.apply_debug_settings(["2", "target=can"], color="never")
    assert debug.DEBUG_LEVEL == 2
    assert debug.DEBUG_TARGET_CATEGORY == "can"

    # apply when filter
    debug.apply_debug_settings(["when=foo"], color="never")
    assert debug.DEBUG_TARGET_WHEN == "foo"

    # echo prints at or below level
    buf = io.StringIO()
    real_stderr = sys.stderr
    try:
        sys.stderr = buf
        debug.apply_debug_settings(["2"], color="never")
        debug.echo(2, "can", "foo", "hello")
        out = buf.getvalue()
        assert "[DEBUG:2:can] hello" in out

        # higher level should not print
        buf.truncate(0)
        buf.seek(0)
        debug.apply_debug_settings(["1"], color="never")
        debug.echo(2, "can", "foo", "nope")
        assert buf.getvalue() == ""
    finally:
        sys.stderr = real_stderr

    # color formatting when COLOR = 'always'
    debug.COLOR = "always"
    colored = debug._debug_color("x", 2)
    assert "\x1b[" in colored


if __name__ == "__main__":
    try:
        run_unit_tests()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise
    print("OK")
