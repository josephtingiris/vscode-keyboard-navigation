#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Canonicalize and sort VS Code keybindings.json (JSONC) while preserving comments.

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
- `--object-clones, -o` — display perfectly identical duplicate objects (default: omitted/False, clone objects are hidden).
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
- Hides exact object clones by default; use `--object-clones` to keep them.
- Debug messages are written to stderr via `_debug._echo(...)` and are controlled by `--debug` and `--color`.

Inputs / Outputs

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

import argparse
import json
import sys
import re

from typing import List, Tuple

from vscode_keynav import cli as _cli
from vscode_keynav import debug as _debug
from vscode_keynav import io as _io
from vscode_keynav import keybindings as _keybindings

# global modifier order, i.e. ctrl+shift, ctrl+shift+alt, ctrl+shift+alt+meta

CANONICAL_MODIFIER_ORDER = ['ctrl', 'shift', 'alt', 'meta']

# color default output value, options: 'auto'|'always'|'never'

COLOR: str = 'auto'

# debug defaults

DEBUG_LEVEL: int = 0  # off
DEBUG_TARGET_CATEGORY: str | None = None  # set vial --debug target=['when', 'ordered', 'canonicalize', ...]
DEBUG_TARGET_WHEN: str = ""  # set via --debug when=

# default when prefixes to be added to standard output, if none are given via the cli

DEFAULT_WHEN_PREFIXES = []

# profile defaults for `--when-grouping` values; arg values always override these

WHEN_GROUPING_PROFILES = {
    'focal-invariant': {
        'primary': 'when',
        'secondary': 'key',
        'group_sorting': 'positive',
        'when_prefix': 'config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters',
        'when_regex': 'config.keyboardNavigation.(.*).enabled,config.keyboardNavigation.chords'
    },
    'config-first': {
        # example defaults for config-first
        'primary': 'key',
        'secondary': 'when',
        'group_sorting': 'alpha',
        'when_prefix': None,
    }
}

#
# functions
#


def _apply_debug_settings(debug_specs: list[str] | None, color: str) -> None:
    """Configure global debug filters and color mode."""

    # delegate to shared debug module and mirror selected values locally
    _debug._apply_settings(debug_specs, color)

    try:
        # mirror values so existing module references continue to work
        global COLOR, DEBUG_LEVEL, DEBUG_TARGET_WHEN, DEBUG_TARGET_CATEGORY
        COLOR = _debug.COLOR
        DEBUG_LEVEL = _debug.DEBUG_LEVEL
        DEBUG_TARGET_WHEN = _debug.DEBUG_TARGET_WHEN
        DEBUG_TARGET_CATEGORY = _debug.DEBUG_TARGET_CATEGORY
    except Exception:
        pass


def _apply_when_grouping_profile(args: argparse.Namespace, raw_argv: list[str]) -> None:
    """Apply a when-grouping profile to set appropriate default argument values."""

    sel_profile = args.when_grouping
    if sel_profile not in WHEN_GROUPING_PROFILES:
        return

    profile = WHEN_GROUPING_PROFILES[sel_profile]

    if not _cli._flag_present(raw_argv, ['-p', '--primary']) and profile.get('primary') is not None:
        args.primary = profile['primary']

    if not _cli._flag_present(raw_argv, ['-s', '--secondary']):
        args.secondary = profile.get('secondary')

    if not _cli._flag_present(raw_argv, ['-g', '--group-sorting']) and profile.get('group_sorting') is not None:
        args.group_sorting = profile['group_sorting']

    if not _cli._flag_present(raw_argv, ['-P', '--when-prefix']):
        args.when_prefix = profile.get('when_prefix')

    if not _cli._flag_present(raw_argv, ['-R', '--when-regex']):
        args.when_regex = profile.get('when_regex')


