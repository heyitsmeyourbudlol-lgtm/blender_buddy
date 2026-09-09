#!/usr/bin/env python3
"""Daily flaw-detection cross-review — 8 niches scan each other's work.

Each day at ``flaw_scan_daily_time`` (local), every agent becomes
**Flaw Detection Scanner + {job title}** and reviews the other 7 niches.
Each subject receives 7 persona-specific reviews, then self-triages upgrades
vs downgrades.

State: ``~/.config/automation-hub/peer-flaw-scan-state.json`` (hub SoT;
peer-* worktrees resolve here — never fork empty twin rounds)
Round: ``~/.config/automation-hub/peer-flaw-scan-round.json``
Reviews: ``~/.config/automation-hub/flaw-scan-reviews/``

Usage:
  python3 scripts/peer_flaw_scan.py --status
  python3 scripts/peer_flaw_scan.py --preview
  python3 scripts/peer_flaw_scan.py --start        # force today's round
  python3 scripts/peer_flaw_scan.py --record-review REVIEWER TARGET "text"
  python3 scripts/peer_flaw_scan.py --compile
  ./scripts/peer flaw-scan
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_roles as roles  # noqa: E402
import project_automation as auto  # noqa: E402

PHASE_SCAN = "scanning"
PHASE_TRIAGE = "triage"
PHASE_COMPLETE = "complete"

# Product contract: 8 scanners × 7 targets = 56 reviews → 8 self-triages.
# Needle: OVERSEER_FLAW_SCAN_POOL_CAP_8_2026_09_07 — staff_all once inflated to 46→2070 pairs.
FLAW_SCAN_POOL_SIZE = 8
FLAW_SCAN_PAIR_TOTAL = FLAW_SCAN_POOL_SIZE * (FLAW_SCAN_POOL_SIZE - 1)

# Hub SoT — scanners write reviews here (prompt hardcodes this path).
HUB_CONFIG_DIR = Path.home() / ".config" / "automation-hub"
HUB_REVIEWS_DIR = HUB_CONFIG_DIR / "flaw-scan-reviews"


def _resolve_flaw_scan_dir() -> Path:
    """Flaw-scan is hub-wide; peer-* worktrees must not fork empty twin rounds."""
    ns = str(auto.CFG.get("config_namespace") or "")
    if re.match(r"^peer-(\d+|coding)$", ns) and HUB_CONFIG_DIR.is_dir():
        return HUB_CONFIG_DIR
    return auto.CONFIG_DIR


def refresh_paths() -> None:
    """Rebind STATE/ROUND/REVIEWS paths (tests may patch; peer-* → hub SoT)."""
    global STATE_PATH, ROUND_PATH, REVIEWS_DIR
    base = _resolve_flaw_scan_dir()
    STATE_PATH = base / "peer-flaw-scan-state.json"
    ROUND_PATH = base / "peer-flaw-scan-round.json"
    REVIEWS_DIR = base / "flaw-scan-reviews"


STATE_PATH: Path
ROUND_PATH: Path
REVIEWS_DIR: Path
refresh_paths()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _plain(text: str, *, limit: int = 280) -> str:
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", str(text or ""))
    s = re.sub(r"`([^`]+)`", r"\1", s).strip()
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class FlawScanConfig:
    enabled: bool
    daily_time: str  # HH:MM local
    min_hour: int
    min_minute: int


def load_config() -> FlawScanConfig:
    raw = auto.CFG.get("flaw_scan") or {}
    if not isinstance(raw, dict):
        raw = {}
    enabled = bool(raw.get("enabled", auto.CFG.get("flaw_scan_enabled", True)))
    daily = str(raw.get("daily_time") or auto.CFG.get("flaw_scan_daily_time") or "09:00").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", daily)
    if not m:
        daily = "09:00"
        m = re.match(r"^(\d{1,2}):(\d{2})$", daily)
    assert m is not None
    hour, minute = int(m.group(1)), int(m.group(2))
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return FlawScanConfig(
        enabled=enabled,
        daily_time=f"{hour:02d}:{minute:02d}",
        min_hour=hour,
        min_minute=minute,
    )


def scanner_title(role: roles.AgentRole) -> str:
    return f"Flaw Detection Scanner + {role.job_title}"


def _target_work_for_role(role_id: str) -> dict[str, Any]:
    try:
        import peer_agent_board as board

        b = board.build_board(refresh_roster=False)
        for agent in b.get("agents") or []:
            if isinstance(agent, dict) and agent.get("role_id") == role_id:
                return {
                    "item": agent.get("item") or "",
                    "item_plain": agent.get("item_plain") or _plain(str(agent.get("item") or "")),
                    "responsibilities": agent.get("responsibilities") or "",
                    "worktree": agent.get("worktree"),
                }
    except Exception:  # noqa: BLE001
        pass
    for role in roles.load_roles():
        if role.id == role_id:
            return {
                "item": role.niche_task or role.responsibilities,
                "item_plain": _plain(role.niche_task or role.responsibilities),
                "responsibilities": role.responsibilities,
                "worktree": None,
            }
    return {"item": "", "item_plain": "(no assignment)", "responsibilities": "", "worktree": None}


def _scan_pool(
    pool: list[roles.AgentRole] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[roles.AgentRole]:
    """Canonical flaw-scan niches — hard-capped at FLAW_SCAN_POOL_SIZE."""
    if pool is None:
        pool = roles.load_roles(cfg)
    return list(pool)[:FLAW_SCAN_POOL_SIZE]


def build_review_pairs(pool: list[roles.AgentRole] | None = None) -> list[dict[str, Any]]:
    """56 directed pairs: each reviewer scans each other niche (not self)."""
    pool = _scan_pool(pool)
    pairs: list[dict[str, Any]] = []
    for reviewer in pool:
        for target in pool:
            if reviewer.id == target.id:
                continue
            work = _target_work_for_role(target.id)
            pairs.append(
                {
                    "reviewer_role_id": reviewer.id,
                    "reviewer_title": scanner_title(reviewer),
                    "reviewer_model": reviewer.model,
                    "reviewer_subagent": reviewer.subagent_type,
                    "target_role_id": target.id,
                    "target_job_title": target.job_title,
                    "target_work": work,
                    "status": "pending",
                    "review": None,
                    "recorded_at": None,
                }
            )
    return pairs


def normalize_round(rnd: dict[str, Any] | None = None, *, save: bool = True) -> dict[str, Any] | None:
    """Collapse catalog-bloated rounds to 8×7 pairs; preserve done reviews + triage."""
    if rnd is None:
        rnd = load_round()
    if not rnd or not isinstance(rnd, dict):
        return None
    pool = _scan_pool()
    pool_ids = {r.id for r in pool}
    done_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for pair in rnd.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        reviewer = str(pair.get("reviewer_role_id") or "")
        target = str(pair.get("target_role_id") or "")
        if reviewer not in pool_ids or target not in pool_ids or reviewer == target:
            continue
        if pair.get("status") != "done" or not str(pair.get("review") or "").strip():
            continue
        key = (reviewer, target)
        if key not in done_by_key:
            done_by_key[key] = pair
    old_subjects = {
        str(s.get("role_id") or ""): s
        for s in (rnd.get("subjects") or [])
        if isinstance(s, dict) and s.get("role_id")
    }
    pairs = build_review_pairs(pool)
    for pair in pairs:
        key = (str(pair["reviewer_role_id"]), str(pair["target_role_id"]))
        old = done_by_key.get(key)
        if not old:
            continue
        pair["status"] = "done"
        pair["review"] = old.get("review")
        pair["recorded_at"] = old.get("recorded_at")
    subjects: list[dict[str, Any]] = []
    for role in pool:
        old = old_subjects.get(role.id) or {}
        received: list[dict[str, Any]] = []
        for pair in pairs:
            if pair.get("target_role_id") != role.id or pair.get("status") != "done":
                continue
            body = str(pair.get("review") or "").strip()
            if not body:
                continue
            received.append(
                {
                    "reviewer_role_id": pair.get("reviewer_role_id"),
                    "reviewer_title": pair.get("reviewer_title") or pair.get("reviewer_role_id"),
                    "body": body,
                    "recorded_at": pair.get("recorded_at"),
                }
            )
        if not received and isinstance(old.get("reviews_received"), list):
            received = [
                r
                for r in old["reviews_received"]
                if isinstance(r, dict) and str(r.get("reviewer_role_id") or "") in pool_ids
            ]
        subjects.append(
            {
                "role_id": role.id,
                "job_title": role.job_title,
                "reviews_received": received,
                "triage": old.get("triage"),
                "upgrades_accepted": list(old.get("upgrades_accepted") or []),
                "downgrades_rejected": list(old.get("downgrades_rejected") or []),
            }
        )
    before_pairs = len(rnd.get("pairs") or [])
    before_subj = len(rnd.get("subjects") or [])
    rnd["pairs"] = pairs
    rnd["subjects"] = subjects
    changed = before_pairs != len(pairs) or before_subj != len(subjects)
    if changed:
        rnd["normalized_at"] = _now_iso()
        rnd["normalize_note"] = (
            f"compacted {before_pairs}→{len(pairs)} pairs "
            f"(hub {FLAW_SCAN_POOL_SIZE} niches; OVERSEER_FLAW_SCAN_POOL_CAP_8_2026_09_07)"
        )
    if save and changed:
        save_round(rnd)
        state = load_state()
        state["heal_note"] = rnd.get("normalize_note")
        save_state(state)
    return rnd


def load_state() -> dict[str, Any]:
    return _safe_read_json(STATE_PATH) or {}


def load_round() -> dict[str, Any] | None:
    return _safe_read_json(ROUND_PATH)


def save_state(state: dict[str, Any]) -> None:
    _write_json(STATE_PATH, state)


def save_round(round_data: dict[str, Any]) -> None:
    _write_json(ROUND_PATH, round_data)


def start_round(*, force: bool = False) -> dict[str, Any]:
    """Begin today's cross-review round."""
    today = _today()
    state = load_state()
    if not force and state.get("last_completed_date") == today:
        existing = load_round()
        if existing and existing.get("round_date") == today:
            return existing
    pool = _scan_pool()
    pairs = build_review_pairs(pool)
    subjects = [
        {
            "role_id": r.id,
            "job_title": r.job_title,
            "reviews_received": [],
            "triage": None,
            "upgrades_accepted": [],
            "downgrades_rejected": [],
        }
        for r in pool
    ]
    round_data: dict[str, Any] = {
        "version": 1,
        "round_id": today,
        "round_date": today,
        "started_at": _now_iso(),
        "phase": PHASE_SCAN,
        "config": {"daily_time": load_config().daily_time},
        "pairs": pairs,
        "subjects": subjects,
        "completed_at": None,
    }
    save_round(round_data)
    state["current_round_date"] = today
    state["last_started_at"] = _now_iso()
    save_state(state)
    return round_data


