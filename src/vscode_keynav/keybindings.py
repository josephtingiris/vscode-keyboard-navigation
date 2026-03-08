"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common keybindings.json functions.
"""

from __future__ import annotations

import hashlib
import json
import re

from typing import List, Tuple

from functools import lru_cache

from vscode_keynav import debug as _debug
from vscode_keynav import io as _io

#
# globals & constants
#

# CLI-level per-run caches to avoid repeated parsing/regex work across hot loops
_CLI_RUN_OBJ_INFO_CACHE: dict = {}
_CLI_RUN_OBJ_MATCH_CACHE: dict = {}

# token groups and maps used by canonicalization heuristics

FOCUS_TOKENS = [
    'auxiliaryBarFocus',
    'terminalFocus',
    'sideBarFocus',
    'statusBarFocused',
    'panelFocus',
    'editorFocus',
    'agentSessionsViewerFocused',
    'editorTextFocus',
    'inputFocus',
    'inQuickInput',
    'listFocus',
    'notificationFocus',
    'textInputFocus',
]

POSITIONAL_TOKENS = [
    'config.workbench.activityBar.location',
    'config.workbench.sideBar.location',
    'panel.location',
    'panelPosition',
    'activeAuxiliary',
    'activeEditor',
    'activePanel',
    'activeViewlet',
    'focusedView',
    'breadcrumbsActive',
    'breadcrumbsPossible',
    'config.keyboardNavigation.juke.enabled',
    'config.keyboardNavigation.highlights.enabled',
    'config.keyboardNavigation.terminal.enabled',
]

VISIBILITY_TOKENS = [
    'chatIsEnabled',
    'auxiliaryBarVisible',
    'editorVisible',
    'panelVisible',
    'agentSessionsViewerVisible',
    'notificationCenterVisible',
    'notificationToastsVisible',
    'outline.visible',
    'searchViewletVisible',
    'sideBarVisible',
    'terminalVisible',
    'timeline.visible',
    'view.<viewId>.visible',
    'webviewFindWidgetVisible',
]

# precomputed maps

FOCUS_TOKENS_MAP = {t: i for i, t in enumerate(FOCUS_TOKENS)}
POSITIONAL_TOKENS_MAP = {t: i for i, t in enumerate(POSITIONAL_TOKENS)}
VISIBILITY_TOKENS_MAP = {t: i for i, t in enumerate(VISIBILITY_TOKENS)}

# re-usable caches

CACHE_CANONICALIZE_WHEN: dict = {}
CACHE_DECODED_JSON_LITERAL: dict = {}
CACHE_JSON_OBJECT: dict = {}
CACHE_NATURAL_KEY: dict = {}
CACHE_NATURAL_KEY_CS: dict = {}
CACHE_SORTABLE_WHEN: dict = {}
CACHE_WHEN_SPECIFICITY: dict = {}

OPERAND_MATCH_CACHE: dict = {}

RUN_CACHE_CONTEXT = None
RUN_CANONICAL_CACHE: dict = {}
RUN_MATCH_CACHE: dict = {}
RUN_OBJ_INFO_CACHE: dict = {}
RUN_SORTABLE_CACHE: dict = {}


#
# classes
#


# AST when node

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


#
# functions
#


def _canonicalize_when(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
    """Return canonicalized when entry from an LRU cache."""

    when_prefixes_tpl = None if when_prefixes is None else tuple(when_prefixes)

    if when_regexes is None:
        when_regexes_tpl = None
    else:
        def _rx_to_str(r):
            try:
                return r.pattern if hasattr(r, 'pattern') else str(r)
            except Exception:
                return str(r)

        when_regexes_tpl = tuple(_rx_to_str(r) for r in when_regexes)

    return _canonicalize_when_cached(when_val, mode, negation_mode, when_prefixes_tpl, when_regexes_tpl)


@lru_cache(maxsize=65536)
def _canonicalize_when_cached(when_val: str, mode: str, negation_mode: str, when_prefixes_tpl: tuple | None, when_regexes_tpl: tuple | None) -> str:
    """Internal canonicalize implementation (LRU caching)."""

    when_prefixes = None if when_prefixes_tpl is None else list(when_prefixes_tpl)
    when_regexes = None if when_regexes_tpl is None else list(when_regexes_tpl)

    return _canonicalize_when_not_cached(when_val, mode=mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)


def _canonicalize_when_not_cached(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
    """Internal canonicalize implementation (no LRU caching)."""

    def _clear_parens(node: WhenNode):
        node.parens = False
        if isinstance(node, WhenLeaf):
            return
        if isinstance(node, WhenNot):
            _clear_parens(node.child)
            return
        if isinstance(node, WhenAnd) or isinstance(node, WhenOr):
            for c in node.children:
                _clear_parens(c)

    def _group_rank(text: str) -> int:
        left = _left_identifier(text)

        if when_prefixes:
            for pref in when_prefixes:
                if not pref:
                    continue
                if left == pref:
                    return 0

        if when_regexes:
            for pat in when_regexes:
                try:
                    if pat.search(left):
                        return 0
                except Exception:
                    try:
                        if re.search(pat, left):
                            return 0
                    except Exception:
                        continue

        if mode == 'none':
            return 1

        if mode == 'focal-invariant':
            if _is_focus(left):
                return 1
            if any(left.startswith(p) for p in POSITIONAL_TOKENS):
                return 2
            if _is_visibility(left):
                return 3
            if left.startswith('config.'):
                return 4
            return 5

        if left.startswith('config.'):
            return 1
        if any(left.startswith(p) for p in POSITIONAL_TOKENS):
            return 2
        if _is_focus(left):
            return 3
        if _is_visibility(left):
            return 4
        return 5

    def _is_focus(left: str) -> bool:
        return any(_matches_entry(left, entry) for entry in FOCUS_TOKENS)

    def _is_visibility(left: str) -> bool:
        return any(_matches_entry(left, entry) for entry in VISIBILITY_TOKENS)

    def _left_identifier(text: str) -> str:
        t = text.strip()
        while t.startswith('(') and t.endswith(')'):
            t = t[1:-1].strip()
        if t.startswith('!'):
            t = t[1:].lstrip()
        if not t:
            return t
        return t.split()[0]

    def _matches_entry(left: str, entry: str) -> bool:
        if entry.endswith('.'):
            return left.startswith(entry)
        if '<viewId>' in entry:
            prefix, suffix = entry.split('<viewId>', 1)
            return left.startswith(prefix) and left.endswith(suffix)
        return left == entry

    def _sort_and_nodes(node: WhenNode):
        if isinstance(node, WhenAnd):
            for child in node.children:
                _sort_and_nodes(child)
            indexed = list(enumerate(node.children))

            prioritized = []
            picked = set()

            def _left_id_of(item_node):
                tok = _render_when_node(item_node)
                lid = _left_identifier(tok)
                return lid

            if when_prefixes:
                for pref in when_prefixes:
                    matches = []
                    for idx, child in indexed:
                        if idx in picked:
                            continue
                        lid = _left_id_of(child)
                        if lid == pref:
                            matches.append((idx, child))

                    if matches:
                        matches.sort(key=lambda t: _natural_key_case_sensitive(_render_when_node(t[1])))
                        for m in matches:
                            prioritized.append(m[1])
                            picked.add(m[0])

            if when_regexes:
                for pat in when_regexes:
                    matches = []
                    for idx, child in indexed:
                        if idx in picked:
                            continue
                        lid = _left_id_of(child)
                        try:
                            ok = pat.search(lid)
                        except Exception:
                            try:
                                ok = re.search(pat, lid)
                            except Exception:
                                ok = False
                        if ok:
                            matches.append((idx, child))

                    if matches:
                        matches.sort(key=lambda t: _natural_key_case_sensitive(_render_when_node(t[1])))
                        for m in matches:
                            prioritized.append(m[1])
                            picked.add(m[0])

            if negation_mode == 'beta':
                nm = 'positive-natural'
            else:
                nm = negation_mode

            if negation_mode == 'alpha':
                indexed.sort(key=_sort_key)
                sorted_children = [it[1] for it in indexed]
            else:
                def render_base_and_flag(child):
                    tok = _render_when_node(child)
                    base = tok.strip()
                    while base.startswith('(') and base.endswith(')'):
                        base = base[1:-1].strip()
                    is_neg = base.startswith('!')
                    if is_neg:
                        base = base[1:].lstrip()
                    return base, is_neg, tok

                items_with_keys = []
                for idx, child in indexed:
                    base, is_neg, tok = render_base_and_flag(child)
                    base_key = _natural_key(base)
                    grp = _group_rank(tok)
                    lid = _left_id_of(child)
                    f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))

                    if nm == 'natural':
                        items_with_keys.append((idx, child, (grp, f_rank, base_key, idx, tok)))
                        continue

                    if nm == 'positive-natural':
                        neg_sort = 0 if not is_neg else 1
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key, idx, tok)))
                        continue

                    if nm == 'negative-natural':
                        neg_sort = 0 if is_neg else 1
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key, idx, tok)))
                        continue

                    if nm == 'positive':
                        neg_sort = 0 if not is_neg else 1
                        f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))
                        base_key_cs = _natural_key_case_sensitive(base)
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key_cs, idx, tok)))
                        continue

                    if nm == 'negative':
                        neg_sort = 0 if is_neg else 1
                        f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))
                        base_key_cs = _natural_key_case_sensitive(base)
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key_cs, idx, tok)))
                        continue

                    neg_sort = 0
                    items_with_keys.append((idx, child, (grp, neg_sort, base_key, idx, tok)))

                items_with_keys.sort(key=lambda t: t[2])
                sorted_children = [it[1] for it in items_with_keys]

            if prioritized:
                prioritized_tokens = [_render_when_node(p) for p in prioritized]
                remaining = [c for c in sorted_children if _render_when_node(c) not in set(prioritized_tokens)]
                merged = prioritized + remaining
            else:
                merged = sorted_children

            unique: list[WhenNode] = []
            seen = set()
            for c in merged:
                tok = _render_when_node(c)
                if tok in seen:
                    continue
                seen.add(tok)
                unique.append(c)
            node.children = unique

        elif isinstance(node, WhenOr):
            for child in node.children:
                _sort_and_nodes(child)

            items: list[WhenNode] = []
            for c in node.children:
                if isinstance(c, WhenOr):
                    items.extend(c.children)
                else:
                    items.append(c)

            indexed = list(enumerate(items))
            indexed.sort(key=lambda it: (_natural_key_case_sensitive(_render_when_node(it[1])), it[0]))
            sorted_children = [it[1] for it in indexed]

            unique: list[WhenNode] = []
            seen = set()
            for c in sorted_children:
                tok = _render_when_node(c)
                if tok in seen:
                    continue
                seen.add(tok)
                unique.append(c)
            node.children = unique
        elif isinstance(node, WhenNot):
            _sort_and_nodes(node.child)

    def _sort_key(idx_and_node):
        idx, node = idx_and_node
        token = _render_when_node(node)
        order_token = token[1:] if token.startswith('!') else token
        left_id = _left_identifier(token)
        sub_rank = FOCUS_TOKENS_MAP.get(left_id, POSITIONAL_TOKENS_MAP.get(left_id, VISIBILITY_TOKENS_MAP.get(left_id, 9999)))
        if negation_mode == 'alpha':
            return (_group_rank(token), sub_rank, _natural_key_case_sensitive(order_token), idx)
        return (_group_rank(token), _natural_key_case_sensitive(order_token), idx)

    if not when_val:
        return ''

    cache_key = (
        when_val,
        mode,
        negation_mode,
        None if when_prefixes is None else tuple(when_prefixes),
        None if when_regexes is None else tuple(when_regexes),
    )

    cached = CACHE_CANONICALIZE_WHEN.get(cache_key)
    if cached is not None:
        return cached

    try:
        run_key = (mode, negation_mode, None if when_prefixes is None else tuple(when_prefixes), None if when_regexes is None else tuple(when_regexes))
        if RUN_CACHE_CONTEXT == run_key:
            cached_run = RUN_CANONICAL_CACHE.get(when_val)
            if cached_run is not None:
                return cached_run
    except Exception:
        pass

    focus_tokens = FOCUS_TOKENS
    positional_tokens = POSITIONAL_TOKENS
    visibility_tokens = VISIBILITY_TOKENS

    ast = _parse_when(when_val)

    _sort_and_nodes(ast)

    _clear_parens(ast)

    result = _render_when_node(ast)

    try:
        CACHE_CANONICALIZE_WHEN[cache_key] = result
    except Exception:
        pass

    try:
        if RUN_CACHE_CONTEXT == (mode, negation_mode, None if when_prefixes is None else tuple(when_prefixes), None if when_regexes is None else tuple(when_regexes)):
            RUN_CANONICAL_CACHE[when_val] = result
    except Exception:
        pass

    return result


def _clear_lru_when_cache() -> None:
    """Clear the LRU cache used by the canonicalizer."""

    try:
        _canonicalize_when_cached.cache_clear()
    except Exception:
        pass


def _contains_focus_token_in_object(obj_text: str) -> bool:
    """Return True if the object's when clause contains any configured focus token."""

    return bool(_get_run_obj_match_info(obj_text).get('has_focus', False))