def _assemble_sorted_output(
    preamble: str,
    sorted_groups: list[tuple[str, str]],
    trailing_comments: str,
    postamble: str,
    grouping_mode: str,
    negation_mode: str,
    object_clones: bool = False,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    """Render the final sorted JSONC output by emitting rendered the preamble, objects, comments, and postamble."""

    out_parts: list[str] = []
    out_parts.append(preamble)
    out_parts.append('[\n')
    rendered_groups: list[tuple[str, str, str]] = []

    seen_pairs: dict[tuple[str, str], set[str]] = {}
    for comments, obj in sorted_groups:
        obj_out = obj.rstrip()

        info = _keybindings._get_run_obj_info(
            obj_out,
            grouping_mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        key_val = info.get('key', '')
        canonical_when = info.get('canonical', '')
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
                is_exact_object_clone = obj_fingerprint in seen_fingerprints
                if is_exact_object_clone and not object_clones:
                    seen_fingerprints.add(obj_fingerprint)
                    continue

                duplicate_comment = f'// DUPLICATE key: {key_val!r} when: {canonical_when!r}'
                if is_exact_object_clone:
                    duplicate_comment += ' (exact object match)'
                obj_out = _keybindings._embed_duplicate_comment_in_object(obj_out, duplicate_comment)
                seen_fingerprints.add(obj_fingerprint)

        rendered_groups.append((comments, obj_out, canonical_when))

    # coalesce identical canonical `when` values into contiguous blocks when grouping is enabled
    if grouping_mode != 'none' or when_prefixes or when_regexes:
        from collections import OrderedDict

        grouped: 'OrderedDict[str, list[tuple[str, str, str]]]' = OrderedDict()
        for comments, obj_out, canonical in rendered_groups:
            grouped.setdefault(canonical, []).append((comments, obj_out, canonical))

        # build JSON-only hashes and full-object hashes to detect duplicates and preserve comments

        new_rendered: list[tuple[str, str, str]] = []

        # compute sort keys derived from the object's `key` field (modifier-first, chord-aware, special<digit<letter ordering)
        for canonical, entries in grouped.items():
            if len(entries) > 1:
                hash_map = {}
                jsonhash_to_indices = {}

                def _key_category_and_order(ch: str) -> tuple[int, int]:

                    #
                    # return (category, order_key) where category is:
                    #
                    # 0 = primary ASCII special (printable non-alnum, ord < 128)
                    # 1 = extended special (ord >= 128)
                    # 2 = digit
                    # 3 = letter
                    # 4 = empty/unknown
                    #
                    # order_key is an int used to order within the category:
                    #
                    # - for ASCII specials: the ASCII code of first char
                    # - for extended specials: attempt CP1252 byte value (Alt-code) falling back to Unicode codepoint
                    # - for digits/letters: the Unicode codepoint of first char
                    #

                    if not ch:
                        return (4, 0)
                    c0 = ch[0]
                    oc = ord(c0)
                    if c0.isalpha():
                        return (3, oc)
                    if c0.isdigit():
                        return (2, oc)
                    # extended (non-ascii) specials
                    if oc >= 128:
                        # try to map to CP1252 byte value (common Alt-code mapping on Windows)
                        try:
                            b = c0.encode('cp1252')
                            if b:
                                return (1, b[0])
                        except Exception:
                            pass
                        return (1, oc)
                    # primary ASCII special
                    return (0, oc)

                def _key_sort_tuple_from_object(obj_text: str):
                    key_raw = _keybindings._extract_literal_key_from_object(obj_text) or ''

                    # detect a trailing '+' (e.g., 'alt++')
                    if '+' in key_raw:
                        mods_part, base_part = key_raw.rsplit('+', 1)
                        if base_part == '':
                            base_part = '+'
                        mods_norm = _normalize_mods(mods_part)
                    else:
                        mods_norm = ''
                        base_part = key_raw

                    # handle '+' before normalization
                    if base_part and all(ch == '+' for ch in base_part):
                        tokens = ['+']
                    else:
                        base_norm = _keybindings._normalize_key_for_compare(base_part)
                        tokens = [t for t in base_norm.split() if t != '']

                    # build token comparator sequence: (category_rank, bytes)
                    token_seq = []
                    for t in tokens:
                        cat, order_key = _key_category_and_order(t)
                        token_seq.append((cat, order_key, t.encode('utf-8')))

                    # final sort tuple: normalized mods (bytewise), token_seq, token_count
                    return (mods_norm.encode('utf-8'), token_seq, len(tokens))

                def _normalize_mods(mods: str) -> str:
                    parts = [p for p in mods.split('+') if p]
                    ordered = [p for p in CANONICAL_MODIFIER_ORDER if p in parts]
                    others = sorted([p for p in parts if p not in ordered])
                    out = ordered + others
                    return '+'.join(out) + ('+' if out else '')

                # compute hashes and collect json-hash groups
                for idx_e, (_comments, obj_text, _canonical) in enumerate(entries):
                    full_h, json_h, json_canonical = _keybindings._get_run_obj_duplicate_info(obj_text)
                    hash_map[idx_e] = (full_h, json_h, json_canonical)
                    jsonhash_to_indices.setdefault(json_h, []).append(idx_e)

                # annotate duplicates where same json_hash but different full_hash
                for json_h, inds in jsonhash_to_indices.items():
                    if len(inds) <= 1:
                        continue
                    full_hashes = {hash_map[i][0] for i in inds}
                    if len(full_hashes) > 1:
                        # inject duplicate comment into each involved object
                        for i in inds:
                            c, o, entry_canonical = entries[i]
                            dup_comment = f'// DUPLICATE JSON object (json-hash={json_h})'
                            entries[i] = (c, _keybindings._embed_duplicate_comment_in_object(o, dup_comment), entry_canonical)

                # now sort entries by comparator derived from their key strings
                entries.sort(key=lambda pair: _key_sort_tuple_from_object(pair[1]))
            new_rendered.extend(entries)

        rendered_groups = new_rendered

    for i, (comments, obj_out, _canonical) in enumerate(rendered_groups):
        is_last = (i == len(rendered_groups) - 1)
        if comments:
            comments = _io._BLANK_LINES_RE.sub('', comments)
            comments = _io._LEADING_COMMA_RE.sub('', comments)
            out_parts.append(comments)

        idx = obj_out.rfind('}')
        if idx != -1:
            after = obj_out[idx + 1:]
            after_clean = _io._LEADING_COMMA_RE.sub('', after)
            obj_out = obj_out[:idx + 1] + after_clean

        out_parts.append(obj_out)
        if not is_last and not _object_has_trailing_comma(obj_out):
            out_parts.append(',')
        out_parts.append('\n')

    trailing_comments = _io._LEADING_COMMA_RE.sub('', trailing_comments)
    out_parts.append(trailing_comments)
    if trailing_comments and not trailing_comments.endswith('\n'):
        out_parts.append('\n')

    postamble_trimmed = _io._STRIP_WS_RE.sub('', postamble)
    if postamble_trimmed:
        out_parts.append(']\n' + postamble_trimmed + '\n')
    else:
        out_parts.append(']\n')

    return ''.join(out_parts)


def _finalize_processed_output(
    text: str,
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    """Perform final output cleanup on the assembled JSONC text (e.g. remove blank lines)."""

    return _remove_blank_lines(text)


def _get_run_obj_match_info(obj_text: str) -> dict:
    """Return per-run cached focus and prefix or regex match signatures for an object text."""

    run_ctx = _keybindings.RUN_CACHE_CONTEXT if _keybindings.RUN_CACHE_CONTEXT else None
    cache_key = (obj_text, run_ctx)
    cached = _keybindings._CLI_RUN_OBJ_MATCH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # delegate to package-level implementation which has its own per-run cache
    try:
        pkg_match = _keybindings._get_run_obj_match_info(obj_text)
        try:
            _keybindings._CLI_RUN_OBJ_MATCH_CACHE[cache_key] = pkg_match
        except Exception:
            pass
        return pkg_match
    except Exception:
        # on any failure, fall back to a conservative empty signature
        empty = {'left_ids': (), 'has_focus': False, 'prefix_idxs': (), 'regex_idxs': ()}
        try:
            _keybindings._CLI_RUN_OBJ_MATCH_CACHE[cache_key] = empty
        except Exception:
            pass
        return empty


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


def _normalize_operand(text: str) -> str:
    """Normalize whitespace in an operand and collapse runs to single spaces."""

    collapsed = _io._WHITESPACE_RE.sub(' ', text).strip()

    return collapsed


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


def _parse_when_prefixes(parser: argparse.ArgumentParser, raw_prefixes: str | None) -> list[str]:
    """Return the parsed `--when-prefix` comma-separated list of prefixes or default a list."""

    if raw_prefixes is not None:
        if raw_prefixes.strip() == '':
            parser.error('--when-prefix requires a comma-separated list with at least one entry')
        when_prefixes = [part.strip() for part in raw_prefixes.split(',') if part.strip()]
        if not when_prefixes:
            parser.error('--when-prefix requires a comma-separated list with at least one entry')
        return when_prefixes

    return DEFAULT_WHEN_PREFIXES.copy()


def _parse_when_regexes(parser: argparse.ArgumentParser, raw_regexes: str | None):
    """Return the parsed `--when-regex` comma-separated list of regexes into compiled regexes or string patterns."""

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
    """Stable-partition groups so that entries containing focus tokens are moved to the end."""

    non_focus: list[tuple[str, str]] = []
    focus: list[tuple[str, str]] = []

    for pair in sorted_groups:
        try:
            if _keybindings._contains_focus_token_in_object(pair[1]):
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


_render_when_node = _keybindings._render_when_node


def _reorder_groups_by_when(sorted_groups: list[tuple[str, str]], negation_mode: str) -> list[tuple[str, str]]:
    """Within equal when groups, reorder objects deterministically by key."""

    if negation_mode in ('positive', 'negative'):
        return sorted_groups
    groups_list = list(sorted_groups)
    i = 0
    while i < len(groups_list):
        raw_when = _keybindings._extract_literal_when_from_object(groups_list[i][1]) or ''
        norm_when = _io._normalize_whitespace(raw_when)
        j = i + 1

        while j < len(groups_list):
            next_when = _keybindings._extract_literal_when_from_object(groups_list[j][1]) or ''
            if _io._normalize_whitespace(next_when) != norm_when:
                break
            j += 1

        if j - i > 1:
            slice_pairs = groups_list[i:j]

            def _mods_lit_from_pair(pair: tuple[str, str]) -> tuple[tuple[str, ...], str]:
                key_raw = _keybindings._extract_literal_key_from_object(pair[1]) or ''
                norm = _keybindings._normalize_key_for_compare(key_raw)
                first = norm.split()[0] if norm else ''
                parts = [p for p in first.split('+') if p]
                mods = tuple(parts[:-1]) if len(parts) > 1 else tuple()
                lit = parts[-1] if parts else ''
                lit_key = _keybindings._normalize_key_for_compare(lit)
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

    canonical = _keybindings._canonicalize_when(
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
    _keybindings.RUN_CACHE_CONTEXT = (
        mode,
        negation_mode,
        None if when_prefixes is None else tuple(when_prefixes),
        None if when_regexes is None else tuple(when_regexes),
    )
    try:
        _keybindings.RUN_CANONICAL_CACHE.clear()
    except Exception:
        _keybindings.RUN_CANONICAL_CACHE = {}
    try:
        _keybindings.RUN_SORTABLE_CACHE.clear()
    except Exception:
        _keybindings.RUN_SORTABLE_CACHE = {}
    try:
        _keybindings.RUN_OBJ_INFO_CACHE.clear()
    except Exception:
        _keybindings.RUN_OBJ_INFO_CACHE = {}
    try:
        _keybindings._CLI_RUN_OBJ_INFO_CACHE.clear()
    except Exception:
        _keybindings._CLI_RUN_OBJ_INFO_CACHE = {}
    try:
        _keybindings._CLI_RUN_OBJ_MATCH_CACHE.clear()
    except Exception:
        _keybindings._CLI_RUN_OBJ_MATCH_CACHE = {}
    try:
        _keybindings.RUN_MATCH_CACHE.clear()
    except Exception:
        _keybindings.RUN_MATCH_CACHE = {}
    try:
        # clear package-level canonicalizer LRU cache
        _keybindings._clear_lru_when_cache()
    except Exception:
        pass


def _sort_groups_for_primary_when(
    sorted_groups: list[tuple[str, str]],
    grouping_mode: str,
    negation_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> list[tuple[str, str]]:
    """Sort by `--primary when` derived keys and apply grouping heuristics."""

    decorated: list[tuple[str, str, str, tuple[str, str]]] = []
    for pair in sorted_groups:
        info = _keybindings._get_run_obj_info(
            pair[1],
            grouping_mode=grouping_mode,
            negation_mode=negation_mode,
            when_prefixes=when_prefixes,
            when_regexes=when_regexes,
        )
        key_val = info.get('key', '')
        when_val = info.get('when', '')
        canonical = info.get('canonical', '')
        if not key_val:
            key_val = _keybindings._extract_literal_key_from_object(pair[1])
        if not when_val:
            when_val = _keybindings._extract_literal_when_from_object(pair[1])
            if not canonical:
                canonical = when_val
        decorated.append((key_val, when_val, canonical, pair))

    for key_val, when_val, canonical, _pair in decorated:
        if not canonical:
            canonical = when_val

        if DEBUG_LEVEL > 0:
            normalized = _keybindings._normalize_key_for_compare(key_val)
            try:
                natural = _keybindings._natural_key(normalized)
            except Exception:
                natural = normalized
            _debug._echo(
                2,
                'sort',
                when_val,
                f"DEBUG_SORT: raw_key={key_val!r} normalized={normalized!r} natural_key={natural!r} when_raw={when_val!r} when_canonical={canonical!r}",
            )

    decorated.sort(
        key=lambda row: (
            row[2],
            row[1],
            _keybindings._natural_key_case_sensitive(row[0]),
        )
    )

    if grouping_mode == 'focal-invariant':
        non_focus_rows = []
        focus_rows = []
        for row in decorated:
            when_val = row[1] or ''
            try:
                match_info = _get_run_obj_match_info(row[3][1])
                found_focus = bool(match_info.get('has_focus', False))
                for left_id in match_info.get('left_ids', ()):
                    try:
                        if 'terminal' in left_id or 'keyboardNavigation' in left_id:
                            _debug._echo(1, 'group', when_val, f"SIG_PART: left_id={left_id!r}")
                    except Exception:
                        pass

                if found_focus:
                    focus_rows.append(row)
                else:
                    non_focus_rows.append(row)
            except Exception:
                non_focus_rows.append(row)
        decorated = non_focus_rows + focus_rows

    sorted_groups = [row[3] for row in decorated]

    for idx, pair in enumerate(sorted_groups):
        key_val, when_val = _keybindings._extract_key_when_from_object(pair[1])
        try:
            canonical = _keybindings._canonicalize_when(
                when_val,
                mode=grouping_mode,
                negation_mode=negation_mode,
                when_prefixes=when_prefixes,
                when_regexes=when_regexes,
            )
        except Exception:
            canonical = when_val

        if DEBUG_LEVEL > 0:
            normalized = _keybindings._normalize_key_for_compare(key_val)
            _debug._echo(1, 'ordered', canonical, f"DEBUG_ORDERED: idx={idx} raw_key={key_val!r} normalized={normalized!r}")

    #
    # stable-partition when prefixes and/or regexes into three contiguous regions,
    # following this order:
    #  1. clauses matching any when_prefix (any operand),
    #  2. clauses matching any when_regex (any operand) but not matching prefixes,
    #  3. all remaining clauses.
    #

    if when_prefixes or when_regexes:
        matched_prefix: list[tuple[str, str]] = []
        matched_regex: list[tuple[str, str]] = []
        others: list[tuple[str, str]] = []
        for pair in sorted_groups:
            match_info = _get_run_obj_match_info(pair[1])
            found_prefix = bool(match_info.get('prefix_idxs'))
            found_regex = bool(match_info.get('regex_idxs'))

            if found_regex:
                matched_regex.append(pair)
            elif found_prefix:
                matched_prefix.append(pair)
            else:
                others.append(pair)

        if matched_prefix or matched_regex:
            _debug._echo(
                1,
                'group',
                None,
                f"partitioned primary-when: prefix={len(matched_prefix)} regex={len(matched_regex)} others={len(others)}",
            )
            sorted_groups = matched_prefix + matched_regex + others

    i = 0
    while i < len(sorted_groups):
        _, raw_when = _keybindings._extract_key_when_from_object(sorted_groups[i][1])
        if not raw_when:
            raw_when = _keybindings._extract_literal_when_from_object(sorted_groups[i][1])

        normalized_when = _io._normalize_whitespace(raw_when)
        j = i + 1
        while j < len(sorted_groups):
            _, next_when = _keybindings._extract_key_when_from_object(sorted_groups[j][1])
            if not next_when:
                next_when = _keybindings._extract_literal_when_from_object(sorted_groups[j][1])
            if _io._normalize_whitespace(next_when) != normalized_when:
                break
            j += 1

        if j - i > 1 and negation_mode not in ('positive', 'negative'):
            slice_pairs = sorted_groups[i:j]
            slice_pairs.sort(key=lambda pair: _keybindings._natural_key_case_sensitive(_keybindings._extract_literal_key_from_object(pair[1])))
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
    """Perform the initial stable sort of normalized groups using extract_sort_keys logic."""

    return sorted(
        normalized_groups,
        key=lambda pair: _keybindings._extract_sort_keys_from_object(
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
    """Re-bucket sorted groups into positional bins according to the when-grouping mode."""

    if grouping_mode == 'none':
        return sorted_groups

    buckets: dict[int, list[tuple[str, str]]] = {}
    for pair in sorted_groups:
        rank = _keybindings._first_when_group_rank(
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


#
# main
#


def main(argv: List[str] | None = None) -> int:
    """Parse arguments, read stdin, sort keybinding objects, and write sorted JSONC to stdout."""

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

    parser.add_argument('--object-clones', '-o', action='store_true', default=False,
                        help='Show exact duplicate objects (clones) in output (default: hidden).')

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
    #

    parser.add_argument('--debug', '-d', nargs='?', const='1', action='append', dest='debug',
                        help=("Enable debug. Use level (integer), or a key=value filter like \"when=EXPR, target=NAME, or level=N\"."))

    args = parser.parse_args(argv)

    _apply_debug_settings(args.debug, args.color)

    try:
        _debug._echo(2, 'init', None, 'debugging enabled')
    except Exception:
        pass

    _apply_when_grouping_profile(args, argv)

    primary_order = args.primary
    secondary_order = args.secondary
    grouping_mode = args.when_grouping
    negation_mode = args.group_sorting

    when_prefixes = _parse_when_prefixes(parser, args.when_prefix)
    when_regexes = _parse_when_regexes(parser, args.when_regex)

    _set_run_cache_context(grouping_mode, negation_mode, when_prefixes, when_regexes)

    raw = sys.stdin.read()
    preamble, array_text, postamble = _keybindings._extract_preamble_postamble(raw)
    groups, trailing_comments = _group_objects_with_comments(array_text)

    normalized_groups = _keybindings._with_normalized_when_groups(
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

    #
    # last-step stable partition
    #
    # desired order:
    #
    #  1. objects with no prefix and no regex (others)
    #  2. objects grouped by prefix combinations (ordered by smallest prefix index, then by fewer prefixes first),
    #     and within each prefix-group emit items without regex first, then with regex combinations ordered by fewest regexes.
    #  3. objects with no prefix but with regex(es) (regex-only)
    #

    # produce a deterministic ordering by prefix/regex combination signature.
    if when_prefixes or when_regexes:
        # helper: compute matched prefix indices and regex indices for an object
        def _match_signature(pair: tuple[str, str]):
            match_info = _get_run_obj_match_info(pair[1])
            return (
                match_info.get('prefix_idxs', ()),
                match_info.get('regex_idxs', ()),
            )

        # build nested mapping: prefix_tuple -> regex_tuple -> list[pairs]
        buckets: dict[tuple[int, ...], dict[tuple[int, ...], list[tuple[str, str]]]] = {}

        # signature map for quick lookup: pair -> (prefix_tuple, regex_tuple)
        sig_map: dict[tuple[str, str], tuple[tuple[int, ...], tuple[int, ...]]] = {}

        for pair in sorted_groups:
            p_sig, r_sig = _match_signature(pair)
            buckets.setdefault(p_sig, {}).setdefault(r_sig, []).append(pair)
            sig_map[pair] = (p_sig, r_sig)

        # debug: summary counts per regex index and sample terminal entries
        try:
            if when_regexes:
                per_idx = [0] * len(when_regexes)
                for p, sig in sig_map.items():
                    _, r_sig = sig
                    for r in r_sig:
                        if 0 <= r < len(per_idx):
                            per_idx[r] += 1
                _debug._echo(1, 'group', None, f"REGEX_COUNTS: {per_idx}")

                sample_count = 0
                for pair, sig in sig_map.items():
                    _, r_sig = sig
                    info = _keybindings._get_run_obj_info(pair[1])
                    when_val = info.get('when', '') or _keybindings._extract_literal_when_from_object(pair[1])
                    if when_val and 'terminal' in when_val:
                        _debug._echo(1, 'group', when_val, f"REGEX_SAMPLE: p_sig={sig[0]} r_sig={r_sig} key={info.get('key', '')!r}")
                        sample_count += 1
                        if sample_count >= 10:
                            break
        except Exception:
            pass

        # sort helper for prefix keys: prefer smaller min-index, then fewer prefixes, then lexicographic
        def _prefix_key(t: tuple[int, ...]):
            if not t:
                return (9999, 9999, ())
            return (min(t), len(t), t)

        # sort helper for regex keys: prefer fewer regexes then lexicographic
        def _regex_key(t: tuple[int, ...]):
            return (0 if not t else 1, len(t), t)

        # stable secondary ordering for each concrete bucket
        def _sort_block(block: list[tuple[str, str]]) -> list[tuple[str, str]]:
            try:
                return sorted(
                    block,
                    key=lambda pair: (
                        _keybindings._canonicalize_when(
                            _keybindings._extract_key_when_from_object(pair[1])[1] or _keybindings._extract_literal_when_from_object(pair[1]),
                            mode=grouping_mode,
                            negation_mode=negation_mode,
                            when_prefixes=when_prefixes,
                            when_regexes=when_regexes,
                        ),
                        _keybindings._natural_key_case_sensitive(_keybindings._normalize_key_for_compare(_keybindings._extract_key_when_from_object(pair[1])[0])),
                    ),
                )
            except Exception:
                return block

        # assemble final ordered list using cumulative prefix and cumulative regex ordering

        # 1. others: prefix==() and regex==()
        final_list: list[tuple[str, str]] = []
        emitted: set[tuple[str, str]] = set()
        others = buckets.get((), {}).get((), [])
        if others:
            for p in _sort_block(others):
                if p not in emitted:
                    final_list.append(p)
                    emitted.add(p)

        # 2. cumulative prefix groups: p1, p1+p2, p1+p2+p3, ...
        num_prefixes = 0 if not when_prefixes else len(when_prefixes)
        num_regexes = 0 if not when_regexes else len(when_regexes)

        for p_len in range(1, num_prefixes + 1):
            p_key = tuple(range(0, p_len))
            regex_map = buckets.get(p_key, {})
            prefix_only_list = regex_map.get((), [])
            if prefix_only_list:
                filtered = [p for p in prefix_only_list if not sig_map.get(p, ((), ()))[1]]
                if filtered:
                    final_list.extend(_sort_block(filtered))

        if when_regexes:
            for r_idx in range(0, len(when_regexes)):
                matches = [p for p in sorted_groups if (r_idx in sig_map.get(p, ((), ()))[1] and p not in emitted)]
                if matches:
                    for p in _sort_block(matches):
                        if p not in emitted:
                            final_list.append(p)
                            emitted.add(p)

        # 3. regex-only cumulative groups (no prefix but regex present)
        regex_only_map = buckets.get((), {})
        for r_len in range(1, (0 if not when_regexes else len(when_regexes)) + 1):
            r_key = tuple(range(0, r_len))
            final_list.extend(_sort_block(regex_only_map.get(r_key, [])))

        # 4. any remaining buckets (non-cumulative combinations); append in stable order
        handled_prefixes: set[tuple[int, ...]] = set()

        handled_prefixes.add(())
        for p_len in range(1, num_prefixes + 1):
            handled_prefixes.add(tuple(range(0, p_len)))

        remaining_keys = [k for k in buckets.keys() if k not in handled_prefixes]
        for k in sorted(remaining_keys, key=_prefix_key):
            regex_map = buckets.get(k, {})
            for rk in sorted(regex_map.keys(), key=_regex_key):
                final_list.extend(_sort_block(regex_map.get(rk, [])))

        # sanity: ensure no items were accidentally dropped during bucket assembly
        orig_count = len(sorted_groups)
        if len(final_list) != orig_count:
            existing = {pair[1] for pair in final_list}
            missing = [p for p in sorted_groups if p[1] not in existing]
            if missing:
                _debug._echo(1, 'group', None, f"WARNING: bucket assembly dropped {len(missing)} items; appending missing items back")
                # append missing items in original order to preserve stability
                final_list.extend(missing)

        # debug: compute contiguous runs for each regex index in the assembled final_list
        try:
            if when_regexes:
                for r_idx in range(0, len(when_regexes)):
                    runs = 0
                    prev_in = False
                    for pair in final_list:
                        r_sig = sig_map.get(pair, ((), ()))[1]
                        in_here = r_idx in r_sig
                        if in_here and not prev_in:
                            runs += 1
                        prev_in = in_here
                    _debug._echo(1, 'group', None, f"REGEX_RUNS idx={r_idx} runs={runs}")
        except Exception:
            pass

        _debug._echo(
            1,
            'group',
            None,
            f"final partition: buckets={len(buckets)} final={len(final_list)}",
        )

        sorted_groups = final_list

    sorted_groups = _reorder_groups_by_when(sorted_groups, negation_mode)

    final_text = _assemble_sorted_output(
        preamble,
        sorted_groups,
        trailing_comments,
        postamble,
        grouping_mode,
        negation_mode,
        object_clones=args.object_clones,
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

    try:
        # write via the binary buffer to avoid Python-level text encoding costs
        out_bytes = processed.encode('utf-8')
        try:
            sys.stdout.buffer.write(out_bytes)
            sys.stdout.buffer.flush()
        except BrokenPipeError:
            try:
                sys.stdout.buffer.flush()
            except Exception:
                pass
            raise SystemExit(0)
    except Exception:
        # fallback to text write if buffer isn't available for any reason
        try:
            sys.stdout.write(processed)
        except BrokenPipeError:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            raise SystemExit(0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