def is_past_daily_time(cfg: FlawScanConfig | None = None) -> bool:
    cfg = cfg or load_config()
    now = datetime.now()
    if now.hour > cfg.min_hour:
        return True
    if now.hour == cfg.min_hour and now.minute >= cfg.min_minute:
        return True
    return False


def should_dispatch_flaw_scan() -> bool:
    """True when peer loop should send flaw-scan orchestration instead of normal plan."""
    cfg = load_config()
    if not cfg.enabled:
        return False
    today = _today()
    state = load_state()
    rnd = load_round()

    # Heal staff_all-bloated rounds in place so 56 done hub-8 reviews can advance.
    if rnd and rnd.get("round_date") == today:
        if len(rnd.get("pairs") or []) != FLAW_SCAN_PAIR_TOTAL or len(rnd.get("subjects") or []) != FLAW_SCAN_POOL_SIZE:
            normalize_round(rnd, save=True)
            _maybe_advance_phase(rnd)
            rnd = load_round() or rnd

    if rnd and rnd.get("round_date") == today and rnd.get("phase") in (PHASE_SCAN, PHASE_TRIAGE):
        return True

    if state.get("last_completed_date") == today:
        return False

    if not is_past_daily_time(cfg):
        return False

    if rnd is None or rnd.get("round_date") != today:
        start_round()
        return True

    return rnd.get("phase") in (PHASE_SCAN, PHASE_TRIAGE)


