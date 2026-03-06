import re
import json
import subprocess
from pathlib import Path


def strip_json_comments(s: str) -> str:
    s = re.sub(r'//.*?\n', '\n', s)
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    return s


def normalize_key_for_compare(key_value: str) -> str:
    if not key_value:
        return ""
    raw = str(key_value).strip()
    if not raw:
        return ""

    CANONICAL_MOD_ORDER = ['ctrl', 'shift', 'alt', 'meta']

    chords = [p for p in raw.split() if p.strip()]
    out_chords = []
    for chord in chords:
        # Preserve trailing '+' (e.g., 'alt++' -> base '+')
        if '+' in chord:
            mods_part, base_part = chord.rsplit('+', 1)
            if base_part == '':
                base = '+'
            else:
                base = base_part.strip().lower()
            mods = [m.strip().lower() for m in mods_part.split('+') if m.strip()]
        else:
            mods = []
            base = chord.strip().lower()

        ordered = [m for m in CANONICAL_MOD_ORDER if m in mods]
        others = sorted([m for m in mods if m not in ordered])
        if ordered or others:
            out_chords.append('+'.join(ordered + others + [base]))
        else:
            out_chords.append(base)
    return ' '.join(out_chords)


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
                objs.append(text[start:i+1])
                start = None
        i += 1
    return objs


def parse_obj_text(obj_text: str):
    clean = strip_json_comments(obj_text)
    # remove trailing commas before closing braces/brackets
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    try:
        return json.loads(clean)
    except Exception:
        return None


def test_when_blocks_contiguous_and_modifier_first():
    repo_root = Path(__file__).resolve().parents[1]
    data_file = repo_root / 'tests' / 'data' / 'keybindings-test-data.jsonc'
    sorter = repo_root / 'bin' / 'keybindings-sort.py'

    inp = data_file.read_text(encoding='utf-8')
    proc = subprocess.run(['python3', str(sorter), '-w', 'focal-invariant'], input=inp, text=True, capture_output=True)
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
        whens.append(parsed.get('when', '') or '')

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

    # in-block modifier-first: vekeybindings_sort_test_performance.graphs.pyy each contiguous block is ordered by the
    # same key the sorter uses (mods_norm, token_seq, token_count).
    CANONICAL_MOD_ORDER = ['ctrl', 'shift', 'alt', 'meta']

    def _normalize_mods(mods: str) -> str:
        parts = [p for p in mods.split('+') if p]
        ordered = [p for p in CANONICAL_MOD_ORDER if p in parts]
        others = sorted([p for p in parts if p not in ordered])
        out = ordered + others
        return '+'.join(out) + ('+' if out else '')

    def _key_category_and_order(ch: str):
        if not ch:
            return (4, 0)
        c0 = ch[0]
        oc = ord(c0)
        if c0.isalpha():
            return (3, oc)
        if c0.isdigit():
            return (2, oc)
        if oc >= 128:
            try:
                b = c0.encode('cp1252')
                if b:
                    return (1, b[0])
            except Exception:
                pass
            return (1, oc)
        return (0, oc)

    def _key_sort_tuple_from_key(key_raw: str):
        if key_raw is None:
            key_raw = ''
        key_raw = str(key_raw)
        if '+' in key_raw:
            mods_part, base_part = key_raw.rsplit('+', 1)
            if base_part == '':
                base_part = '+'
            mods_norm = _normalize_mods(mods_part)
        else:
            mods_norm = ''
            base_part = key_raw

        if base_part and all(ch == '+' for ch in base_part):
            tokens = ['+']
        else:
            base_norm = normalize_key_for_compare(base_part)
            tokens = [t for t in base_norm.split() if t != '']

        token_seq = []
        for t in tokens:
            cat, order_key = _key_category_and_order(t)
            token_seq.append((cat, order_key, t.encode('utf-8')))

        return (mods_norm.encode('utf-8'), token_seq, len(tokens))

    i = 0
    violations = []
    n = len(whens)
    while i < n:
        j = i + 1
        while j < n and whens[j] == whens[i]:
            j += 1
        block_objs = objs[i:j]
        # compute keys and comparator tuples
        keys_block = [parse_obj_text(o).get('key', '') or '' for o in block_objs]
        tuples = [ _key_sort_tuple_from_key(k) for k in keys_block ]
        # check stable sorted order
        sorted_indices = sorted(range(len(tuples)), key=lambda idx: tuples[idx])
        if sorted_indices != list(range(len(tuples))):
            violations.append((whens[i], i, j-1, keys_block[:8], [t.decode('utf-8', errors='ignore') if isinstance(t, bytes) else t for t in tuples[:8]]))
        i = j
    assert not violations, f"Modifier-first ordering violated in {len(violations)} blocks; sample: {violations[:5]}"
