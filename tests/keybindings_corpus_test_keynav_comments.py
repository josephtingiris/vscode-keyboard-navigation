#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Tests that `bin/keybindings-corpus.py` can inject comments from a
reference JSONC file without modifying the source file, and that the
emitted JSONC can be stripped and parsed as valid JSON.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "bin", "keybindings-corpus.py")
)
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def get_path_python() -> str:
    python_path = shutil.which("python3") or shutil.which("python")
    if python_path is None:
        raise RuntimeError("python3 or python must be available on PATH")
    return python_path


PATH_PYTHON = get_path_python()


def strip_jsonc(text: str) -> str:
    """Strip JSONC comments (line `//` and block `/* */`) while preserving strings."""
    out = []
    i = 0
    n = len(text)
    in_string = False
    string_char = ""
    esc = False
    in_line = False
    in_block = False
    while i < n:
        ch = text[i]
        nxt2 = text[i:i + 2] if i + 2 <= n else ""
        if in_line:
            if ch == "\n":
                out.append(ch)
                in_line = False
            i += 1
            continue
        if in_block:
            if nxt2 == '*/':
                i += 2
                in_block = False
            else:
                i += 1
            continue
        if in_string:
            out.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        # default
        if nxt2 == '//':
            in_line = True
            i += 2
            continue
        if nxt2 == '/*':
            in_block = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r',\s*([}\]])', r"\1", text)


class KeynavCommentsTests(unittest.TestCase):
    def test_default_output_does_not_add_feature_gate_contexts(self):
        proc = subprocess.run(
            [
                PATH_PYTHON,
                SCRIPT,
                "--comments",
                "none",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))

        parsed = json.loads(proc.stdout.decode("utf-8"))
        self.assertIsInstance(parsed, list)

        juke_record = next(item for item in parsed if item["key"] == "alt+end")
        self.assertNotIn("config.keyboardNavigation.juke.enabled", juke_record["when"])

        split_record = next(item for item in parsed if item["key"] == "alt+-")
        self.assertNotIn("config.keyboardNavigation.split.enabled", split_record["when"])

    def test_add_context_augments_generated_when_clauses(self):
        proc = subprocess.run(
            [
                PATH_PYTHON,
                SCRIPT,
                "--comments",
                "none",
                "--add-context",
                "editorTextFocus && !inputFocus",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))

        parsed = json.loads(proc.stdout.decode("utf-8"))
        self.assertIsInstance(parsed, list)

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
        rel = "references/keybindings.json"
        ref_path = os.path.join(REPO_ROOT, rel)
        with open(ref_path, "r", encoding="utf-8") as fh:
            orig = fh.read()

        proc = subprocess.run(
            [PATH_PYTHON, SCRIPT, "-c", rel],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))

        # write stdout to a temp file for inspection (simulate redirect)
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".jsonc") as tmp:
            tmp.write(proc.stdout)
            tmp_name = tmp.name

        try:
            with open(tmp_name, "r", encoding="utf-8") as fh:
                emitted = fh.read()

            # strip comments and trailing commas, then parse JSON
            stripped = strip_jsonc(emitted)
            stripped = _strip_trailing_commas(stripped)
            parsed = json.loads(stripped)
            self.assertIsInstance(parsed, list)

            # vekeybindings_sort_test_performance.graphs.pyy original reference file unchanged
            with open(ref_path, "r", encoding="utf-8") as fh:
                after = fh.read()
            self.assertEqual(orig, after)
        finally:
            try:
                os.unlink(tmp_name)
            except Exception:
                pass

    def test_add_context_updates_comments_mode_when_output_only(self):
        rel = "references/keybindings.json"
        ref_path = os.path.join(REPO_ROOT, rel)
        with open(ref_path, "r", encoding="utf-8") as fh:
            orig = fh.read()

        proc = subprocess.run(
            [
                PATH_PYTHON,
                SCRIPT,
                "-c",
                rel,
                "--add-context",
                "editorTextFocus",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr.decode("utf-8"))

        emitted = proc.stdout.decode("utf-8")
        self.assertIn("config.keyboardNavigation.juke.enabled", emitted)
        self.assertIn("config.keyboardNavigation.split.enabled", emitted)
        self.assertIn("editorTextFocus", emitted)

        with open(ref_path, "r", encoding="utf-8") as fh:
            after = fh.read()
        self.assertEqual(orig, after)


if __name__ == "__main__":
    unittest.main()
