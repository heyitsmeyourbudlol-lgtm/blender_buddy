#!/usr/bin/env python3
"""DGX GPU compute worker — batch Mamba embeddings on CUDA (L1 precompute + TOPs)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import knowledge_index as kindex  # noqa: E402
import knowledge_index_config as kcfg  # noqa: E402
import knowledge_mamba as kmamba  # noqa: E402
import knowledge_mamba_stack as kstack  # noqa: E402
import dgx_ram_efficiency as eff  # noqa: E402
import project_automation as auto  # noqa: E402


def _compute_cfg() -> dict[str, Any]:
    raw = auto.CFG.get("dgx_compute")
    return raw if isinstance(raw, dict) else {}


# Held flock fd — must stay open for the process lifetime. Re-open + LOCK_NB
# from the same forever worker used to EWOULDBLOCK every embed cycle (0 embeds).
_LOCK_FD: int | None = None
_LAST_CUDA_RECLAIM_TS: float = 0.0
_LAST_EMBED_TS: float = 0.0
_LAST_EMBED_N: int = 0


def reclaim_cuda_allocator_cache(
    *,
    log_fn: Callable[[str], None] = print,
    force: bool = False,
    min_slack_mb: float = 2048.0,
) -> dict[str, float]:
    """Return unused CUDA caching-allocator pages to the OS.

    Needle: student embed allocates ~250MB but PyTorch keeps ~24GB *reserved*
    after teacher warmups — MemAvailable collapses and RAM fill stalls ~82GB
    forever while nvidia-smi still shows productive util.

    Counter-needle: empty_cache on ~10–35GB teacher reserved → 1.5GB samples as
    0%/14W emergency + folio_wait thrash while 790m is mid-flight. Never reclaim
    while a teacher working set is resident — prefer RAM tiered-replace over
    collapsing CUDA cache.

    Soft-reclaim (2026-09-06): 2.8b-4bit sits at ~1.8GB *allocated* with
    18–21GB *reserved* from prior warmups — that slack starves anon fill on
    unified GB10. empty_cache keeps live tensors; only drops unused cache.
    """
    global _LAST_CUDA_RECLAIM_TS
    out = {"allocated_mb": 0.0, "reserved_mb": 0.0, "reclaimed": 0.0}
    try:
        import torch
    except ImportError:
        return out
    if not torch.cuda.is_available():
        return out
    try:
        allocated = float(torch.cuda.memory_allocated()) / (1024 * 1024)
        reserved = float(torch.cuda.memory_reserved()) / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return out
    out["allocated_mb"] = round(allocated, 1)
    out["reserved_mb"] = round(reserved, 1)
    slack = reserved - allocated
    now = time.time()
    soft = bool(_compute_cfg().get("cuda_soft_reclaim", True))
    enabled = bool(_compute_cfg().get("cuda_reclaim_enabled", False)) or soft
    if not enabled and not force:
        return out
    try:
        keep_mb = float(_compute_cfg().get("cuda_keep_reserved_mb") or 4096)
    except (TypeError, ValueError):
        keep_mb = 4096.0
    try:
        hot_sec = float(_compute_cfg().get("cuda_reclaim_hot_sec") or 90.0)
    except (TypeError, ValueError):
        hot_sec = 90.0
    # Soft path: reclaim orphaned slack above working set even mid-drain.
    # Hard path (force/legacy): keep old guards (no reclaim while alloc hot).
    if soft and not force:
        # Hot teacher encode window — never empty_cache mid-batch (needle: 18→1.8GB
        # mid 2.8b burst → 0%/14W emergency while 126k chunks remain).
        # Between batches, unused reserved (30GB+) parks MemAvailable and freezes
        # the ~100GB anon climb — reclaim *slack only*, keep live weights.
        # Hot encode: skip only the first few seconds of a batch.
        if _LAST_EMBED_TS and now - _LAST_EMBED_TS < 3.0:
            return out
        if slack < max(min_slack_mb, 4096.0):
            return out
        if not force and now - _LAST_CUDA_RECLAIM_TS < 20.0:
            return out
        # Keep live weights + modest activation pad (~4–8GB), drop the rest.
        working_keep = max(allocated + 2048.0, min(max(keep_mb, allocated + 4096.0), allocated + 8192.0))
        if reserved <= working_keep + 2048.0:
            return out
        avail_gb = 99.0
        fp_gb = 100.0
        try:
            import dgx_ram_budget as _rb

            avail_gb = float(_rb.mem_stats()["avail_gb"])
            fp_gb = float(_rb.footprint_gb())
        except Exception:  # noqa: BLE001
            pass
        under_target = fp_gb < 97.0
        # Reclaim orphan reserved whenever under target or avail is tight —
        # unified GB10 20–57GB reserved freezes / OOM-kills the anon climb.
        if avail_gb >= 24.0 and not under_target and slack < 20480.0:
            return out
    else:
        # Hot embed window — never shrink teacher footprint (legacy hard reclaim).
        if _LAST_EMBED_TS and now - _LAST_EMBED_TS < hot_sec:
            return out
        # Resident weights / process VRAM ⇒ productive teacher — never empty_cache.
        if allocated >= 512.0:
            return out
        try:
            import dgx_gpu_events as _gev

            if float(_gev._compute_process_vram_mib()) >= 4000.0:
                return out
        except Exception:  # noqa: BLE001
            pass
        if not force and slack < min_slack_mb:
            return out
        if not force and now - _LAST_CUDA_RECLAIM_TS < 300.0:
            return out
        if reserved <= keep_mb + 2048:
            return out
        avail_gb = 99.0
        try:
            import dgx_ram_budget as _rb

            avail_gb = float(_rb.mem_stats()["avail_gb"])
        except Exception:  # noqa: BLE001
            pass
        if not force and avail_gb >= 6.0:
            return out
        if allocated >= 256.0:
            return out
    try:
        import dgx_ram_budget as _rb

        avail_gb = float(_rb.mem_stats()["avail_gb"])
    except Exception:  # noqa: BLE001
        avail_gb = 99.0
    try:
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        reserved_after = float(torch.cuda.memory_reserved()) / (1024 * 1024)
        out["reserved_mb"] = round(reserved_after, 1)
        out["reclaimed"] = round(max(0.0, reserved - reserved_after), 1)
        _LAST_CUDA_RECLAIM_TS = now
        if out["reclaimed"] >= 256 or force:
            _log(
                f"cuda reclaim: reserved {reserved:.0f}→{reserved_after:.0f}MB "
                f"(alloc {allocated:.0f}MB avail {avail_gb:.1f}GB)",
                log_fn,
            )
    except Exception as exc:  # noqa: BLE001
        _log(f"cuda reclaim failed — {exc}", log_fn)
    return out


def _singleton_lock() -> bool:
    """Refuse a second process — reentrant for the worker that already holds the lock."""
    global _LOCK_FD
    if _LOCK_FD is not None:
        return True
    lock_path = auto.CONFIG_DIR / "gpu-compute.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        return True
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        _LOCK_FD = fd
        return True
    except OSError:
        os.close(fd)
        return False
    _LOCK_FD = fd
    return True


def enabled() -> bool:
    """True when dgx_compute.enabled — forever worker also honors force env.

    Needle: competing agents flip ``enabled: false`` while systemd still runs the
    unit; without FORCE the loop sleeps 30s and GB10 stays at 0% util.
    """
    force = os.environ.get("DGX_GPU_COMPUTE_FORCE", "").strip().lower()
    if force in ("1", "true", "yes"):
        return True
    # Empty string in systemd Environment= still counts as "set" for setdefault —
    # treat blank / 0 as unset so --forever can arm FORCE.
    if force in ("0", "false", "no"):
        return bool(_compute_cfg().get("enabled", True))
    # systemd ExecStart ... --forever is itself the enable signal.
    if "--forever" in sys.argv:
        return True
    return bool(_compute_cfg().get("enabled", True))


def apply_gpu_health_cap(*, log_fn: Callable[[str], None] | None = None) -> float:
    """Cap CUDA caching-allocator growth (thermal + absolute ceiling).

    On unified-memory GB10, mapping thermal→35–95% lets PyTorch reserve
    20–30GB while student Mamba only needs ~256MB — MemAvailable collapses
    and RAM footprint stalls ~70–85GB forever.
    """
    cfg = _compute_cfg()
    try:
        # Teachers need headroom but unified GB10 cannot hold ~100GB anon AND
        # 45–57GB CUDA reserved (needle 2026-09-08). Default 0.32 (~38GB).
        frac_max = float(cfg.get("cuda_memory_fraction_max") or 0.32)
    except (TypeError, ValueError):
        frac_max = 0.32
    try:
        frac_min = float(cfg.get("cuda_memory_fraction_min") or 0.18)
    except (TypeError, ValueError):
        frac_min = 0.18
    # Absolute ceiling — leave room for OS/agents + ~100GB footprint climb.
    frac_max = max(0.18, min(0.34, frac_max))
    frac_min = max(0.10, min(frac_max, frac_min))
    try:
        import dgx_gpu_events as gev

        if gev.thermal_enabled():
            frac = frac_min + (frac_max - frac_min) * float(gev.thermal_scale())
        else:
            frac = frac_max
    except Exception:  # noqa: BLE001
        frac = frac_max
    frac = max(frac_min, min(frac_max, frac))
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.set_per_process_memory_fraction(frac, 0)
            if log_fn:
                log_fn(f"cuda memory fraction capped at {frac:.0%} (embed ceiling)")
    except Exception:  # noqa: BLE001
        pass
    return frac


def embed_batch_size() -> int:
    try:
        return max(8, int(_compute_cfg().get("gpu_embed_batch") or kcfg.mamba_batch_size() or 64))
    except (TypeError, ValueError):
        return 64


def cycle_interval_sec() -> float:
    try:
        return max(0.05, float(_compute_cfg().get("gpu_embed_interval_sec") or 5))
    except (TypeError, ValueError):
        return 5.0


def sustain_when_idle() -> bool:
    # Default False — prefer productive Mamba embed over synthetic GEMM burn.
    return bool(_compute_cfg().get("gpu_sustain_when_idle", False))


def sustain_seconds() -> float:
    override = _load_runtime_override()
    if override.get("sustain_sec") is not None:
        try:
            return max(0.5, float(override["sustain_sec"]))
        except (TypeError, ValueError):
            pass
    try:
        return max(0.5, float(_compute_cfg().get("gpu_sustain_sec") or 3.0))
    except (TypeError, ValueError):
        return 3.0


def sustain_dim() -> int:
    override = _load_runtime_override()
    if override.get("sustain_dim") is not None:
        try:
            return max(1024, int(override["sustain_dim"]))
        except (TypeError, ValueError):
            pass
    try:
        return max(1024, int(_compute_cfg().get("gpu_sustain_dim") or 6144))
    except (TypeError, ValueError):
        return 6144


def _load_runtime_override() -> dict[str, Any]:
    try:
        import dgx_gpu_events as gev

        return gev.load_sustain_override()
    except ImportError:
        return {}


def effective_embed_batch_size() -> int:
    base = embed_batch_size()
    override = _load_runtime_override()
    if override.get("embed_batch") is not None:
        try:
            # Events governor writes the intentional batch (already capped ≤48 in
            # emergency/boost). Using max(base, override) ignored the 48 cap when
            # base was 128 — then run_embed_cycle floored 2.8b to 384 and hung
            # unified GB10 at ~50GB reserved / 0% util (needle 2026-09-08).
            return max(8, min(128, int(override["embed_batch"])))
        except (TypeError, ValueError):
            pass
    return max(8, min(128, base))


def effective_cycle_interval_sec() -> float:
    base = cycle_interval_sec()
    override = _load_runtime_override()
    if override.get("interval_sec") is not None:
        try:
            return max(0.02, min(base, float(override["interval_sec"])))
        except (TypeError, ValueError):
            pass
    return base


def embed_burst_sec() -> float:
    try:
        # Default 20s back-to-back embed — keeps GB10 busy between nvidia-smi samples.
        base = max(0.0, float(_compute_cfg().get("embed_burst_sec") or 20))
    except (TypeError, ValueError):
        base = 20.0
    override = _load_runtime_override()
    if override.get("embed_burst_sec") is not None:
        try:
            # Stale short bursts (28–90s) must not undercut emergency CFG pin.
            return max(0.0, base, float(override["embed_burst_sec"]))
        except (TypeError, ValueError):
            pass
    return base


def _embed_model_queue() -> list[tuple[str, str]]:
    """Cascade tiers in order — finish student, then teacher_1, then teacher_2."""
    if kcfg.mamba_cascade_enabled():
        return [
            (kcfg.cascade_student_model(), kcfg.cascade_compression("student")),
            (kcfg.cascade_teacher_1_model(), kcfg.cascade_compression("teacher_1")),
            (kcfg.cascade_teacher_2_model(), kcfg.cascade_compression("teacher_2")),
        ]
    model_id = kcfg.mamba_model() or ""
    if not model_id:
        return []
    return [(model_id, kcfg.mamba_dtype())]



def _force_cuda_device(*, log_fn=print) -> None:
    """Forever worker must embed on CUDA — config races flip mamba_device back to cpu."""
    try:
        import torch
        if not torch.cuda.is_available():
            return
    except Exception:
        return
    ki = auto.CFG.setdefault("knowledge_index", {})
    if not isinstance(ki, dict):
        return
    if str(ki.get("mamba_device") or "").lower() != "cuda":
        ki["mamba_device"] = "cuda"
        _log("forced knowledge_index.mamba_device=cuda for productive embed", log_fn)
    # Keep resident while the forever worker is alive.
    ki["mamba_resident"] = True


def _ensure_mamba_loaded(*, log_fn: Callable[[str], None] = print) -> bool:
    """Resident Mamba on CUDA — prefer cascade teachers when student queue is thin."""
    # Forever worker always preloads; config preload_mamba:false was idling GB10 at 0%.
    force_preload = os.environ.get("DGX_GPU_COMPUTE_FORCE", "").strip().lower() in ("1", "true", "yes")
    if not force_preload and not bool(_compute_cfg().get("preload_mamba", True)):
        return False
    if not kcfg.mamba_enabled():
        return False
    model_id = kcfg.cascade_student_model() if kcfg.mamba_cascade_enabled() else (kcfg.mamba_model() or "")
    compression = kcfg.cascade_compression("student") if kcfg.mamba_cascade_enabled() else kcfg.mamba_dtype()
    # Prefer teacher preload when cascade pending — 130m never moves GB10 util.
    if kcfg.mamba_cascade_enabled():
        try:
            prefer_below = int(_compute_cfg().get("prefer_teachers_when_student_below") or 12000)
        except (TypeError, ValueError):
            prefer_below = 12000
        queue = _embed_model_queue()
        student_key = kcfg.cascade_student_model() or ""
        try:
            conn = _connect_db(busy_ms=1500)
            try:
                total = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
                student_done = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?",
                        (student_key,),
                    ).fetchone()[0]
                )
                student_left = max(0, total - student_done)
                if student_left <= prefer_below:
                    for mid, comp in queue:
                        if mid == student_key:
                            continue
                        embedded = int(
                            conn.execute(
                                "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?",
                                (mid,),
                            ).fetchone()[0]
                        )
                        if embedded < total:
                            model_id, compression = mid, comp
                            break
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
    if not model_id:
        return False
    if kmamba.status().get("loaded"):
        return True
    ok = kmamba._load_model(model_id, compression=compression)
    if ok:
        _log(f"preloaded {model_id} on {kcfg.mamba_device()}", log_fn)
    else:
        _log(f"preload failed — {kmamba.status().get('load_failed') or 'unknown'}", log_fn)
    return bool(ok)


def sustain_matmul(
    *,
    log_fn: Callable[[str], None] = print,
    dim: int | None = None,
    secs: float | None = None,
) -> dict[str, Any]:
    """Heavy FP16 GEMMs to keep GB10 busy when embed queue is empty."""
    try:
        import torch
    except ImportError:
        return {"skipped": True}
    if not torch.cuda.is_available():
        return {"skipped": True}
    mat_dim = dim if dim is not None else sustain_dim()
    duration = secs if secs is not None else sustain_seconds()
    a = torch.randn(mat_dim, mat_dim, device="cuda", dtype=torch.float16)
    b = torch.randn(mat_dim, mat_dim, device="cuda", dtype=torch.float16)
    started = time.time()
    ops = 0
    while time.time() - started < duration:
        torch.mm(a, b)
        ops += 1
    torch.cuda.synchronize()
    elapsed = time.time() - started
    tflops = (2 * mat_dim**3 * ops) / elapsed / 1e12 if elapsed > 0 else 0.0
    _log(f"sustain GEMM {mat_dim}x{mat_dim} x{ops} ~{tflops:.1f} TFLOP/s", log_fn)
    return {"sustain_ops": ops, "dim": mat_dim, "elapsed_sec": round(elapsed, 2), "tflops_est": round(tflops, 2)}


def sustain_burst(*, log_fn: Callable[[str], None] = print, passes: int = 1) -> dict[str, Any]:
    """Run one or more sustain GEMM bursts using runtime override knobs."""
    override = _load_runtime_override()
    dim = int(override.get("sustain_dim") or sustain_dim())
    secs = float(override.get("sustain_sec") or sustain_seconds())
    total_passes = max(1, passes)
    bursts: list[dict[str, Any]] = []
    for _ in range(total_passes):
        bursts.append(sustain_matmul(log_fn=log_fn, dim=dim, secs=secs))
    return {"passes": total_passes, "bursts": bursts}


def sustain_until_target(*, log_fn: Callable[[str], None] = print, max_sec: float | None = None) -> dict[str, Any]:
    """Keep firing GEMM until util nears target or max_sec elapsed."""
    try:
        import dgx_gpu_events as gev
    except ImportError:
        return sustain_matmul(log_fn=log_fn)

    mode = gev.gpu_mode()
    if max_sec is None:
        max_sec = {"emergency": 30.0, "pressure": 22.0, "boost": 16.0}.get(mode, 12.0)
    started = time.time()
    bursts: list[dict[str, Any]] = []
    while time.time() - started < max_sec:
        snap = gev.gpu_snapshot()
        if gev.over_max(snap=snap) or gev.thermal_scale(snap=snap) <= 0.0:
            _log(
                f"thermal stop — temp {float(snap.get('gpu_temp_c') or 0):.0f}C "
                f"scale={gev.thermal_scale(snap=snap):.2f}",
                log_fn,
            )
            break
        if float(snap.get("gpu_util_pct") or 0) >= gev.throttle_util_pct(snap=snap):
            _log(
                f"throttle — util {float(snap.get('gpu_util_pct') or 0):.0f}% "
                f">= effective max {gev.throttle_util_pct(snap=snap):.0f}% "
                f"(temp {float(snap.get('gpu_temp_c') or 0):.0f}C)",
                log_fn,
            )
            break
        if gev.at_target(snap=snap):
            break
        params = gev.sustain_params(snap=snap)
        if params.get("throttled") or float(params.get("sustain_sec") or 0) <= 0:
            break
        bursts.append(
            sustain_matmul(
                log_fn=log_fn,
                dim=int(params.get("sustain_dim") or sustain_dim()),
                secs=float(params.get("sustain_sec") or sustain_seconds()),
            )
        )
    return {"elapsed_sec": round(time.time() - started, 2), "bursts": bursts}


def _log(msg: str, log_fn: Callable[[str], None] = print) -> None:
    # Avoid double "gpu_compute:" when callers pass this function as log_fn.
    if msg.startswith("gpu_compute:") or " gpu_compute: " in msg[:48]:
        line = msg if msg[:4].isdigit() else f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    else:
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  gpu_compute: {msg}"
    if log_fn is print or log_fn is _log:
        print(line, flush=True)
    else:
        log_fn(line)


def _connect_db(*, busy_ms: int | None = None) -> sqlite3.Connection:
    # Short busy wait — indexer long writers used to park forever worker for
    # 120s+ per cycle (needle: mamba loaded, 15W idle, permanent emergency).
    if busy_ms is None:
        try:
            busy_ms = int(_compute_cfg().get("sqlite_busy_timeout_ms") or 8000)
        except (TypeError, ValueError):
            busy_ms = 8000
    busy_ms = max(500, min(60_000, int(busy_ms)))
    timeout_s = max(1.0, busy_ms / 1000.0)
    conn = sqlite3.connect(kcfg.db_path(), timeout=timeout_s, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={busy_ms}")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _embedding_pk_is_composite(conn: sqlite3.Connection) -> bool:
    """True when chunk_embeddings PK is (chunk_id, model) — cascade-safe."""
    try:
        rows = conn.execute("PRAGMA table_info(chunk_embeddings)").fetchall()
    except sqlite3.OperationalError:
        return False
    if not rows:
        return False
    pk_cols = sorted((int(r[5]), str(r[1])) for r in rows if int(r[5] or 0) > 0)
    names = [n for _ord, n in pk_cols]
    return names == ["chunk_id", "model"]


def _migrate_embeddings_composite_pk(
    conn: sqlite3.Connection, *, log_fn: Callable[[str], None] = print
) -> None:
    """Batched migrate to (chunk_id, model) — never long exclusive rewrite."""
    if _embedding_pk_is_composite(conn):
        return
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_embeddings' LIMIT 1"
    ).fetchone()
    if not row:
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings_v2 (
          chunk_id INTEGER NOT NULL,
          model TEXT NOT NULL,
          dim INTEGER NOT NULL,
          quant TEXT NOT NULL DEFAULT 'float32',
          vector BLOB NOT NULL,
          updated_at REAL NOT NULL,
          PRIMARY KEY (chunk_id, model),
          FOREIGN KEY(chunk_id) REFERENCES chunks(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_v2_model ON chunk_embeddings_v2(model)"
    )
    copied = 0
    batch = 2000
    for _ in range(200):  # cap per process call — forever loop continues
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO chunk_embeddings_v2
                  (chunk_id, model, dim, quant, vector, updated_at)
                SELECT e.chunk_id, e.model, e.dim,
                       COALESCE(e.quant, 'float32'), e.vector, e.updated_at
                FROM chunk_embeddings e
                WHERE NOT EXISTS (
                  SELECT 1 FROM chunk_embeddings_v2 v
                  WHERE v.chunk_id = e.chunk_id AND v.model = e.model
                )
                LIMIT ?
                """,
                (batch,),
            )
            n = int(cur.rowcount or 0)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                _log(f"migrate batch yield — {exc}", log_fn)
                return
            raise
        if n <= 0:
            break
        copied += n
    if copied:
        _log(f"migrate copied +{copied} rows → chunk_embeddings_v2", log_fn)
    try:
        old_n = int(conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0])
        new_n = int(conn.execute("SELECT COUNT(*) FROM chunk_embeddings_v2").fetchone()[0])
    except sqlite3.OperationalError:
        return
    if new_n < old_n:
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE chunk_embeddings")
        conn.execute("ALTER TABLE chunk_embeddings_v2 RENAME TO chunk_embeddings")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON chunk_embeddings(model)"
        )
        conn.execute("COMMIT")
        _log(f"chunk_embeddings composite PK cutover complete ({new_n} rows)", log_fn)
    except sqlite3.OperationalError as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        _log(f"cutover deferred — {exc}", log_fn)



