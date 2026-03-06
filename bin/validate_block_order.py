#!/usr/bin/env python3
"""Validate in-block ordering of keybinding objects against LC_ALL=C dictionary sort.

Usage: bin/validate_block_order.py [--profile PROFILE] [--limit N]

Runs the `bin/keybindings-sort.py` sorter, parses the JSONC output into objects
robustly (balanced-brace parser that ignores braces in strings), groups
contiguous objects by their normalized `when` string, and for each group
compares the observed sequence of `key` values to the expected ordering from
`sort -u -d` with `LC_ALL=C`.

Exits with code 0 when all blocks match, or 2 when mismatches are found.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from typing import List, Tuple


def run_sorter(profile: str) -> str:
    cmd = [sys.executable, "bin/keybindings-sort.py", "-w", profile]
    # If the reference keybindings file exists, feed it to the sorter to avoid
    # the sorter blocking on stdin.
    ref_path = os.path.join(os.getcwd(), "references", "keybindings.json")
    if os.path.exists(ref_path):
        with open(ref_path, "r", encoding="utf-8") as fh:
            data = fh.read()
        proc = subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=30)
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def extract_objects(text: str) -> List[str]:
    """Return a list of top-level object text blocks by balanced-brace parsing.

    Handles strings and escaped quotes so braces inside strings are ignored.
    """
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


WHEN_RE = re.compile(r'"when"\s*:\s*"((?:[^"\\]|\\.)*)"')
KEY_RE = re.compile(r'"key"\s*:\s*"((?:[^"\\]|\\.)*)"')


def unescape_json_string(s: str) -> str:
    try:
        return json.loads('"' + s + '"')
    except Exception:
        return s


def normalize_when(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def group_contiguous_by_when(objects: List[str]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    groups: List[Tuple[str, List[Tuple[str, str]]]] = []
    cur_when = None
    cur_items: List[Tuple[str, str]] = []
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


def expected_order(keys: List[str]) -> List[str]:
    if not keys:
        return []
    env = {**os.environ, 'LC_ALL': 'C'}
    proc = subprocess.run(['sort', '-u', '-d'], input='\n'.join(keys), capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return [line for line in proc.stdout.splitlines() if line]


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', '-w', default='focal-invariant')
    ap.add_argument('--limit', '-n', type=int, default=10, help='max mismatches to show')
    args = ap.parse_args(argv)

    out = run_sorter(args.profile)
    objects = extract_objects(out)
    groups = group_contiguous_by_when(objects)

    mismatches = []
    for idx, (when, items) in enumerate(groups):
        keys = [k for k, _ in items if k]
        if len(keys) <= 1:
            continue
        exp = expected_order(keys)
        if keys != exp:
            mismatches.append((idx, when, keys, exp, items))
            if len(mismatches) >= args.limit:
                break

    print(f'Checked {len(groups)} blocks, mismatches: {len(mismatches)}')
    if mismatches:
        for mi, (idx, when, keys, exp, items) in enumerate(mismatches, start=1):
            print('\nMismatch #%d (block %d)' % (mi, idx))
            print('When:', repr(when))
            print('\nActual keys:')
            for k in keys:
                print('  ', k)
            print('\nExpected keys (LC_ALL=C sort -u -d):')
            for k in exp:
                print('  ', k)
            print('\nObjects in block:')
            for k, obj in items:
                head = '\n'.join(line for line in obj.splitlines()[:6])
                print('---')
                print(head)
        return 2

    print('All blocks match expected LC_ALL=C dictionary ordering.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
