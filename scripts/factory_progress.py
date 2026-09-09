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
import os
import re
import stat as statmod
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
import asi_rubric  # noqa: E402 — wake-credit + tests patch fp.asi_rubric
import project_automation as auto  # noqa: E402


class _LazyMod:
    """Load peer_* modules on first use - preserve call-site + patch names."""

    __slots__ = ("_modname", "_mod")

    def __init__(self, modname: str) -> None:
        object.__setattr__(self, "_modname", modname)
        object.__setattr__(self, "_mod", None)

    def _load(self):  # noqa: ANN202
        mod = object.__getattribute__(self, "_mod")
        if mod is None:
            import importlib

            mod = importlib.import_module(object.__getattribute__(self, "_modname"))
            object.__setattr__(self, "_mod", mod)
        return mod

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self._load(), name)

    def __setattr__(self, name: str, value) -> None:  # noqa: ANN001
        if name in ("_modname", "_mod"):
            object.__setattr__(self, name, value)
            return
        setattr(self._load(), name, value)


self_heal = _LazyMod("peer_self_heal")
peer_worktree = _LazyMod("peer_worktree")

# COMPRESSION_LAZY_FACTORY_PROGRESS_2026_09_04
# COMPRESSION_FACTORY_LAZY_WT_HEAL_IN_STAMP_2026_09_04

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

# Needle: IMPROVE_LOG_PATH_TARGETED_SCANDIR_2026_09_08 — factory remiss paid
# pathlib ``~/.config/*/improve-loop.log`` glob (~17–22ms of ~35–38ms) walking
# ~2k config dirs; only automation* / peer-* hold daemon logs. Targeted scandir
# + 30s path TTL share across self_sufficiency / meter remiss.
# Needle: IMPROVE_LOG_PATH_CANDIDATE_STRSET_2026_09_08 — cold miss paid
# pathlib ``cand not in candidates`` (~1385 Path.__eq__ / ~53 dirs, ~1.1ms);
# dedupe via os.fspath str-set (O(1)) then Path only for return.
# Needle: IMPROVE_LOG_PATH_BOUNDED_PEERS_2026_09_08 — after str-set, cold miss
# still walked ~2240 ~/.config dirents (~1.6ms) for ~4 live improve logs.
# Bound to fallback NS + peer-0..max_parallel_peers-1 + CONFIG_DIR ns (~0.017ms).
_IMPROVE_LOG_PATH_TTL_SEC = 30.0
_IMPROVE_LOG_PATH_CACHE: dict[str, Any] = {"at": 0.0, "path": None}


def clear_improve_log_path_cache() -> None:
    """Drop freshest-improve-log path memo (tests + after ns moves)."""
    _IMPROVE_LOG_PATH_CACHE["at"] = 0.0
    _IMPROVE_LOG_PATH_CACHE["path"] = None


def _improve_log_peer_slot_cap() -> int:
    """How many peer-N namespaces to probe for freshest improve-loop.log."""
    try:
        n = int(cfg_mod.CFG.get("max_parallel_peers") or 8)
    except (TypeError, ValueError):
        n = 8
    # Floor 8 so peer-6 freshest tests + historic pool stay covered; cap runaway.
    return max(8, min(n, 64))


def _improve_log_path() -> Path:
    """Prefer the freshest improve-loop.log among hub + peer-* daemon namespaces."""
    now = time.monotonic()
    cached = _IMPROVE_LOG_PATH_CACHE.get("path")
    at = float(_IMPROVE_LOG_PATH_CACHE.get("at") or 0.0)
    if isinstance(cached, Path) and (now - at) < _IMPROVE_LOG_PATH_TTL_SEC:
        return cached

    # IMPROVE_LOG_PATH_CANDIDATE_STRSET_2026_09_08 — str paths avoid Path.__eq__ storm.
    # Use Path.home() (not expanduser) so tests can patch fp.Path.home.
    # IMPROVE_LOG_PATH_BOUNDED_PEERS_2026_09_08 — no full ~/.config scandir.
    home_cfg = os.fspath(Path.home() / ".config")
    seen: set[str] = set()
    candidates: list[str] = []

    def _add(path_s: str) -> None:
        if path_s not in seen:
            seen.add(path_s)
            candidates.append(path_s)

    _add(os.fspath(IMPROVE_LOG))
    for ns in _IMPROVE_LOG_FALLBACK_NS:
        _add(os.path.join(home_cfg, ns, "improve-loop.log"))
    try:
        cfg_ns = os.fspath(CONFIG_DIR.name)
        if cfg_ns:
            _add(os.path.join(home_cfg, cfg_ns, "improve-loop.log"))
    except (TypeError, ValueError, AttributeError):
        pass
    for i in range(_improve_log_peer_slot_cap()):
        _add(os.path.join(home_cfg, f"peer-{i}", "improve-loop.log"))
    best: str | None = None
    best_mtime = -1.0
    for cand in candidates:
        try:
            st = os.stat(cand)
        except OSError:
            continue
        if not statmod.S_ISREG(st.st_mode):
            continue
        mtime = st.st_mtime
        if mtime > best_mtime:
            best_mtime = mtime
            best = cand
    chosen = Path(best) if best is not None else IMPROVE_LOG
    _IMPROVE_LOG_PATH_CACHE["at"] = time.monotonic()
    _IMPROVE_LOG_PATH_CACHE["path"] = chosen
    return chosen

