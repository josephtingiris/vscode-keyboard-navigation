#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

[WIP] Lint and optionally canonicalize in-object key comments in JSONC keybindings.

Usage:
    python3 bin/keybindings-lint-comments.py [path/to/keybindings.json]

Options:
    --details    Print surrounding lines for each reported issue.
    --update     Print the file with canonicalized comments to stdout (no files modified).

Examples:
    python3 bin/keybindings-lint-comments.py
    python3 bin/keybindings-lint-comments.py --details
    python3 bin/keybindings-lint-comments.py --update > updated-keybindings.json

Behavior:
    - Checks that each top-level object containing a `"key"` has exactly one single-line comment immediately above it and that the comment matches the project's heuristic convention.
    - `--update` emits canonicalized comment lines to stdout; the script itself never writes files in-place.

Inputs / Outputs:
    path: Path to JSONC file (defaults to `references/keybindings.json`).
    stdout: Diagnostics or updated file content depending on options.

Exit codes:
    0   Success (no errors found)
    0   Success with issues reported to stdout
    1   Usage / bad args
    2   File read/write or other runtime error
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple


CONVENTION_RE = re.compile(
    r"^\s*//\s*(?:\([^\)]*\)\s*)+(?:-\s*[^\{\n]+)?(?:\s*\{[^\}]+\})?\s*$")


def usage(prog: str | None = None) -> None:
    if prog is None:
        prog = os.path.basename(sys.argv[0])
    msg = (
        f"Usage: {prog} [path/to/keybindings.json] [--details] [--update]\n\n"
        "Options:\n  --details    Print surrounding lines for each issue\n"
        "  --update     Print the file with canonicalized comments to stdout\n"
        "  -h, --help   Show this usage message and exit\n"
    )
    print(msg, file=sys.stderr)
    # Help/usage should exit successfully when requested
    sys.exit(0)


def find_top_level_objects(lines: List[str]) -> List[List[Tuple[int, str]]]:
    objs: List[List[Tuple[int, str]]] = []
    buf: List[Tuple[int, str]] = []
    depth = 0
    in_array = False
    for i, line in enumerate(lines):
        if not in_array and '[' in line:
            in_array = True
        opens = line.count('{')
        closes = line.count('}')
        prev_depth = depth
        depth += opens - closes
        if in_array and prev_depth == 0 and depth > 0:
            buf = [(i + 1, line)]
        elif in_array and depth > 0:
            buf.append((i + 1, line))
        elif in_array and prev_depth > 0 and depth == 0:
            objs.append(buf)
            buf = []
    return objs


