"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common corpus functions.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .keybindings import canonicalize_when, key_tail_literal


def tags_for(obj: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    if not isinstance(obj, dict):
        return tags
    if "command" in obj:
        tags.append(f"cmd:{obj.get('command')}")
    if "key" in obj:
        tail = key_tail_literal(obj.get("key", ""))
        if tail:
            tags.append(f"key-tail:{tail}")
    when = obj.get("when") or obj.get("whenExpr") or ""
    if when:
        can = canonicalize_when(str(when))
        if can:
            tags.append(f"when:{can}")
    return tags


def augment_when_clause(base_when: str, contexts: List[str]) -> str:
    if not contexts:
        return base_when or ""
    ctx_clause = " || ".join([c.strip() for c in contexts if c and c.strip()])
    if not base_when or not base_when.strip():
        return ctx_clause
    return f"({base_when}) && ({ctx_clause})"
