#!/usr/bin/env python3
"""Fact Librarian — remembrance relay for the main agent.

Needle: OVERSEER_FACT_LIBRARIAN_2026_09_07

Main agent = work. Librarian = facts. Do not stuff the whole repo into chat.

Mechanical MVP (``--query``):
  - Load lossless pack index (paths/sha/kind) if present
  - Scan thin live SoT (WORK_QUEUE Active, AGENTS sticky, last_cycle, MEMORY_SPAN)
  - Return a compact fact relay (paths + needles + queue lines)

Optional ``--agent``: print a librarian-only prompt for a tiny free-desktop
cursor-agent spawn (never paid API). Does not auto-bill.

Usage:
  python3 scripts/peer_fact_librarian.py --query "plan-gate noop"
  ./scripts/peer fact-query "WORK_QUEUE Active"
  python3 scripts/peer_fact_librarian.py --query "..." --agent
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import zlib
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

NEEDLE = "OVERSEER_FACT_LIBRARIAN_2026_09_07"
PACK_PATH = ROOT / "notes" / "memory_artifacts" / "repo_memory_pack.json.z"
PACK_SUMMARY = PACK_PATH.with_suffix(PACK_PATH.suffix + ".summary.json")
DOMAIN_MAP_PATH = SCRIPTS / "repo_domain_smes.json"
DOMAIN_OWNERS_MD = ROOT / "notes" / "DOMAIN_OWNERS.md"
FACT_QUERY_RECEIPT_JSON = auto.CONFIG_DIR / "fact-query-receipt.json"

# When pack JSON (uncompressed ledger) exceeds this, Hot/pre-dispatch should
# prefer librarian over stuffing notes into the prompt.
LIBRARIAN_PACK_JSON_THRESHOLD_BYTES = 512_000  # 512 KB
LIBRARIAN_FILE_COUNT_THRESHOLD = 200
RECEIPT_MAX_AGE_SEC = 3600  # 1h — plan-gate librarian-receipt window


def _short_fp(raw: bytes, n: int = 16) -> str:
    """zlib adler+crc — COMPRESSION_ZLIB_FACT_LIBRARIAN_2026_09_07.

    Eager ``hashlib`` pulled libcrypto into peer_loop once ``peer_agent_gates`` /
    ``peer_memory_span`` import the librarian (~4–6 MB sticky).
    """
    n = max(4, int(n))
    digest = (
        f"{zlib.adler32(raw) & 0xffffffff:08x}"
        f"{zlib.crc32(raw) & 0xffffffff:08x}"
    )
    return digest[:n]

_TERM_SPLIT = re.compile(r"[^\w./:-]+")
_PATHISH = re.compile(
    r"(?:(?:notes|scripts|dashboard|tests|repos)/[\w./\-*]+|AGENTS\.md|"
    r"COMPRESSION_[\w.]+\.md|BITNET_[\w.]+\.md|train\.(?:html|js)|server\.py)",
    re.IGNORECASE,
)
_OVERSEER = re.compile(r"(OVERSEER_[A-Z0-9_]+_\d{4}_\d{2}_\d{2})")


def load_domain_map(*, path: Path | None = None) -> dict[str, Any]:
    p = path or DOMAIN_MAP_PATH
    if not p.is_file():
        return {"version": 1, "domains": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "domains": []}
    if not isinstance(data, dict):
        return {"version": 1, "domains": []}
    domains = data.get("domains") or []
    data["domains"] = [d for d in domains if isinstance(d, dict) and d.get("id")]
    return data


def list_domains() -> list[dict[str, Any]]:
    return list(load_domain_map().get("domains") or [])


def get_domain(domain_id: str) -> dict[str, Any] | None:
    want = str(domain_id or "").strip().lower()
    for d in list_domains():
        if str(d.get("id") or "").lower() == want:
            return d
    return None


def path_in_domain(path: str, domain: dict[str, Any]) -> bool:
    """True if relative path is in domain globs or SoT list."""
    from fnmatch import fnmatch

    rel = path.replace("\\", "/").lstrip("./")
    for g in domain.get("globs") or []:
        pat = str(g).replace("\\", "/")
        if pat.endswith("/**"):
            prefix = pat[:-3].rstrip("/")
            if rel == prefix or rel.startswith(prefix + "/"):
                return True
        elif fnmatch(rel, pat):
            return True
    for s in domain.get("sot") or []:
        sot = str(s).replace("\\", "/")
        if rel == sot or rel.startswith(sot.rstrip("/") + "/"):
            return True
    return False


def extract_query_paths(query: str) -> list[str]:
    """Pull path-like tokens from a query for DOMAIN_OWNERS / glob routing."""
    found: list[str] = []
    seen: set[str] = set()
    for m in _PATHISH.finditer(query or ""):
        rel = m.group(0).replace("\\", "/").lstrip("./")
        if rel not in seen:
            seen.add(rel)
            found.append(rel)
    for t in _terms(query):
        if "/" in t or t.endswith(".md") or t.endswith(".py"):
            rel = t.replace("\\", "/").lstrip("./")
            if rel not in seen and len(rel) > 3:
                seen.add(rel)
                found.append(rel)
    return found[:16]


def domain_for_path(path: str) -> dict[str, Any] | None:
    """Map a relative path to its Domain SME (first matching domain in map order)."""
    rel = path.replace("\\", "/").lstrip("./")
    for d in list_domains():
        if path_in_domain(rel, d):
            return d
    return None


def auto_pick_domain(query: str) -> tuple[dict[str, Any] | None, list[tuple[str, int]]]:
    """Pick best domain from query keywords + path tokens (DOMAIN_OWNERS globs)."""
    q = query.lower()
    terms = _terms(query)
    path_hits = extract_query_paths(query)
    scored: list[tuple[str, int]] = []
    best: dict[str, Any] | None = None
    best_sc = 0
    for d in list_domains():
        sc = 0
        did = str(d.get("id") or "")
        if did and did in q:
            sc += 20
        for kw in d.get("keywords") or []:
            kw_l = str(kw).lower()
            if kw_l and kw_l in q:
                sc += 8
            for t in terms:
                if t and t in kw_l:
                    sc += 2
        for sot in d.get("sot") or []:
            if str(sot).lower() in q:
                sc += 5
        for p in path_hits:
            if path_in_domain(p, d):
                sc += 15
        scored.append((did, sc))
        if sc > best_sc:
            best_sc = sc
            best = d
    scored.sort(key=lambda x: -x[1])
    if best_sc <= 0:
        return None, scored
    return best, scored


def format_domain_owners_md(*, domains: list[dict[str, Any]] | None = None) -> str:
    """CODEOWNERS-like DOMAIN_OWNERS.md body from repo_domain_smes.json."""
    rows = domains if domains is not None else list_domains()
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# DOMAIN_OWNERS — path → Domain SME",
        "",
        f"_Auto-generated {now} from `scripts/repo_domain_smes.json` — "
        "do not hand-edit; regenerate via `./scripts/peer domain-owners --write`._",
        "",
        f"Needle: `{NEEDLE}`",
        "",
        "Fact Librarian routes `fact-query` using this map "
        "(same globs/SoT as the JSON). Main agent asks "
        "`./scripts/peer fact-query [--domain ID] \"…\"` — does not deep-read "
        "other domains.",
        "",
        "## Domains",
        "",
        "| Domain id | Role | Globs (summary) | SoT |",
        "|-----------|------|-----------------|-----|",
    ]
    for d in rows:
        did = str(d.get("id") or "")
        role = str(d.get("role_id") or "")
        globs = ", ".join(f"`{g}`" for g in (d.get("globs") or [])[:4])
        extra = len(d.get("globs") or []) - 4
        if extra > 0:
            globs += f" (+{extra})"
        sot = ", ".join(f"`{s}`" for s in (d.get("sot") or [])[:3])
        lines.append(f"| `{did}` | `{role}` | {globs} | {sot} |")
    lines.extend(
        [
            "",
            "## CODEOWNERS-like rules",
            "",
            "```",
            "# path-pattern → domain_id (role_id)",
        ]
    )
    for d in rows:
        did = str(d.get("id") or "")
        role = str(d.get("role_id") or "")
        lines.append(f"# domain:{did} role:{role}")
        for g in d.get("globs") or []:
            lines.append(f"{g}  @{did}/{role}")
        for s in d.get("sot") or []:
            lines.append(f"{s}  @{did}/{role}")
        lines.append("")
    lines.extend(
        [
            "```",
            "",
            "## Invoke",
            "",
            "```bash",
            "./scripts/peer domain-owners --write   # refresh this file",
            "./scripts/peer fact-domains",
            './scripts/peer fact-query "noop plan-gate"',
            "./scripts/peer fact-query --domain queue_sync \"Active\"",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_domain_owners_md(*, path: Path | None = None) -> Path:
    out = path or DOMAIN_OWNERS_MD
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_domain_owners_md(), encoding="utf-8")
    return out


def write_fact_query_receipt(relay: dict[str, Any], *, path: Path | None = None) -> Path:
    """Persist a short receipt so plan-gate can prove librarian was consulted."""
    out = path or FACT_QUERY_RECEIPT_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = float(relay.get("ts") or time.time())
    q = str(relay.get("query") or "")
    rid = _short_fp(f"{ts}:{q}:{NEEDLE}".encode(), 16)
    dom = relay.get("domain") or {}
    payload = {
        "receipt_id": rid,
        "ts": ts,
        "needle": NEEDLE,
        "query": q[:400],
        "domain_id": dom.get("id"),
        "domain_source": dom.get("source"),
        "prefer_librarian": (relay.get("remembrance") or {}).get("prefer_librarian"),
        "no_pay": True,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def load_fact_query_receipt(
    *,
    path: Path | None = None,
    max_age_sec: int = RECEIPT_MAX_AGE_SEC,
) -> tuple[bool, dict[str, Any], str]:
    """Return (fresh_ok, payload, detail)."""
    p = path or FACT_QUERY_RECEIPT_JSON
    if not p.is_file():
        return False, {}, "no fact-query receipt — run ./scripts/peer fact-query \"…\""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, {}, f"receipt unreadable ({exc})"
    if not isinstance(data, dict):
        return False, {}, "receipt not an object"
    ts = float(data.get("ts") or 0)
    age = time.time() - ts
    if ts <= 0 or age > max_age_sec:
        return (
            False,
            data,
            f"receipt stale ({int(age)}s > {max_age_sec}s) id={data.get('receipt_id')}",
        )
    rid = str(data.get("receipt_id") or "")
    return (
        True,
        data,
        f"receipt {rid} age={int(age)}s domain={data.get('domain_id') or '—'}",
    )


def should_prefer_librarian(*, pack_path: Path | None = None) -> tuple[bool, str]:
    """True when compressed store is large enough that main agent should query librarian."""
    path = pack_path or PACK_PATH
    if not path.is_file():
        return False, "no pack yet — open Always-read SoT directly"
    try:
        import peer_memory_compress as pmc

        header, payload = pmc.read_pack(path)
    except Exception as exc:  # noqa: BLE001
        return False, f"pack unreadable ({exc})"
    jb = int(header.get("json_bytes") or 0)
    nfiles = int((payload.get("stats") or {}).get("file_count") or len(payload.get("files") or []))
    if jb >= LIBRARIAN_PACK_JSON_THRESHOLD_BYTES or nfiles >= LIBRARIAN_FILE_COUNT_THRESHOLD:
        return True, (
            f"pack json={jb}B files={nfiles} ≥ threshold "
            f"({LIBRARIAN_PACK_JSON_THRESHOLD_BYTES}B / {LIBRARIAN_FILE_COUNT_THRESHOLD} files) "
            f"— use `./scripts/peer fact-query [--domain ID]` instead of stuffing notes"
        )
    return False, f"pack small (json={jb}B files={nfiles}) — Always-read may suffice"


def _terms(query: str) -> list[str]:
    return [t.lower() for t in _TERM_SPLIT.split(query) if len(t) > 1][:24]


def _score(hay: str, terms: list[str]) -> int:
    low = hay.lower()
    return sum(3 if t in low else 0 for t in terms)


def _load_pack_index(pack_path: Path | None = None) -> dict[str, Any]:
    path = pack_path or PACK_PATH
    if not path.is_file():
        return {"files": [], "header": {}, "stats": {}}
    import peer_memory_compress as pmc

    header, payload = pmc.read_pack(path)
    return {
        "files": payload.get("files") or [],
        "header": header,
        "stats": payload.get("stats") or {},
        "policy": payload.get("policy") or {},
    }


def _active_queue_lines(*, limit: int = 12) -> list[str]:
    path = ROOT / "notes" / "WORK_QUEUE.md"
    if not path.is_file():
        return []
    lines: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    in_active = False
    for line in text.splitlines():
        if line.startswith("## Active"):
            in_active = True
            continue
        if in_active and line.startswith("## "):
            break
        if in_active and line.strip().startswith("- ["):
            lines.append(line.strip()[:220])
            if len(lines) >= limit:
                break
    if not lines:
        # fallback: any open checkbox near top
        for line in text.splitlines():
            if line.strip().startswith("- [ ]"):
                lines.append(line.strip()[:220])
                if len(lines) >= limit:
                    break
    return lines


def _last_cycle_facts() -> dict[str, Any]:
    try:
        import peer_transcript as pt

        state = pt.load_state()
        lc = state.get("last_cycle") if isinstance(state, dict) else None
        if not isinstance(lc, dict):
            return {}
        return {
            "verify_ok": lc.get("verify_ok"),
            "noop": lc.get("noop"),
            "failure_type": lc.get("failure_type"),
            "queue_fp": lc.get("queue_fp"),
            "note": str(lc.get("note") or "")[:160],
            "rc": lc.get("rc"),
        }
    except Exception:  # noqa: BLE001
        return {}


def _scan_live_snippets(
    query: str,
    terms: list[str],
    *,
    domain: dict[str, Any] | None = None,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Grep thin live SoT files for query terms — domain SoT when set."""
    targets: list[Path] = [
        ROOT / "notes" / "AGENT_WORKING_MEMORY.md",
        ROOT / "notes" / "MEMORY_SPAN.md",
        ROOT / "notes" / "WORK_QUEUE.md",
        ROOT / "scripts" / "self_improve_context.md",
        ROOT / "AGENTS.md",
        ROOT / "notes" / "AGENT_ERROR_PLAYBOOK.md",
        ROOT / "notes" / "SOP_LOSSLESS_MEMORY_COMPRESSION.md",
        ROOT / "notes" / "SOP_AGENT_REMEMBRANCE.md",
        ROOT / "notes" / "REPO_DOMAIN_SMES.md",
    ]
    if domain:
        for s in domain.get("sot") or []:
            p = ROOT / str(s)
            if p.is_file() and p not in targets:
                targets.append(p)
    hits: list[tuple[int, dict[str, str]]] = []
    for path in targets:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(ROOT))
        for i, line in enumerate(text.splitlines(), 1):
            sc = _score(line, terms) if terms else 0
            if terms and sc <= 0:
                continue
            if not terms and i > 30:
                break
            if not terms:
                sc = 1
            needle = ""
            m = _OVERSEER.search(line)
            if m:
                needle = m.group(1)
            hits.append(
                (
                    sc,
                    {
                        "path": f"{rel}:{i}",
                        "line": line.strip()[:180],
                        "needle": needle,
                    },
                )
            )
    hits.sort(key=lambda x: -x[0])
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in hits:
        key = row["path"]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _pack_path_hits(
    index: dict[str, Any],
    terms: list[str],
    *,
    domain: dict[str, Any] | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    files = index.get("files") or []
    scored: list[tuple[int, dict[str, Any]]] = []
    for ent in files:
        path = str(ent.get("path") or "")
        if domain and not path_in_domain(path, domain):
            continue
        sc = _score(path, terms) if terms else 0
        if domain and not terms:
            sc = 2  # domain slice alone is enough
        elif terms and sc <= 0:
            if domain:
                sc = 1  # still list domain paths matching slice
            else:
                continue
        if not terms and not domain:
            low = path.lower()
            if not any(
                k in low
                for k in ("work_queue", "agents", "memory", "peer_", "sop_", "automation")
            ):
                continue
            sc = 1
        scored.append(
            (
                sc,
                {
                    "path": path,
                    "sha256": str(ent.get("sha256") or "")[:16],
                    "kind": ent.get("kind"),
                    "size": ent.get("size"),
                    "embedded": bool(ent.get("embedded")),
                },
            )
        )
    scored.sort(key=lambda x: (-x[0], x[1]["path"]))
    return [row for _, row in scored[:limit]]


def build_fact_relay(
    query: str,
    *,
    pack_path: Path | None = None,
    domain_id: str | None = None,
    auto_domain: bool = True,
    max_paths: int = 12,
    max_snippets: int = 8,
) -> dict[str, Any]:
    terms = _terms(query)
    index = _load_pack_index(pack_path)
    prefer, prefer_why = should_prefer_librarian(pack_path=pack_path)

    domain: dict[str, Any] | None = None
    domain_scores: list[tuple[str, int]] = []
    domain_source = "none"
    if domain_id:
        domain = get_domain(domain_id)
        domain_source = "explicit"
        if domain is None:
            domain_source = f"unknown:{domain_id}"
    elif auto_domain:
        domain, domain_scores = auto_pick_domain(query)
        domain_source = "auto" if domain else "auto_none"

    classifier: dict[str, Any] | None = None
    if auto_domain and not domain_id:
        try:
            import niche_domain_classify as ndc

            clf = ndc.classify(query)
            classifier = {
                "domain_id": clf.get("domain_id"),
                "confidence": clf.get("confidence"),
                "source": clf.get("source"),
                "model_ready": ndc.model_available(),
            }
        except Exception:  # noqa: BLE001 — classifier is advisory only
            classifier = None

    relay = {
        "needle": NEEDLE,
        "ts": time.time(),
        "query": query.strip()[:400],
        "terms": terms,
        "domain": {
            "id": (domain or {}).get("id"),
            "title": (domain or {}).get("title"),
            "role_id": (domain or {}).get("role_id"),
            "source": domain_source,
            "sot": (domain or {}).get("sot") or [],
            "globs": (domain or {}).get("globs") or [],
            "scores_top": domain_scores[:5],
        },
        "classifier": classifier,
        "remembrance": {
            "main_agent": "do the work — do not re-read whole repo",
            "librarian": "facts only — this relay (domain-scoped when set)",
            "prefer_librarian": prefer,
            "prefer_why": prefer_why,
        },
        "pack": {
            "path": str((pack_path or PACK_PATH).relative_to(ROOT))
            if (pack_path or PACK_PATH).is_file()
            and (pack_path or PACK_PATH).is_relative_to(ROOT)
            else str(pack_path or PACK_PATH),
            "codec": (index.get("header") or {}).get("codec"),
            "pack_bytes": (index.get("header") or {}).get("pack_bytes"),
            "json_bytes": (index.get("header") or {}).get("json_bytes"),
            "file_count": (index.get("stats") or {}).get("file_count"),
            "raw_bytes": (index.get("stats") or {}).get("raw_bytes"),
        },
        "last_cycle": _last_cycle_facts(),
        "active_queue": _active_queue_lines(),
        "pack_paths": _pack_path_hits(
            index, terms, domain=domain, limit=max_paths
        ),
        "live_snippets": _scan_live_snippets(
            query, terms, domain=domain, limit=max_snippets
        ),
        "always_read": [
            "notes/AGENT_WORKING_MEMORY.md",
            "notes/REPO_DOMAIN_SMES.md",
            "notes/DOMAIN_OWNERS.md",
            "notes/WORK_QUEUE.md",
            "scripts/self_improve_context.md",
            "AGENTS.md",
        ],
        "domain_owners": str(DOMAIN_OWNERS_MD.relative_to(ROOT)),
        "no_pay": "free desktop/local/CLEAN only — never paid API/Stripe/credits",
        "invoke": './scripts/peer fact-query [--domain ID] "YOUR QUESTION"',
    }
    return relay


def format_relay_text(relay: dict[str, Any]) -> str:
    lines = [
        "## Fact librarian relay (compact — not whole-repo)",
        f"- Needle: `{relay.get('needle')}`",
        f"- Query: {relay.get('query')!r}",
        f"- Prefer librarian: {relay.get('remembrance', {}).get('prefer_librarian')} "
        f"— {relay.get('remembrance', {}).get('prefer_why')}",
        f"- NO PAY: {relay.get('no_pay')}",
        "",
    ]
    dom = relay.get("domain") or {}
    if dom.get("id"):
        lines.extend(
            [
                "### Domain SME",
                f"- `{dom.get('id')}` — {dom.get('title')} "
                f"(role=`{dom.get('role_id')}`, source={dom.get('source')})",
                f"- SoT: {', '.join(f'`{s}`' for s in (dom.get('sot') or [])[:6])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "### Domain SME",
                f"- _(none — source={dom.get('source')}; pass `--domain ID` or add keywords)_",
                "",
            ]
        )
    clf = relay.get("classifier") or {}
    if clf:
        lines.extend(
            [
                "### Domain classifier",
                f"- domain_id=`{clf.get('domain_id')}` source={clf.get('source')} "
                f"confidence={clf.get('confidence')} model_ready={clf.get('model_ready')}",
                "",
            ]
        )
    lines.append("### Pack")
    pack = relay.get("pack") or {}
    lines.append(
        f"- `{pack.get('path')}` codec={pack.get('codec')} "
        f"pack={pack.get('pack_bytes')}B json={pack.get('json_bytes')}B "
        f"files={pack.get('file_count')} raw={pack.get('raw_bytes')}"
    )
    lc = relay.get("last_cycle") or {}
    if lc:
        lines.extend(
            [
                "",
                "### Last cycle",
                f"- verify_ok={lc.get('verify_ok')} noop={lc.get('noop')} "
                f"ft={lc.get('failure_type')} rc={lc.get('rc')}",
                f"- queue_fp={lc.get('queue_fp')}",
                f"- note={lc.get('note')!r}",
            ]
        )
    aq = relay.get("active_queue") or []
    lines.extend(["", "### Active queue (live SoT)"])
    if not aq:
        lines.append("- _(empty Active / no open items)_")
    else:
        for row in aq[:10]:
            lines.append(f"- {row}")
    paths = relay.get("pack_paths") or []
    lines.extend(["", "### Pack index hits (domain-scoped path keys)"])
    if not paths:
        lines.append("- _(no path hits — broaden query or pick --domain)_")
    else:
        for p in paths:
            emb = "embed" if p.get("embedded") else "hash_ref"
            lines.append(
                f"- `{p.get('path')}` [{p.get('kind')}/{emb}] "
                f"sha={p.get('sha256')}… size={p.get('size')}"
            )
    snips = relay.get("live_snippets") or []
    lines.extend(["", "### Live SoT snippets"])
    if not snips:
        lines.append("- _(no snippet hits)_")
    else:
        for s in snips:
            needle = f" `{s['needle']}`" if s.get("needle") else ""
            lines.append(f"- `{s.get('path')}`{needle}: {s.get('line')}")
    lines.extend(
        [
            "",
            "### Always-read",
            "- " + " · ".join(f"`{p}`" for p in (relay.get("always_read") or [])),
            f"- Invoke again: `{relay.get('invoke')}`",
            "- Domains: `notes/REPO_DOMAIN_SMES.md` · `notes/DOMAIN_OWNERS.md` · "
            "`python3 scripts/peer_fact_librarian.py --list-domains`",
        ]
    )
    return "\n".join(lines)


def format_librarian_agent_prompt(query: str, *, domain_id: str | None = None) -> str:
    """Librarian-only prompt for optional tiny free-desktop agent spawn."""
    relay = build_fact_relay(query, domain_id=domain_id, auto_domain=not domain_id)
    dom = (relay.get("domain") or {}).get("id") or "auto"
    return (
        "You are the Fact Librarian / domain SME niche only. Do NOT edit code or the queue.\n"
        f"Domain focus: {dom}. Return a tighter relay of facts the main agent needs.\n"
        f"Query: {query!r}\n"
        "Constraints: free desktop/local/CLEAN only — never paid API.\n"
        "Read only domain SoT + Always-read index + pack summary + last_cycle.\n\n"
        "Mechanical seed relay:\n\n"
        + format_relay_text(relay)
    )


def format_hot_librarian_block() -> str:
    prefer, why = should_prefer_librarian()
    domains = ", ".join(d.get("id", "") for d in list_domains()[:8])
    more = max(0, len(list_domains()) - 8)
    extra = f" (+{more})" if more else ""
    owners = "ok" if DOMAIN_OWNERS_MD.is_file() else "missing — ./scripts/peer domain-owners --write"
    return (
        "## Fact librarian + domain SMEs (remembrance)\n"
        f"- Prefer librarian now: **{prefer}** — {why}\n"
        "- Main = work; librarian/SME = facts for one domain — not whole-repo.\n"
        f"- Domains: `{domains}`{extra} — `notes/REPO_DOMAIN_SMES.md` · "
        f"`notes/DOMAIN_OWNERS.md` ({owners})\n"
        '- Invoke: `./scripts/peer fact-query [--domain queue_sync] "…"`\n'
        f"- Needle: `{NEEDLE}`"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fact Librarian remembrance relay")
    ap.add_argument("--query", "-q", default="", help="fact query")
    ap.add_argument("query_pos", nargs="*", help="query words (alt to --query)")
    ap.add_argument("--domain", "-d", default="", help="domain id (see --list-domains)")
    ap.add_argument(
        "--auto",
        action="store_true",
        default=True,
        help="auto-pick domain from query keywords (default)",
    )
    ap.add_argument("--no-auto", action="store_true", help="disable auto domain pick")
    ap.add_argument("--json", action="store_true", help="emit JSON relay")
    ap.add_argument("--agent", action="store_true", help="print librarian-only agent prompt")
    ap.add_argument("--pack", type=Path, default=None)
    ap.add_argument("--threshold-status", action="store_true")
    ap.add_argument("--list-domains", action="store_true")
    ap.add_argument(
        "--write-owners",
        action="store_true",
        help="Regenerate notes/DOMAIN_OWNERS.md from repo_domain_smes.json",
    )
    ap.add_argument(
        "--no-receipt",
        action="store_true",
        help="Skip writing fact-query receipt (tests / dry relay)",
    )
    args = ap.parse_args(argv)

    if args.write_owners:
        path = write_domain_owners_md()
        print(f"domain-owners: wrote {path.relative_to(ROOT)}")
        return 0

    if args.list_domains:
        for d in list_domains():
            print(
                f"{d.get('id'):20} role={d.get('role_id'):28} {d.get('title')}"
            )
        return 0

    if args.threshold_status:
        prefer, why = should_prefer_librarian(pack_path=args.pack)
        print(
            json.dumps(
                {
                    "prefer_librarian": prefer,
                    "why": why,
                    "needle": NEEDLE,
                    "domains": [d.get("id") for d in list_domains()],
                    "domain_owners": str(DOMAIN_OWNERS_MD.relative_to(ROOT)),
                },
                indent=2,
            )
        )
        return 0

    q = (args.query or "").strip()
    if not q and args.query_pos:
        q = " ".join(args.query_pos).strip()
    if not q:
        print(
            "--query required (or --list-domains / --threshold-status / --write-owners)",
            file=sys.stderr,
        )
        return 2

    auto = not args.no_auto
    domain_id = (args.domain or "").strip() or None

    if args.agent:
        print(format_librarian_agent_prompt(q, domain_id=domain_id))
        return 0

    relay = build_fact_relay(
        q,
        pack_path=args.pack,
        domain_id=domain_id,
        auto_domain=auto and not domain_id,
    )
    if not args.no_receipt:
        receipt_path = write_fact_query_receipt(relay)
        relay["receipt"] = {
            "path": str(receipt_path),
            "receipt_id": json.loads(receipt_path.read_text(encoding="utf-8")).get(
                "receipt_id"
            ),
        }
    if args.json:
        print(json.dumps(relay, indent=2))
    else:
        text = format_relay_text(relay)
        if relay.get("receipt"):
            text += (
                f"\n- Receipt: `{relay['receipt'].get('receipt_id')}` "
                f"→ plan-gate librarian-receipt preflight"
            )
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())