def record_review(reviewer_role_id: str, target_role_id: str, body: str) -> bool:
    rnd = load_round()
    if not rnd:
        return False
    body = str(body or "").strip()
    if not body:
        return False
    updated = False
    for pair in rnd.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        if pair.get("reviewer_role_id") == reviewer_role_id and pair.get("target_role_id") == target_role_id:
            pair["review"] = body
            pair["status"] = "done"
            pair["recorded_at"] = _now_iso()
            updated = True
            break
    if not updated:
        return False
    _attach_review_to_subject(rnd, target_role_id, reviewer_role_id, body)
    save_round(rnd)
    _maybe_advance_phase(rnd)
    return True


def _attach_review_to_subject(
    rnd: dict[str, Any],
    target_role_id: str,
    reviewer_role_id: str,
    body: str,
) -> None:
    reviewer_title = reviewer_role_id
    for pair in rnd.get("pairs") or []:
        if (
            isinstance(pair, dict)
            and pair.get("target_role_id") == target_role_id
            and pair.get("reviewer_role_id") == reviewer_role_id
        ):
            reviewer_title = pair.get("reviewer_title") or reviewer_role_id
            break

    for subj in rnd.get("subjects") or []:
        if subj.get("role_id") != target_role_id:
            continue
        received = list(subj.get("reviews_received") or [])
        received = [r for r in received if r.get("reviewer_role_id") != reviewer_role_id]
        received.append(
            {
                "reviewer_role_id": reviewer_role_id,
                "reviewer_title": reviewer_title,
                "body": body,
                "recorded_at": _now_iso(),
            }
        )
        subj["reviews_received"] = received
        return


