#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Test --when-prefix functionality in `bin/keybindings-sort.py`.
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


def test_when_prefix_prioritizes_and_sorts():
    data = [
        {"key": "z", "command": "c", "when": "config.keyboardNavigation.zed"},
        {"key": "a", "command": "d", "when": "other"},
        {"key": "m", "command": "e", "when": "config.keyboardNavigation.alpha"},
        {"key": "b", "command": "f", "when": "something"},
    ]

    out = run_sort(['--primary', 'when', '--when-prefix', 'config.keyboardNavigation.'], data)
    keys = [e['key'] for e in out]

    # matched group (config.keyboardNavigation.) should be first and sorted by key
    assert keys[0:2] == ['m', 'z']
    # all keys preserved
    assert set(keys) == {'a', 'b', 'm', 'z'}


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
