#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Duplicate keys for and detect duplicates in VS Code keybindings.

Usage
    keybindings-duplicate.py [INPUT] [OPTIONS]

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
        keybindings-duplicate.py -d < references/keybindings.json
        keybindings-duplicate.py -f h,j,k,l -t left,down,up,right -m alt,ctrl references/keybindings.json
        keybindings-duplicate.py -F vi -T arrows -m alt,ctrl -d
        keybindings-duplicate.py -f x,y,z -T vi,arrows

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
from typing import List

import argparse
import json
import re
import sys
from dataclasses import dataclass
from vscode_keynav import io as _io
from vscode_keynav import keybindings as _keybindings
from vscode_keynav import corpus as _corpus
import signal


ABORTING_EXIT_CODE = 1
ERROR_EXIT_CODE = 2
USAGE_EXIT_CODE = 99

# update CORPUS_* from keybindings-corpus.py

CORPUS_GROUPS: dict[str, list[str]] = {
    "arrows": ["left", "down", "up", "right"],
    "emacs": ["b", "n", "p", "f"],
    "kbm": ["a", "s", "w", "d"],
    "vi": ["h", "j", "k", "l"],
    "four-pack-down": ["end", "pagedown"],
    "four-pack-up": ["home", "pageup"],
    "four-pack": ["home", "pageup", "end", "pagedown"],
    "punctuation-left": ["[", "{", ";", ","],
    "punctuation-right": ["]", "}", "'", "."],
    "punctuation": ["[", "{", ";", ",", "]", "}", "'", "."],
    "fold": ["[", "]"],
    "split-horizontal": ["-", "_"],
    "split-vertical": ["=", "+", "\\", "|"],
    "split": ["-", "_", "=", "+", "\\", "|"],
    "juke": ["[", "{", ";", ",", "]", "}", "'", ".", "home", "pageup", "end", "pagedown"],
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


def remove_trailing_object_comma(obj_text: str) -> str:
    """Remove a final comma after the object body if present."""

    return re.sub(r",\s*$", "", obj_text, count=1)


# Use normalize/canonicalize parsers from keynav package where available.


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
    canonical_existing = _keybindings._canonicalize_when(existing)
    canonical_extra = _keybindings._canonicalize_when(extra)
    if canonical_extra and canonical_extra in canonical_existing:
        return existing
    return f"{extra} && {existing}"


def has_non_negated_when_context(expr: str, context_name: str) -> bool:
    """Return True when a context appears in expr without leading negation."""

    if not expr or not context_name:
        return False

    for token in _keybindings._split_when_contexts(expr):
        normalized = token.strip()
        while normalized.startswith("(") and normalized.endswith(")") and len(normalized) >= 2:
            normalized = normalized[1:-1].strip()
        if not normalized or normalized.startswith("!"):
            continue
        if normalized == context_name or normalized.startswith(f"{context_name} "):
            return True
    return False


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

    # indentation based on the line containing the last '}'
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

    before = re.sub(r"(?:\n\s*)+\Z", "\n", before)

    if not before.endswith("\n"):
        before = before + "\n"
    return before + comment_block + "\n" + after


def extract_command_id(command_value: str) -> str | None:
    """Extract preferred 5 character hex id from command string (accepts 4 or 5 character ids)."""

    if not command_value:
        return None

    match = re.search(r"\b([0-9a-fA-F]{4,5})\b", command_value)
    if match:
        return match.group(1).lower()
    return None


def extract_comment_id(comment_text: str) -> str | None:
    """Extract fallback 4 or 5 character id from leading comments."""

    if not comment_text:
        return None
    match = re.search(r"\b([0-9a-fA-F]{4}|[A-Za-z0-9]{5})\b", comment_text)
    if match:
        return match.group(1).lower()
    return None


def extract_commented_command_id(text: str | None) -> str | None:
    """Extract a 4 or 5 character hex id from a commented or uncommented command inside text."""

    if not text:
        return None
    matches = re.findall(r"""['"]command['"]\s*:\s*['"]([^'\"]*?([0-9a-fA-F]{4,5}))['"]""", text)
    if matches:
        # matches is a list of tuples; take the last captured hex-group (4 or 5 chars)
        last = matches[-1]
        # last is (full_match_without_quotes, group_hex)
        return last[1].lower()
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


def parse_record_object(obj_text: str) -> dict:
    """Parse one keybinding object, preferring keynav parser and tolerating JSON5 syntax."""

    parsed = _keybindings._parse_object(obj_text)
    if isinstance(parsed, dict):
        return parsed

    cleaned = _keybindings._strip_trailing_commas(_keybindings._strip_json_comments(obj_text)).strip()
    try:
        reparsed = json.loads(cleaned)
        if isinstance(reparsed, dict):
            return reparsed
    except Exception:
        pass

    try:
        import json5  # type: ignore

        reparsed = json5.loads(obj_text)
        if isinstance(reparsed, dict):
            return reparsed
    except Exception:
        pass

    raise ValueError("unable to parse keybinding object")


def load_records(array_text: str) -> tuple[list[ObjectRecord], str]:
    """Load grouped records from array text."""

    groups, trailing_comments = _keybindings._group_objects_with_comments(array_text)
    records: list[ObjectRecord] = []

    for leading_comments, object_text in groups:
        normalized_object_text = remove_trailing_object_comma(object_text)
        try:
            parsed_obj = parse_record_object(normalized_object_text)
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
    automatic_when_contexts: bool = False,
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
        normalized_source = _keybindings._normalize_key_for_compare(source_key)
        if normalized_source not in source_to_targets:
            source_to_targets[normalized_source] = []
        source_to_targets[normalized_source].append(target_key)

    if not records:
        for _, generated_key in expanded_pairs:
            # derive automatic contexts for generated-only mode
            combined_extra = extra_when_clause or ""
            if automatic_when_contexts:
                auto_ctxs: list[str] = []
                key_norm = _keybindings._normalize_key(generated_key)
                if key_norm in _corpus._JUKE_GROUP:
                    auto_ctxs.append("config.keyboardNavigation.juke.enabled")
                if key_norm in _corpus._SPLIT_GROUP:
                    auto_ctxs.append("config.keyboardNavigation.split.enabled")
                if has_non_negated_when_context(extra_when_clause or "", "terminalFocus"):
                    auto_ctxs.append("config.keyboardNavigation.terminal.enabled")
                if auto_ctxs:
                    if combined_extra:
                        combined_extra = " && ".join([combined_extra, " && ".join(auto_ctxs)])
                    else:
                        combined_extra = " && ".join(auto_ctxs)

            generated_when = merge_when_clause("", combined_extra)

            # seed based on generated key + when clause
            generated_id = _corpus._generate_key_id(used_ids, generated_key, generated_when)
            if generated_id is None:
                failure = f"// FAILED generating id for {generated_key}/{generated_when}"
                emitted.append(
                    EmittedObject(
                        text=make_generated_object_text(
                            generated_key,
                            generated_when,
                            f"{generated_key} xxxxx",
                        ),
                        parsed_obj={
                            "key": generated_key,
                            "command": f"{generated_key} xxxxx",
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
        normalized_source = _keybindings._normalize_key_for_compare(source_key)
        matching_targets = source_to_targets.get(normalized_source)
        if not matching_targets:
            continue

        source_when = str(record.parsed_obj.get("when", ""))
        # build automatic contexts derived from the key/record when requested
        combined_extra = extra_when_clause or ""
        if automatic_when_contexts:
            auto_ctxs = []
            # compute per-generated-key below inside loop since key varies

        for generated_key in matching_targets:
            # per-generated-key automatic contexts
            per_combined_extra = combined_extra
            if automatic_when_contexts:
                key_norm = _keybindings._normalize_key(generated_key)
                if key_norm in _corpus._JUKE_GROUP and "config.keyboardNavigation.juke.enabled" not in per_combined_extra:
                    auto_ctxs = ["config.keyboardNavigation.juke.enabled"]
                else:
                    auto_ctxs = []
                if key_norm in _corpus._SPLIT_GROUP and "config.keyboardNavigation.split.enabled" not in per_combined_extra:
                    auto_ctxs.append("config.keyboardNavigation.split.enabled")
                if (
                    has_non_negated_when_context(source_when, "terminalFocus")
                    or has_non_negated_when_context(per_combined_extra, "terminalFocus")
                ):
                    if "config.keyboardNavigation.terminal.enabled" not in per_combined_extra:
                        auto_ctxs.append("config.keyboardNavigation.terminal.enabled")
                if auto_ctxs:
                    if per_combined_extra:
                        per_combined_extra = " && ".join([per_combined_extra, " && ".join(auto_ctxs)])
                    else:
                        per_combined_extra = " && ".join(auto_ctxs)

            generated_when = merge_when_clause(source_when, per_combined_extra)
            generated_id = _corpus._generate_key_id(used_ids, generated_key, generated_when)
            if generated_id is None:
                failure = f"// FAILED generating id for {generated_key}/{generated_when}"
                emitted.append(
                    EmittedObject(
                        text=make_generated_object_text(
                            generated_key,
                            generated_when,
                            f"{generated_key} xxxxx",
                        ),
                        parsed_obj={
                            "key": generated_key,
                            "command": f"{generated_key} xxxxx",
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


def annotate_and_render(emitted: list[EmittedObject], trailing_comments: str, detect: bool, correct_duplicate_ids: bool = False) -> str:
    """Annotate and return final array-body text."""

    seen_pairs: set[tuple[str, str]] = set()
    seen_ids: dict[str, tuple[str, str]] = {}

    # extract ids from the `command` field (preferred) or a commented `"command"` inside the object
    used_ids: set[str] = set()
    for itm in emitted:
        fid = None
        if itm.parsed_obj is not None:
            fid = extract_command_id(str(itm.parsed_obj.get("command", "")))
        if not fid:
            fid = extract_commented_command_id(itm.text)
        if fid:
            used_ids.add(fid)

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
            normalized_key = _keybindings._normalize_key_for_compare(key_value)
            canonical_when = _keybindings._canonicalize_when(when_value)

            pair = (normalized_key, canonical_when)
            if pair in seen_pairs:
                comments.append(f"// DUPLICATE object detected for {key_value}/{when_value}")
            else:
                seen_pairs.add(pair)

            found_id = extract_any_id(item.parsed_obj, item.leading_comments, item.text)
            if found_id:
                if found_id in seen_ids:
                    if correct_duplicate_ids:
                        new_id = _corpus._generate_key_id(used_ids, key_value, when_value)
                        if new_id:
                            pattern = re.compile(r"\b" + re.escape(found_id) + r"\b", flags=re.IGNORECASE)
                            item.text = pattern.sub(new_id, item.text, count=1)

                            if item.parsed_obj is not None and isinstance(item.parsed_obj.get("command", None), str):
                                item.parsed_obj["command"] = pattern.sub(new_id, str(item.parsed_obj["command"]), count=1)
                            seen_ids[new_id] = (key_value, when_value)
                            # suppressed stderr output during automatic corrections
                        else:
                            comments.append(f"// FAILED generating id for duplicate {found_id} on {key_value}/{when_value}")
                    else:
                        comments.append(f"// DUPLICATE id {found_id} detected for {key_value}/{when_value}")
                else:
                    seen_ids[found_id] = (key_value, when_value)
            else:
                new_id = _corpus._generate_key_id(used_ids, key_value, when_value)
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


# `read_input_text` is provided by `keynav.io` package


def main(argv: List[str] | None = None) -> int:
    """CLI entrypoint."""

    def _signal_handler(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _signal_handler)
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
    except Exception:
        pass

    argv = sys.argv[1:] if argv is None else argv

    default_modifiers = parse_comma_list(DEFAULT_MODIFIERS)
    default_modifiers_csv = ", ".join(default_modifiers)
    corpus_groups = sorted(CORPUS_GROUPS.keys())
    corpus_groups_csv = ", ".join(corpus_groups)
    corpus_modifiers_csv = ", ".join(CORPUS_MODIFIERS)

    parser = argparse.ArgumentParser(
        description="Duplicate keys for and detect duplicates in VS Code keybindings.",
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
        help="Comma-separated list of source key literals",
    )
    parser.add_argument(
        "-F",
        "--from-groups",
        action="append",
        default=[],
        metavar="GROUPS",
        help="Comma-separated list of source key group names",
    )
    parser.add_argument(
        "-t",
        "--to-keys",
        action="append",
        default=[],
        metavar="KEYS",
        help="Comma-separated target key literals",
    )
    parser.add_argument(
        "-T",
        "--to-groups",
        action="append",
        default=[],
        metavar="GROUPS",
        help="Comma-separated list of target key group names",
    )
    parser.add_argument(
        "-m",
        "--modifiers",
        default=DEFAULT_MODIFIERS,
        help=(
            f"Comma-separated list of modifiers"
        ),
    )
    parser.add_argument(
        "-w",
        "--when",
        default=DEFAULT_WHEN_CLAUSE,
        help="When clause for generated entries",
    )
    parser.add_argument(
        "-a",
        "--automatic-when-contexts",
        action="store_true",
        help=(
            "Automatically inject config.keyboardNavigation.*.enabled contexts\n"
            "(juke/split/terminal) into generated/augmented when-clauses"
        ),
    )
    parser.add_argument(
        "-d",
        "--detect",
        action="store_true",
        help="Run duplicate and id detection over final object set",
    )
    parser.add_argument(
        "-c",
        "--correct-duplicate-ids",
        dest="correct_duplicate_ids",
        action="store_true",
        help="When detecting duplicate ids, replace duplicate ids with new unique ids instead of annotating",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help=f"Optional {JSON_FLAVOR} input file path",
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
        raw_text = _io._read_input_text(args.input)
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
        preamble, array_text, postamble = _keybindings._extract_preamble_postamble(raw_text)
        records, trailing_comments = load_records(array_text)

    emitted = build_emitted_objects(
        records=records,
        mapping_pairs=mapping_pairs,
        modifiers=modifiers,
        extra_when_clause=args.when,
        automatic_when_contexts=bool(getattr(args, "automatic_when_contexts", False)),
    )

    rendered_body = annotate_and_render(
        emitted,
        trailing_comments,
        detect=args.detect,
        correct_duplicate_ids=bool(getattr(args, "correct_duplicate_ids", False)),
    )
    output_text = f"{preamble}[{rendered_body}]{postamble}"
    sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(ABORTING_EXIT_CODE)
