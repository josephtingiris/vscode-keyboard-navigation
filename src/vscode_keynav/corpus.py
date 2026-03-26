"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common corpus functions.
"""

from __future__ import annotations

import re
import hashlib

from typing import Any, Dict, List

from .keybindings import _canonicalize_when, _key_tail_literal, _normalize_key


#
# globals & constants
#

_GENERATED_KEY_IDS: set[str] = set()

# corpus generation constants originally defined in bin/keybindings-corpus.py

_MODIFIERS_SINGLE = [
    "alt",
    "ctrl",
]

_MODIFIERS_MULTI = [
    "ctrl+alt",
    "shift+alt",
    "ctrl+alt+meta",
    "ctrl+shift+alt",
    "shift+alt+meta",
    "ctrl+shift+alt+meta",
]

_ARROW_GROUP = ("left", "down", "up", "right")
_LEFT, _DOWN, _UP, _RIGHT = _ARROW_GROUP

_EMACS_GROUP = ("b", "n", "p", "f")
_KBM_GROUP = ("a", "s", "w", "d")
_VI_GROUP = ("h", "j", "k", "l")

_LETTER_GROUPS = {
    "emacs": _EMACS_GROUP,
    "kbm": _KBM_GROUP,
    "vi": _VI_GROUP,
}

_FOUR_PACK_DOWN_GROUP = {"end", "pagedown"}
_FOUR_PACK_UP_GROUP = {"home", "pageup"}
_FOUR_PACK_GROUP = _FOUR_PACK_DOWN_GROUP | _FOUR_PACK_UP_GROUP

_PUNCTUATION_LEFT_GROUP = {"[", "{", ";", ","}
_PUNCTUATION_RIGHT_GROUP = {"]", "}", "'", "."}
_PUNCTUATION_GROUP = _PUNCTUATION_LEFT_GROUP | _PUNCTUATION_RIGHT_GROUP

_FOLD_LEFT_GROUP = {"["}
_FOLD_RIGHT_GROUP = {"]"}
_FOLD_GROUP = _FOLD_LEFT_GROUP | _FOLD_RIGHT_GROUP

_LEFT_GROUP = set(_PUNCTUATION_LEFT_GROUP)
_DOWN_GROUP = set(_FOUR_PACK_DOWN_GROUP)
_UP_GROUP = set(_FOUR_PACK_UP_GROUP)
_RIGHT_GROUP = set(_PUNCTUATION_RIGHT_GROUP)

_DIRECTIONAL_GROUP_TAGS = [
    ("(left)", 0, _PUNCTUATION_LEFT_GROUP),
    ("(down)", 1, _FOUR_PACK_DOWN_GROUP),
    ("(up)", 2, _FOUR_PACK_UP_GROUP),
    ("(right)", 3, _PUNCTUATION_RIGHT_GROUP),
]

_DIRECTIONAL_KEY_TAGS = {
    tag: {_ARROW_GROUP[idx]} | extra_keys | {
        group[idx] for group in _LETTER_GROUPS.values() if idx < len(group)
    }
    for tag, idx, extra_keys in _DIRECTIONAL_GROUP_TAGS
}

_JUKE_GROUP = _PUNCTUATION_GROUP | _FOUR_PACK_GROUP

_SPLIT_HORIZONTAL_GROUP = {"-", "_"}
_SPLIT_VERTICAL_GROUP = {"=", "+", "\\", "|"}
_SPLIT_GROUP = _SPLIT_HORIZONTAL_GROUP | _SPLIT_VERTICAL_GROUP

_ACTION_GROUP = {"a"}
_ALTERNATE_ACTION_KEY = 'l'

_DEBUG_GROUP = {"d"}
_ALTERNATE_DEBUG_KEY = 'j'

_EXTENSION_GROUP = {"x"}
_ALTERNATE_EXTENSION_KEY = 'n'

_FIN_TAGS = {
    "alt": ("(gold)", ("(self)", "(0)", "(gold)", "(X)")),
    "shift+alt": ("(red)", ("(move)", "(1)", "(red)", "(A)")),
    "ctrl+alt": ("(blue)", ("(jump)", "(2)", "(blue)", "(B)")),
    "ctrl+alt+meta": ("(black)", ("(warp)", "(3)", "(black)", "(C)")),
    "ctrl+shift+alt": ("(yellow)", ("(change)", "(!)", "(yellow)", "(+)")),
}

_TAG_ORDER = [
    "(corpus)",
    "(map)",
    "(down)", "(left)", "(right)", "(up)",
    "(horizontal)", "(vertical)",
    "(arrow)", "(emacs)", "(kbm)", "(vi)",
    "(juke)", "(split)",
    "(fold)",
    "(move)", "(jump)", "(warp)", "(change)", "(assign)",
    "(!)",
    "(0)", "(1)", "(2)", "(3)",
    "(self)",
    "(gold)", "(red)", "(blue)", "(black)", "(yellow)",
    "(X)", "(A)", "(B)", "(C)",
    "(+)",
    "(debug)", "(action)", "(extension)",
    "(chord)",
    "(primary)", "(secondary)", "(panel)",
    "(editor)", "(terminal)", "(explorer)",
    "(text)",
    "(multiple)",
    "(immutable)",
    "(block)", "(pass)",
]

_WHEN_CONTEXT_SELECTORS = [
    (_ARROW_GROUP, "config.keyboardNavigation.keys.arrows"),
    (_JUKE_GROUP, "config.keyboardNavigation.juke.enabled"),
    (_SPLIT_GROUP, "config.keyboardNavigation.split.enabled"),
]

_WHEN_TAG_SELECTORS = [
    ("auxiliarBarFocus", "(secondary)"),
    ("config.keyboardNavigation.terminal.enabled", "(terminal)"),
    ("config.keyboardNavigation.enabledMap", "(map)"),
    ("editorFocus", "(editor)"),
    ("editorTextFocus", "(editor)"),
    ("editorTextFocus", "(text)"),
    ("multipleEditorGroups", "(multiple)"),
    (r"/(?i:(?<!!)\\b\\S*multiple\\S*\\b)/", "(multiple)"),
    (r"/(?i:) !neovim.init/", "(monaco)"),
    ("neovim.init", "(neovim)"),
    ("panelFocus", "(panel)"),
    ("sideBarFocus", "(primary)"),
    ("terminalFocus", "(terminal)"),
    (r"/(?i:(?<!!)\\b\\S*readonly\\S*\\b)/", "(immutable)"),
]


#
# functions
#


def _augment_when_clause(base_when: str, contexts: List[str]) -> str:
    """Augment a base when clause by OR-ing the provided context clauses."""

    if not contexts:
        return base_when or ""
    ctx_clause = " || ".join([c.strip() for c in contexts if c and c.strip()])
    if not base_when or not base_when.strip():
        return ctx_clause
    return f"({base_when}) && ({ctx_clause})"


def _generate_key_id(used_ids: set[str], key: str, when: str) -> str | None:
    """Generate a deterministic (consistent) key ID.

    Strategy:
    - compute SHA256 of "{key}||{when}" and take first 4 hex chars as base
    - on collision increment base (mod 0x10000) until unused
    - fallback to a 12-char SHA prefix and ensure uniqueness by appending
      a numeric suffix if necessary
    """
    h = hashlib.sha256(f"{key}||{when}".encode()).hexdigest()

    # try 4-hex id first
    base = int(h[:4], 16)
    for delta in range(0x10000):
        val = (base + delta) & 0xFFFF
        candidate = f"{val:04x}"
        if candidate not in used_ids and candidate not in _GENERATED_KEY_IDS:
            used_ids.add(candidate)
            _GENERATED_KEY_IDS.add(candidate)
            return candidate

    # fallback: use a 12-char SHA prefix
    id12 = h[:12]
    if id12 not in used_ids and id12 not in _GENERATED_KEY_IDS:
        used_ids.add(id12)
        _GENERATED_KEY_IDS.add(id12)
        return id12

    # if collision, append a numeric suffix until unique (bounded loop)
    for suffix in range(1, 10000):
        candidate = f"{id12}{suffix}"
        if candidate not in used_ids and candidate not in _GENERATED_KEY_IDS:
            used_ids.add(candidate)
            _GENERATED_KEY_IDS.add(candidate)
            return candidate

    # last resort: try longer slices of the hash
    for L in range(13, len(h) + 1):
        candidate = h[:L]
        if candidate not in used_ids and candidate not in _GENERATED_KEY_IDS:
            used_ids.add(candidate)
            _GENERATED_KEY_IDS.add(candidate)
            return candidate

    return None


def _tags_for(
    key: str,
    mod: str = "",
    when_clause: str | None = None,
    command: str | None = None,
    existing_comments: str | None = None,
) -> List[str]:
    """Return a list of tags for a keybinding object (command, key-tail, and when)."""

    if not when_clause or "config.keyboardNavigation.enabled" not in when_clause:
        return []

    ordered_tags: List[str] = ["[keynav]"]
    dynamic_tags: set[str] = set()

    key_norm = _normalize_key(key)

    nav_group_clauses = {
        name
        for name in _LETTER_GROUPS
        if f"config.keyboardNavigation.keys.letters == '{name}'" in when_clause
    }

    for tag, keys in _DIRECTIONAL_KEY_TAGS.items():
        if key_norm not in keys:
            continue
        if key_norm in _ARROW_GROUP or key_norm in _PUNCTUATION_GROUP:
            dynamic_tags.add(tag)
            continue
        if any(key_norm in _LETTER_GROUPS[name] for name in nav_group_clauses):
            dynamic_tags.add(tag)

    if "config.keyboardNavigation.keys.arrows" in when_clause:
        dynamic_tags.add("(arrow)")

    for name in _LETTER_GROUPS:
        clause = f"config.keyboardNavigation.keys.letters == '{name}'"
        if clause in when_clause:
            dynamic_tags.add(f"({name})")

    if key_norm in _FOLD_GROUP:
        dynamic_tags.add("(fold)")
    if key_norm in _JUKE_GROUP:
        dynamic_tags.add("(juke)")
    if key_norm in _SPLIT_GROUP:
        dynamic_tags.add("(split)")
    if key_norm in _SPLIT_HORIZONTAL_GROUP:
        dynamic_tags.add("(horizontal)")
    if key_norm in _SPLIT_VERTICAL_GROUP:
        dynamic_tags.add("(vertical)")

    if "config.keyboardNavigation.chords.debug" in when_clause:
        dynamic_tags.add("(debug)")
    if "config.keyboardNavigation.chords.action" in when_clause:
        dynamic_tags.add("(action)")
    if "config.keyboardNavigation.chords.extension" in when_clause:
        dynamic_tags.add("(extension)")

    if command and "corpus" in command.lower():
        dynamic_tags.add("(corpus)")

    if existing_comments and "corpus" in existing_comments.lower():
        dynamic_tags.add("(corpus)")

    if existing_comments and "(map)" in existing_comments.lower():
        dynamic_tags.add("(map)")

    if command and command.strip().lower() == "-noop":
        dynamic_tags.add("(pass)")

    if command and command.strip().lower() == "noop":
        dynamic_tags.add("(block)")

    fin_entry = _FIN_TAGS.get(mod)
    if fin_entry:
        color_tag, meta_tags = fin_entry
        if color_tag:
            dynamic_tags.add(color_tag)
        if meta_tags:
            for t in meta_tags:
                dynamic_tags.add(t)

    if when_clause and "config.keyboardNavigation.chords." in when_clause:
        dynamic_tags.add("(chord)")

    # context-based tags: map substrings or regexes in the when-clause to tags
    if when_clause:
        for pattern, tag in _WHEN_TAG_SELECTORS:
            if pattern.startswith("/") and pattern.endswith("/"):
                regex = pattern[1:-1]
                try:
                    if re.search(regex, when_clause):
                        dynamic_tags.add(tag)
                except re.error:
                    # ignore bad regexes; should probably emit a warning here ...
                    pass
            else:
                # avoid matching negated occurrences like '!editorFocus'
                try:
                    # search for whole-word occurrence not immediately preceded by '!'
                    regex = rf"(?<!\!)\b{re.escape(pattern)}\b"
                    if re.search(regex, when_clause):
                        dynamic_tags.add(tag)
                except re.error:
                    # fallback to simple substring match on regex error
                    if pattern in when_clause:
                        dynamic_tags.add(tag)

    ordered_tags.extend([tag for tag in _TAG_ORDER if tag in dynamic_tags])

    # append any remaining dynamic tags not listed in TAG_ORDER, sorted alphabetically
    remaining = sorted(t for t in dynamic_tags if t not in _TAG_ORDER)
    ordered_tags.extend(remaining)

    return ordered_tags


def _when_for(
    key: str,
    mod: str = "",
    *,
    allowed_letter_keys: set[str] | None = None,
    selected_nav_group: str | None = None,
    debug_group: set[str] | None = None,
    action_group: set[str] | None = None,
    extension_group: set[str] | None = None,
) -> str:
    """Compute a when-clause for `key`/`mod`.

    Accepts optional runtime state instead of reading module globals so callers
    (such as the CLI script) can pass their current selections.
    """

    parts = ["config.keyboardNavigation.enabled"]
    seen = set()

    def _add(cond: str) -> None:
        if cond not in seen:
            parts.append(cond)
            seen.add(cond)

    key_norm = _normalize_key(key)

    if key_norm in _ARROW_GROUP:
        _add("config.keyboardNavigation.keys.arrows")

    allowed = allowed_letter_keys if allowed_letter_keys is not None else globals().get("_ALLOWED_LETTER_KEYS", set())
    for name, group in _LETTER_GROUPS.items():
        if key_norm in group and key_norm in allowed:
            _add(f"config.keyboardNavigation.keys.letters == '{name}'")

    # qualify a chord when it's a valid combination defined in MODIFIERS_SINGLE or MODIFIERS_MULTI
    def _qualify_chord(chord_set, chord_name: str) -> None:
        allowed_mods = set(_MODIFIERS_SINGLE) | set(_MODIFIERS_MULTI)
        if mod not in allowed_mods:
            return
        if key_norm in chord_set:
            _add(f"config.keyboardNavigation.chords.{chord_name}")
            sel = selected_nav_group if selected_nav_group is not None else globals().get("_SELECTED_NAV_GROUP")
            if sel and sel != "none":
                _add(f"config.keyboardNavigation.keys.letters == '{sel}'")

    # use provided chord groups or fall back to module globals
    _qualify_chord(set(debug_group if debug_group is not None else globals().get("_DEBUG_GROUP", set())), 'debug')
    _qualify_chord(set(action_group if action_group is not None else globals().get("_ACTION_GROUP", set())), 'action')
    _qualify_chord(set(extension_group if extension_group is not None else globals().get("_EXTENSION_GROUP", set())), 'extension')

    return " && ".join(parts)
