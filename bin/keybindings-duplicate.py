#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Duplicate/map VS Code keybindings JSONC entries while preserving comments.

Usage
    ./bin/keybindings-duplicate.py --from KEYS --to KEYS [OPTIONS] [FILE]

Options
    -f, --from KEYS         Comma-separated source keys to map from (required).
    -t, --to KEYS           Comma-separated target keys to map to (required).
    -k, --keys KEYS         Comma-separated source keys to duplicate (optional; defaults to --from keys).
    -m, --modifiers MODS    Comma-separated modifiers for generated keys (default: alt,shift+alt,ctrl+alt).
    -w, --when-clause WHEN  Additional when clause for generated entries
                            (default: config.keyboardNavigation.enabled).
    -h, --help              Show usage/help and exit with code 99.

Examples
    ./bin/keybindings-duplicate.py -f h,j,k,l -t left,down,up,right < references/keybindings.json
    ./bin/keybindings-duplicate.py -f h,j,k,l -t left,down,up,right -m alt < references/keybindings.corpus.jsonc
    for f in references/keybindings.corpus.*.json; do
      ./bin/keybindings-duplicate.py -f h,j,k,l -t left,down,up,right < "$f" > /tmp/out.jsonc
    done

Behavior
    - Reads JSONC from FILE or stdin, preserves preamble/postamble and comments, and writes transformed JSONC to stdout.
    - Never writes files. Emits diagnostics to stderr.
    - Annotates duplicate object pairs by normalized key + canonical when expression.
    - Annotates duplicate ids and generates new 4-hex command ids with collision retries.

Inputs / Outputs
    stdin|FILE: JSONC text with a top-level keybinding array
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
from typing import Any
from typing import NoReturn

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass


USAGE_EXIT_CODE = 99
RUNTIME_EXIT_CODE = 2
ID_RETRY_LIMIT = 100
DEFAULT_MODIFIERS = "alt,shift+alt,ctrl+alt"
DEFAULT_WHEN_CLAUSE = "config.keyboardNavigation.enabled"
MODIFIER_ORDER = ["ctrl", "shift", "alt", "meta", "cmd", "win"]


class UsageArgumentParser(argparse.ArgumentParser):
    """Argument parser that exits with code 99 for help and usage errors."""

    def error(self, message: str) -> NoReturn:
        # type signature matches base class (which returns NoReturn)
        self.print_usage(sys.stderr)
        self.exit(USAGE_EXIT_CODE, f"{self.prog}: error: {message}\n")

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        # also matches base class signature
        if message:
            stream = sys.stdout if status == 0 else sys.stderr
            stream.write(message)
        if status in (0, 2):
            raise SystemExit(USAGE_EXIT_CODE)
        raise SystemExit(status)


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


def parse_jsonc_object(obj_text: str) -> Any:
    """Parse one JSONC object using json5 if available, else fallback stripper."""
    try:
        import json5  # type: ignore

        return json5.loads(obj_text)
    except Exception:
        clean = strip_json_comments(obj_text)
        clean = strip_trailing_commas(clean)
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

        ordered_modifiers: list[str] = []
        for token in MODIFIER_ORDER:
            if token in unique_modifiers:
                ordered_modifiers.append(token)
        unknown_modifiers = sorted([token for token in unique_modifiers if token not in MODIFIER_ORDER])
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


def extract_any_id(parsed_obj: dict | None, leading_comments: str) -> str | None:
    """Extract id from command first, then leading comments."""
    if parsed_obj is not None:
        command_value = str(parsed_obj.get("command", ""))
        cmd_id = extract_command_id(command_value)
        if cmd_id:
            return cmd_id
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
    mapping: dict[str, str],
    key_filter: set[str],
    modifiers: list[str],
    extra_when_clause: str,
    rng: random.Random,
) -> list[EmittedObject]:
    """Build output objects list including generated duplicates."""
    used_ids: set[str] = set()
    for record in records:
        found_id = extract_any_id(record.parsed_obj, record.leading_comments)
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

        if record.parsed_obj is None:
            continue

        source_key = str(record.parsed_obj.get("key", ""))
        source_tail = key_tail_literal(source_key)
        if not source_tail:
            continue
        if source_tail not in mapping:
            continue
        if key_filter and source_tail not in key_filter:
            continue

        target_tail = mapping[source_tail]
        source_when = str(record.parsed_obj.get("when", ""))
        generated_when = merge_when_clause(source_when, extra_when_clause)

        for modifier in modifiers:
            generated_key = combine_modifier_and_key(modifier, target_tail)
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


