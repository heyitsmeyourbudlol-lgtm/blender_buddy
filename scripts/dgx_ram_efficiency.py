"""RAM efficiency — productive pins only, compressed vectors, trim waste under load."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path
from typing import Any

import dgx_ram_budget as budget
import project_automation as auto


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("ram_efficiency")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def stable_mode() -> bool:
    return bool(_cfg().get("stable_mode", True))


def page_warm_enabled() -> bool:
    raw = _cfg().get("page_warm_enabled")
    if raw is not None:
        return bool(raw)
    return not stable_mode()


def oom_min_avail_gb() -> float:
    try:
        return max(12.0, float(_cfg().get("oom_min_avail_gb") or 22))
    except (TypeError, ValueError):
        return 22.0


def fill_headroom_gb() -> float:
    """Minimum free RAM required before any fill/mirror growth."""
    try:
        return max(oom_min_avail_gb(), float(_cfg().get("fill_headroom_gb") or oom_min_avail_gb()))
    except (TypeError, ValueError):
        return oom_min_avail_gb()


def trim_ballast_below_avail_gb() -> float:
    try:
        return max(8.0, float(_cfg().get("trim_ballast_below_avail_gb") or 18))
    except (TypeError, ValueError):
        return 18.0


def trim_ballast_when_agents_above() -> int:
    try:
        return max(1, int(_cfg().get("trim_ballast_when_agents_above") or 20))
    except (TypeError, ValueError):
        return 20


def target_productive_shm_gb() -> float:
    try:
        return max(0.0, float(_cfg().get("target_productive_shm_gb") or 8))
    except (TypeError, ValueError):
        return 8.0


def max_productive_shm_gb() -> float:
    try:
        return max(4.0, float(_cfg().get("max_productive_shm_gb") or 24))
    except (TypeError, ValueError):
        return 24.0


def target_used_ram_pct() -> float:
    try:
        return min(0.95, max(0.5, float(_cfg().get("target_used_ram_pct") or 0.88)))
    except (TypeError, ValueError):
        return 0.88


def target_used_gb(total_gb: float | None = None) -> float:
    import dgx_ram_budget as budget

    stats = budget.mem_stats()
    total = total_gb if total_gb is not None else stats["total_gb"]
    cap = budget.ram_max_used_gb()
    pct_target = total * target_used_ram_pct()
    if cap is not None:
        return min(cap, pct_target)
    return pct_target


def effective_productive_target_gb() -> float:
    import dgx_ram_budget as budget

    base = target_productive_shm_gb()
    cap = max_productive_shm_gb()
    stats = budget.mem_stats()
    if stable_mode():
        try:
            import dgx_ram_priority as priority

            if priority.enabled():
                target_used = priority.target_used_gb()
                # Reserve ~55GB for agents + Mamba + daemons; rest can pin in shm.
                agent_reserve = float(_cfg().get("agent_reserve_gb") or 55)
                shm_budget = max(base, target_used - agent_reserve)
                cap = max(cap, min(float(_cfg().get("max_productive_shm_gb") or 48), shm_budget))
        except ImportError:
            pass
        if stats["avail_gb"] < fill_headroom_gb() + 4:
            return min(cap, base)
        if productive_shm_gb() >= cap:
            return cap
        # Grow pinned shm in small steps toward cap when below RAM target.
        target_used = budget.ram_max_used_gb() or stats["total_gb"] * target_used_ram_pct()
        if stats["used_gb"] < target_used - 8:
            return min(cap, max(base, productive_shm_gb() + 2.0))
        return min(cap, base)
    target_used = target_used_gb(stats["total_gb"])
    gap = target_used - stats["used_gb"]
    if gap < 2.0:
        return min(cap, base)
    boost = min(gap * 0.3, cap - base)
    return min(cap, base + max(0.0, boost))


def productive_shm_gb() -> float:
    import dgx_ram_fill as rfill

    return rfill.productive_shm_gb()


def fill_pressure_ok() -> bool:
    """True when there is enough headroom to grow pinned caches safely."""
    import dgx_ram_budget as budget

    stats = budget.mem_stats()
    fp = budget.footprint_gb(stats=stats)
    if stats["avail_gb"] < fill_headroom_gb():
        return False
    cap = budget.ram_max_used_gb()
    if cap is not None and fp >= cap - 0.5:
        return False
    if budget.pressure_level(avail_gb=stats["avail_gb"], total_gb=stats["total_gb"], stats=stats) != "ok":
        return False
    return True


def agent_count() -> int:
    count = 0
    for _pid, cmd in budget.iter_proc_cmdlines():
        if "cursor-agent" not in cmd:
            continue
        if "worker-server" in cmd:
            continue
        # Path ``cursor-agent-worker`` must not exclude peer ``-p`` agents.
        if any(tok.rsplit("/", 1)[-1] == "worker" for tok in cmd.split()):
            continue
        if " -p " in cmd or cmd.rstrip().endswith(" -p"):
            count += 1
    if count or Path("/proc").is_dir():
        return count
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "cursor-agent"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0 or not proc.stdout:
        return 0
    fallback = 0
    for line in proc.stdout.splitlines():
        if "worker-server" in line:
            continue
        if any(tok.rsplit("/", 1)[-1] == "worker" for tok in line.split()):
            continue
        if " -p " in line or line.rstrip().endswith(" -p"):
            fallback += 1
    return fallback


def should_trim_ballast(avail_gb: float) -> bool:
    if not enabled():
        return False
    if avail_gb < trim_ballast_below_avail_gb():
        return True
    return agent_count() > trim_ballast_when_agents_above()


def quantize_int8(vec: list[float]) -> bytes:
    """Pack float32 vector as scale (f32) + int8 payload — 4× smaller than raw floats."""
    if not vec:
        return b""
    peak = max(abs(v) for v in vec) or 1.0
    scale = peak / 127.0
    payload = bytes((max(-128, min(127, int(round(v / scale)))) + 128) & 255 for v in vec)
    return struct.pack("<f", scale) + payload


def dequantize_int8(blob: bytes) -> list[float]:
    if len(blob) < 5:
        return []
    scale = struct.unpack("<f", blob[:4])[0] or 1.0
    return [(b - 128) * scale for b in blob[4:]]


def embedding_blob(vec: list[float], *, quant: str) -> tuple[bytes, str]:
    q = (quant or "none").lower()
    if q in ("int8", "i8", "quant8"):
        return quantize_int8(vec), "int8"
    import array

    return array.array("f", vec).tobytes(), "float32"
