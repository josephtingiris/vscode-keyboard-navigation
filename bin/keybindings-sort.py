#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Sort and canonicalize VS Code keybindings.json (JSONC) while preserving comments.

Usage

```
keybindings-sort.py [OPTIONS]

# read from stdin and write sorted JSONC to stdout
cat keybindings.json | keybindings-sort.py > keybindings.sorted.json
```

Options

- `-h, --help` — show help and exit.
- `--primary, -p` — primary sort field (`key` or `when`).
- `--secondary, -s` — optional secondary sort field.
- `--when-grouping, -w` — grouping mode (`none`, `config-first`, `focal-invariant`).
- `--group-sorting, -g` — how to sort tokens inside a when-group (alpha, natural, positive, negative, ...).
- `--color, -c` — control ANSI coloring of debug output: `auto` (default), `always`, `never`.
- `--debug, -d` — repeatable flag to enable debug output and supply filters. Values may be a numeric level (e.g. `3`), `when=EXPR`, or `target=NAME`/`category=NAME`.

Examples

- Minimal: `cat keybindings.json | keybindings-sort.py`
- With grouping: `cat keybindings.json | keybindings-sort.py -w focal-invariant -p when -s key`
- Enable debug level 2 for canonicalization: `--debug 2 --debug target=canonicalize`

Behavior

- Memoizes canonicalization results to improve performance.
- Parses and canonicalizes `when` expressions into an internal AST.
- Attempts to preserve comments and trailing commas in the original JSONC input.
- Deduplicates operands, groups tokens by semantic buckets, and re-renders a stable canonical `when` form.
- Debug messages are written to stderr via `debug_echo(...)` and are controlled by `--debug` and `--color`.

Inputs / outputs

- stdin: JSONC text containing a top-level array of keybinding objects.
- stdout: sorted JSONC text (UTF-8) with formatting and comments preserved where feasible.

Important notes

- Requires Python 3.10 or newer (uses modern typing syntax).
- Canonicalization is the primary CPU hotspot; memoization significantly reduces repeated work for identical `when` strings.

Exit codes