def analyze_object(buf: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    issues: List[Tuple[int, str]] = []
    for idx, (ln, line) in enumerate(buf):
        if '"key"' in line:
            key_line_idx = idx
            # previous line must exist and be a single-line comment
            if key_line_idx == 0:
                issues.append(
                    (ln, 'key at start of object; no space for comment above'))
                continue
            prev_ln, prev_line = buf[key_line_idx - 1]
            if not prev_line.lstrip().startswith('//'):
                issues.append(
                    (ln, 'missing in-object comment directly above "key"'))
            else:
                if key_line_idx - 2 >= 0 and buf[key_line_idx - 2][1].lstrip().startswith('//'):
                    issues.append(
                        (prev_ln, 'multiple comment lines found directly above "key" — only one allowed'))
                if not CONVENTION_RE.match(prev_line):
                    issues.append(
                        (prev_ln, 'comment does not match convention pattern'))
    return issues


def lint(path: Path) -> List[Tuple[int, str]]:
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    objs = find_top_level_objects(lines)
    all_issues: List[Tuple[int, str]] = []
    for buf in objs:
        issues = analyze_object(buf)
        all_issues.extend(issues)
    return all_issues


def parse_args() -> Tuple[Path, bool, bool]:
    raw_argv = sys.argv[1:]
    if any(a in ('-h', '--help') for a in raw_argv):
        usage()
    parser = argparse.ArgumentParser(
        description='Lint keybinding comments (in-object, above "key")')
    parser.add_argument('path', nargs='?', type=Path, default=Path(
        'references/keybindings.json'), help='Path to JSONC keybindings file')
    parser.add_argument('--details', action='store_true',
                        help='Print surrounding lines for each issue')
    parser.add_argument('--update', action='store_true',
                        help='Print the file with canonicalized comments to stdout (no files are modified)')
    args = parser.parse_args()
    return args.path, args.details, args.update


def main() -> None:
    try:
        path, details, do_update = parse_args()
    except SystemExit:
        # argparse already printed help/usage; exit cleanly
        return

    if not path.exists():
        print(f'ERROR: file not found: {path}', file=sys.stderr)
        return

    # If update requested, print the canonicalized content to stdout and exit
    if do_update:
        try:
            changed, new_text = generate_updated_content(path)
        except Exception as exc:
            print(
                f'ERROR: failed to generate updated content for {path}: {exc}', file=sys.stderr)
            return
        sys.stdout.write(new_text)
        return

    try:
        issues = lint(path)
    except Exception as exc:
        print(f'ERROR: failed to lint {path}: {exc}', file=sys.stderr)
        return
    if not issues:
        print('OK: all checked key entries have an in-object comment directly above and match convention (heuristic)')
        return
    print(f'Found {len(issues)} issue(s):')
    for lineno, msg in issues:
        print(f' - [line {lineno}] {msg}')
        if details:
            # print a small context window
            text = path.read_text(encoding='utf-8')
            lines = text.splitlines()
            start = max(0, lineno - 3)
            end = min(len(lines), lineno + 2)
            for i in range(start, end):
                prefix = '>' if (i + 1) == lineno else ' '
                print(f'{prefix} {i+1:5d}: {lines[i]}')
            print('')
    print('\nNotes:')
    print(' - This linter is conservative and uses heuristics; it expects the JSONC layout similar to repository conventions.')
    print(' - It does not modify files (read-only).')


def canonical_comment_for(key: str, command_val: str | None, key_indent: str, extra_tokens: List[str] | None = None) -> Tuple[str, List[str], str]:
    """Return (canonical_comment_line, extra_note_lines[]).

    The canonical comment line is already indented with `key_indent`.
    Extra note lines are also indented and ready to insert below the canonical line.
    """
    # Build token list from supplied extra_tokens only. Do NOT derive tokens
    # from the key string or the binding letters (user requested).
    extra_tokens = extra_tokens or []
    tokens: List[str] = []
    seen: set[str] = set()
    for t in extra_tokens:
        if not t:
            continue
        tok = t.strip().lower()
        # normalize parentheses if present
        if tok.startswith('(') and tok.endswith(')'):
            tok = tok[1:-1].strip()
        # drop senseless tokens: single letters, lone 't', 'placeholder', or hex ids
        if len(tok) <= 1:
            continue
        if tok in ('t', 'placeholder'):
            continue
        if tok == 'note':
            continue
        if re.fullmatch(r'[0-9a-f]{4}', tok):
            continue
        # keep alpha-numeric and hyphenated tokens
        tok = re.sub(r"[^a-z0-9\-]", '', tok)
        if not tok:
            continue
        if tok not in seen:
            seen.add(tok)
            tokens.append(tok)

    # canonical ordering: high-priority tokens first, then alphabetical rest
    priority = ['split', 'vertical', 'horizontal', 'left', 'right',
                'up', 'down', 'vi', 'zoom', 'copy', 'debug', 'neovim']

    def token_key(x: str) -> Tuple[int, str]:
        try:
            return (priority.index(x), x)
        except ValueError:
            return (len(priority), x)
    tokens.sort(key=token_key)

    # derive action from command_val (fallback)
    action = ''
    if command_val:
        cmd = command_val.strip()
        if re.search(r"\b[0-9a-f]{4}\b", cmd):
            action = ''
        elif '.' in cmd:
            action = cmd.split('.')[-1]
        else:
            action = re.sub(r"\s+", '_', cmd)

    # build token parts string (caller will merge description/action as needed)
    if tokens:
        token_parts = ' '.join(f'({t})' for t in tokens)
    else:
        token_parts = ''

    # 'extra' was not constructed; return an empty list for extra-note lines
    return token_parts, [], action


def generate_updated_content(path: Path) -> tuple[bool, str]:
    """Return (changed, new_text) after canonicalizing comments.

    This function does NOT write files; it only returns the new content so
    callers can choose to write it or print it. The script's policy is to
    never modify files in-place.
    """
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    objs = []
    depth = 0
    in_array = False
    obj_start = None
    # find object boundaries (line indices)
    for i, line in enumerate(lines):
        if not in_array and '[' in line:
            in_array = True
        opens = line.count('{')
        closes = line.count('}')
        prev_depth = depth
        depth += opens - closes
        if in_array and prev_depth == 0 and depth > 0:
            obj_start = i
        elif in_array and prev_depth > 0 and depth == 0 and obj_start is not None:
            objs.append((obj_start, i))
            obj_start = None

    new_lines: List[str] = []
    last_out = 0
    changed = False

    KEY_RE = re.compile(r'"key"\s*:\s*"([^"]+)"')
    COMMAND_RE = re.compile(r'"command"\s*:\s*"([^"]+)"')

    for (start, end) in objs:
        # scan within object for key lines
        i = start
        while i <= end:
            mkey = KEY_RE.search(lines[i])
            if mkey:
                key_val = mkey.group(1)
                # find contiguous comment block immediately above key (within object)
                j = i - 1
                comment_block = []
                while j >= start and lines[j].lstrip().startswith('//'):
                    comment_block.insert(0, (j, lines[j]))
                    j -= 1

                # find command value in the object (search forward from i to end)
                cmd_val = None
                k = i + 1
                while k <= end:
                    mcmd = COMMAND_RE.search(lines[k])
                    if mcmd:
                        cmd_val = mcmd.group(1)
                        break
                    k += 1

                key_indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]

                # If block already has a canonical line and is directly above key, leave it
                has_canonical = False
                if comment_block:
                    # the last comment in block is the one immediately above key
                    # filter out purely hex placeholders from the preserved notes
                    filtered_block = []
                    for (lnn, linetxt) in comment_block:
                        # remove command-placeholder comments like: // "command": "... 1a2b"
                        if re.search(r'"command"\s*:', linetxt):
                            # if it also contains a 4-hex id, drop it
                            if re.search(r"\b[0-9a-f]{4}\b", linetxt):
                                continue
                        # drop bare meta-only braces {abcd}
                        if re.match(r"\s*//\s*\{?[0-9a-f]{4}\}?\s*$", linetxt):
                            continue
                        filtered_block.append((lnn, linetxt))

                    comment_block = filtered_block
                    if comment_block and CONVENTION_RE.match(comment_block[-1][1]):
                        has_canonical = True

                # build extra tokens and descriptions from existing comment block (to preserve tags)
                existing_tokens: List[str] = []
                existing_descs: List[str] = []
                pre_preserve_notes: List[str] = []
                if comment_block:
                    for (_, linetxt) in comment_block:
                        # preserve any '(note)' comment lines verbatim and skip them
                        if '(note)' in linetxt.lower():
                            pre_preserve_notes.append(linetxt)
                            continue
                        # extract parenthesized tokens
                        found = re.findall(r"\([^\)]+\)", linetxt)
                        for f in found:
                            token = f.strip('()')
                            if token and token not in existing_tokens:
                                existing_tokens.append(token)
                        # extract bracketed tokens like [vertical]
                        found_br = re.findall(r"\[([^\]]+)\]", linetxt)
                        for f in found_br:
                            token = f.strip()
                            if token and token not in existing_tokens:
                                existing_tokens.append(token)
                        # extract description text after ' - '
                        mdesc = re.search(r"-\s*(.+)$", linetxt)
                        if mdesc:
                            desc = mdesc.group(1).strip()
                            if desc and desc not in existing_descs:
                                existing_descs.append(desc)
                        else:
                            # capture trailing text after tokens, e.g. "(zoom) toggle zen mode"
                            # remove parenthesized and bracketed tokens and leading '//' marker
                            remainder = re.sub(
                                r"\s*(\([^\)]+\)|\[[^\]]+\])\s*", ' ', linetxt)
                            remainder = remainder.lstrip()[2:].strip()
                            if remainder and not re.search(r'"command"\s*:', linetxt):
                                if remainder not in existing_descs:
                                    existing_descs.append(remainder)
                        # also detect keyword tags like 'zoom', 'copy', 'debug'
                        for kw in ('zoom', 'copy', 'debug', 'neovim', 'placeholder', 't'):
                            if kw in linetxt.lower() and kw not in existing_tokens:
                                existing_tokens.append(kw)

                # Prepare to rebuild output: push all content up to (j+1)
                new_lines.extend(lines[last_out: j + 1])

                # candidate merged description (first existing description, if any)
                merged_desc = existing_descs[0].strip(
                ) if existing_descs else None

                # Always produce a single canonical comment line (deduplicate and normalize)
                token_parts, extra, derived_action = canonical_comment_for(
                    key_val, cmd_val, key_indent, existing_tokens)
                token_parts = token_parts.strip()

                # Build canonical equivalent string for comparison (tokens + merged_desc)
                canonical_equiv = ''
                parts_eq: List[str] = []
                if token_parts:
                    parts_eq.append(token_parts)
                # if we have any explicit '(note)' lines, do not merge their descriptions
                if merged_desc and not pre_preserve_notes:
                    parts_eq.append(merged_desc)
                if parts_eq:
                    canonical_equiv = f"{key_indent}// {' - '.join(parts_eq)}"

                # If the existing comment block is exactly the canonical line and there
                # are no other comment lines immediately above the key, keep as-is.
                if comment_block and len(comment_block) == 1 and comment_block[-1][1].strip() == canonical_equiv and canonical_equiv:
                    new_lines.extend([ln for (_, ln) in comment_block])
                else:
                    # If there are original descriptions, merge the first description
                    # into the canonical comment line (preferred merge mode).
                    # merged_desc already computed above

                    # insert canonical line only if we have tokens or a description
                    if token_parts or merged_desc:
                        token_part = token_parts
                        # build merged comment: tokens then description then action
                        parts = []
                        if token_part:
                            parts.append(token_part)
                        # prefer existing merged description, but do not merge note lines
                        if merged_desc and not pre_preserve_notes:
                            parts.append(merged_desc)
                        # do NOT append any fragments derived from the raw command value
                        if parts:
                            merged_line = f"{key_indent}// {' - '.join(parts)}"
                            new_lines.append(merged_line)

                    # keep '(note)' lines verbatim and exclude them from filtering
                    other_notes = [ln for (_, ln) in comment_block if not re.search(
                        r'\b[0-9a-f]{4}\b', ln) and '(note)' not in ln.lower()]
                    # avoid re-adding a line identical to canonical for non-note lines
                    other_notes = [
                        ln for ln in other_notes if ln.strip() != canonical_equiv]
                    # if we merged a description into the canonical line, drop
                    # non-note preserved notes that duplicate that description
                    if merged_desc:
                        other_notes = [
                            ln for ln in other_notes if merged_desc.lower() not in ln.lower()]
                    # filter out notes that are solely a subset of canonical tokens (dedupe)
                    canonical_tokens = set(re.findall(
                        r"\([^\)]+\)", token_parts)) if token_parts else set()
                    useful_notes: list[str] = []
                    for ln in other_notes:
                        note_tokens = set(re.findall(r"\([^\)]+\)", ln))
                        if note_tokens and canonical_tokens and note_tokens.issubset(canonical_tokens):
                            continue
                        useful_notes.append(ln)
                    # combine preserved '(note)' lines (verbatim) with the filtered useful notes
                    preserved_notes = pre_preserve_notes + useful_notes[-2:]
                    for ln in preserved_notes:
                        new_lines.append(ln)

                    if comment_block or preserved_notes or existing_descs:
                        changed = True

                # remove blank lines directly above the key (avoid leftover gaps)
                while new_lines and new_lines[-1].strip() == '':
                    new_lines.pop()

                # append the key line
                new_lines.append(lines[i])
                last_out = i + 1
            i += 1

    # append remaining lines after last_out
    new_lines.extend(lines[last_out:])

    # Trim trailing whitespace on each line but preserve blank lines.
    # Preserve the original commented preamble and any trailing postamble
    orig_lines = text.splitlines()
    header_end = None
    if orig_lines and orig_lines[0].lstrip().startswith('/*'):
        for i, ln in enumerate(orig_lines):
            if '*/' in ln:
                header_end = i
                break

    footer_start = None
    for i in range(len(orig_lines) - 1, -1, -1):
        if orig_lines[i].strip().startswith(']') or orig_lines[i].strip() == ']':
            footer_start = i + 1
            break

    # normalize lines by trimming trailing spaces
    new_lines = [ln.rstrip() for ln in new_lines]

    # restore original preamble (if present) trimmed of trailing spaces
    if header_end is not None and header_end + 1 <= len(new_lines):
        pre = [ln.rstrip() for ln in orig_lines[: header_end + 1]]
        new_lines[: header_end + 1] = pre

    # restore original postamble (if present) trimmed of trailing spaces
    if footer_start is not None:
        # find last closing bracket in new_lines
        last_bracket_idx = None
        for i in range(len(new_lines) - 1, -1, -1):
            if new_lines[i].strip().startswith(']') or new_lines[i].strip() == ']':
                last_bracket_idx = i
                break
        if last_bracket_idx is not None:
            post = [ln.rstrip() for ln in orig_lines[footer_start:]]
            new_lines[last_bracket_idx + 1:] = post

    new_text = '\n'.join(new_lines) + '\n'
    return (changed, new_text)


if __name__ == '__main__':
    main()
