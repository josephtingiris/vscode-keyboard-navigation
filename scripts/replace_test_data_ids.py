#!/usr/bin/env python3
"""
Prefix 4-hex ids with a leading 0 in files under tests/data.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data_dir = root / 'tests' / 'data'
pattern = re.compile(r"(?<=\s)([0-9a-f]{4})(?=[\s\"',\]])")

for p in data_dir.rglob('*'):
    if not p.is_file():
        continue
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        # skip binary or unreadable files
        continue
    new_text, n = pattern.subn(lambda m: '0' + m.group(1), text)
    if n > 0:
        p.write_text(new_text, encoding='utf-8')
        print(f"Updated {p} ({n} replacements)")