```
0   Success
1   Usage / bad args
2   File read/write or other runtime error
```
"""
import sys
import os
import re
import json
import argparse
from typing import List, Tuple

# global memoization cache for canonicalized when results
CACHE_CANONICALIZE_WHEN: dict = {}

# global memoization object cache for parsed JSON objects (key: raw object string including braces)
CACHE_JSON_OBJECT: dict = {}

# global memoization cache for sortable when keys (key: when string, value: sortable key)
CACHE_SORTABLE_WHEN: dict = {}

# global memoization cache for when specificity (key: when string, value: specificity tuple)
CACHE_WHEN_SPECIFICITY: dict = {}

# global memoization cache for natural keys (key: string, value: list of string and int parts)
CACHE_NATURAL_KEY: dict = {}

# global memoization cache for case-sensitive natural keys (key: string, value: list of string and int parts)
CACHE_NATURAL_KEY_CS: dict = {}

# color default output value, options: 'auto'|'always'|'never'
COLOR: str = 'auto'

# debug defaults
DEBUG_LEVEL: int = 0  # off
DEBUG_TARGET_CATEGORY: str | None = None  # set vial --debug target=['when', 'ordered', 'canonicalize', ...]
DEBUG_TARGET_WHEN: str = ""  # set via --debug when=

# default when prefixes to be added to standard output, if none are given via the cli
DEFAULT_WHEN_PREFIXES = []

#
# global token groups used for heuristics
#

FOCUS_TOKENS = [
    # primary (order matters!)
    'auxiliaryBarFocus',
    'editorFocus',
    'panelFocus',
    'sideBarFocus',
    'terminalFocus',
    # secondary
    'agentSessionsViewerFocused',
    'editorTextFocus',
    'inputFocus',
    'listFocus',
    'notificationFocus',
    'textInputFocus',
]

POSITIONAL_TOKENS = [
    # primary (order matters!)
    'config.workbench.activityBar.location',
    'config.workbench.sideBar.location',
    'panel.location',
    'panelPosition',
    # secondary
    'activeAuxiliary',
    'activeEditor',
    'activePanel',
    'activeViewlet',
    'focusedView',
]

VISIBILITY_TOKENS = [
    'auxiliaryBarVisible',
    'agentSessionsViewerVisible',
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
]

# precomputed token ordering maps for performance
FOCUS_TOKENS_MAP = {t: i for i, t in enumerate(FOCUS_TOKENS)}
POSITIONAL_TOKENS_MAP = {t: i for i, t in enumerate(POSITIONAL_TOKENS)}
VISIBILITY_TOKENS_MAP = {t: i for i, t in enumerate(VISIBILITY_TOKENS)}

# profile defaults for `--when-grouping` values; arg values always override these
WHEN_GROUPING_PROFILES = {
    'focal-invariant': {
        'primary': 'when',
        'secondary': 'key',
        'group_sorting': 'positive',
        'when_prefix': 'config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters'
    },
    'config-first': {
        # example defaults for config-first
        'primary': 'key',
        'secondary': 'when',
        'group_sorting': 'alpha',
        'when_prefix': None,
    }
}

# precompiled regexes for performance
COMMENT_RE = re.compile(r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)', re.DOTALL | re.MULTILINE)
TRAILING_COMMA_RE = re.compile(r',\s*([}\]])')
NUMBER_SPLIT_RE = re.compile(r'(\d+)')
WHEN_TERM_SPLIT_RE = re.compile(r'\s*&&\s*|\s*\|\|\s*')
OBJ_RE = re.compile(r'\{.*\}', re.DOTALL)
WHEN_LITERAL_RE = re.compile(r'("when"\s*:\s*\")((?:\\.|[^"\\])*)(\")')
KEY_EXTRACT_RE = re.compile(r'"key"\s*:\s*"((?:\\.|[^"\\])*)"')
WHEN_EXTRACT_RE = re.compile(r'"when"\s*:\s*"((?:\\.|[^"\\])*)"')
WHITESPACE_RE = re.compile(r'\s+')
WHEN_SORTED_RE = re.compile(r'^\s*//\s*when-sorted:.*\n', re.MULTILINE)
BLANK_LINES_RE = re.compile(r'(?m)^[ \t]*\n+')
LEADING_COMMA_RE = re.compile(r'^\s*,+')
STRIP_WS_RE = re.compile(r'^[ \t\r\n]+|[ \t\r\n]+$')
LEADING_NEWLINES_RE = re.compile(r'^\n+')


class WhenNode:
    def __init__(self, parens: bool = False):
        self.parens = parens

    def to_str(self) -> str:
        raise NotImplementedError


class WhenAnd(WhenNode):
    def __init__(self, children, parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def to_str(self) -> str:
        parts: list[str] = []
        for c in self.children:
            s = render_when_node(c)
            # when an OR appears as an operand of an AND, it must be parenthesized
            if isinstance(c, WhenOr):
                s = f'({s})'
            parts.append(s)
        return ' && '.join(parts)


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


class WhenOr(WhenNode):
    def __init__(self, children, parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def to_str(self) -> str:
        parts: list[str] = []
        for c in self.children:
            s = render_when_node(c)
            # when an AND appears as an operand of an OR, it must be parenthesized
            if isinstance(c, WhenAnd):
                s = f'({s})'
            parts.append(s)
        return ' || '.join(parts)


def _apply_debug_settings(debug_specs: list[str] | None, color: str) -> None:
    global DEBUG_LEVEL, DEBUG_TARGET_WHEN, DEBUG_TARGET_CATEGORY, COLOR

    COLOR = color
    DEBUG_LEVEL = 0
    DEBUG_TARGET_WHEN = ''
    DEBUG_TARGET_CATEGORY = None

    if not debug_specs:
        return

    max_level = 0
    for spec in debug_specs:
        if spec is None:
            spec = '1'
        spec = str(spec).strip()

        if re.fullmatch(r'\d+', spec):
            max_level = max(max_level, int(spec))
            continue

        if '=' in spec:
            key, value = spec.split('=', 1)
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")
            if key == 'when':
                DEBUG_TARGET_WHEN = value
            elif key in ('target', 'category'):
                DEBUG_TARGET_CATEGORY = value
            elif key == 'level' and re.fullmatch(r'\d+', value):
                max_level = max(max_level, int(value))

    if max_level == 0:
        max_level = 1
    DEBUG_LEVEL = max_level


def _apply_when_grouping_profile(args: argparse.Namespace, raw_argv: list[str]) -> None:
    sel_profile = args.when_grouping
    if sel_profile not in WHEN_GROUPING_PROFILES:
        return

    profile = WHEN_GROUPING_PROFILES[sel_profile]

    if not _flag_present(raw_argv, ['-p', '--primary']) and profile.get('primary') is not None:
        args.primary = profile['primary']

    if not _flag_present(raw_argv, ['-s', '--secondary']):
        args.secondary = profile.get('secondary')

    if not _flag_present(raw_argv, ['-g', '--group-sorting']) and profile.get('group_sorting') is not None:
        args.group_sorting = profile['group_sorting']

    if not _flag_present(raw_argv, ['-P', '--when-prefix']):
        args.when_prefix = profile.get('when_prefix')


def _assemble_sorted_output(
    preamble: str,
    sorted_groups: list[tuple[str, str]],
    trailing_comments: str,
    postamble: str,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    out_parts: list[str] = []
    out_parts.append(preamble)
    out_parts.append('[\n')

    seen_pairs: dict[tuple[str, str], set[str]] = {}
    for i, (comments, obj) in enumerate(sorted_groups):
        is_last = (i == len(sorted_groups) - 1)
        obj_out = obj.rstrip()

        try:
            obj_out, _ = normalize_when_in_object(
                obj_out,
                mode=grouping_mode,
                negation_mode=negation_mode,
                when_prefixes=when_prefixes,
                when_regexes=when_regexes,
            )
        except Exception:
            pass

        obj_out = obj_out.rstrip()
        key_val, when_val = extract_key_when(obj_out)
        canonical_when = canonicalize_when(
            when_val,
            mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        pair_id = (key_val, canonical_when)
        if key_val or canonical_when:
            idx_r = obj_out.rfind('}')
            if idx_r != -1:
                obj_fingerprint = obj_out[:idx_r + 1].strip()
            else:
                obj_fingerprint = obj_out.strip()
            seen_fingerprints = seen_pairs.get(pair_id)
            if seen_fingerprints is None:
                seen_pairs[pair_id] = {obj_fingerprint}
            else:
                duplicate_comment = f'// DUPLICATE key: {key_val!r} when: {canonical_when!r}'
                if obj_fingerprint in seen_fingerprints:
                    duplicate_comment += ' (exact object match)'
                obj_out = _embed_duplicate_comment_in_object(obj_out, duplicate_comment)
                seen_fingerprints.add(obj_fingerprint)

        if comments:
            comments = BLANK_LINES_RE.sub('', comments)
            out_parts.append(comments)

        idx = obj_out.rfind('}')
        if idx != -1:
            after = obj_out[idx + 1:]
            after_clean = LEADING_COMMA_RE.sub('', after)
            obj_out = obj_out[:idx + 1] + after_clean

        out_parts.append(obj_out)
        if not is_last and not object_has_trailing_comma(obj_out):
            out_parts.append(',')
        out_parts.append('\n')

    out_parts.append(trailing_comments)
    if trailing_comments and not trailing_comments.endswith('\n'):
        out_parts.append('\n')

    postamble_trimmed = STRIP_WS_RE.sub('', postamble)
    if postamble_trimmed:
        out_parts.append(']\n' + postamble_trimmed + '\n')
    else:
        out_parts.append(']\n')

    return ''.join(out_parts)


def _color_enabled() -> bool:
    if COLOR == 'never':
        return False
    if COLOR == 'always':
        return True
    try:
        # auto (default)
        return sys.stderr.isatty()
    except Exception:
        return False


def _contains_focus_token_in_object(obj_text: str) -> bool:
    when_key, when_val = extract_key_when(obj_text)
    raw = when_val

    if not raw:
        raw = _extract_literal_when_from_object(obj_text)

    if not raw:
        return False

    parts = re.split(r'\s*&&\s*|\s*\|\|\s*', raw)
    for part in parts:
        token = part.strip()
        while token.startswith('(') and token.endswith(')'):
            token = token[1:-1].strip()
        if not token:
            continue

        left = token[1:].lstrip() if token.startswith('!') else token
        left_id = left.split()[0] if left else ''
        if any(_matches_when_entry(left_id, entry) for entry in FOCUS_TOKENS):
            return True

    return False


def _decode_json_string_literal(raw: str) -> str:
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        try:
            return bytes(raw, 'utf-8').decode('unicode_escape')
        except Exception:
            return raw


def _embed_duplicate_comment_in_object(obj_text: str, duplicate_comment: str) -> str:
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


def _extract_literal_key_from_object(obj_text: str) -> str:
    match = re.search(r'"key"\s*:\s*"((?:\\.|[^"\\])*)"', obj_text)
    if not match:
        return ''
    return _decode_json_string_literal(match.group(1))


def _extract_literal_when_from_object(obj_text: str) -> str:
    match = re.search(r'"when"\s*:\s*"((?:\\.|[^"\\])*)"', obj_text)
    if not match:
        return ''
    return _decode_json_string_literal(match.group(1))


def _finalize_processed_output(
    text: str,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    processed = _remove_blank_lines(text)
    processed = _replace_when_literals(
        processed,
        grouping_mode,
        negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    try:
        processed = _reorder_processed_by_when(processed, negation_mode)
    except Exception:
        pass

    return processed


def _first_when_group_rank(
    obj_text: str,
    mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> int:
    when_key, when_val = extract_key_when(obj_text)
    canonical = canonicalize_when(
        when_val,
        mode=mode,
        negation_mode=negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    if not canonical:
        return 5

    parts = re.split(r'\s*&&\s*|\s*\|\|\s*', canonical.strip())
    if not parts:
        return 5

    first = parts[0].strip()
    while first.startswith('(') and first.endswith(')'):
        first = first[1:-1].strip()

    left = first[1:].lstrip() if first.startswith('!') else first
    if not left:
        return 5

    left_id = left.split()[0]

    if mode == 'focal-invariant':
        if any(_matches_when_entry(left_id, entry) for entry in FOCUS_TOKENS):
            return 1
        if any(_matches_when_entry(left_id, entry) for entry in VISIBILITY_TOKENS):
            return 2
        if any(left_id.startswith(prefix) for prefix in POSITIONAL_TOKENS):
            return 3
        if left_id.startswith('config.'):
            return 4
        return 5

    if left_id.startswith('config.'):
        return 1
    if any(left_id.startswith(prefix) for prefix in POSITIONAL_TOKENS):
        return 2
    if any(_matches_when_entry(left_id, entry) for entry in FOCUS_TOKENS):
        return 3
    if any(_matches_when_entry(left_id, entry) for entry in VISIBILITY_TOKENS):
        return 4
    return 5


def _flag_present(raw_argv: list[str], names: list[str]) -> bool:
    for name in names:
        if name in raw_argv:
            return True
    return False


def _matches_when_entry(left: str, entry: str) -> bool:
    if entry.endswith('.'):
        return left.startswith(entry)
    if '<viewId>' in entry:
        prefix, suffix = entry.split('<viewId>', 1)
        return left.startswith(prefix) and left.endswith(suffix)
    return left == entry


def _normalize_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(' ', text).strip() if text else ''


def _parse_when_prefixes(parser: argparse.ArgumentParser, raw_prefixes: str | None) -> list[str]:
    if raw_prefixes is not None:
        if raw_prefixes.strip() == '':
            parser.error('--when-prefix requires a comma-separated list with at least one entry')
        when_prefixes = [part.strip() for part in raw_prefixes.split(',') if part.strip()]
        if not when_prefixes:
            parser.error('--when-prefix requires a comma-separated list with at least one entry')
        return when_prefixes

    return DEFAULT_WHEN_PREFIXES.copy()


def _parse_when_regexes(parser: argparse.ArgumentParser, raw_regexes: str | None):
    if not raw_regexes:
        return None

    parts = [part.strip() for part in raw_regexes.split(',') if part.strip()]
    if not parts:
        parser.error('--when-regex requires a comma-separated list with at least one entry')

    compiled = []
    for part in parts:
        try:
            compiled.append(re.compile(part))
        except Exception:
            compiled.append(part)
    return compiled


def _partition_focus_groups_to_end(sorted_groups: list[tuple[str, str]]) -> list[tuple[str, str]]:
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


def _reorder_processed_by_when(processed_text: str, negation_mode: str) -> str:
    preamble, array_text, postamble = extract_preamble_postamble(processed_text)
    if array_text is None:
        return processed_text

    groups_list, trailing = group_objects_with_comments(array_text)

    i = 0
    while i < len(groups_list):
        raw_when = _extract_literal_when_from_object(groups_list[i][1]) or ''
        norm_when = _normalize_whitespace(raw_when)
        j = i + 1

        while j < len(groups_list):
            next_when = _extract_literal_when_from_object(groups_list[j][1]) or ''
            if _normalize_whitespace(next_when) != norm_when:
                break
            j += 1

        if j - i > 1 and negation_mode not in ('positive', 'negative'):
            slice_pairs = groups_list[i:j]
            slice_pairs.sort(key=lambda pair: natural_key_case_sensitive(_extract_literal_key_from_object(pair[1])))
            groups_list[i:j] = slice_pairs

        i = j

    out: list[str] = []
    for idx, (comments, obj) in enumerate(groups_list):
        is_last = idx == len(groups_list) - 1
        obj_out = obj

        idx_r = obj_out.rfind('}')
        if idx_r != -1:
            after = obj_out[idx_r + 1:]
            after_clean = LEADING_COMMA_RE.sub('', after)
            after_clean = after_clean.lstrip()
            obj_out = (obj_out[:idx_r + 1] + after_clean).rstrip()

        if comments:
            comments = BLANK_LINES_RE.sub('', comments)
            out.append(comments)

        line = obj_out.rstrip()
        if not is_last and not object_has_trailing_comma(obj_out):
            line += ','
        out.append(line + '\n')

    out.append(trailing)
    new_array = ''.join(out)
    new_array = LEADING_NEWLINES_RE.sub('', new_array)

    return preamble + '[\n' + new_array + ']' + postamble


def _replace_when_literal_match(
    match,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    inner = match.group(2)

    try:
        unescaped = json.loads('"' + inner + '"')
    except Exception:
        unescaped = inner

    canonical = canonicalize_when(
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


def _sort_groups_for_primary_when(
    sorted_groups: list[tuple[str, str]],
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> list[tuple[str, str]]:
    decorated: list[tuple[str, str, tuple[str, str]]] = []
    for pair in sorted_groups:
        key_val, when_val = extract_key_when(pair[1])
        if not key_val:
            key_val = _extract_literal_key_from_object(pair[1])
        if not when_val:
            when_val = _extract_literal_when_from_object(pair[1])
        decorated.append((key_val, when_val, pair))

    for key_val, when_val, _pair in decorated:
        try:
            canonical = canonicalize_when(
                when_val,
                mode=grouping_mode,
                negation_mode=negation_mode,
                when_prefixes=when_prefixes,
                when_regexes=when_regexes,
            )
        except Exception:
            canonical = when_val

        if DEBUG_LEVEL > 0:
            normalized = normalize_key_for_compare(key_val)
            try:
                natural = natural_key(normalized)
            except Exception:
                natural = normalized
            debug_echo(
                2,
                'sort',
                when_val,
                f"DEBUG_SORT: raw_key={key_val!r} normalized={normalized!r} natural_key={natural!r} when_raw={when_val!r} when_canonical={canonical!r}",
            )

    decorated.sort(
        key=lambda row: (
            canonicalize_when(
                row[1],
                mode=grouping_mode,
                negation_mode=negation_mode,
                when_prefixes=when_prefixes,
                when_regexes=when_regexes,
            ),
            row[1],
            natural_key_case_sensitive(row[0]),
        )
    )

    if grouping_mode == 'focal-invariant':
        non_focus_rows = []
        focus_rows = []
        for row in decorated:
            when_val = row[1] or ''
            try:
                parts = re.split(r'\s*&&\s*|\s*\|\|\s*', when_val.strip()) if when_val else []
                found_focus = False
                for part in parts:
                    token = part.strip()
                    while token.startswith('(') and token.endswith(')'):
                        token = token[1:-1].strip()
                    if not token:
                        continue

                    left = token[1:].lstrip() if token.startswith('!') else token
                    left_id = left.split()[0] if left else ''
                    if any(_matches_when_entry(left_id, entry) for entry in FOCUS_TOKENS):
                        found_focus = True
                        break

                if found_focus:
                    focus_rows.append(row)
                else:
                    non_focus_rows.append(row)
            except Exception:
                non_focus_rows.append(row)
        decorated = non_focus_rows + focus_rows

    sorted_groups = [row[2] for row in decorated]

    for idx, pair in enumerate(sorted_groups):
        key_val, when_val = extract_key_when(pair[1])
        try:
            canonical = canonicalize_when(
                when_val,
                mode=grouping_mode,
                negation_mode=negation_mode,
                when_prefixes=when_prefixes,
                when_regexes=when_regexes,
            )
        except Exception:
            canonical = when_val

        if DEBUG_LEVEL > 0:
            normalized = normalize_key_for_compare(key_val)
            debug_echo(1, 'ordered', canonical, f"DEBUG_ORDERED: idx={idx} raw_key={key_val!r} normalized={normalized!r}")

    i = 0
    while i < len(sorted_groups):
        _, raw_when = extract_key_when(sorted_groups[i][1])
        if not raw_when:
            raw_when = _extract_literal_when_from_object(sorted_groups[i][1])

        normalized_when = _normalize_whitespace(raw_when)
        j = i + 1
        while j < len(sorted_groups):
            _, next_when = extract_key_when(sorted_groups[j][1])
            if not next_when:
                next_when = _extract_literal_when_from_object(sorted_groups[j][1])
            if _normalize_whitespace(next_when) != normalized_when:
                break
            j += 1

        if j - i > 1 and negation_mode not in ('positive', 'negative'):
            slice_pairs = sorted_groups[i:j]
            slice_pairs.sort(key=lambda pair: natural_key_case_sensitive(_extract_literal_key_from_object(pair[1])))
            sorted_groups[i:j] = slice_pairs

        i = j

    return sorted_groups


def _sort_groups_initial(
    normalized_groups: list[tuple[str, str]],
    primary_order: str,
    secondary_order: str | None,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> list[tuple[str, str]]:
    return sorted(
        normalized_groups,
        key=lambda pair: extract_sort_keys(
            pair[1],
            primary=primary_order,
            secondary=secondary_order,
            grouping=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        ),
    )


def _sort_groups_with_grouping_mode(
    sorted_groups: list[tuple[str, str]],
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> list[tuple[str, str]]:
    if grouping_mode == 'none':
        return sorted_groups

    buckets: dict[int, list[tuple[str, str]]] = {}
    for pair in sorted_groups:
        rank = _first_when_group_rank(
            pair[1],
            grouping_mode,
            negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        buckets.setdefault(rank, []).append(pair)

    final_groups: list[tuple[str, str]] = []
    for rank in sorted(buckets.keys(), reverse=True):
        final_groups.extend(buckets[rank])
    return final_groups


def _strip_when_sorted_comment(comment_text: str, when_changed: bool) -> str:
    if not when_changed:
        return comment_text
    return WHEN_SORTED_RE.sub('', comment_text)


def _with_normalized_when_groups(
    groups: list[tuple[str, str]],
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> list[tuple[str, str]]:
    normalized_groups: list[tuple[str, str]] = []
    for comments, obj in groups:
        obj_out = obj.rstrip()
        obj_out, when_changed = normalize_when_in_object(
            obj_out,
            mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        comments = _strip_when_sorted_comment(comments, when_changed)
        normalized_groups.append((comments, obj_out))
    return normalized_groups


def canonicalize_when(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
    """Produce a canonical string for a `when` clause.

    Sort operands inside every AND node according to project conventions.
    Preserves OR groupings and existing parentheses; does not reorder OR-level operands.
    """
    if not when_val:
        return ''

    # memoization: avoid repeated expensive parsing of identical inputs
    cache_key = (
        when_val,
        mode,
        negation_mode,
        None if when_prefixes is None else tuple(when_prefixes),
        None if when_regexes is None else tuple(when_regexes),
    )

    # key: (when_val, mode, negation_mode, when_prefixes_tuple_or_None, when_regexes_tuple_or_None)
    cached = CACHE_CANONICALIZE_WHEN.get(cache_key)

    if cached is not None:
        return cached
    """
        TBD: these need to be better tested before being fully integrated, especially with the focal-invariant mode:
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
                    # if a string pattern was provided that wasn't compiled, fall back to a simple substring match
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

        # compute left identifier and a combined sub-rank preference
        left_id = left_identifier(token)

        # prefer focus_order, then positional_order, then visibility_order
        sub_rank = FOCUS_TOKENS_MAP.get(left_id, POSITIONAL_TOKENS_MAP.get(left_id, VISIBILITY_TOKENS_MAP.get(left_id, 9999)))

        # default alpha behavior: preserve group_rank and use natural-sensitive ordering
        if negation_mode == 'alpha':
            return (group_rank(token), sub_rank, natural_key_case_sensitive(order_token), idx)

        return (group_rank(token), natural_key_case_sensitive(order_token), idx)

    def sort_and_nodes(node: WhenNode):
        if isinstance(node, WhenAnd):
            for child in node.children:
                sort_and_nodes(child)
            indexed = list(enumerate(node.children))

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
                    for idx, child in indexed:
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
                        matches.sort(key=lambda t: natural_key_case_sensitive(
                            render_when_node(t[1])))
                        for m in matches:
                            prioritized.append(m[1])
                            picked.add(m[0])

            if negation_mode == 'beta':
                # alias: 'beta' points to positive-natural
                nm = 'positive-natural'
            else:
                nm = negation_mode

            if negation_mode == 'alpha':
                # use existing group-aware sort_key
                indexed.sort(key=sort_key)
                sorted_children = [it[1] for it in indexed]
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
                for idx, child in indexed:
                    base, is_neg, tok = render_base_and_flag(child)

                    # natural-style comparison: use natural_key (case-insensitive)
                    base_key = natural_key(base)

                    # always preserve grouping as the primary key so sorting does not move operands between buckets.
                    grp = group_rank(tok)

                    # compute a combined sub-rank if this token belongs to a known ordered identifier
                    lid = _left_id_of(child)
                    f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))

                    # natural mode: ignore negation and sort by group then base_key
                    if nm == 'natural':
                        items_with_keys.append(
                            (idx, child, (grp, f_rank, base_key, idx, tok)))
                        continue

                    # positive-natural / negative-natural: existing "alpha/natural"-style
                    if nm == 'positive-natural':
                        neg_sort = 0 if not is_neg else 1
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key, idx, tok)))
                        continue

                    if nm == 'negative-natural':
                        neg_sort = 0 if is_neg else 1
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key, idx, tok)))
                        continue

                    # positive / negative: preserve original list order within positive/negative groups
                    if nm == 'positive':
                        neg_sort = 0 if not is_neg else 1
                        # use token-list ordering (focus/positional/visibility) as sub-rank
                        f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))
                        base_key_cs = natural_key_case_sensitive(base)
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key_cs, idx, tok)))
                        continue

                    if nm == 'negative':
                        neg_sort = 0 if is_neg else 1
                        f_rank = FOCUS_TOKENS_MAP.get(lid, POSITIONAL_TOKENS_MAP.get(lid, VISIBILITY_TOKENS_MAP.get(lid, 9999)))
                        base_key_cs = natural_key_case_sensitive(base)
                        items_with_keys.append((idx, child, (grp, neg_sort, f_rank, base_key_cs, idx, tok)))
                        continue

                    # default fallback
                    neg_sort = 0
                    items_with_keys.append((idx, child, (grp, neg_sort, base_key, idx, tok)))

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
            # recurse first
            for child in node.children:
                sort_and_nodes(child)

            # flatten nested ORs (commutative) and collect items
            items: list[WhenNode] = []
            for c in node.children:
                if isinstance(c, WhenOr):
                    items.extend(c.children)
                else:
                    items.append(c)

            # sort OR operands deterministically so equivalent ASTs render the same
            indexed = list(enumerate(items))
            indexed.sort(key=lambda it: (natural_key_case_sensitive(render_when_node(it[1])), it[0]))
            sorted_children = [it[1] for it in indexed]

            # remove duplicates while preserving sorted order
            unique: list[WhenNode] = []
            seen = set()
            for c in sorted_children:
                tok = render_when_node(c)
                if tok in seen:
                    continue
                seen.add(tok)
                unique.append(c)
            node.children = unique
        elif isinstance(node, WhenNot):
            sort_and_nodes(node.child)

    ast = parse_when(when_val)
    try:
        # debug: dump top-level AND operand ordering before/after sort for inspection
        if DEBUG_LEVEL > 0:
            if isinstance(ast, WhenAnd):
                for i, c in enumerate(ast.children):
                    try:
                        tok = render_when_node(c)
                    except Exception:
                        tok = str(c)
                    debug_echo(2, 'canonicalize', when_val, f"DBG_CANON_PRE: idx={i} token={tok!r}")
            else:
                try:
                    debug_echo(2, 'canonicalize', when_val, f"DBG_CANON_PRE: node={render_when_node(ast)!r}")
                except Exception:
                    debug_echo(2, 'canonicalize', when_val, f"DBG_CANON_PRE: node={ast!r}")
    except Exception:
        pass

    sort_and_nodes(ast)

    try:
        if DEBUG_LEVEL > 0:
            if isinstance(ast, WhenAnd):
                for i, c in enumerate(ast.children):
                    try:
                        tok = render_when_node(c)
                    except Exception:
                        tok = str(c)
                    debug_echo(2, 'canonicalize', when_val, f"DBG_CANON_POST: idx={i} token={tok!r}")
            else:
                try:
                    debug_echo(2, 'canonicalize', when_val, f"DBG_CANON_POST: node={render_when_node(ast)!r}")
                except Exception:
                    debug_echo(2, 'canonicalize', when_val, f"DBG_CANON_POST: node={ast!r}")
    except Exception:
        pass

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

    _clear_parens(ast)
    result = render_when_node(ast)

    try:
        CACHE_CANONICALIZE_WHEN[cache_key] = result
    except Exception:
        pass

    return result


