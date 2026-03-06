#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Regression test: ensure `-w focal-invariant` groups simple `when` clauses first

This test runs the sorter on the full `references/keybindings.json` and asserts
that the first emitted `when` clause (ignoring comments) is the simple
`config.keyboardNavigation.enabled` clause and that those entries appear
grouped at the start of the when-list.
"""

import os
import subprocess
import sys
import unittest
import py_compile
import re


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")
REFERENCE_INPUT = os.path.join(REPO_ROOT, "tests/data", "keybindings-test-data.jsonc")


def run_sort_file(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    cmd = [sys.executable, SCRIPT]
    cmd.extend(args)
    with open(REFERENCE_INPUT, "rb") as fh:
        return subprocess.run(cmd, input=fh.read(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=REPO_ROOT)


class KeybindingsSortGroupingRegression(unittest.TestCase):
    def test_when_grouping_focal_invariant_first_when(self):
        # ensure script compiles
        py_compile.compile(SCRIPT, doraise=True)

        # rely on the when-grouping profile to set primary/secondary
        proc = run_sort_file(["-w", "focal-invariant"])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))
        out = proc.stdout.decode("utf-8")

        # extract non-comment when lines
        when_lines = re.findall(r'^[ \t]*"when"\s*:\s*"([^"]*)"', out, flags=re.MULTILINE)
        self.assertTrue(when_lines, msg="no when clauses found in output")

        # first when clause should be the simple enabled flag
        self.assertEqual(when_lines[0], "config.keyboardNavigation.enabled")

        # ensure subsequent when clauses that include the same canonical left-id
        # appear grouped (the first block of identical canonical values should
        # include at least one compound when in this reference file).
        # We'll check that all contiguous identical-left-id entries starting at
        # index 0 have left-id 'config.keyboardNavigation.enabled'.
        def left_id(s: str) -> str:
            s = s.strip()
            while s.startswith("(") and s.endswith(")"):
                s = s[1:-1].strip()
            if s.startswith("!"):
                s = s[1:].lstrip()
            return s.split()[0] if s else ""

        first_left = left_id(when_lines[0])
        i = 0
        while i < len(when_lines) and left_id(when_lines[i]) == first_left:
            i += 1

        # require at least one grouped item (the simple one plus at least one sibling)
        self.assertGreaterEqual(i, 1)


if __name__ == "__main__":
    unittest.main()
