#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Unit test: validate in-block ordering of keybinding objects using
modifier-first ordering (modifiers before base key).

This test runs `bin/keybindings-sort.py -w focal-invariant`, groups
contiguous objects by their normalized `when` clause, and for each group
compares the observed unique-in-order `key` values to the expected
modifier-first ordering.

Exit: test failure on any mismatch.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from typing import List, Tuple

import unittest

from vscode_keynav import io as _io
from vscode_keynav import keybindings as _keybindings


#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

KEYBINDINGS_SORT_PY = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "bin", "keybindings-sort.py"))


#
# classes
#


class ModifierFirstOrderingTests(unittest.TestCase):
    def test_modifier_first_block_order(self):
        out = _run_sorter('focal-invariant')

        # parse array contents from the sorter output
        preamble, array_text, postamble = _keybindings._extract_preamble_postamble(out)
        pairs, trailing_comments = _keybindings._group_objects_with_comments(array_text)

        # group contiguous objects by their normalized literal `when` value
        groups = []
        cur_when = None
        cur_items = []
        for comments, obj in pairs:
            when_raw = _keybindings._extract_literal_when_from_object(obj) or ''
            when_norm = _io._normalize_whitespace(when_raw)
            key_raw = _keybindings._extract_literal_key_from_object(obj) or ''
            if cur_when is None:
                cur_when = when_norm
                cur_items = [(key_raw, obj)]
            elif when_norm == cur_when:
                cur_items.append((key_raw, obj))
            else:
                groups.append((cur_when, cur_items))
                cur_when = when_norm
                cur_items = [(key_raw, obj)]
        if cur_when is not None:
            groups.append((cur_when, cur_items))

        mismatches = []
        for idx, (when, items) in enumerate(groups):
            keys = [k for k, _ in items if k]
            if len(keys) <= 1:
                continue
            # observed: unique-in-order (first occurrences kept)
            seen = set()
            unique_obs = []
            for k in keys:
                if k in seen:
                    continue
                seen.add(k)
                unique_obs.append(k)

            exp = _expected_order_modifier_first(keys)
            if unique_obs != exp:
                mismatches.append((idx, when, unique_obs, exp))

        if mismatches:
            out_lines = [f'Found {len(mismatches)} mismatching blocks']
            for mi, (idx, when, obs, exp) in enumerate(mismatches, start=1):
                out_lines.append(f'\nMismatch #{mi} (block {idx})')
                out_lines.append(f'When: {when!r}')
                out_lines.append('\nActual unique-in-order keys:')
                out_lines.extend(f'  {k}' for k in obs)
                out_lines.append('\nExpected modifier-first keys:')
                out_lines.extend(f'  {k}' for k in exp)
            self.fail('\n'.join(out_lines))


#
# functions
#


def _expected_order_modifier_first(keys: List[str]) -> List[str]:
    unique = list(dict.fromkeys(k for k in keys if k))

    def _sort_tuple_from_key_string(key_raw: str):
        # construct a minimal object and delegate to the package's sort-key generator
        return _keybindings._group_sort_tuple_from_key_string(key_raw)

    return sorted(unique, key=_sort_tuple_from_key_string)


def _run_sorter(profile: str) -> str:
    cmd = [sys.executable, KEYBINDINGS_SORT_PY, "-w", profile]
    ref_path = os.path.join(REPO_ROOT, "references", "keybindings.json")
    if os.path.exists(ref_path):
        with open(ref_path, "r", encoding="utf-8") as fh:
            data = fh.read()
        proc = subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=30)
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout


#
# main
#

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

if __name__ == '__main__':
    unittest.main()