NORTH_STAR = auto.factory_north_star()
OVERSIGHT_LABEL = f"com.togi.{cfg_mod.CFG.get('config_namespace', 'automation-hub')}-oversight-loop"

# Deferred in self_sufficient mode (still in queue, not scored as blockers).
# OVERSEER_DEFERRED_CREATIVE_MARKERS_2026_09_04 — Creative "Newdrop native verify"
# / "registry native verify" must match or loop_work_items fingerprints them forever.
# OVERSEER_KIT_RUN_NOT_DEFERRED_2026_09_07 — bare "registry target" matched
# Active kit-run lines ("Kit-run third registry target") → false theater / flat %.
_DEFERRED_MARKERS = (
    "external proof",
    "irreversible artifact",
    "registry native verify",
    "factory-sprint",
    "native verify on newdrop",
    "newdrop native verify",
    "native verify on cpt",
    "native verify on ram",
    "factory_meter_mode=external_proof",
    "resume when factory_meter_mode",
    # OVERSEER_DEMOTE_HUMAN_AUTH_BLOCK_2026_09_07 — Creative demotes must not
    # re-enter loop_work_items fingerprint when Active is empty.
    "push_auth_missing",
    "gh_cli_missing",
    "human-auth block",
    "no ssh/gh",
    # OVERSEER_DEMOTE_A_TO_Z_AUTH_PIN_2026_09_07 — red sequencing-lock Creative
    "factory a→z sequencing lock",
    "red until real pr/merge_note",
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
    # OVERSEER_TOP10_FACTORY_MARKERS_2026_09_07 — Top10 Newdrop-only Active is
    # production policy, not "other" theater (Executable queue was pinned 35%).
    "[top10]",
    "top10_next",
    "top10_implementer",
    "newdrop production",
    "scoreboard ritual",
    "production_power_scoreboard",
    # OVERSEER_A_TO_Z_FACTORY_MARKERS_2026_09_07 — sequencing-lock kit work is
    # factory outcome (kit-run A→E), not ASI theater.
    "[a-to-z",
    "kit-run",
    "factory_kit_run",
    "kit_a_to_z",
)


@dataclass
class Dimension:
    id: str
    name: str
    score: float
    weight: float
    evidence: str
    blocker: str | None = None


# OVERSEER_FACTORY_THROUGHPUT_2026_09_07 — mass×speed live signal for /progress.
THROUGHPUT_WINDOW_SEC = 3600.0
# Efficient bar: ≥2 non-noop cycles/hour when Active has work; idle OK when quiet.
THROUGHPUT_EFFICIENT_CPH = 2.0
THROUGHPUT_EFFICIENT_NON_NOOP = 0.5
THROUGHPUT_STALE_CYCLE_SEC = 1800.0


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
    throughput: dict[str, Any] = field(default_factory=dict)

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
            "throughput": dict(self.throughput) if self.throughput else {},
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

    Needle: FACTORY_DAEMON_PROBE_SHARE_ASI_TTL_2026_09_08 — on Linux/DGX, reuse
    ``asi_rubric._launchctl_running`` (DAEMON_PROBE_TTL + skip launchctl) so factory
    remiss does not re-shell systemctl after write_prompts/ASI already probed.
    Darwin keeps the plist-style PID parser below (tests + LaunchAgent).
    """
    if not label:
        return False
    # FACTORY_DAEMON_PROBE_SHARE_ASI_TTL_2026_09_08
    if sys.platform != "darwin":
        return bool(asi_rubric._launchctl_running(label))
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
    """Scrub fixture/deferred poison without importing peer_transcript.

    Needle: FACTORY_STATE_SCRUB_POISON_LIGHT_2026_09_08 — cold
    ``import peer_transcript`` pulled worktree/poison (~75ms compile) just to
    call ``scrub_last_cycle_poison``; light module is ~9ms and API-identical.
    """
    import peer_last_cycle_poison as poison

    scrubbed = dict(data)
    if isinstance(scrubbed.get("last_cycle"), dict):
        scrubbed["last_cycle"] = dict(scrubbed["last_cycle"])
    poison.scrub_last_cycle_poison(scrubbed)
    return scrubbed


def _read_state_json(path: Path) -> dict[str, Any]:
    """Read + scrub peer-loop-state.json (no peer_transcript / no save side-effect)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return _scrub_state_dict(data)


