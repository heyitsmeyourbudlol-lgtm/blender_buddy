"""GPU event triggers — temperature sensor scales work up/down for PC health."""

from __future__ import annotations

import ctypes
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import project_automation as auto

STATE_PATH = auto.CONFIG_DIR / "gpu-event-state.json"
OVERRIDE_PATH = auto.CONFIG_DIR / "gpu-sustain-override.json"

MODES = ("hold", "boost", "pressure", "emergency")

_last_good_util: float | None = None
_last_good_util_ts: float = 0.0
_LAST_GOOD_UTIL_PATH = auto.CONFIG_DIR / "gpu-last-good-util.json"


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("gpu_events")
    return raw if isinstance(raw, dict) else {}


def _load_persisted_last_good() -> None:
    """Cross-process stale util — in-memory alone false-emergency between poll ticks."""
    global _last_good_util, _last_good_util_ts
    if _last_good_util is not None:
        return
    try:
        if not _LAST_GOOD_UTIL_PATH.is_file():
            return
        data = json.loads(_LAST_GOOD_UTIL_PATH.read_text())
        util = float(data.get("util") or 0)
        ts = float(data.get("ts") or 0)
        if util > 0 and ts > 0:
            _last_good_util = util
            _last_good_util_ts = ts
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return


def _persist_last_good(util: float, ts: float) -> None:
    try:
        _LAST_GOOD_UTIL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAST_GOOD_UTIL_PATH.write_text(json.dumps({"util": util, "ts": ts}))
    except OSError:
        pass


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def max_util_pct() -> float:
    """Soft util ceiling when thermal scaling is off (kept as fallback)."""
    try:
        return float(_cfg().get("max_util_pct") or 95)
    except (TypeError, ValueError):
        return 95.0


def thermal_enabled() -> bool:
    return bool(_cfg().get("thermal_enabled", True))


def temp_cool_c() -> float:
    try:
        # GB10 steady embed sits ~68–76C — default 55C was permanently soft-throttling.
        return float(_cfg().get("temp_cool_c") or 70)
    except (TypeError, ValueError):
        return 70.0


def temp_warm_c() -> float:
    try:
        return float(_cfg().get("temp_warm_c") or 76)
    except (TypeError, ValueError):
        return 76.0


def temp_hot_c() -> float:
    try:
        return float(_cfg().get("temp_hot_c") or 86)
    except (TypeError, ValueError):
        return 86.0


def temp_critical_c() -> float:
    try:
        return float(_cfg().get("temp_critical_c") or 92)
    except (TypeError, ValueError):
        return 92.0


def thermal_gamma() -> float:
    """Curve steepness between cool→hot (1=linear, >1 stays high longer then drops)."""
    try:
        return max(0.5, float(_cfg().get("thermal_gamma") or 1.8))
    except (TypeError, ValueError):
        return 1.8


def thermal_min_scale() -> float:
    """Floor scale at hot band before critical (not zero until critical)."""
    try:
        # Allow up to 0.65 so productive Mamba keep ~65% work at steady 70–78C
        # instead of collapsing to 0.15 and boom-busting util into pressure.
        return max(0.0, min(0.65, float(_cfg().get("thermal_min_scale") or 0.35)))
    except (TypeError, ValueError):
        return 0.35


def target_util_pct() -> float:
    try:
        target = float(_cfg().get("target_util_pct") or 80)
    except (TypeError, ValueError):
        target = 80.0
    return min(target, max_util_pct())


def boost_util_pct() -> float:
    try:
        return float(_cfg().get("boost_util_pct") or target_util_pct())
    except (TypeError, ValueError):
        return target_util_pct()


def pressure_util_pct() -> float:
    try:
        return float(_cfg().get("pressure_util_pct") or 60)
    except (TypeError, ValueError):
        return 60.0


def emergency_util_pct() -> float:
    try:
        return float(_cfg().get("emergency_util_pct") or 40)
    except (TypeError, ValueError):
        return 40.0


def cursor_agent_enabled() -> bool:
    # Hard off unless DGX_ALLOW_CURSOR_AGENT=1 — local.json races re-enable
    # cursor_agent:true and INFRA storms restart gpu_compute mid-embed.
    import os

    if os.environ.get("DGX_ALLOW_CURSOR_AGENT", "").strip().lower() not in ("1", "true", "yes"):
        return False
    return bool(_cfg().get("cursor_agent", False))


def cursor_agent_cooldown_sec() -> float:
    try:
        return max(60.0, float(_cfg().get("cursor_agent_cooldown_sec") or 300))
    except (TypeError, ValueError):
        return 300.0


def stale_util_sec() -> float:
    try:
        return max(3.0, float(_cfg().get("stale_util_sec") or 20))
    except (TypeError, ValueError):
        return 20.0


def util_proxy_enabled() -> bool:
    return bool(_cfg().get("util_proxy_enabled", True))


def util_proxy_power_idle_w() -> float:
    try:
        # GB10 true idle sits ~13.5–14.5W. Default 15 required ~18W+ and missed
        # productive teacher bursts at 17–21W (false boost/emergency). 14.5
        # credits real embed work without greenwashing pure 14W idle.
        return max(5.0, float(_cfg().get("util_proxy_power_idle_w") or 14.5))
    except (TypeError, ValueError):
        return 14.5


def util_proxy_power_loaded_w() -> float:
    try:
        # GB10 teacher bursts often land ~17–28W; map loaded nearer that band.
        return max(util_proxy_power_idle_w() + 5.0, float(_cfg().get("util_proxy_power_loaded_w") or 24))
    except (TypeError, ValueError):
        return 24.0


def _parse_vram_mib(snap: dict[str, Any]) -> float:
    raw = snap.get("gpu_mem_mib")
    if raw is None:
        return 0.0
    text = str(raw).strip().strip("[]")
    if not text or text.upper() == "N/A":
        return float(snap.get("gpu_compute_vram_mib") or 0)
    try:
        return float(text.split()[0])
    except (TypeError, ValueError):
        return 0.0


def _compute_process_vram_mib() -> float:
    """Sum compute-process VRAM when driver reports memory.used as N/A (GB10)."""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=used_gpu_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return 0.0
        total = 0.0
        for line in proc.stdout.strip().splitlines():
            part = line.strip().split()[0] if line.strip() else "0"
            if part.upper() == "[N/A]":
                continue
            try:
                total += float(part)
            except ValueError:
                continue
        return total
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0.0


