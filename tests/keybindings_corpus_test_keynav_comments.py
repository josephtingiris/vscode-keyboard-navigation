#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Tests that `bin/keybindings-corpus.py` can inject comments from a
reference JSONC file without modifying the source file, and that the
emitted JSONC can be stripped and parsed as valid JSON.
"""

import json
import os
import subprocess
import unittest

from vscode_keynav import cli as _cli
from vscode_keynav import keybindings as _keybindings


#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "references", "keybindings.corpus.all.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "references", "keybindings.corpus.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")

KEYBINDINGS_CORPUS_PY = os.path.join(REPO_ROOT, "bin", "keybindings-corpus.py")

PYTHON_EXEC = _cli._get_python_exec()


#
# classes
#


class KeynavCommentsTests(unittest.TestCase):
    def _run_corpus(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        """Run keybindings-corpus and return the completed process."""

        return subprocess.run(
            [PYTHON_EXEC, KEYBINDINGS_CORPUS_PY, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
        )

    def _run_corpus_json(self, args: list[str]) -> list[dict]:
        """Run keybindings-corpus and parse stdout as JSON list."""

        proc = self._run_corpus(args)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))
        parsed = json.loads(proc.stdout.decode("utf-8"))
        self.assertIsInstance(parsed, list)
        return parsed

    def test_default_output_does_not_add_feature_gate_contexts(self):
        parsed = self._run_corpus_json(["--comments", "none"])

        juke_record = next(item for item in parsed if item["key"] == "alt+end")
        self.assertNotIn("config.keyboardNavigation.juke.enabled", juke_record["when"])

        split_record = next(item for item in parsed if item["key"] == "alt+-")
        self.assertNotIn("config.keyboardNavigation.split.enabled", split_record["when"])

    def test_add_context_augments_generated_when_clauses(self):
        parsed = self._run_corpus_json(
            ["--comments", "none", "--add-context", "editorTextFocus && !inputFocus"]
        )

        juke_record = next(item for item in parsed if item["key"] == "alt+end")
        self.assertIn("config.keyboardNavigation.juke.enabled", juke_record["when"])
        self.assertIn("editorTextFocus", juke_record["when"])
        self.assertIn("!inputFocus", juke_record["when"])

        split_record = next(item for item in parsed if item["key"] == "alt+-")
        self.assertIn("config.keyboardNavigation.split.enabled", split_record["when"])
        self.assertIn("editorTextFocus", split_record["when"])
        self.assertIn("!inputFocus", split_record["when"])

    def test_inject_comments_and_validate_json(self):
        # ensure the reference file is not modified

        with open(DEFAULT_INPUT_FULL, "r", encoding="utf-8") as fh:
            orig = fh.read()

        proc = self._run_corpus(["-c", DEFAULT_INPUT_FULL])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))

        emitted = proc.stdout.decode("utf-8")

        # strip comments and trailing commas, then parse JSON
        stripped = _keybindings._strip_json_comments(emitted)
        stripped = _keybindings._strip_trailing_commas(stripped)
        parsed = json.loads(stripped)
        self.assertIsInstance(parsed, list)

        # verify original reference file is unchanged
        with open(DEFAULT_INPUT_FULL, "r", encoding="utf-8") as fh:
            after = fh.read()
        self.assertEqual(orig, after)

    def test_add_context_updates_comments_mode_when_output_only(self):
        with open(DEFAULT_INPUT_FULL, "r", encoding="utf-8") as fh:
            orig = fh.read()

        proc = self._run_corpus(["-c", DEFAULT_INPUT_FULL, "--add-context", "editorTextFocus"])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))

        emitted = proc.stdout.decode("utf-8")
        self.assertIn("config.keyboardNavigation.juke.enabled", emitted)
        self.assertIn("config.keyboardNavigation.split.enabled", emitted)
        self.assertIn("editorTextFocus", emitted)

        with open(DEFAULT_INPUT_FULL, "r", encoding="utf-8") as fh:
            after = fh.read()
        self.assertEqual(orig, after)


#
# main
#


if __name__ == "__main__":
    unittest.main()
