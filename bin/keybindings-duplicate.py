#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Duplicate keys for and detect duplicates in VS Code keybindings.

Usage
    ./bin/keybindings-duplicate.py [INPUT] [OPTIONS]

Options
    -f, --from-keys KEYS      Comma-separated source key literals.
    -F, --from-groups GROUPS  Comma-separated source group names.
    -t, --to-keys KEYS        Comma-separated target key literals.
    -T, --to-groups GROUPS    Comma-separated target group names.
    -m, --modifiers MODS      Comma-separated modifiers for matching and emitting keys.
    -w, --when WHEN           Additional when clause for generated entries
                              (default: config.keyboardNavigation.enabled).
    -d, --detect              Run duplicate/id detection after generation.
    -h, --help                Show usage/help and exit with code 99.

Examples
        ./bin/keybindings-duplicate.py -d < references/keybindings.json
        ./bin/keybindings-duplicate.py -f h,j,k,l -t left,down,up,right -m alt,ctrl references/keybindings.json
        ./bin/keybindings-duplicate.py -F vi -T arrows -m alt,ctrl -d
        ./bin/keybindings-duplicate.py -f x,y,z -T vi,arrows

Behavior
    - Reads JSONC from INPUT or stdin when piped; input is optional for generation-only runs.
    - Never writes files. Emits diagnostics to stderr.
    - Expands source->target mappings in source-major order using the order provided.
    - `--detect` annotates duplicate objects, duplicate ids, and missing ids.

Inputs / Outputs
    stdin|INPUT|none: JSONC text with a top-level keybinding array (optional)
    stdout: transformed JSONC array text
    stderr: diagnostics and parse warnings

Important notes
    - Normalizes modifier ordering for duplicate detection.
    - Handles empty when clauses safely.
    - If keys contain commas, escape/quoting is not supported in comma lists.

Exit codes
    0   Success
    99  Usage/help displayed or missing/invalid required args
    >0  Runtime errors
