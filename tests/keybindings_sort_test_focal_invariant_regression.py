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


#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")

GOLDEN = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.focal-invariant")


#
# classes
#


class KeybindingsSortFocalInvariantRegression(unittest.TestCase):
    def test_focal_invariant_output_matches_golden(self):
        with open(DEFAULT_INPUT_FULL, 'rb') as fh:
            inp = fh.read()

        proc = subprocess.run([sys.executable, KEYBINDINGS_SORT_PY, '-w', 'focal-invariant'], input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=REPO_ROOT)
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
