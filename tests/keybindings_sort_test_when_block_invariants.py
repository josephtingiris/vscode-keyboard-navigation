#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Test when block invariants.
"""

import json
import os

from pathlib import Path

import re
import subprocess
import sys

from vscode_keynav import io as _io
from vscode_keynav import keybindings as _keybindings

#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "tests", "data", "keybindings-test-data.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")

#
# functions
#


def strip_json_comments(s: str) -> str:
    s = re.sub(r'//.*?\n', '\n', s)
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    return s


def extract_objects_from_jsonc(text: str):
    # crude object extractor: find top-level { ... } occurrences
    objs = []
    depth = 0
    start = None
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(text[start:i + 1])
                start = None
        i += 1
    return objs


def parse_obj_text(obj_text: str):
    clean = strip_json_comments(obj_text)
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    try:
        return json.loads(clean)
    except Exception:
        return None


def test_when_blocks_contiguous_and_modifier_first():
    with open(DEFAULT_INPUT_FULL, 'r', encoding='utf-8') as fh:
        inp = fh.read()

    proc = subprocess.run([sys.executable, str(KEYBINDINGS_SORT_PY), '-w', 'focal-invariant'], input=inp, text=True, capture_output=True)
    assert proc.returncode == 0, f"sorter failed: {proc.stderr}"

    out_text = proc.stdout

    # extract objects in output
    objs = extract_objects_from_jsonc(out_text)
    assert objs, "no JSON objects found in sorter output"

    # build canonical when sequence and keys per object
    whens = []
    keys = []
    for o in objs:
        parsed = parse_obj_text(o)
        if parsed is None:
            # skip unparsable objects
            continue
        keys.append(parsed.get('key', '') or '')
        whens.append(_io._normalize_whitespace(parsed.get('when', '') or ''))

    # contiguity: for each canonical when, occurrences must be contiguous
    idxs = {}
    for i, w in enumerate(whens):
        idxs.setdefault(w, []).append(i)
    non_contig = []
    for k, arr in idxs.items():
        if not arr:
            continue
        if arr[-1] - arr[0] + 1 != len(arr):
            non_contig.append((k, len(arr), arr[0], arr[-1]))
    assert not non_contig, f"Found non-contiguous canonical when blocks: {non_contig[:10]}"

    # in-block modifier-first: each contiguous block is ordered by the
    # same key the sorter uses (mods_norm, token_seq, token_count).
    def _key_sort_tuple_from_key(key_raw: str):
        return _keybindings._group_sort_tuple_from_key_string(key_raw)

    i = 0
    violations = []
    n = len(whens)
    while i < n:
        j = i + 1
        while j < n and whens[j] == whens[i]:
            j += 1
        # use already-parsed keys for this contiguous block
        keys_block = keys[i:j]
        tuples = [_key_sort_tuple_from_key(k) for k in keys_block]
        # check stable sorted order
        sorted_indices = sorted(range(len(tuples)), key=lambda idx: tuples[idx])
        if sorted_indices != list(range(len(tuples))):
            violations.append((whens[i], i, j - 1, keys_block[:8], [t.decode('utf-8', errors='ignore') if isinstance(t, bytes) else t for t in tuples[:8]]))
        i = j
    assert not violations, f"Modifier-first ordering violated in {len(violations)} blocks; sample: {violations[:5]}"

#
# main
#


if __name__ == "__main__":
    test_when_blocks_contiguous_and_modifier_first()
    print("OK")
