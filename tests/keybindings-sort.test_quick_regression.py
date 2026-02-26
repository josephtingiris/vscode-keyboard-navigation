#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Quick regression checks for `bin/keybindings-sort.py`.

This test focuses on fast, high-signal checks that run in seconds and can be
used between larger benchmark runs.
"""

import os
import subprocess
import sys
import unittest
import py_compile
from textwrap import dedent


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")
REFERENCE_INPUT = os.path.join(REPO_ROOT, "references", "keybindings.surface.vi.jsonc")


def run_sort(input_text: str, args: list[str] | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run keybindings-sort with text input and optional args."""
    cmd = [sys.executable, SCRIPT]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        input=input_text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=REPO_ROOT,
    )


class KeybindingsSortQuickRegressionTests(unittest.TestCase):
    """Fast regression checks for keybindings-sort behavior."""

    def test_script_compiles(self) -> None:
        py_compile.compile(SCRIPT, doraise=True)

    def test_duplicate_clone_toggle(self) -> None:
        payload = dedent(
            """
            [
              {
                "key": "ctrl+x",
                "command": "workbench.action.closeActiveEditor",
                "when": "editorTextFocus && !editorReadonly"
              },
              {
                "key": "ctrl+x",
                "command": "workbench.action.closeActiveEditor",
                "when": "editorTextFocus && !editorReadonly"
              }
            ]
            """
        )

        hidden = run_sort(payload, ["-d"])
        self.assertEqual(hidden.returncode, 0, msg=hidden.stderr.decode("utf-8"))
        hidden_out = hidden.stdout.decode("utf-8")
        self.assertEqual(hidden_out.count('"key": "ctrl+x"'), 1)

        shown = run_sort(payload, ["-d", "-o"])
        self.assertEqual(shown.returncode, 0, msg=shown.stderr.decode("utf-8"))
        shown_out = shown.stdout.decode("utf-8")
        self.assertGreaterEqual(shown_out.count('"key": "ctrl+x"'), 2)

    def test_reference_file_smoke(self) -> None:
        with open(REFERENCE_INPUT, "r", encoding="utf-8") as handle:
            payload = handle.read()

        cases = [
            [],
            ["-w", "focal-invariant", "-p", "when", "-s", "key"],
        ]

        for args in cases:
            proc = run_sort(payload, args)
            self.assertEqual(proc.returncode, 0, msg=f"args={args} stderr={proc.stderr.decode('utf-8')}")
            output = proc.stdout.decode("utf-8")
            self.assertTrue(output.strip())
            self.assertIn("[", output)


if __name__ == "__main__":
    unittest.main()