_SCHEMA_READY = False


def _ensure_embedding_schema(conn: sqlite3.Connection) -> None:
    """DDL/migrate once per process — repeating under indexer lock stalls embeds at 0%."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    # Fast path: already composite — never enter migrate under indexer lock.
    try:
        if _embedding_pk_is_composite(conn):
            _SCHEMA_READY = True
            return
    except sqlite3.OperationalError:
        pass
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
          chunk_id INTEGER NOT NULL,
          model TEXT NOT NULL,
          dim INTEGER NOT NULL,
          quant TEXT NOT NULL DEFAULT 'float32',
          vector BLOB NOT NULL,
          updated_at REAL NOT NULL,
          PRIMARY KEY (chunk_id, model),
          FOREIGN KEY(chunk_id) REFERENCES chunks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON chunk_embeddings(model);
        """
    )
    try:
        conn.execute("ALTER TABLE chunk_embeddings ADD COLUMN quant TEXT NOT NULL DEFAULT 'float32'")
    except sqlite3.OperationalError:
        pass
    # Legacy tables used chunk_id INTEGER PRIMARY KEY — migrate in place (batched).
    if not _embedding_pk_is_composite(conn):
        # Ensure v2 exists first so teachers can write while cutover waits on locks.
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_embeddings_v2 (
                  chunk_id INTEGER NOT NULL,
                  model TEXT NOT NULL,
                  dim INTEGER NOT NULL,
                  quant TEXT NOT NULL DEFAULT 'float32',
                  vector BLOB NOT NULL,
                  updated_at REAL NOT NULL,
                  PRIMARY KEY (chunk_id, model),
                  FOREIGN KEY(chunk_id) REFERENCES chunks(id)
                )
                """
            )
            _SCHEMA_READY = True
        except sqlite3.OperationalError:
            pass
        _migrate_embeddings_composite_pk(conn)
    # Ready once composite OR v2 staging exists (teachers can write safely).
    if _embedding_pk_is_composite(conn):
        _SCHEMA_READY = True
    else:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_embeddings_v2' LIMIT 1"
        ).fetchone()
        _SCHEMA_READY = bool(row)


def _pack_vector(vec: list[float]) -> tuple[bytes, str]:
    quant = kstack.vector_quant() if kstack.stack_enabled() else "float32"
    return eff.embedding_blob(vec, quant=quant)


def _embeddings_table(conn: sqlite3.Connection) -> str:
    """Use v2 while legacy PK migration is in flight (cascade-safe writes)."""
    if _embedding_pk_is_composite(conn):
        return "chunk_embeddings"
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_embeddings_v2' LIMIT 1"
    ).fetchone()
    return "chunk_embeddings_v2" if row else "chunk_embeddings"


def _fetch_pending(conn: sqlite3.Connection, *, model: str, limit: int) -> list[tuple[int, str]]:
    table = _embeddings_table(conn)
    # During migration, also treat legacy student rows as done for that model.
    if table == "chunk_embeddings_v2":
        rows = conn.execute(
            f"""
            SELECT c.id, c.text
            FROM chunks c
            WHERE NOT EXISTS (
              SELECT 1 FROM chunk_embeddings_v2 v
              WHERE v.chunk_id = c.id AND v.model = ?
            )
            AND NOT EXISTS (
              SELECT 1 FROM chunk_embeddings e
              WHERE e.chunk_id = c.id AND e.model = ?
            )
            ORDER BY c.id
            LIMIT ?
            """,
            (model, model, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT c.id, c.text
            FROM chunks c
            LEFT JOIN {table} e ON e.chunk_id = c.id AND e.model = ?
            WHERE e.chunk_id IS NULL
            ORDER BY c.id
            LIMIT ?
            """,
            (model, limit),
        ).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def _store_embeddings(
    conn: sqlite3.Connection,
    *,
    model: str,
    items: list[tuple[int, list[float]]],
) -> int:
    if not items:
        return 0
    now = time.time()
    dim = len(items[0][1])
    rows = []
    for cid, vec in items:
        blob, quant = _pack_vector(vec)
        rows.append((cid, model, dim, quant, blob, now))
    table = _embeddings_table(conn)
    if table == "chunk_embeddings" and not _embedding_pk_is_composite(conn):
        # Legacy PK — still overwrite by chunk_id (student-only path).
        sql = """
        INSERT INTO chunk_embeddings (chunk_id, model, dim, quant, vector, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
          model=excluded.model,
          dim=excluded.dim,
          quant=excluded.quant,
          vector=excluded.vector,
          updated_at=excluded.updated_at
        """
    else:
        sql = f"""
        INSERT INTO {table} (chunk_id, model, dim, quant, vector, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chunk_id, model) DO UPDATE SET
          dim=excluded.dim,
          quant=excluded.quant,
          vector=excluded.vector,
          updated_at=excluded.updated_at
        """
    for attempt in range(8):
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(sql, rows)
            conn.execute("COMMIT")
            return len(items)
        except sqlite3.OperationalError as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if "locked" not in str(exc).lower() or attempt >= 7:
                raise
            # Fail-fast backoff — never sleep tens of seconds (0% util needle).
            time.sleep(min(1.5, 0.1 * (2**attempt)))
    return 0