"""

from __future__ import annotations
from typing import Any, List

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass


ABORTING_EXIT_CODE = 1
ERROR_EXIT_CODE = 2
USAGE_EXIT_CODE = 99
ID_RETRY_LIMIT = 100

# update CORPUS_* from keybindings-corpus.py

CORPUS_GROUPS: dict[str, list[str]] = {
    "arrows": ["left", "down", "up", "right"],
    "emacs": ["b", "n", "p", "f"],
    "kbm": ["a", "s", "w", "d"],
    "vi": ["h", "j", "k", "l"],
    "four-pack-down": ["end", "pagedown"],
    "four-pack-up": ["home", "pageup"],
    "punctuation-left": ["[", "{", ";", ","],
    "punctuation-right": ["]", "}", "'", "."],
    "fold": ["[", "]"],
    "split-horizontal": ["-", "_"],
    "split-vertical": ["=", "+", "\\", "|"],
    "action": ["a"],
    "debug": ["d"],
    "extension": ["x"],
}

CORPUS_MODIFIERS = [
    "alt",
    "ctrl",
    "ctrl+alt",
    "shift+alt",
    "ctrl+alt+meta",
    "ctrl+shift+alt",
    "shift+alt+meta",
    "ctrl+shift+alt+meta",
]

DEFAULT_MODIFIERS = "alt,shift+alt,ctrl+alt"

DEFAULT_WHEN_CLAUSE = "config.keyboardNavigation.enabled"

# prefer json5 libraries
_json5 = None
try:
    import json5 as _json5  # type: ignore
    JSON_FLAVOR = "JSON5"
except Exception:
    JSON_FLAVOR = "JSONC"


@dataclass
class ObjectRecord:
    """Represents one array object with attached leading comments."""

    leading_comments: str
    object_text: str
    parsed_obj: dict | None
    parse_error: str | None
    generated: bool = False
    force_failure_comment: str | None = None


@dataclass
class EmittedObject:
    """Represents one output object plus duplicate-check metadata."""

    text: str
    parsed_obj: dict | None
    leading_comments: str
    parse_error: str | None
    forced_comment: str | None = None


class WhenNode:
    """Base node type for when-expression AST."""

    def __init__(self, parens: bool = False):
        self.parens = parens

    def to_str(self) -> str:
        raise NotImplementedError


class WhenLeaf(WhenNode):
    """Leaf operand node."""

    def __init__(self, text: str, parens: bool = False):
        super().__init__(parens=parens)
        self.text = text

    def to_str(self) -> str:
        return self.text


class WhenNot(WhenNode):
    """Unary negation node."""

    def __init__(self, child: WhenNode, parens: bool = False):
        super().__init__(parens=parens)
        self.child = child

    def to_str(self) -> str:
        child_str = self.child.to_str()
        if isinstance(self.child, (WhenAnd, WhenOr)) and not self.child.parens:
            child_str = f"({child_str})"
        return f"!{child_str}"


class WhenAnd(WhenNode):
    """AND-expression node."""

    def __init__(self, children: list[WhenNode], parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def to_str(self) -> str:
        return " && ".join([render_when_node(child) for child in self.children])


class WhenOr(WhenNode):
    """OR-expression node."""

    def __init__(self, children: list[WhenNode], parens: bool = False):
        super().__init__(parens=parens)
        self.children = children

    def to_str(self) -> str:
        return " || ".join([render_when_node(child) for child in self.children])


def render_when_node(node: WhenNode) -> str:
    """Render an AST node back to string form."""
    inner = node.to_str()
    if node.parens:
        return f"({inner})"
    return inner


def normalize_operand(text: str) -> str:
    """Normalize whitespace within one when operand."""
    return re.sub(r"\s+", " ", text).strip()


def tokenize_when(expr: str) -> list[tuple[str, str]]:
    """Tokenize a VS Code when expression while preserving strings/regex."""
    tokens: list[tuple[str, str]] = []
    buf = ""
    i = 0
    n = len(expr)
    in_single = False
    in_double = False
    in_regex = False
    regex_escape = False
    prev_nonspace = ""

    def flush_buf() -> None:
        nonlocal buf
        if buf.strip():
            tokens.append(("OPERAND", normalize_operand(buf)))
        buf = ""

    while i < n:
        ch = expr[i]

        if in_single:
            buf += ch
            if ch == "\\":
                if i + 1 < n:
                    buf += expr[i + 1]
                    i += 1
            elif ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            buf += ch
            if ch == "\\":
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
            elif ch == "\\":
                regex_escape = True
            elif ch == "/":
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

        if ch == "/" and prev_nonspace == "~":
            in_regex = True
            buf += ch
            i += 1
            continue

        if expr.startswith("&&", i) or expr.startswith("||", i):
            flush_buf()
            tokens.append(("OP", expr[i:i + 2]))
            i += 2
            prev_nonspace = ""
            continue

        if ch in "()":
            flush_buf()
            tokens.append(("OP", ch))
            i += 1
            prev_nonspace = ch
            continue

        if ch == "!":
            nxt = expr[i + 1] if i + 1 < n else ""
            if nxt == "=":
                buf += ch
                i += 1
                prev_nonspace = ch
                continue
            if not buf.strip():
                flush_buf()
                tokens.append(("OP", "!"))
                i += 1
                prev_nonspace = "!"
                continue

        buf += ch
        if not ch.isspace():
            prev_nonspace = ch
        i += 1

    flush_buf()
    return tokens


def parse_when(expr: str) -> WhenNode:
    """Parse a when expression into a small AST."""
    tokens = tokenize_when(expr)
    idx = 0

    def peek() -> tuple[str, str] | None:
        return tokens[idx] if idx < len(tokens) else None

    def consume() -> tuple[str, str] | None:
        nonlocal idx
        token = tokens[idx] if idx < len(tokens) else None
        idx += 1
        return token

    def parse_primary() -> WhenNode:
        token = peek()
        if not token:
            return WhenLeaf("")
        if token[0] == "OP" and token[1] == "(":
            consume()
            node = parse_or()
            next_token = peek()
            if next_token and next_token[0] == "OP" and next_token[1] == ")":
                consume()
                node.parens = True
            return node
        if token[0] == "OPERAND":
            consume()
            return WhenLeaf(token[1])
        return WhenLeaf("")

    def parse_unary() -> WhenNode:
        token = peek()
        if token and token[0] == "OP" and token[1] == "!":
            consume()
            return WhenNot(parse_unary())
        return parse_primary()

    def parse_and() -> WhenNode:
        node = parse_unary()
        children = [node]
        while True:
            token = peek()
            if token and token[0] == "OP" and token[1] == "&&":
                consume()
                children.append(parse_unary())
            else:
                break
        if len(children) == 1:
            return children[0]
        return WhenAnd(children)

    def parse_or() -> WhenNode:
        node = parse_and()
        children = [node]
        while True:
            token = peek()
            if token and token[0] == "OP" and token[1] == "||":
                consume()
                children.append(parse_and())
            else:
                break
        if len(children) == 1:
            return children[0]
        return WhenOr(children)

    return parse_or()


def canonicalize_when(when_val: str) -> str:
    """Canonicalize when by flattening AND terms and deduping exact operands."""
    if not when_val:
        return ""

    def sort_and_nodes(node: WhenNode) -> None:
        if isinstance(node, WhenAnd):
            for child in node.children:
                sort_and_nodes(child)
            items = list(enumerate(node.children))

            def key_func(item: tuple[int, WhenNode]) -> tuple[list[object], int]:
                idx, child = item
                token = render_when_node(child)
                return natural_key(token), idx

            items.sort(key=key_func)
            merged = [item[1] for item in items]

            unique: list[WhenNode] = []
            seen: set[str] = set()
            for child in merged:
                token = render_when_node(child)
                if token in seen:
                    continue
                seen.add(token)
                unique.append(child)
            node.children = unique

        elif isinstance(node, WhenOr):
            for child in node.children:
                sort_and_nodes(child)

            unique = []
            seen = set()
            for child in node.children:
                token = render_when_node(child)
                if token in seen:
                    continue
                seen.add(token)
                unique.append(child)
            node.children = unique
        elif isinstance(node, WhenNot):
            sort_and_nodes(node.child)

    ast = parse_when(when_val)
    sort_and_nodes(ast)
    return render_when_node(ast)


def natural_key(text: str) -> list[object]:
    """Natural sort helper."""
    parts = re.split(r"(\d+)", text)
    result: list[object] = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            result.append(part.lower())
    return result


def strip_json_comments(text: str) -> str:
    """Remove JSONC comments while preserving strings."""

    def replacer(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith("/"):
            return ""
        return value

    pattern = r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)'  # string or comment
    return re.sub(pattern, replacer, text, flags=re.DOTALL | re.MULTILINE)


def strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before object/array endings."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def extract_preamble_postamble(text: str) -> tuple[str, str, str]:
    """Extract preamble, array-body, and postamble around top-level array."""
    i = 0
    n = len(text)
    in_string = False
    string_char = ""
    esc = False
    in_line_comment = False
    in_block_comment = False
    start = -1

    while i < n:
        ch = text[i]
        next2 = text[i:i + 2] if i + 2 <= n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == "*/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue

        if next2 == "//":
            in_line_comment = True
            i += 2
            continue
        if next2 == "/*":
            in_block_comment = True
            i += 2
            continue
        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == "[":
            start = i
            break
        i += 1

    if start == -1:
        return "", text, ""

    depth = 1
    i = start + 1
    in_string = False
    string_char = ""
    esc = False
    in_line_comment = False
    in_block_comment = False
    end = -1

    while i < n:
        ch = text[i]
        next2 = text[i:i + 2] if i + 2 <= n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == "*/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue

        if next2 == "//":
            in_line_comment = True
            i += 2
            continue
        if next2 == "/*":
            in_block_comment = True
            i += 2
            continue
        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1

    if end == -1:
        return "", text, ""

    preamble = text[:start]
    array_text = text[start + 1:end]
    postamble = text[end + 1:]
    return preamble, array_text, postamble


def group_objects_with_comments(array_text: str) -> tuple[list[tuple[str, str]], str]:
    """Split array body into (leading_comments, object_text) groups."""
    groups: list[tuple[str, str]] = []
    comments = ""
    buf = ""
    depth = 0
    in_obj = False
    for line in array_text.splitlines(keepends=True):
        stripped = line.strip()
        if not in_obj:
            if "{" in stripped:
                in_obj = True
                depth = stripped.count("{") - stripped.count("}")
                buf = line
            else:
                comments += line
        else:
            buf += line
            depth += line.count("{") - line.count("}")
            if depth == 0:
                groups.append((comments, buf))
                comments = ""
                buf = ""
                in_obj = False
    return groups, comments


def parse_comma_list(value: str) -> list[str]:
    """Split a comma list into trimmed, non-empty values."""
    parts = [part.strip() for part in value.split(",")]
    return [part for part in parts if part]


def parse_comma_list_chunks(values: list[str]) -> list[str]:
    """Parse repeated comma-list arguments while preserving option order."""
    parsed: list[str] = []
    for value in values:
        parsed.extend(parse_comma_list(value))
    return parsed


def expand_group_names(names: list[str], parser: argparse.ArgumentParser, flag_name: str) -> list[str]:
    """Expand group names to ordered key literals."""
    expanded: list[str] = []
    for raw_name in names:
        group_name = raw_name.strip().lower()
        if not group_name:
            continue
        if group_name not in CORPUS_GROUPS:
            known = ", ".join(sorted(CORPUS_GROUPS.keys()))
            parser.error(f"unknown group '{raw_name}' for {flag_name}; known groups: {known}")
        expanded.extend([token.lower() for token in CORPUS_GROUPS[group_name]])
    return expanded


def build_mapping_pairs(from_keys: list[str], to_keys: list[str]) -> list[tuple[str, str]]:
    """Create source-major ordered source->target pairs."""
    if not from_keys:
        return []
    if not to_keys:
        return [(source, source) for source in from_keys]

    pairs: list[tuple[str, str]] = []
    for source in from_keys:
        for target in to_keys:
            pairs.append((source, target))
    return pairs


def parse_jsonc_object(obj_text: str) -> Any:
    """Parse one object using JSON5 when available, else JSONC fallback."""
    try:
        if _json5 is not None:
            return _json5.loads(obj_text)
    except Exception:
        pass

    clean = strip_json_comments(obj_text)
    clean = strip_trailing_commas(clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # attempt to recover
        text = clean
        start = text.find("{")
        if start == -1:
            raise

        i = start
        n = len(text)
        depth = 0
        in_string = False
        esc = False
        string_char = ""
        while i < n:
            ch = text[i]
            if in_string:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == string_char:
                    in_string = False
            else:
                if ch == '"' or ch == "'":
                    in_string = True
                    string_char = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        obj_sub = text[start: i + 1]
                        try:
                            return json.loads(obj_sub)
                        except Exception:
                            break
            i += 1

        # couldn't recover, re-raise the original error
        return json.loads(clean)


def remove_trailing_object_comma(obj_text: str) -> str:
    """Remove a final comma after the object body if present."""
    return re.sub(r",\s*$", "", obj_text, count=1)


def normalize_modifier(modifier: str) -> str:
    """Normalize one modifier token."""
    return modifier.strip().lower()


def normalize_key_for_compare(key_value: str) -> str:
    """Normalize key text for duplicate comparisons."""
    key_value = key_value.strip().lower()
    if not key_value:
        return ""

    chord_parts = [part for part in key_value.split() if part.strip()]
    normalized_chords: list[str] = []

    for chord in chord_parts:
        key_bits = [bit.strip() for bit in chord.split("+") if bit.strip()]
        if not key_bits:
            continue
        literal = key_bits[-1]
        modifiers = [normalize_modifier(bit) for bit in key_bits[:-1]]
        unique_modifiers = list(dict.fromkeys(modifiers))

        corpus_modifier_tokens = list(
            dict.fromkeys(
                token
                for modifier in CORPUS_MODIFIERS
                for token in modifier.split("+")
                if token
            )
        )
        ordered_modifiers: list[str] = []
        for token in corpus_modifier_tokens:
            if token in unique_modifiers:
                ordered_modifiers.append(token)
        unknown_modifiers = sorted([
            token for token in unique_modifiers if token not in corpus_modifier_tokens
        ])
        ordered_modifiers.extend(unknown_modifiers)

        if ordered_modifiers:
            normalized_chords.append("+".join(ordered_modifiers + [literal]))
        else:
            normalized_chords.append(literal)

    return " ".join(normalized_chords)


def key_tail_literal(key_value: str) -> str:
    """Extract final literal key token (without modifiers) from key text."""
    cleaned = key_value.strip().lower()
    if not cleaned:
        return ""
    final_chord = cleaned.split()[-1]
    bits = [bit.strip() for bit in final_chord.split("+") if bit.strip()]
    if not bits:
        return ""
    return bits[-1]


def combine_modifier_and_key(modifier: str, key_literal: str) -> str:
    """Build a full key value from modifier and key literal."""
    modifier = modifier.strip().lower()
    key_literal = key_literal.strip().lower()
    if not modifier:
        return key_literal
    return f"{modifier}+{key_literal}"


def merge_when_clause(existing: str, extra: str) -> str:
    """Merge existing and extra when-clause strings without duplicates."""
    existing = (existing or "").strip()
    extra = (extra or "").strip()
    if not existing:
        return extra
    if not extra:
        return existing
    canonical_existing = canonicalize_when(existing)
    canonical_extra = canonicalize_when(extra)
    if canonical_extra and canonical_extra in canonical_existing:
        return existing
    return f"{extra} && {existing}"


def insert_comments_inside_object(obj_text: str, comments: list[str]) -> str:
    """Insert comment lines inside an object before its final closing brace.

    Preserves indentation of the object's last line when adding comment lines.
    If a closing brace can't be found, falls back to appending comments after the
    object text.
    """
    s = obj_text.rstrip()
    # find last closing brace
    idx = s.rfind("}")
    if idx == -1:
        return s + "\n" + "\n".join(comments)

    # determine indentation based on the line containing the last '}'
    nl = s.rfind("\n", 0, idx)
    if nl == -1:
        indent = ""
    else:
        # capture whitespace at start of the line before the '}'
        line = s[nl + 1: idx]
        m = re.match(r"(\s*)", line)
        indent = m.group(1) if m else ""

    comment_block = "\n".join([indent + c for c in comments])

    before = s[:idx]
    after = s[idx:]
    if not before.endswith("\n"):
        before = before + "\n"
    return before + comment_block + "\n" + after


def extract_command_id(command_value: str) -> str | None:
    """Extract preferred 4-hex id from command string."""
    if not command_value:
        return None
    match = re.search(r"\b([0-9a-fA-F]{4})\b", command_value)
    if match:
        return match.group(1).lower()
    return None


def extract_comment_id(comment_text: str) -> str | None:
    """Extract fallback 4-5 char id from leading comments."""
    if not comment_text:
        return None
    match = re.search(r"\b([0-9a-fA-F]{4}|[A-Za-z0-9]{5})\b", comment_text)
    if match:
        return match.group(1).lower()
    return None


def extract_commented_command_id(text: str | None) -> str | None:
    """Extract a 4-hex id from a commented or uncommented command inside text."""
    if not text:
        return None
    # look for patterns like: "command": "(...) 1a2b"
    m = re.search(r"['\"]command['\"]\s*:\s*['\"][^'\"]*?([0-9a-fA-F]{4})", text)
    if m:
        return m.group(1).lower()
    return None


def extract_any_id(parsed_obj: dict | None, leading_comments: str, object_text: str | None = None) -> str | None:
    """Extract id from command first, then commented command inside object, then leading comments."""
    if parsed_obj is not None:
        command_value = str(parsed_obj.get("command", ""))
        cmd_id = extract_command_id(command_value)
        if cmd_id:
            return cmd_id

    # attempt to find a commented-out command id inside the object's text
    commented_id = extract_commented_command_id(object_text or "")
    if commented_id:
        return commented_id

    return extract_comment_id(leading_comments)


def generate_unique_hex_id(used_ids: set[str], rng: random.Random) -> str | None:
    """Generate a unique 4-hex id with retry limit."""
    for _ in range(ID_RETRY_LIMIT):
        candidate = f"{rng.randint(0, 0xFFFF):04x}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
    return None


def make_generated_object_text(key_value: str, when_value: str, command_value: str) -> str:
    """Render a generated keybinding object as JSONC text."""
    lines = [
        "  {",
        f'    "key": {json.dumps(key_value)},',
        f'    "command": {json.dumps(command_value)},',
        f'    "when": {json.dumps(when_value)}',
        "  }",
    ]
    return "\n".join(lines) + "\n"


def load_records(array_text: str) -> tuple[list[ObjectRecord], str]:
    """Load grouped records from array text."""
    groups, trailing_comments = group_objects_with_comments(array_text)
    records: list[ObjectRecord] = []

    for leading_comments, object_text in groups:
        normalized_object_text = remove_trailing_object_comma(object_text)
        try:
            parsed_obj = parse_jsonc_object(normalized_object_text)
            records.append(
                ObjectRecord(
                    leading_comments=leading_comments,
                    object_text=normalized_object_text,
                    parsed_obj=parsed_obj,
                    parse_error=None,
                )
            )
        except Exception as exc:
            records.append(
                ObjectRecord(
                    leading_comments=leading_comments,
                    object_text=normalized_object_text,
                    parsed_obj=None,
                    parse_error=str(exc),
                )
            )

    return records, trailing_comments


def build_emitted_objects(
    records: list[ObjectRecord],
    mapping_pairs: list[tuple[str, str]],
    modifiers: list[str],
    extra_when_clause: str,
    rng: random.Random,
) -> list[EmittedObject]:
    """Build output objects list including generated mappings."""
    used_ids: set[str] = set()
    for record in records:
        found_id = extract_any_id(record.parsed_obj, record.leading_comments, record.object_text)
        if found_id:
            used_ids.add(found_id)

    emitted: list[EmittedObject] = []
    for record in records:
        emitted.append(
            EmittedObject(
                text=record.object_text,
                parsed_obj=record.parsed_obj,
                leading_comments=record.leading_comments,
                parse_error=record.parse_error,
            )
        )

    expanded_pairs: list[tuple[str, str]] = []
    for source_literal, target_literal in mapping_pairs:
        for modifier in modifiers:
            source_key = combine_modifier_and_key(modifier, source_literal)
            target_key = combine_modifier_and_key(modifier, target_literal)
            expanded_pairs.append((source_key, target_key))

    source_to_targets: dict[str, list[str]] = {}
    for source_key, target_key in expanded_pairs:
        normalized_source = normalize_key_for_compare(source_key)
        if normalized_source not in source_to_targets:
            source_to_targets[normalized_source] = []
        source_to_targets[normalized_source].append(target_key)

    if not records:
        for _, generated_key in expanded_pairs:
            generated_when = merge_when_clause("", extra_when_clause)
            generated_id = generate_unique_hex_id(used_ids, rng)
            if generated_id is None:
                failure = f"// FAILED generating id for {generated_key}/{generated_when}"
                emitted.append(
                    EmittedObject(
                        text=make_generated_object_text(
                            generated_key,
                            generated_when,
                            f"{generated_key} xxxx",
                        ),
                        parsed_obj={
                            "key": generated_key,
                            "command": f"{generated_key} xxxx",
                            "when": generated_when,
                        },
                        leading_comments="",
                        parse_error=None,
                        forced_comment=failure,
                    )
                )
                continue

            generated_command = f"{generated_key} {generated_id}"
            emitted.append(
                EmittedObject(
                    text=make_generated_object_text(generated_key, generated_when, generated_command),
                    parsed_obj={
                        "key": generated_key,
                        "command": generated_command,
                        "when": generated_when,
                    },
                    leading_comments="",
                    parse_error=None,
                )
            )
        return emitted

    for record in records:
        if record.parsed_obj is None:
            continue

        source_key = str(record.parsed_obj.get("key", ""))
        normalized_source = normalize_key_for_compare(source_key)
        matching_targets = source_to_targets.get(normalized_source)
        if not matching_targets:
            continue

        source_when = str(record.parsed_obj.get("when", ""))
        generated_when = merge_when_clause(source_when, extra_when_clause)

        for generated_key in matching_targets:
            generated_id = generate_unique_hex_id(used_ids, rng)
            if generated_id is None:
                failure = f"// FAILED generating id for {generated_key}/{generated_when}"
                emitted.append(
                    EmittedObject(
                        text=make_generated_object_text(
                            generated_key,
                            generated_when,
                            f"{generated_key} xxxx",
                        ),
                        parsed_obj={
                            "key": generated_key,
                            "command": f"{generated_key} xxxx",
                            "when": generated_when,
                        },
                        leading_comments="",
                        parse_error=None,
                        forced_comment=failure,
                    )
                )
                continue

            generated_command = f"{generated_key} {generated_id}"
            generated_obj = {
                "key": generated_key,
                "command": generated_command,
                "when": generated_when,
            }
            emitted.append(
                EmittedObject(
                    text=make_generated_object_text(generated_key, generated_when, generated_command),
                    parsed_obj=generated_obj,
                    leading_comments="",
                    parse_error=None,
                )
            )

    return emitted


def annotate_and_render(emitted: list[EmittedObject], trailing_comments: str, detect: bool) -> str:
    """Annotate and return final array-body text."""
    seen_pairs: set[tuple[str, str]] = set()
    seen_ids: dict[str, tuple[str, str]] = {}
    # collect ids already present in the emitted set (including generated ones)
    used_ids: set[str] = set()
    for itm in emitted:
        fid = extract_any_id(itm.parsed_obj, itm.leading_comments, itm.text)
        if fid:
            used_ids.add(fid)

    rng = random.Random()
    chunks: list[str] = []

    for item in emitted:
        comments: list[str] = []

        if item.parse_error:
            print(
                f"warn: skipping duplicate checks for unparsable object: {item.parse_error}",
                file=sys.stderr,
            )
        elif item.parsed_obj is not None and detect:
            key_value = str(item.parsed_obj.get("key", ""))
            when_value = str(item.parsed_obj.get("when", ""))
            normalized_key = normalize_key_for_compare(key_value)
            canonical_when = canonicalize_when(when_value)

            pair = (normalized_key, canonical_when)
            if pair in seen_pairs:
                comments.append(f"// DUPLICATE object detected for {key_value}/{when_value}")
            else:
                seen_pairs.add(pair)

            found_id = extract_any_id(item.parsed_obj, item.leading_comments, item.text)
            if found_id:
                if found_id in seen_ids:
                    comments.append(f"// DUPLICATE id {found_id} detected for {key_value}/{when_value}")
                else:
                    seen_ids[found_id] = (key_value, when_value)
            else:
                new_id = generate_unique_hex_id(used_ids, rng)
                if new_id:
                    comments.append(f'// MISSING id: "command": "{key_value} {new_id}",')

                    # duplicate ids
                    seen_ids[new_id] = (key_value, when_value)
                else:
                    comments.append(f"// MISSING id for {key_value}/{when_value}")

        if item.forced_comment:
            comments.append(item.forced_comment)

        chunk = item.text.rstrip("\n")
        if comments:
            chunk = insert_comments_inside_object(chunk, comments)
        chunks.append(chunk)

    rendered = ""
    for index, chunk in enumerate(chunks):
        rendered += chunk
        if index < len(chunks) - 1:
            rendered += ",\n"
        else:
            rendered += "\n"

    rendered += trailing_comments
    return rendered


def parse_args(argv: list[str], parser: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse CLI arguments using the provided parser instance."""
    args = parser.parse_args(argv)

    from_key_tokens = parse_comma_list_chunks(args.from_keys)
    from_group_tokens = parse_comma_list_chunks(args.from_groups)
    to_key_tokens = parse_comma_list_chunks(args.to_keys)
    to_group_tokens = parse_comma_list_chunks(args.to_groups)

    effective_from_keys = [key.lower() for key in from_key_tokens]
    effective_from_keys.extend(expand_group_names(from_group_tokens, parser, "--from-groups"))

    effective_to_keys = [key.lower() for key in to_key_tokens]
    effective_to_keys.extend(expand_group_names(to_group_tokens, parser, "--to-groups"))

    if effective_to_keys and not effective_from_keys:
        parser.error("target keys/groups require source keys/groups")

    args.effective_from_keys = effective_from_keys
    args.effective_to_keys = effective_to_keys

    return args


