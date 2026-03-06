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
import unittest
from typing import List, Tuple


SCRIPT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "bin", "keybindings-sort.py")
)
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


WHEN_RE = re.compile(r'"when"\s*:\s*"((?:[^"\\]|\\.)*)"')
KEY_RE = re.compile(r'"key"\s*:\s*"((?:[^"\\]|\\.)*)"')


def run_sorter(profile: str) -> str:
    cmd = [sys.executable, SCRIPT, "-w", profile]
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


def extract_objects(text: str) -> List[str]:
    objects: List[str] = []
    i = 0
    n = len(text)
    in_str = False
    esc = False
    depth = 0
    start = None
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        objects.append(text[start: i + 1])
                        start = None
        i += 1
    return objects


def unescape_json_string(s: str) -> str:
    try:
        return json.loads('"' + s + '"')
    except Exception:
        return s


def normalize_when(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def group_contiguous_by_when(objects: List[str]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    groups = []
    cur_when = None
    cur_items = []
    for obj in objects:
        m = WHEN_RE.search(obj)
        when_raw = unescape_json_string(m.group(1)) if m else ''
        when_norm = normalize_when(when_raw)
        k = KEY_RE.search(obj)
        key_raw = unescape_json_string(k.group(1)) if k else ''
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
    return groups


# Modifier-first ordering as requested by the user (outer loop order)
MODIFIER_ORDER = [
    "alt+",
    "ctrl+",
    "ctrl+alt+",
    "shift+alt+",
    "ctrl+alt+meta+",
    "ctrl+shift+alt+",
    "shift+alt+meta+",
    "ctrl+shift+alt+meta+",
]


def split_modifiers_and_base(key: str) -> Tuple[str, str]:
    # Split on last '+' to separate modifiers from base key
    if '+' in key:
        parts = key.rsplit('+', 1)
        # handle trailing '+' meaning the literal key is '+' (e.g., 'alt++')
        mods = parts[0] + '+'
        base = parts[1] if parts[1] != '' else '+'
    else:
        mods = ''
        base = key
    return mods, base


def expected_order_modifier_first(keys: List[str]) -> List[str]:
    # Build unique set of keys (we'll sort and return unique list)
    unique = list(dict.fromkeys(k for k in keys if k))

    def rank_key(k: str):
        mods, base = split_modifiers_and_base(k)
        try:
            rank = MODIFIER_ORDER.index(mods)
        except ValueError:
            rank = len(MODIFIER_ORDER)
        # Use UTF-8 bytes for stable, bytewise ordering similar to LC_ALL=C
        return (rank, base.encode('utf-8'))

    sorted_keys = sorted(unique, key=rank_key)
    return sorted_keys


class ModifierFirstOrderingTests(unittest.TestCase):
    def test_modifier_first_block_order(self):
        out = run_sorter('focal-invariant')
        objects = extract_objects(out)
        groups = group_contiguous_by_when(objects)

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

            exp = expected_order_modifier_first(keys)
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


if __name__ == '__main__':
    unittest.main()
