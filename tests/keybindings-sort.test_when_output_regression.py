#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Regression test: ensure `grep "when" | uniq` output matches golden file

Runs: cat tests/data/keybindings-test-data.jsonc | keybindings-sort.py -w focal-invariant | grep "when" | uniq
and diffs against tests/data/keybindings-test-data.when. Fails if different.
"""

import os
import subprocess
import sys
import unittest
import re

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")
INPUT_FIXTURE = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.jsonc")
GOLDEN = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.when")


def extract_when_uniq(output_text: str) -> str:
    # emulate: grep "when" | uniq
    lines = []
    for line in output_text.splitlines():
        if '"when"' in line:
            lines.append(line.rstrip())
    # uniq: remove consecutive duplicates
    uniqed = []
    prev = None
    for l in lines:
        if l != prev:
            uniqed.append(l)
        prev = l
    return "\n".join(uniqed) + ("\n" if uniqed else "")


class KeybindingsSortWhenOutputRegression(unittest.TestCase):
    def test_when_output_matches_golden(self):
        with open(INPUT_FIXTURE, 'rb') as fh:
            inp = fh.read()

        proc = subprocess.run([sys.executable, SCRIPT, '-w', 'focal-invariant'], input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode('utf-8'))
        out = proc.stdout.decode('utf-8', errors='replace')

        actual = extract_when_uniq(out)

        with open(GOLDEN, 'r', encoding='utf-8') as fh:
            expected = fh.read()

        if actual != expected:
            # provide helpful diff in assertion message
            import difflib
            diff = ''.join(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True), fromfile='expected', tofile='actual'))
            self.fail("when-output differs from golden:\n" + diff)


if __name__ == '__main__':
    unittest.main()
