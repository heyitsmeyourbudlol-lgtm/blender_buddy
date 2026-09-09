#!/usr/bin/env python3
"""Product end-to-end gaps — factory unlocks shippable products.

See notes/PRODUCT_E2E_GAPS.md for the assessment. Consumed by automation_improve.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRODUCT_E2E_NORTH_STAR = (
    "Shippable product loop: spec → implement → native verify → deploy proof → "
    "billing smoke → distribution handoff — autonomously on registry repos without babysitting"
)

WORK_KIT_MARKERS = (
    "product e2e",
    "product-e2e",
    "product ship",
    "ship gate",
    "deploy gate",
    "deploy smoke",
    "live url",
    "billing smoke",
    "per-repo queue",
    "product queue",
    "distribution handoff",
    "revenue repo",
    "bootstrap revenue",
    "vercel",
    "stripe smoke",
)


def product_e2e_opportunities(registry_path: Path) -> list[dict[str, Any]]:
    """Ranked product-E2E gaps as Opportunity kwargs dicts."""
    gaps: list[dict[str, Any]] = [
        {
            "category": "product",
            "title": "Product ship gate — deploy + live URL in verify",
            "detail": (
                "peer_loop cycle success for ship/revenue registry repos must include deploy smoke "
                "and live URL check — not only unittest/self-check. Wire into last_cycle + "
                "peer_tasks verify_commands per profile. See notes/PRODUCT_E2E_GAPS.md."
            ),
            "priority": 12,
        },
        {
            "category": "product",
            "title": "Per-repo product queue on external dispatch",
            "detail": (
                "When peer_loop or factory_sprint dispatches into a registry repo, read that repo's "
                "LAUNCH.md / WORK_QUEUE — not only hub notes/WORK_QUEUE.md. peer_loop cwd translation."
            ),
            "priority": 15,
        },
        {
            "category": "product",
            "title": "Multi-repo dispatch default for ship/revenue registry",
            "detail": (
                "Hub peer_loop sets cursor-agent cwd from registry path for priority=ship|revenue "
                "(RAM, CaaS). Today mostly hub-only; factory_sprint is DGX-only. peer_loop + registry."
            ),
            "priority": 16,
        },
        {
            "category": "product",
            "title": "Billing + deploy verify template for revenue profiles",
            "detail": (
                "peer_tasks product template: stripe test-checkout smoke + vercel preview/production "
                "URL after ship peers. Add to profiles/caas.json verify_commands when credentials exist."
            ),
            "priority": 18,
        },
        {
            "category": "product",
            "title": "Distribution handoff gate — agent prepares, human posts",
            "detail": (
                "LAUNCH phases 4–6 stay RED/human-only for paid ads and PH/HN posts — but peer must "
                "auto-prepare copy/assets and check off prep items. launch_spike + launch_paid_gate."
            ),
            "priority": 28,
        },
    ]
    if not registry_path.is_file():
        return gaps
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return gaps
    for repo in data.get("repos") or []:
        if not isinstance(repo, dict):
            continue
        name = str(repo.get("name") or "").strip()
        status = str(repo.get("status") or "").lower()
        priority_label = str(repo.get("priority") or "").lower()
        if priority_label in ("revenue", "ship") and status in (
            "needs-kit-install",
            "unaudited",
            "git",
        ):
            gaps.insert(
                0,
                {
                    "category": "product",
                    "title": f"Bootstrap revenue/ship repo — {name}",
                    "detail": (
                        f"registry status={status} priority={priority_label} — "
                        f"run automation_adapt --heal on {repo.get('path')}; native verify; "
                        "open first LAUNCH phase item; product queue on target repo."
                    ),
                    "priority": 14 if priority_label == "revenue" else 17,
                },
            )
            break
    return gaps
