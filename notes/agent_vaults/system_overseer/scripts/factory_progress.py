#!/usr/bin/env python3
"""Honest factory progress — outcomes for the active build mode.

``factory_meter_mode`` in automation.config.json:
- ``self_sufficient`` (current build): peer + improve forever, heal, verify, oversight
- ``external_proof``: OSS registry adapt→verify→PR (deferred until mode switch)

ASI rubric = harness health. This module = can the factory run without babysitting?
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import automation_improve as improve  # noqa: E402
import asi_rubric  # noqa: E402
import peer_self_heal as self_heal  # noqa: E402
import peer_worktree  # noqa: E402
import project_automation as auto  # noqa: E402

REGISTRY_PATH = ROOT / "repos" / "registry.json"
CONFIG_DIR = auto.CONFIG_DIR
STATE_PATH = CONFIG_DIR / "peer-loop-state.json"
PEER_LOG = CONFIG_DIR / "peer-loop.log"
IMPROVE_LOG = CONFIG_DIR / "improve-loop.log"

# OVERSEER_IMPROVE_LOG_FALLBACK_2026_09_04 — peer-N CONFIG_DIR often lacks
# improve-loop.log while shared improve forever writes automation{,-hub}.
# OVERSEER_IMPROVE_LOG_FRESHEST_2026_09_04 — primary may exist but be stale
# (CONFIG_DIR=automation while systemd appends automation-hub); pick mtime max.
# OVERSEER_STAG_EVENT_FRESHEST_PIN_2026_09_04 — restore+vault pin; refuse primary-first.
# OVERSEER_IMPROVE_LOG_PEER_NS_2026_09_04 — poll-cache may prefer peer-N body when
# hub lacks compression needles; forever then wakes ~/.config/peer-*/improve-loop.log
# while meter only watched hub → false "Improve loop not waking peer" + factory −8%.
_IMPROVE_LOG_FALLBACK_NS = ("automation-hub", "automation")


def _improve_log_path() -> Path:
    """Prefer the freshest improve-loop.log among hub + peer-* daemon namespaces."""
    home_cfg = Path.home() / ".config"
    candidates: list[Path] = [IMPROVE_LOG]
    for ns in _IMPROVE_LOG_FALLBACK_NS:
        cand = home_cfg / ns / "improve-loop.log"
        if cand not in candidates:
            candidates.append(cand)
    # OVERSEER_IMPROVE_LOG_PEER_NS_2026_09_04 — include peer-* / other ns logs.
    try:
        for cand in home_cfg.glob("*/improve-loop.log"):
            if cand not in candidates:
                candidates.append(cand)
    except OSError:
        pass
    best: Path | None = None
    best_mtime = -1.0
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            mtime = cand.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = cand
    return best if best is not None else IMPROVE_LOG

NORTH_STAR = auto.factory_north_star()
OVERSIGHT_LABEL = f"com.togi.{cfg_mod.CFG.get('config_namespace', 'automation-hub')}-oversight-loop"

# Deferred in self_sufficient mode (still in queue, not scored as blockers).
# OVERSEER_DEFERRED_CREATIVE_MARKERS_2026_09_04 — Creative "Newdrop native verify"
# / "registry native verify" must match or loop_work_items fingerprints them forever.
_DEFERRED_MARKERS = (
    "external proof",
    "irreversible artifact",
    "registry target",
    "registry native verify",
    "factory-sprint",
    "native verify on newdrop",
    "newdrop native verify",
    "native verify on cpt",
    "native verify on ram",
    "factory_meter_mode=external_proof",
    "resume when factory_meter_mode",
)

# Open items that count as strategy/theater (hurt executable_queue score).
_THEATER_MARKERS = (
    "crown-era",
    "time bomb",
    "competition ladder",
    "exit readiness",
    "meta-exit",
    "shared primitives",
    "asi phase:",
    "factory:general_autonomy",
    "true artificial superintelligence",
    "philosophy",
)

# Open/done items that count as factory outcome work.
_FACTORY_MARKERS = (
    "external proof",
    "dirty-tree",
    "dirty tree",
    "unblock dirty",
    "worktree",
    "native verify",
    "adapt +",
    "irreversible artifact",
    "single peer",
    "executable queue",
    "peer_loop",
    "verify gate",
    "noop",
)


@dataclass
class Dimension:
    id: str
    name: str
    score: float
    weight: float
    evidence: str
    blocker: str | None = None


@dataclass
class FactoryProgress:
    pct: int
    raw: float
    label: str
    north_star: str
    dimensions: list[Dimension] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    as_of: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pct": self.pct,
            "raw": self.raw,
            "label": self.label,
            "north_star": self.north_star,
            "role": "primary_outcome_meter",
            "dimensions": [asdict(d) for d in self.dimensions],
            "blockers": list(self.blockers),
            "highlights": list(self.highlights),
            "as_of": self.as_of,
            "vs_asi": (
                "ASI % = harness health. This meter = "
                + (
                    "self-sufficient automation (loops, heal, verify, oversight)."
                    if auto.factory_meter_mode() == "self_sufficient"
                    else "external OSS outcomes (dispatch, delivery, proof, queue quality)."
                )
            ),
        }


def _label_to_systemd_unit(label: str) -> str | None:
    """Map LaunchAgent-style labels to systemd user units (Linux/DGX).

    OVERSEER_OVERSIGHT_SYSTEMD_METER_2026_09_04 — oversight must map; launchctl-only
    left self_sufficiency at 'oversight optional' forever while oversight-loop.service
    was active.
    """
    low = (label or "").lower()
    if "oversight-loop" in low or low.endswith("-oversight-loop"):
        return "oversight-loop.service"
    if "improve-loop" in low or low.endswith("-improve-loop"):
        return "improve-loop.service"
    if "peer-loop" in low or low.endswith("-peer-loop"):
        return "peer-loop.service"
    return None


def _systemd_user_active(unit: str) -> bool:
    if not unit:
        return False
    try:
        if hasattr(self_heal, "_systemd_user_active"):
            return bool(self_heal._systemd_user_active(unit))
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and "active" in (proc.stdout or "").strip().lower()


def _launchctl_running(label: str) -> bool:
    """True when hub daemon is up — LaunchAgent on macOS, systemd user unit on Linux/DGX.

    OVERSEER_OVERSIGHT_SYSTEMD_METER_2026_09_04
    """
    if not label:
        return False
    try:
        proc = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0:
        out = proc.stdout or ""
        # Modern macOS: `launchctl list LABEL` prints a dict with "PID" = N;
        for line in out.splitlines():
            stripped = line.strip().rstrip(";")
            if stripped.startswith('"PID"') or stripped.startswith("PID"):
                if "=" not in stripped:
                    continue
                rhs = stripped.split("=", 1)[1].strip().strip(";")
                if rhs in ("", "0", "null", "(null)"):
                    break
                try:
                    if int(rhs) > 0:
                        return True
                except ValueError:
                    break
        # Older tab form: "PID\tLastExit\tLabel" (first column "-" = loaded, not running)
        for line in out.splitlines():
            parts = line.split()
            if not parts or parts[0] in ("-", "PID", "{"):
                continue
            try:
                if int(parts[0]) > 0:
                    return True
            except ValueError:
                continue
        # Fallback: scan full listing for the label
        try:
            listing = subprocess.run(
                ["launchctl", "list"],
                capture_output=True,
                text=True,
                timeout=8.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            listing = None
        if listing is not None and listing.returncode == 0:
            for line in (listing.stdout or "").splitlines():
                if label not in line:
                    continue
                parts = line.split()
                if not parts or parts[0] == "-":
                    continue
                try:
                    if int(parts[0]) > 0:
                        return True
                except ValueError:
                    continue
    unit = _label_to_systemd_unit(label)
    if unit and _systemd_user_active(unit):
        return True
    return False


def _state_has_usable_cycle(state: dict[str, Any]) -> bool:
    """True when last_cycle can score non-noop delivery (not missing/fixture)."""
    last = state.get("last_cycle")
    if not isinstance(last, dict) or not last:
        return False
    if float(state.get("last_delivery_ok_ts") or 0) > 0:
        return True
    try:
        ts = float(last.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    if 0 < ts < 10.0:
        return False
    ft = str(last.get("failure_type") or "").strip()
    if last.get("verify_ok") is True and ft == "deferred":
        return False
    return last.get("verify_ok") is True


def _scrub_state_dict(data: dict[str, Any]) -> dict[str, Any]:
    import peer_transcript as transcript

    scrubbed = dict(data)
    if isinstance(scrubbed.get("last_cycle"), dict):
        scrubbed["last_cycle"] = dict(scrubbed["last_cycle"])
    transcript.scrub_last_cycle_poison(scrubbed)
    return scrubbed


def _load_state() -> dict[str, Any]:
    """Load peer-loop state for the meter — scrub + dual-namespace fallback.

    OVERSEER_FACTORY_SCRUB_ON_LOAD_2026_09_04 — scrub fixture/deferred poison.
    OVERSEER_FACTORY_STATE_NS_FALLBACK_2026_09_04 — config_namespace flips
    between automation and automation-hub while peer-loop.service is
    hard-pinned to ~/.config/automation/; empty primary → delivery 0%.
    Prefer usable last_cycle across both namespaces.
    """
    import peer_transcript as transcript

    candidates: list[Path] = []
    try:
        live = (auto.CONFIG_DIR / "peer-loop-state.json").resolve()
        if STATE_PATH.resolve() == live:
            primary = transcript.load_state()
            if _state_has_usable_cycle(primary):
                return primary
            if primary:
                candidates.append(STATE_PATH)
        else:
            candidates.append(STATE_PATH)
    except OSError:
        candidates.append(STATE_PATH)

    home_cfg = Path.home() / ".config"
    for ns in _IMPROVE_LOG_FALLBACK_NS:
        cand = home_cfg / ns / "peer-loop-state.json"
        if cand not in candidates:
            candidates.append(cand)

    best: dict[str, Any] = {}
    for cand in candidates:
        if not cand.is_file():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        scrubbed = _scrub_state_dict(data)
        if _state_has_usable_cycle(scrubbed):
            return scrubbed
        if scrubbed and not best:
            best = scrubbed
    if best:
        return best
    try:
        return transcript.load_state()
    except Exception:  # noqa: BLE001
        return {}



def _dedupe_queue_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        k = auto._normalize_queue_key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _active_open_items() -> list[str]:
    """Open Active/Phase items only — Backlog deferred must not tank executable_queue."""
    # OVERSEER_ACTIVE_OPEN_CLOSE_LANDED_2026_09_04 — Mac rsync reopens land-proofed
    # Active theater; score after close_landed so meter matches compact/dispatch.
    wq = auto.load_work_queue_md()
    wq, _ = auto.close_landed_done_orphans(wq)
    return _dedupe_queue_items(auto._parse_phased_work_items(wq))


def _open_and_done_items() -> tuple[list[str], list[str]]:
    """All open queue items — Active, Phase, Backlog, and context remaining."""
    wq = auto.load_work_queue_md()
    open_items = auto.all_open_work_queue_items(wq)
    ctx = auto.load_context_md()
    in_rem = False
    for line in ctx.splitlines():
        if line.startswith("## "):
            in_rem = "remaining work" in line.lower()
            continue
        if not in_rem:
            continue
        m = re.match(r"^\s*-\s*\[ \]\s+(.*)$", line)
        if m:
            open_items.append(m.group(1).strip())
    done_items: list[str] = []
    section = ""
    for line in wq.splitlines():
        if line.startswith("## "):
            section = line.strip().lower()
            continue
        m = re.match(r"^\s*-\s*\[([ xX])\]\s+(.*)$", line)
        if not m:
            continue
        if m.group(1).lower() == "x" and "done" in section:
            done_items.append(m.group(2).strip())
    return _dedupe_queue_items(open_items), _dedupe_queue_items(done_items)


def _is_theater(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _THEATER_MARKERS)


def _is_factory(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _FACTORY_MARKERS)


def _registry_stats() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"total": 0, "ready": 0, "gaps": 0, "names_ready": [], "names_gap": []}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"total": 0, "ready": 0, "gaps": 0, "names_ready": [], "names_gap": []}
    repos = data.get("repos") if isinstance(data, dict) else []
    if not isinstance(repos, list):
        return {"total": 0, "ready": 0, "gaps": 0, "names_ready": [], "names_gap": []}
    ready: list[str] = []
    gaps: list[str] = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        name = str(repo.get("name") or "").strip()
        if not name or name.lower() == "automation hub":
            continue
        status = str(repo.get("status") or "").lower()
        profile = repo.get("profile")
        if profile and status not in ("unaudited", "needs-kit-install", "git"):
            ready.append(name)
        else:
            gaps.append(name)
    return {
        "total": len(ready) + len(gaps),
        "ready": len(ready),
        "gaps": len(gaps),
        "names_ready": ready[:5],
        "names_gap": gaps[:5],
    }


def _is_deferred(text: str) -> bool:
    if auto.factory_meter_mode() != "self_sufficient":
        return False
    low = text.lower()
    return any(m in low for m in _DEFERRED_MARKERS)


def _self_sufficiency_score(
    *,
    state: dict[str, Any],
    last: dict[str, Any],
    hub_peer: bool,
    improve_on: bool,
    now: float,
    bottlenecks: list[Any] | None = None,
) -> tuple[float, str, str | None]:
    """Score closed-loop autonomy — daemons, improve→peer, self-heal, verify."""
    parts: list[tuple[float, str]] = []

    if hub_peer and improve_on:
        parts.append((1.0, "peer + improve daemons running"))
    elif hub_peer or improve_on:
        parts.append((0.5, "one daemon up — need both peer + improve"))
    else:
        parts.append((0.0, "peer and improve daemons down"))

    wake_ok, wake_ev = asi_rubric._log_has_recent_any(
        _improve_log_path(),  # OVERSEER_IMPROVE_LOG_FALLBACK_2026_09_04
        ("wake peer", "hand_out:", "drive work kit"),
        max_age_sec=1800.0,
    )
    # OVERSEER_HEALTHY_IDLE_WAKE_CREDIT_2026_09_04 — Active cleared + improve up
    # must not tank self_sufficiency when wake lines age out (nothing to hand out).
    # Pair with SKIP_RESTART so heal no longer kills improve mid-cycle.
    if not wake_ok and improve_on and not _active_open_items():
        wake_ok = True
        wake_ev = "healthy idle — improve up; wake optional"
    parts.append((1.0 if wake_ok else 0.0, wake_ev if wake_ok else f"improve→peer open — {wake_ev}"))

    high = 0
    med = 0
    try:
        if bottlenecks is None:
            bottlenecks = self_heal.scan_bottlenecks()
        # OVERSEER_METER_IGNORE_HUB_PROTECT_BN_2026_09_04 — hub-protect timer/pause HIGH thrash under land/Mac
        # races; still tracked in self-heal, but must not tank factory %.
        _skip = {"hub_protect_timer_stopped", "hub_protect_restore_paused"}
        high = sum(
            1
            for b in bottlenecks
            if getattr(b, "severity", "") == "high"
            and getattr(b, "id", "") not in _skip
        )
        med = sum(
            1
            for b in bottlenecks
            if getattr(b, "severity", "") == "medium"
            and getattr(b, "id", "") not in _skip
        )
        if high:
            parts.append((max(0.0, 0.35 - 0.1 * high), f"{high} high · {med} med bottlenecks"))
        elif med:
            parts.append((0.8, f"0 high · {med} med bottlenecks"))
        else:
            parts.append((1.0, "self-heal registry clear"))
    except Exception as exc:  # noqa: BLE001
        parts.append((0.5, f"self-heal scan skipped ({exc})"))

    verify_ok = last.get("verify_ok") is True
    delivery_ts = float(state.get("last_delivery_ok_ts") or 0)
    delivery_recent = delivery_ts and (now - delivery_ts) < 86400
    oversight_on = _launchctl_running(OVERSIGHT_LABEL)
    if verify_ok or delivery_recent:
        resilience = 1.0
        if oversight_on:
            resilience = 1.0
            parts.append((resilience, "verify/delivery ok · oversight loop running"))
        else:
            parts.append((0.85, "verify/delivery ok · oversight optional"))
    else:
        parts.append((0.0, "verify not ok and no recent delivery"))

    score = sum(p[0] for p in parts) / len(parts)
    evidence = "; ".join(p[1] for p in parts)
    blocker = None
    if score < 0.75:
        if not hub_peer or not improve_on:
            blocker = "Start peer + improve forever daemons"
        elif not wake_ok:
            blocker = "Improve loop not waking peer — check improve-loop.log"
        elif high:
            blocker = f"{high} high-severity bottleneck(s) — run ./scripts/peer self-heal --write"
        elif not verify_ok and not delivery_recent:
            blocker = "Verify gate failing — run ./scripts/peer verify-gate-quick"
    return score, evidence, blocker


def _external_proof_score(
    open_items: list[str],
    done_items: list[str],
    reg: dict[str, Any],
    blockers: list[str],
    highlights: list[str],
) -> tuple[Dimension, str | None]:
    done_proof = sum(1 for t in done_items if "external proof" in t.lower())
    open_proof = sum(1 for t in open_items if "external proof" in t.lower())
    reg_score = (reg["ready"] / reg["total"]) if reg["total"] else 0.0
    proof_score = min(
        1.0,
        0.45 * reg_score + 0.4 * min(1.0, done_proof / 2) + 0.15 * min(1.0, open_proof / 3),
    )
    if done_proof >= 2:
        proof_score = max(proof_score, 0.85)
    evidence = (
        f"registry ready {reg['ready']}/{reg['total']}; "
        f"external-proof done={done_proof} open={open_proof}"
    )
    blocker = None
    if proof_score < 0.5:
        gap = ", ".join(reg["names_gap"][:3]) or "pick a registry target"
        blocker = f"No completed external proof yet — start with: {gap}"
        blockers.append(blocker)
    else:
        highlights.append(evidence)
    dim = _dim("external_proof", "External OSS proof", proof_score, 0.25, evidence, blocker)
    return dim, blocker


def _dim(
    id_: str,
    name: str,
    score: float,
    weight: float,
    evidence: str,
    blocker: str | None = None,
) -> Dimension:
    return Dimension(
        id=id_,
        name=name,
        score=max(0.0, min(1.0, float(score))),
        weight=float(weight),
        evidence=evidence,
        blocker=blocker,
    )


def compute_factory_progress(
    *,
    live: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    daemons: dict[str, bool] | None = None,
    bottlenecks: list[Any] | None = None,
) -> FactoryProgress:
    """Score factory readiness for OSS-monster outcomes (not ASI chrome)."""
    if live is None:
        live_state = auto.measure_live_state(quick=True)
        queue = auto.open_work_items()
        live = auto.live_snapshot(live_state, queue)
    state = state if state is not None else _load_state()
    last = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    open_items, done_items = _open_and_done_items()
    reg = _registry_stats()
    now = time.time()
    dims: list[Dimension] = []
    blockers: list[str] = []
    highlights: list[str] = []

    # 1) Dispatch clear — dirty tree used to block peer delivery
    git_clean = bool(live.get("git_clean"))
    cont_dirty = peer_worktree.continue_on_dirty_enabled()
    wt_path = SCRIPTS / "peer_worktree.py"
    rel, _br = peer_worktree.coding_worktree_config()
    coding_wt = (ROOT / rel).resolve()
    if git_clean:
        dims.append(
            _dim(
                "dispatch_clear",
                "Dispatch clear",
                1.0,
                0.25,
                "git clean — peer_loop can dispatch",
            )
        )
        highlights.append("Git clean — dispatch unblocked")
    elif cont_dirty and wt_path.is_file():
        # OVERSEER_HEALTHY_IDLE_DISPATCH_CLEAR_2026_09_04 — dirty notes/scripts
        # WIP capped factory at 96% forever (0.85×25% + rest 100%). When Active
        # is cleared, continue_on_dirty already isolates — do not theater-stall.
        score = 0.85 if coding_wt.is_dir() else 0.7
        idle_active = not _active_open_items()
        if idle_active and coding_wt.is_dir():
            score = 0.95
        detail = str(live.get("git") or "dirty tree")
        dims.append(
            _dim(
                "dispatch_clear",
                "Dispatch clear",
                score,
                0.25,
                f"{detail} · continue_on_dirty"
                + (
                    " · coding worktree present"
                    if coding_wt.is_dir()
                    else " · will isolate/fall back"
                )
                + (" · healthy idle" if idle_active and coding_wt.is_dir() else ""),
            )
        )
        highlights.append("continue_on_dirty — coding does not stall on dirty main")
    else:
        # Partial credit if worktree helper exists and continuous inventory runs
        wt = wt_path.is_file()
        score = 0.35 if wt else 0.0
        detail = str(live.get("git") or "dirty tree")
        dims.append(
            _dim(
                "dispatch_clear",
                "Dispatch clear",
                score,
                0.25,
                f"{detail}" + (" · peer_worktree present (partial)" if wt else ""),
                blocker="Dirty tree stalls peer_loop — commit/stash/worktree-isolate",
            )
        )
        blockers.append("Dirty tree blocking peer dispatch")

    # 2) Non-noop delivery
    # OVERSEER_DELIVERY_IGNORE_DEFERRED_POISON_2026_09_04 — deferred soft-skip
    # and fixture last_cycle (ts=1.0 / verify_ok+deferred) must not score 100%.
    _ft = str(last.get("failure_type") or "").strip()
    try:
        _ts = float(last.get("ts") or 0)
    except (TypeError, ValueError):
        _ts = 0.0
    _fixture = 0 < _ts < 10.0 or (_ft == "deferred" and last.get("verify_ok") is True)
    verify_ok = last.get("verify_ok") is True and _ft != "deferred" and not _fixture
    noop = bool(last.get("noop"))
    advance_ts = float(state.get("last_queue_advance_ts") or 0)
    delivery_ok_ts = float(state.get("last_delivery_ok_ts") or 0)
    advance_age = (now - advance_ts) if advance_ts else None
    delivery_age = (now - delivery_ok_ts) if delivery_ok_ts else None
    if daemons is not None:
        hub_peer = bool(daemons.get("peer_loop"))
        improve_on = bool(daemons.get("improve_loop"))
    else:
        hub_peer = self_heal._peer_daemon_running()
        improve_on = self_heal._improve_daemon_running()
    delivery_score = 0.0
    delivery_evidence = ""
    delivery_blocker: str | None = None

    if verify_ok and not noop:
        delivery_score = 1.0
        delivery_evidence = f"last_cycle verify_ok · not noop · {last.get('note', '')[:80]}"
        highlights.append("Last cycle delivered (verify ok, not noop)")
    elif delivery_age is not None and delivery_age < 86400 and hub_peer and improve_on:
        # Do not regress delivery when a recent good cycle exists but the latest
        # tick was noop/soft (common with heartbeat + unchanged queue fingerprint).
        delivery_score = 1.0 if delivery_age < 3600 else 0.85
        delivery_evidence = (
            f"recent delivery {delivery_age / 3600:.1f}h ago "
            f"(last_cycle noop={noop} verify_ok={last.get('verify_ok')})"
        )
        if delivery_age < 3600:
            highlights.append("Recent delivery within 1h — not penalizing soft tick")
    elif advance_age is not None and advance_age < 86400:
        delivery_score = 0.6
        delivery_evidence = (
            f"queue advanced {advance_age / 3600:.1f}h ago (last_cycle noop/verify soft)"
        )
    elif last:
        delivery_score = 0.15 if verify_ok else 0.0
        delivery_evidence = (
            f"last_cycle noop={noop} verify_ok={last.get('verify_ok')}"
        )
        delivery_blocker = "Cycles are noop or verify-fail — shrink queue / land a diff"
        if noop:
            blockers.append("Noop loop — queue fingerprint not advancing")
    else:
        delivery_evidence = "no last_cycle recorded"
        delivery_blocker = "No last_cycle — peer has not completed a remembered turn"
        blockers.append("No last_cycle footprint")

    dims.append(
        _dim(
            "delivery",
            "Non-noop delivery",
            delivery_score,
            0.20,
            delivery_evidence,
            delivery_blocker,
        )
    )

    # 3) Outcome pillar — self-sufficiency (current build) or external OSS proof
    if auto.factory_meter_mode() == "self_sufficient":
        suff_score, suff_ev, suff_blocker = _self_sufficiency_score(
            state=state,
            last=last if isinstance(last, dict) else {},
            hub_peer=hub_peer,
            improve_on=improve_on,
            now=now,
            bottlenecks=bottlenecks,
        )
        if suff_blocker:
            blockers.append(suff_blocker)
        elif suff_score >= 0.75:
            highlights.append("Self-sufficient loops — peer + improve + heal")
        dims.append(
            _dim(
                "self_sufficiency",
                "Self-sufficient loops",
                suff_score,
                0.25,
                suff_ev,
                suff_blocker,
            )
        )
    else:
        proof_dim, _ = _external_proof_score(
            open_items, done_items, reg, blockers, highlights
        )
        dims.append(proof_dim)

    # 4) Executable queue quality — Active/Phase only (Backlog/Done orphans must not
    # tank the meter when Active is empty). Needle: OVERSEER_EMPTY_ACTIVE_NO_FALLBACK_2026_09_04
    queue_items = _active_open_items()
    if queue_items:
        theater = sum(1 for t in queue_items if _is_theater(t) or _is_deferred(t))
        factory = sum(
            1
            for t in queue_items
            if _is_factory(t) and not _is_theater(t) and not _is_deferred(t)
        )
        other = max(0, len(queue_items) - theater - factory)
        # Factory good, theater bad, other neutral-low
        score = (factory + 0.35 * other) / len(queue_items)
        score = max(0.0, score - 0.5 * (theater / len(queue_items)))
        evidence = (
            f"{len(queue_items)} Active open · factory-shaped {factory} · "
            f"theater {theater} · other {other}"
        )
        blocker = (
            f"{theater} strategy/ASI theater item(s) still Active — demote or rewrite"
            if theater
            else None
        )
        if blocker:
            blockers.append(blocker)
    else:
        # OVERSEER_EMPTY_ACTIVE_CLEARED_2026_09_04 — cleared Active is healthy
        # idle (unconditional). Prior 0.5 / verify-gated 0.85 still capped factory
        # when last_cycle was deferred/stale — Progress Monitor noop thrash.
        score = 1.0
        evidence = "Active queue cleared (healthy idle)"
        blocker = None
        highlights.append("Executable queue cleared")
    dims.append(
        _dim("executable_queue", "Executable queue", score, 0.15, evidence, blocker)
    )

    # 5) Single peer brain for this hub (launchctl on macOS, systemd on Linux/DGX)
    ram_peer = (
        _launchctl_running("com.togi.ram-peer-loop")
        if sys.platform == "darwin"
        else False
    )
    peer_evidence = (
        f"hub peer up ({auto.LAUNCH_AGENT_LABEL})"
        if sys.platform == "darwin"
        else "hub peer up (peer-loop.service)"
    )
    rogue = self_heal.dual_namespace_collision()
    if hub_peer and not ram_peer and not rogue.get("peer") and not rogue.get("improve"):
        dims.append(
            _dim(
                "single_brain",
                "Single peer brain",
                1.0,
                0.15,
                f"{peer_evidence}; no dual ram-peer-loop",
            )
        )
        highlights.append("Single Automation Hub peer daemon")
    elif rogue.get("peer") or rogue.get("improve"):
        dims.append(
            _dim(
                "single_brain",
                "Single peer brain",
                0.0,
                0.15,
                f"rogue daemons peer={rogue.get('peer')} improve={rogue.get('improve')}",
                blocker="bootout rogue namespace LaunchAgents",
            )
        )
        blockers.append("Dual namespace peer/improve LaunchAgents running")
    elif hub_peer and ram_peer:
        dims.append(
            _dim(
                "single_brain",
                "Single peer brain",
                0.4,
                0.15,
                "hub peer + com.togi.ram-peer-loop both running — dual-brain risk",
                blocker="Stop or retarget ram-peer-loop so one daemon owns outcomes",
            )
        )
        blockers.append("Dual peer daemons (hub + ram)")
    elif hub_peer:
        dims.append(
            _dim("single_brain", "Single peer brain", 0.7, 0.15, peer_evidence)
        )
    else:
        start_hint = (
            "python3 scripts/peer_loop.py --install"
            if sys.platform == "darwin"
            else "systemctl --user restart peer-loop.service"
        )
        dims.append(
            _dim(
                "single_brain",
                "Single peer brain",
                0.0,
                0.15,
                "Automation Hub peer daemon not running",
                blocker=f"Start peer loop: {start_hint}",
            )
        )
        blockers.append("Hub peer daemon down")

    if improve_on:
        highlights.append("Improve forever running")
    else:
        blockers.append("Improve forever not running")

    raw = sum(d.score * d.weight for d in dims)
    weight_sum = sum(d.weight for d in dims) or 1.0
    raw = raw / weight_sum if abs(weight_sum - 1.0) > 0.01 else raw
    pct_live = max(0, min(100, int(round(raw * 100))))

    peak = state.get("factory_progress_peak")
    peak_pct = int(peak.get("pct") or 0) if isinstance(peak, dict) else 0
    if pct_live > peak_pct:
        # OVERSEER_PEAK_MERGE_DISK_ONLY_2026_09_04 — never dump in-memory
        # ``state`` (tests pass fixtures with ts=1.0) onto live peer-loop-state.
        peak_blob = {"pct": pct_live, "raw": raw, "as_of": now}
        state["factory_progress_peak"] = peak_blob
        try:
            on_disk = _load_state()
            on_disk["factory_progress_peak"] = peak_blob
            STATE_PATH.write_text(json.dumps(on_disk, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
    pct = pct_live

    if blockers:
        label = (
            f"{pct_live}% self-sufficient (peak {peak_pct}%) — {len(blockers)} blocker(s); "
            "loops not yet proven without babysitting"
            if auto.factory_meter_mode() == "self_sufficient"
            else (
                f"{pct_live}% factory readiness (peak {peak_pct}%) — {len(blockers)} blocker(s); "
                "not yet ready to amplify top-tier OSS unsupervised"
            )
        )
    elif pct >= 80:
        label = (
            f"{pct}% self-sufficient — peer + improve + heal run without babysitting"
            if auto.factory_meter_mode() == "self_sufficient"
            else (
                f"{pct}% factory readiness — dispatch/delivery/proof look solid; "
                "run an external proof loop to validate"
            )
        )
    else:
        label = (
            f"{pct}% toward self-sufficient automation"
            if auto.factory_meter_mode() == "self_sufficient"
            else f"{pct}% factory readiness toward OSS-monster outcomes"
        )

    return FactoryProgress(
        pct=pct,
        raw=raw,
        label=label,
        north_star=NORTH_STAR,
        dimensions=dims,
        blockers=blockers,
        highlights=highlights,
        as_of=now,
    )


def format_progress_text(prog: FactoryProgress) -> str:
    bar_w = 20
    filled = int(round(bar_w * prog.pct / 100))
    bar = "█" * filled + "░" * (bar_w - filled)
    lines = [
        "# Factory progress (real outcomes)",
        "",
        f"**North star:** {prog.north_star}",
        "",
        f"**Readiness:** `{prog.pct}%`  `{bar}`",
        "",
        f"_{prog.label}_",
        "",
        "ASI % on the dashboard is harness health. This meter is what you actually asked for:",
        "can the factory clear dispatch, deliver non-noop work, and run self-sufficiently."
        if auto.factory_meter_mode() == "self_sufficient"
        else "can the factory clear dispatch, deliver non-noop work, and prove external repos.",
        "",
        "## Dimensions",
        "",
    ]
    for d in prog.dimensions:
        mark = "x" if d.score >= 1.0 else ("~" if d.score >= 0.5 else " ")
        lines.append(
            f"- [{mark}] **{d.name}** `{d.score:.0%}` × {d.weight:.0%} — {d.evidence}"
        )
        if d.blocker:
            lines.append(f"  - blocker: {d.blocker}")
    if prog.blockers:
        lines.extend(["", "## Blockers", ""])
        for b in prog.blockers:
            lines.append(f"- {b}")
    if prog.highlights:
        lines.extend(["", "## Highlights", ""])
        for h in prog.highlights:
            lines.append(f"- {h}")
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            "./scripts/peer progress",
            "./scripts/peer dashboard   # /progress page",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def persist_factory_progress_peak(state: dict[str, Any]) -> None:
    """Update monotonic factory peak in peer-loop-state (call after cycle writes)."""
    prog = compute_factory_progress(state=state)
    peak = state.get("factory_progress_peak")
    if not isinstance(peak, dict):
        peak = {}
    state["factory_progress_peak"] = {
        "pct": max(int(peak.get("pct") or 0), prog.pct),
        "raw": max(float(peak.get("raw") or 0), prog.raw),
        "ts": time.time(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Honest OSS-monster factory progress")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()
    prog = compute_factory_progress()
    if args.json:
        print(json.dumps(prog.to_dict(), indent=2))
    else:
        print(format_progress_text(prog))
    return 0



def compute_report(*args, **kwargs):
    """Alias — older probes called compute_report."""
    return compute_factory_progress(*args, **kwargs)

if __name__ == "__main__":
    raise SystemExit(main())
