#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Focused duplicate-regression checks for `bin/keybindings-sort.py`.

These tests lock down duplicate-object behavior that is easy to regress while
optimizing the sorter: exact clone hiding, duplicate annotations, command
suffix IDs, missing IDs, and JSON-equivalent duplicates that differ only in
comments or formatting.
"""

import os
import subprocess
import sys
import unittest
from textwrap import dedent


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")


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


class KeybindingsSortDuplicateRegressionTests(unittest.TestCase):
    """Regression checks for duplicate-object handling in keybindings-sort."""

    def test_exact_object_clones_are_hidden_by_default(self) -> None:
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

        proc = run_sort(payload)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))
        out = proc.stdout.decode("utf-8")
        self.assertEqual(out.count('"key": "ctrl+x"'), 1)
        self.assertNotIn("exact object match", out)

    def test_exact_object_clones_are_shown_and_annotated_with_object_clones(self) -> None:
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

        proc = run_sort(payload, ["-o"])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))
        out = proc.stdout.decode("utf-8")
        self.assertEqual(out.count('"key": "ctrl+x"'), 2)
        self.assertIn("// DUPLICATE key: 'ctrl+x' when: 'editorTextFocus && !editorReadonly' (exact object match)", out)

    def test_duplicate_pair_with_and_without_command_suffix_id_is_preserved(self) -> None:
        payload = dedent(
            """
            [
              {
                "key": "alt+h",
                "command": "workbench.action.left a1b2",
                "when": "editorFocus && config.keyboardNavigation.enabled"
              },
              {
                "key": "alt+h",
                "command": "workbench.action.left",
                "when": "config.keyboardNavigation.enabled && editorFocus"
              }
            ]
            """
        )

        proc = run_sort(payload, ["-w", "focal-invariant", "-p", "when", "-s", "key", "-o"])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))
        out = proc.stdout.decode("utf-8")
        self.assertEqual(out.count('"key": "alt+h"'), 2)
        self.assertIn('"command": "workbench.action.left a1b2"', out)
        self.assertIn('"command": "workbench.action.left"', out)
        self.assertIn("// DUPLICATE key: 'alt+h' when: 'config.keyboardNavigation.enabled && editorFocus'", out)

    def test_json_equivalent_duplicates_are_annotated_even_when_comments_differ(self) -> None:
        payload = dedent(
            """
            [
              {
                // first
                "key": "alt+h",
                "command": "workbench.action.left",
                "when": "editorFocus && config.keyboardNavigation.enabled"
              },
              {
                // second
                "key": "alt+h",
                "command": "workbench.action.left",
                "when": "config.keyboardNavigation.enabled && editorFocus"
              }
            ]
            """
        )

        proc = run_sort(payload, ["-w", "focal-invariant", "-p", "when", "-s", "key", "-o"])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))
        out = proc.stdout.decode("utf-8")
        self.assertGreaterEqual(out.count("// DUPLICATE JSON object (json-hash="), 2)
        self.assertIn("// first", out)
        self.assertIn("// second", out)


if __name__ == "__main__":
    unittest.main()
