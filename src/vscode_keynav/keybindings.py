"""Shared keybindings helpers (JSONC parsing and when/key utils).

This is a minimal, importable stub added to the package so bin scripts
can import `vscode_keynav.keybindings` while we iterate on implementations.
"""

def parse_jsonc(text: str):
    """Parse JSON with comments — minimal placeholder."""
    import json, re

    text = re.sub(r"//.*?$", "", text, flags=re.M)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def canonicalize_when(when_val: str) -> str:
    """Return a stable canonical form for a when expression (placeholder)."""
    if not when_val:
        return ""
    return ' && '.join(sorted({p.strip() for p in when_val.split('&&')}))


def normalize_key_for_compare(key_value: str) -> str:
    if not key_value:
        return ""
    return key_value.strip().lower()

def key_tail_literal(key_value: str) -> str:
    """Return the last literal in a key description, e.g. `ctrl+k` -> `k`."""
    cleaned = str(key_value).strip().lower()
    if not cleaned:
        return ""
    final = cleaned.split()[-1]
    bits = [bit.strip() for bit in final.split('+') if bit.strip()]
    if not bits:
        return ""
    return bits[-1]
