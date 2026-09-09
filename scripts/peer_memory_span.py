#!/usr/bin/env python3
"""Memory span — 100x effective context via tiered external memory.

Models forget; the kit remembers. Three tiers inject each cycle:
  HOT  (~3.5k chars) — last cycle, journal pins, open assignments
  WARM (~12k chars)  — role learnings, vault, GLink, team slice
  COLD (~45k chars)  — knowledge_index retrieval (FTS + hybrid)

~60k chars/cycle vs ~600 from conversation tail alone ≈ **100x** recall surface.

Usage:
  python3 scripts/peer_memory_span.py --write
  python3 scripts/peer_memory_span.py --pack --role factory_engineer --task "fix dispatch"
  python3 scripts/peer_memory_span.py --record --role factory_engineer --text "wake path: peer_loop:820"
  ./scripts/peer memory-recall --role factory_engineer --query "peer_loop wake"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

MEMORY_SPAN_MD = ROOT / "notes" / "MEMORY_SPAN.md"
JOURNAL_DIR = auto.CONFIG_DIR / "memory-journal"
SUMMARY_PATH = auto.CONFIG_DIR / "memory-summaries.jsonl"

# Tier budgets (chars) — tune via automation.config.json memory_span.*
DEFAULT_HOT_MAX = 3500
DEFAULT_WARM_MAX = 12_000
DEFAULT_COLD_MAX = 45_000

MEMORY_MANDATE = """**Memory span (100x)** — you have ~128k tokens; the kit has terabytes.

Never rely on chat history alone. **Open files → retrieve → act:**

| Tier | Budget | Source | Rule |
|------|--------|--------|------|
| **Hot** | ~3.5k | Always-read paths + last_cycle + journal pins | Open listed files first every cycle |
| **Warm** | ~12k | learnings, vault, GLink, team slice | Role-scoped; don't re-discover |
| **Cold** | ~45k | knowledge_index FTS + hybrid | Query before reading whole files |