def _gpu_compute_status_paths() -> list[Path]:
    """Prefer CONFIG_DIR, then sibling automation namespaces (stale dual-write)."""
    seen: set[str] = set()
    out: list[Path] = []
    for path in (
        auto.CONFIG_DIR / "gpu-compute-status.json",
        Path.home() / ".config" / "automation-hub" / "gpu-compute-status.json",
        Path.home() / ".config" / "automation" / "gpu-compute-status.json",
    ):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _gpu_compute_status_path() -> Path:
    return _gpu_compute_status_paths()[0]


def _status_heartbeat_fresh(*, max_age_sec: float = 90.0) -> bool:
    """False when forever worker stopped updating status (sqlite lock hang)."""
    now = time.time()
    for path in _gpu_compute_status_paths():
        if not path.is_file():
            continue
        try:
            age = now - path.stat().st_mtime
            if age <= max_age_sec:
                return True
            st = json.loads(path.read_text())
            updated = float((st or {}).get("updated_at") or 0)
            if updated > 0 and (now - updated) <= max_age_sec:
                return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return False


def embed_productive() -> bool:
    """True when gpu_compute has a resident CUDA Mamba (or is actively embedding).

    Never import ``dgx_gpu_compute`` here — that module eagerly loads torch/mamba
    (~490 MB RSS) into improve/peer via ``resource_priority`` → ``snapshot``.
    Read the status JSON the gpu_compute daemon persists instead.

    Needle: pending chunks alone used to credit 80% effective util while the
    forever worker was hung on HF CloudFront CLOSE-WAIT with mamba unloaded and
    nvidia-smi at 0% — permanent false ``hold`` / ``development_allowed``.
    Require loaded model or CUDA RSS; pending-only is warming, not productive.

    Stale status + idle power means the worker is hung (usually sqlite lock) —
    do not treat reserved VRAM alone as productive.
    """
    if not _gpu_compute_active():
        return False
    fresh = _status_heartbeat_fresh()
    vram = _compute_process_vram_mib()
    # GB10 often reports memory.used N/A — compute-app VRAM is the live signal.
    if fresh and vram >= 1500:
        return True
    # Teacher mid-flight can stall status writes 1–3min (sqlite COUNT) while
    # nvidia-smi still shows 15–35GB compute VRAM — do not false-emergency.
    if vram >= 8000 and _status_heartbeat_fresh(max_age_sec=180.0):
        return True
    if vram >= 4000 and _recent_embed_activity(max_age_sec=120.0):
        return True
    saw_status = False
    try:
        for path in _gpu_compute_status_paths():
            if not path.is_file():
                continue
            saw_status = True
            try:
                st = json.loads(path.read_text())
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if not isinstance(st, dict):
                continue
            if st.get("db_error") and not fresh:
                continue
            # Recent productive embed cycle — teacher mid-flight even if VRAM dipped.
            try:
                last_embed = float(st.get("last_embed_ts") or 0)
            except (TypeError, ValueError):
                last_embed = 0.0
            if last_embed > 0 and time.time() - last_embed < 120.0:
                return True
            mamba = st.get("mamba") or {}
            cuda = st.get("cuda") or {}
            alloc = float(cuda.get("memory_allocated_mb") or 0)
            reserved = float(cuda.get("memory_reserved_mb") or 0)
            loaded = bool(mamba.get("loaded")) or alloc > 128
            pending = int(st.get("chunks_pending") or 0)
            # Needle: stale status loaded=true + 0 CUDA after worker restart
            # greenwashed hold while nvidia-smi had no compute apps. Require
            # live VRAM, reserved working set, or a recent embed timestamp.
            live_cuda = vram >= 1500 or alloc >= 128 or reserved >= 1024
            if loaded and fresh and live_cuda:
                return True
            # GB10 teacher preload: status may show loaded=true with low allocated
            # for 1–3min before first encode — still productive if VRAM/process live.
            if fresh and pending > 0 and loaded and (live_cuda or vram >= 800):
                return True
            if fresh and pending >= 1000 and live_cuda and _gpu_compute_process_active():
                return True
        # Daemon up but no loaded status in any namespace — warming / hung preload.
        return False if saw_status else False
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _recent_embed_activity(*, max_age_sec: float = 30.0) -> bool:
    """True when forever worker stored embeddings within max_age_sec."""
    try:
        for path in _gpu_compute_status_paths():
            if not path.is_file():
                continue
            try:
                st = json.loads(path.read_text())
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if not isinstance(st, dict):
                continue
            try:
                last_embed = float(st.get("last_embed_ts") or 0)
            except (TypeError, ValueError):
                continue
            if last_embed > 0 and time.time() - last_embed < max_age_sec:
                return True
    except (OSError, ValueError, TypeError):
        return False
    return False


