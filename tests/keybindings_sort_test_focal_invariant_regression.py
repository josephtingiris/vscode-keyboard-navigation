#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Regression test: ensure full `focal-invariant` output matches golden file

Runs: cat tests/data/keybindings-test-data.jsonc | bin/keybindings-sort.py -w focal-invariant
and diffs against tests/data/keybindings-test-data.focal-invariant. Fails if different.
"""

import os
import subprocess
import sys
import unittest


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")
INPUT_FIXTURE = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.jsonc")
GOLDEN = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.focal-invariant")


class KeybindingsSortFocalInvariantRegression(unittest.TestCase):
    def test_focal_invariant_output_matches_golden(self):
        with open(INPUT_FIXTURE, 'rb') as fh:
            inp = fh.read()

        proc = subprocess.run([sys.executable, SCRIPT, '-w', 'focal-invariant'], input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode('utf-8'))
        out = proc.stdout.decode('utf-8', errors='replace')

        with open(GOLDEN, 'r', encoding='utf-8') as fh:
            expected = fh.read()

        actual = out

        if actual != expected:
            import difflib
            diff = ''.join(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True), fromfile='expected', tofile='actual'))
            self.fail("focal-invariant output differs from golden:\n" + diff)


if __name__ == '__main__':
    unittest.main()