def _clean_peer_improve_active() -> tuple[bool, bool, str]:
    """Credit CLEAN systemd peer+improve when Mac is mac-offloaded.

    Prefer fresh ``dgx-watch.json`` cache (watch already SSHes); fall back to a
    direct ``systemctl --user is-active`` over SSH. Local LaunchAgent checks are
    false-negatives under offload — meter must not say Mac daemons are down.
    """
    peer_ok = False
    improve_ok = False
    evidence = "CLEAN peer/improve unknown"

    # 1) Cached dgx-watch status (written by dgx_watch run_watch)
    for ns in ("automation-hub", "automation"):
        watch = Path.home() / ".config" / ns / "dgx-watch.json"
        if not watch.is_file():
            continue
        try:
            age = time.time() - watch.stat().st_mtime
            data = json.loads(watch.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        services = data.get("services")
        if not isinstance(services, dict):
            continue
        # Accept cache up to 10m — watch interval is typically 30s
        if age > 600.0:
            continue
        peer_ok = str(services.get("peer-loop") or "").strip() == "active"
        improve_ok = str(services.get("improve-loop") or "").strip() == "active"
        ssh_rc = str(services.get("_ssh_rc") or "")
        evidence = (
            f"CLEAN peer-loop={'active' if peer_ok else 'down'} "
            f"improve-loop={'active' if improve_ok else 'down'} "
            f"(dgx-watch cache age={age:.0f}s ssh_rc={ssh_rc or '?'})"
        )
        if peer_ok or improve_ok or ssh_rc == "0":
            return peer_ok, improve_ok, evidence

    # 2) Live SSH via dgx_watch.remote_service_status
    try:
        import dgx_watch as dw

        status = dw.remote_service_status()
        if isinstance(status, dict):
            peer_ok = str(status.get("peer-loop") or "").strip() == "active"
            improve_ok = str(status.get("improve-loop") or "").strip() == "active"
            evidence = (
                f"CLEAN peer-loop={'active' if peer_ok else 'down'} "
                f"improve-loop={'active' if improve_ok else 'down'} "
                f"(ssh_rc={status.get('_ssh_rc', '?')})"
            )
            return peer_ok, improve_ok, evidence
    except Exception:  # noqa: BLE001
        pass

    # 3) Direct SSH fallback
    host = "CLEAN"
    try:
        import dgx_watch as dw

        host = str(dw.ssh_host() or "CLEAN")
    except Exception:  # noqa: BLE001
        pass
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=12",
                host,
                "systemctl --user is-active peer-loop improve-loop 2>/dev/null",
            ],
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, False, f"CLEAN ssh failed host={host}"
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    peer_ok = bool(lines) and lines[0] == "active"
    improve_ok = len(lines) > 1 and lines[1] == "active"
    evidence = (
        f"CLEAN peer-loop={'active' if peer_ok else 'down'} "
        f"improve-loop={'active' if improve_ok else 'down'} "
        f"(ssh_rc={proc.returncode})"
    )
    return peer_ok, improve_ok, evidence


# Needle: MAC_OFFLOADED_TTL_2026_09_08 — factory compute called ``_mac_offloaded``
# 5×/MISS (~0.01ms each via marker ``is_file``); marker almost never flips mid-tick.
_MAC_OFFLOADED_TTL_SEC = 30.0
_MAC_OFFLOADED_CACHE: dict[str, Any] = {"at": 0.0, "val": None}


def clear_mac_offloaded_cache() -> None:
    """Drop mac-offload memo (tests + after offload marker flips)."""
    _MAC_OFFLOADED_CACHE["at"] = 0.0
    _MAC_OFFLOADED_CACHE["val"] = None


def _mac_offloaded() -> bool:
    """True when Mac peer/improve are parked on CLEAN (dgx_mac_offload marker).

    Needle: MAC_OFFLOADED_TTL_2026_09_08 — TTL memo; marker is sticky.
    Needle: FACTORY_MAC_OFFLOAD_LINUX_NO_DGX_IMPORT_2026_09_08 — on Linux/DGX
    the marker file is SoT; skip cold ``import dgx_watch`` (~35ms) when absent.
    """
    now = time.monotonic()
    cached = _MAC_OFFLOADED_CACHE.get("val")
    if cached is not None and (now - float(_MAC_OFFLOADED_CACHE.get("at") or 0.0)) < _MAC_OFFLOADED_TTL_SEC:
        return bool(cached)
    marker = Path.home() / ".config" / "automation-hub" / "mac-offloaded"
    if marker.is_file():
        val = True
    elif sys.platform != "darwin":
        # FACTORY_MAC_OFFLOAD_LINUX_NO_DGX_IMPORT_2026_09_08
        val = False
    else:
        try:
            import dgx_watch as dw

            val = bool(dw.mac_offloaded())
        except Exception:  # noqa: BLE001
            val = False
    _MAC_OFFLOADED_CACHE["at"] = now
    _MAC_OFFLOADED_CACHE["val"] = val
    return val


