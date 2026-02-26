#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Integration tests for v0.0.2 corpus files against bin/keybindings-sort.py

These are lightweight checks intended to run under `make test` quickly.
"""
import os
import subprocess
import sys
import traceback


def run_cmd(cmd, input_bytes=None):
    proc = subprocess.run(cmd, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


def test_corpus_roundtrip():
    repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
    script = os.path.join(repo_root, 'bin', 'keybindings-sort.py')
    variants = [
        'keybindings.corpus.jsonc',
        'keybindings.corpus.all.jsonc',
        'keybindings.corpus.emacs.jsonc',
        'keybindings.corpus.kbm.jsonc',
        'keybindings.corpus.vi.jsonc',
    ]

    for name in variants:
        corpus = os.path.join(repo_root, 'references', name)
        print(f'CHECK {name}')
        if not os.path.exists(corpus):
            print('MISSING', corpus, file=sys.stderr)
            raise SystemExit(2)
        with open(corpus, 'rb') as f:
            data = f.read()

        proc = run_cmd([sys.executable, script], input_bytes=data)
        if proc.returncode != 0:
            print(f'FAILED {name} rc={proc.returncode}', file=sys.stderr)
            print('STDERR:', proc.stderr.decode(), file=sys.stderr)
            raise SystemExit(proc.returncode)
        out = proc.stdout.decode()
        if not out.strip():
            print(f'EMPTY OUTPUT {name}', file=sys.stderr)
            raise SystemExit(3)
        # basic content sanity checks
        if 'config.keyboardNavigation' in data.decode():
            if 'config.keyboardNavigation' not in out:
                print(f'Expected config.keyboardNavigation in output for {name}', file=sys.stderr)
                raise SystemExit(4)


if __name__ == '__main__':
    try:
        print('RUN test_corpus_roundtrip')
        test_corpus_roundtrip()
        print('OK')
        sys.exit(0)
    except SystemExit as e:
        raise
    except Exception:
        print('ERROR', file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
