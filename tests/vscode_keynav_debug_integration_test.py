#!/usr/bin/env python3
"""Integration test: run bin/keybindings-sort.py with debug flags and assert debug output."""
from __future__ import annotations

import subprocess
import sys
import os


def main() -> int:
    script = os.path.join('..', 'bin', 'keybindings-sort.py')
    if not os.path.exists(script):
        print(f"error: {script} not found", file=sys.stderr)
        return 2

    proc = subprocess.run(
        [sys.executable, script, '--debug', '2', '--color', 'always'],
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
