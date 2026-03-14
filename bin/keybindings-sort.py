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
- `--group-sorting, -g` — how to sort tokens inside a when-group (alphanumeric, natural, positive, negative, ...).
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


#
# globals & constants
#


# profile defaults for `--when-grouping` value; actual arg values always override profile values

_WHEN_GROUPING_PROFILES = {
    'config-first': {
        'primary': 'key',
        'secondary': 'when',
        'group_sorting': 'alphanumeric',
        'when_prefix': None,
        'when_regex': None,
    },
    'focal-invariant': {
        'primary': 'when',
        'secondary': 'key',
        'group_sorting': 'positive',
        'when_prefix': 'config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters',
        'when_regex': 'config.keyboardNavigation.chords'
    }
}

#
# functions
#


def _apply_when_grouping_profile(args: argparse.Namespace, raw_argv: list[str]) -> None:
    """Apply a when-grouping profile to set appropriate default argument values."""

    # name the profiles after the --when-grouping value
    sel_profile = args.when_grouping
    if sel_profile not in _WHEN_GROUPING_PROFILES:
        return

    profile = _WHEN_GROUPING_PROFILES[sel_profile]

    if not _cli._flag_present(raw_argv, ['-p', '--primary']) and profile.get('primary') is not None:
        args.primary = profile['primary']

    if not _cli._flag_present(raw_argv, ['-s', '--secondary']) and profile.get('secondary') is not None:
        args.secondary = profile.get('secondary')

    if not _cli._flag_present(raw_argv, ['-g', '--group-sorting']) and profile.get('group_sorting') is not None:
        args.group_sorting = profile['group_sorting']

    if not _cli._flag_present(raw_argv, ['-P', '--when-prefix']) and profile.get('when_prefix') is not None:
        args.when_prefix = profile.get('when_prefix')

    if not _cli._flag_present(raw_argv, ['-R', '--when-regex']) and profile.get('when_regex') is not None:
        args.when_regex = profile.get('when_regex')


