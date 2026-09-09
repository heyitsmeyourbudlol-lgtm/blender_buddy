#!/usr/bin/env python3
"""Company org → teams → roles gap audit vs live agent_roles.

Maps a SaaS/product company structure to Automation Hub niches, reports
missing roles, and can emit enqueue lines for staffing gaps.

Usage:
  python3 scripts/peer_company_org.py --audit
  python3 scripts/peer_company_org.py --write-md
  python3 scripts/peer_company_org.py --enqueue-missing --cap 4
  ./scripts/peer company-org
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

DIGEST_PATH = ROOT / "notes" / "COMPANY_TEAMS.md"


@dataclass(frozen=True)
class OrgRole:
    role_id: str
    job_title: str
    team: str
    department: str
    purpose: str
    strengths: tuple[str, ...] = ()


@dataclass
class GapReport:
    present: list[str] = field(default_factory=list)
    missing: list[OrgRole] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    by_team: dict[str, dict[str, Any]] = field(default_factory=dict)


# Full company catalog — required niches for a product + automation factory.
COMPANY_ROLES: tuple[OrgRole, ...] = (
    # Always-on progress review
    OrgRole(
        "progress_monitor",
        "Progress Monitor",
        "Progress Review",
        "Operations",
        "24/7 progress watch — call cursor-agent when stalled (oversight daemon)",
        ("progress-monitor", "oversight", "stagnation", "24/7"),
    ),
    # Engineering
    OrgRole(
        "factory_engineer",
        "Factory Engineer",
        "Platform Engineering",
        "Engineering",
        "Kit/orchestration Python — peer_loop, worktrees, tasks",
        ("kit", "peer_loop", "orchestrate"),
    ),
    OrgRole(
        "backend_engineer",
        "Backend Engineer",
        "Product Engineering",
        "Engineering",
        "APIs, auth, billing hooks, server routes on product repos",
        ("backend", "api", "auth", "server"),
    ),
    OrgRole(
        "frontend_engineer",
        "Frontend Engineer",
        "Product Engineering",
        "Engineering",
        "UI/UX implementation — elegant statue, one job per screen",
        ("frontend", "ui", "react", "next"),
    ),
    OrgRole(
        "verify_runner",
        "Verify Runner",
        "Quality Engineering",
        "Engineering",
        "unittest / self-check / verify gate — run-only",
        ("verify", "unittest", "self-check"),
    ),
    OrgRole(
        "qa_engineer",
        "QA Engineer",
        "Quality Engineering",
        "Engineering",
        "Product acceptance, smoke paths, regression checklists",
        ("qa", "smoke", "acceptance", "regression"),
    ),
    OrgRole(
        "adapt_specialist",
        "Adapt & Heal Specialist",
        "DevOps / Platform",
        "Engineering",
        "automation_adapt heal, profiles, registry drift",
        ("adapt", "heal", "profile"),
    ),
    OrgRole(
        "sre_release",
        "SRE / Release Engineer",
        "DevOps / Platform",
        "Engineering",
        "Deploy, rollback, health, release notes, uptime",
        ("sre", "release", "deploy", "uptime"),
    ),
    OrgRole(
        "compression_engineer",
        "Compression Engineer",
        "Performance",
        "Engineering",
        "RAM/RSS down without cutting features",
        ("ram", "rss", "footprint"),
    ),
    OrgRole(
        "command_builder",
        "Command Builder Agent",
        "Developer Experience",
        "Engineering",
        "peer CLI compounds — kill repeated shell loops",
        ("command-builder", "cli", "compound"),
    ),
    # Security
    OrgRole(
        "safety_auditor",
        "Safety Auditor",
        "Security",
        "Security",
        "SAFETY_GATES PASS/BLOCK veto",
        ("safety", "gates"),
    ),
    OrgRole(
        "pen_test_researcher",
        "Pen Test Researcher",
        "Security",
        "Security",
        "Defensive pen-test + harden (no exploit PoCs)",
        ("pen-test", "hardening", "secrets"),
    ),
    OrgRole(
        "legal_compliance",
        "Legal / Compliance Officer",
        "Trust & Safety",
        "Security",
        "Terms, privacy, export controls, consent copy",
        ("legal", "compliance", "privacy", "terms"),
    ),
    # Product
    OrgRole(
        "product_manager",
        "Product Manager",
        "Product",
        "Product",
        "Scope, prioritization, acceptance criteria, roadmap slices",
        ("product", "roadmap", "acceptance", "prioritize"),
    ),
    OrgRole(
        "design_ux",
        "Design / UX Lead",
        "Design",
        "Product",
        "Visual system, a11y, elegant statue — remove chrome",
        ("design", "ux", "a11y", "visual"),
    ),
    # Research
    OrgRole(
        "efficiency_researcher",
        "Efficiency Research Agent",
        "Research",
        "Research",
        "Hot paths, yield, latency",
        ("efficiency-research", "latency"),
    ),
    OrgRole(
        "output_researcher",
        "Output Research Agent",
        "Research",
        "Research",
        "Monster factory / external proof",
        ("output-research", "factory"),
    ),
    # GTM
    OrgRole(
        "growth_marketer",
        "Growth / Marketing Lead",
        "Growth",
        "GTM",
        "Distribution, landing, launch spikes, acquisition loops",
        ("growth", "marketing", "landing", "launch"),
    ),
    OrgRole(
        "customer_success",
        "Customer Success Lead",
        "Support",
        "GTM",
        "Support playbooks, onboarding, retention signals",
        ("support", "success", "onboarding", "retention"),
    ),
    # Ops
    OrgRole(
        "queue_steward",
        "Queue Steward",
        "Program Management",
        "Operations",
        "WORK_QUEUE ↔ context sync, Active cap",
        ("queue", "steward", "drift"),
    ),
    OrgRole(
        "communications_engineer",
        "Communications Engineer",
        "Internal Comms",
        "Operations",
        "GLink bus, token-efficient messaging",
        ("comms", "glink", "messaging"),
    ),
    OrgRole(
        "finance_billing",
        "Finance / Billing Lead",
        "Finance",
        "Operations",
        "Stripe/billing correctness, receipts, plan gates",
        ("billing", "stripe", "finance", "receipt"),
    ),
    OrgRole(
        "data_analyst",
        "Data Analyst",
        "Analytics",
        "Operations",
        "KPIs, funnels, factory_progress metrics",
        ("data", "analytics", "kpi", "funnel"),
    ),
    OrgRole(
        "tech_writer",
        "Technical Writer",
        "Documentation",
        "Operations",
        "SOPs, AGENTS.md, user-facing docs",
        ("docs", "sop", "readme", "writer"),
    ),
    # External
    OrgRole(
        "integration_architect",
        "OSS Integration Architect",
        "External Integration",
        "External",
        "Registry adapt → verify → worktree → PR",
        ("oss", "registry", "external proof"),
    ),
)


def live_role_ids() -> set[str]:
    cfg = auto.load_tasks_config()
    roles = cfg.get("agent_roles") or []
    out: set[str] = set()
    for r in roles:
        if isinstance(r, dict) and r.get("id"):
            out.add(str(r["id"]).strip())
    return out


def audit() -> GapReport:
    live = live_role_ids()
    catalog_ids = {r.role_id for r in COMPANY_ROLES}
    report = GapReport()
    report.present = sorted(live & catalog_ids)
    report.missing = [r for r in COMPANY_ROLES if r.role_id not in live]
    report.extra = sorted(live - catalog_ids)

    for role in COMPANY_ROLES:
        team = report.by_team.setdefault(
            role.team,
            {
                "department": role.department,
                "required": [],
                "present": [],
                "missing": [],
            },
        )
        team["required"].append(role.role_id)
        if role.role_id in live:
            team["present"].append(role.role_id)
        else:
            team["missing"].append(role.role_id)
    return report


def build_digest(report: GapReport) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Company teams → roles",
        "",
        f"_Updated {now}. Gap audit: catalog vs `peer_tasks.json` → `agent_roles`._",
        "",
        "## Summary",
        "",
        f"| Catalog roles | {len(COMPANY_ROLES)} |",
        f"| Live agent_roles | {len(live_role_ids())} |",
        f"| Present | {len(report.present)} |",
        f"| Missing | {len(report.missing)} |",
        f"| Extra (not in catalog) | {len(report.extra)} |",
        "",
        "## Plan → steps → execute (all agents)",
        "",
        "Every niche **must** draft a numbered step plan before editing, then execute only those steps.",
        "See `notes/CRITICAL_THINKING.md` · `PLAN_EXECUTE_MANDATE`.",
        "",
        "## Departments / teams",
        "",
    ]
    by_dept: dict[str, list[str]] = {}
    for team, info in sorted(report.by_team.items(), key=lambda x: (x[1]["department"], x[0])):
        by_dept.setdefault(info["department"], []).append(team)

    for dept, teams in sorted(by_dept.items()):
        lines.append(f"### {dept}")
        lines.append("")
        for team in teams:
            info = report.by_team[team]
            miss = info["missing"]
            status = "STAFFED" if not miss else f"GAP ({len(miss)} missing)"
            lines.append(
                f"- **{team}** — {status}; present={info['present'] or '—'}; "
                f"missing={miss or '—'}"
            )
        lines.append("")

    if report.missing:
        lines.extend(["## Missing roles (implement)", ""])
        for r in report.missing:
            lines.append(
                f"- `{r.role_id}` — **{r.job_title}** ({r.department} / {r.team}) — {r.purpose}"
            )
        lines.append("")

    if report.extra:
        lines.extend(["## Extra live roles (keep)", ""])
        for rid in report.extra:
            lines.append(f"- `{rid}`")
        lines.append("")

    lines.extend(
        [
            "## Commands",
            "",
            "- `./scripts/peer company-org` — audit + print JSON summary",
            "- `./scripts/peer company-org-md` — refresh this digest",
            "- `./scripts/peer company-org-enqueue` — enqueue staffing gaps",
            "",
        ]
    )
    return "\n".join(lines)


def write_digest(report: GapReport | None = None) -> Path:
    report = report or audit()
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(build_digest(report), encoding="utf-8")
    return DIGEST_PATH


def enqueue_missing(*, cap: int = 4) -> list[str]:
    report = audit()
    if not report.missing or cap <= 0:
        return []
    enqueued: list[str] = []
    work_path = auto.WORK_QUEUE_PATH
    try:
        work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
    except OSError:
        return []
    known = {auto._normalize_queue_key(x) for x in auto.open_work_items(work_md=work_md).open_items}

    for role in report.missing:
        if len(enqueued) >= cap:
            break
        marker = f"[company-org] Staff role {role.role_id} — {role.job_title}"
        if auto._normalize_queue_key(marker) in known:
            continue
        detail = (
            f"{role.department}/{role.team}: {role.purpose}; add agent_roles + persona; "
            f"plan→steps→execute; `./scripts/peer company-org`"
        )
        line = f"- [ ] **{marker}** — {detail}"
        if "## Active" in work_md:
            work_md = work_md.replace("## Active\n", f"## Active\n{line}\n", 1)
        else:
            work_md = work_md.rstrip() + f"\n\n## Active\n{line}\n"
        enqueued.append(marker)
        known.add(auto._normalize_queue_key(marker))
        ctx_path = auto.CONTEXT_PATH
        if ctx_path.is_file():
            try:
                ctx = ctx_path.read_text(encoding="utf-8")
                if marker not in ctx:
                    ctx = auto.insert_remaining_work_bullet(ctx, line)
                    ctx_path.write_text(ctx, encoding="utf-8")
            except OSError:
                pass

    if enqueued:
        work_path.write_text(work_md, encoding="utf-8")
    return enqueued


def role_stub(role: OrgRole) -> dict[str, Any]:
    """JSON stub for peer_tasks.json agent_roles entry."""
    peer = "implement"
    if role.department == "Security":
        peer = "safety"
    elif role.role_id in ("verify_runner", "qa_engineer"):
        peer = "verify"
    elif role.role_id in ("compression_engineer", "efficiency_researcher"):
        peer = "footprint"
    elif role.role_id in ("growth_marketer", "customer_success", "product_manager"):
        peer = "launch"
    sub = "generalPurpose"
    model = "inherit"
    if role.role_id in ("verify_runner", "qa_engineer", "data_analyst", "tech_writer"):
        model = "composer-2.5-fast"
    if role.role_id in ("safety_auditor", "pen_test_researcher"):
        sub = "security-review"
    return {
        "id": role.role_id,
        "job_title": role.job_title,
        "legacy_peer": peer,
        "subagent_type": sub,
        "model": model,
        "strengths": list(role.strengths) or [role.role_id.replace("_", "-")],
        "responsibilities": role.purpose,
        "niche_task": (
            f"**{role.job_title}** — {role.purpose}. "
            "Draft numbered plan (≥3 steps) before any edit; execute only those steps."
        ),
        "reads": ["notes/COMPANY_TEAMS.md", "notes/CRITICAL_THINKING.md", "notes/WORK_QUEUE.md"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Company org role gap audit")
    parser.add_argument("--audit", action="store_true", help="Print JSON gap report")
    parser.add_argument("--write-md", action="store_true", help="Write notes/COMPANY_TEAMS.md")
    parser.add_argument("--enqueue-missing", action="store_true")
    parser.add_argument("--cap", type=int, default=4)
    parser.add_argument("--stubs", action="store_true", help="Print JSON stubs for missing roles")
    args = parser.parse_args(argv)

    report = audit()
    if args.write_md or not any((args.audit, args.enqueue_missing, args.stubs)):
        path = write_digest(report)
        print(f"wrote {path}")

    if args.stubs:
        print(json.dumps([role_stub(r) for r in report.missing], indent=2))

    if args.enqueue_missing:
        got = enqueue_missing(cap=args.cap)
        print(json.dumps({"enqueued": got}, indent=2))

    if args.audit or not any((args.write_md, args.enqueue_missing, args.stubs)):
        print(
            json.dumps(
                {
                    "catalog": len(COMPANY_ROLES),
                    "live": len(live_role_ids()),
                    "present": len(report.present),
                    "missing": [r.role_id for r in report.missing],
                    "extra": report.extra,
                    "by_team": {
                        t: {
                            "department": i["department"],
                            "missing": i["missing"],
                            "present": i["present"],
                        }
                        for t, i in report.by_team.items()
                    },
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