def read_input_text(path: str | None) -> str | None:
    """Read input from file, piped stdin, or return None when absent."""
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def main(argv: List[str] | None = None) -> int:
    """CLI entrypoint."""
    argv = sys.argv[1:] if argv is None else argv

    default_modifiers = parse_comma_list(DEFAULT_MODIFIERS)
    default_modifiers_csv = ", ".join(default_modifiers)
    corpus_groups = sorted(CORPUS_GROUPS.keys())
    corpus_groups_csv = ", ".join(corpus_groups)
    corpus_modifiers_csv = ", ".join(CORPUS_MODIFIERS)

    parser = argparse.ArgumentParser(
        description=f"Duplicate keys for and detect duplicates in VS Code keybindings.",
        epilog=(
            "Examples:\n"
            f"  %(prog)s -d < keybindings.json\n"
            "\n"
            "  %(prog)s \\\n    -f h,j,k,l -t left,down,up,right \\\n    -m alt,ctrl -w 'config.keyboardNavigation.enabled' \\\n    keybindings.json\n"
            "\n"
            "  %(prog)s \\\n    -F vi -T arrows \\\n    -m alt,ctrl -d\n"
            "\n"
            "  %(prog)s \\\n    -f x,y,z -T vi,arrows\n"
            "\n"
            f"Group choices:\n\n"
            f"  {corpus_groups_csv}"
            f"\n"
            f"\n"
            f"Modifier choices:\n\n"
            f"  {corpus_modifiers_csv}"
            f"\n"
            f"\n"
            f"Modifier defaults: {default_modifiers_csv}\n"
            f"\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--from-keys",
        action="append",
        default=[],
        metavar="KEYS",
        help="Comma-separated source key literals.",
    )
    parser.add_argument(
        "-F",
        "--from-groups",
        action="append",
        default=[],
        metavar="GROUPS",
        help=f"Comma-separated source group names.",
    )
    parser.add_argument(
        "-t",
        "--to-keys",
        action="append",
        default=[],
        metavar="KEYS",
        help="Comma-separated target key literals.",
    )
    parser.add_argument(
        "-T",
        "--to-groups",
        action="append",
        default=[],
        metavar="GROUPS",
        help=f"Comma-separated target group names.",
    )
    parser.add_argument(
        "-m",
        "--modifiers",
        default=DEFAULT_MODIFIERS,
        help=(
            f"Comma-separated modifiers. Choices: {corpus_modifiers_csv}. "
            f"Default: {default_modifiers_csv}."
        ),
    )
    parser.add_argument(
        "-w",
        "--when",
        default=DEFAULT_WHEN_CLAUSE,
        help="When clause for generated entries.",
    )
    parser.add_argument(
        "-d",
        "--detect",
        action="store_true",
        help="Run duplicate and id detection over final object set.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help=f"Optional {JSON_FLAVOR} input file path.",
    )

    if not argv:
        parser.print_help()
        return USAGE_EXIT_CODE

    try:
        args = parse_args(argv, parser)
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 2
        try:
            numeric_code = int(code)
            if numeric_code in (0, 2):
                return USAGE_EXIT_CODE
            return numeric_code
        except Exception:
            return USAGE_EXIT_CODE

    try:
        raw_text = read_input_text(args.input)
    except Exception as exc:
        print(f"error: failed to read input: {exc}", file=sys.stderr)
        return ERROR_EXIT_CODE

    has_generation = bool(args.effective_from_keys) or bool(args.effective_to_keys)
    if raw_text is None and not has_generation and not args.detect:
        print("error: no input provided and no generation/detect options were requested", file=sys.stderr)
        return USAGE_EXIT_CODE

    mapping_pairs = build_mapping_pairs(args.effective_from_keys, args.effective_to_keys)

    modifiers = parse_comma_list(args.modifiers)
    if not modifiers:
        modifiers = parse_comma_list(DEFAULT_MODIFIERS)

    if raw_text is None:
        preamble = ""
        postamble = ""
        records = []
        trailing_comments = ""
    else:
        preamble, array_text, postamble = extract_preamble_postamble(raw_text)
        records, trailing_comments = load_records(array_text)

    rng = random.Random()
    emitted = build_emitted_objects(
        records=records,
        mapping_pairs=mapping_pairs,
        modifiers=modifiers,
        extra_when_clause=args.when,
        rng=rng,
    )

    rendered_body = annotate_and_render(emitted, trailing_comments, detect=args.detect)
    output_text = f"{preamble}[{rendered_body}]{postamble}"
    sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