def _scan_complete(rnd: dict[str, Any]) -> bool:
    """True when every canonical 8×7 pair is done (ignore bloated catalog pairs)."""
    pool_ids = {r.id for r in _scan_pool()}
    needed = {(a, b) for a in pool_ids for b in pool_ids if a != b}
    if len(needed) != FLAW_SCAN_PAIR_TOTAL:
        return False
    done: set[tuple[str, str]] = set()
    for pair in rnd.get("pairs") or []:
        if not isinstance(pair, dict) or pair.get("status") != "done":
            continue
        if not str(pair.get("review") or "").strip():
            continue
        reviewer = str(pair.get("reviewer_role_id") or "")
        target = str(pair.get("target_role_id") or "")
        if reviewer in pool_ids and target in pool_ids and reviewer != target:
            done.add((reviewer, target))
    return needed <= done


def _triage_complete(rnd: dict[str, Any]) -> bool:
    pool_ids = {r.id for r in _scan_pool()}
    subjects = [
        s
        for s in (rnd.get("subjects") or [])
        if isinstance(s, dict) and str(s.get("role_id") or "") in pool_ids
    ]
    if len(subjects) < FLAW_SCAN_POOL_SIZE:
        return False
    return all(isinstance(s, dict) and s.get("triage") for s in subjects)


def _maybe_advance_phase(rnd: dict[str, Any]) -> None:
    normalize_round(rnd, save=False)
    phase = rnd.get("phase")
    if phase == PHASE_SCAN and _scan_complete(rnd):
        rnd["phase"] = PHASE_TRIAGE
        rnd["scan_completed_at"] = _now_iso()
        save_round(rnd)
    elif phase == PHASE_TRIAGE and _triage_complete(rnd):
        rnd["phase"] = PHASE_COMPLETE
        rnd["completed_at"] = _now_iso()
        save_round(rnd)
        state = load_state()
        state["last_completed_date"] = rnd.get("round_date") or _today()
        state["last_completed_at"] = _now_iso()
        save_state(state)
        try:
            import peer_debrief as debrief

            debrief.capture_flaw_round_debrief()
            debrief.ensure_sop_index()
        except Exception:  # noqa: BLE001
            pass
    elif len(rnd.get("pairs") or []) != FLAW_SCAN_PAIR_TOTAL or len(rnd.get("subjects") or []) != FLAW_SCAN_POOL_SIZE:
        # Persist heal even when phase unchanged (bloated round stuck in scanning).
        save_round(rnd)


def record_triage(
    role_id: str,
    *,
    summary: str,
    upgrades: list[str] | None = None,
    downgrades: list[str] | None = None,
) -> bool:
    rnd = load_round()
    if not rnd:
        return False
    for subj in rnd.get("subjects") or []:
        if subj.get("role_id") != role_id:
            continue
        subj["triage"] = {
            "summary": summary.strip(),
            "recorded_at": _now_iso(),
        }
        subj["upgrades_accepted"] = list(upgrades or [])
        subj["downgrades_rejected"] = list(downgrades or [])
        save_round(rnd)
        _maybe_advance_phase(rnd)
        return True
    return False


