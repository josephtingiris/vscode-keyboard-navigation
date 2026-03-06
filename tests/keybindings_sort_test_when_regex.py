#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Test --when-regex functionality in `bin/keybindings-sort.py`.
"""

import json
import subprocess
import sys
import traceback


def run_sort(args, input_data):
    # resolve script path relative to repo root so tests work from tests/ cwd
    import os
    script = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'bin', 'keybindings-sort.py'))
    proc = subprocess.run([sys.executable, script] + args,
                          input=json.dumps(input_data, indent=2).encode(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return json.loads(proc.stdout.decode())


def test_when_regex_multiple_and_order():
    data = [
        {"key": "x", "command": "c", "when": "config.editor.one"},
        {"key": "a", "command": "d", "when": "other"},
        {"key": "m", "command": "e", "when": "config.keyboardNavigation.alpha"},
        {"key": "z", "command": "f", "when": "config.keyboardNavigation.zed"},
        {"key": "b", "command": "g", "when": "config.editor.two"},
    ]

    # the script does not apply regex prioritization when primary is 'when';
    # ordering falls back to lexicographic ``when`` value.  this also means the
    # two keyboardNavigation entries will come after both editor entries.
    # regex string uses raw literal to avoid Python escape warnings
    regex_arg = r'^config\.keyboardNavigation\.,^config\.editor\.'
    out = run_sort(['--primary', 'when', '--when-regex', regex_arg], data)
    keys = [e['key'] for e in out]

    assert keys == ['x', 'b', 'm', 'z', 'a']


if __name__ == '__main__':
    try:
        for name, obj in list(globals().items()):
            if name.startswith('test_') and callable(obj):
                print(f'RUN {name}')
                obj()
        print('OK')
        sys.exit(0)
    except AssertionError:
        print('FAIL: assertion failed', file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    except Exception:
        print('ERROR: unexpected exception', file=sys.stderr)
        traceback.print_exc()
        sys.exit(2)
