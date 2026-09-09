#!/usr/bin/env python3
"""Research efficient agent-to-agent communication patterns for the automation kit.

Curated baseline + optional HN refresh. Maps findings to GLink / bus / MCP gaps.

Usage:
  python3 scripts/automation_comms_research.py
  python3 scripts/automation_comms_research.py --refresh --write
  python3 scripts/automation_comms_research.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402

ROOT = cfg_mod.ROOT
TRENDS_MD = ROOT / "notes" / "COMMS_TRENDS.md"
TRENDS_JSON = ROOT / "notes" / "COMMS_TRENDS.json"
CACHE_JSON = cfg_mod.config_dir() / "comms-trends-cache.json"

HN_SEARCH = "https://hn.algolia.com/api/v1/search"
HN_QUERIES = (
    "agent to agent communication protocol",
    "multi agent shared memory blackboard",
    "MCP model context protocol agents",
    "efficient LLM agent messaging",
    "GibberLink ggwave AI agents",
)

FETCH_TIMEOUT = 12.0


@dataclass
class CommsTrend:
    id: str
    theme: str
    summary: str
    kit_status: str  # have | partial | gap
    opportunity: str
    efficiency_note: str
    sources: list[str]
    priority: int = 50


@dataclass
class Headline:
    title: str
    url: str
    source: str
    points: int | None = None


CURATED_COMMS_TRENDS: list[CommsTrend] = [
    CommsTrend(
        id="glink_file_bus",
        theme="Structured file bus (GLink) vs English",
        summary="Text agents gain more from append-only JSONL buses than from natural-language standups.",
        kit_status="partial",
        opportunity="Extend GLink schema: binary refs, path hashes, REQ/ACK correlation ids.",
        efficiency_note="~10–50× fewer tokens than prose status updates when agents use STAT/DIFF codes.",
        sources=["https://techcrunch.com/2025/03/05/gibberlink-lets-ai-agents-call-each-other-in-robo-language/"],
        priority=12,
    ),
    CommsTrend(
        id="gibberlink_audio",
        theme="GibberLink / GGWave (audio A2A)",
        summary="Voice-channel agents can switch to GGWave tones; file-based agents should not copy audio.",
        kit_status="gap",
        opportunity="Document when to use GLink (disk) vs MCP (RPC) vs GGWave (voice) — no audio in peer_loop.",
        efficiency_note="GGWave wins on phone calls; JSONL bus wins on Cursor text peers.",
        sources=["https://github.com/PennyroyalTea/gibberlink"],
        priority=40,
    ),
    CommsTrend(
        id="mcp_tool_layer",
        theme="MCP / tool protocol for structured calls",
        summary=(
            "GLink REQ→MCP landed (PROTOCOL=1): need=mcp:<tool> or need=mcp+args.tool "
            "→ mcp=1 + args.tool; fixed codes vfy|adapt|heal|sync|assign|review|audit|comms|rsusp|rchg; "
            "free-text need rejected; open threads via materialize_open_reqs_mcp; "
            "bus records intent — Cursor MCP namespaces execute tools."
        ),
        kit_status="have",
        opportunity=(
            "Dogfood mcp:<tool> on bus for Cursor MCP namespaces; optional live RPC bridge later. "
            "Schema: glink_schema().mcp_prefix / validators.mcp_need."
        ),
        efficiency_note="Schema-bound args beat free-text handoffs for verify/adapt triggers.",
        sources=["https://modelcontextprotocol.io/", "scripts/peer_agent_comms.py"],
        priority=25,
    ),
    CommsTrend(
        id="blackboard_memory",
        theme="Shared blackboard + private scratchpads",
        summary="Broadcast facts on a bus; keep todos/summaries in per-agent vaults.",
        kit_status="have",
        opportunity="Auto-summarize bus → vault SUM lines; prune bus after N messages.",
        efficiency_note="O(1) append broadcast; agents read tail only.",
        sources=["https://en.wikipedia.org/wiki/Blackboard_system"],
        priority=18,
    ),
    CommsTrend(
        id="compact_encoding",
        theme="Compact encodings (msgpack / CBOR / columnar)",
        summary="Beyond JSON: binary or columnar logs for high-frequency agent telemetry.",
        kit_status="gap",
        opportunity="Optional msgpack line mode for bus.jsonl when message rate > threshold.",
        efficiency_note="Smaller disk + parse cost at scale; JSONL fine until ~1k msgs/day.",
        sources=["https://msgpack.org/"],
        priority=45,
    ),
    CommsTrend(
        id="a2a_google",
        theme="Agent2Agent (A2A) task delegation",
        summary="Cards/tasks with explicit capability negotiation between agents.",
        kit_status="have",
        opportunity="Map GLink REQ/ACK to A2A-style task cards for cross-repo agents.",
        efficiency_note="Structured delegation reduces ambiguous handoffs.",
        sources=["https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/"],
        priority=35,
    ),
    CommsTrend(
        id="event_sourcing",
        theme="Event-sourced agent memory",
        summary="Append-only logs as source of truth; materialized views for dashboards.",
        kit_status="partial",
        opportunity="Dashboard /api/comms streams bus tail; materialize per-role last STAT.",
        efficiency_note="Replay bus to rebuild state without re-running agents.",
        sources=["https://martinfowler.com/eaaDev/EventSourcing.html"],
        priority=30,
    ),
    CommsTrend(
        id="coordination_vs_chatter",
        theme="Hub-and-spoke vs mesh P2P",
        summary="Orchestrator + shared bus beats N² direct chats for 8 fixed niches.",
        kit_status="have",
        opportunity="Keep targeted GLink `to:` field; discourage English side-channels.",
        efficiency_note="8 agents × bus read << 56 pairwise chat sessions.",
        sources=["notes/OPERATING_SYSTEM.md"],
        priority=15,
    ),
]


def _fetch_hn(query: str, *, hits: int = 5) -> list[Headline]:
    params = urllib.parse.urlencode(
        {"query": query, "tags": "story", "hitsPerPage": hits}
    )
    url = f"{HN_SEARCH}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "automation-comms-research/1.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        return []
    out: list[Headline] = []
    for hit in (data.get("hits") or [])[:hits]:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").strip()
        if not title:
            continue
        out.append(
            Headline(
                title=title,
                url=str(hit.get("url") or hit.get("story_url") or ""),
                source="hn",
                points=int(hit.get("points") or 0) if hit.get("points") is not None else None,
            )
        )
    return out


def refresh_headlines() -> list[Headline]:
    seen: set[str] = set()
    out: list[Headline] = []
    for q in HN_QUERIES:
        for h in _fetch_hn(q, hits=4):
            key = h.title.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(h)
    return out


def build_comms_report(*, refresh: bool = False) -> dict[str, Any]:
    headlines: list[Headline] = []
    if refresh:
        headlines = refresh_headlines()
        try:
            CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
            CACHE_JSON.write_text(
                json.dumps(
                    {
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "headlines": [asdict(h) for h in headlines],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
    elif CACHE_JSON.is_file():
        try:
            cached = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
            for raw in cached.get("headlines") or []:
                if isinstance(raw, dict):
                    headlines.append(Headline(**raw))
        except (OSError, json.JSONDecodeError, TypeError):
            headlines = []

    trends = [asdict(t) for t in CURATED_COMMS_TRENDS]
    gaps = [t for t in CURATED_COMMS_TRENDS if t.kit_status == "gap"]
    partial = [t for t in CURATED_COMMS_TRENDS if t.kit_status == "partial"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "curated_count": len(CURATED_COMMS_TRENDS),
        "gap_count": len(gaps),
        "partial_count": len(partial),
        "trends": trends,
        "headlines": [asdict(h) for h in headlines[:20]],
        "gaps": [asdict(t) for t in gaps],
        "partials": [asdict(t) for t in partial],
    }


def write_comms_trends_md(report: dict[str, Any]) -> Path:
    lines = [
        "# Agent communication trends",
        "",
        f"_Updated {report.get('generated_at', '')}_ · curated {report.get('curated_count')} · "
        f"gaps {report.get('gap_count')} · partial {report.get('partial_count')}_",
        "",
        "Research input for **comms improve forever** (`automation_comms_improve.py`).",
        "",
        "## Curated patterns",
        "",
    ]
    for t in report.get("trends") or []:
        if not isinstance(t, dict):
            continue
        status = str(t.get("kit_status") or "?").upper()
        lines.append(f"### [{status}] {t.get('theme')}")
        lines.append("")
        lines.append(str(t.get("summary") or ""))
        lines.append("")
        lines.append(f"- **Opportunity:** {t.get('opportunity')}")
        lines.append(f"- **Efficiency:** {t.get('efficiency_note')}")
        if t.get("sources"):
            lines.append(f"- **Sources:** {', '.join(t['sources'][:2])}")
        lines.append("")
    if report.get("headlines"):
        lines.extend(["## Recent headlines (HN)", ""])
        for h in report["headlines"][:12]:
            if not isinstance(h, dict):
                continue
            title = h.get("title") or ""
            url = h.get("url") or ""
            pts = h.get("points")
            suffix = f" ({pts} pts)" if pts is not None else ""
            lines.append(f"- [{title}]({url}){suffix}" if url else f"- {title}{suffix}")
        lines.append("")
    TRENDS_MD.parent.mkdir(parents=True, exist_ok=True)
    TRENDS_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    TRENDS_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return TRENDS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Comms efficiency research")
    parser.add_argument("--refresh", action="store_true", help="Fetch HN headlines")
    parser.add_argument("--write", action="store_true", help="Write notes/COMMS_TRENDS.md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_comms_report(refresh=args.refresh)
    if args.write:
        path = write_comms_trends_md(report)
        print(f"wrote {path}")
    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.write:
        for t in CURATED_COMMS_TRENDS:
            print(f"[{t.kit_status}] {t.theme} — {t.opportunity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