def debug_color(text: str, level: int) -> str:
    if not _color_enabled():
        return text

    # simple level -> color mapping
    colors = {
        1: '\x1b[33m',
        2: '\x1b[36m',
        3: '\x1b[35m',
        4: '\x1b[34m',
    }

    code = colors.get(level, '\x1b[37m')
    return f"{code}{text}\x1b[0m"


def debug_echo(level: int, category: str, when_val: str | None, msg: str) -> None:
    """Emit a filtered, leveled debug message to stderr.

    Messages are emitted when `level` <= `DEBUG_LEVEL` and category/when
    filters (if set) match. Always writes to stderr.
    """
    if DEBUG_LEVEL <= 0:
        return
    if level > DEBUG_LEVEL:
        return
    if DEBUG_TARGET_CATEGORY and DEBUG_TARGET_CATEGORY != 'all' and category != DEBUG_TARGET_CATEGORY:
        return
    if DEBUG_TARGET_WHEN:
        if not when_val:
            return
        if when_val != DEBUG_TARGET_WHEN:
            return
    out = f"[DEBUG:{level}:{category}] {msg}"
    out = debug_color(out, level)
    try:
        sys.stderr.write(out + '\n')
    except Exception:
        pass


def extract_key_when(obj_text: str) -> Tuple[str, str]:
    parsed = parse_object_text(obj_text)
    if not parsed:
        return ('', '')
    try:
        key_val = str(parsed.get('key', ''))
        when_val = str(parsed.get('when', ''))
        return (key_val, when_val)
    except Exception:
        return ('', '')


