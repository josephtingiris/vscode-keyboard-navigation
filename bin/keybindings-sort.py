#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Sort VS Code `keybindings.json` (JSONC) while preserving comments.

Usage:
    python3 keybindings-sort.py [--primary {key,when}] [--secondary {key,when}] [--when-grouping {none,config-first,focal-invariant}] [--group-sorting {alpha,beta,natural,negative,positive}] < keybindings.json

Examples:
    python3 bin/keybindings-sort.py < keybindings.json > keybindings.sorted.by_key.json
    python3 bin/keybindings-sort.py --primary when < keybindings.json > keybindings.sorted.by_when.json

Options:
    --primary, -p {key,when}                                               Primary sort field (default: key)
    --secondary, -s {key,when}                                             Secondary sort field (optional)
    --when-grouping, -w {none,config-first,focal-invariant}                When grouping mode: built-in group/rank modes for when tokens (default: none)
    --group-sorting, -g {alpha,beta,natural,negative,positive}             Group sorting mode: how-to sort within the when token grouping(s) (default: alpha)
    -h, --help                                                             Show this usage message and exit

Behavior:
    - Predictably and purposefully sorts entries in a VS Code `keybindings.json` while preserving comments and surrounding formatting.

    Sorting Overview
        - Default: Sort by `key` (natural, numeric-aware order).
        - Primary `when`: Use `--primary when` to make `when` the primary sort key; objects are grouped by the first top-level token of the canonicalized `when` and then ordered by `when`-specificity and `key`.
        - Group sorting option: `--group-sorting` controls token ordering inside canonicalized `when` clauses (modes: `alpha`, `natural`, `positive`, `negative`, `beta`).

    `when` Handling (High Level)
        1) Canonicalize: Parse and normalize each `when` expression into an AST, flatten safe AND operands, and remove exact duplicate operands.
        2) Group: Assign every operand to a stable semantic bucket according to `--when-grouping` (examples: `config.*`, positional, focus, visibility, other). Grouping decides which classes of tokens appear before others. Use `none` to disable grouping.
        3) Sort within groups: Within each bucket, order operands using the comparator chosen by `--group-sorting`. Sorting only reorders operands inside their group and never moves an operand into a different group.
        4) Render: Reassemble the canonical `when` string, preserving OR structure and parentheses.

    Trailing Commas & Duplicates
        - Preserve commas: Attempts to preserve trailing commas where present.
        - Annotate duplicates: Exact duplicate key/`when` pairs receive a trailing `// DUPLICATE` comment.
        - Duplicate removal rule: Removes exact duplicate operands by rendered-string match; `a` and `!a` are treated as different tokens.

    Additional Details
        - Stability: Grouping is stable; operands never move between groups during sorting.
        - Duplicate semantics: Duplicates are determined by exact rendered-string equality.
        - Formatting preservation: Preserves comments and surrounding formatting before/after the top-level array and inside each object.

Inputs / Outputs:
    stdin:  JSONC text (keybindings array)
    stdout: Sorted JSONC text encoded as UTF-8

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""
import sys
import re
import json
import argparse
from typing import List, Tuple

# canonical when-token classification sets
FOCUS_TOKENS = {
    'auxiliaryBarFocus',
    'editorFocus',
    'editorTextFocus',
    'inputFocus',
    'listFocus',
    'notificationFocus',
    'panelFocus',
    'sideBarFocus',
    'terminalFocus',
    'textInputFocus',
}

POSITIONAL_TOKENS = [
    'activeAuxiliary',
    'activeEditor',
    'activePanel',
    'activeViewlet',
    'config.workbench.activityBar.location',
    'config.workbench.sideBar.location',
    'focusedView',
    'panel.location',
    'panelPosition',
]

VISIBILITY_TOKENS = {
    'auxiliaryBarVisible',
    'editorVisible',
    'notificationCenterVisible',
    'notificationToastsVisible',
    'outline.visible',
    'panelVisible',
    'searchViewletVisible',
    'sideBarVisible',
    'terminalVisible',
    'timeline.visible',
    'view.<viewId>.visible',
    'webviewFindWidgetVisible',
}

# default literal prefixes to prioritize (can be overridden via CLI)
DEFAULT_WHEN_PREFIXES = []


