"""Data-driven queue item → task template matching."""

from __future__ import annotations

import re
from typing import Any

_BACKTICK_RE = re.compile(r"`([^`]+)`")


def scope_hints_from_item(item: str, module_scope: dict[str, str]) -> list[str]:
    scopes: list[str] = []
    for raw in _BACKTICK_RE.findall(item):
        token = raw.strip().rstrip(".,;")
        if not token:
            continue
        if token.endswith(".py"):
            if token not in scopes:
                scopes.append(token)
            continue
        head = token.split(".", 1)[0]
        mapped = module_scope.get(token) or module_scope.get(head)
        if mapped and mapped not in scopes:
            scopes.append(mapped)
            continue
        if token.startswith("contrib/"):
            path = token if token.endswith(".py") else f"{token}.py"
            if path not in scopes:
                scopes.append(path)
    return scopes


def _rule_matches(lower: str, rule: dict[str, Any]) -> bool:
    exclude = rule.get("exclude") or []
    for term in exclude:
        if term.lower() in lower:
            return False
    all_terms = rule.get("all") or []
    if all_terms and not all(t.lower() in lower for t in all_terms):
        return False
    any_terms = rule.get("any") or []
    if not any_terms:
        return False
    return any(t.lower() in lower for t in any_terms)


def _matched_any_len(lower: str, rule: dict[str, Any]) -> int:
    """Longest matching ``any`` term — tie-break so tagged prefixes beat bare keywords."""
    any_terms = rule.get("any") or []
    hits = [len(t) for t in any_terms if str(t).lower() in lower]
    return max(hits) if hits else 0


def match_template(item: str, templates: dict, match_rules: list[dict]) -> tuple[str, dict]:
    """Pick first matching rule by ascending priority, then longest matched ``any`` term.

    Lower ``priority`` wins (e.g. flaw_research=7 before automation_audit=8). Equal
    priority prefers the longer matched keyword so bare ``automation`` cannot steal
    ``[flaw-research] … automation …`` when both rules share priority.
    """
    lower = item.lower()
    ordered = sorted(
        match_rules,
        key=lambda r: (int(r.get("priority", 100)), -_matched_any_len(lower, r)),
    )
    for rule in ordered:
        if _rule_matches(lower, rule):
            template_id = str(rule.get("template", "generic_task"))
            return template_id, dict(templates.get(template_id) or {})
    fallback = templates.get("generic_task") or templates.get("generic_reclaim") or {}
    return "generic_task", dict(fallback)
