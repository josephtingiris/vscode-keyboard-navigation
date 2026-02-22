#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Focused CLI tests for `bin/keybindings-duplicate.py`.
"""

import os
import subprocess
import sys
import unittest
from textwrap import dedent


SCRIPT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "bin", "keybindings-duplicate.py")
)
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def run_dup(input_text: str, args: list[str] | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run the duplicate script with optional args and stdin input."""
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


class KeybindingsDuplicateCliTests(unittest.TestCase):
    """CLI behavior tests for keybindings-duplicate."""

    def test_help_exits_99(self) -> None:
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        self.assertEqual(proc.returncode, 99)
        self.assertIn("usage:", proc.stdout.decode("utf-8").lower())

    def test_mismatched_from_to_exits_99(self) -> None:
        proc = run_dup(
            "[]\n",
            ["-f", "h,j", "-t", "left"],
        )
        self.assertEqual(proc.returncode, 99)
        self.assertIn("--from and --to", proc.stderr.decode("utf-8"))

    def test_duplicate_annotations_present(self) -> None:
        data = dedent(
            """
            [
              {
                "key": "alt+h",
                "command": "workbench.action.left a1b2",
                "when": "editorFocus && config.keyboardNavigation.enabled"
              },
              {
                "key": "alt+h",
                "command": "workbench.action.left a1b2",
                "when": "config.keyboardNavigation.enabled && editorFocus"
              }
            ]
            """
        )

        proc = run_dup(data, ["-f", "h", "-t", "left", "-m", "alt"])
        self.assertEqual(proc.returncode, 0)
        out = proc.stdout.decode("utf-8")
        self.assertIn("// DUPLICATE object detected for alt+h/", out)
        self.assertIn("// DUPLICATE id a1b2 detected for alt+h/", out)
        self.assertRegex(out, r'"key":\s*"alt\+left"')
        self.assertRegex(out, r'"command":\s*"alt\+left\s+[0-9a-f]{4}"')

    def test_reference_inputs_smoke(self) -> None:
        files = [
            "references/keybindings.json",
            "references/keybindings.corpus.jsonc",
            "references/keybindings.corpus.emacs.jsonc",
            "references/keybindings.corpus.kbm.jsonc",
            "references/keybindings.corpus.vi.jsonc",
        ]
        for rel_path in files:
            path = os.path.join(REPO_ROOT, rel_path)
            with open(path, "r", encoding="utf-8") as handle:
                payload = handle.read()
            proc = run_dup(payload, ["-f", "h,j,k,l", "-t", "left,down,up,right"])
            self.assertEqual(proc.returncode, 0, msg=rel_path)
            self.assertIn("[", proc.stdout.decode("utf-8"), msg=rel_path)


if __name__ == "__main__":
    unittest.main()
