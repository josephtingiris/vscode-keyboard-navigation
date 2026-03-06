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
import subprocess
import sys
import tempfile
import unittest

from textwrap import dedent


SCRIPT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "bin", "keybindings-corpus.py")
)
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


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
    def test_inject_comments_and_validate_json(self):
        # ensure the reference file is not modified
        rel = "references/keybindings.json"
        ref_path = os.path.join(REPO_ROOT, rel)
        with open(ref_path, "r", encoding="utf-8") as fh:
            orig = fh.read()

        proc = subprocess.run(
            [sys.executable, SCRIPT, "-c", rel],
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


if __name__ == "__main__":
    unittest.main()