def _brain_meta() -> dict[str, Any]:
    """Honest brain label — mac-offload must not look like a dead local factory."""
    offloaded = _mac_offloaded()
    if offloaded:
        return {
            "brain": "CLEAN",
            "mac_offloaded": True,
            "note": (
                "mac-offloaded — peer/improve run on CLEAN; "
                "local LaunchAgent checks are false-negatives"
            ),
        }
    if sys.platform != "darwin":
        return {
            "brain": "CLEAN",
            "mac_offloaded": False,
            "note": "Linux/DGX hub host — brain=CLEAN",
        }
    return {
        "brain": "local",
        "mac_offloaded": False,
        "note": "Mac local brain (not offloaded)",
    }


def _load_state_with_source() -> tuple[dict[str, Any], str]:
    """Load scrubbed peer-loop state + source path (prefer hub/CLEAN ns).

    OVERSEER_FACTORY_SCRUB_ON_LOAD_2026_09_04 — scrub fixture/deferred poison.
    OVERSEER_FACTORY_STATE_NS_FALLBACK_2026_09_04 — config_namespace flips
    between automation and automation-hub while peer-loop.service is
    hard-pinned to ~/.config/automation/; empty primary → delivery 0%.
    Prefer usable last_cycle across both namespaces.
    Needle: FACTORY_STATE_SCRUB_POISON_LIGHT_2026_09_08 — json+poison scrub;
    never cold-import peer_transcript for the meter read path.
    """
    candidates: list[Path] = []
    try:
        live = (auto.CONFIG_DIR / "peer-loop-state.json").resolve()
        if STATE_PATH.resolve() == live:
            # FACTORY_STATE_SCRUB_POISON_LIGHT — meter is read-only (no save_state)
            primary = _read_state_json(STATE_PATH) if STATE_PATH.is_file() else {}
            if _state_has_usable_cycle(primary):
                return primary, str(STATE_PATH)
            if primary:
                candidates.append(STATE_PATH)
        else:
            candidates.append(STATE_PATH)
    except OSError:
        candidates.append(STATE_PATH)

    home_cfg = Path.home() / ".config"
    # Prefer hub ns first when mac-offloaded (CLEAN writes automation-hub).
    ns_order = list(_IMPROVE_LOG_FALLBACK_NS)
    if _mac_offloaded() and "automation-hub" in ns_order:
        ns_order = ["automation-hub"] + [n for n in ns_order if n != "automation-hub"]
    for ns in ns_order:
        cand = home_cfg / ns / "peer-loop-state.json"
        if cand not in candidates:
            candidates.append(cand)

    best: dict[str, Any] = {}
    best_path = ""
    for cand in candidates:
        if not cand.is_file():
            continue
        scrubbed = _read_state_json(cand)
        if not scrubbed:
            continue
        if _state_has_usable_cycle(scrubbed):
            return scrubbed, str(cand)
        if scrubbed and not best:
            best = scrubbed
            best_path = str(cand)
    if best:
        return best, best_path
    if STATE_PATH.is_file():
        return _read_state_json(STATE_PATH), str(STATE_PATH)
    return {}, ""


def _load_state() -> dict[str, Any]:
    """Load peer-loop state for the meter — scrub + dual-namespace fallback."""
    state, _src = _load_state_with_source()
    return state



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


# Needle: ACTIVE_OPEN_WQ_MTIME_GENERATION_2026_09_08 — factory remiss called
# ``_active_open_items`` 3–4× (dispatch idle + throughput + executable_queue +
# wake credit) → ``close_landed_done_orphans`` ×4 (~5ms of ~6–10ms WQ remiss).
# Memo by WORK_QUEUE mtime_ns; clear with factory progress cache.
_ACTIVE_OPEN_CACHE: dict[str, Any] = {"mtime_ns": None, "items": None}


def clear_active_open_items_cache() -> None:
    """Drop Active-open memo (tests + after queue heal)."""
    _ACTIVE_OPEN_CACHE["mtime_ns"] = None
    _ACTIVE_OPEN_CACHE["items"] = None
    clear_open_and_done_items_cache()


# Needle: OPEN_AND_DONE_QUEUE_MD_INDEX_SHARE_2026_09_08 — share ``_queue_md_index``
# for phased+backlog+done; memo by WQ+context mtime so remiss repeats are free.
_OPEN_DONE_CACHE: dict[str, Any] = {"key": None, "open": None, "done": None}


def clear_open_and_done_items_cache() -> None:
    """Drop open+done memo (tests + after queue heal)."""
    _OPEN_DONE_CACHE["key"] = None
    _OPEN_DONE_CACHE["open"] = None
    _OPEN_DONE_CACHE["done"] = None