def run_embed_cycle(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    global _LAST_EMBED_TS, _LAST_EMBED_N
    if not _singleton_lock():
        return {"skipped": True, "reason": "duplicate gpu_compute worker"}
    if not kcfg.mamba_enabled():
        report: dict[str, Any] = {"skipped": True, "reason": "mamba disabled"}
        if sustain_when_idle():
            report["sustain"] = sustain_until_target(log_fn=log_fn)
        return report

    db = kcfg.db_path()
    if not db.is_file():
        return {"skipped": True, "reason": "no index db"}

    queue = _embed_model_queue()
    if not queue:
        return {"skipped": True, "reason": "no model"}

    try:
        conn = _connect_db()
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks' LIMIT 1"
            ).fetchone()
            if not row:
                kindex.init_db(conn)
            _ensure_embedding_schema(conn)
            batch = effective_embed_batch_size()
            model_id = ""
            compression = ""
            pending: list[tuple[int, str]] = []
            # Prefer teacher tiers when student queue is thin — keeps 126k+
            # cascade pending hot instead of finishing last student crumbs.
            # Threshold is deliberately high: 130m @ batch≤768 never moves GB10
            # nvidia util (idle ~14W) while 790m/2.8b does.
            student_key = (
                kcfg.cascade_student_model()
                if kcfg.mamba_cascade_enabled()
                else (kcfg.mamba_model() or "")
            )
            ordered = list(queue)
            if kcfg.mamba_cascade_enabled() and len(ordered) > 1:
                try:
                    prefer_below = int(
                        _compute_cfg().get("prefer_teachers_when_student_below") or 12000
                    )
                except (TypeError, ValueError):
                    prefer_below = 12000
                prefer_below = max(512, prefer_below)
                try:
                    student_left = conn.execute(
                        """
                        SELECT COUNT(*) FROM chunks c
                        LEFT JOIN chunk_embeddings e
                          ON e.chunk_id = c.id AND e.model = ?
                        WHERE e.chunk_id IS NULL
                        """,
                        (student_key,),
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    student_left = 10**9
                # Force teachers under boost/pressure/emergency — productive util.
                # Also prefer teachers when raw util is below boost (130m crumbs
                # leave GB10 at ~0%/14W while 126k+ cascade pending remains).
                force_teachers = False
                try:
                    import dgx_gpu_events as gev

                    mode = gev.gpu_mode()
                    snap = gev.gpu_snapshot()
                    raw_u = float(snap.get("gpu_util_pct") or 0)
                    force_teachers = mode in ("boost", "pressure", "emergency") or (
                        raw_u < gev.boost_util_pct() - 5.0
                    )
                except Exception:  # noqa: BLE001
                    force_teachers = False
                if force_teachers or int(student_left) <= prefer_below:
                    ordered = [q for q in ordered if q[0] != student_key] + [
                        q for q in ordered if q[0] == student_key
                    ]
            for mid, comp in ordered:
                batch_n = batch
                # 2.8b-4bit: respect gpu_embed_batch_2_8b (≤48). Old floor of 384
                # reserved ~50GB on unified GB10 and stalled first encode (0%/15W).
                if "2.8b" in mid or comp in ("4bit", "q4", "int4"):
                    try:
                        cap_28 = int(_compute_cfg().get("gpu_embed_batch_2_8b") or 48)
                    except (TypeError, ValueError):
                        cap_28 = 48
                    cap_28 = max(16, min(64, cap_28))
                    batch_n = max(8, min(batch, cap_28))
                    # First encode after preload: batch 8 so last_embed_ts lands in
                    # ~30–60s (batch 40–48 took 3–4min → stale status → emergency beep).
                    if not _LAST_EMBED_TS:
                        batch_n = min(batch_n, 8)
                elif "790m" in mid:
                    batch_n = max(batch, min(int(batch * 1.25), 128))
                    if not _LAST_EMBED_TS:
                        batch_n = min(batch_n, 16)
                rows = _fetch_pending(conn, model=mid, limit=batch_n)
                if rows:
                    model_id, compression, pending = mid, comp, rows
                    batch = batch_n
                    break
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            _log(f"db busy — skip cycle ({exc})", log_fn)
            return {"skipped": True, "reason": "database is locked"}
        raise

    if not model_id or not pending:
        conn = _connect_db()
        try:
            total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            done_by_model: dict[str, int] = {}
            pending_by_model: dict[str, int] = {}
            for mid, _comp in queue:
                done = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?", (mid,)
                    ).fetchone()[0]
                )
                done_by_model[mid] = done
                pending_by_model[mid] = max(0, int(total) - done)
            report = {
                "embedded": 0,
                "pending": sum(pending_by_model.values()),
                "total_chunks": int(total),
                "pending_by_model": pending_by_model,
                "embedded_by_model": done_by_model,
            }
        finally:
            conn.close()
        # Student tier nearly done — keep GPU on cascade teachers (790m / 2.8b).
        student_key = kcfg.cascade_student_model() if kcfg.mamba_cascade_enabled() else (kcfg.mamba_model() or "")
        student_pending = int(report.get("pending_by_model", {}).get(student_key, report.get("pending") or 0))
        if student_pending <= max(64, batch // 4):
            for mid, comp in queue:
                if mid == student_key:
                    continue
                conn = _connect_db()
                try:
                    rows = _fetch_pending(conn, model=mid, limit=max(8, batch // 2))
                    if rows:
                        model_id, compression, pending = mid, comp, rows
                        break
                finally:
                    conn.close()
        if not model_id or not pending:
            if sustain_when_idle():
                report["sustain"] = sustain_until_target(log_fn=log_fn)
            return report

    if not kmamba._load_model(model_id, compression=compression):
        report = {"skipped": True, "reason": kmamba.status().get("load_failed") or "load failed", "model": model_id}
        if sustain_when_idle():
            report["sustain"] = sustain_until_target(log_fn=log_fn)
        return report

    ids = [row[0] for row in pending]
    texts = [row[1] for row in pending]
    started = time.time()
    # Touch heartbeat before long encode so resource_priority doesn't emergency-beep
    # for 40–90s while status mtime goes stale (needle 2026-09-08).
    try:
        status()
    except Exception:  # noqa: BLE001
        pass
    vectors = kmamba._encode_batch(texts)
    # Retry store — knowledge_index writers briefly lock WAL; dropping encoded
    # vectors wastes a full CUDA batch and collapses util to 0% (needle: 2.8b
    # @528/s then "db busy" → emergency beep with 123k pending left).
    stored = 0
    last_lock_exc: Exception | None = None
    for attempt in range(8):
        try:
            conn = _connect_db(busy_ms=min(60000, 8000 + attempt * 4000))
            try:
                stored = _store_embeddings(
                    conn,
                    model=model_id,
                    items=list(zip(ids, vectors, strict=False)),
                )
            finally:
                conn.close()
            last_lock_exc = None
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            last_lock_exc = exc
            time.sleep(min(1.5, 0.12 * (2**attempt)))
    if last_lock_exc is not None:
        _log(f"db busy on store — retry next burst ({last_lock_exc})", log_fn)
        return {"skipped": True, "reason": "database is locked", "encoded": len(vectors)}
    elapsed = time.time() - started
    rate = stored / elapsed if elapsed > 0 else 0.0
    if stored > 0:
        _LAST_EMBED_TS = time.time()
        _LAST_EMBED_N = int(stored)
    _log(f"embedded {stored} chunks ({model_id.split('/')[-1]}) @ {rate:.1f}/s on {kcfg.mamba_device()}", log_fn)
    # Immediately after a successful batch — safe to drop orphaned reserved.
    # Soft reclaim's 8s hot-window would never fire under continuous embed
    # (needle 2026-09-08: reserved climbed 6→36GB while embeds every ~20s).
    if stored > 0:
        try:
            import torch

            if torch.cuda.is_available():
                allocated = float(torch.cuda.memory_allocated()) / (1024 * 1024)
                reserved = float(torch.cuda.memory_reserved()) / (1024 * 1024)
                if reserved - allocated >= 8192.0:
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                    after = float(torch.cuda.memory_reserved()) / (1024 * 1024)
                    if reserved - after >= 256:
                        _log(
                            f"cuda post-embed reclaim: reserved {reserved:.0f}→{after:.0f}MB "
                            f"(alloc {allocated:.0f}MB)",
                            log_fn,
                        )
        except Exception:  # noqa: BLE001
            pass
    report = {
        "embedded": stored,
        "elapsed_sec": round(elapsed, 2),
        "rate_per_sec": round(rate, 1),
        "model": model_id,
        "device": kcfg.mamba_device(),
        "last_embed_ts": _LAST_EMBED_TS,
    }
    try:
        import dgx_gpu_events as gev

        snap = gev.gpu_snapshot()
        if (
            gev.synthetic_sustain_enabled()
            and not gev.gpu_unavailable(snap=snap)
            and not gev.at_target(snap=snap)
            and float(snap.get("gpu_util_pct") or 0) < gev.throttle_util_pct(snap=snap)
        ):
            report["top_up"] = sustain_until_target(log_fn=log_fn, max_sec=8.0)
    except ImportError:
        pass
    return report


def status() -> dict[str, Any]:
    report: dict[str, Any] = {
        "enabled": enabled(),
        "embed_batch": embed_batch_size(),
        "interval_sec": cycle_interval_sec(),
        "mamba": kmamba.status(),
        "updated_at": time.time(),
    }
    db = kcfg.db_path()
    if db.is_file():
        try:
            conn = _connect_db(busy_ms=2000)
            try:
                _ensure_embedding_schema(conn)
                model = kcfg.cascade_student_model() if kcfg.mamba_cascade_enabled() else (kcfg.mamba_model() or "")
                total = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
                done = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?", (model,)
                    ).fetchone()[0]
                )
                report["chunks_total"] = total
                report["chunks_embedded"] = done
                report["chunks_pending"] = max(0, total - done)
                if kcfg.mamba_cascade_enabled():
                    pending_by_model: dict[str, int] = {}
                    embedded_by_model: dict[str, int] = {}
                    for mid, _comp in _embed_model_queue():
                        embedded = int(
                            conn.execute(
                                "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?", (mid,)
                            ).fetchone()[0]
                        )
                        embedded_by_model[mid] = embedded
                        pending_by_model[mid] = max(0, total - embedded)
                    report["pending_by_model"] = pending_by_model
                    report["embedded_by_model"] = embedded_by_model
                    report["chunks_pending"] = sum(pending_by_model.values())
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            report["db_error"] = str(exc)
    try:
        import torch

        if torch.cuda.is_available():
            report["cuda"] = {
                "device": torch.cuda.get_device_name(0),
                "memory_allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 1),
                "memory_reserved_mb": round(torch.cuda.memory_reserved() / (1024 * 1024), 1),
            }
    except ImportError:
        pass
    try:
        path = auto.CONFIG_DIR / "gpu-compute-status.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # ONLY the forever worker may persist status. One-shot --status probes
        # share no CUDA context and were writing mamba.loaded=false over a live
        # 17GB resident worker — false boost beep / development_allowed flip.
        forever = (
            "--forever" in sys.argv
            or os.environ.get("DGX_GPU_COMPUTE_FORCE", "").strip().lower() in ("1", "true", "yes")
        )
        if forever:
            mamba = report.get("mamba") or {}
            cuda = report.get("cuda") or {}
            loaded = bool(mamba.get("loaded"))
            # CUDA RSS / allocated memory is the live signal — _MODEL can briefly
            # read None across cascade tier switches while VRAM stays hot.
            if not loaded and float(cuda.get("memory_allocated_mb") or 0) > 128:
                loaded = True
            if not loaded:
                try:
                    import dgx_gpu_events as gev

                    if gev._compute_process_vram_mib() >= 1500:
                        loaded = True
                except Exception:  # noqa: BLE001
                    pass
            lean = {
                "enabled": True,
                "updated_at": report.get("updated_at"),
                "chunks_pending": report.get("chunks_pending"),
                "chunks_embedded": report.get("chunks_embedded"),
                "chunks_total": report.get("chunks_total"),
                "mamba": {"loaded": loaded},
                "cuda": cuda,
                "db_error": report.get("db_error"),
                "last_embed_ts": _LAST_EMBED_TS or None,
                "last_embed_n": _LAST_EMBED_N or None,
            }
            payload = __import__("json").dumps(lean)
            path.write_text(payload)
            # Mirror into sibling namespace — stale automation/ status was
            # greenwashing unloaded while hub worker was productive (false beep).
            alt = Path.home() / ".config" / "automation" / "gpu-compute-status.json"
            if alt != path:
                try:
                    alt.parent.mkdir(parents=True, exist_ok=True)
                    alt.write_text(payload)
                except OSError:
                    pass
    except OSError:
        pass
    return report


def _touch_status_heartbeat() -> None:
    """Lightweight mtime/updated_at refresh — no SQLite COUNTs.

    Needle: multi-minute 790m encode left status stale → embed_productive False
    → emergency beep → INFRA restart mid-teacher.
    """
    now = time.time()
    try:
        import torch

        cuda: dict[str, Any] = {}
        if torch.cuda.is_available():
            cuda = {
                "device": torch.cuda.get_device_name(0),
                "memory_allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 1),
                "memory_reserved_mb": round(torch.cuda.memory_reserved() / (1024 * 1024), 1),
            }
    except ImportError:
        cuda = {}
    lean = {
        "enabled": True,
        "updated_at": now,
        "mamba": {"loaded": True},
        "cuda": cuda,
        "last_embed_ts": _LAST_EMBED_TS or None,
        "last_embed_n": _LAST_EMBED_N or None,
        "heartbeat_only": True,
    }
    # Preserve last known queue counters when present.
    for path in (
        auto.CONFIG_DIR / "gpu-compute-status.json",
        Path.home() / ".config" / "automation" / "gpu-compute-status.json",
    ):
        try:
            if path.is_file():
                prev = json.loads(path.read_text())
                if isinstance(prev, dict):
                    for key in (
                        "chunks_pending",
                        "chunks_embedded",
                        "chunks_total",
                        "pending_by_model",
                        "embedded_by_model",
                    ):
                        if key in prev and key not in lean:
                            lean[key] = prev[key]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(lean))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue


