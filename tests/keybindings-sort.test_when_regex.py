#!/usr/bin/env python3
import json
import subprocess
import sys
import traceback


def run_sort(args, input_data):
    proc = subprocess.run([sys.executable, 'bin/keybindings-sort.py'] + args,
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

    # two regexes: keyboardNavigation first, then editor
    out = run_sort(['--primary', 'when', '--when-regex', '^config\\.keyboardNavigation\\.,^config\\.editor\\.'], data)
    keys = [e['key'] for e in out]

    # keyboardNavigation matches first (m,z sorted), then editor matches (b,x sorted), then remaining
    assert keys[0:2] == ['m', 'z']
    assert keys[2:4] == ['b', 'x']
    assert 'a' in keys


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
