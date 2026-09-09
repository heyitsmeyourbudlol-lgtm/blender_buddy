"""Inject retrieved knowledge into peer-loop prompts."""

from __future__ import annotations

import re

import knowledge_index as ki
import knowledge_index_config as kcfg
import project_automation as auto


def inject_on_quick() -> bool:
    return bool(kcfg._cfg().get("inject_on_quick", True))


def _queue_hint() -> str:
    lines: list[str] = []
    try:
        wq = auto.load_work_queue_md()
        for line in wq.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [ ]"):
                lines.append(stripped[5:].strip())
            if len(lines) >= 3:
                break
    except Exception:  # noqa: BLE001
        pass
    return " ".join(lines)


def _conversation_hint(conversation: str) -> str:
    if not conversation:
        return ""
    chunks = [ln.strip() for ln in conversation.splitlines() if ln.strip()]
    tail = " ".join(chunks[-12:])
    tail = re.sub(r"\s+", " ", tail)
    return tail[:2500]


def build_query(*, conversation: str = "", extra: str = "") -> str:
    parts = [_queue_hint(), _conversation_hint(conversation), extra.strip()]
    query = " ".join(p for p in parts if p).strip()
    return query[:4000]


def inject_for_dispatch(
    *,
    conversation: str = "",
    extra: str = "",
    quick: bool = False,
    hybrid: bool | None = None,
) -> str:
    """Inject retrieved knowledge into prompts.

    Default ``hybrid=False`` for dispatch/cold-memory paths so peer_loop never
    loads torch/mamba; pass ``hybrid=True`` for explicit hybrid CLI/tools.
    """
    if not kcfg.enabled():
        return ""
    if quick and not inject_on_quick():
        return ""
    query = build_query(conversation=conversation, extra=extra)
    if not query:
        return ""
    # Sparse-only by default — mamba residency belongs in dgx_gpu_compute.
    use_hybrid = False if hybrid is None else bool(hybrid)
    hits = ki.retrieve(query, hybrid=use_hybrid)
    return ki.format_hits(hits)