def _active_open_items() -> list[str]:
    """Open Active/Phase items only — Backlog deferred must not tank executable_queue."""
    # OVERSEER_ACTIVE_OPEN_CLOSE_LANDED_2026_09_04 — Mac rsync reopens land-proofed
    # Active theater; score after close_landed so meter matches compact/dispatch.
    # ACTIVE_OPEN_WQ_MTIME_GENERATION_2026_09_08 — share one close+parse per WQ mtime.
    try:
        mtime_ns = int(auto.WORK_QUEUE_PATH.stat().st_mtime_ns)
    except OSError:
        mtime_ns = -1
    cached = _ACTIVE_OPEN_CACHE.get("items")
    if (
        cached is not None
        and _ACTIVE_OPEN_CACHE.get("mtime_ns") == mtime_ns
    ):
        return list(cached)
    wq = auto.load_work_queue_md()
    wq, _ = auto.close_landed_done_orphans(wq)
    items = _dedupe_queue_items(auto._parse_phased_work_items(wq))
    _ACTIVE_OPEN_CACHE["mtime_ns"] = mtime_ns
    _ACTIVE_OPEN_CACHE["items"] = list(items)
    return items


def _open_and_done_items() -> tuple[list[str], list[str]]:
    """All open queue items — Active, Phase, Backlog, and context remaining.

    Needle: OPEN_AND_DONE_QUEUE_MD_INDEX_SHARE_2026_09_08 — reuse
    ``_queue_md_index`` (primed by ``open_work_items``) for WQ open+Done
    instead of a second full-file walk (~0.1–0.4ms remiss theater).
    """
    try:
        wq_m = int(auto.WORK_QUEUE_PATH.stat().st_mtime_ns)
    except OSError:
        wq_m = -1
    try:
        ctx_m = int(auto.CONTEXT_PATH.stat().st_mtime_ns)
    except OSError:
        ctx_m = -1
    key = (wq_m, ctx_m)
    cached_o = _OPEN_DONE_CACHE.get("open")
    cached_d = _OPEN_DONE_CACHE.get("done")
    if (
        cached_o is not None
        and cached_d is not None
        and _OPEN_DONE_CACHE.get("key") == key
    ):
        return list(cached_o), list(cached_d)

    wq = auto.load_work_queue_md()
    idx = auto._queue_md_index(wq)
    open_items = list(idx.phased_items) + list(idx.backlog_open_items)
    ctx = auto.load_context_md()
    open_items.extend(auto.remaining_work_items(ctx))
    open_out = _dedupe_queue_items(open_items)
    done_out = _dedupe_queue_items(list(idx.done_items))
    _OPEN_DONE_CACHE["key"] = key
    _OPEN_DONE_CACHE["open"] = list(open_out)
    _OPEN_DONE_CACHE["done"] = list(done_out)
    return open_out, done_out


def _is_theater(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _THEATER_MARKERS)


def _is_factory(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _FACTORY_MARKERS)


# Needle: REGISTRY_STATS_MTIME_MEMO_2026_09_08 — factory WQ remiss re-parsed
# ``repos/registry.json`` every tick (~0.05–0.1ms JSON) while registry mtime
# was unchanged; share with open/done Active memos on the remiss path.
_REGISTRY_STATS_CACHE: dict[str, Any] = {"mtime_ns": None, "stats": None}


def clear_registry_stats_cache() -> None:
    """Drop registry stats memo (tests + after registry writes)."""
    _REGISTRY_STATS_CACHE["mtime_ns"] = None
    _REGISTRY_STATS_CACHE["stats"] = None


def _registry_stats() -> dict[str, Any]:
    """Ready/gap counts from ``repos/registry.json`` — mtime generation memo."""
    try:
        mtime_ns = int(REGISTRY_PATH.stat().st_mtime_ns) if REGISTRY_PATH.is_file() else -1
    except OSError:
        mtime_ns = -1
    cached = _REGISTRY_STATS_CACHE.get("stats")
    if cached is not None and _REGISTRY_STATS_CACHE.get("mtime_ns") == mtime_ns:
        return dict(cached)
    empty = {"total": 0, "ready": 0, "gaps": 0, "names_ready": [], "names_gap": []}
    if mtime_ns < 0 or not REGISTRY_PATH.is_file():
        _REGISTRY_STATS_CACHE["mtime_ns"] = mtime_ns
        _REGISTRY_STATS_CACHE["stats"] = dict(empty)
        return dict(empty)
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _REGISTRY_STATS_CACHE["mtime_ns"] = mtime_ns
        _REGISTRY_STATS_CACHE["stats"] = dict(empty)
        return dict(empty)
    repos = data.get("repos") if isinstance(data, dict) else []
    if not isinstance(repos, list):
        _REGISTRY_STATS_CACHE["mtime_ns"] = mtime_ns
        _REGISTRY_STATS_CACHE["stats"] = dict(empty)
        return dict(empty)
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
    stats = {
        "total": len(ready) + len(gaps),
        "ready": len(ready),
        "gaps": len(gaps),
        "names_ready": ready[:5],
        "names_gap": gaps[:5],
    }
    _REGISTRY_STATS_CACHE["mtime_ns"] = mtime_ns
    _REGISTRY_STATS_CACHE["stats"] = dict(stats)
    return stats


