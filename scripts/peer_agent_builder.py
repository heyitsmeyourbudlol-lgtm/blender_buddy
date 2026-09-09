#!/usr/bin/env python3
"""Agent Builder — provision specialist roles in seconds (NO PAY).

Needle: OVERSEER_AGENT_BUILDER_2026_09_07

Protocol: spec → validate → provision → self-check → dispatch.
Patches peer_tasks.json (agent_roles + task_templates + match_rules) atomically.
Never deletes other roles. Refuses paid/billing specialists without --human-ack.

Usage::
    python3 scripts/peer_agent_builder.py --list
    python3 scripts/peer_agent_builder.py --validate agent_builder
    python3 scripts/peer_agent_builder.py --who "[agent-builder] refine spec"
    python3 scripts/peer_agent_builder.py --dry-run --spec path.json
    python3 scripts/peer_agent_builder.py --write --id … --title … --strengths … --match …
    ./scripts/peer agent-build --write --spec …
    ./scripts/peer agent-who "task text"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

NEEDLE = "OVERSEER_AGENT_BUILDER_2026_09_07"
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PEER_TASKS = SCRIPTS / "peer_tasks.json"
AUTOMATION_MD = ROOT / "notes" / "AUTOMATION.md"
DOMAIN_SMES_JSON = SCRIPTS / "repo_domain_smes.json"
REPO_DOMAIN_SMES_MD = ROOT / "notes" / "REPO_DOMAIN_SMES.md"
VAULTS = ROOT / "notes" / "agent_vaults"
CURSOR_RULES = ROOT / ".cursor" / "rules"
WQ = ROOT / "notes" / "WORK_QUEUE.md"
CTX = SCRIPTS / "self_improve_context.md"
SPEC_DIR = ROOT / "notes" / "agent_builder_specs"

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,48}$")
# Intent: refuse *being* a paid/billing specialist — not docs that say "refuse billing".
_PAID_ID_RE = re.compile(
    r"(stripe|paddle|billing|paid_api|monetiz|credits_purchas)",
    re.I,
)
_PAID_ENABLE_RE = re.compile(
    r"\b(enable|integrate|wire|sell|charge|collect)\b.{0,40}\b"
    r"(stripe|paddle|billing|paid\s*api|credits)\b"
    r"|\b(stripe|paddle)\b.{0,40}\b(enable|checkout|subscription|payment)\b",
    re.I,
)
_SAFE_TIERS = frozenset({"green", "yellow", "red"})
_LEGACY_PEERS = frozenset(
    {"implement", "verify", "launch", "footprint", "reclaim", "safety"}
)

REQUIRED_FIELDS = (
    "id",
    "job_title",
    "strengths",
    "responsibilities",
    "niche_task",
    "reads",
    "legacy_peer",
    "safety_tier",
    "match",
    "template_prompt",
)


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_peer_tasks(path: Path | None = None) -> dict[str, Any]:
    p = path or PEER_TASKS
    return json.loads(p.read_text(encoding="utf-8"))


def load_spec_file(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("spec must be a JSON object")
    return raw


def flags_to_spec(args: argparse.Namespace) -> dict[str, Any]:
    strengths = _split_csv(getattr(args, "strengths", None))
    reads = _split_csv(getattr(args, "reads", None))
    match = _split_csv(getattr(args, "match", None))
    rid = str(getattr(args, "id", "") or "").strip()
    title = str(getattr(args, "title", "") or "").strip()
    if not strengths and rid:
        strengths = [rid, rid.replace("_", "-"), f"[{rid.replace('_', '-')}]"]
    if not match and strengths:
        match = list(strengths[:6])
    if not reads:
        reads = ["notes/AGENT_WORKING_MEMORY.md", "notes/WORK_QUEUE.md", "AGENTS.md"]
    prompt = str(getattr(args, "prompt", "") or "").strip()
    if not prompt and title:
        prompt = (
            f"You are {rid}. Job: {title}. Read AGENT_WORKING_MEMORY + WORK_QUEUE. "
            "Minimal diff; NO PAY (free desktop / local / CLEAN only). "
            "Safe deletes = scratch/temp only."
        )
    domain = getattr(args, "domain_sme", None)
    domain_obj = None
    if isinstance(domain, str) and domain.strip():
        domain_obj = {"id": domain.strip(), "title": title or rid}
    elif isinstance(domain, dict):
        domain_obj = domain
    return {
        "id": rid,
        "job_title": title,
        "strengths": strengths,
        "responsibilities": str(getattr(args, "responsibilities", "") or "").strip()
        or f"{title} — specialist provisioned by Agent Builder.",
        "niche_task": str(getattr(args, "niche_task", "") or "").strip()
        or f"**{title}** — execute matching queue items; NO PAY.",
        "reads": reads,
        "legacy_peer": str(getattr(args, "legacy_peer", "") or "implement").strip(),
        "safety_tier": str(getattr(args, "safety_tier", "") or "green").strip(),
        "prefer_remote": bool(getattr(args, "prefer_remote", True)),
        "match": match,
        "template_prompt": prompt,
        "always_apply_rule": str(getattr(args, "always_apply_rule", "") or "").strip(),
        "domain_sme": domain_obj,
        "subagent_type": str(getattr(args, "subagent_type", "") or "generalPurpose"),
        "model": str(getattr(args, "model", "") or "inherit"),
        "match_priority": int(getattr(args, "match_priority", 15) or 15),
        "create_vault": bool(getattr(args, "create_vault", True)),
        "create_cursor_rule": bool(
            getattr(args, "create_cursor_rule", False)
            or bool(getattr(args, "always_apply_rule", "") or "").strip()
        ),
    }


def normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce/fill defaults; return a validated-ready spec dict."""
    spec = dict(raw)
    rid = str(spec.get("id") or "").strip()
    title = str(spec.get("job_title") or spec.get("title") or "").strip()
    strengths = spec.get("strengths") or []
    if isinstance(strengths, str):
        strengths = _split_csv(strengths)
    strengths = [str(s).strip() for s in strengths if str(s).strip()]
    reads = spec.get("reads") or []
    if isinstance(reads, str):
        reads = _split_csv(reads)
    reads = [str(r).strip() for r in reads if str(r).strip()]
    match = spec.get("match") or spec.get("match_keywords") or []
    if isinstance(match, str):
        match = _split_csv(match)
    match = [str(m).strip() for m in match if str(m).strip()]
    if not match:
        match = list(strengths[:8])
    prompt = str(
        spec.get("template_prompt") or spec.get("prompt") or ""
    ).strip()
    domain = spec.get("domain_sme")
    if isinstance(domain, str) and domain.strip():
        domain = {
            "id": domain.strip(),
            "title": title or rid,
            "role_id": rid,
            "globs": list(spec.get("domain_globs") or []),
            "sot": list(reads[:4]),
            "keywords": list(match[:8]),
        }
    elif isinstance(domain, dict):
        domain = dict(domain)
        domain.setdefault("role_id", rid)
        domain.setdefault("title", title or rid)
        domain.setdefault("globs", [])
        domain.setdefault("sot", list(reads[:4]))
        domain.setdefault("keywords", list(match[:8]))
    else:
        domain = None
    create_rule = bool(spec.get("create_cursor_rule"))
    rule_blurb = str(spec.get("always_apply_rule") or "").strip()
    if rule_blurb:
        create_rule = True
    return {
        "id": rid,
        "job_title": title,
        "strengths": strengths,
        "responsibilities": str(spec.get("responsibilities") or "").strip(),
        "niche_task": str(spec.get("niche_task") or "").strip(),
        "reads": reads,
        "legacy_peer": str(spec.get("legacy_peer") or "implement").strip(),
        "safety_tier": str(spec.get("safety_tier") or "green").strip().lower(),
        "prefer_remote": bool(spec.get("prefer_remote", True)),
        "match": match,
        "template_prompt": prompt,
        "always_apply_rule": rule_blurb,
        "domain_sme": domain,
        "subagent_type": str(spec.get("subagent_type") or "generalPurpose").strip(),
        "model": str(spec.get("model") or "inherit").strip(),
        "match_priority": int(spec.get("match_priority") or 15),
        "create_vault": bool(spec.get("create_vault", True)),
        "create_cursor_rule": create_rule,
        "host": str(spec.get("host") or "").strip(),
    }