**Effective recall ≈ 100×** conversation tail when all tiers are used."""

# Canonical SoT paths — Hot block lists these every cycle (paths only; open the files).
ALWAYS_READ_PATHS: tuple[str, ...] = (
    "notes/AGENT_WORKING_MEMORY.md",
    "notes/REPO_DOMAIN_SMES.md",
    "notes/DOMAIN_OWNERS.md",
    "notes/MEMORY_SPAN.md",
    "notes/WORK_QUEUE.md",
    "scripts/self_improve_context.md",
    "notes/PEER_CONVERSATION.md",
    "AGENTS.md",
)

NO_PAY_HOT_LINE = (
    "NO PAY: free desktop/local/CLEAN only — never paid API/Stripe/credits"
)

ALWAYS_READ_HEADER = "## Always-read (open these — do not rely on chat memory)"

MEMORY_HABITS: tuple[str, ...] = (
    "Do not rely on chat memory — open Always-read paths every turn (Hot block lists them)",
    "After non-obvious work: `./scripts/peer memory-record --role ROLE --text \"file:line fact\"`",
    "Before Plan: read Hot tier + Active WQ; run `./scripts/peer memory-recall --query \"...\"` if gap",
    "Before reading a whole module: Cold tier should already cite the needle — grep index first",
    "Do not repeat last_cycle facts — they are in Hot tier on purpose",
    "Promote repeated journal facts to PROJECT_LEARNING via learn-record when team-wide",
)


def format_always_read_block() -> str:
    """Sticky Hot pointer — paths only; agents must open files, not invent from chat."""
    lines = [
        ALWAYS_READ_HEADER,
        "",
        f"- {NO_PAY_HOT_LINE}",
        "- **Chat truncates; kit files are SoT.** Open before Plan/edit:",
    ]
    for path in ALWAYS_READ_PATHS:
        lines.append(f"  - `{path}`")
    lines.append(
        "- Then use last_cycle (below) + Active WQ items; on error → "
        "`notes/AGENT_ERROR_PLAYBOOK.md`."
    )
    lines.append(
        "- **Fact librarian** (when pack large / before big tasks): "
        '`./scripts/peer fact-query "…"` — main=work, librarian=facts '
        "(`notes/SOP_AGENT_REMEMBRANCE.md`)."
    )
    try:
        import peer_fact_librarian as fl

        prefer, why = fl.should_prefer_librarian()
        lines.append(f"- Prefer librarian now: **{prefer}** — {why}")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


@dataclass(frozen=True)
class TierBudget:
    hot: int
    warm: int
    cold: int


def tier_budget() -> TierBudget:
    block = auto.CFG.get("memory_span") or {}
    if not isinstance(block, dict):
        block = {}
    return TierBudget(
        hot=int(block.get("hot_max_chars") or DEFAULT_HOT_MAX),
        warm=int(block.get("warm_max_chars") or DEFAULT_WARM_MAX),
        cold=int(block.get("cold_max_chars") or DEFAULT_COLD_MAX),
    )


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def journal_path(role_id: str) -> Path:
    return JOURNAL_DIR / f"{base_role_id(role_id)}.jsonl"


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 40] + "\n…_(tier truncated)_\n"


def record_memory(
    role_id: str,
    text: str,
    *,
    tags: list[str] | None = None,
    also_learn: bool = False,
) -> None:
    """Append a durable fact to role journal (hot tier source)."""
    body = str(text or "").strip()[:1500]
    if not body:
        raise ValueError("memory text required")
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "role_id": base_role_id(role_id),
        "text": body,
        "tags": list(tags or [])[:8],
        "ts": time.time(),
    }
    with journal_path(role_id).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    try:
        import peer_agent_comms as comms

        if comms.comms_enabled():
            comms.append_note(role_id, f"mem: {body[:500]}", kind="memory")
    except Exception:  # noqa: BLE001
        pass
    if also_learn:
        try:
            import peer_project_learning as pl

            pl.record_learning(role_id, f"mem: {body}", also_agent_note=False)
        except Exception:  # noqa: BLE001
            pass
    _maybe_compact_journal(role_id)


def _read_journal(role_id: str, *, limit: int = 40) -> list[dict]:
    path = journal_path(role_id)
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows[-limit:]


def _maybe_compact_journal(role_id: str, *, max_entries: int = 80) -> None:
    rows = _read_journal(role_id, limit=max_entries + 20)
    if len(rows) <= max_entries:
        return
    drop = rows[: len(rows) - max_entries]
    keep = rows[len(rows) - max_entries :]
    summary = "; ".join(str(r.get("text", ""))[:80] for r in drop[-12:])
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "role_id": base_role_id(role_id),
                    "summary": summary[:2000],
                    "dropped": len(drop),
                    "ts": time.time(),
                },
                separators=(",", ":"),
            )
            + "\n"
        )
    path = journal_path(role_id)
    path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in keep) + "\n",
        encoding="utf-8",
    )


def _score_row(row: dict, terms: list[str]) -> int:
    hay = f"{row.get('text', '')} {' '.join(row.get('tags') or [])}".lower()
    return sum(2 if t in hay else 0 for t in terms)


def recall_from_journal(
    role_id: str,
    query: str,
    *,
    limit: int = 8,
) -> list[dict]:
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2][:12]
    rows = _read_journal(role_id, limit=60)
    if not terms:
        return rows[-limit:]
    scored = sorted(rows, key=lambda r: _score_row(r, terms), reverse=True)
    return [r for r in scored if _score_row(r, terms) > 0][:limit] or rows[-limit:]


def build_recall_query(*, role_id: str, assignment: str = "", extra: str = "") -> str:
    parts: list[str] = []
    if assignment.strip():
        parts.append(assignment.strip()[:800])
    if extra.strip():
        parts.append(extra.strip()[:400])
    try:
        import peer_roles as roles

        for role in roles.load_roles():
            if role.id == role_id or base_role_id(role.id) == base_role_id(role_id):
                parts.extend(list(role.strengths[:6]))
                break
    except Exception:  # noqa: BLE001
        pass
    for row in _read_journal(role_id, limit=3):
        parts.append(str(row.get("text", ""))[:120])
    return " ".join(parts)[:4000]


def format_hot_tier(role_id: str, *, max_chars: int | None = None) -> str:
    cap = max_chars or tier_budget().hot
    lines = [
        "### Hot memory (always — do not re-explore)",
        "",
        format_always_read_block(),
        "",
    ]
    try:
        import peer_transcript as tx

        last = tx.format_last_cycle_block()
        if last.strip():
            lines.append(last.strip())
            lines.append("")
    except Exception:  # noqa: BLE001
        pass
    pins = _read_journal(role_id, limit=8)
    if pins:
        lines.append("**Journal pins:**")
        for row in pins[-8:]:
            lines.append(f"- {str(row.get('text', ''))[:220]}")
        lines.append("")
    try:
        import peer_work_assign as wa

        inbox = wa.format_assignments_block(for_role=role_id, max_entries=4)
        if inbox.strip() and "No open" not in inbox:
            lines.extend(["**Open assignments:**", inbox, ""])
    except Exception:  # noqa: BLE001
        pass
    summaries = _read_role_summaries(role_id, limit=2)
    if summaries:
        lines.append("**Compacted history:**")
        for s in summaries:
            lines.append(f"- {s[:300]}")
    return _truncate("\n".join(lines).strip(), cap)


def _read_role_summaries(role_id: str, *, limit: int = 3) -> list[str]:
    if not SUMMARY_PATH.is_file():
        return []
    base = base_role_id(role_id)
    out: list[str] = []
    try:
        for line in SUMMARY_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("role_id") == base:
                out.append(str(row.get("summary") or ""))
    except OSError:
        return []
    return out[-limit:]


def format_warm_tier(role_id: str, *, max_chars: int | None = None) -> str:
    cap = max_chars or tier_budget().warm
    lines = ["### Warm memory (role-scoped this cycle)", ""]
    try:
        import peer_project_learning as pl

        recent = pl.recent_learnings(role_id=role_id, limit=6)
        if recent:
            lines.append("**Recent learnings:**")
            for row in recent:
                lines.append(f"- {str(row.get('text', ''))[:180]}")
            lines.append("")
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_agent_comms as comms

        if comms.comms_enabled():
            state = comms.ensure_agent(role_id)
            summary = str(state.get("summary") or "").strip()
            if summary:
                lines.extend(["**Vault summary:**", summary[:1200], ""])
            bus = comms.read_bus(limit=12, for_role=role_id)
            if bus:
                lines.append("**GLink (for you):**")
                for msg in bus[-5:]:
                    p = json.dumps(msg.get("p") or {})[:100]
                    lines.append(f"- {msg.get('t')} {msg.get('f')}: {p}")
                lines.append("")
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_team_context as tc

        slice_md = tc.load_team_context_markdown(max_chars=min(2500, cap // 2))
        if slice_md.strip():
            lines.extend(["**Team slice:**", slice_md[: min(2500, cap // 2)], ""])
    except Exception:  # noqa: BLE001
        pass
    return _truncate("\n".join(lines).strip(), cap)


def format_cold_tier(
    role_id: str,
    *,
    assignment: str = "",
    conversation: str = "",
    max_chars: int | None = None,
) -> str:
    cap = max_chars or tier_budget().cold
    lines = ["### Cold memory (retrieved index — 100x surface)", ""]
    query = build_recall_query(role_id=role_id, assignment=assignment)
    if conversation.strip():
        query = f"{query} {conversation[-1500:]}".strip()[:4000]
    journal_hits = recall_from_journal(role_id, query, limit=5)
    if journal_hits:
        lines.append("**Journal recall:**")
        for row in journal_hits:
            lines.append(f"- {str(row.get('text', ''))[:200]}")
        lines.append("")
    try:
        import knowledge_retrieve as kr

        # Sparse FTS only — never load mamba/torch into peer_loop for cold tier.
        block = kr.inject_for_dispatch(
            conversation=conversation, extra=query, quick=False, hybrid=False
        )
        if block.strip():
            lines.append(block.strip())
        else:
            import knowledge_index as ki
            import knowledge_index_config as kcfg

            if kcfg.enabled():
                hits = ki.retrieve(query, hybrid=False)
                block = ki.format_hits(hits, max_chars=max(2000, cap - 800))
                if block.strip():
                    lines.append(block.strip())
    except Exception as exc:  # noqa: BLE001
        lines.append(f"- knowledge retrieve unavailable ({exc})")
    finally:
        # Only unload if mamba already imported — never import torch just to check.
        kmamba = sys.modules.get("knowledge_mamba")
        if kmamba is not None:
            try:
                if kmamba.status().get("loaded"):
                    kmamba.unload()
            except Exception:  # noqa: BLE001
                pass
    if len(lines) <= 2:
        lines.append(
            "_Cold tier empty — run `./scripts/peer knowledge-index --index` or memory-record facts._"
        )
    return _truncate("\n".join(lines).strip(), cap)


def format_memory_pack(
    *,
    role_id: str,
    assignment: str = "",
    conversation: str = "",
    include_cold: bool = True,
) -> str:
    budget = tier_budget()
    parts = [
        "## Memory span (100x external — read tiers in order)",
        "",
        MEMORY_MANDATE,
        "",
        format_hot_tier(role_id, max_chars=budget.hot),
        "",
        format_warm_tier(role_id, max_chars=budget.warm),
    ]
    if include_cold:
        parts.extend([
            "",
            format_cold_tier(
                role_id,
                assignment=assignment,
                conversation=conversation,
                max_chars=budget.cold,
            ),
        ])
    parts.extend([
        "",
        "_Record:_ `./scripts/peer memory-record --role "
        f"{role_id} --text \"file:line fact\"` · "
        "_Recall:_ `./scripts/peer memory-recall --query \"...\"`",
    ])
    return "\n".join(parts).strip()


def format_memory_habits_block() -> str:
    lines = ["## Memory span habits", "", MEMORY_MANDATE, "", "**Habits:**", ""]
    for i, h in enumerate(MEMORY_HABITS, 1):
        lines.append(f"{i}. {h}")
    total = tier_budget().hot + tier_budget().warm + tier_budget().cold
    lines.append("")
    lines.append(
        f"_Tier budget:_ hot {tier_budget().hot} + warm {tier_budget().warm} + "
        f"cold {tier_budget().cold} ≈ **{total // 1000}k chars/cycle** (~100× chat tail)."
    )
    return "\n".join(lines).strip()


def write_memory_span_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    budget = tier_budget()
    lines = [
        "# Memory span — 100x effective context",
        "",
        f"_Updated {now}_ · tiered external memory for every agent",
        "",
        MEMORY_MANDATE,
        "",
        f"## Tier budgets\n\n- Hot: {budget.hot} chars\n- Warm: {budget.warm} chars\n"
        f"- Cold: {budget.cold} chars\n- **Total:** ~{(budget.hot + budget.warm + budget.cold) // 1000}k chars/cycle\n",
        "## Habits",
        "",
    ]
    for i, h in enumerate(MEMORY_HABITS, 1):
        lines.append(f"{i}. {h}")
    lines.extend([
        "",
        "## Always-read paths (Hot inject every cycle)",
        "",
        "Chat memory is not SoT. Open these before acting:",
        "",
    ])
    for path in ALWAYS_READ_PATHS:
        lines.append(f"- `{path}`")
    lines.extend([
        "",
        f"- Sticky: `{NO_PAY_HOT_LINE}`",
        "",
        "## Commands",
        "",
        "```bash",
        "./scripts/peer memory              # refresh this doc",
        "./scripts/peer memory-pack --role factory_engineer --task \"...\"",
        "./scripts/peer memory-record --role ROLE --text \"path:line fact\"",
        "./scripts/peer memory-recall --role ROLE --query \"peer_loop wake\"",
        "./scripts/peer knowledge-search \"query\"   # cold tier source",
        "```",
        "",
    ])
    MEMORY_SPAN_MD.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_SPAN_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return MEMORY_SPAN_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Memory span — 100x tiered external memory")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--pack", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--recall", action="store_true")
    parser.add_argument("--role", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--task", default="", help="Assignment for pack/cold query")
    parser.add_argument("--also-learn", action="store_true")
    parser.add_argument("--no-cold", action="store_true")
    args = parser.parse_args()

    if args.record:
        if not args.role or not args.text:
            print("memory-record requires --role and --text", file=sys.stderr)
            return 1
        record_memory(args.role, args.text, also_learn=args.also_learn)
        print(f"recorded memory for {args.role}")
        return 0

    if args.recall:
        role = args.role or "orchestrator"
        query = args.query or args.task or args.text
        if not query:
            print("memory-recall requires --query (or --task)", file=sys.stderr)
            return 1
        for row in recall_from_journal(role, query):
            print(f"- {row.get('text', '')}")
        try:
            import knowledge_index as ki
            import knowledge_index_config as kcfg

            if kcfg.enabled():
                # COMPRESSION_2026_09_03 — Sparse FTS only; default hybrid loaded mamba-2.8b (~26GB RSS) on DGX.
                hits = ki.retrieve(query, hybrid=False)
                if hits:
                    print("")
                    print(ki.format_hits(hits, max_chars=8000))
        except Exception:  # noqa: BLE001
            pass
        return 0

    if args.pack:
        if not args.role:
            print("memory-pack requires --role", file=sys.stderr)
            return 1
        print(
            format_memory_pack(
                role_id=args.role,
                assignment=args.task,
                include_cold=not args.no_cold,
            )
        )
        return 0

    path = write_memory_span_md()
    print(f"memory-span: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