def effective_util_pct(*, snap: dict[str, Any] | None = None) -> float:
    """Raw nvidia/NVML util, with GB10 power+VRAM proxy when driver reports 0%."""
    snap = dict(snap or gpu_snapshot())
    raw = float(snap.get("gpu_util_pct") or 0)
    proxy = raw
    # Power/VRAM proxy only when raw is below emergency — real samples above that
    # are trustworthy for magnitude. Do NOT early-return before productive-embed
    # credit (needle: 41–59% raw → permanent pressure while Mamba is resident).
    if (
        raw < emergency_util_pct()
        and util_proxy_enabled()
        and not snap.get("gpu_unavailable")
    ):
        vram_mib = _parse_vram_mib(snap)
        if vram_mib <= 0:
            vram_mib = _compute_process_vram_mib()
            if vram_mib > 0:
                snap["gpu_compute_vram_mib"] = vram_mib
        power = float(snap.get("gpu_power_w") or 0)
        idle_w = util_proxy_power_idle_w()
        loaded_w = util_proxy_power_loaded_w()
        if power > idle_w and loaded_w > idle_w:
            frac = min(1.0, max(0.0, (power - idle_w) / (loaded_w - idle_w)))
            proxy = max(proxy, frac * target_util_pct())
        # VRAM alone ≠ busy — resident Mamba reserves ~13GB while between bursts.
        # Only lift proxy from VRAM when power also shows real work above idle.
        if power > idle_w + 4.0:
            if vram_mib >= 8000:
                proxy = max(proxy, target_util_pct())
            elif vram_mib >= 1500:
                proxy = max(proxy, pressure_util_pct())
            elif vram_mib >= 300:
                proxy = max(proxy, emergency_util_pct() + 5.0)
    # Productive resident embed must not read as emergency/pressure on GB10
    # mid-burst nvidia-smi dips — but stale VRAM alone (hung sqlite, 15W, 0%)
    # must NOT credit to boost target. Require recent embed OR elevated power.
    if embed_productive() and proxy < boost_util_pct() and (
        _status_heartbeat_fresh(max_age_sec=180.0)
        or (_gpu_compute_process_active() and _compute_process_vram_mib() >= 1500)
    ):
        power = float(snap.get("gpu_power_w") or 0)
        idle_w = util_proxy_power_idle_w()
        vram_mib = float(snap.get("gpu_compute_vram_mib") or 0) or _parse_vram_mib(snap)
        if vram_mib <= 0:
            vram_mib = _compute_process_vram_mib()
        reserved_mb = 0.0
        try:
            for path in _gpu_compute_status_paths():
                if not path.is_file():
                    continue
                st = json.loads(path.read_text())
                if isinstance(st, dict):
                    reserved_mb = max(
                        reserved_mb,
                        float((st.get("cuda") or {}).get("memory_reserved_mb") or 0),
                    )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            reserved_mb = 0.0
        recent = _recent_embed_activity(max_age_sec=180.0)
        recent_hot = _recent_embed_activity(max_age_sec=120.0)
        # Needle: GB10 teacher often sits 12–16W with 0% SMI between batches
        # (and during brief folio_wait) while still draining 70k–126k chunks.
        # Credit target when embeds are fresh + teacher working set is resident
        # so mode→hold (not permanent boost/emergency beep).
        # Counter-needle: status reserved_mb alone after worker death greenwashed
        # eff=80 with apps=[] / 5W idle (false GREEN_STABLE). Prefer live VRAM.
        live_vram = float(vram_mib or 0) or _compute_process_vram_mib()
        proc_live = _gpu_compute_process_active()
        if not proc_live and live_vram < 300:
            teacher_set = 0.0
        else:
            teacher_set = max(live_vram, reserved_mb if proc_live else 0.0)
        # Mid-encode (status mtime stale >90s): still leave emergency when the
        # forever worker holds teacher VRAM (needle 2026-09-08 fp~100 + beep).
        if proc_live and teacher_set >= 1500 and (recent or recent_hot or live_vram >= 1500):
            proxy = max(
                proxy,
                target_util_pct() if (recent_hot or teacher_set >= 8000) else boost_util_pct(),
            )
        elif recent_hot and teacher_set >= 1500:
            proxy = max(proxy, target_util_pct())
        elif recent and teacher_set >= 8000:
            proxy = max(proxy, target_util_pct())
        elif recent and proc_live and (
            power > idle_w + 1.5
            or raw >= max(15.0, emergency_util_pct() * 0.4)
        ):
            proxy = max(proxy, boost_util_pct())
        elif recent and teacher_set >= 1500 and power > idle_w - 0.5:
            proxy = max(proxy, boost_util_pct())
        elif recent and teacher_set >= 1500:
            proxy = max(proxy, pressure_util_pct())
        elif teacher_set >= 300 and raw >= 10:
            # Mid-burst sample: at least leave pressure band, not emergency.
            proxy = max(proxy, pressure_util_pct())
        elif (
            recent
            and embed_productive()
            and proc_live
            and teacher_set >= 1500
        ):
            # Only leave emergency when embeds are actually landing — never
            # greenwash preload/idle (needle: 0%/14W + loaded status → false
            # hold / development_allowed while last_embed_ts is null).
            proxy = max(proxy, pressure_util_pct())
    return min(proxy, max_util_pct())


def throttle_util_pct(*, snap: dict[str, Any] | None = None) -> float:
    """Effective util throttle — derived from temperature when thermal sensor is on."""
    if thermal_enabled():
        return effective_max_util_pct(snap=snap)
    try:
        raw = _cfg().get("throttle_util_pct")
        if raw is None:
            return max_util_pct()
        return min(float(raw), max_util_pct())
    except (TypeError, ValueError):
        return max_util_pct()


def thermal_scale(*, snap: dict[str, Any] | None = None, temp_c: float | None = None) -> float:
    """Scale factor 0..1 from GPU temperature for PC health.

    Formula (piecewise):
      T ≤ cool     → 1.0  (full throughput)
      cool < T < hot → 1 - ((T-cool)/(hot-cool))^γ   (smooth pullback)
      hot ≤ T < crit → min_scale * (crit-T)/(crit-hot)  (aggressive cool-down)
      T ≥ crit     → 0.0  (hard stop)

    Raises throughput when cool; shrinks work as temp climbs.
    """
    if not thermal_enabled():
        return 1.0
    if temp_c is None:
        snap = snap or gpu_snapshot()
        try:
            temp_c = float(snap.get("gpu_temp_c") or 0)
        except (TypeError, ValueError):
            temp_c = 0.0
    if temp_c <= 0:
        return 1.0  # unknown sensor → don't starve the GPU

    cool = temp_cool_c()
    hot = max(cool + 1.0, temp_hot_c())
    crit = max(hot + 1.0, temp_critical_c())
    gamma = thermal_gamma()
    floor = thermal_min_scale()

    if temp_c <= cool:
        return 1.0
    if temp_c >= crit:
        return 0.0
    if temp_c < hot:
        x = (temp_c - cool) / (hot - cool)
        return max(floor, 1.0 - (x**gamma))
    # hot → critical band
    y = (crit - temp_c) / (crit - hot)
    return max(0.0, floor * y)


def effective_max_util_pct(*, snap: dict[str, Any] | None = None) -> float:
    """Util ceiling that rises when cool and falls when hot."""
    try:
        floor_util = float(_cfg().get("thermal_min_util_pct") or 25)
    except (TypeError, ValueError):
        floor_util = 25.0
    ceiling = max_util_pct()
    scale = thermal_scale(snap=snap)
    return floor_util + (ceiling - floor_util) * scale


def over_max(*, snap: dict[str, Any] | None = None) -> bool:
    snap = snap or gpu_snapshot()
    if thermal_enabled():
        try:
            temp = float(snap.get("gpu_temp_c") or 0)
        except (TypeError, ValueError):
            temp = 0.0
        if temp >= temp_critical_c():
            return True
        return thermal_scale(snap=snap, temp_c=temp) <= 0.0
    util = float(snap.get("gpu_util_pct") or 0)
    return util >= max_util_pct()