def _decode_json_string_literal(raw: str) -> str:
    """Decode the inner text of a JSON string literal into a Python string."""

    if raw is None:
        return ''

    cached = CACHE_DECODED_JSON_LITERAL.get(raw)
    if cached is not None:
        return cached

    try:
        val = json.loads('"' + raw + '"')
    except Exception:
        try:
            val = bytes(raw, 'utf-8').decode('unicode_escape')
        except Exception:
            val = raw

    try:
        CACHE_DECODED_JSON_LITERAL[raw] = val
    except Exception:
        pass
    return val


def _embed_duplicate_comment_in_object(obj_text: str, duplicate_comment: str) -> str:
    """Insert a 'duplicate' line comment immediately inside an object's opening brace."""

    if not duplicate_comment:
        return obj_text

    line_comment = duplicate_comment.strip()
    if not line_comment:
        return obj_text
    if not line_comment.startswith('//'):
        line_comment = f'// {line_comment}'

    lines = obj_text.splitlines(keepends=True)
    if not lines:
        return obj_text

    open_idx = -1
    for idx, line in enumerate(lines):
        if '{' in line:
            open_idx = idx
            break

    if open_idx == -1:
        return obj_text

    indent = ''
    for idx in range(open_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if stripped.startswith('}'):
            break
        indent = lines[idx][:len(lines[idx]) - len(lines[idx].lstrip(' \t'))]
        break

    if not indent:
        opener = lines[open_idx]
        base_indent = opener[:len(opener) - len(opener.lstrip(' \t'))]
        indent = base_indent + '    '

    lines.insert(open_idx + 1, f'{indent}{line_comment}\n')
    return ''.join(lines)


def _extract_key_when_from_object(obj_text: str) -> Tuple[str, str]:
    """Return a tuple of literal `(key, when)` values extracted from an object text."""

    return (_extract_literal_key_from_object(obj_text), _extract_literal_when_from_object(obj_text))


def _extract_literal_key_from_object(obj_text: str) -> str:
    """Return the decoded literal `key` value from an object text or empty string."""

    match = _io._KEY_EXTRACT_RE.search(obj_text)
    if not match:
        return ''
    return _decode_json_string_literal(match.group(1))


def _extract_literal_when_from_object(obj_text: str) -> str:
    """Return the decoded literal `when` value from an object text or empty string."""

    match = _io._WHEN_EXTRACT_RE.search(obj_text)

    if not match:
        return ''

    return _decode_json_string_literal(match.group(1))


def _extract_modifiers_from_object(obj_text: str) -> tuple[tuple[str, ...], str]:
    """Return the modifier tuple and literal key token from the object key string."""

    key_raw = _extract_literal_key_from_object(obj_text) or ''
    norm = _normalize_key_for_compare(key_raw)
    first = norm.split()[0] if norm else ''
    parts = [p for p in first.split('+') if p]
    mods = tuple(parts[:-1]) if len(parts) > 1 else tuple()
    lit = parts[-1] if parts else ''
    lit_key = _normalize_key_for_compare(lit)

    return (mods, lit_key)


def _extract_preamble_postamble(text):
    """Return sliced preamble, array_text, and postamble."""

    # optimized single-pass scanner with local variables bound for speed
    n = len(text)
    i = 0
    start = -1
    in_line = False
    in_block = False
    in_str = False
    esc = False
    str_char = ''

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ''

        if in_line:
            if ch == '\n':
                in_line = False
            i += 1
            continue
        if in_block:
            if ch == '*' and nxt == '/':
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == str_char:
                in_str = False
            i += 1
            continue

        if ch == '/' and nxt == '/':
            in_line = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_str = True
            str_char = ch
            i += 1
            continue
        if ch == '[':
            start = i
            break
        i += 1

    if start == -1:
        return '', '', text

    # scan for matching closing bracket
    depth = 1
    i = start + 1
    in_line = False
    in_block = False
    in_str = False
    esc = False
    str_char = ''
    end = -1

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ''

        if in_line:
            if ch == '\n':
                in_line = False
            i += 1
            continue
        if in_block:
            if ch == '*' and nxt == '/':
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == str_char:
                in_str = False
            i += 1
            continue

        if ch == '/' and nxt == '/':
            in_line = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_str = True
            str_char = ch
            i += 1
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1

    if end == -1:
        return '', '', text

    return text[:start], text[start + 1:end], text[end + 1:]


def _extract_sort_keys_from_object(obj_text: str, primary: str = 'key', secondary: str | None = None, grouping: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> Tuple:
    """Return a computed stable sort key tuple for the object text."""

    info = _get_run_obj_info(
        obj_text,
        grouping_mode=grouping,
        negation_mode=negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    key_val = info.get('key', '')
    when_val = info.get('when', '')
    canonical_when = info.get('canonical', '')
    sortable_when = info.get('sortable', '')
    parsed = info.get('parsed')

    if not parsed:
        # return a consistent fallback sort key (rank high so these sort last)
        return (9999, [], (0,), [])

    # main token-building logic
    try:
        # derive the first top-level when token for grouping when primary sorting
        first_when_token = ''
        if canonical_when:
            parts = _io._WHEN_TERM_SPLIT_RE.split(canonical_when.strip())
            if parts:
                first_when_token = parts[0].strip()
                # remove surrounding parentheses and leading negation for grouping
                while first_when_token.startswith('(') and first_when_token.endswith(')'):
                    first_when_token = first_when_token[1:-1].strip()
                if first_when_token.startswith('!'):
                    first_when_token = first_when_token[1:].lstrip()

        # special-case: when primary is key and secondary is when, ensure strict key-first ordering by returning a simple tuple: (rank, key, when_specificity, when_sortable)
        if primary == 'key' and secondary == 'when':
            norm = _normalize_key_for_compare(key_val)
            key_token = _natural_key(norm)
            spec = _when_specificity(when_val)
            when_token = _natural_key_case_sensitive(sortable_when)
            return (0, key_token, spec, when_token)

        tokens = []

        def append_when():
            if primary == 'when':
                first_key = _natural_key_case_sensitive(first_when_token)

                # compute an optional priority rank based on given when_prefixes
                match_rank = 9999
                spec_key = _when_specificity(when_val)
                left_id = first_when_token
                if left_id.startswith('(') and left_id.endswith(')'):
                    left_id = left_id[1:-1].strip()
                if left_id.startswith('!'):
                    left_id = left_id[1:].lstrip()
                if when_prefixes:
                    for i, pref in enumerate(when_prefixes):
                        if not pref:
                            continue
                        # support literal prefix ending in '.' to match startswith
                        if pref.endswith('.'):
                            if left_id.startswith(pref):
                                match_rank = i
                                break
                        elif '<viewId>' in pref:
                            prefix, suffix = pref.split('<viewId>', 1)
                            if left_id.startswith(prefix) and left_id.endswith(suffix):
                                match_rank = i
                                break
                        else:
                            if left_id == pref:
                                match_rank = i
                                break
                if when_regexes and match_rank == 9999:
                    for i, pat in enumerate(when_regexes):
                        try:
                            ok = pat.search(left_id)
                        except Exception:
                            try:
                                ok = re.search(pat, left_id)
                            except Exception:
                                ok = False
                        if ok:
                            match_rank = (len(when_prefixes)
                                          if when_prefixes else 0) + i
                            break
                    spec_key = _when_specificity(when_val)

                tokens.append(match_rank)
                if negation_mode == 'alpha':
                    grouping = _natural_key_case_sensitive(sortable_when)
                elif negation_mode == 'natural':
                    base = sortable_when.lstrip('!')
                    grouping = _natural_key(base)
                elif negation_mode in ('positive', 'beta', 'positive-natural'):
                    # positive-natural: prefer non-negated then natural base ordering
                    is_neg = 1 if sortable_when.startswith('!') else 0
                    base = sortable_when.lstrip('!')

                    # prioritize token-list ordering (FOCUS -> POSITIONAL -> VISIBILITY)
                    if negation_mode == 'positive':
                        # compute sub-rank based on the first_when_token
                        lid = first_when_token
                        if lid.startswith('(') and lid.endswith(')'):
                            lid = lid[1:-1].strip()
                        if lid.startswith('!'):
                            lid = lid[1:].lstrip()
                        f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))
                        grouping = (is_neg, f_rank, _natural_key_case_sensitive(base))
                    else:
                        grouping = (is_neg, _natural_key(base))
                elif negation_mode in ('negative', 'negative-natural'):
                    is_neg = 0 if sortable_when.startswith('!') else 1
                    base = sortable_when.lstrip('!')
                    if negation_mode == 'negative':
                        lid = first_when_token
                        if lid.startswith('(') and lid.endswith(')'):
                            lid = lid[1:-1].strip()
                        if lid.startswith('!'):
                            lid = lid[1:].lstrip()
                        f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))
                        grouping = (is_neg, f_rank, _natural_key_case_sensitive(base))
                    else:
                        grouping = (is_neg, _natural_key(base))
                else:
                    grouping = _natural_key_case_sensitive(sortable_when)

                # this makes matched groups easier to inspect
                if match_rank != 9999:
                    # prefer normalized key ordering for stability: modifiers normalized
                    norm_key = _normalize_key_for_compare(key_val)
                    tokens.append(_natural_key(norm_key))
                    tokens.append(spec_key)
                    tokens.append(grouping)
                else:
                    # default behavior: include first_when token so grouping remains primary, then specificity and grouping ordering
                    tokens.append(first_key)
                    tokens.append(spec_key)
                    tokens.append(grouping)
                return

            tokens.append(_when_specificity(when_val))
            tokens.append(_natural_key_case_sensitive(sortable_when))

        def append_key():
            # use normalized key comparison (consistent modifier ordering)
            norm = _normalize_key_for_compare(key_val)
            tokens.append(_natural_key(norm))

        # primary
        if primary == 'when':
            append_when()
        else:
            append_key()

        # secondary (if provided and different)
        if secondary and secondary != primary:
            if secondary == 'when':
                append_when()
            else:
                append_key()

        # append any remaining fields not yet included
        if 'when' not in (primary, secondary):
            append_when()
        if 'key' not in (primary, secondary):
            append_key()

        if tokens:
            if not isinstance(tokens[0], int):
                # prefer a low rank when primary is 'key'
                if primary == 'key':
                    tokens.insert(0, 0)
                else:
                    tokens.insert(0, 9999)

        return tuple(tokens)
    except Exception:
        # return a key with the same structural types as a normal sort key: (int rank, list key, tuple specificity, list grouping)
        return (9999, [], (0,), [])