def run_embed_burst(*, log_fn: Callable[[str], None] = print, max_sec: float | None = None) -> dict[str, Any]:
    """Back-to-back embed cycles — keeps GPU busy between nvidia-smi samples."""
    burst_sec = embed_burst_sec() if max_sec is None else max(0.0, float(max_sec))
    if burst_sec <= 0:
        one = run_embed_cycle(log_fn=log_fn)
        return {"embedded_total": int(one.get("embedded") or 0), "cycles": 1, "reports": [one]}
    started = time.time()
    total = 0
    cycles: list[dict[str, Any]] = []
    empty_streak = 0
    heartbeat_every = 2
    while time.time() - started < burst_sec:
        try:
            report = run_embed_cycle(log_fn=log_fn)
        except sqlite3.OperationalError as exc:
            # DB locked by knowledge_index — brief yield, keep burst alive.
            _log(f"burst yield — {exc}", log_fn)
            time.sleep(0.35)
            empty_streak += 1
            if empty_streak >= 12:
                break
            continue
        cycles.append(report)
        n = int(report.get("embedded") or 0)
        # Keep status mtime fresh mid-burst so embed_productive stays true
        # during multi-minute teacher encode (status-only COUNT used to lag 90s+).
        if len(cycles) % heartbeat_every == 0 or n > 0:
            try:
                _touch_status_heartbeat()
            except Exception:  # noqa: BLE001
                pass
        if report.get("skipped"):
            reason = str(report.get("reason") or "")
            if "duplicate" in reason:
                break
            # DB lock after a successful encode — keep burst hot; do not treat as empty.
            if "locked" in reason or int(report.get("encoded") or 0) > 0:
                empty_streak = max(0, empty_streak - 1)
                time.sleep(0.25)
                continue
            empty_streak += 1
            if empty_streak >= 12:
                break
            time.sleep(0.2)
            continue
        if n <= 0:
            # Model switch / brief empty — don't abort while cascade pending remains.
            pending = int(report.get("pending") or report.get("chunks_pending") or 0)
            empty_streak += 1
            if pending <= 0 and empty_streak >= 3:
                break
            if empty_streak >= 16:
                break
            time.sleep(0.15)
            continue
        empty_streak = 0
        total += n
        # Mid-burst soft reclaim — long bursts park 20–40GB reserved and freeze
        # anon fill at ~50GB (needle 2026-09-07). Orphaned park only.
        if n > 0 and len(cycles) % 2 == 0:
            try:
                import dgx_ram_budget as _rb_burst

                if float(_rb_burst.footprint_gb()) < 97.0:
                    reclaim_cuda_allocator_cache(log_fn=log_fn, min_slack_mb=16384.0)
            except Exception:  # noqa: BLE001
                pass
    return {
        "embedded_total": total,
        "cycles": len(cycles),
        "elapsed_sec": round(time.time() - started, 2),
        "last": cycles[-1] if cycles else {},
    }