def validate_spec(
    raw: dict[str, Any],
    *,
    human_ack: bool = False,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    """Return list of validation issues (empty = ok)."""
    issues: list[str] = []
    try:
        spec = normalize_spec(raw)
    except (TypeError, ValueError) as exc:
        return [f"normalize failed: {exc}"]

    rid = spec["id"]
    if not rid:
        issues.append("missing id")
    elif not _ID_RE.match(rid):
        issues.append(f"id must match {_ID_RE.pattern}: {rid!r}")

    if not spec["job_title"]:
        issues.append("missing job_title")
    if not spec["strengths"]:
        issues.append("strengths[] required (non-empty)")
    if not spec["responsibilities"]:
        issues.append("responsibilities required")
    if not spec["niche_task"]:
        issues.append("niche_task required")
    if not spec["reads"]:
        issues.append("reads[] required (non-empty)")
    if not spec["match"]:
        issues.append("match keywords required")
    if not spec["template_prompt"]:
        issues.append("template_prompt required")
    if spec["legacy_peer"] not in _LEGACY_PEERS:
        issues.append(
            f"legacy_peer must be one of {sorted(_LEGACY_PEERS)}: {spec['legacy_peer']!r}"
        )
    if spec["safety_tier"] not in _SAFE_TIERS:
        issues.append(f"safety_tier must be green|yellow|red: {spec['safety_tier']!r}")

    identity_blob = " ".join(
        [rid, spec["job_title"], " ".join(spec["strengths"]), " ".join(spec["match"])]
    )
    body_blob = " ".join(
        [spec["responsibilities"], spec["niche_task"], spec["template_prompt"]]
    )
    paid_hit = _PAID_ID_RE.search(identity_blob) or _PAID_ENABLE_RE.search(body_blob)
    if paid_hit and not human_ack:
        issues.append(
            "NO-PAY: paid/billing/Stripe-like specialist refused without --human-ack"
        )

    if cfg is not None:
        templates = cfg.get("task_templates") or {}
        if rid in templates and not isinstance(templates.get(rid), dict):
            issues.append(f"existing task_templates.{rid} is not an object")

    return issues


def role_entry(spec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": spec["id"],
        "job_title": spec["job_title"],
        "legacy_peer": spec["legacy_peer"],
        "subagent_type": spec["subagent_type"],
        "model": spec["model"],
        "prefer_remote": bool(spec["prefer_remote"]),
        "strengths": list(spec["strengths"]),
        "responsibilities": spec["responsibilities"],
        "niche_task": spec["niche_task"],
        "reads": list(spec["reads"]),
    }
    if spec.get("host"):
        out["host"] = spec["host"]
    return out


def template_entry(spec: dict[str, Any]) -> dict[str, Any]:
    scope = list(dict.fromkeys([*spec["reads"], "scripts/peer_tasks.json"]))
    return {
        "peer": spec["legacy_peer"],
        "safety_tier": spec["safety_tier"],
        "scope": scope,
        "prompt": spec["template_prompt"],
    }


def match_rule_entry(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "template": spec["id"],
        "any": list(spec["match"]),
        "priority": int(spec["match_priority"]),
    }


def upsert_role(cfg: dict[str, Any], role: dict[str, Any]) -> str:
    """Insert or replace role by id. Never deletes other roles. Returns action."""
    roles = list(cfg.get("agent_roles") or [])
    rid = role["id"]
    for i, raw in enumerate(roles):
        if isinstance(raw, dict) and str(raw.get("id") or "") == rid:
            roles[i] = role
            cfg["agent_roles"] = roles
            return "updated"
    roles.append(role)
    cfg["agent_roles"] = roles
    return "added"


def upsert_template(cfg: dict[str, Any], tid: str, tmpl: dict[str, Any]) -> str:
    templates = dict(cfg.get("task_templates") or {})
    action = "updated" if tid in templates else "added"
    templates[tid] = tmpl
    cfg["task_templates"] = templates
    return action


def upsert_match_rule(cfg: dict[str, Any], rule: dict[str, Any]) -> str:
    rules = list(cfg.get("match_rules") or [])
    tid = str(rule.get("template") or "")
    for i, raw in enumerate(rules):
        if isinstance(raw, dict) and str(raw.get("template") or "") == tid:
            rules[i] = rule
            cfg["match_rules"] = rules
            return "updated"
    # Prefer inserting near front of mid-priority band (after priority 0–5 locks)
    insert_at = len(rules)
    for i, raw in enumerate(rules):
        if not isinstance(raw, dict):
            continue
        if int(raw.get("priority", 100)) > int(rule.get("priority", 15)):
            insert_at = i
            break
    rules.insert(insert_at, rule)
    cfg["match_rules"] = rules
    return "added"


def ensure_role_importance(cfg: dict[str, Any], rid: str) -> None:
    order = list(cfg.get("role_importance_order") or [])
    if rid not in order:
        # Keep progress_monitor last if present
        if order and order[-1] == "progress_monitor":
            order.insert(-1, rid)
        else:
            order.append(rid)
        cfg["role_importance_order"] = order


def provision_plan(spec: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a dry-run plan describing patches (does not mutate cfg)."""
    s = normalize_spec(spec)
    role = role_entry(s)
    tmpl = template_entry(s)
    rule = match_rule_entry(s)
    existing_ids = {
        str(r.get("id") or "")
        for r in (cfg.get("agent_roles") or [])
        if isinstance(r, dict)
    }
    return {
        "needle": NEEDLE,
        "id": s["id"],
        "role_action": "updated" if s["id"] in existing_ids else "added",
        "template_action": "updated"
        if s["id"] in (cfg.get("task_templates") or {})
        else "added",
        "match_action": "updated"
        if any(
            isinstance(r, dict) and r.get("template") == s["id"]
            for r in (cfg.get("match_rules") or [])
        )
        else "added",
        "role": role,
        "template": tmpl,
        "match_rule": rule,
        "create_vault": bool(s["create_vault"]),
        "vault_path": str(VAULTS / s["id"] / "README.md"),
        "create_cursor_rule": bool(s["create_cursor_rule"]),
        "cursor_rule_path": str(CURSOR_RULES / f"{s['id']}.mdc"),
        "domain_sme": s["domain_sme"],
        "automation_md_row": s["id"],
        "other_roles_untouched": True,
    }


def apply_provision(spec: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Mutate cfg in place; return summary of actions."""
    s = normalize_spec(spec)
    actions = {
        "role": upsert_role(cfg, role_entry(s)),
        "template": upsert_template(cfg, s["id"], template_entry(s)),
        "match_rule": upsert_match_rule(cfg, match_rule_entry(s)),
    }
    ensure_role_importance(cfg, s["id"])
    return {"id": s["id"], "actions": actions, "spec": s}


def write_vault_stub(spec: dict[str, Any]) -> Path:
    s = normalize_spec(spec)
    d = VAULTS / s["id"]
    d.mkdir(parents=True, exist_ok=True)
    path = d / "README.md"
    if path.is_file():
        return path
    body = (
        f"# Vault — {s['job_title']} (`{s['id']}`)\n\n"
        f"_Provisioned by Agent Builder · {NEEDLE}_\n\n"
        f"**Responsibilities:** {s['responsibilities']}\n\n"
        f"**Niche:** {s['niche_task']}\n\n"
        "## Reads\n\n"
        + "\n".join(f"- `{r}`" for r in s["reads"])
        + "\n\n## Notes\n\n_Scratch for this niche only. Do not promote into Always-read._\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def write_cursor_rule(spec: dict[str, Any]) -> Path | None:
    s = normalize_spec(spec)
    if not s["create_cursor_rule"]:
        return None
    CURSOR_RULES.mkdir(parents=True, exist_ok=True)
    path = CURSOR_RULES / f"{s['id']}.mdc"
    blurb = s["always_apply_rule"] or (
        f"When working as `{s['id']}` / {s['job_title']}: follow niche reads; "
        "NO PAY; minimal diff; do not steal other roles' scopes."
    )
    always = "true" if s["always_apply_rule"] else "false"
    body = (
        f"---\n"
        f"description: {s['job_title']} — Agent Builder niche\n"
        f"alwaysApply: {always}\n"
        f"---\n\n"
        f"# {s['job_title']}\n\n"
        f"{blurb}\n\n"
        f"Role id: `{s['id']}` · Needle `{NEEDLE}`\n"
    )
    _atomic_write_text(path, body)
    return path


def patch_automation_md(spec: dict[str, Any]) -> bool:
    """Insert template table row if missing. Returns True if wrote."""
    s = normalize_spec(spec)
    if not AUTOMATION_MD.is_file():
        return False
    text = AUTOMATION_MD.read_text(encoding="utf-8")
    if f"| {s['id']} |" in text:
        return False
    # Insert after top10_next row if present, else before first blank after table header block
    row = (
        f"| {s['id']} | {s['legacy_peer']} | {s['job_title']}, "
        f"{', '.join(s['match'][:3])} |\n"
    )
    anchor = "| top10_next |"
    if anchor in text:
        idx = text.index(anchor)
        # end of that line
        nl = text.index("\n", idx) + 1
        text = text[:nl] + row + text[nl:]
    else:
        marker = "| Key | Peer | When matched |"
        if marker not in text:
            return False
        # find third newline after marker (header + sep + first?) — append after sep line
        i = text.index(marker)
        nl1 = text.index("\n", i) + 1
        nl2 = text.index("\n", nl1) + 1
        text = text[:nl2] + row + text[nl2:]
    _atomic_write_text(AUTOMATION_MD, text)
    return True


def patch_domain_sme(spec: dict[str, Any]) -> bool:
    s = normalize_spec(spec)
    domain = s.get("domain_sme")
    if not domain or not isinstance(domain, dict):
        return False
    did = str(domain.get("id") or "").strip()
    if not did:
        return False
    data = {"version": 1, "needle": "OVERSEER_FACT_LIBRARIAN_2026_09_07", "domains": []}
    if DOMAIN_SMES_JSON.is_file():
        try:
            data = json.loads(DOMAIN_SMES_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    domains = list(data.get("domains") or [])
    entry = {
        "id": did,
        "title": str(domain.get("title") or s["job_title"]),
        "role_id": str(domain.get("role_id") or s["id"]),
        "globs": list(domain.get("globs") or []),
        "sot": list(domain.get("sot") or s["reads"][:4]),
        "keywords": list(domain.get("keywords") or s["match"][:8]),
    }
    replaced = False
    for i, raw in enumerate(domains):
        if isinstance(raw, dict) and str(raw.get("id") or "") == did:
            domains[i] = entry
            replaced = True
            break
    if not replaced:
        domains.append(entry)
    data["domains"] = domains
    _atomic_write_json(DOMAIN_SMES_JSON, data)
    # Light MD table row
    if REPO_DOMAIN_SMES_MD.is_file():
        md = REPO_DOMAIN_SMES_MD.read_text(encoding="utf-8")
        if f"| `{did}` |" not in md:
            line = (
                f"| `{did}` | `{entry['role_id']}` | "
                f"{entry['title'][:60]} |\n"
            )
            # after Domains table header separator
            if "| Domain id | Role | Owns" in md:
                # find end of table header row pair
                pos = md.index("| Domain id | Role | Owns")
                nl = md.index("\n", pos) + 1
                if nl < len(md) and md[nl:].startswith("|"):
                    nl = md.index("\n", nl) + 1
                md = md[:nl] + line + md[nl:]
                _atomic_write_text(REPO_DOMAIN_SMES_MD, md)
    try:
        import peer_fact_librarian as pfl

        pfl.write_domain_owners_md()
    except Exception:  # noqa: BLE001
        pass
    return True


def enqueue_smoke(spec: dict[str, Any]) -> bool:
    """Append identical Active smoke lines to WQ ↔ self_improve_context."""
    s = normalize_spec(spec)
    tag = s["id"].replace("_", "-")
    line = (
        f"- [ ] **[{tag}] Smoke assign `{s['id']}`** — prove agent-who + orchestrate "
        f"route to role `{s['id']}`; `./scripts/peer agent-who \"[{tag}] smoke\"`; "
        f"NO PAY. Needle `{NEEDLE}`"
    )
    wrote = False
    for path in (WQ, CTX):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if f"**[{tag}] Smoke assign" in text or f"`{s['id']}`** — prove agent-who" in text:
            continue
        if "## Active" in text:
            idx = text.index("## Active")
            nl = text.index("\n", idx) + 1
            text = text[:nl] + line + "\n" + text[nl:]
            _atomic_write_text(path, text)
            wrote = True
    return wrote


def run_self_check() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "peer_orchestrate.py"), "--self-check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out[-4000:]


def who_for_task(
    task: str,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mechanical task → template + role (match_template + pick_role)."""
    import peer_roles as pr
    import template_match as tm

    if cfg is None:
        cfg = load_peer_tasks()
    templates = cfg.get("task_templates") or {}
    rules = list(cfg.get("match_rules") or [])
    tid, tmpl = tm.match_template(task, templates, rules)
    peer_key = str(tmpl.get("peer") or "")
    roles = pr.load_roles(cfg)
    assignment = pr.pick_role(task, roles, template_peer=peer_key)
    scores = sorted(
        (
            {
                "id": r.id,
                "score": pr.score_item_for_role(task, r, template_peer=peer_key),
                "job_title": r.job_title,
            }
            for r in roles
        ),
        key=lambda x: (-x["score"], x["id"]),
    )[:8]
    return {
        "needle": NEEDLE,
        "task": task,
        "template": tid,
        "template_peer": peer_key,
        "safety_tier": tmpl.get("safety_tier"),
        "role_id": assignment.role.id,
        "job_title": assignment.role.job_title,
        "score": assignment.score,
        "legacy_peer": assignment.role.legacy_peer,
        "prefer_remote": assignment.role.prefer_remote,
        "top_role_scores": scores,
    }


def list_roles(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if cfg is None:
        cfg = load_peer_tasks()
    templates = cfg.get("task_templates") or {}
    rules = cfg.get("match_rules") or []
    by_tmpl = {
        str(r.get("template")): r
        for r in rules
        if isinstance(r, dict) and r.get("template")
    }
    out: list[dict[str, Any]] = []
    for raw in cfg.get("agent_roles") or []:
        if not isinstance(raw, dict):
            continue
        rid = str(raw.get("id") or "")
        out.append(
            {
                "id": rid,
                "job_title": raw.get("job_title"),
                "legacy_peer": raw.get("legacy_peer"),
                "has_template": rid in templates,
                "has_match_rule": rid in by_tmpl,
                "strengths_n": len(raw.get("strengths") or []),
                "prefer_remote": bool(raw.get("prefer_remote")),
            }
        )
    return out


def validate_role_id(rid: str, cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg = load_peer_tasks()
    issues: list[str] = []
    role = None
    for raw in cfg.get("agent_roles") or []:
        if isinstance(raw, dict) and str(raw.get("id") or "") == rid:
            role = raw
            break
    if role is None:
        return [f"role {rid!r} not in agent_roles"]
    templates = cfg.get("task_templates") or {}
    if rid not in templates:
        issues.append(f"missing task_templates.{rid}")
    else:
        tmpl = templates[rid]
        if not isinstance(tmpl, dict):
            issues.append(f"task_templates.{rid} not object")
        else:
            if not tmpl.get("prompt"):
                issues.append(f"task_templates.{rid} missing prompt")
            tier = str(tmpl.get("safety_tier") or "")
            if tier and tier not in _SAFE_TIERS:
                issues.append(f"bad safety_tier on template: {tier}")
    rules = [
        r
        for r in (cfg.get("match_rules") or [])
        if isinstance(r, dict) and r.get("template") == rid
    ]
    if not rules:
        issues.append(f"missing match_rules for template={rid}")
    strengths = role.get("strengths") or []
    if not strengths:
        issues.append("role has empty strengths")
    return issues


def build(
    spec_raw: dict[str, Any],
    *,
    write: bool,
    human_ack: bool = False,
    enqueue: bool = False,
    skip_self_check: bool = False,
    cfg_path: Path | None = None,
) -> dict[str, Any]:
    path = cfg_path or PEER_TASKS
    cfg = load_peer_tasks(path)
    issues = validate_spec(spec_raw, human_ack=human_ack, cfg=cfg)
    if issues:
        return {"ok": False, "issues": issues, "needle": NEEDLE}

    plan = provision_plan(spec_raw, cfg)
    if not write:
        return {"ok": True, "dry_run": True, "plan": plan, "needle": NEEDLE}

    before_ids = {
        str(r.get("id") or "")
        for r in (cfg.get("agent_roles") or [])
        if isinstance(r, dict)
    }
    summary = apply_provision(spec_raw, cfg)
    after_ids = {
        str(r.get("id") or "")
        for r in (cfg.get("agent_roles") or [])
        if isinstance(r, dict)
    }
    # Safety: never lose roles
    lost = before_ids - after_ids
    if lost:
        return {
            "ok": False,
            "issues": [f"abort: would lose roles {sorted(lost)}"],
            "needle": NEEDLE,
        }

    # Backup then atomic write
    bak = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
    try:
        shutil.copy2(path, bak)
    except OSError:
        bak = None
    _atomic_write_json(path, cfg)

    s = summary["spec"]
    extras: dict[str, Any] = {}
    if s["create_vault"]:
        extras["vault"] = str(write_vault_stub(s).relative_to(ROOT))
    rule_path = write_cursor_rule(s)
    if rule_path:
        extras["cursor_rule"] = str(rule_path.relative_to(ROOT))
    extras["automation_md"] = patch_automation_md(s)
    extras["domain_sme"] = patch_domain_sme(s)
    if enqueue:
        extras["enqueue_smoke"] = enqueue_smoke(s)

    self_check: dict[str, Any] | None = None
    if not skip_self_check:
        rc, out = run_self_check()
        self_check = {"rc": rc, "tail": out[-1500:]}

    # Prove who
    sample = s["match"][0] if s["match"] else s["id"]
    who = who_for_task(f"[{sample}] smoke assign {s['id']}", cfg=cfg)

    return {
        "ok": True,
        "dry_run": False,
        "needle": NEEDLE,
        "summary": summary["actions"],
        "id": s["id"],
        "backup": str(bak) if bak else None,
        "extras": extras,
        "self_check": self_check,
        "who_sample": who,
        "plan": plan,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Agent Builder — provision specialist roles (NO PAY)"
    )
    parser.add_argument("--spec", type=Path, help="Path to agent spec JSON")
    parser.add_argument("--id", default="", help="Role id (snake_case)")
    parser.add_argument("--title", default="", help="Job title")
    parser.add_argument("--strengths", default="", help="Comma-separated strengths")
    parser.add_argument("--reads", default="", help="Comma-separated read paths")
    parser.add_argument("--match", default="", help="Comma-separated match keywords")
    parser.add_argument("--prompt", default="", help="Template prompt")
    parser.add_argument("--responsibilities", default="")
    parser.add_argument("--niche-task", dest="niche_task", default="")
    parser.add_argument("--legacy-peer", dest="legacy_peer", default="implement")
    parser.add_argument("--safety-tier", dest="safety_tier", default="green")
    parser.add_argument("--prefer-remote", dest="prefer_remote", action="store_true", default=True)
    parser.add_argument("--no-prefer-remote", dest="prefer_remote", action="store_false")
    parser.add_argument("--always-apply-rule", dest="always_apply_rule", default="")
    parser.add_argument("--domain-sme", dest="domain_sme", default="")
    parser.add_argument("--subagent-type", dest="subagent_type", default="generalPurpose")
    parser.add_argument("--model", default="inherit")
    parser.add_argument("--match-priority", dest="match_priority", type=int, default=15)
    parser.add_argument("--create-vault", dest="create_vault", action="store_true", default=True)
    parser.add_argument("--no-vault", dest="create_vault", action="store_false")
    parser.add_argument("--create-cursor-rule", dest="create_cursor_rule", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--validate", metavar="ID", default="")
    parser.add_argument("--who", metavar="TASK", default="", help="Print role/template for task")
    parser.add_argument("--human-ack", action="store_true", help="Allow paid/billing specs")
    parser.add_argument("--enqueue-smoke", action="store_true")
    parser.add_argument("--skip-self-check", action="store_true")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    if args.list:
        rows = list_roles()
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                flags = []
                if r["has_template"]:
                    flags.append("tmpl")
                if r["has_match_rule"]:
                    flags.append("match")
                print(
                    f"{r['id']:28} {r['job_title'] or '':36} "
                    f"peer={r['legacy_peer'] or '-':10} [{','.join(flags)}]"
                )
            print(f"# {len(rows)} roles · {NEEDLE}")
        return 0

    if args.validate:
        issues = validate_role_id(args.validate)
        if args.json:
            print(json.dumps({"id": args.validate, "ok": not issues, "issues": issues}))
        else:
            if issues:
                for i in issues:
                    print(f"ISSUE: {i}")
                return 1
            print(f"validate ok: {args.validate}")
        return 1 if issues else 0

    if args.who:
        report = who_for_task(args.who)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"task:     {report['task']}")
            print(f"template: {report['template']} (peer={report['template_peer']})")
            print(
                f"role:     {report['role_id']} — {report['job_title']} "
                f"(score={report['score']:.2f})"
            )
            print("top scores:")
            for row in report["top_role_scores"][:5]:
                print(f"  {row['score']:5.2f}  {row['id']}  ({row['job_title']})")
        return 0

    spec: dict[str, Any] | None = None
    if args.spec:
        spec = load_spec_file(args.spec)
    elif args.id and args.title:
        spec = flags_to_spec(args)
    else:
        parser.error("need --spec PATH or --id + --title (or --list / --validate / --who)")

    write = bool(args.write) and not args.dry_run
    if not write and not args.dry_run and not args.write:
        # default dry-run when neither flag
        write = False
        args.dry_run = True

    result = build(
        spec,
        write=write,
        human_ack=args.human_ack,
        enqueue=args.enqueue_smoke,
        skip_self_check=args.skip_self_check,
    )
    if args.json or True:
        # Always print JSON for machine use; human gets readable too when not --json only
        print(json.dumps(result, indent=2, default=str))
    if not result.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