def extract_preamble_postamble(text):
    """Find the top-level JSON array brackets.

    Skip any brackets that appear inside comments or strings in the preamble/postamble.
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
        next2 = text[i:i + 2] if i + 2 <= n else ''

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
        next2 = text[i:i + 2] if i + 2 <= n else ''

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
    postamble = text[end + 1:]
    array_text = text[start + 1:end]  # exclude [ and ]
    return preamble, array_text, postamble


def extract_sort_keys(obj_text: str, primary: str = 'key', secondary: str | None = None, grouping: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> Tuple:
    parsed = parse_object_text(obj_text)
    if not parsed:
        # return a consistent fallback sort key (rank high so these sort last)
        return (9999, [], (0,), [])
    try:
        key_val = str(parsed.get('key', ''))
        when_val = str(parsed.get('when', ''))
        canonical_when = canonicalize_when(
            when_val, mode=grouping, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)
        sortable_when = sortable_when_key(
            when_val, mode=grouping, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)

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

        # special-case: when primary is key and secondary is when, ensure strict key-first ordering by returning a simple tuple: (rank, key, when_specificity, when_sortable)
        if primary == 'key' and secondary == 'when':
            norm = normalize_key_for_compare(key_val)
            key_token = natural_key(norm)
            spec = when_specificity(when_val)
            when_token = natural_key_case_sensitive(sortable_when)
            return (0, key_token, spec, when_token)

        tokens = []

        def append_when():
            if primary == 'when':
                first_key = natural_key_case_sensitive(first_when_token)

                # compute an optional priority rank based on given when_prefixes
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
                    grouping = natural_key_case_sensitive(sortable_when)
                elif negation_mode == 'natural':
                    base = sortable_when.lstrip('!')
                    grouping = natural_key(base)
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
                        grouping = (is_neg, f_rank, natural_key_case_sensitive(base))
                    else:
                        grouping = (is_neg, natural_key(base))
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
                        grouping = (is_neg, f_rank, natural_key_case_sensitive(base))
                    else:
                        grouping = (is_neg, natural_key(base))
                else:
                    grouping = natural_key_case_sensitive(sortable_when)

                # this makes matched groups easier to inspect
                if match_rank != 9999:
                    # prefer normalized key ordering for stability: modifiers normalized
                    norm_key = normalize_key_for_compare(key_val)
                    tokens.append(natural_key(norm_key))
                    tokens.append(spec_key)
                    tokens.append(grouping)
                else:
                    # default behavior: include first_when token so grouping remains primary, then specificity and grouping ordering
                    tokens.append(first_key)
                    tokens.append(spec_key)
                    tokens.append(grouping)
                return

            tokens.append(when_specificity(when_val))
            tokens.append(natural_key_case_sensitive(sortable_when))

        def append_key():
            # use normalized key comparison (consistent modifier ordering)
            norm = normalize_key_for_compare(key_val)
            tokens.append(natural_key(norm))

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


def natural_key(s):
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


def natural_key_case_sensitive(s):
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


def normalize_key_for_compare(key_value):
    """Lightweight normalization for key sorting.

    Lowercases, splits chord parts on spaces, orders modifiers alphabetically
    before the literal, and rejoins chords with spaces.
    """
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


def normalize_operand(text: str) -> str:
    collapsed = WHITESPACE_RE.sub(' ', text).strip()
    return collapsed


def normalize_when_in_object(obj_text: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> Tuple[str, bool]:
    parsed = parse_object_text(obj_text)
    if not parsed:
        return obj_text, False

    when_val = parsed.get('when')
    if not when_val:
        return obj_text, False

    normalized = canonicalize_when(
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


def parse_object_text(obj_text: str):
    """Parse an object text (including braces) into a dict and cache the result.

    Returns the parsed dict or None on failure.
    """
    if not obj_text:
        return None

    # use the raw object string (including comments) as cache key
    m = OBJ_RE.search(obj_text)
    if not m:
        return None

    obj_str = m.group(0)
    cached = CACHE_JSON_OBJECT.get(obj_str)

    if cached is not None:
        return cached

    try:
        clean = strip_json_comments(obj_str)
        clean = strip_trailing_commas(clean)
        parsed = json.loads(clean)
        CACHE_JSON_OBJECT[obj_str] = parsed
        return parsed
    except Exception:
        return None


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


def render_when_node(node: WhenNode) -> str:
    inner = node.to_str()
    if node.parens:
        return f'({inner})'
    return inner


def sortable_when_key(when_val: str, mode: str = 'config-first', negation_mode: str = 'alpha', when_prefixes: list | None = None, when_regexes: list | None = None) -> str:
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

    # preserve negation for stable sorting
    when = canonicalize_when(when_val, mode=mode, negation_mode=negation_mode, when_prefixes=when_prefixes, when_regexes=when_regexes)

    try:
        CACHE_SORTABLE_WHEN[cache_key] = when
    except Exception:
        pass

    return when


def strip_json_comments(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ''
        return s
    return COMMENT_RE.sub(replacer, text)


def strip_trailing_commas(text):
    text = TRAILING_COMMA_RE.sub(r'\1', text)
    return text


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
            tokens.append(('OP', expr[i:i + 2]))
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
            nxt = expr[i + 1] if i + 1 < n else ''
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


def when_specificity(when_val: str) -> Tuple[int]:
    """Heuristic specificity scorer for a when clause. Lower is broader.

    Returns a tuple to sort stably by:
        1) number of condition terms (split on && / ||)
    """
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

#
# main
#


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    parser = argparse.ArgumentParser(
        description='Sort VS Code `keybindings.json` (JSONC) while preserving comments.',
        epilog="Example: cat keybindings.json | %(prog)s --primary when"
    )

    parser.add_argument('--primary', '-p', choices=['key', 'when'], default='key',
                        help="Primary sort field (default: key).")

    parser.add_argument('--secondary', '-s', choices=['key', 'when'], default=None,
                        help="Secondary sort field (default: none)")

    parser.add_argument('--group-sorting', '-g', dest='group_sorting',
                        choices=['alpha', 'beta', 'natural', 'positive-natural', 'negative-natural', 'positive', 'negative'], default='alpha',
                        help="Group sorting mode: pre-defined ording algorithms for when clauses (default: alpha)")

    parser.add_argument('--when-grouping', '-w', dest='when_grouping',
                        choices=['none', 'config-first', 'focal-invariant'], default='none',
                        help="When grouping mode: pre-defined final sort algorithms for explicit use cases (default: none)")

    parser.add_argument('--when-prefix', '-P', dest='when_prefix', default=None,
                        help="Comma-separated list of when prefixes to match and move to the front of the when clause (exact match).")

    parser.add_argument('--when-regex', '-R', dest='when_regex', default=None,
                        help="Comma-separated list of regular expressions to match and move to the front of the when clause (order matters).")

    parser.add_argument('--color', '-c', dest='color', choices=['auto', 'always', 'never'], default='auto',
                        help='Colorize output (auto|always|never)')

    #
    # debug: flexible single flag. each --debug may optionally take a single value
    #
    # --debug <values>:
    #
    #   - a positive integer: sets/updates the debug level (higher = more verbose)
    #   - key=value: e.g. when=EXPR, target=NAME, level=N
    #
    # Use multiple --debug flags to combine filters and levels.
    #
    # Examples:
    #   `--debug` # enable debug level 1 (default)
    #   `--debug 3` # enable debug level 3
    #   `--debug when=panelFocus` # enable debug level 1 and filter when
    #   `--debug when="a && b" --debug level=3` # enable debug level 3 and filter when
    #
    # Notes:
    #   - Use multiple --debug flags to combine filters and levels, i.e. `--debug when-panelFocus --debug 3`
    #   - The following is NOT supported and will be parsed incorrectly: `--debug when=panelFocus 3`

    parser.add_argument('--debug', '-d', nargs='?', const='1', action='append', dest='debug',
                        help=("Enable debug. Use level (integer), or a key=value filter like \"when=EXPR, target=NAME, or level=N\"."))

    args = parser.parse_args(argv)

    _apply_debug_settings(args.debug, args.color)
    _apply_when_grouping_profile(args, argv)

    primary_order = args.primary
    secondary_order = args.secondary
    grouping_mode = args.when_grouping
    negation_mode = args.group_sorting

    when_prefixes = _parse_when_prefixes(parser, args.when_prefix)
    when_regexes = _parse_when_regexes(parser, args.when_regex)

    raw = sys.stdin.read()
    preamble, array_text, postamble = extract_preamble_postamble(raw)
    groups, trailing_comments = group_objects_with_comments(array_text)

    normalized_groups = _with_normalized_when_groups(
        groups,
        grouping_mode,
        negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    sorted_groups = _sort_groups_initial(
        normalized_groups,
        primary_order,
        secondary_order,
        grouping_mode,
        negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    sorted_groups = _sort_groups_with_grouping_mode(
        sorted_groups,
        grouping_mode,
        negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    if grouping_mode == 'focal-invariant':
        sorted_groups = _partition_focus_groups_to_end(sorted_groups)

    if primary_order == 'when':
        sorted_groups = _sort_groups_for_primary_when(
            sorted_groups,
            grouping_mode,
            negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )

    final_text = _assemble_sorted_output(
        preamble,
        sorted_groups,
        trailing_comments,
        postamble,
        grouping_mode,
        negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    processed = _finalize_processed_output(
        final_text,
        grouping_mode,
        negation_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    sys.stdout.write(processed)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
