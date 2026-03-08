"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common keybindings.json functions.
"""

from __future__ import annotations

import json
import re
from typing import List, Tuple

# Simple helpers and constants
NUMBER_SPLIT_RE = re.compile(r"(\d+)")
WHEN_TERM_SPLIT_RE = re.compile(r"\s*&&\s*|\s*\|\|\s*")

# caches
CACHE_NATURAL_KEY: dict = {}
CACHE_NATURAL_KEY_CS: dict = {}
CACHE_WHEN_SPECIFICITY: dict = {}


def _canonicalize_when(when_val: str) -> str:
    """Return a stable, operand-level canonical form of a when expression."""

    if not when_val:
        return ""
    parts = [p.strip() for p in WHEN_TERM_SPLIT_RE.split(when_val) if p and p.strip()]
    return ' && '.join(sorted(set(parts)))


def _key_tail_literal(key_value: str) -> str:
    """Return the last literal part of a key description (e.g. 'ctrl+k' -> 'k')."""

    cleaned = str(key_value).strip().lower()
    if not cleaned:
        return ""
    final = cleaned.split()[-1]
    bits = [bit.strip() for bit in final.split('+') if bit.strip()]
    if not bits:
        return ""
    return bits[-1]


def _normalize_key(k: str | None) -> str:
    """Normalize a key string by trimming whitespace and decoding escapes."""

    if k is None:
        return ""
    nk = str(k).strip()
    try:
        if "\\u" in nk or "\\x" in nk:
            nk = nk.encode('utf-8').decode('unicode_escape')
    except Exception:
        pass
    return nk


def _normalize_key_for_compare(key_value: str) -> str:
    """Return a lowercase, trimmed form of a key suitable for comparisons."""

    if not key_value:
        return ""
    return key_value.strip().lower()


def _parse_jsonc(text: str):
    """Parse JSONC text by removing comments and trailing commas then loading JSON."""

    t = re.sub(r"//.*?$", "", text, flags=re.M)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return json.loads(t)


def _split_when_contexts(expr: str | None) -> List[str]:
    """Split a when expression into individual && contexts and return them."""

    if not expr:
        return []

    normalized = str(expr).strip()
    if not normalized:
        return []

    normalized = re.sub(r"^\s*&&\s*", "", normalized)
    normalized = re.sub(r"\s*&&\s*$", "", normalized)
    if not normalized:
        return []

    return [part.strip() for part in re.split(r"\s*&&\s*", normalized) if part.strip()]


# AST node classes used by the token/parse functions


class WhenNode:
    def __init__(self, parens: bool = False):
        self.parens = parens

    def _to_str(self) -> str:
        raise NotImplementedError


class WhenAnd(WhenNode):
    def __init__(self, children, parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def _to_str(self) -> str:
        parts: list[str] = []
        for c in self.children:
            s = _render_when_node(c)
            if isinstance(c, WhenOr):
                s = f'({s})'
            parts.append(s)
        return ' && '.join(parts)


class WhenLeaf(WhenNode):
    def __init__(self, text: str, parens: bool = False):
        super().__init__(parens=parens)
        self.text = text

    def _to_str(self) -> str:
        return self.text


class WhenNot(WhenNode):
    def __init__(self, child: WhenNode, parens: bool = False):
        super().__init__(parens=parens)
        self.child = child

    def _to_str(self) -> str:
        child_str = self.child._to_str()
        if isinstance(self.child, (WhenAnd, WhenOr)) and not self.child.parens:
            child_str = f'({child_str})'
        return f'!{child_str}'


class WhenOr(WhenNode):
    def __init__(self, children, parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def _to_str(self) -> str:
        parts: list[str] = []
        for c in self.children:
            s = _render_when_node(c)
            if isinstance(c, WhenAnd):
                s = f'({s})'
            parts.append(s)
        return ' || '.join(parts)


def _render_when_node(node: WhenNode) -> str:
    """Render a WhenNode AST back to its string form while preserving parentheses."""

    inner = node._to_str()
    if node.parens:
        return f'({inner})'
    return inner


def _tokenize_when(expr: str):
    """Tokenize a when expression into operand and operator tokens for parsing."""

    tokens = []
    buf = ''
    i = 0
    n = len(expr)
    in_single = False
    in_double = False
    in_regex = False
    regex_escape = False
    prev_nonspace = ''

    def _flush_buf():
        nonlocal buf
        if buf.strip():
            tokens.append(('OPERAND', re.sub(r'\s+', ' ', buf).strip()))
        buf = ''

    while i < n:
        ch = expr[i]

        if in_single:
            buf += ch
            if ch == '\\':
                if i + 1 < n:
                    buf += expr[i + 1]
                    i += 1
            elif ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            buf += ch
            if ch == '\\':
                if i + 1 < n:
                    buf += expr[i + 1]
                    i += 1
            elif ch == '"':
                in_double = False
            i += 1
            continue

        if in_regex:
            buf += ch
            if regex_escape:
                regex_escape = False
            elif ch == '\\':
                regex_escape = True
            elif ch == '/':
                in_regex = False
            i += 1
            continue

        if ch.isspace():
            buf += ch
            i += 1
            continue

        if ch == "'":
            in_single = True
            buf += ch
            i += 1
            continue

        if ch == '"':
            in_double = True
            buf += ch
            i += 1
            continue

        if ch == '/' and prev_nonspace == '~':
            in_regex = True
            buf += ch
            i += 1
            continue

        if expr.startswith('&&', i) or expr.startswith('||', i):
            _flush_buf()
            tokens.append(('OP', expr[i:i + 2]))
            i += 2
            prev_nonspace = ''
            continue

        if ch in '()':
            _flush_buf()
            tokens.append(('OP', ch))
            i += 1
            prev_nonspace = ch
            continue

        if ch == '!':
            nxt = expr[i + 1] if i + 1 < n else ''
            if nxt == '=':
                buf += ch
                i += 1
                prev_nonspace = ch
                continue
            if not buf.strip():
                _flush_buf()
                tokens.append(('OP', '!'))
                i += 1
                prev_nonspace = '!'
                continue

        buf += ch
        if not ch.isspace():
            prev_nonspace = ch
        i += 1

    _flush_buf()

    return tokens


def _parse_when(expr: str) -> WhenNode:
    """Parse a when expression into a WhenNode AST representing its logical structure."""

    tokens = _tokenize_when(expr)
    idx = 0

    def _consume():
        nonlocal idx
        t = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return t

    def _parse_and():
        node = _parse_unary()
        children = [node]
        while True:
            t = _peek()
            if t and t[0] == 'OP' and t[1] == '&&':
                _consume()
                children.append(_parse_unary())
            else:
                break
        if len(children) == 1:
            return children[0]
        return WhenAnd(children)

    def _parse_or():
        node = _parse_and()
        children = [node]

        while True:
            t = _peek()
            if t and t[0] == 'OP' and t[1] == '||':
                _consume()
                children.append(_parse_and())
            else:
                break
        if len(children) == 1:
            return children[0]
        return WhenOr(children)

    def _parse_primary():
        t = _peek()
        if not t:
            return WhenLeaf('')
        if t[0] == 'OP' and t[1] == '(':
            _consume()
            node = _parse_or()
            next_token = _peek()
            if next_token and next_token[0] == 'OP' and next_token[1] == ')':
                _consume()
                node.parens = True
            return node
        if t[0] == 'OPERAND':
            _consume()
            return WhenLeaf(t[1])
        return WhenLeaf('')

    def _parse_unary():
        t = _peek()
        if t and t[0] == 'OP' and t[1] == '!':
            _consume()
            return WhenNot(_parse_unary())
        return _parse_primary()

    def _peek():
        return tokens[idx] if idx < len(tokens) else None

    return _parse_or()


def _when_specificity(when_val: str) -> Tuple[int]:
    """Return a heuristic specificity tuple for a when clause (fewer terms is broader)."""

    key = '' if when_val is None else str(when_val)
    cached = CACHE_WHEN_SPECIFICITY.get(key)
    if cached is not None:
        return cached
    if not key:
        res = (0,)
    else:
        term_count = len(WHEN_TERM_SPLIT_RE.split(key.strip()))
        res = (term_count,)
    try:
        CACHE_WHEN_SPECIFICITY[key] = res
    except Exception:
        pass
    return res


def _natural_key(s):
    """Return a locale-independent natural-sort key (a list of ints and strings) for sorting."""

    key = str(s)
    cached = CACHE_NATURAL_KEY.get(key)
    if cached is not None:
        return cached
    parts = NUMBER_SPLIT_RE.split(key)
    out = [int(text) if text.isdigit() else text.lower() for text in parts]
    try:
        CACHE_NATURAL_KEY[key] = out
    except Exception:
        pass
    return out


def _natural_key_case_sensitive(s):
    """Return a case-sensitive natural-sort key for the string."""

    key = str(s)
    cached = CACHE_NATURAL_KEY_CS.get(key)
    if cached is not None:
        return cached
    parts = NUMBER_SPLIT_RE.split(key)
    out = [int(text) if text.isdigit() else text for text in parts]
    try:
        CACHE_NATURAL_KEY_CS[key] = out
    except Exception:
        pass
    return out