def _review_md_dirs() -> list[Path]:
    """Namespace reviews dir + hub SoT (prompt tells scanners to write under automation-hub)."""
    dirs: list[Path] = []
    for path in (REVIEWS_DIR, HUB_REVIEWS_DIR):
        if path.is_dir() and path not in dirs:
            dirs.append(path)
    return dirs


def compile_from_review_files() -> int:
    """Ingest ``flaw-scan-reviews/{reviewer}__{target}.md`` files into round JSON."""
    rnd = load_round()
    if not rnd:
        return 0
    normalize_round(rnd, save=True)
    count = 0
    seen: set[tuple[str, str]] = set()
    for reviews_dir in _review_md_dirs():
        for path in sorted(reviews_dir.glob("*__*.md")):
            parts = path.stem.split("__", 1)
            if len(parts) != 2:
                continue
            reviewer, target = parts[0], parts[1]
            key = (reviewer, target)
            if key in seen:
                continue
            seen.add(key)
            try:
                body = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if body and record_review(reviewer, target, body):
                count += 1
    rnd = load_round()
    if rnd:
        normalize_round(rnd, save=True)
        _maybe_advance_phase(rnd)
    return count


def _reviews_for_scanner(reviewer_id: str, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in pairs if p.get("reviewer_role_id") == reviewer_id]


def _format_scanner_task(role: roles.AgentRole, targets: list[dict[str, Any]]) -> str:
    lines = [
        f"**Your identity:** {scanner_title(role)}",
        f"**Model:** {role.model} · **Subagent:** {role.subagent_type}",
        "",
        "You are a **flaw detection scanner** wearing your niche persona. "
        "Review **7 other agents' work** below — improvement & efficiency focus; holistic, not nitpicky.",
        "",
        "For **each** target output exactly:",
        "",
        "```",
        "### REVIEW:{target_role_id}",
        "- Flaws:",
        "- Efficiency upgrades:",
        "- Holistic advice:",
        "- Severity: low|med|high",
        "```",
        "",
        "After all 7 reviews, append each review via:",
        f"`python3 scripts/peer_flaw_scan.py --record-review {role.id} TARGET_ROLE_ID \"...\"`",
        f"Or save to `{REVIEWS_DIR}/{{reviewer}}__{{target}}.md` (hub SoT also: `{HUB_REVIEWS_DIR}`) and run `--compile`.",
        "",
        "## Targets to scan",
        "",
    ]
    for i, t in enumerate(targets, 1):
        work = t.get("target_work") or {}
        lines.append(f"### {i}. {t.get('target_job_title')} (`{t.get('target_role_id')}`)")
        lines.append(f"- **Work / assignment:** {work.get('item_plain') or _plain(str(work.get('item')))}")
        if work.get("responsibilities"):
            lines.append(f"- **Niche duties:** {work['responsibilities']}")
        wt = work.get("worktree")
        if isinstance(wt, dict) and wt.get("path"):
            lines.append(f"- **Worktree:** `{wt.get('path')}` branch `{wt.get('branch', '')}`")
        lines.append("")
    return "\n".join(lines)


def _format_triage_task(role: roles.AgentRole, subject: dict[str, Any]) -> str:
    received = subject.get("reviews_received") or []
    lines = [
        f"**Your identity:** {role.job_title} (original niche — not scanner mode)",
        f"**Model:** {role.model}",
        "",
        "You received **7 flaw-detection reviews** from the other niches (one per persona). "
        "**Self-triage:** decide which advice is a genuine **upgrade** vs a **downgrade** for your work.",
        "",
        "Output:",
        "1. **Summary** — themes across reviews",
        "2. **Upgrades accepted** — bullet list (actionable)",
        "3. **Downgrades rejected** — bullet list with one-line why",
        "4. Run: "
        f"`python3 scripts/peer_flaw_scan.py --record-triage {role.id} --summary \"...\"`",
        "",
        "## Your 7 reviews",
        "",
    ]
    for i, rev in enumerate(received, 1):
        lines.append(f"### Review {i} — {rev.get('reviewer_title', '?')}")
        lines.append(str(rev.get("body") or "(missing)"))
        lines.append("")
    if len(received) < 7:
        lines.append(f"_({7 - len(received)} review(s) still pending — triage when all 7 arrive.)_")
    return "\n".join(lines)