def _first_when_group_rank(
    obj_text: str,
    mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> int:
    """Assign a numeric grouping rank to the first operand of an object's when clause."""

    info = _get_run_obj_info(
        obj_text,
        grouping_mode=mode,
        negation_mode=negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )
    canonical = info.get('canonical', '')

    if not canonical:
        return 5

    parts = _io._WHEN_TERM_SPLIT_RE.split(canonical.strip())
    if not parts:
        return 5

    # ensure related contexts are grouped together
    if when_prefixes or when_regexes:
        match_info = _get_run_obj_match_info(obj_text)
        left_ids = match_info.get('left_ids', ())
        prefix_idxs = match_info.get('prefix_idxs', ())
        regex_idxs = match_info.get('regex_idxs', ())
        if prefix_idxs:
            left_id = next((lid for lid in left_ids if any(lid.startswith(prefix) for prefix in when_prefixes or [])), '')
            if left_id:
                _debug._echo(1, 'group', canonical, f"matched when_prefix in operand: {left_id}")
            return 6
        if regex_idxs:
            left_id = ''
            pattern = ''
            for candidate in left_ids:
                for rx in when_regexes or []:
                    try:
                        ok = rx.search(candidate) if hasattr(rx, 'search') else str(rx) in candidate
                    except Exception:
                        ok = False
                    if ok:
                        left_id = candidate
                        pattern = rx.pattern if hasattr(rx, 'pattern') else rx
                        break
                if left_id:
                    break
            if left_id:
                _debug._echo(1, 'group', canonical, f"matched when_regex in operand: {left_id} (pattern={pattern})")
            return 6

    first = parts[0].strip()
    while first.startswith('(') and first.endswith(')'):
        first = first[1:-1].strip()

    left = first[1:].lstrip() if first.startswith('!') else first
    if not left:
        return 5

    left_id = left.split()[0]

    if mode == 'focal-invariant':
        if any(_matches_when_entry(left_id, entry) for entry in FOCUS_TOKENS):
            return 1  # Focus tokens have the highest priority
        if any(left_id.startswith(prefix) for prefix in POSITIONAL_TOKENS):
            return 2  # Positional tokens are next in priority
        if any(_matches_when_entry(left_id, entry) for entry in VISIBILITY_TOKENS):
            return 3  # Visibility tokens follow
        if left_id.startswith('config.'):
            return 4  # Config tokens are lower priority
        return 5

    if left_id.startswith('config.'):
        return 1
    if any(_matches_when_entry(left_id, entry) for entry in FOCUS_TOKENS):
        return 2
    if any(left_id.startswith(prefix) for prefix in POSITIONAL_TOKENS):
        return 3
    if any(_matches_when_entry(left_id, entry) for entry in VISIBILITY_TOKENS):
        return 4
    return 5


def _get_run_obj_duplicate_info(obj_text: str) -> tuple[str, str, str]:
    """Return per-run cached duplicate-detection fingerprints for an object text."""

    info = _get_run_obj_info(obj_text)

    full_hash = info.get('full_hash')
    json_hash = info.get('json_hash')
    json_canonical = info.get('json_canonical')
    if full_hash and json_hash and json_canonical is not None:
        return (full_hash, json_hash, json_canonical)

    parsed = info.get('parsed')
    if parsed is not None:
        try:
            json_canonical = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            json_canonical = ''
    else:
        json_only = _strip_trailing_commas(_strip_json_comments(obj_text)).strip()
        try:
            parsed = json.loads(json_only)
            json_canonical = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            json_canonical = json_only

    full_hash = hashlib.sha256(obj_text.encode('utf-8')).hexdigest()
    json_hash = hashlib.sha256(json_canonical.encode('utf-8')).hexdigest()

    info['full_hash'] = full_hash
    info['json_hash'] = json_hash
    info['json_canonical'] = json_canonical

    return (full_hash, json_hash, json_canonical)


def _get_run_obj_info(
    obj_text: str,
    grouping_mode: str = 'config-first',
    negation_mode: str = 'alpha',
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> dict:
    """Return per-run cached object metadata for the current sorting context."""

    # prefer a CLI-local cache keyed by object text and current run context
    run_ctx = RUN_CACHE_CONTEXT if RUN_CACHE_CONTEXT else None
    cache_key = (obj_text, run_ctx)
    info = _CLI_RUN_OBJ_INFO_CACHE.get(cache_key)
    if info is not None:
        return info

    # fall back to package-level per-object cache (by raw obj_text)
    info = RUN_OBJ_INFO_CACHE.get(obj_text)
    if info is not None:
        try:
            _CLI_RUN_OBJ_INFO_CACHE[cache_key] = info
        except Exception:
            pass
        return info

    parsed = _parse_object(obj_text)
    key_val = ''
    when_val = ''
    canonical_when = ''
    sortable_when = ''

    if parsed:
        try:
            key_val = str(parsed.get('key', ''))
            when_val = str(parsed.get('when', ''))
        except Exception:
            key_val = ''
            when_val = ''

    if when_val:
        canonical_when = _canonicalize_when(
            when_val,
            mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        sortable_when = _sortable_when_key(
            when_val,
            mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )

    info = {
        'parsed': parsed,
        'key': key_val,
        'when': when_val,
        'canonical': canonical_when,
        'sortable': sortable_when,
    }

    try:
        RUN_OBJ_INFO_CACHE[obj_text] = info
    except Exception:
        pass
    try:
        _CLI_RUN_OBJ_INFO_CACHE[cache_key] = info
    except Exception:
        pass

    return info


def _get_run_obj_match_info(obj_text: str) -> dict:
    """Return per-run cached focus/prefix/regex match signatures for an object text."""

    # respect the package run context when caching
    run_ctx = RUN_CACHE_CONTEXT if RUN_CACHE_CONTEXT else None
    cache_key = (obj_text, run_ctx)
    cached = RUN_MATCH_CACHE.get(cache_key)

    if cached is not None:
        return cached

    # attempt to reuse parsed object info if available
    parsed = RUN_OBJ_INFO_CACHE.get(obj_text)

    if parsed is None:
        parsed = _parse_object(obj_text)

    when_val = ''

    if parsed is not None:
        try:
            when_val = str(parsed.get('when', ''))
        except Exception:
            when_val = ''

    if not when_val:
        when_val = _extract_literal_when_from_object(obj_text)

    left_ids: list[str] = []
    prefix_idxs: set[int] = set()
    regex_idxs: set[int] = set()
    has_focus = False

    try:
        parts = _io._WHEN_TERM_SPLIT_RE.split(str(when_val).strip()) if when_val else []
        for part in parts:
            token = part.strip()
            if not token:
                continue

            left_id, op_has_focus, op_prefixes, op_regexes = _operand_match_signature(token, RUN_CACHE_CONTEXT)
            if not left_id:
                continue

            left_ids.append(left_id)

            if not has_focus and op_has_focus:
                has_focus = True
            for idx in op_prefixes:
                prefix_idxs.add(idx)
            for idx in op_regexes:
                regex_idxs.add(idx)

    except Exception:
        left_ids = []
        prefix_idxs = set()
        regex_idxs = set()
        has_focus = False

    match_info = {
        'left_ids': tuple(left_ids),
        'has_focus': has_focus,
        'prefix_idxs': tuple(sorted(prefix_idxs)),
        'regex_idxs': tuple(sorted(regex_idxs)),
    }

    try:
        RUN_MATCH_CACHE[cache_key] = match_info
    except Exception:
        pass

    return match_info


def _group_objects_with_comments(array_text: str) -> Tuple[List[Tuple[str, str]], str]:
    """Split a JSON array body into a list of (leading_comments, object_text) pairs and trailing comments."""

    groups: list[tuple[str, str]] = []
    comments = ''
    n = len(array_text)
    i = 0
    comments_start = 0
    obj_start = None
    depth = 0

    in_line = False
    in_block = False
    in_str = False
    esc = False
    str_char = ''

    append = groups.append
    txt = array_text

    while i < n:
        ch = txt[i]
        nxt = txt[i + 1] if i + 1 < n else ''

        if in_line:
            if ch == '\n':
                in_line = False
            i += 1
            continue
        if in_block:
            if ch == '*' and nxt == '/':
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == str_char:
                in_str = False
            i += 1
            continue

        if ch == '/' and nxt == '/':
            in_line = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_str = True
            str_char = ch
            i += 1
            continue

        if obj_start is None:
            if ch == '{':
                comments = txt[comments_start:i]
                obj_start = i
                depth = 1
            i += 1
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                obj_end = i + 1
                obj_text = txt[obj_start:obj_end]
                append((comments, obj_text))
                obj_start = None
                comments_start = obj_end
        i += 1

    trailing_comments = txt[comments_start:]
    return groups, trailing_comments


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


def _matches_entry(left: str, entry: str) -> bool:
    """Return True if the left identifier matches the when-entry pattern."""

    if entry.endswith('.'):
        return left.startswith(entry)

    if '<viewId>' in entry:
        prefix, suffix = entry.split('<viewId>', 1)
        return left.startswith(prefix) and left.endswith(suffix)

    return left == entry


def _matches_when_entry(left: str, entry: str) -> bool:
    """Return True if the left identifier matches the when-entry pattern (supports prefixes and <viewId>)."""

    if entry.endswith('.'):
        return left.startswith(entry)
    if '<viewId>' in entry:
        prefix, suffix = entry.split('<viewId>', 1)
        return left.startswith(prefix) and left.endswith(suffix)

    return left == entry


def _natural_key(s):
    """Return a locale-independent natural-sort key (a list of ints and strings) for sorting."""

    key = str(s)
    cached = CACHE_NATURAL_KEY.get(key)
    if cached is not None:
        return cached
    parts = _io._NUMBER_SPLIT_RE.split(key)
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
    parts = _io._NUMBER_SPLIT_RE.split(key)
    out = [int(text) if text.isdigit() else text for text in parts]

    try:
        CACHE_NATURAL_KEY_CS[key] = out
    except Exception:
        pass

    return out


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
    """Lightweight normalization for key sorting."""

    if not key_value:
        return ""
    key_value = str(key_value).strip().lower()
    if not key_value:
        return ""

    chords = [p for p in key_value.split() if p.strip()]
    out_chords = []
    for chord in chords:
        parts = [b.strip() for b in chord.split("+") if b.strip()]
        if not parts:
            continue
        lit = parts[-1]
        mods = sorted(parts[:-1])
        if mods:
            out_chords.append("+".join(mods + [lit]))
        else:
            out_chords.append(lit)

    return " ".join(out_chords)


def _normalize_when_in_object(obj_text: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> Tuple[str, bool]:
    """Canonicalize the `when` value inside an object text and return (new_text, changed)."""

    parsed = _parse_object(obj_text)
    if not parsed or 'when' not in parsed:
        return obj_text, False

    when_val = parsed.get('when')
    if not when_val:
        return obj_text, False

    normalized = _canonicalize_when(
        str(when_val), mode=mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
    if normalized == when_val:
        return obj_text, False

    # safely locate and replace the string literal for the `when` value
    idx = obj_text.find('"when"')
    if idx == -1:
        return obj_text, False
    # find the colon after the key
    colon = obj_text.find(':', idx)
    if colon == -1:
        return obj_text, False

    i = colon + 1
    n = len(obj_text)

    # skip whitespace/comments to find opening quote
    while i < n:
        if obj_text.startswith('//', i):
            i2 = obj_text.find('\n', i)
            i = i2 + 1 if i2 != -1 else n
            continue
        if obj_text.startswith('/*', i):
            i2 = obj_text.find('*/', i + 2)
            i = (i2 + 2) if i2 != -1 else n
            continue
        if obj_text[i].isspace():
            i += 1
            continue
        break

    if i >= n or obj_text[i] != '"':
        return obj_text, False

    qstart = i

    # find matching closing quote, honoring backslash escapes
    j = qstart + 1
    while j < n:
        ch = obj_text[j]
        if ch == '\\':
            j += 2
            continue
        if ch == '"':
            break
        j += 1
    if j >= n:
        return obj_text, False

    # build JSON-escaped inner string reliably
    try:
        escaped = json.dumps(normalized)[1:-1]
    except Exception:
        escaped = normalized.replace('\\', '\\\\').replace('"', '\\"')

    new_obj = obj_text[:qstart + 1] + escaped + obj_text[j:]
    return new_obj, True


def _object_has_trailing_comma(obj_text: str) -> bool:
    """Return True if an object text ends with a trailing comma after its closing brace."""

    lines = obj_text.rstrip().splitlines()
    found_closing = False

    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not found_closing and stripped.endswith('}'):  # first closing brace
            found_closing = True
            continue
        if found_closing:
            if stripped.startswith(','):
                return True
            elif stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
                return False

    return False


def _parse_jsonc(text: str):
    """Parse JSONC text by removing comments and trailing commas then loading JSON."""

    t = re.sub(r"//.*?$", "", text, flags=re.M)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return json.loads(t)


def _parse_object(obj_text: str):
    """Parse an object text (including braces) into a dict, caching results where possible."""

    if not obj_text:
        return None

    m = _io._OBJ_RE.search(obj_text)
    if not m:
        return None

    obj_str = m.group(0)
    cached = CACHE_JSON_OBJECT.get(obj_str)
    if cached is not None:
        return cached

    try:
        clean = _strip_json_comments(obj_str)
        clean = _strip_trailing_commas(clean)
        parsed = json.loads(clean)
        try:
            CACHE_JSON_OBJECT[obj_str] = parsed
        except Exception:
            pass
        return parsed
    except Exception:
        return None


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


def _partition_focus_groups_to_end(sorted_groups: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Stable-partition groups so that entries containing focus tokens are moved to the end."""

    non_focus: list[tuple[str, str]] = []
    focus: list[tuple[str, str]] = []

    for pair in sorted_groups:
        try:
            if _contains_focus_token_in_object(pair[1]):
                focus.append(pair)
            else:
                non_focus.append(pair)
        except Exception:
            non_focus.append(pair)

    return non_focus + focus


def _remove_blank_lines(text: str) -> str:
    """Remove empty lines that are not present in comments."""

    lines = text.splitlines(keepends=True)
    out_lines: list[str] = []
    in_block = False

    for line in lines:
        if in_block:
            out_lines.append(line)
            if '*/' in line:
                in_block = False
            continue

        if '/*' in line:
            out_lines.append(line)
            if '*/' not in line:
                in_block = True
            continue

        if line.strip() == '':
            continue
        out_lines.append(line)

    return ''.join(out_lines)


def _render_when_node(node: WhenNode) -> str:
    """Render a WhenNode AST back to its string form while preserving parentheses."""

    inner = node._to_str()

    if node.parens:
        return f'({inner})'

    return inner


def _reorder_groups_by_when(sorted_groups: list[tuple[str, str]], negation_mode: str) -> list[tuple[str, str]]:
    """Within equal when groups, reorder objects deterministically by key."""

    if negation_mode in ('positive', 'negative'):
        return sorted_groups
    groups_list = list(sorted_groups)
    i = 0
    while i < len(groups_list):
        raw_when = _extract_literal_when_from_object(groups_list[i][1]) or ''
        norm_when = _io._normalize_whitespace(raw_when)
        j = i + 1

        while j < len(groups_list):
            next_when = _extract_literal_when_from_object(groups_list[j][1]) or ''
            if _io._normalize_whitespace(next_when) != norm_when:
                break
            j += 1

        if j - i > 1:
            slice_pairs = groups_list[i:j]

            def _mods_lit_from_pair(pair: tuple[str, str]) -> tuple[tuple[str, ...], str]:
                key_raw = _extract_literal_key_from_object(pair[1]) or ''
                norm = _normalize_key_for_compare(key_raw)
                first = norm.split()[0] if norm else ''
                parts = [p for p in first.split('+') if p]
                mods = tuple(parts[:-1]) if len(parts) > 1 else tuple()
                lit = parts[-1] if parts else ''
                lit_key = _normalize_key_for_compare(lit)
                return (mods, lit_key)

            slice_pairs.sort(key=lambda pair: _mods_lit_from_pair(pair))
            groups_list[i:j] = slice_pairs

        i = j

    return groups_list


def _replace_when_literal_match(
    match,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    """Replace a `when` literal match with its canonicalized, JSON-escaped value."""

    inner = match.group(2)

    try:
        unescaped = json.loads('"' + inner + '"')
    except Exception:
        unescaped = inner

    canonical = _canonicalize_when(
        unescaped,
        mode=grouping_mode,
        negation_mode=negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    try:
        escaped = json.dumps(canonical)[1:-1]
    except Exception:
        escaped = canonical.replace('\\', '\\\\').replace('"', '\\"')

    escaped = escaped.replace('\n', '\\n').replace('\r', '\\r')
    return match.group(1) + escaped + match.group(3)


def _replace_when_literals(
    text: str,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    """Replace all `when` string literals inside JSONC text with their canonical forms."""

    return re.sub(
        r'("when"\s*:\s*")((?:\\.|[^"\\])*)(")',
        lambda match: _replace_when_literal_match(
            match,
            grouping_mode,
            negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        ),
        text,
    )


def _set_run_cache_context(mode: str, negation_mode: str, when_prefixes: list | None, when_regexes: list | None) -> None:
    """Initialize and clear per-run caches for the current run parameter context."""

    global _CLI_RUN_OBJ_INFO_CACHE, _CLI_RUN_OBJ_MATCH_CACHE
    global RUN_CACHE_CONTEXT, RUN_CANONICAL_CACHE, RUN_SORTABLE_CACHE, RUN_OBJ_INFO_CACHE, RUN_MATCH_CACHE

    RUN_CACHE_CONTEXT = (
        mode,
        negation_mode,
        None if when_prefixes is None else tuple(when_prefixes),
        None if when_regexes is None else tuple(when_regexes),
    )
    try:
        RUN_CANONICAL_CACHE.clear()
    except Exception:
        RUN_CANONICAL_CACHE = {}
    try:
        RUN_SORTABLE_CACHE.clear()
    except Exception:
        RUN_SORTABLE_CACHE = {}
    try:
        RUN_OBJ_INFO_CACHE.clear()
    except Exception:
        RUN_OBJ_INFO_CACHE = {}
    try:
        _CLI_RUN_OBJ_INFO_CACHE.clear()
    except Exception:
        _CLI_RUN_OBJ_INFO_CACHE = {}
    try:
        _CLI_RUN_OBJ_MATCH_CACHE.clear()
    except Exception:
        _CLI_RUN_OBJ_MATCH_CACHE = {}
    try:
        RUN_MATCH_CACHE.clear()
    except Exception:
        RUN_MATCH_CACHE = {}
    try:
        # clear package-level canonicalizer LRU cache
        _clear_lru_when_cache()
    except Exception:
        pass


def _sortable_when_key(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
    """Return a canonicalized when string suitable for stable sorting, preserving negation."""

    if not when_val:
        return ''

    cache_key = (
        when_val,
        mode,
        negation_mode,
        None if when_prefixes is None else tuple(when_prefixes),
        None if when_regexes is None else tuple(when_regexes),
    )

    cached = CACHE_SORTABLE_WHEN.get(cache_key)
    if cached is not None:
        return cached

    # preserve negation for stable sorting by canonicalizing using package canonicalizer
    when = _canonicalize_when(when_val)

    try:
        CACHE_SORTABLE_WHEN[cache_key] = when
    except Exception:
        pass

    return when


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


def _strip_json_comments(text):
    """Strip JavaScript-style comments from JSONC text while preserving string literals."""

    def _replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ''
        return s

    return _io._COMMENT_RE.sub(_replacer, text)


def _strip_trailing_commas(text):
    """Remove trailing commas from JSON/JSONC text."""

    return _io._TRAILING_COMMA_RE.sub(r"\1", text)


def _strip_when_sorted_comment(comment_text: str, when_changed: bool) -> str:
    """Remove previously-inserted when-sorted comment lines."""

    if not when_changed:
        return comment_text

    return _io._WHEN_SORTED_RE.sub('', comment_text)


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


def _when_specificity(when_val: str) -> Tuple[int]:
    """Return a heuristic specificity tuple for a when clause (fewer terms is broader)."""

    key = '' if when_val is None else str(when_val)
    cached = CACHE_WHEN_SPECIFICITY.get(key)
    if cached is not None:
        return cached
    if not key:
        res = (0,)
    else:
        term_count = len(_io._WHEN_TERM_SPLIT_RE.split(key.strip()))
        res = (term_count,)
    try:
        CACHE_WHEN_SPECIFICITY[key] = res
    except Exception:
        pass
    return res


def _operand_match_signature(token: str, run_ctx) -> tuple[str, bool, tuple[int, ...], tuple[int, ...]]:
    """Compute and cache a small signature for a single operand token under a run context.

    Returns (left_id, has_focus, prefix_idxs_tuple, regex_idxs_tuple).
    """

    cache_key = (token, run_ctx)
    cached = OPERAND_MATCH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    t = token.strip()
    while t.startswith('(') and t.endswith(')'):
        t = t[1:-1].strip()
    if not t:
        res = ('', False, (), ())
        try:
            OPERAND_MATCH_CACHE[cache_key] = res
        except Exception:
            pass
        return res

    left = t[1:].lstrip() if t.startswith('!') else t
    left_id = left.split()[0] if left else ''

    has_focus = any(_matches_entry(left_id, entry) for entry in FOCUS_TOKENS) if left_id else False

    prefix_idxs: set[int] = set()
    regex_idxs: set[int] = set()

    run_prefixes = run_ctx[2] if run_ctx else None
    if run_prefixes:
        for idx, prefix in enumerate(run_prefixes):
            try:
                if left_id.startswith(prefix):
                    prefix_idxs.add(idx)
            except Exception:
                continue

    run_regexes = run_ctx[3] if run_ctx else None
    if run_regexes:
        for idx, rx in enumerate(run_regexes):
            try:
                if hasattr(rx, 'search'):
                    if rx.search(left_id):
                        regex_idxs.add(idx)
                else:
                    if str(rx) in left_id:
                        regex_idxs.add(idx)
            except Exception:
                continue

    res = (left_id, has_focus, tuple(sorted(prefix_idxs)), tuple(sorted(regex_idxs)))
    try:
        OPERAND_MATCH_CACHE[cache_key] = res
    except Exception:
        pass
    return res


def _with_normalized_when_groups(
    groups: list[tuple[str, str]],
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> list[tuple[str, str]]:
    """Normalize the when clauses across a list of groups and return the resulting list."""

    normalized_groups: list[tuple[str, str]] = []
    for comments, obj in groups:
        obj_out = obj.rstrip()
        obj_out, when_changed = _normalize_when_in_object(
            obj_out,
            mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        comments = _strip_when_sorted_comment(comments, when_changed)
        normalized_groups.append((comments, obj_out))

        # warm the per-run object cache for downstream sort and grouping passes
        try:
            _ = _get_run_obj_info(
                obj_out,
                grouping_mode=grouping_mode,
                negation_mode=negation_mode,
                when_prefixes=when_prefixes,
                when_regexes=when_regexes,
            )
        except Exception:
            pass

    return normalized_groups