def synthetic_sustain_enabled() -> bool:
    return bool(_cfg().get("synthetic_sustain_enabled", False))


def sustain_params(mode: str | None = None, *, snap: dict[str, Any] | None = None) -> dict[str, Any]:
    """Runtime sustain knobs per mode — written to override file for gpu_compute."""
    if snap is None:
        snap = gpu_snapshot()
    if mode is None:
        mode = gpu_mode(snap=snap)
    util = effective_util_pct(snap=snap)
    base = _compute_defaults()
    profiles: dict[str, dict[str, Any]] = {
        "hold": {
            "sustain_sec": base.get("gpu_sustain_sec", 3),
            "sustain_dim": base.get("gpu_sustain_dim", 6144),
            "embed_batch_mult": 1.0,
            "interval_sec": base.get("gpu_embed_interval_sec", 0.5),
            "sustain_passes": 1,
            "embed_burst_sec": float(_compute_defaults().get("embed_burst_sec") or 0),
        },
        "boost": {
            "sustain_sec": max(6.0, float(_cfg().get("boost_sustain_sec") or 8)),
            "sustain_dim": int(_cfg().get("boost_sustain_dim") or 7168),
            "embed_batch_mult": float(_cfg().get("boost_embed_batch_mult") or 1.25),
            "interval_sec": float(_cfg().get("boost_interval_sec") or 0.25),
            "sustain_passes": int(_cfg().get("boost_sustain_passes") or 2),
            "embed_burst_sec": float(_cfg().get("boost_embed_burst_sec") or 30),
        },
        "pressure": {
            "sustain_sec": max(10.0, float(_cfg().get("pressure_sustain_sec") or 14)),
            "sustain_dim": int(_cfg().get("pressure_sustain_dim") or 8192),
            "embed_batch_mult": float(_cfg().get("pressure_embed_batch_mult") or 1.5),
            "interval_sec": float(_cfg().get("pressure_interval_sec") or 0.15),
            "sustain_passes": int(_cfg().get("pressure_sustain_passes") or 3),
            "embed_burst_sec": float(_cfg().get("pressure_embed_burst_sec") or 45),
        },
        "emergency": {
            "sustain_sec": max(15.0, float(_cfg().get("emergency_sustain_sec") or 22)),
            "sustain_dim": int(_cfg().get("emergency_sustain_dim") or 8192),
            "embed_batch_mult": float(_cfg().get("emergency_embed_batch_mult") or 1.0),
            "interval_sec": float(_cfg().get("emergency_interval_sec") or 0.02),
            "sustain_passes": int(_cfg().get("emergency_sustain_passes") or 4),
            # 120s left GB10 in 0% sample holes between bursts; prefer 180s.
            "embed_burst_sec": float(_cfg().get("emergency_embed_burst_sec") or 180),
        },
    }
    params = dict(profiles.get(mode, profiles["hold"]))
    if not synthetic_sustain_enabled():
        params["sustain_passes"] = 0
        # Productive Mamba only — never schedule GEMM when synthetic is off.
        params["sustain_sec"] = 0.0

    scale = thermal_scale(snap=snap) if thermal_enabled() else 1.0
    eff_max = throttle_util_pct(snap=snap)
    params["thermal_scale"] = round(scale, 3)
    params["effective_max_util_pct"] = round(eff_max, 1)

    if scale <= 0.0 or over_max(snap=snap):
        # Critical thermal — stop synthetic GEMM. Keep a tiny productive drip when
        # Mamba is already resident so status stays loaded and backlog still drains.
        params["sustain_passes"] = 0
        params["sustain_sec"] = 0.0
        params["throttled"] = True
        params["thermal_stop"] = True
        if embed_productive():
            params["embed_burst_sec"] = 2.0
            params["embed_batch_mult"] = 0.25
        else:
            params["embed_burst_sec"] = 0.0
            params["embed_batch_mult"] = 0.0
    else:
        # Scale work intensity with temperature (cool → more, hot → less).
        params["sustain_sec"] = max(0.0, float(params.get("sustain_sec") or 0) * scale)
        params["embed_burst_sec"] = max(0.0, float(params.get("embed_burst_sec") or 0) * scale)
        params["embed_batch_mult"] = float(params.get("embed_batch_mult") or 1.0) * (0.35 + 0.65 * scale)
        params["sustain_passes"] = max(0, int(round(float(params.get("sustain_passes") or 0) * scale)))
        # Stretch interval when warm (slower cycles).
        params["interval_sec"] = float(params.get("interval_sec") or 0.5) / max(0.2, scale)
        # Soft util guard must use LIVE nvidia util — never stale last-good.
        # Needle: 0% gap → util_stale credits 96% → throttle cuts burst/batch →
        # boom-bust 0%↔91% while mamba-2.8b is mid-drain (false under-util beep).
        # effective_util credits embed_productive up to boost and must not gate.
        live_util = float(snap.get("gpu_util_pct") or 0)
        util_is_stale = bool(snap.get("util_stale"))
        if (not util_is_stale) and live_util >= eff_max:
            params["sustain_passes"] = 0
            params["sustain_sec"] = max(0.0, float(params.get("sustain_sec") or 0) * 0.25)
            # Keep a thermal-scaled floor burst so Mamba stays resident-busy.
            floor_burst = max(3.0, 8.0 * scale)
            params["embed_burst_sec"] = max(
                floor_burst, float(params.get("embed_burst_sec") or 0) * 0.35
            )
            params["embed_batch_mult"] = min(float(params.get("embed_batch_mult") or 1.0), 0.65)
            params["throttled"] = True
        # Hold / productive floor — keep Mamba embedding between SMI samples.
        if mode in ("hold", "boost", "pressure", "emergency") and not params.get("thermal_stop"):
            floor = float(base.get("embed_burst_sec") or 20) * max(0.45, scale)
            # Emergency/pressure: long productive bursts close 0% sample holes.
            if mode in ("emergency", "pressure"):
                floor = max(floor, 120.0 * max(0.5, scale))
                ceiling = 200.0
            else:
                ceiling = 90.0 if util_is_stale or embed_productive() else 48.0
            params["embed_burst_sec"] = max(
                float(params.get("embed_burst_sec") or 0), min(ceiling, floor)
            )
            # Tighten cycle gap so raw util does not drop to 0% between bursts.
            params["interval_sec"] = min(float(params.get("interval_sec") or 0.5), 0.05)
            if (util_is_stale or mode in ("emergency", "pressure")) and embed_productive():
                # Never force ×2 — 2.8b-4bit OOM-kills at batch 768–1280 (needle 2026-09-07).
                params["embed_batch_mult"] = min(
                    max(float(params.get("embed_batch_mult") or 1.0), 1.0), 1.0
                )
                params["throttled"] = False

    # Modest base — floor 512×emergency forced 768–1280 and SIGKILL'd forever worker.
    base_batch = max(32, min(int(base.get("gpu_embed_batch") or 64), 128))
    params["embed_batch"] = max(8, int(base_batch * float(params.get("embed_batch_mult") or 1.0)))
    # Hard cap for unified GB10 teacher encode.
    try:
        prod_max = int(_cfg().get("productive_embed_batch_max") or 96)
    except (TypeError, ValueError):
        prod_max = 96
    params["embed_batch"] = min(int(params["embed_batch"]), max(32, min(prod_max, 128)))
    if mode in ("emergency", "pressure", "boost"):
        params["embed_batch"] = min(int(params["embed_batch"]), 48)
    return params