def _is_deferred(text: str) -> bool:
    if auto.factory_meter_mode() != "self_sufficient":
        return False
    low = text.lower()
    # Active kit-run / factory A→E is executable — never meter as deferred theater.
    if "kit-run" in low or "kit_a_to_z" in low or "[a-to-z" in low:
        return False
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


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def compute_throughput(
    *,
    state: dict[str, Any] | None = None,
    agents_board: dict[str, Any] | None = None,
    now: float | None = None,
    window_sec: float = THROUGHPUT_WINDOW_SEC,
    state_source: str | None = None,
) -> dict[str, Any]:
    """Live mass×speed signal — cycles/hour, non-noop rate, parallel busy, latency.

    Prefer hub/CLEAN peer-loop-state. When mac-offloaded, brain=CLEAN so local
    daemon-down does not look like a stalled factory.
    """
    now_ts = float(now if now is not None else time.time())
    source = state_source or ""
    if state is None:
        state, source = _load_state_with_source()
    elif not source:
        source = str(STATE_PATH)

    brain = _brain_meta()
    last = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    try:
        last_ts = float(last.get("ts") or 0)
    except (TypeError, ValueError):
        last_ts = 0.0
    last_age: float | None = (now_ts - last_ts) if last_ts > 10.0 else None

    hist_raw = state.get("cycle_history")
    hist: list[dict[str, Any]] = []
    if isinstance(hist_raw, list):
        for row in hist_raw:
            if not isinstance(row, dict):
                continue
            try:
                ts = float(row.get("ts") or 0)
            except (TypeError, ValueError):
                continue
            if ts <= 10.0:
                continue
            if (now_ts - ts) <= window_sec:
                hist.append(row)

    # If ring is empty but last_cycle is in-window, count it once.
    if not hist and last_ts > 10.0 and (now_ts - last_ts) <= window_sec:
        hist = [
            {
                "ts": last_ts,
                "noop": bool(last.get("noop")),
                "verify_ok": last.get("verify_ok") is True,
            }
        ]

    window_cycles = len(hist)
    hours = max(window_sec / 3600.0, 1.0 / 60.0)
    cycles_per_hour = window_cycles / hours
    non_noop_n = sum(1 for h in hist if not bool(h.get("noop")))
    non_noop_rate = (non_noop_n / window_cycles) if window_cycles else 0.0
    # Effective delivery rate (mass of good cycles × speed)
    non_noop_cph = non_noop_n / hours

    deltas: list[float] = []
    ts_sorted = sorted(
        float(h.get("ts") or 0) for h in hist if float(h.get("ts") or 0) > 10.0
    )
    for i in range(1, len(ts_sorted)):
        gap = ts_sorted[i] - ts_sorted[i - 1]
        if gap > 0:
            deltas.append(gap)
    median_latency = _median(deltas)

    try:
        open_active = len(_active_open_items())
    except Exception:  # noqa: BLE001
        open_active = 0

    parallel_busy: int | None = None
    parallel_target: int | None = None
    phase = ""
    if isinstance(agents_board, dict) and agents_board:
        sm = agents_board.get("summary") if isinstance(agents_board.get("summary"), dict) else {}
        try:
            parallel_busy = int(sm.get("active_agents") or 0)
        except (TypeError, ValueError):
            parallel_busy = 0
        try:
            parallel_target = int(
                agents_board.get("worker_target")
                or sm.get("total_agents")
                or 0
            )
        except (TypeError, ValueError):
            parallel_target = None
        phase = str(sm.get("phase") or "").upper()

    # mass = parallel utilization (or Active pressure when board unknown)
    if parallel_busy is not None and parallel_target and parallel_target > 0:
        mass = min(1.0, parallel_busy / float(parallel_target))
    elif open_active > 0:
        mass = min(1.0, open_active / 8.0)
    else:
        mass = 0.0
    # speed = non-noop cycles/hour vs efficient bar
    speed = min(1.0, non_noop_cph / THROUGHPUT_EFFICIENT_CPH)
    mass_speed = max(0.0, min(1.0, mass * speed if open_active > 0 else speed))

    healthy_idle = open_active == 0
    fresh_enough = last_age is not None and last_age <= THROUGHPUT_STALE_CYCLE_SEC
    if healthy_idle:
        efficient = True
        efficiency_label = "healthy idle — Active cleared; throughput optional"
    else:
        efficient = (
            non_noop_rate >= THROUGHPUT_EFFICIENT_NON_NOOP
            and non_noop_cph >= THROUGHPUT_EFFICIENT_CPH
            and (fresh_enough or window_cycles >= 2)
        )
        if efficient:
            efficiency_label = (
                f"efficient — {non_noop_cph:.1f} non-noop/h · "
                f"{non_noop_rate:.0%} non-noop · Active {open_active}"
            )
        elif non_noop_rate < THROUGHPUT_EFFICIENT_NON_NOOP:
            efficiency_label = (
                f"noop-heavy — non-noop rate {non_noop_rate:.0%} "
                f"(want ≥{THROUGHPUT_EFFICIENT_NON_NOOP:.0%})"
            )
        elif non_noop_cph < THROUGHPUT_EFFICIENT_CPH:
            efficiency_label = (
                f"slow — {non_noop_cph:.1f} non-noop/h "
                f"(want ≥{THROUGHPUT_EFFICIENT_CPH:.0f})"
            )
        else:
            efficiency_label = (
                f"stale cycle — last age {last_age:.0f}s"
                if last_age is not None
                else "no last_cycle footprint"
            )

    return {
        "cycles_per_hour": round(cycles_per_hour, 2),
        "non_noop_cycles_per_hour": round(non_noop_cph, 2),
        "non_noop_rate": round(non_noop_rate, 3),
        "open_active": open_active,
        "parallel_busy": parallel_busy,
        "parallel_target": parallel_target,
        "phase": phase or None,
        "last_cycle_age_sec": round(last_age, 1) if last_age is not None else None,
        "median_cycle_latency_sec": (
            round(median_latency, 1) if median_latency is not None else None
        ),
        "window_sec": window_sec,
        "window_cycles": window_cycles,
        "mass": round(mass, 3),
        "speed": round(speed, 3),
        "mass_speed": round(mass_speed, 3),
        "efficient": efficient,
        "efficiency_label": efficiency_label,
        "brain": brain["brain"],
        "mac_offloaded": brain["mac_offloaded"],
        "brain_note": brain["note"],
        "state_source": source,
        "as_of": now_ts,
    }


