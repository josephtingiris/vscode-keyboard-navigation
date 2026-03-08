#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Test when block invariants (extras).
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

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "references", "keybindings.surface.all.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "references", "keybindings.surface.vi.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")

#
# classes
#


#
# functions
#


def normalize_key_for_compare(key_value: str) -> str:
    return _keybindings._normalize_key_for_compare(key_value)


def extract_objects_from_jsonc(text: str):
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
    clean = _keybindings._strip_json_comments(obj_text)
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    try:
        return json.loads(clean)
    except Exception:
        return None


def test_when_block_invariants_extra():
    with open(DEFAULT_INPUT_FULL, 'r', encoding='utf-8') as fh:
        inp = fh.read()

    proc = subprocess.run(['python3', KEYBINDINGS_SORT_PY, '-w', 'focal-invariant'], input=inp, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr

    out_text = proc.stdout
    objs = extract_objects_from_jsonc(out_text)
    assert objs

    parsed_objs = []
    whens = []
    for o in objs:
        p = parse_obj_text(o)
        if p is None:
            continue
        parsed_objs.append((o, p))
        whens.append(_io._normalize_whitespace(p.get('when', '') or ''))

    # contiguity
    idxs = {}
    for i, w in enumerate(whens):
        idxs.setdefault(w, []).append(i)
    bad = [(k, arr) for k, arr in idxs.items() if arr and (arr[-1] - arr[0] + 1) != len(arr)]
    assert not bad, f"Non-contiguous whens: {bad[:5]}"

    # in-block ordering: delegate to package comparator generator
    def _key_sort_tuple_from_key(key_raw: str):
        return _keybindings._group_sort_tuple_from_key_string(key_raw)

    i = 0
    n = len(whens)
    viol = []
    while i < n:
        j = i + 1
        while j < n and whens[j] == whens[i]:
            j += 1
        block = parsed_objs[i:j]
        keys_block = [p[1].get('key', '') or '' for p in block]
        tuples = [_key_sort_tuple_from_key(k) for k in keys_block]
        sorted_idx = sorted(range(len(tuples)), key=lambda idx: tuples[idx])
        if sorted_idx != list(range(len(tuples))):
            viol.append((whens[i], i, j - 1, keys_block[:6]))
        i = j
    assert not viol, f"In-block ordering violations: {viol[:5]}"


#
# main
#


sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