def annotate_and_render(emitted: list[EmittedObject], trailing_comments: str) -> str:
    """Annotate duplicates and return final array-body text."""
    seen_pairs: set[tuple[str, str]] = set()
    seen_ids: dict[str, tuple[str, str]] = {}
    chunks: list[str] = []

    for item in emitted:
        comments: list[str] = []

        if item.parse_error:
            print(
                f"warn: skipping duplicate checks for unparsable object: {item.parse_error}",
                file=sys.stderr,
            )
        elif item.parsed_obj is not None:
            key_value = str(item.parsed_obj.get("key", ""))
            when_value = str(item.parsed_obj.get("when", ""))
            normalized_key = normalize_key_for_compare(key_value)
            canonical_when = canonicalize_when(when_value)

            pair = (normalized_key, canonical_when)
            if pair in seen_pairs:
                comments.append(f"// DUPLICATE object detected for {key_value}/{when_value}")
            else:
                seen_pairs.add(pair)

            found_id = extract_any_id(item.parsed_obj, item.leading_comments)
            if found_id:
                if found_id in seen_ids:
                    comments.append(f"// DUPLICATE id {found_id} detected for {key_value}/{when_value}")
                else:
                    seen_ids[found_id] = (key_value, when_value)

        if item.forced_comment:
            comments.append(item.forced_comment)

        chunk = item.text.rstrip("\n")
        if comments:
            chunk += "\n" + "\n".join(comments)
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = UsageArgumentParser(
        description=(
            "Duplicate/map VS Code keybindings entries from JSONC while preserving comments. "
            "Writes transformed JSONC to stdout."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-f", "--from", dest="from_keys", required=True, help="Comma-separated source keys.")
    parser.add_argument("-t", "--to", dest="to_keys", required=True, help="Comma-separated target keys.")
    parser.add_argument("-k", "--keys", default="", help="Optional comma-separated source keys filter.")
    parser.add_argument("-m", "--modifiers", default=DEFAULT_MODIFIERS, help="Comma-separated modifiers.")
    parser.add_argument(
        "-w",
        "--when-clause",
        default=DEFAULT_WHEN_CLAUSE,
        help="Additional when clause for generated entries.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSONC file path or '-' for stdin (default).",
    )

    args = parser.parse_args(argv)

    from_keys = parse_comma_list(args.from_keys)
    to_keys = parse_comma_list(args.to_keys)
    if len(from_keys) != len(to_keys):
        parser.error("--from and --to must contain the same number of keys")
    if not from_keys:
        parser.error("--from must contain at least one key")

    return args


def read_input_text(path: str) -> str:
    """Read input from stdin or file path."""
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    """Run CLI entrypoint."""
    argv = sys.argv[1:] if argv is None else argv

    try:
        args = parse_args(argv)
    except SystemExit as exc:
        code = exc.code if exc.code is not None else USAGE_EXIT_CODE
        try:
            return int(code)
        except Exception:
            return USAGE_EXIT_CODE

    try:
        raw_text = read_input_text(args.input)
    except Exception as exc:
        print(f"error: failed to read input: {exc}", file=sys.stderr)
        return RUNTIME_EXIT_CODE

    from_keys = [key.lower() for key in parse_comma_list(args.from_keys)]
    to_keys = [key.lower() for key in parse_comma_list(args.to_keys)]
    mapping = {source: target for source, target in zip(from_keys, to_keys)}

    keys_arg = parse_comma_list(args.keys)
    key_filter = set([key.lower() for key in keys_arg]) if keys_arg else set(from_keys)

    modifiers = parse_comma_list(args.modifiers)
    if not modifiers:
        modifiers = parse_comma_list(DEFAULT_MODIFIERS)

    preamble, array_text, postamble = extract_preamble_postamble(raw_text)
    records, trailing_comments = load_records(array_text)

    rng = random.Random()
    emitted = build_emitted_objects(
        records=records,
        mapping=mapping,
        key_filter=key_filter,
        modifiers=modifiers,
        extra_when_clause=args.when_clause,
        rng=rng,
    )

    rendered_body = annotate_and_render(emitted, trailing_comments)
    output_text = f"{preamble}[{rendered_body}]{postamble}"
    sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