def run_forever() -> None:
    if not _singleton_lock():
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  gpu_compute: duplicate --forever — exit", file=sys.stderr)
        raise SystemExit(0)
    _log("forever loop started")
    # Prefer OOM-kill elsewhere — mid-load SIGKILL leaves permanent 0% util beep.
    try:
        Path("/proc/self/oom_score_adj").write_text("-800")
    except OSError:
        pass
    # Models are hub-cached on this host. Never block forever on CloudFront
    # CLOSE-WAIT (needle: weights hit 100% then hang → 0% util for minutes).
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # Prefer returning unused blocks to the driver — teacher warmups otherwise
    # leave ~20GB+ reserved while student embed only needs ~256MB.
    os.environ.setdefault(
        "PYTORCH_CUDA_ALLOC_CONF",
        "expandable_segments:True,max_split_size_mb:512",
    )
    # systemd --forever is the enable signal; don't idle on config flip races.
    # Overwrite blank FORCE= from unit files so setdefault is not a no-op.
    if os.environ.get("DGX_GPU_COMPUTE_FORCE", "").strip() in ("", "0", "false", "no"):
        os.environ["DGX_GPU_COMPUTE_FORCE"] = "1"
    else:
        os.environ.setdefault("DGX_GPU_COMPUTE_FORCE", "1")
    _force_cuda_device(log_fn=_log)
    # Pin live CFG BEFORE health cap — otherwise default 0.28 locks SM util at
    # idle after preload (needle: "capped at 28%" then 0%/14W with 70k+ pending).
    try:
        dc = auto.CFG.setdefault("dgx_compute", {})
        if isinstance(dc, dict):
            dc["enabled"] = True
            dc["gpu_sustain_when_idle"] = False
            dc["preload_mamba"] = True
            # Soft reclaim: orphaned reserved only when MemAvailable tight (keeps
            # allocated teacher weights). Hard reclaim stays off.
            dc["cuda_reclaim_enabled"] = False
            dc["cuda_soft_reclaim"] = True
            # Keep live 2.8b-4bit (~1.8GB) + modest activation pad — not 30–60GB orphan.
            dc["cuda_keep_reserved_mb"] = min(
                max(float(dc.get("cuda_keep_reserved_mb") or 4096), 3072), 5120
            )
            # Cap ≤0.32 (~38GB on 121GB GB10). 0.45 allowed 45–57GB reserved and
            # OOM-killed ram_events anon climb (needle 2026-09-08: fp 99→54).
            dc["cuda_memory_fraction_max"] = min(
                float(dc.get("cuda_memory_fraction_max") or 0.32), 0.32
            )
            dc["cuda_memory_fraction_max"] = max(float(dc["cuda_memory_fraction_max"]), 0.28)
            # Modest batches — 256+/768 first encode OOM-kills 2.8b on unified GB10.
            dc["embed_burst_sec"] = max(float(dc.get("embed_burst_sec") or 0), 90)
            dc["gpu_embed_batch"] = max(int(dc.get("gpu_embed_batch") or 0), 64)
            dc["gpu_embed_batch"] = min(int(dc["gpu_embed_batch"]), 128)
            dc["gpu_embed_batch_2_8b"] = min(
                max(int(dc.get("gpu_embed_batch_2_8b") or 40), 32), 48
            )
            dc["gpu_embed_interval_sec"] = min(float(dc.get("gpu_embed_interval_sec") or 0.2), 0.02)
            dc["prefer_teachers_when_student_below"] = max(
                int(dc.get("prefer_teachers_when_student_below") or 0), 50000
            )
            # Seed 2.8b cursor at first gap — NOT MAX-4096.
            try:
                db = kcfg.db_path()
                if db.is_file():
                    conn = _connect_db(busy_ms=2500)
                    try:
                        mid = "state-spaces/mamba-2.8b-hf"
                        mx_e = int(
                            (
                                conn.execute(
                                    "SELECT MAX(chunk_id) FROM chunk_embeddings WHERE model = ?",
                                    (mid,),
                                ).fetchone()
                                or [0]
                            )[0]
                            or 0
                        )
                        mx_c = int(
                            (conn.execute("SELECT MAX(id) FROM chunks").fetchone() or [0])[0]
                            or 0
                        )
                        if mx_e > 0 and mx_c > 0 and mx_e >= mx_c:
                            gap = conn.execute(
                                """
                                SELECT MIN(c.id) FROM chunks c
                                WHERE NOT EXISTS (
                                  SELECT 1 FROM chunk_embeddings e
                                  WHERE e.chunk_id = c.id AND e.model = ?
                                )
                                """,
                                (mid,),
                            ).fetchone()
                            if gap and gap[0]:
                                _PENDING_CURSOR[mid] = max(0, int(gap[0]) - 1)
                                _log(f"cursor seed {mid.split('/')[-1]} @ first gap {int(gap[0])}")
                            else:
                                _PENDING_CURSOR[mid] = 0
                        elif mx_e > 0:
                            _PENDING_CURSOR[mid] = max(0, mx_e - 4096)
                    finally:
                        conn.close()
            except Exception:  # noqa: BLE001
                pass
        ge = auto.CFG.setdefault("gpu_events", {})
        if isinstance(ge, dict):
            ge["cursor_agent"] = False
            ge["synthetic_sustain_enabled"] = False
            ge["restart_cooldown_sec"] = max(float(ge.get("restart_cooldown_sec") or 0), 3600)
            ge["util_proxy_power_idle_w"] = min(float(ge.get("util_proxy_power_idle_w") or 14.5), 14.5)
            ge["util_proxy_power_loaded_w"] = min(
                max(float(ge.get("util_proxy_power_loaded_w") or 24), 22.0), 28.0
            )
            ge["emergency_embed_burst_sec"] = max(
                float(ge.get("emergency_embed_burst_sec") or 0), 180
            )
            # Mult≤1.0 — 2.5× OOM-kills mid first encode.
            ge["emergency_embed_batch_mult"] = min(
                max(float(ge.get("emergency_embed_batch_mult") or 1.0), 1.0), 1.0
            )
            ge["productive_embed_batch_max"] = min(
                max(int(ge.get("productive_embed_batch_max") or 128), 64), 128
            )
        rp = auto.CFG.setdefault("resource_priority", {})
        if isinstance(rp, dict):
            rp["resource_fix_cooldown_sec"] = max(
                float(rp.get("resource_fix_cooldown_sec") or 0), 86400
            )
        _log("gpu_compute: pinned live CFG (reclaim off, batch≤128/2.8b≤48, burst≥90s, INFRA cooldown 24h)")
    except Exception as exc:  # noqa: BLE001
        _log(f"gpu_compute: CFG pin failed — {exc}")
    apply_gpu_health_cap(log_fn=_log)
    # Always preload on the forever worker — config flip must not skip CUDA resident.
    preload_ok = False
    try:
        preload_ok = bool(_ensure_mamba_loaded(log_fn=_log))
    except Exception as exc:  # noqa: BLE001
        _log(f"preload exception — {exc}")
    if not preload_ok:
        _log("preload incomplete — will retry each cycle (offline hub)")
    # Do NOT force-reclaim after student preload — cascade immediately loads
    # teacher and empty_cache→1.5GB causes 0.4/s embeds + memory thrash.
    try:
        status()  # persist pending/enabled so resource_priority sees productive embed
    except Exception:  # noqa: BLE001
        pass
    # First productive burst BEFORE gpu_events — handle_events used to credit
    # false hold @ 0%/14W after preload and delay encode for minutes (needle
    # 2026-09-08: preload then silence, RSS collapse, development_allowed).
    try:
        _log("gpu_compute: first productive embed burst (skip events until hot)")
        run_embed_burst(log_fn=_log, max_sec=max(45.0, float(embed_burst_sec())))
        status()
    except Exception as exc:  # noqa: BLE001
        _log(f"first embed burst failed — {exc}")
    while True:
        if not enabled():
            # Re-arm FORCE each idle tick — agents keep flipping local.json enabled:false.
            os.environ["DGX_GPU_COMPUTE_FORCE"] = "1"
            if not enabled():
                time.sleep(5)
                continue
        burst_sec = 0.0
        embed_hot = bool(_LAST_EMBED_TS) and (time.time() - _LAST_EMBED_TS) < 120.0
        try:
            import dgx_gpu_events as gev

            # Skip event handle until embeds are landing — avoids false hold and
            # INFRA restart thrash while first teacher encode warms SMs.
            if gev.enabled() and embed_hot:
                gev.handle_events(log_fn=_log, skip_cursor_agent=True, skip_restart=True)
                snap = gev.gpu_snapshot()
                scale = gev.thermal_scale(snap=snap)
                temp = float(snap.get("gpu_temp_c") or 0)
                if gev.over_max(snap=snap) or scale <= 0.0:
                    _log(
                        f"thermal cool-down — {temp:.0f}C "
                        f"(crit {gev.temp_critical_c():.0f}C) scale={scale:.2f}"
                    )
                    apply_gpu_health_cap(log_fn=_log)
                    time.sleep(max(3.0, cycle_interval_sec() * 2))
                    continue
                if scale < 0.5:
                    _log(f"thermal pullback — {temp:.0f}C scale={scale:.2f}")
                    apply_gpu_health_cap(log_fn=_log)
                burst_sec = embed_burst_sec() * scale
                if (
                    gev.synthetic_sustain_enabled()
                    and not gev.at_target(snap=snap)
                    and not gev.over_max(snap=snap)
                    and float(snap.get("gpu_util_pct") or 0) < gev.throttle_util_pct(snap=snap)
                    and scale > 0.15
                ):
                    sustain_burst(
                        log_fn=_log,
                        passes=int(gev.sustain_params(snap=snap).get("sustain_passes") or 1),
                    )
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            _log(f"gpu events error — {exc}")
        try:
            min_burst = 0.0
            try:
                import dgx_gpu_events as gev

                mode = gev.gpu_mode()
                if mode in ("emergency", "pressure", "boost") or not embed_hot:
                    # Emergency/pressure/cold: long productive bursts — not synthetic GEMM.
                    min_burst = max(min_burst, float(embed_burst_sec()) * 0.85)
                elif mode == "hold":
                    # Hold must not idle between samples — productive queue stays hot.
                    min_burst = max(min_burst, max(12.0, float(embed_burst_sec()) * 0.5))
            except ImportError:
                pass
            # Override thermal soft-guard may set burst→floor; never fall to single-cycle idle
            # while chunks remain (needle: 96%→0% boom-bust).
            burst = max(burst_sec, min_burst)
            if burst < 4.0:
                burst = max(burst, 20.0)
            # Keep back-to-back embed hot — GB10 samples 0% between short bursts.
            burst = max(burst, 24.0)
            if burst > 0:
                run_embed_burst(log_fn=_log, max_sec=burst)
            else:
                run_embed_cycle(log_fn=_log)
            # Soft reclaim between batches when under ~100GB footprint.
            # Outer embed_hot(120s) used to skip reclaim entirely while 18–45GB
            # orphaned CUDA reserved parked MemAvailable and OOM-killed ram_events
            # (needle 2026-09-08: fp 82→50 after teacher reserved 45GB).
            # reclaim_cuda_allocator_cache already no-ops <8s after last embed.
            try:
                import dgx_ram_budget as _rb

                fp = float(_rb.footprint_gb())
                avail = float(_rb.mem_stats()["avail_gb"])
            except Exception:  # noqa: BLE001
                fp, avail = 100.0, 99.0
            # Always soft-reclaim orphan reserved after a burst when under target
            # or MemAvailable is tight — do not wait for a long idle gap.
            if fp < 97.0 or avail < 16.0:
                reclaim_cuda_allocator_cache(log_fn=_log, min_slack_mb=6144.0)
            elif fp >= 100.0 and avail < 8.0:
                reclaim_cuda_allocator_cache(log_fn=_log, min_slack_mb=4096.0)
            if bool(_compute_cfg().get("cuda_reclaim_enabled", False)) and (
                not _LAST_EMBED_TS or time.time() - _LAST_EMBED_TS >= 120.0
            ):
                reclaim_cuda_allocator_cache(log_fn=_log, min_slack_mb=16384.0)
            try:
                status()
            except Exception:  # noqa: BLE001
                pass
        except sqlite3.OperationalError as exc:
            _log(f"cycle error — {exc}")
            time.sleep(0.4)
        except Exception as exc:  # noqa: BLE001
            _log(f"cycle error — {exc}")
            time.sleep(0.5)
        # Tiny yield only — long sleeps create pressure dips at 40–55% raw util.
        time.sleep(min(0.08, effective_cycle_interval_sec()))


def main() -> int:
    parser = argparse.ArgumentParser(description="DGX GPU batch embedding worker")
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--gpu-events", action="store_true", help="Run GPU event trigger cycle")
    parser.add_argument("--gpu-snapshot", action="store_true", help="Print GPU util snapshot JSON")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.gpu_snapshot:
        import dgx_gpu_events as gev

        print(json.dumps(gev.snapshot(), indent=2))
        return 0
    if args.gpu_events:
        import dgx_gpu_events as gev

        report = gev.handle_events(log_fn=lambda m: None if args.json else print(m))
        if args.json:
            print(json.dumps(report, indent=2))
        return 0
    if args.status or args.json:
        payload = status()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"gpu_compute: embedded {payload.get('chunks_embedded', '?')}/"
                f"{payload.get('chunks_total', '?')} batch={payload.get('embed_batch')}"
            )
        return 0
    if args.forever:
        run_forever()
        return 0
    report = run_embed_cycle()
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