def build_orchestrator_prompt() -> str | None:
    """Full orchestrator prompt for the active flaw-scan phase."""
    rnd = load_round()
    if not rnd:
        if should_dispatch_flaw_scan():
            rnd = start_round()
        else:
            return None

    phase = rnd.get("phase")
    if phase == PHASE_COMPLETE:
        return None

    pool = _scan_pool()
    # Persist compact + advance so preview/compile unlock triage (not save=False theater).
    normalize_round(rnd, save=True)
    _maybe_advance_phase(rnd)
    rnd = load_round() or rnd
    phase = rnd.get("phase") or phase
    if phase == PHASE_COMPLETE:
        return None
    pairs = rnd.get("pairs") or build_review_pairs(pool)
    round_date = rnd.get("round_date") or _today()

    lines = [
        f"# Daily Flaw Detection Round — {round_date}",
        "",
        "Holistic improvement focus: each niche scans the others' automation work. "
        "Every agent gets **7 persona-specific reviews**, then self-triages upgrades vs downgrades.",
        "",
    ]

    if phase == PHASE_SCAN:
        done = sum(
            1
            for p in pairs
            if isinstance(p, dict)
            and p.get("status") == "done"
            and p.get("reviewer_role_id") != p.get("target_role_id")
        )
        lines.extend(
            [
                f"## Phase 1 — Cross-scan ({min(done, FLAW_SCAN_PAIR_TOTAL)}/{FLAW_SCAN_PAIR_TOTAL} reviews recorded)",
                "",
                "Launch **8 parallel Task peers** in **ONE** message. "
                "Each peer is **Flaw Detection Scanner + {job title}** and reviews **7 other agents**.",
                "",
            ]
        )
        for role in pool:
            targets = _reviews_for_scanner(role.id, pairs)
            lines.append(f"### Task: {scanner_title(role)}")
            lines.append(
                f'- Task(subagent_type="{role.subagent_type}", model="{role.model}", '
                f'description="{scanner_title(role)}", prompt="""'
            )
            lines.append(_format_scanner_task(role, targets))
            lines.append('""")')
            lines.append("")

        lines.extend(
            [
                "## After Phase 1",
                "- Ensure all 56 reviews are recorded (`--record-review` or `--compile`)",
                "- When complete, phase advances to triage automatically",
                "- Re-dispatch or continue to Phase 2 prompts",
                "",
            ]
        )
    elif phase == PHASE_TRIAGE:
        subjects = {s.get("role_id"): s for s in (rnd.get("subjects") or []) if isinstance(s, dict)}
        lines.extend(
            [
                "## Phase 2 — Self-triage (7 reviews → upgrade vs downgrade)",
                "",
                "Launch **8 parallel Task peers** in **ONE** message. "
                "Each original niche reads their 7 reviews and triages.",
                "",
            ]
        )
        for role in pool:
            subj = subjects.get(role.id) or {"reviews_received": [], "role_id": role.id}
            lines.append(f"### Task: {role.job_title} — self-triage")
            lines.append(
                f'- Task(subagent_type="{role.subagent_type}", model="{role.model}", '
                f'description="{role.job_title} triage", prompt="""'
            )
            lines.append(_format_triage_task(role, subj))
            lines.append('""")')
            lines.append("")

    lines.append("## Constraints")
    lines.append("- Improvement & efficiency focus — no style-only nitpicks")
    lines.append("- Each scanner uses their niche lens (verify, perf, safety, queue, …)")
    lines.append("- Subject agent owns final judgment on upgrades vs downgrades")
    return "\n".join(lines)


