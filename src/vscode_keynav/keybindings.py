"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common keybindings.json functions.
"""


def parse_jsonc(text: str):
    """Parse JSON with comments."""

    import json
    import re

    text = re.sub(r"//.*?$", "", text, flags=re.M)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def canonicalize_when(when_val: str) -> str:
    """Return a stable canonical form for a when expression."""

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


def normalize_key(k: str | None) -> str:
    """Return a normalized key literal for reliable membership tests."""

    if k is None:
        return ""
    nk = str(k).strip()
    try:
        if "\\u" in nk or "\\x" in nk:
            nk = nk.encode('utf-8').decode('unicode_escape')
    except Exception:
        pass
    return nk


def split_when_contexts(expr: str | None) -> list[str]:
    if not expr:
        return []

    normalized = expr.strip()
    if not normalized:
        return []

    import re

    normalized = re.sub(r"^\s*&&\s*", "", normalized)
    normalized = re.sub(r"\s*&&\s*$", "", normalized)
    if not normalized:
        return []

    return [part.strip() for part in re.split(r"\s*&&\s*", normalized) if part.strip()]
