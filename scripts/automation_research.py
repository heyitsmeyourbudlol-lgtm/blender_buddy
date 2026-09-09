#!/usr/bin/env python3
"""Industry trend research for automation improvement — web + curated baseline.

Maps 2025–2026 agent-orchestration patterns to concrete kit gaps.

Usage:
  python3 scripts/automation_research.py              # print trends + kit mapping
  python3 scripts/automation_research.py --refresh    # fetch HN headlines, update cache
  python3 scripts/automation_research.py --json       # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# COMPRESSION_LAZY_URLLIB_RESEARCH_2026_09_04 — defer urllib→libssl/libcrypto
# (~+12 MB cold) until HN refresh; forever --research ticks use cache/curated.
# Hub re-land 2026-09-07 (peer-6 already lazy; live improve still hit hub import).

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402

ROOT = cfg_mod.ROOT
TRENDS_MD = ROOT / "notes" / "AUTOMATION_TRENDS.md"
TRENDS_JSON = ROOT / "notes" / "AUTOMATION_TRENDS.json"
CACHE_JSON = cfg_mod.config_dir() / "automation-trends-cache.json"

HN_SEARCH = "https://hn.algolia.com/api/v1/search"
HN_QUERIES = (
    "ai coding agent orchestration",
    "git worktree parallel agents",
    "self-healing CI automation",
)

FETCH_TIMEOUT = 12.0


@dataclass
class Trend:
    id: str
    theme: str
    summary: str
    kit_status: str  # have | partial | gap
    opportunity: str
    sources: list[str]
    priority: int = 50


@dataclass
class Headline:
    title: str
    url: str
    source: str
    points: int | None = None


CURATED_TRENDS: list[Trend] = [
    Trend(
        id="parallel_worktrees",
        theme="Parallel agents via git worktrees",
        summary="Industry pattern: isolate each agent in its own worktree/branch to avoid file conflicts.",
        kit_status="have",
        opportunity=(
            "Shipped: peer_worktree.spawn_parallel_worktree + ./scripts/peer ensure-pool "
            "(floor=8, refuse out-of-cap slots). Keep pool floor ↔ max_parallel_peers aligned."
        ),
        sources=[
            "https://www.mindstudio.ai/blog/parallel-ai-coding-agents-git-worktrees",
            "https://github.com/spillwavesolutions/parallel-worktrees",
        ],
        priority=22,
    ),
    Trend(
        id="phase_orchestration",
        theme="Phase-based orchestration (plan → implement → verify → review)",
        summary="Discrete phases with recovery points beat free-roaming agents.",
        kit_status="have",
        opportunity="Formalize phases in peer_orchestrate output; gate merge on verify between phases.",
        sources=[
            "https://maecapozzi.com/blog/building-a-multi-agent-orchestrator",
        ],
        priority=28,
    ),
    Trend(
        id="coordinator_routing",
        theme="Coordinator-first specialist routing",
        summary="A coordinator picks specialists instead of hardcoded if/else routing.",
        kit_status="partial",
        opportunity="Optional coordinator pass before template_match for ambiguous queue items.",
        sources=[
            "https://htdocs.dev/posts/from-conductor-to-orchestrator-a-practical-guide-to-multi-agent-coding-in-2026/",
        ],
        priority=35,
    ),
    Trend(
        id="self_healing_ci",
        theme="Self-healing CI / verify loops",
        summary="Agents re-run CI, fix failures, and stop wedged PR loops with terminal close + respawn.",
        kit_status="have",
        opportunity="Extend post-agent verify to retry-once + classify failure type in peer-loop-state.",
        sources=[
            "https://github.com/kai-linux/agent-os",
            "https://github.com/amitdevx/self-healops",
        ],
        priority=18,
    ),
    Trend(
        id="graduated_automation",
        theme="dispatcher_only → full automation rollout",
        summary="Start supervised; graduate to full loop after reliability metrics are green.",
        kit_status="have",
        opportunity="Document dispatcher_only path in IMPORT.md; expose automation_mode in config.",
        sources=[
            "https://github.com/kai-linux/agent-os",
        ],
        priority=55,
    ),
    Trend(
        id="event_driven_wake",
        theme="Event-driven agent wake (not poll timers)",
        summary="Wake on transcript/git/signal events; long fallback sleep only off macOS.",
        kit_status="have",
        opportunity="Keep kqueue path hot; avoid adding short poll timers.",
        sources=[
            "https://www.firecrawl.dev/blog/agentic-ai-trends",
        ],
        priority=70,
    ),
    Trend(
        id="harness_memory",
        theme="Agent harness: memory + state across sessions",
        summary="WORK_QUEUE, adapt-state, loop retrospect — persistence outside the chat window.",
        kit_status="have",
        opportunity="Inject last_cycle + trend cache into every peer prompt; trim stale context.",
        sources=[
            "https://www.firecrawl.dev/blog/agentic-ai-trends",
        ],
        priority=32,
    ),
    Trend(
        id="mcp_tool_layer",
        theme="MCP / tool protocol layer",
        summary="Standard tool interfaces (MCP) for agents; kit should play nice with Cursor MCP.",
        kit_status="partial",
        opportunity="Self-check tip when MCP namespaces error; document peer + MCP workflow.",
        sources=[
            "https://www.firecrawl.dev/blog/agentic-ai-trends",
        ],
        priority=45,
    ),
]


def _fetch_hn_headlines(query: str, *, hits: int = 3) -> list[Headline]:
    import urllib.error
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "query": query,
        "tags": "story",
        "hitsPerPage": hits,
    })
    url = f"{HN_SEARCH}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "automation-hub-research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        return []

    out: list[Headline] = []
    for hit in data.get("hits") or []:
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        out.append(Headline(
            title=str(hit.get("title") or "").strip(),
            url=story_url,
            source="hn",
            points=hit.get("points"),
        ))
    return [h for h in out if h.title]


def refresh_web_headlines() -> list[Headline]:
    seen: set[str] = set()
    headlines: list[Headline] = []
    for query in HN_QUERIES:
        for h in _fetch_hn_headlines(query):
            key = h.title.lower()
            if key in seen:
                continue
            seen.add(key)
            headlines.append(h)
    return headlines[:12]


def load_cache() -> dict[str, Any]:
    for path in (CACHE_JSON, TRENDS_JSON):
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
    return {}


def save_cache(payload: dict[str, Any]) -> Path:
    CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
    CACHE_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    return CACHE_JSON


def write_trends_json(report: dict[str, Any]) -> Path:
    TRENDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRENDS_JSON.write_text(json.dumps({
        "version": 1,
        "fetched_at": report.get("fetched_at"),
        "trends": report["trends"],
    }, indent=2) + "\n")
    return TRENDS_JSON


def _kit_fingerprint(trends: list[Any]) -> dict[str, str]:
    """id → kit_status map for drift detection."""
    out: dict[str, str] = {}
    for t in trends:
        if isinstance(t, Trend):
            out[t.id] = t.kit_status
        elif isinstance(t, dict) and t.get("id"):
            out[str(t["id"])] = str(t.get("kit_status") or "")
    return out


_SOURCE_MTIME: float | None = None


def _fresh_curated_trends() -> list[Trend]:
    """Return CURATED_TRENDS, reloading from disk when this file changes.

    Long-running daemons (improve --forever) import once; without a reload they
    keep serving stale kit_status after CURATED_TRENDS edits.
    """
    global CURATED_TRENDS, _SOURCE_MTIME
    path = Path(__file__).resolve()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return list(CURATED_TRENDS)
    if _SOURCE_MTIME is None:
        _SOURCE_MTIME = mtime
        return list(CURATED_TRENDS)
    if mtime == _SOURCE_MTIME:
        return list(CURATED_TRENDS)

    import importlib.util

    spec = importlib.util.spec_from_file_location("_automation_research_fresh", path)
    if spec is None or spec.loader is None:
        return list(CURATED_TRENDS)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001 — fall back to in-memory curated
        return list(CURATED_TRENDS)
    fresh = getattr(mod, "CURATED_TRENDS", None)
    if not fresh:
        return list(CURATED_TRENDS)
    CURATED_TRENDS = list(fresh)
    _SOURCE_MTIME = mtime
    return list(CURATED_TRENDS)


def build_trend_report(*, refresh: bool = False, persist: bool = True) -> dict[str, Any]:
    headlines: list[Headline] = []
    fetched_at: str | None = None
    if refresh:
        headlines = refresh_web_headlines()
        fetched_at = datetime.now(timezone.utc).isoformat()

    cached = load_cache()
    if not headlines and cached.get("headlines"):
        headlines = [Headline(**h) for h in cached["headlines"]]

    # Always from live curated (reloaded if source mtime changed) — never trust
    # stale cache/notes kit_status for opportunity ranking.
    trends = _fresh_curated_trends()
    gaps = [t for t in trends if t.kit_status == "gap"]
    partials = [t for t in trends if t.kit_status == "partial"]

    payload: dict[str, Any] = {
        "fetched_at": fetched_at or cached.get("fetched_at"),
        "curated_count": len(trends),
        "gap_count": len(gaps),
        "partial_count": len(partials),
        "trends": [asdict(t) for t in trends],
        "headlines": [asdict(h) for h in headlines],
    }
    drifted = _kit_fingerprint(cached.get("trends") or []) != _kit_fingerprint(trends)
    if persist and (refresh or drifted):
        save_cache(payload)
    if persist and drifted:
        # Keep notes + md aligned when kit_status changes without requiring --refresh.
        write_trends_json(payload)
        write_trends_md(payload)
    return payload


def trends_to_opportunities(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert trend gaps/partials into improve-script opportunity dicts.

    kit_status == \"have\" is never an opportunity (already shipped in the kit).
    """
    opps: list[dict[str, Any]] = []
    for raw in report.get("trends") or []:
        status = str(raw.get("kit_status") or "").lower()
        if status == "have" or status not in ("gap", "partial"):
            continue
        category = "efficiency" if status == "gap" else "ease"
        opps.append({
            "category": category,
            "title": f"[trend] {raw.get('theme', 'trend')}",
            "detail": raw.get("opportunity", raw.get("summary", "")),
            "priority": int(raw.get("priority", 50)),
            "sources": raw.get("sources") or [],
            "trend_id": raw.get("id"),
            "kit_status": status,
        })
    opps.sort(key=lambda o: o["priority"])
    return opps[:6]


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "# Automation industry trends",
        "",
        f"Curated: {report.get('curated_count', 0)} · gaps: {report.get('gap_count', 0)} · "
        f"partial: {report.get('partial_count', 0)}",
    ]
    if report.get("fetched_at"):
        lines.append(f"Web refresh: {report['fetched_at']}")
    lines.append("")

    lines.append("## Kit mapping (actionable)")
    for raw in report.get("trends") or []:
        if raw.get("kit_status") == "have":
            continue
        status = raw.get("kit_status", "?").upper()
        lines.append(f"### [{status}] {raw.get('theme')}")
        lines.append(raw.get("opportunity", ""))
        for src in raw.get("sources") or []:
            lines.append(f"- {src}")
        lines.append("")

    headlines = report.get("headlines") or []
    if headlines:
        lines.append("## Recent headlines (HN)")
        for h in headlines[:8]:
            pts = f" ({h['points']} pts)" if h.get("points") is not None else ""
            lines.append(f"- [{h['title']}]({h['url']}){pts}")
        lines.append("")

    lines.append("## Research command")
    lines.append("```bash")
    lines.append("./scripts/peer research --refresh   # update HN cache")
    lines.append("./scripts/peer improve --research   # plan with trends")
    lines.append("```")
    return "\n".join(lines)


def write_trends_md(report: dict[str, Any]) -> Path:
    TRENDS_MD.parent.mkdir(parents=True, exist_ok=True)
    TRENDS_MD.write_text(format_report(report) + "\n")
    return TRENDS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Research industry trends for automation improvement")
    parser.add_argument("--refresh", action="store_true", help="Fetch HN headlines and update cache")
    parser.add_argument("--write", action="store_true", help="Write notes/AUTOMATION_TRENDS.md")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    report = build_trend_report(refresh=args.refresh, persist=True)
    if args.write or args.refresh:
        write_trends_md(report)
    write_trends_json(report)
    if args.refresh or args.write:
        save_cache(report)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(format_report(report))
    if args.refresh:
        print(f"\ncache: {CACHE_JSON}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
