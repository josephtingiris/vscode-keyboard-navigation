"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common corpus functions.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .keybindings import _canonicalize_when, _key_tail_literal


#
# globals & constants
#

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
    ("config.keyboardNavigation.terminal", "(terminal)"),
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


def _tags_for(obj: Dict[str, Any]) -> List[str]:
    """Return a list of simple tags for a keybinding object (command, key-tail, and when)."""

    tags: List[str] = []
    if not isinstance(obj, dict):
        return tags
    if "command" in obj:
        tags.append(f"cmd:{obj.get('command')}")
    if "key" in obj:
        tail = _key_tail_literal(obj.get("key", ""))
        if tail:
            tags.append(f"key-tail:{tail}")
    when = obj.get("when") or obj.get("whenExpr") or ""
    if when:
        can = _canonicalize_when(str(when))
        if can:
            tags.append(f"when:{can}")
    return tags