def extract_preamble_postamble(text):
    """
    Find the top-level JSON array brackets, skipping any brackets that appear
    inside comments or strings in the preamble/postamble.
    """
    i = 0
    n = len(text)
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    start = -1

    # find opening bracket, skipping comments and strings
    while i < n:
        ch = text[i]
        next2 = text[i:i+2] if i+2 <= n else ''

        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == '*/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if next2 == '//':
            in_line_comment = True
            i += 2
            continue
        if next2 == '/*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == '[':
            start = i
            break
        i += 1

    if start == -1:
        return '', '', text

    # find matching closing bracket
    depth = 1
    i = start + 1
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    end = -1

    while i < n:
        ch = text[i]
        next2 = text[i:i+2] if i+2 <= n else ''

        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == '*/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue

        # not in string/comment
        if next2 == '//':
            in_line_comment = True
            i += 2
            continue
        if next2 == '/*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
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

    preamble = text[:start]
    postamble = text[end+1:]
    array_text = text[start+1:end]  # exclude [ and ]
    return preamble, array_text, postamble


def group_objects_with_comments(array_text: str) -> Tuple[List[Tuple[str, str]], str]:
    groups = []
    comments = ''
    buf = ''
    depth = 0
    in_obj = False
    for line in array_text.splitlines(keepends=True):
        stripped = line.strip()
        if not in_obj:
            if '{' in stripped:
                in_obj = True
                depth = stripped.count('{') - stripped.count('}')
                buf = line
            else:
                comments += line
        else:
            buf += line
            depth += line.count('{') - line.count('}')
            if depth == 0:
                groups.append((comments, buf))
                comments = ''
                buf = ''
                in_obj = False
    trailing_comments = comments
    return groups, trailing_comments


def strip_json_comments(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ''
        return s
    pattern = r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)'  # string or comment
    return re.sub(pattern, replacer, text, flags=re.DOTALL | re.MULTILINE)


def strip_trailing_commas(text):
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def natural_key(s):
    import re
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def natural_key_case_sensitive(s):
    import re
    return [int(text) if text.isdigit() else text for text in re.split(r'(\d+)', s)]


def when_specificity(when_val: str) -> Tuple[int]:
    """
    Heuristic specificity score for a when clause. Lower is broader.
        Returns a tuple so we can sort stably by:
            1) number of condition terms (split on && / ||)
    """
    if not when_val:
        return (0,)

    term_count = len(re.split(r'\s*&&\s*|\s*\|\|\s*', when_val.strip()))
    return (term_count,)


class WhenNode:
    def __init__(self, parens: bool = False):
        self.parens = parens

    def to_str(self) -> str:
        raise NotImplementedError


class WhenLeaf(WhenNode):
    def __init__(self, text: str, parens: bool = False):
        super().__init__(parens=parens)
        self.text = text

    def to_str(self) -> str:
        return self.text


class WhenNot(WhenNode):
    def __init__(self, child: WhenNode, parens: bool = False):
        super().__init__(parens=parens)
        self.child = child

    def to_str(self) -> str:
        child_str = self.child.to_str()
        if isinstance(self.child, (WhenAnd, WhenOr)) and not self.child.parens:
            child_str = f'({child_str})'
        return f'!{child_str}'


class WhenAnd(WhenNode):
    def __init__(self, children, parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def to_str(self) -> str:
        return ' && '.join([render_when_node(c) for c in self.children])


class WhenOr(WhenNode):
    def __init__(self, children, parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def to_str(self) -> str:
        return ' || '.join([render_when_node(c) for c in self.children])


def render_when_node(node: WhenNode) -> str:
    inner = node.to_str()
    if node.parens:
        return f'({inner})'
    return inner


def normalize_operand(text: str) -> str:
    collapsed = re.sub(r'\s+', ' ', text).strip()
    return collapsed


def tokenize_when(expr: str):
    tokens = []
    buf = ''
    i = 0
    n = len(expr)
    in_single = False
    in_double = False
    in_regex = False
    regex_escape = False
    prev_nonspace = ''

    def flush_buf():
        nonlocal buf
        if buf.strip():
            tokens.append(('OPERAND', normalize_operand(buf)))
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
            flush_buf()
            tokens.append(('OP', expr[i:i+2]))
            i += 2
            prev_nonspace = ''
            continue

        if ch in '()':
            flush_buf()
            tokens.append(('OP', ch))
            i += 1
            prev_nonspace = ch
            continue

        if ch == '!':
            nxt = expr[i+1] if i + 1 < n else ''
            if nxt == '=':
                buf += ch
                i += 1
                prev_nonspace = ch
                continue
            if not buf.strip():
                flush_buf()
                tokens.append(('OP', '!'))
                i += 1
                prev_nonspace = '!'
                continue

        buf += ch
        if not ch.isspace():
            prev_nonspace = ch
        i += 1

    flush_buf()
    return tokens


def parse_when(expr: str) -> WhenNode:
    tokens = tokenize_when(expr)
    idx = 0

    def peek():
        return tokens[idx] if idx < len(tokens) else None

    def consume():
        nonlocal idx
        t = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return t

    def parse_primary():
        t = peek()
        if not t:
            return WhenLeaf('')
        if t[0] == 'OP' and t[1] == '(':
            consume()  # (
            node = parse_or()
            next_token = peek()
            if next_token and next_token[0] == 'OP' and next_token[1] == ')':
                consume()
                node.parens = True
            return node
        if t[0] == 'OPERAND':
            consume()
            return WhenLeaf(t[1])
        return WhenLeaf('')

    def parse_unary():
        t = peek()
        if t and t[0] == 'OP' and t[1] == '!':
            consume()
            return WhenNot(parse_unary())
        return parse_primary()

    def parse_and():
        node = parse_unary()
        children = [node]
        while True:
            t = peek()
            if t and t[0] == 'OP' and t[1] == '&&':
                consume()
                children.append(parse_unary())
            else:
                break
        if len(children) == 1:
            return children[0]
        return WhenAnd(children)

    def parse_or():
        node = parse_and()
        children = [node]
        while True:
            t = peek()
            if t and t[0] == 'OP' and t[1] == '||':
                consume()
                children.append(parse_and())
            else:
                break
        if len(children) == 1:
            return children[0]
        return WhenOr(children)

    return parse_or()


def canonicalize_when(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
    """
    Produce a canonical string for a `when` clause by sorting operands inside every AND node according to project conventions. Preserves OR groupings and existing parentheses; does not reorder OR-level operands.
    """
    if not when_val:
        return ''
    """
        TBD: these need to be tested before being integrated, especially with the focal-invariant mode:
        'view.',
        'view.<viewId>.visible',
        'view.container.',
        'viewContainer.',
        'workbench.panel.',
        'workbench.view.',
    ]
    """
    focus_tokens = FOCUS_TOKENS
    positional_tokens = POSITIONAL_TOKENS
    visibility_tokens = VISIBILITY_TOKENS

    def left_identifier(text: str) -> str:
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

    def _is_focus(left: str) -> bool:
        return any(_matches_entry(left, entry) for entry in focus_tokens)

    def _is_visibility(left: str) -> bool:
        return any(_matches_entry(left, entry) for entry in visibility_tokens)

    def group_rank(text: str) -> int:
        left = left_identifier(text)

        if when_prefixes:
            for pref in when_prefixes:
                if not pref:
                    continue
                # literal exact-match against the left identifier
                if left == pref:
                    return 0
        if when_regexes:
            for pat in when_regexes:
                try:
                    if pat.search(left):
                        return 0
                except Exception:
                    # if user provided a string pattern that wasn't compiled,
                    # fall back to a simple substring match.
                    try:
                        if re.search(pat, left):
                            return 0
                    except Exception:
                        continue
        # 'config-first' Group order: config.* -> positional prefixes -> focus -> visibility -> other
        # 'focal-invariant' Group order: focus -> visibility -> positional prefixes -> config.* -> other
        # 'none' disables grouping by returning the same rank for all tokens.
        if mode == 'none':
            return 1
        if mode == 'focal-invariant':
            if _is_focus(left):
                return 1
            if _is_visibility(left):
                return 2
            if any(left.startswith(p) for p in positional_tokens):
                return 3
            if left.startswith('config.'):
                return 4
            return 5
        # config-first behavior
        if left.startswith('config.'):
            return 1
        if any(left.startswith(p) for p in positional_tokens):
            return 2
        if _is_focus(left):
            return 3
        if _is_visibility(left):
            return 4
        return 5

    def sort_key(idx_and_node):
        idx, node = idx_and_node
        token = render_when_node(node)
        # strip leading '!' for ordering token but keep for grouping rank
        order_token = token[1:] if token.startswith('!') else token
        # default alpha behavior: preserve group_rank and use natural-sensitive ordering
        if negation_mode == 'alpha':
            return (group_rank(token), natural_key_case_sensitive(order_token), idx)
        # for other modes we'll not use this sort_key; they use alternate sorting below
        return (group_rank(token), natural_key_case_sensitive(order_token), idx)

    def sort_and_nodes(node: WhenNode):
        if isinstance(node, WhenAnd):
            for child in node.children:
                sort_and_nodes(child)
            items = list(enumerate(node.children))

            # prioritize operands
            prioritized = []
            picked = set()

            # get left identifier for an item
            def _left_id_of(item_node):
                tok = render_when_node(item_node)
                lid = left_identifier(tok)
                return lid
            if when_prefixes:
                for pref in when_prefixes:
                    matches = []
                    for idx, child in items:
                        if idx in picked:
                            continue
                        lid = _left_id_of(child)
                        if lid == pref:
                            matches.append((idx, child))
                    if matches:
                        # alphabetical order for multiples
                        matches.sort(key=lambda t: natural_key_case_sensitive(
                            render_when_node(t[1])))
                        for m in matches:
                            prioritized.append(m[1])
                            picked.add(m[0])
            if when_regexes:
                for pat in when_regexes:
                    matches = []
                    for idx, child in items:
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
                        matches.sort(key=lambda t: natural_key_case_sensitive(
                            render_when_node(t[1])))
                        for m in matches:
                            prioritized.append(m[1])
                            picked.add(m[0])

            if negation_mode == 'beta':
                # alias
                nm = 'positive'
            else:
                nm = negation_mode

            if negation_mode == 'alpha':
                # use existing group-aware sort_key
                items.sort(key=sort_key)
                sorted_children = [it[1] for it in items]
            else:
                # for natural/positive/negative/beta: sort by rendered token base
                def render_base_and_flag(child):
                    tok = render_when_node(child)
                    base = tok.strip()
                    # strip surrounding parentheses
                    while base.startswith('(') and base.endswith(')'):
                        base = base[1:-1].strip()
                    is_neg = base.startswith('!')
                    if is_neg:
                        base = base[1:].lstrip()
                    return base, is_neg, tok

                items_with_keys = []
                for idx, child in items:
                    base, is_neg, tok = render_base_and_flag(child)
                    # natural-style comparison: use natural_key (case-insensitive)
                    base_key = natural_key(base)
                    # always preserve grouping as the primary key so sorting does not move operands between buckets.
                    grp = group_rank(tok)
                    # natural mode: ignore negation and sort by group then base_key
                    if nm == 'natural':
                        items_with_keys.append(
                            (idx, child, (grp, base_key, idx, tok)))
                        continue
                    # positive/negative: prefer positives or negatives accordingly
                    if nm == 'positive':
                        neg_sort = 0 if not is_neg else 1
                    elif nm == 'negative':
                        neg_sort = 0 if is_neg else 1
                    else:
                        neg_sort = 0
                    # prioritize negation flag before base key
                    items_with_keys.append(
                        (idx, child, (grp, neg_sort, base_key, idx, tok)))
                items_with_keys.sort(key=lambda t: t[2])
                sorted_children = [it[1] for it in items_with_keys]

            if prioritized:
                prioritized_tokens = [render_when_node(p) for p in prioritized]
                remaining = [c for c in sorted_children if render_when_node(c) not in set(prioritized_tokens)]
                merged = prioritized + remaining
            else:
                merged = sorted_children

            unique: list[WhenNode] = []
            seen = set()
            for c in merged:
                tok = render_when_node(c)
                if tok in seen:
                    continue
                seen.add(tok)
                unique.append(c)
            node.children = unique
        elif isinstance(node, WhenOr):
            for child in node.children:
                sort_and_nodes(child)

            # rrmove duplicate OR operands while preserving order
            unique: list[WhenNode] = []
            seen = set()
            for c in node.children:
                tok = render_when_node(c)
                if tok in seen:
                    continue
                seen.add(tok)
                unique.append(c)
            node.children = unique
        elif isinstance(node, WhenNot):
            sort_and_nodes(node.child)

    ast = parse_when(when_val)
    sort_and_nodes(ast)
    return render_when_node(ast)


def sortable_when_key(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
    if not when_val:
        return ''

    # preserve negation for sorting to avoid unstable ordering when otherwise-identical clauses differ only by '!'.
    return canonicalize_when(when_val, mode=mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)


def extract_sort_keys(obj_text: str, primary: str = 'key', secondary: str | None = None, tertiary: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> Tuple:
    obj_match = re.search(r'\{.*\}', obj_text, re.DOTALL)
    if not obj_match:
        return ([], '', '')
    obj_str = obj_match.group(0)
    try:
        clean = strip_json_comments(obj_str)
        clean = strip_trailing_commas(clean)
        obj = json.loads(clean)
        key_val = str(obj.get('key', ''))
        when_val = str(obj.get('when', ''))
        canonical_when = canonicalize_when(
            when_val, mode=tertiary, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
        sortable_when = sortable_when_key(
            when_val, mode=tertiary, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)

        # derive the first top-level when token for grouping when primary sorting
        first_when_token = ''
        if canonical_when:
            parts = re.split(r'\s*&&\s*|\s*\|\|\s*', canonical_when.strip())
            if parts:
                first_when_token = parts[0].strip()
                # remove surrounding parentheses and leading negation for grouping
                while first_when_token.startswith('(') and first_when_token.endswith(')'):
                    first_when_token = first_when_token[1:-1].strip()
                if first_when_token.startswith('!'):
                    first_when_token = first_when_token[1:].lstrip()

        # build a flexible sort tuple based on primary/secondary preferences.
        tokens = []

        def append_when():
            if primary == 'when':
                first_key = natural_key_case_sensitive(first_when_token)

                # compute an optional priority rank based on user-supplied when_prefixes
                match_rank = 9999
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
                spec_key = when_specificity(when_val)

                tokens.append(match_rank)
                if negation_mode == 'alpha':
                    tert = natural_key_case_sensitive(sortable_when)
                elif negation_mode == 'natural':
                    base = sortable_when.lstrip('!')
                    tert = natural_key(base)
                elif negation_mode in ('positive', 'beta'):
                    is_neg = 1 if sortable_when.startswith('!') else 0
                    base = sortable_when.lstrip('!')
                    tert = (is_neg, natural_key(base))
                elif negation_mode == 'negative':
                    is_neg = 0 if sortable_when.startswith('!') else 1
                    base = sortable_when.lstrip('!')
                    tert = (is_neg, natural_key(base))
                else:
                    tert = natural_key_case_sensitive(sortable_when)

                # (this makes matched groups easier to inspect).
                if match_rank != 9999:
                    tokens.append(natural_key_case_sensitive(key_val))
                    tokens.append(spec_key)
                    tokens.append(tert)
                else:
                    # default behavior: include first_when token so grouping remains primary,
                    # then specificity and tertiary ordering
                    tokens.append(first_key)
                    tokens.append(spec_key)
                    tokens.append(tert)
                return

            tokens.append(when_specificity(when_val))
            tokens.append(natural_key_case_sensitive(sortable_when))

        def append_key():
            tokens.append(natural_key(key_val))

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

        if tokens and not isinstance(tokens[0], int):
            tokens.insert(0, 9999)
        return tuple(tokens)
    except Exception:
        # return a key with the same structural types as a normal sort key: (int rank, list key, tuple specificity, list tertiary)
        return (9999, [], (0,), [])


def normalize_when_in_object(obj_text: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> Tuple[str, bool]:
    pattern = re.compile(r'("when"\s*:\s*")((?:\\.|[^"\\])*)(")')
    match = pattern.search(obj_text)
    if not match:
        return obj_text, False
    original_when = match.group(2)

    normalized = canonicalize_when(
        original_when, mode=mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
    if normalized == original_when:
        return obj_text, False
    new_obj = obj_text[:match.start(2)] + normalized + obj_text[match.end(2):]
    return new_obj, True


def extract_key_when(obj_text: str) -> Tuple[str, str]:
    obj_match = re.search(r'\{.*\}', obj_text, re.DOTALL)
    if not obj_match:
        return ('', '')
    obj_str = obj_match.group(0)
    try:
        clean = strip_json_comments(obj_str)
        clean = strip_trailing_commas(clean)
        obj = json.loads(clean)
        key_val = str(obj.get('key', ''))
        when_val = str(obj.get('when', ''))
        return (key_val, when_val)
    except Exception:
        return ('', '')


def object_has_trailing_comma(obj_text: str) -> bool:
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


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description='Sort VS Code keybindings.json by key/when',
        epilog="Example: %(prog)s --primary when < keybindings.json > out.json",
    )
    parser.add_argument('--primary', '-p', choices=['key', 'when'], default='key',
                        help="Primary sort field: 'key' (default) or 'when')")
    parser.add_argument('--secondary', '-s', choices=['key', 'when'], default=None,
                        help="Secondary sort field: 'key' or 'when' (optional)")
    parser.add_argument('--group-sorting', '-g', dest='group_sorting',
                        choices=['alpha', 'beta', 'natural', 'negative', 'positive'], default='alpha',
                        help="Group sorting mode: how to sort tokens within when groups (default: alpha)")
    parser.add_argument('--when-grouping', '-w', dest='when_grouping',
                        choices=['none', 'config-first', 'focal-invariant'], default='none',
                        help="When grouping mode: how to group/rank top-level when tokens")
    parser.add_argument('--when-prefix', '-P', dest='when_prefix', default=None,
                        help="Comma-separated literal when-prefixes to prioritize (exact match). Provide at least one when present.")
    parser.add_argument('--when-regex', '-R', dest='when_regex', default=None,
                        help="Comma-separated regexes to match when-identifiers to prioritize (order matters). Provide at least one when present.")

    args = parser.parse_args(argv)

    primary_order = args.primary
    secondary_order = args.secondary
    tertiary_mode = args.when_grouping
    negation_mode = args.group_sorting

    if args.when_prefix is not None:
        if args.when_prefix.strip() == '':
            parser.error(
                '--when-prefix requires a comma-separated list with at least one entry')
        else:
            when_prefixes = [p.strip()
                             for p in args.when_prefix.split(',') if p.strip()]
            if not when_prefixes:
                parser.error(
                    '--when-prefix requires a comma-separated list with at least one entry')
    else:
        when_prefixes = DEFAULT_WHEN_PREFIXES.copy()
    when_regexes = None
    if args.when_regex:
        parts = [p.strip() for p in args.when_regex.split(',') if p.strip()]
        if not parts:
            parser.error(
                '--when-regex requires a comma-separated list with at least one entry')
        compiled = []
        for p in parts:
            try:
                compiled.append(re.compile(p))
            except Exception:
                # keep raw string fallback (will be tried with re.search)
                compiled.append(p)
        when_regexes = compiled

    # always normalize `when` clauses so sub-clauses are deduped and grouped consistently before any sorting.
    normalize_when = True

    raw = sys.stdin.read()
    preamble, array_text, postamble = extract_preamble_postamble(raw)
    groups, trailing_comments = group_objects_with_comments(array_text)

    normalized_groups = []
    for comments, obj in groups:
        obj_out = obj.rstrip()
        when_changed = False
        if normalize_when:
            obj_out, when_changed = normalize_when_in_object(
                obj_out, mode=tertiary_mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
            if when_changed:
                comments = re.sub(r'^\s*//\s*when-sorted:.*\n',
                                  '', comments, flags=re.MULTILINE)
        normalized_groups.append((comments, obj_out))

    # sort by chosen primary (natural), then the other field (natural), then by _comment
    sorted_groups = sorted(normalized_groups, key=lambda pair: extract_sort_keys(
        pair[1], primary=primary_order, secondary=secondary_order, tertiary=tertiary_mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes))

    # partition results by the first top-level `when` token's semantic group and emit groups in reverse rank order so the most "focused" group (rank 1 under focal-invariant) ends up at the bottom of the file.
    def first_when_group_rank(obj_text: str, mode: str, when_prefixes: list | None = None, when_regexes: list | None = None) -> int:
        # TODO: DRY; share the grouping logic used in `canonicalize_when`.
        when_key, when_val = extract_key_when(obj_text)
        canonical = canonicalize_when(
            when_val, mode=mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
        if not canonical:
            return 5
        parts = re.split(r'\s*&&\s*|\s*\|\|\s*', canonical.strip())
        if not parts:
            return 5
        first = parts[0].strip()
        while first.startswith('(') and first.endswith(')'):
            first = first[1:-1].strip()
        if first.startswith('!'):
            left = first[1:].lstrip()
        else:
            left = first
        if not left:
            return 5
        left_id = left.split()[0]

        focus_tokens = FOCUS_TOKENS
        positional_tokens = POSITIONAL_TOKENS
        visibility_tokens = VISIBILITY_TOKENS

        def _matches_entry(left: str, entry: str) -> bool:
            if entry.endswith('.'):
                return left.startswith(entry)
            if '<viewId>' in entry:
                prefix, suffix = entry.split('<viewId>', 1)
                return left.startswith(prefix) and left.endswith(suffix)
            return left == entry

        def _is_focus(left: str) -> bool:
            return any(_matches_entry(left, entry) for entry in focus_tokens)

        def _is_visibility(left: str) -> bool:
            return any(_matches_entry(left, entry) for entry in visibility_tokens)

        # group ranking matches the logic in canonicalize_when
        if mode == 'focal-invariant':
            if _is_focus(left_id):
                return 1
            if _is_visibility(left_id):
                return 2
            if any(left_id.startswith(p) for p in positional_tokens):
                return 3
            if left_id.startswith('config.'):
                return 4
            return 5
        # default ordering
        if left_id.startswith('config.'):
            return 1
        if any(left_id.startswith(p) for p in positional_tokens):
            return 2
        if _is_focus(left_id):
            return 3
        if _is_visibility(left_id):
            return 4
        return 5

    if tertiary_mode != 'none':
        buckets: dict[int, list] = {}
        for pair in sorted_groups:
            rank = first_when_group_rank(
                pair[1], tertiary_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
            buckets.setdefault(rank, []).append(pair)

        # emit buckets in reverse rank order so lower-numbered (focus) groups end up at the bottom of the output
        final_groups: list = []
        for rank in sorted(buckets.keys(), reverse=True):
            final_groups.extend(buckets[rank])

        sorted_groups = final_groups

    # for primary `when` sorting (-p when), enforce canonical-when group order for the final output
    if primary_order == 'when':
        def _pair_key_literal(obj_text: str) -> str:
            m = re.search(r'"key"\s*:\s*"((?:\\.|[^"\\])*)"', obj_text)
            if not m:
                return ''
            raw = m.group(1)
            try:
                return bytes(raw, 'utf-8').decode('unicode_escape')
            except Exception:
                return raw

        def _pair_when_literal(obj_text: str) -> str:
            m = re.search(r'"when"\s*:\s*"((?:\\.|[^"\\])*)"', obj_text)
            if not m:
                return ''
            raw = m.group(1)
            try:
                return bytes(raw, 'utf-8').decode('unicode_escape')
            except Exception:
                return raw

        decorated: list[tuple[str, str, tuple[str, str]]] = []
        for pair in sorted_groups:
            key_val, when_val = extract_key_when(pair[1])
            if not key_val:
                key_val = _pair_key_literal(pair[1])
            if not when_val:
                when_val = _pair_when_literal(pair[1])
            decorated.append((key_val, when_val, pair))

        # stable two-pass sort:
        #   1) key ascending (secondary within group)
        #   2) when ascending (final primary ordering)
        decorated = sorted(decorated, key=lambda row: natural_key(row[0]))
        decorated = sorted(decorated, key=lambda row: row[1])
        sorted_groups = [row[2] for row in decorated]

    seen = set()
    sys.stdout.write(preamble)

    sys.stdout.write('[\n')
    for i, (comments, obj) in enumerate(sorted_groups):
        is_last = (i == len(sorted_groups) - 1)
        obj_out = obj.rstrip()
        key_val, when_val = extract_key_when(obj_out)
        canonical_when = canonicalize_when(
            when_val, mode=tertiary_mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
        pair_id = (key_val, canonical_when)
        if pair_id in seen:
            comments += f'// DUPLICATE key: {key_val!r} when: {canonical_when!r}\n'
        seen.add(pair_id)

        if comments:
            comments = re.sub(r'(?m)^[ \t]*\n+', '', comments)
        sys.stdout.write(comments)
        idx = obj_out.rfind('}')
        if idx != -1:
            after = obj_out[idx+1:]
            after_clean = re.sub(r'^\s*,+', '', after)
            obj_out = obj_out[:idx+1] + after_clean
        sys.stdout.write(obj_out)
        if not is_last and not object_has_trailing_comma(obj_out):
            sys.stdout.write(',')
        sys.stdout.write('\n')

    sys.stdout.write(trailing_comments)

    if trailing_comments and not trailing_comments.endswith('\n'):
        sys.stdout.write('\n')

    postamble_trimmed = re.sub(r'^[ \t\r\n]+|[ \t\r\n]+$', '', postamble)
    if postamble_trimmed:
        sys.stdout.write(']\n' + postamble_trimmed + '\n')
    else:
        sys.stdout.write(']\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