def status_dict() -> dict[str, Any]:
    cfg = load_config()
    state = load_state()
    rnd = load_round() or {}
    pool_ids = {r.id for r in _scan_pool()}
    pairs = rnd.get("pairs") or []
    done_reviews = sum(
        1
        for p in pairs
        if isinstance(p, dict)
        and p.get("status") == "done"
        and str(p.get("reviewer_role_id") or "") in pool_ids
        and str(p.get("target_role_id") or "") in pool_ids
        and p.get("reviewer_role_id") != p.get("target_role_id")
        and str(p.get("review") or "").strip()
    )
    subjects = [
        s
        for s in (rnd.get("subjects") or [])
        if isinstance(s, dict) and str(s.get("role_id") or "") in pool_ids
    ]
    done_triage = sum(1 for s in subjects if isinstance(s, dict) and s.get("triage"))
    return {
        "enabled": cfg.enabled,
        "daily_time": cfg.daily_time,
        "past_daily_time": is_past_daily_time(cfg),
        "today": _today(),
        "last_completed_date": state.get("last_completed_date"),
        "round": {
            "round_date": rnd.get("round_date"),
            "phase": rnd.get("phase"),
            "started_at": rnd.get("started_at"),
            "reviews_done": done_reviews,
            "reviews_total": FLAW_SCAN_PAIR_TOTAL,
            "triage_done": done_triage,
            "triage_total": FLAW_SCAN_POOL_SIZE,
            "pairs_on_disk": len(pairs),
            "subjects_on_disk": len(rnd.get("subjects") or []),
        },
        "should_dispatch": should_dispatch_flaw_scan(),
    }


def format_status() -> str:
    st = status_dict()
    r = st.get("round") or {}
    lines = [
        f"Flaw scan · enabled={st['enabled']} · daily {st['daily_time']} local",
        f"Today {st['today']} · last completed {st.get('last_completed_date') or '—'}",
        f"Round phase={r.get('phase') or '—'} · reviews {r.get('reviews_done')}/{r.get('reviews_total')} "
        f"· triage {r.get('triage_done')}/{r.get('triage_total')}",
        f"Should dispatch now: {st.get('should_dispatch')}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily flaw-detection cross-review")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--preview", action="store_true", help="Print orchestrator prompt")
    parser.add_argument("--start", action="store_true", help="Force start today's round")
    parser.add_argument("--record-review", nargs=3, metavar=("REVIEWER", "TARGET", "BODY"))
    parser.add_argument("--record-triage", metavar="ROLE_ID")
    parser.add_argument("--summary", default="", help="With --record-triage")
    parser.add_argument("--upgrades", default="", help="Comma-separated accepted upgrades")
    parser.add_argument("--downgrades", default="", help="Comma-separated rejected advice")
    parser.add_argument("--compile", action="store_true", help="Ingest flaw-scan-reviews/*.md")
    parser.add_argument(
        "--advance",
        action="store_true",
        help="Normalize bloated rounds to 8×7 + force phase check (56→triage)",
    )
    parser.add_argument(
        "--heal",
        action="store_true",
        help="Alias of --advance (Lane F compile heal)",
    )
    args = parser.parse_args(argv)

    if args.start:
        start_round(force=True)

    if args.record_review:
        ok = record_review(args.record_review[0], args.record_review[1], args.record_review[2])
        return 0 if ok else 1

    if args.record_triage:
        ups = [s.strip() for s in args.upgrades.split(",") if s.strip()] if args.upgrades else []
        downs = [s.strip() for s in args.downgrades.split(",") if s.strip()] if args.downgrades else []
        ok = record_triage(args.record_triage, summary=args.summary or "(triage recorded)", upgrades=ups, downgrades=downs)
        return 0 if ok else 1

    if args.compile:
        n = compile_from_review_files()
        print(f"compiled {n} review file(s)")
        st = status_dict().get("round") or {}
        print(
            f"phase={st.get('phase')} reviews {st.get('reviews_done')}/{st.get('reviews_total')} "
            f"triage {st.get('triage_done')}/{st.get('triage_total')}"
        )
        return 0

    if args.advance or args.heal:
        rnd = load_round()
        if rnd:
            normalize_round(rnd, save=True)
            _maybe_advance_phase(rnd)
            state = load_state()
            state["heal_note"] = (
                f"flaw_researcher normalize→{FLAW_SCAN_PAIR_TOTAL} pairs/"
                f"{FLAW_SCAN_POOL_SIZE} subjects (OVERSEER_FLAW_SCAN_POOL_CAP_8_2026_09_07)"
            )
            save_state(state)
        print(format_status())
        return 0

    if args.preview:
        text = build_orchestrator_prompt()
        print(text or "(no active flaw-scan round)")
        return 0

    if args.json:
        print(json.dumps(status_dict(), indent=2))
        return 0

    if args.status:
        print(format_status())
        return 0

    print(format_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