# Needle: FACTORY_PROGRESS_GENERATION_2026_09_05 — hub improve-loop + dual-research
# probe_output paid compute_factory_progress ~250–320ms every call (fp2 still ~247ms;
# peer-1 already generation-HIT ~0ms). Default-path memo on state/WQ/registry mtimes.
# FACTORY_PROGRESS_QUICK_KW_2026_09_05 — automation_team/peer_debrief pass quick=;
# without kwarg TypeError → factory_pct=None every gather.
_FACTORY_PROGRESS_CACHE: dict[str, Any] = {"key": None, "prog": None}


def clear_factory_progress_cache() -> None:
    """Drop generation memo (tests + forced remiss).

    Needle: FACTORY_CLEAR_KEEP_IMPROVE_LOG_TTL_2026_09_08 — WQ remiss / test
    ``clear_factory_progress_cache`` must not drop improve-log path TTL (L75);
    call ``clear_improve_log_path_cache`` only when namespaces move.
    """
    _FACTORY_PROGRESS_CACHE["key"] = None
    _FACTORY_PROGRESS_CACHE["prog"] = None
    clear_active_open_items_cache()
    clear_registry_stats_cache()


def _factory_progress_input_key(*, quick: bool = True) -> tuple[int, int, int, int]:
    """state + WORK_QUEUE + registry mtime_ns + quick — factory meter generation token."""

    def _ns(path: Path) -> int:
        try:
            return int(path.stat().st_mtime_ns) if path.is_file() else 0
        except OSError:
            return 0

    return (
        _ns(STATE_PATH),
        _ns(auto.WORK_QUEUE_PATH),
        _ns(REGISTRY_PATH),
        1 if quick else 0,
    )


