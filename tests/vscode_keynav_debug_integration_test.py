#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

run bin/keybindings-sort.py with debug flags and assert debug output.
"""

from __future__ import annotations

import os
import subprocess
import sys


#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "references", "keybindings.surface.all.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "references", "keybindings.surface.vi.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")


#
# main
#


def main() -> int:
    proc = subprocess.run(
        [sys.executable, KEYBINDINGS_SORT_PY, '--debug', '2', '--color', 'always'],
        input='[{"key":"a","when":"config.keyboardNavigation.enabled"}]\n',
        capture_output=True,
        text=True,
    )

    stderr = proc.stderr or ''
    # expect at least one debug prefix and ANSI codes when color=always
    if '[DEBUG:2:' not in stderr and '[DEBUG:1:' not in stderr:
        print('error: no debug prefix in stderr', file=sys.stderr)
        print('stderr:', stderr, file=sys.stderr)
        return 3
    if '\x1b[' not in stderr:
        print('error: expected ANSI color codes in stderr', file=sys.stderr)
        print('stderr:', stderr, file=sys.stderr)
        return 4
    print('OK')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