def _assemble_sorted_output(
    preamble: str,
    sorted_groups: list[tuple[str, str]],
    trailing_comments: str,
    postamble: str,
    grouping_mode: str,
    sorting_mode: str,
    when_canonical_mode: str | None = None,
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
            sorting_mode=(when_canonical_mode if when_canonical_mode is not None else sorting_mode),
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

                # sort by comparator derived from the key strings
                entries.sort(key=lambda pair: _keybindings._group_sort_tuple_from_key_string(_keybindings._extract_literal_key_from_object(pair[1]) or ''))
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
        if not is_last and not _keybindings._object_has_trailing_comma(obj_out):
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


def _assemble_final_output(
    text: str,
    grouping_mode: str,
    sorting_mode: str,
    when_prefixes: list | None = None,
    when_regexes: list | None = None,
) -> str:
    """Perform final output cleanup on the assembled JSONC text (e.g. remove blank lines)."""

    return _keybindings._remove_blank_lines(text)


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
                        choices=['alphanumeric', 'natural', 'positive-natural', 'negative-natural', 'positive', 'negative', 'lexicographic', 'specificity'], default='lexicographic',
                        help="Group sorting mode: pre-defined ordering algorithms for when clauses (default: lexicographic). Use 'specificity' to prefer term-count specificity as a tie-break.")

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

    _debug._apply_settings(args.debug, args.color)

    try:
        _debug._echo(2, 'init', None, 'debugging enabled')
    except Exception:
        pass

    _apply_when_grouping_profile(args, argv)

    primary_order = args.primary
    secondary_order = args.secondary
    grouping_mode = args.when_grouping
    sorting_mode = args.group_sorting

    when_prefixes = _cli._parse_when_prefixes(parser, args.when_prefix)
    when_regexes = _cli._parse_when_regexes(parser, args.when_regex)

    flag_g = _cli._flag_present(argv, ['-g', '--group-sorting'])
    flag_w = _cli._flag_present(argv, ['-w', '--when-grouping'])
    profile_has_group_sorting = args.when_grouping in _WHEN_GROUPING_PROFILES and _WHEN_GROUPING_PROFILES[args.when_grouping].get('group_sorting') is not None

    _keybindings._set_run_cache_context(grouping_mode, sorting_mode, when_prefixes, when_regexes)

    raw = sys.stdin.read()
    preamble, array_text, postamble = _keybindings._extract_preamble_postamble(raw)
    groups, trailing_comments = _keybindings._group_objects_with_comments(array_text)

    normalized_groups = _keybindings._with_normalized_when_groups(
        groups,
        grouping_mode,
        sorting_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    sorted_groups = _keybindings._sort_groups_initial(
        normalized_groups,
        primary_order,
        secondary_order,
        grouping_mode,
        sorting_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    # Stabilize ordering within identical `key` groups for the common
    # lexicographic case when primary==key and secondary is when (or omitted).
    # Do this only when no when-prefix/when-regex are in use and when grouping
    # mode is `none` so we don't affect focal-invariant or other partitioning
    # behaviors (they are handled elsewhere).
    if (
        primary_order == 'key'
        and (secondary_order is None or secondary_order == 'when')
        and grouping_mode == 'none'
        and sorting_mode == 'lexicographic'
        and not when_prefixes
        and not when_regexes
    ):
        stabilized: list[tuple[str, str]] = []
        i = 0
        n = len(sorted_groups)

        def _first_when_sort_tuple(pair: tuple[str, str]):
            # return tuple used for intra-key sorting: (first_when_key, full_when_key)
            obj_text = pair[1]
            info = _keybindings._get_run_obj_info(obj_text, grouping_mode=grouping_mode, sorting_mode=sorting_mode)
            canonical = info.get('canonical', '') or ''
            parts = _keybindings._split_when_contexts(canonical)
            first = parts[0] if parts else ''
            first_key = _keybindings._natural_key_case_sensitive(first)
            full_when = _keybindings._sortable_when_key(info.get('when', '') or '', grouping_mode, sorting_mode)
            full_key = _keybindings._natural_key_case_sensitive(full_when)
            return (first_key, full_key)

        while i < n:
            # collect contiguous run of same literal `key` (already grouped by initial sort)
            j = i + 1
            key_i = _keybindings._extract_literal_key_from_object(sorted_groups[i][1]) or ''
            while j < n and (_keybindings._extract_literal_key_from_object(sorted_groups[j][1]) or '') == key_i:
                j += 1

            if j - i > 1:
                run = sorted_groups[i:j]
                # stable sort the run by first_when then full when (both natural-case-sensitive)
                run.sort(key=lambda pair: _first_when_sort_tuple(pair))
                stabilized.extend(run)
            else:
                stabilized.append(sorted_groups[i])

            i = j

        sorted_groups = stabilized

    sorted_groups = _keybindings._sort_groups_with_grouping_mode(
        sorted_groups,
        grouping_mode,
        sorting_mode,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    if grouping_mode == 'focal-invariant':
        sorted_groups = _keybindings._partition_focus_groups_to_end(sorted_groups)

    if primary_order == 'when':
        sorted_groups = _keybindings._sort_groups_for_primary_when(
            sorted_groups,
            grouping_mode,
            sorting_mode,
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
            match_info = _keybindings._get_run_obj_match_info(pair[1])
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
                            sorting_mode=sorting_mode,
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

    sorted_groups = _keybindings._reorder_groups_by_when(sorted_groups, sorting_mode)

    # Make canonicalization/rendering mode follow the chosen group-sorting.
    # The user requested that canonicalization and sorting be controlled by
    # the same flag; set `when_canonical_mode` to the active `sorting_mode`.
    when_canonical_mode = sorting_mode

    final_text = _assemble_sorted_output(
        preamble,
        sorted_groups,
        trailing_comments,
        postamble,
        grouping_mode,
        sorting_mode,
        when_canonical_mode=when_canonical_mode,
        object_clones=args.object_clones,
        when_prefixes=when_prefixes,
        when_regexes=when_regexes,
    )

    processed = _assemble_final_output(
        final_text,
        grouping_mode,
        sorting_mode,
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