def compute_factory_progress(
    *,
    live: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    daemons: dict[str, bool] | None = None,
    bottlenecks: list[Any] | None = None,
    quick: bool = True,
) -> FactoryProgress:
    """Score factory readiness for OSS-monster outcomes (not ASI chrome).

    Needle: FACTORY_PROGRESS_GENERATION_2026_09_05 + FACTORY_PROGRESS_QUICK_KW_2026_09_05
    hub port (efficiency L65) — dual-research gather residual.
    """
    # GenerationChangedPredicate: only memoize the default hot path. Explicit
    # live/state/daemons/bottlenecks (tests, peak persist, investigate) bypass.
    use_default_inputs = (
        live is None
        and state is None
        and daemons is None
        and bottlenecks is None
    )
    if use_default_inputs:
        cached = _FACTORY_PROGRESS_CACHE.get("prog")
        if (
            cached is not None
            and _FACTORY_PROGRESS_CACHE.get("key")
            == _factory_progress_input_key(quick=quick)
        ):
            return cached

    if live is None:
        live_state = auto.measure_live_state(quick=quick)
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
        # OVERSEER_HEALTHY_IDLE_DISPATCH_FULL_2026_09_07 — 0.95×25% + soft
        # delivery 0.85×20% pinned readiness at 96% across oversight cycles;
        # healthy idle + coding wt is full dispatch clear under COD.
        # OVERSEER_T10_08_CODING_WT_DISPATCH_2026_09_07 — Active open + coding
        # worktree under COD → ≥0.95 (was 0.85 soft-cap pinning factory at 86%).
        score = 0.95 if coding_wt.is_dir() else 0.7
        idle_active = not _active_open_items()
        if idle_active and coding_wt.is_dir():
            score = 1.0
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
    clean_brain_ev = ""
    if daemons is not None:
        hub_peer = bool(daemons.get("peer_loop"))
        improve_on = bool(daemons.get("improve_loop"))
    else:
        hub_peer = self_heal._peer_daemon_running()
        improve_on = self_heal._improve_daemon_running()
        # OVERSEER_T10_07_CLEAN_BRAIN_METER_2026_09_07 — mac-offloaded: credit
        # CLEAN systemd peer+improve; local LaunchAgents are intentionally down.
        if _mac_offloaded() and (not hub_peer or not improve_on):
            c_peer, c_improve, clean_brain_ev = _clean_peer_improve_active()
            if c_peer:
                hub_peer = True
            if c_improve:
                improve_on = True
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
        # OVERSEER_DELIVERY_RECENT_SOFT_DEFERRED_2026_09_07 — exclusive <3600
        # + display :.1f ("1.0h") scored 0.85 while soft deferred ticks were
        # current → factory flat 96% with healthy-idle dispatch 0.95.
        soft_deferred = _ft == "deferred"
        full_window_sec = 3960.0 if soft_deferred else 3600.0  # ~66m on deferred
        delivery_score = 1.0 if delivery_age <= full_window_sec else 0.85
        delivery_evidence = (
            f"recent delivery {delivery_age / 3600:.1f}h ago "
            f"(last_cycle noop={noop} verify_ok={last.get('verify_ok')}"
            + ("; soft deferred" if soft_deferred else "")
            + ")"
        )
        if delivery_age <= full_window_sec:
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
        if _mac_offloaded() and clean_brain_ev:
            peer_evidence = clean_brain_ev
        dims.append(
            _dim(
                "single_brain",
                "Single peer brain",
                1.0,
                0.15,
                f"{peer_evidence}; no dual ram-peer-loop",
            )
        )
        if _mac_offloaded():
            highlights.append(
                clean_brain_ev or "CLEAN peer+improve brain (mac-offloaded)"
            )
        else:
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
        if _mac_offloaded():
            highlights.append(
                clean_brain_ev or "CLEAN improve-loop active (mac-offloaded)"
            )
        else:
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

    tp = compute_throughput(state=state, now=now)
    # Throughput is its own meter — do not inflate factory blockers (mac-offload
    # false-negatives + empty history would spam). Surface via highlights only.
    highlights.append(
        f"Throughput [{tp.get('brain')}]: {tp.get('efficiency_label')} "
        f"(non-noop/h {tp.get('non_noop_cycles_per_hour')}, "
        f"rate {tp.get('non_noop_rate')}, Active {tp.get('open_active')})"
    )

    prog = FactoryProgress(
        pct=pct,
        raw=raw,
        label=label,
        north_star=NORTH_STAR,
        dimensions=dims,
        blockers=blockers,
        highlights=highlights,
        as_of=now,
        throughput=tp,
    )
    if use_default_inputs:
        # Re-key after possible peak write to STATE_PATH (mtime bump).
        _FACTORY_PROGRESS_CACHE["key"] = _factory_progress_input_key(quick=quick)
        _FACTORY_PROGRESS_CACHE["prog"] = prog
    return prog


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
    ]
    tp = prog.throughput if isinstance(prog.throughput, dict) else {}
    if tp:
        busy = tp.get("parallel_busy")
        target = tp.get("parallel_target")
        parallel = (
            f"{busy}/{target}"
            if busy is not None and target is not None
            else ("?" if busy is None else str(busy))
        )
        age = tp.get("last_cycle_age_sec")
        age_s = f"{age:.0f}s" if isinstance(age, (int, float)) else "—"
        lat = tp.get("median_cycle_latency_sec")
        lat_s = f"{lat:.0f}s" if isinstance(lat, (int, float)) else "—"
        lines.extend(
            [
                "## Throughput (mass × speed)",
                "",
                f"- brain=`{tp.get('brain')}` · efficient=`{tp.get('efficient')}`",
                f"- cycles/h `{tp.get('cycles_per_hour')}` · non-noop rate "
                f"`{tp.get('non_noop_rate')}` · non-noop/h `{tp.get('non_noop_cycles_per_hour')}`",
                f"- open Active `{tp.get('open_active')}` · parallel busy `{parallel}`",
                f"- last cycle age `{age_s}` · median latency `{lat_s}`",
                f"- _{tp.get('efficiency_label')}_",
                "",
            ]
        )
    lines.extend(
        [
            "## Dimensions",
            "",
        ]
    )
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