def _compute_defaults() -> dict[str, Any]:
    raw = auto.CFG.get("dgx_compute")
    return raw if isinstance(raw, dict) else {}


_NVML_INITED = False
_NVML_TEMP_GPU = 0


class _NvmlUtilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


def _nvml_snapshot() -> dict[str, Any] | None:
    """Fast NVML ctypes path — avoids nvidia-smi fork (~20–130ms/call)."""
    global _NVML_INITED
    try:
        nvml = ctypes.CDLL("libnvidia-ml.so.1")
    except OSError:
        return None

    init_rc = nvml.nvmlInit()
    if init_rc not in (0, 999):
        return None
    _NVML_INITED = True

    handle = ctypes.c_void_p()
    if nvml.nvmlDeviceGetHandleByIndex(0, ctypes.byref(handle)) != 0:
        return None

    util = _NvmlUtilization()
    if nvml.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(util)) != 0:
        return None

    power_mw = ctypes.c_uint()
    nvml.nvmlDeviceGetPowerUsage(handle, ctypes.byref(power_mw))

    mem = _NvmlMemory()
    nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem))

    temp_c = ctypes.c_uint()
    nvml.nvmlDeviceGetTemperature(handle, _NVML_TEMP_GPU, ctypes.byref(temp_c))

    return {
        "gpu_util_pct": float(util.gpu),
        "gpu_power_w": round(float(power_mw.value) / 1000.0, 2),
        "gpu_mem_mib": str(int(mem.used // (1024 * 1024))),
        "gpu_temp_c": float(temp_c.value),
        "gpu_unavailable": False,
    }


def _apply_util_stale(snap: dict[str, Any]) -> dict[str, Any]:
    global _last_good_util, _last_good_util_ts
    _load_persisted_last_good()
    util = float(snap.get("gpu_util_pct") or 0.0)
    now = time.time()
    stale = stale_util_sec()
    # Productive mid-burst dips: also credit last-good when power is up but
    # nvidia-smi sampled a 0% gap (GB10 between Mamba batches).
    power = float(snap.get("gpu_power_w") or 0.0)
    # Only credit last-good across sample gaps when power shows real work.
    # Idle power + stale last-good greenwashed 0% → false hold / development_allowed
    # while forever worker drained light student crumbs (needle: 14W forever).
    # Resident VRAM / heartbeat alone is NOT enough — require recent embed or
    # power above idle (hung folio_wait still has 31GB + fresh status JSON).
    recent = _recent_embed_activity(max_age_sec=45.0)
    productive_gap = (
        embed_productive()
        and _status_heartbeat_fresh(max_age_sec=45.0)
        and (recent or power > util_proxy_power_idle_w() + 2.0)
    )
    if (
        util <= 0
        and _last_good_util is not None
        and now - _last_good_util_ts < stale
        and (power > util_proxy_power_idle_w() + 2.0 or productive_gap)
    ):
        snap = dict(snap)
        snap["gpu_util_pct"] = _last_good_util
        snap["util_stale"] = True
    elif util > 0:
        _last_good_util = util
        _last_good_util_ts = now
        _persist_last_good(util, now)
    elif util <= 0 and power <= util_proxy_power_idle_w() + 2.0 and not recent:
        # Clear stale credit when truly idle — force emergency/boost path.
        snap = dict(snap)
        snap["util_stale"] = False
        _last_good_util = None
        _last_good_util_ts = 0.0
    return snap


def _gpu_snapshot_smi() -> dict[str, Any]:
    proc = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,power.draw,memory.used,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=8.0,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"gpu_util_pct": 0.0, "gpu_unavailable": True}
    parts = [p.strip() for p in proc.stdout.strip().split(",")]
    util = float(parts[0]) if parts else 0.0
    snap: dict[str, Any] = {
        "gpu_util_pct": util,
        "gpu_power_w": float(parts[1]) if len(parts) > 1 else 0.0,
        "gpu_mem_mib": parts[2] if len(parts) > 2 else "0",
        "gpu_temp_c": float(parts[3]) if len(parts) > 3 else 0.0,
        "gpu_unavailable": False,
    }
    return _apply_util_stale(snap)


def gpu_snapshot() -> dict[str, Any]:
    global _last_good_util, _last_good_util_ts
    try:
        snap = _nvml_snapshot()
        if snap is not None:
            return _apply_util_stale(snap)
        return _gpu_snapshot_smi()
    except (OSError, ValueError, subprocess.TimeoutExpired, ctypes.ArgumentError):
        now = time.time()
        if _last_good_util is not None and now - _last_good_util_ts < stale_util_sec():
            return {
                "gpu_util_pct": _last_good_util,
                "gpu_power_w": 0.0,
                "gpu_mem_mib": "[N/A]",
                "gpu_temp_c": 0.0,
                "gpu_unavailable": False,
                "util_stale": True,
            }
        return {"gpu_util_pct": 0.0, "gpu_unavailable": True}


def gpu_unavailable(*, snap: dict[str, Any] | None = None) -> bool:
    """True when nvidia-smi is missing — Mac/offload hosts must not beep emergency."""
    return bool((snap or gpu_snapshot()).get("gpu_unavailable"))


def gpu_mode(*, snap: dict[str, Any] | None = None) -> str:
    if not enabled():
        return "hold"
    snap = snap or gpu_snapshot()
    if gpu_unavailable(snap=snap):
        return "hold"
    util = effective_util_pct(snap=snap)
    scale = thermal_scale(snap=snap) if thermal_enabled() else 1.0
    # Critical / zero scale → hold (cool down), never boost.
    if scale <= 0.05 or over_max(snap=snap):
        return "hold"
    power = float(snap.get("gpu_power_w") or 0)
    raw = float(snap.get("gpu_util_pct") or 0)
    idle_w = util_proxy_power_idle_w()
    # Resident VRAM alone is NOT working — needle: 25GB reserved + 14W + 0% was
    # permanently hold/green while forever worker sat between bursts.
    # GB10 Mamba-2.8b-4bit often stays ~14–21W while nvidia-smi flickers 0%
    # between batches — treat a fresh embed as working even at idle power.
    recent = _recent_embed_activity(max_age_sec=90.0)
    recent_hot = _recent_embed_activity(max_age_sec=45.0)
    working = (
        power > idle_w + 2.0
        or raw >= max(15.0, emergency_util_pct() * 0.35)
        or (embed_productive() and recent_hot)
        or (embed_productive() and recent and power > idle_w - 1.0)
        or (embed_productive() and recent)
    )
    # Never emergency while productive embed is mid-flight (false beep → INFRA
    # restart unloads 2.8b mid-queue). Require recent_hot — loaded-only must
    # still beep emergency until first encode lands.
    if embed_productive() and recent_hot and scale >= 0.35:
        if util >= boost_util_pct() - 1.0 or raw >= target_util_pct() - 10.0:
            return "hold"
        # Fresh productive drain: credit hold when effective util already at target
        # (proxy), else boost — never emergency on GB10 0%/14W sample gaps.
        return "hold" if util >= boost_util_pct() - 1.0 else "boost"
    # Resident + actively embedding near target → hold. Idle VRAM alone must
    # fall through to boost/pressure so we keep draining the queue.
    if embed_productive() and working and recent and util >= boost_util_pct() - 1.0:
        return "hold"
    # Power+resident: even when effective util dips (status race / sample gap),
    # stay hold/boost — never emergency restart that unloads CUDA Mamba.
    if embed_productive() and working and recent:
        if scale < 0.35:
            return "hold"
        return "hold" if util >= boost_util_pct() - 1.0 else "boost"
    # When warm, prefer hold over aggressive boost even if util is low.
    if scale < 0.4:
        if util < emergency_util_pct() * scale:
            return "pressure"
        return "hold"
    if util < emergency_util_pct():
        return "emergency"
    if util < pressure_util_pct():
        return "pressure"
    if util < boost_util_pct() and scale >= 0.6:
        return "boost"
    return "hold"


def at_target(*, snap: dict[str, Any] | None = None) -> bool:
    snap = snap or gpu_snapshot()
    raw = float(snap.get("gpu_util_pct") or 0)
    util = effective_util_pct(snap=snap)
    slack = float(_cfg().get("target_slack_pct") or 5)
    # Require real samples near target — productive-only must not greenwash 0%.
    if raw >= target_util_pct() - slack:
        return True
    if util >= target_util_pct() - slack and raw >= pressure_util_pct():
        return True
    # GB10 nvidia-smi often samples 0% between Mamba batches while the forever
    # worker is mid-burst. Require a *recent* embed — loaded+pending alone must
    # not greenwash at_target (needle: preload → false hold @ 0%/14W).
    if (
        embed_productive()
        and util >= target_util_pct() - slack
        and _recent_embed_activity(max_age_sec=45.0)
        and (
            float(snap.get("gpu_power_w") or 0) > util_proxy_power_idle_w() + 1.0
            or raw >= max(10.0, emergency_util_pct() * 0.25)
        )
    ):
        return True
    return False


def _load_state() -> dict[str, Any]:
    try:
        if STATE_PATH.is_file():
            return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def write_sustain_override(*, mode: str | None = None) -> dict[str, Any]:
    params = sustain_params(mode)
    payload = {
        "mode": mode or gpu_mode(),
        "updated_at": time.time(),
        **params,
    }
    try:
        OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDE_PATH.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass
    return payload


def load_sustain_override() -> dict[str, Any]:
    try:
        if OVERRIDE_PATH.is_file():
            return json.loads(OVERRIDE_PATH.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def snapshot(*, snap: dict[str, Any] | None = None) -> dict[str, Any]:
    if snap is None:
        snap = gpu_snapshot()
    mode = gpu_mode(snap=snap)
    util = float(snap.get("gpu_util_pct") or 0)
    eff_util = effective_util_pct(snap=snap)
    return {
        "mode": mode,
        "gpu_util_pct": util,
        "effective_util_pct": round(eff_util, 1),
        "embed_productive": embed_productive(),
        "gpu_temp_c": float(snap.get("gpu_temp_c") or 0),
        "thermal_enabled": thermal_enabled(),
        "thermal_scale": round(thermal_scale(snap=snap), 3),
        "temp_cool_c": temp_cool_c(),
        "temp_hot_c": temp_hot_c(),
        "temp_critical_c": temp_critical_c(),
        "max_util_pct": max_util_pct(),
        "effective_max_util_pct": round(effective_max_util_pct(snap=snap), 1),
        "target_util_pct": target_util_pct(),
        "boost_util_pct": boost_util_pct(),
        "pressure_util_pct": pressure_util_pct(),
        "emergency_util_pct": emergency_util_pct(),
        "throttle_util_pct": round(throttle_util_pct(snap=snap), 1),
        "over_max": over_max(snap=snap),
        "at_target": at_target(snap=snap),
        "sustain": sustain_params(mode, snap=snap),
        **{k: v for k, v in snap.items() if k not in ("gpu_util_pct", "gpu_temp_c")},
    }


def _build_gpu_agent_prompt(*, mode: str, snap: dict[str, Any], prev_mode: str | None) -> str:
    return f"""# GPU event — {mode.upper()} mode

GPU utilization **{snap.get('gpu_util_pct', 0):.0f}%** (target **{target_util_pct():.0f}%** steady).
Previous mode: `{prev_mode or 'none'}` → `{mode}`.

## Event thresholds (all modes steer toward ~{target_util_pct():.0f}%)
- **hold** — util ≥ {boost_util_pct():.0f}%: maintain embed + light sustain
- **boost** — util < {boost_util_pct():.0f}%: longer GEMM sustain + larger embed batches
- **pressure** — util < {pressure_util_pct():.0f}%: aggressive sustain toward {target_util_pct():.0f}%
- **emergency** — util < {emergency_util_pct():.0f}%: max sustain; verify dgx-gpu-compute daemon

## Your job (GPU / performance niche)
1. Read `scripts/dgx_gpu_events.py`, `scripts/dgx_gpu_compute.py`, `automation.config.local.json`
2. Confirm Mamba embed + GEMM sustain keeps GB10 near **{target_util_pct():.0f}%** (nvidia-smi utilization.gpu)
3. Tune batch size / sustain_dim / interval without breaking knowledge index correctness
4. Run `python3 scripts/dgx_gpu_events.py --snapshot --json` and cite util vs target
5. Prefer productive embed work over dumb burn when queue has pending chunks

Power: {snap.get('gpu_power_w', '?')}W · VRAM: {snap.get('gpu_mem_mib', '?')} MiB · temp: {snap.get('gpu_temp_c', '?')}°C
"""


def _dispatch_gpu_cursor_agent(
    *,
    mode: str,
    snap: dict[str, Any],
    prev_mode: str | None,
    log_fn: Callable[[str], None],
) -> bool:
    if not cursor_agent_enabled():
        return False
    try:
        import peer_terminal as terminal

        ready, detail = terminal.desktop_auth_ready()
        if not ready:
            log_fn(f"gpu event: cursor-agent skip — {detail}")
            return False
        prompt = _build_gpu_agent_prompt(mode=mode, snap=snap, prev_mode=prev_mode)
        rc, _auth_fail = terminal.run_cursor_agent(
            prompt,
            log_fn=log_fn,
            sync=False,
            paid_api=False,
        )
        return rc == 0
    except Exception as exc:  # noqa: BLE001
        log_fn(f"gpu event: cursor-agent dispatch failed — {exc}")
        return False


def restart_cooldown_sec() -> float:
    # Floor 10m — parallel INFRA agents were force-restarting every cooldown
    # and killing CUDA Mamba mid-load (permanent boost beep).
    try:
        return max(600.0, float(_cfg().get("restart_cooldown_sec") or 900))
    except (TypeError, ValueError):
        return 900.0


def _gpu_compute_process_active() -> bool:
    """True when ``dgx_gpu_compute.py --forever`` is running (systemd or bare)."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", r"dgx_gpu_compute\.py --forever"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _gpu_compute_active() -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", "dgx-gpu-compute.service"],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip() == "active":
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return _gpu_compute_process_active()


def _infra_load_protect_active() -> bool:
    """True while INFRA agents hold gpu-compute-protect.json (mid-load lock)."""
    for path in (
        auto.CONFIG_DIR / "gpu-compute-protect.json",
        Path.home() / ".config" / "automation-hub" / "gpu-compute-protect.json",
    ):
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text()) or {}
            # Accept protect_until (canonical) or until (agent shorthand).
            until = float(data.get("protect_until") or data.get("until") or 0)
            if until > time.time():
                return True
            if bool(data.get("protected")) and until <= 0:
                # Boolean-only lock without expiry — treat as active for 2h from mtime.
                try:
                    if time.time() - path.stat().st_mtime < 7200:
                        return True
                except OSError:
                    return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return False


def _restart_gpu_compute(log_fn: Callable[[str], None], *, force: bool = False) -> bool:
    """Start gpu-compute if dead. Never restart a live worker (kills CUDA load).

    Needle: force=True used to bypass cooldown and thrash-restart every poll while
    nvidia-smi reported 0% — GB10 never finished Mamba preload.
    """
    # Never stop/restart a live forever worker — INFRA storms + systemctl restart
    # unload mid-preload (needle: 51GB VRAM → 0 apps → emergency beep).
    if _gpu_compute_process_active() or _gpu_compute_active():
        log_fn("gpu event: skip restart — gpu_compute process/unit already live")
        return False
    if _infra_load_protect_active():
        log_fn("gpu event: skip restart — INFRA load protect active")
        return False
    state = _load_state()
    now = time.time()
    last_restart = float(state.get("last_gpu_compute_restart_ts") or 0)
    if not force and now - last_restart < restart_cooldown_sec():
        log_fn("gpu event: skip restart — within cooldown")
        return False
    try:
        # Ensure unit is enabled so Restart=always sticks across logout.
        subprocess.run(
            ["systemctl", "--user", "enable", "dgx-gpu-compute.service"],
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
        # Prefer start over restart — restart stops a racing just-started unit.
        proc = subprocess.run(
            ["systemctl", "--user", "start", "dgx-gpu-compute.service"],
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
        if proc.returncode == 0:
            log_fn("gpu event: started dgx-gpu-compute.service")
            state["last_gpu_compute_restart_ts"] = time.time()
            _save_state(state)
            return True
        log_fn(f"gpu event: start failed ({proc.stderr or proc.stdout})")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_fn(f"gpu event: restart error — {exc}")
    return False


def _apply_mode_actions(
    *,
    mode: str,
    snap: dict[str, Any],
    log_fn: Callable[[str], None],
    mode_changed: bool = False,
    skip_restart: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {"actions": []}
    override = write_sustain_override(mode=mode)
    report["sustain_override"] = override
    report["actions"].append("write_sustain_override")

    if mode in ("boost", "pressure", "emergency") and synthetic_sustain_enabled():
        try:
            import dgx_gpu_compute as gcompute

            burst = gcompute.sustain_burst(log_fn=log_fn, passes=int(override.get("sustain_passes") or 1))
            report["sustain_burst"] = burst
            report["actions"].append("sustain_burst")
        except Exception as exc:  # noqa: BLE001
            report["sustain_error"] = str(exc)
    elif mode in ("boost", "pressure", "emergency"):
        report["actions"].append("skip_synthetic_sustain")

    # Prefer productive Mamba embed daemon over synthetic GEMM in every under-util mode.
    # Never restart an already-active worker just because nvidia-smi samples 0% —
    # that kills mid-load / mid-embed and guarantees permanent boost beeping.
    #
    # Needle: empty cascade queue + pause_indexer_on_emergency=true → permanent
    # 0%/14W emergency (no new chunks → no embed → stays emergency). Only pause
    # the indexer when there is already a large pending embed backlog (sqlite
    # writers contend with gpu_compute). When pending is thin/empty, keep or
    # start the indexer so productive work can refill.
    pending_chunks = 0
    try:
        for path in _gpu_compute_status_paths():
            if not path.is_file():
                continue
            st = json.loads(path.read_text())
            if isinstance(st, dict):
                pending_chunks = max(pending_chunks, int(st.get("chunks_pending") or 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pending_chunks = 0
    # Default ON when backlog is large — config false was leaving indexer writers
    # parking forever worker on sqlite lock (needle: 2.8b encode then store fail).
    pause_indexer = bool(_cfg().get("pause_indexer_on_emergency", True)) and (
        pending_chunks >= 5000 or mode in ("emergency", "pressure", "boost")
    )
    if mode in ("emergency", "pressure", "boost") and pause_indexer and pending_chunks >= 1000:
        # Indexer long writers park gpu_compute on sqlite lock → 0% util forever.
        already_stopped = False
        try:
            chk = subprocess.run(
                ["systemctl", "--user", "is-active", "knowledge-indexer.service"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            already_stopped = (chk.stdout or "").strip() != "active"
        except (OSError, subprocess.TimeoutExpired):
            already_stopped = False
        if not already_stopped:
            try:
                proc = subprocess.run(
                    ["systemctl", "--user", "stop", "knowledge-indexer.service"],
                    capture_output=True,
                    text=True,
                    timeout=20.0,
                    check=False,
                )
                if proc.returncode == 0:
                    log_fn("gpu event: paused knowledge-indexer (emergency util, pending backlog)")
                    report["actions"].append("pause_knowledge_indexer")
            except (OSError, subprocess.TimeoutExpired) as exc:
                log_fn(f"gpu event: indexer pause failed — {exc}")
        try:
            killed = subprocess.run(
                ["pkill", "-f", "scripts/knowledge_index.py --forever"],
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
            if killed.returncode in (0, 1):
                report["actions"].append("pkill_knowledge_index_orphans")
        except (OSError, subprocess.TimeoutExpired) as exc:
            log_fn(f"gpu event: indexer orphan pkill failed — {exc}")
    elif mode == "emergency" and pending_chunks < 1000 and not embed_productive():
        # Empty/thin queue — unpause so indexer can refill productive embed work.
        # Never start indexer while gpu_compute is mid-embed (heartbeat may briefly
        # omit pending) — sqlite writers park store and collapse util to 0%.
        pause_path = auto.CONFIG_DIR / "pause-knowledge-indexer"
        try:
            if pause_path.is_file():
                pause_path.unlink(missing_ok=True)
                report["actions"].append("clear_pause_knowledge_indexer")
        except OSError:
            pass
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "start", "knowledge-indexer.service"],
                capture_output=True,
                text=True,
                timeout=20.0,
                check=False,
            )
            if proc.returncode == 0:
                log_fn("gpu event: started knowledge-indexer (empty embed queue)")
                report["actions"].append("start_knowledge_indexer")
        except (OSError, subprocess.TimeoutExpired) as exc:
            log_fn(f"gpu event: indexer start failed — {exc}")
    if mode in ("boost", "pressure", "emergency") and not skip_restart:
        if _gpu_compute_active():
            report["actions"].append(
                "embed_mode_active" if embed_productive() else "gpu_compute_active_warming"
            )
        else:
            # Soft start only — force=True on every boost poll thrash-restarts
            # mid-load (journal: Stop every ~60s) and locks util at 0%.
            force = mode == "emergency"
            if _restart_gpu_compute(log_fn, force=force):
                report["actions"].append("restart_gpu_compute")
            else:
                report["actions"].append("skip_restart_cooldown")
    elif mode in ("boost", "pressure", "emergency") and skip_restart:
        report["actions"].append("skip_restart_in_compute_worker")

    return report


def handle_events(
    *,
    log_fn: Callable[[str], None] = print,
    skip_cursor_agent: bool = False,
    skip_restart: bool = False,
) -> dict[str, Any]:
    snap = gpu_snapshot()
    mode = gpu_mode(snap=snap)
    state = _load_state()
    prev_mode = str(state.get("mode") or "")
    now = time.time()
    mode_changed = prev_mode != mode
    report: dict[str, Any] = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **snapshot(snap=snap),
        "mode_changed": mode_changed,
        "prev_mode": prev_mode or None,
    }

    if mode_changed:
        log_fn(
            f"gpu event: {prev_mode or 'init'} → {mode} "
            f"(util {snap.get('gpu_util_pct', 0):.0f}% / target {target_util_pct():.0f}%)"
        )

    mode_report = _apply_mode_actions(
        mode=mode,
        snap=snap,
        log_fn=log_fn,
        mode_changed=mode_changed,
        skip_restart=skip_restart,
    )
    report.update(mode_report)

    last_agent = float(state.get("last_agent_dispatch_ts") or 0)
    want_agent = not skip_cursor_agent and (
        mode_changed or (mode != "hold" and now - last_agent >= cursor_agent_cooldown_sec())
    )
    if want_agent and cursor_agent_enabled() and not skip_cursor_agent:
        if _dispatch_gpu_cursor_agent(mode=mode, snap=snap, prev_mode=prev_mode or None, log_fn=log_fn):
            state["last_agent_dispatch_ts"] = now
            report["cursor_agent_dispatched"] = True
            log_fn(f"gpu event: dispatched cursor-agent for {mode} mode")

    state["mode"] = mode
    state["gpu_util_pct"] = snap.get("gpu_util_pct")
    state["last_ts"] = now
    if mode_changed:
        state["last_transition_ts"] = now
        state["last_transition"] = f"{prev_mode or 'init'}→{mode}"
    _save_state(state)
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="DGX GPU event triggers (target 80% util)")
    parser.add_argument("--handle", action="store_true", help="Run one GPU event evaluation cycle")
    parser.add_argument("--snapshot", action="store_true", help="Print GPU mode snapshot JSON")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.snapshot or not args.handle:
        payload = snapshot()
        print(json.dumps(payload, indent=2))
        return 0
    report = handle_events(log_fn=lambda m: None if args.json else print(m))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"gpu event {report['mode']}: util {report.get('gpu_util_pct', 0):.0f}% "
            f"/ target {report.get('target_util_pct', 80):.0f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
