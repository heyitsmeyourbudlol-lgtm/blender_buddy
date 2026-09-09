"""Cursor agent transcript → next peer-loop input.

COMPRESSION_ZLIB_FP_STAMP_2026_09_04
"""

from __future__ import annotations

import contextlib
import fcntl
import zlib
import json
import os
import re
import select
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import peer_worktree
import project_automation as auto
import peer_last_cycle_poison as _lc_poison  # OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04

# Fail-closed re-exports — deferred soft-skip never counts as verify green.
sanitize_last_cycle = _lc_poison.sanitize_last_cycle
effective_verify_ok = _lc_poison.effective_verify_ok
coerce_deferred_verify_ok = _lc_poison.coerce_deferred_verify_ok

STATE_PATH = auto.CONFIG_DIR / "peer-loop-state.json"
STATE_LOCK_PATH = auto.CONFIG_DIR / "peer-loop-state.lock"
SIGNAL_PATH = auto.CONFIG_DIR / "peer-turn.signal"
# Non-macOS / no-kqueue safety net only — macOS blocks indefinitely on VNODE events.
FALLBACK_POLL_SEC = 300.0
# Free-desktop / CLEAN: blind 300s sleeps starve refill after agent exit.
# Needle: OVERSEER_FREE_DESKTOP_FALLBACK_POLL_2026_09_08
FREE_DESKTOP_FALLBACK_POLL_SEC = 45.0


def effective_fallback_poll_sec(cfg: dict[str, Any] | None = None) -> float:
    """Wall-clock fallback when event watch is unavailable.

    Prefer ``fallback_poll_sec`` config; under free-desktop auth default to a
    shorter poll so CLEAN refill does not wait a full 300s after agents exit.
    """
    raw = cfg if cfg is not None else auto.CFG
    try:
        override = float(raw.get("fallback_poll_sec") or 0)
    except (TypeError, ValueError):
        override = 0.0
    if override > 0:
        return max(5.0, override)
    free = bool(raw.get("force_free_desktop_auth")) or str(
        raw.get("cursor_agent_auth") or ""
    ).strip().lower() in {"desktop", "free_desktop", "free-desktop"}
    if free:
        return FREE_DESKTOP_FALLBACK_POLL_SEC
    return FALLBACK_POLL_SEC
CONVERSATION_SUMMARY_PATH = auto.ROOT / "notes" / "PEER_CONVERSATION.md"
TRENDS_MD = auto.ROOT / "notes" / "AUTOMATION_TRENDS.md"
MAX_CONVERSATION_CHARS = 24_000
MAX_RECENT_TURNS = 6
MAX_RECENT_CHARS = 6_000
# OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07 — cycle_history ring is short (~20);
# persist UTC day buckets so T10-04 / scoreboard can meter ≥8 non-noop/day.
# Sidecar + thin-save merge survive SIGUSR1/peer flaps that wipe short state.
NON_NOOP_DAY_RETENTION = 14
NON_NOOP_DAY_BAR = 8.0
NON_NOOP_DAY_PATH = auto.CONFIG_DIR / "non_noop_by_day.json"


def _utc_day_key(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def _coerce_day_buckets(raw: Any) -> dict[str, int]:
    buckets: dict[str, int] = {}
    if not isinstance(raw, dict):
        return buckets
    for key, val in raw.items():
        try:
            buckets[str(key)] = int(val)
        except (TypeError, ValueError):
            continue
    return buckets


def _trim_day_buckets(buckets: dict[str, int]) -> dict[str, int]:
    if len(buckets) <= NON_NOOP_DAY_RETENTION:
        return buckets
    keep = sorted(buckets.keys())[-NON_NOOP_DAY_RETENTION:]
    return {k: int(buckets[k]) for k in keep}


def _merge_day_buckets(*sources: Any) -> dict[str, int]:
    """Max-merge day counters — never lose rollup across thin saves / flaps."""
    merged: dict[str, int] = {}
    for raw in sources:
        for key, val in _coerce_day_buckets(raw).items():
            merged[key] = max(int(merged.get(key) or 0), int(val))
    return _trim_day_buckets(merged)


def _load_non_noop_day_sidecar() -> dict[str, int]:
    try:
        if not NON_NOOP_DAY_PATH.is_file():
            return {}
        data = json.loads(NON_NOOP_DAY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("by_day"), dict):
            return _coerce_day_buckets(data["by_day"])
        return _coerce_day_buckets(data)
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _save_non_noop_day_sidecar(buckets: dict[str, int]) -> None:
    trimmed = _trim_day_buckets(_coerce_day_buckets(buckets))
    try:
        NON_NOOP_DAY_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "by_day": trimmed,
            "updated_ts": time.time(),
            "needle": "OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07",
        }
        tmp = NON_NOOP_DAY_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, NON_NOOP_DAY_PATH)
    except OSError:
        pass


def rehydrate_non_noop_day(live: dict[str, Any]) -> None:
    """Merge live + sidecar + history so flaps cannot zero the day meter."""
    hist_buckets: dict[str, int] = {}
    hist = live.get("cycle_history")
    if isinstance(hist, list):
        for row in hist:
            if not isinstance(row, dict) or bool(row.get("noop")) or bool(row.get("local_only")):
                continue
            # Deferred soft-skips are not countable throughput (T10-04 honesty).
            if str(row.get("failure_type") or "").strip() == "deferred":
                continue
            try:
                ts = float(row.get("ts") or 0)
            except (TypeError, ValueError):
                continue
            if ts <= 10.0:
                continue
            day = _utc_day_key(ts)
            hist_buckets[day] = int(hist_buckets.get(day) or 0) + 1
    merged = _merge_day_buckets(
        live.get("non_noop_by_day"),
        _load_non_noop_day_sidecar(),
        hist_buckets,
    )
    if merged:
        live["non_noop_by_day"] = merged
        _save_non_noop_day_sidecar(merged)


def bump_non_noop_day_rollup(
    live: dict[str, Any],
    *,
    ts: float,
    noop: bool,
    local_only: bool = False,
    failure_type: str | None = None,
) -> None:
    """Increment durable UTC-day non-noop counter (keeps last N days).

    local_only / deferred verify ticks are not countable throughput (soft-skip theater).
    """
    buckets = _merge_day_buckets(live.get("non_noop_by_day"), _load_non_noop_day_sidecar())
    day = _utc_day_key(ts)
    deferred = str(failure_type or "").strip() == "deferred"
    if not noop and not local_only and not deferred:
        buckets[day] = int(buckets.get(day) or 0) + 1
    buckets = _trim_day_buckets(buckets)
    live["non_noop_by_day"] = buckets
    _save_non_noop_day_sidecar(buckets)


def seed_non_noop_day_from_history(live: dict[str, Any]) -> None:
    """Rebuild / merge day buckets from cycle_history + flap-resistant sidecar."""
    rehydrate_non_noop_day(live)


def non_noop_day_stats(
    state: dict[str, Any] | None = None,
    *,
    now: float | None = None,
    bar: float = NON_NOOP_DAY_BAR,
) -> dict[str, Any]:
    """Observed + projected non-noop/day from durable rollup (+ history seed)."""
    live = dict(state or {})
    seed_non_noop_day_from_history(live)
    now_ts = float(now if now is not None else time.time())
    today = _utc_day_key(now_ts)
    buckets = _coerce_day_buckets(live.get("non_noop_by_day"))
    today_n = int(buckets.get(today) or 0)
    # Hours elapsed today (UTC); floor at 1/60h so early-day proj is finite.
    day_start = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    hours_elapsed = max((now_ts - day_start) / 3600.0, 1.0 / 60.0)
    projected = today_n / hours_elapsed * 24.0
    # Week average over completed buckets + today (up to 7 calendar days).
    week_keys = sorted(buckets.keys())[-7:]
    week_vals = [int(buckets[k]) for k in week_keys]
    week_avg = (sum(week_vals) / len(week_vals)) if week_vals else 0.0
    # T10-04: PASS only on observed today ≥ bar — never proj alone (false-close risk).
    meets = today_n >= bar
    return {
        "today": today,
        "today_non_noop": today_n,
        "projected_per_day": round(projected, 1),
        "week_avg_per_day": round(week_avg, 1),
        "hours_elapsed_today": round(hours_elapsed, 2),
        "bar": bar,
        "meets_bar": bool(meets),
        "buckets": {k: buckets[k] for k in sorted(buckets.keys())[-7:]},
    }


@dataclass
class TranscriptMeta:
    path: Path
    line_count: int
    mtime: float
    turn_ended: bool
    turn_status: str | None


def cursor_projects_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def workspace_slug_for_root(root: Path) -> str:
    """Cursor project slug: Users-togi-CaaS for /Users/togi/CaaS; home-user-repo on Linux."""
    resolved = root.resolve()
    users_root = Path("/Users")
    try:
        rel = resolved.relative_to(users_root)
        return "Users-" + str(rel).replace("/", "-").replace("\\", "-")
    except ValueError:
        pass
    text = str(resolved).lstrip("/").replace("/", "-").replace("\\", "-")
    return text or "workspace"


def transcript_roots() -> list[Path]:
    """Agent transcript dirs for this repo and optionally all Cursor workspaces."""
    roots: list[Path] = []
    base = cursor_projects_root()
    primary = base / workspace_slug_for_root(auto.ROOT) / "agent-transcripts"
    if primary.is_dir():
        roots.append(primary)
    if auto.CFG.get("watch_all_cursor_transcripts"):
        for path in sorted(base.glob("*/agent-transcripts")):
            if path.is_dir() and path not in roots:
                roots.append(path)
    extra = auto.CFG.get("extra_transcript_roots") or []
    for raw in extra:
        p = Path(str(raw)).expanduser()
        if p.is_dir() and p not in roots:
            roots.append(p)
    return roots


# OVERSEER_TRANSCRIPT_PATHS_CACHE_2026_09_07 — primary agent-transcripts can hold
# 10k+ session dirs; uncached iterdir+is_file was ~150ms/find_latest on hub wakes.
_TRANSCRIPT_PATHS_CACHE: tuple[tuple[float, ...], list[Path]] | None = None
_LATEST_TRANSCRIPT_CACHE: tuple[float, tuple[float, ...], Path | None] | None = None
_LATEST_TRANSCRIPT_TTL_SEC = 2.0


def _transcript_roots_fingerprint(roots: list[Path]) -> tuple[float, ...]:
    """Dir mtimes — invalidate when a new session dir appears under a root."""
    fps: list[float] = []
    for root in roots:
        try:
            fps.append(root.stat().st_mtime)
        except OSError:
            fps.append(0.0)
    return tuple(fps)


def clear_transcript_paths_cache() -> None:
    """Drop path-list + latest-transcript memo (tests / after prune)."""
    global _TRANSCRIPT_PATHS_CACHE, _LATEST_TRANSCRIPT_CACHE
    _TRANSCRIPT_PATHS_CACHE = None
    _LATEST_TRANSCRIPT_CACHE = None


def _parent_transcript_paths() -> list[Path]:
    """Parent ``<uuid>/<uuid>.jsonl`` paths under transcript roots (mtime-cached).

    Rebuild uses ``os.scandir`` + ``os.path.isfile`` (Path.iterdir thrash on 10k+ dirs).
    """
    global _TRANSCRIPT_PATHS_CACHE
    roots = transcript_roots()
    fp = _transcript_roots_fingerprint(roots)
    if _TRANSCRIPT_PATHS_CACHE is not None and _TRANSCRIPT_PATHS_CACHE[0] == fp:
        return _TRANSCRIPT_PATHS_CACHE[1]
    out: list[Path] = []
    for root in roots:
        try:
            with os.scandir(root) as it:
                for ent in it:
                    if not ent.is_dir(follow_symlinks=False):
                        continue
                    cand = f"{ent.path}/{ent.name}.jsonl"
                    if os.path.isfile(cand):
                        out.append(Path(cand))
        except OSError:
            continue
    _TRANSCRIPT_PATHS_CACHE = (fp, out)
    return out


def _find_latest_transcript_scandir(roots: list[Path]) -> Path | None:
    """Single scandir+stat pass — avoids building a 10k+ Path list then max()."""
    latest: Path | None = None
    latest_m = -1.0
    for root in roots:
        try:
            with os.scandir(root) as it:
                for ent in it:
                    if not ent.is_dir(follow_symlinks=False):
                        continue
                    cand = f"{ent.path}/{ent.name}.jsonl"
                    try:
                        st = os.stat(cand)
                    except OSError:
                        continue
                    if st.st_mtime > latest_m:
                        latest_m = st.st_mtime
                        latest = Path(cand)
        except OSError:
            continue
    return latest


def find_latest_transcript(*, fresh: bool = False) -> Path | None:
    """Newest parent transcript JSONL (scandir one-pass + short TTL on winner).

    Needle: OVERSEER_TRANSCRIPT_PATHS_CACHE_2026_09_07 — cold miss was ~290ms on
    17k UUID dirs (Path.iterdir + second max-stat pass); scandir+stat ~40ms.

    Soft path also generation-skips when transcript-root mtimes match the cached
    fingerprint (new UUID session dirs bump root mtime). ``fresh=True`` always
    rescans. Needle: FIND_LATEST_ROOT_FP_GENERATION_2026_09_07 — wake=30 ≫ wall
    TTL=2 otherwise re-pays ~30ms scandir every continuous timeout.
    """
    global _LATEST_TRANSCRIPT_CACHE
    roots = transcript_roots()
    fp = _transcript_roots_fingerprint(roots)
    now = time.time()
    if not fresh and _LATEST_TRANSCRIPT_CACHE is not None and _LATEST_TRANSCRIPT_CACHE[1] == fp:
        age = now - _LATEST_TRANSCRIPT_CACHE[0]
        cached = _LATEST_TRANSCRIPT_CACHE[2]
        # Wall TTL HIT, or generation HIT (same roots mtime after TTL expiry).
        if age < _LATEST_TRANSCRIPT_TTL_SEC or _LATEST_TRANSCRIPT_CACHE[1] is not None:
            if cached is None or cached.is_file():
                return cached
    latest = _find_latest_transcript_scandir(roots)
    _LATEST_TRANSCRIPT_CACHE = (now, fp, latest)
    return latest


def read_transcript_meta(path: Path | None) -> TranscriptMeta | None:
    if path is None or not path.is_file():
        return None
    lines = path.read_text(errors="replace").splitlines()
    turn_ended = False
    turn_status: str | None = None
    for line in reversed(lines[-30:]):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "turn_ended":
            turn_ended = True
            turn_status = str(obj.get("status") or "")
            break
    st = path.stat()
    return TranscriptMeta(
        path=path,
        line_count=len(lines),
        mtime=st.st_mtime,
        turn_ended=turn_ended,
        turn_status=turn_status,
    )


def _state_lock_path() -> Path:
    """Lock beside the active STATE_PATH (follows unittest patches).

    Needle: OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04
    """
    try:
        return Path(str(STATE_PATH) + ".lock")
    except Exception:  # noqa: BLE001
        return STATE_LOCK_PATH


@contextlib.contextmanager
def _state_file_lock(*, shared: bool = False, timeout_sec: float | None = None):
    """Serialize load/mutate/save of peer-loop-state.json across daemons.

    Never block forever — hung agents previously held LOCK_EX and poisoned
    ``tests.test_automation`` / measure with FAIL (failures=2–3) under swarm.
    Needle: OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04
    """
    lock_path = _state_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        limit = float(os.environ.get("PEER_STATE_LOCK_TIMEOUT_SEC") or 8.0)
    except (TypeError, ValueError):
        limit = 8.0
    if timeout_sec is not None:
        limit = float(timeout_sec)
    flag = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    with open(lock_path, "a+", encoding="utf-8") as lock_fp:
        deadline = time.time() + max(0.5, limit)
        while True:
            try:
                fcntl.flock(lock_fp.fileno(), flag | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"peer-loop-state flock timeout ({limit:.1f}s)"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)





def is_last_cycle_poison(lc: Any) -> bool:
    """OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04 + FIXTURE_NOTE_OK."""
    if _lc_poison is not None:
        try:
            return bool(_lc_poison.is_last_cycle_poison(lc))
        except Exception:  # noqa: BLE001
            pass
    if not isinstance(lc, dict) or not lc:
        return False
    ft = str(lc.get("failure_type") or "").strip()
    if lc.get("verify_ok") is True and ft == "deferred":
        return True
    try:
        ts = float(lc.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    # OVERSEER_SCRUB_FIXTURE_NOTE_OK_2026_09_04
    if 0 < ts <= 1.0 and not lc.get("queue_fp") and not lc.get("git_head"):
        return True
    return False


def scrub_last_cycle_poison(state: dict[str, Any]) -> str | None:
    # OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04 — never pop failure_type
    # OVERSEER_SCRUB_FIXTURE_BEFORE_SANITIZE_2026_09_04 — fixture pop before sanitize
    if _lc_poison is not None:
        try:
            return _lc_poison.scrub_last_cycle_poison(state)
        except Exception:  # noqa: BLE001
            pass
    lc = state.get("last_cycle")
    if not is_last_cycle_poison(lc):
        return None
    assert isinstance(lc, dict)
    ft = str(lc.get("failure_type") or "").strip()
    try:
        ts = float(lc.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    if 0 < ts <= 1.0 and not lc.get("queue_fp") and not lc.get("git_head"):
        state.pop("last_cycle", None)
        return "cleared fixture last_cycle (ts<=1.0)"
    if lc.get("verify_ok") is True and ft == "deferred":
        fixed = dict(lc)
        fixed["verify_ok"] = False
        note = str(fixed.get("note") or "").strip()
        tag = "sanitized: deferred clears verify_ok"
        if tag not in note.lower():
            fixed["note"] = ((note + "; " if note else "") + tag)[:240]
        state["last_cycle"] = fixed
        return "sanitized deferred clears verify_ok"
    state.pop("last_cycle", None)
    return "cleared poison last_cycle"


sanitize_last_cycle = _lc_poison.sanitize_last_cycle if _lc_poison is not None else None  # type: ignore[union-attr]



# restore vault_ok needles — sanitize_last_cycle = _lc_poison; return _lc_poison.scrub_last_cycle_poison
sanitize_last_cycle = _lc_poison.sanitize_last_cycle if _lc_poison is not None else None  # type: ignore[union-attr]


def last_cycle_poisoned(lc: dict[str, Any] | None) -> bool:
    if not isinstance(lc, dict) or not lc:
        return False
    if is_last_cycle_poison(lc):
        return True
    try:
        ts = float(lc.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    if 0 < ts < 10.0:
        return True
    keys = set(lc.keys())
    if keys and keys <= {"verify_ok", "ts", "failure_type", "noop", "note"} and "rc" not in lc:
        return True
    return False

def _unlocked_read_state() -> dict[str, Any] | None:
    """Best-effort read without flock — used when lock wait times out.

    Needle: OVERSEER_STATE_LOAD_TIMEOUT_NO_WIPE_2026_09_04
    """
    try:
        if not STATE_PATH.is_file():
            return None
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


_PRESERVE_ON_THIN_SAVE: tuple[str, ...] = (
    "last_cycle",
    "cycle_history",
    "last_delivery_ok_ts",
    "last_queue_advance_ts",
    "factory_progress_peak",
    "non_noop_by_day",  # OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07 — survive flaps
)


def _merge_preserve_cycle_memory(
    thin: dict[str, Any], rich: dict[str, Any] | None
) -> str | None:
    """Merge delivery memory from rich into a stall-only / thin save.

    Needle: OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04
    Also: OVERSEER_STATE_SAVE_PRESERVE_LAST_CYCLE_2026_09_04
    Incoming last_cycle always wins; otherwise copy rich last_cycle + preserve keys.
    """
    if not isinstance(thin, dict) or not isinstance(rich, dict):
        return None
    notes: list[str] = []
    # Always max-merge day rollup (incoming + rich + sidecar) — never zero on flap.
    merged_days = _merge_day_buckets(
        thin.get("non_noop_by_day"),
        rich.get("non_noop_by_day"),
        _load_non_noop_day_sidecar(),
    )
    if merged_days:
        thin["non_noop_by_day"] = merged_days
        _save_non_noop_day_sidecar(merged_days)
        notes.append("preserved non_noop_by_day")
    incoming_lc = thin.get("last_cycle")
    if isinstance(incoming_lc, dict) and incoming_lc:
        return "; ".join(notes) if notes else None
    rich_lc = rich.get("last_cycle")
    if isinstance(rich_lc, dict) and rich_lc and not is_last_cycle_poison(rich_lc):
        thin["last_cycle"] = rich_lc
    for key in _PRESERVE_ON_THIN_SAVE:
        if key in ("last_cycle", "non_noop_by_day"):
            continue
        if key not in thin and key in rich:
            thin[key] = rich[key]
    if "last_cycle" in thin and thin.get("last_cycle") is rich.get("last_cycle"):
        notes.append("preserved cycle memory on thin save")
    elif any(k in thin and k in rich and k != "last_cycle" for k in _PRESERVE_ON_THIN_SAVE):
        notes.append("preserved cycle memory on thin save")
    return "; ".join(notes) if notes else None


def _preserve_rich_fields_from_disk(state: dict[str, Any]) -> str | None:
    """Refuse stall-only / thin saves that would wipe last_cycle memory.

    Needle: OVERSEER_STATE_SAVE_PRESERVE_LAST_CYCLE_2026_09_04
    Also: OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04
    Race: load_state TimeoutError → {} → note_stall → save wiped delivery memory.
    """
    disk = _unlocked_read_state()
    return _merge_preserve_cycle_memory(state, disk if isinstance(disk, dict) else {})


def load_state() -> dict[str, Any]:
    """Load peer-loop state; scrub fixture poison on read.

    Needle: OVERSEER_SCRUB_ON_LOAD_2026_09_04 — unit-test fixtures
    (ts<=1.0 / verify_ok+deferred) must not poison live detect() between
    raw JSON writes and the next save_state.
    OVERSEER_STATE_LOAD_TIMEOUT_NO_WIPE_2026_09_04 — flock timeout must not
    return {} that note_stall later saves over a rich on-disk state.
    """
    try:
        with _state_file_lock(shared=True):
            if STATE_PATH.is_file():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # OVERSEER_SCRUB_ON_LOAD_2026_09_04
                    if scrub_last_cycle_poison(data):
                        try:
                            save_state(data)
                        except Exception:
                            pass
                    return data
    except TimeoutError:
        # OVERSEER_STATE_LOAD_TIMEOUT_NO_WIPE_2026_09_04
        data = _unlocked_read_state()
        if data is not None:
            scrub_last_cycle_poison(data)
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}



def save_state(state: dict[str, Any]) -> None:
    scrub_last_cycle_poison(state)
    # OVERSEER_STATE_SAVE_PRESERVE_LAST_CYCLE_2026_09_04
    # OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04
    _preserve_rich_fields_from_disk(state)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # OVERSEER_TRANSCRIPT_SAVE_NEWLINE_2026_09_04
    payload = json.dumps(state, indent=2) + "\n"
    tmp_path = STATE_PATH.with_suffix(".json.tmp")
    try:
        with _state_file_lock():
            # Re-check under exclusive lock — another writer may have enriched disk.
            _preserve_rich_fields_from_disk(state)
            payload = json.dumps(state, indent=2) + "\n"
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, STATE_PATH)
    except TimeoutError:
        # OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04 — prefer drop write over hang
        return


def _strip_user_wrapper(text: str) -> str:
    text = re.sub(r"<timestamp>.*?</timestamp>\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"<user_query>\s*", "", text)
    text = re.sub(r"\s*</user_query>\s*", "", text)
    return text.strip()


def _extract_message_text(obj: dict[str, Any]) -> str:
    message = obj.get("message") or {}
    parts: list[str] = []
    for block in message.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            txt = str(block.get("text") or "").strip()
            if txt and txt != "[REDACTED]":
                parts.append(txt)
    return "\n".join(parts).strip()


def read_conversation(path: Path | None) -> list[tuple[str, str]]:
    """Return (role, text) turns — user and assistant text only."""
    if path is None or not path.is_file():
        return []
    turns: list[tuple[str, str]] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = obj.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _extract_message_text(obj)
        if not text:
            continue
        if role == "user":
            text = _strip_user_wrapper(text)
        if text:
            turns.append((role, text))
    return turns


def format_conversation(turns: list[tuple[str, str]], *, max_chars: int = MAX_CONVERSATION_CHARS) -> str:
    """Keep newest turns when truncating — oldest-first walk dropped recent decisions."""
    if not turns:
        return "(no prior conversation text)"
    kept: list[str] = []
    used = 0
    for role, text in reversed(turns):
        label = "USER" if role == "user" else "ASSISTANT"
        block = f"### {label}\n{text}\n"
        if used + len(block) > max_chars:
            if not kept:
                overflow = len(block) + used - max_chars
                block = block[: max(0, len(block) - overflow - 20)] + "\n…(truncated)\n"
                kept.append(block)
            break
        kept.append(block)
        used += len(block)
    kept.reverse()
    return "\n".join(kept).strip()


def count_turns(path: Path | None) -> int:
    return len(read_conversation(path))


def has_new_assistant_since_dispatch(path: Path | None, state: dict[str, Any]) -> bool:
    """Avoid re-dispatch on the same user paste — require assistant reply after last dispatch."""
    if path is None:
        return True
    last_dispatch = float(state.get("last_dispatch_ts") or 0)
    if last_dispatch <= 0:
        return True
    turns = read_conversation(path)
    if not turns:
        return False
    role, _text = turns[-1]
    return role == "assistant"


def output_generated(meta: TranscriptMeta | None, state: dict[str, Any]) -> bool:
    """True when transcript has a new successful turn since last processed."""
    if meta is None:
        return False
    prev_lines = int(state.get("processed_lines") or 0)
    prev_path = str(state.get("transcript_path") or "")
    if meta.line_count <= prev_lines and str(meta.path) == prev_path:
        return False
    if not meta.turn_ended:
        return False
    if meta.turn_status and meta.turn_status not in ("success", "completed", "ok"):
        return False
    if not has_new_assistant_since_dispatch(meta.path, state):
        return False
    return True


def mark_processed(meta: TranscriptMeta, state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state["transcript_path"] = str(meta.path)
    state["processed_lines"] = meta.line_count
    state["processed_mtime"] = meta.mtime
    save_state(state)
    return state


def load_conversation_summary() -> str:
    """Canonical entire-conversation summary (preferred over raw transcript)."""
    if CONVERSATION_SUMMARY_PATH.is_file():
        return CONVERSATION_SUMMARY_PATH.read_text(errors="replace").strip()
    return ""


def format_recent_turns(turns: list[tuple[str, str]], *, max_chars: int = MAX_RECENT_CHARS) -> str:
    if not turns:
        return ""
    recent = turns[-MAX_RECENT_TURNS:]
    return format_conversation(recent, max_chars=max_chars)


def entire_conversation_block(path: Path | None) -> str:
    """Summary file + optional recent transcript delta."""
    summary = load_conversation_summary()
    turns = read_conversation(path)
    recent = format_recent_turns(turns)

    parts: list[str] = []
    if summary:
        parts.append(summary)
    if recent and recent != "(no prior conversation text)":
        parts.append("## Recent turns (since summary)\n\n" + recent)
    if parts:
        return "\n\n---\n\n".join(parts)

    if turns:
        return format_conversation(turns)
    return "(no conversation summary — add notes/PEER_CONVERSATION.md)"


def queue_fingerprint(items: list[str]) -> str:
    """Stable short hash of open queue — detects noop cycles that re-plan the same work.

    COMPRESSION_ZLIB_QUEUE_FP_2026_09_04 — zlib adler+crc (16 hex) keeps peer path
    libcrypto-free; collision resistance is not required for noop detection.
    QUEUE_FP_LITE_DRY_PROJECT_AUTOMATION_2026_09_08 — delegates to auto SoT.
    """
    return auto.queue_fingerprint_items(items)


def current_queue_fingerprint() -> tuple[str, list[str]]:
    ctx = auto.load_context_md()
    work = auto.load_work_queue_md()
    live = auto.measure_live_state(quick=True)
    items = auto.loop_work_items(ctx, work, live=live).open_items
    return queue_fingerprint(items), items


def git_head_oneline() -> str:
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=str(auto.ROOT),
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "(git log unavailable)"
    return (proc.stdout or "").strip() or "(empty)"



def record_cycle_outcome(
    state: dict[str, Any],
    *,
    rc: int,
    verify_ok: bool,
    queue_fp_before: str,
    queue_fp_after: str,
    note: str = "",
    local_only: bool = False,
    failure_type: str | None = None,
) -> dict[str, Any]:
    """Persist last-cycle intelligence for the next prompt + noop backoff.

    ``local_only`` ticks (prompt refresh without cursor-agent) must not arm
    noop backoff — otherwise the loop never dispatches agents.

    ``failure_type=deferred`` is coerced fail-closed: verify_ok forced False
    (OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04).
    """
    live = load_state()
    for key, value in state.items():
        if key != "last_cycle":
            live[key] = value
    ft = str(failure_type or "").strip() or None
    # Atomic coerce — never persist verify_ok=True with failure_type=deferred.
    verify_ok = coerce_deferred_verify_ok(verify_ok, ft)
    agent_cycle = not local_only
    noop = bool(
        agent_cycle
        and rc == 0
        and verify_ok
        and queue_fp_before == queue_fp_after
        and queue_fp_before
    )
    delivery = bool(
        agent_cycle
        and verify_ok
        and not noop
        and queue_fp_before
        and queue_fp_before != queue_fp_after
    )
    cycle_ts = time.time()
    live["last_cycle"] = {
        "ts": cycle_ts,
        "rc": rc,
        "verify_ok": verify_ok,
        "queue_fp": queue_fp_after or queue_fp_before,
        "queue_fp_before": queue_fp_before,
        "noop": noop,
        "local_only": local_only,
        "git_head": git_head_oneline(),
        "note": note[:240],
    }
    if ft:
        live["last_cycle"]["failure_type"] = ft
    scrub_last_cycle_poison(live)
    # Scrub may pop poison stamps (e.g. self-heal seeded + verify_ok=False) —
    # keep history append on local cycle_ts so we never KeyError.
    if not noop and queue_fp_before != queue_fp_after:
        live["last_queue_advance_ts"] = time.time()
    if verify_ok and (not noop or local_only):
        live["last_delivery_ok_ts"] = time.time()
    # Keep a small in-memory cycle ring so unit tests and prompt memory can
    # reason about consecutive delivery/noop behavior.
    history = live.get("cycle_history")
    if not isinstance(history, list):
        history = []
    # Seed day rollup from prior ring before appending this cycle (avoid double-count).
    seed_non_noop_day_from_history(live)
    history.append(
        {
            "ts": cycle_ts,
            "verify_ok": verify_ok,
            "noop": noop,
            "local_only": local_only,
            "queue_fp_before": queue_fp_before,
            "queue_fp_after": queue_fp_after,
            "delivery": delivery,
            "failure_type": ft,
        }
    )
    live["cycle_history"] = history[-20:]
    # Durable day meter for production-power / T10-04 (ring alone cannot span a day).
    bump_non_noop_day_rollup(
        live, ts=cycle_ts, noop=noop, local_only=local_only, failure_type=ft
    )
    writing_live = STATE_PATH.resolve() == (auto.CONFIG_DIR / "peer-loop-state.json").resolve()
    if writing_live:
        try:
            import factory_progress as fp

            fp.persist_factory_progress_peak(live)
        except Exception:  # noqa: BLE001 — telemetry must not break cycle
            pass
    save_state(live)
    # When load_state() returns the same dict passed as ``state`` (tests /
    # cached callers), clear()+update(self) would wipe last_cycle.
    if state is not live:
        state.clear()
        state.update(live)
    if writing_live:
        try:
            import peer_agent_comms as comms

            role_id = str(state.get("active_role_id") or state.get("last_role_id") or "")
            comms.record_cycle_glink(
                role_id=role_id or None,
                verify_ok=verify_ok,
                noop=noop,
                note=note,
                failure_type=ft,
            )
        except Exception:  # noqa: BLE001
            pass
        if not verify_ok or noop:
            try:
                import peer_debrief as debrief

                debrief.capture_cycle_debrief()
            except Exception:  # noqa: BLE001 — telemetry must not break cycle
                pass
    return state



def format_last_cycle_block(state: dict[str, Any] | None = None) -> str:
    state = state if state is not None else load_state()
    lc = state.get("last_cycle")
    if not isinstance(lc, dict) or not lc:
        return ""
    age = max(0.0, time.time() - float(lc.get("ts") or 0))
    # OVERSEER_LAND_DEFERRED_HOT_MEMORY_2026_09_03 — surface failure_type
    # (esp. deferred soft-skip) in Hot memory so next peer does not treat
    # swarm/lock defer as a hard verify FAIL storm.
    ft = lc.get("failure_type")
    ft_s = str(ft).strip() if ft not in (None, "") else ""
    verify_label = "ok" if effective_verify_ok(lc) else "FAIL"
    if ft_s == "deferred":
        verify_label = "deferred (soft-skip — not a gate FAIL)"
    elif ft_s and not effective_verify_ok(lc):
        verify_label = f"FAIL [{ft_s}]"
    lines = [
        "## Last cycle (carry forward — do not re-explore)",
        f"- Age: {age:.0f}s",
        f"- Exit rc: {lc.get('rc')}",
        f"- Verify: {verify_label}",
        f"- Queue fingerprint: {lc.get('queue_fp_before')} → {lc.get('queue_fp')}",
        f"- Noop (same queue after ok): {lc.get('noop')}",
        f"- Git HEAD: {lc.get('git_head')}",
    ]
    if ft_s:
        lines.append(f"- Failure type: {ft_s}")
    if lc.get("note"):
        lines.append(f"- Note: {lc.get('note')}")
    if lc.get("noop"):
        lines.append(
            "- Instruction: previous cycle did not advance the queue — "
            "diagnose why items stayed open (wrong scope, Safety BLOCK, tests) "
            "before repeating the same plan."
        )
    if ft_s == "deferred":
        lines.append(
            "- Instruction: verify was deferred (swarm/lock) — soft-skip only; "
            "retry gate next wake; do not treat as FAIL storm or re-dispatch theater."
        )
    elif lc.get("verify_ok") is False:
        lines.append(
            "- Instruction: fix verify failures first; do not start new reclaim items until green."
        )
    return "\n".join(lines)


def format_trend_hint(*, trends_path: Path | None = None) -> str:
    """One-line pointer to industry trends when the cache file exists."""
    path = trends_path if trends_path is not None else TRENDS_MD
    if not path.is_file():
        return ""
    return "- Trends: skim `notes/AUTOMATION_TRENDS.md` for one industry hint if relevant."


def format_harness_memory(
    state: dict[str, Any] | None = None,
    *,
    trends_path: Path | None = None,
) -> str:
    """Last-cycle retrospect + worktree hint + optional trend hint for the next peer prompt."""
    parts: list[str] = []
    last = format_last_cycle_block(state)
    if last:
        parts.append(last)
    try:
        wt_hint = peer_worktree.format_prompt_hint()
        if wt_hint:
            parts.append(wt_hint)
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_rule_shutdown as rshut

        rule_block = rshut.format_hot_memory_block()
        if rule_block:
            parts.append(rule_block)
    except Exception:  # noqa: BLE001
        pass
    trend = format_trend_hint(trends_path=trends_path)
    if trend:
        parts.append(trend)
    return "\n".join(parts)


def noop_backoff_remaining(state: dict[str, Any] | None = None, *, backoff_sec: float = 120.0) -> float:
    """Seconds left before re-dispatching the same queue fingerprint after a noop ok cycle."""
    state = state if state is not None else load_state()
    lc = state.get("last_cycle")
    if not isinstance(lc, dict) or not lc.get("noop"):
        return 0.0
    if lc.get("local_only"):
        return 0.0
    age = time.time() - float(lc.get("ts") or 0)
    return max(0.0, backoff_sec - age)


def local_verify_cooldown_remaining(state: dict[str, Any] | None = None) -> float:
    """Throttle local-only verify ticks so unittest does not storm RAM."""
    state = state if state is not None else load_state()
    last = float(state.get("last_local_verify_ts") or 0)
    if not last:
        return 0.0
    cooldown = float(auto.CFG.get("local_only_verify_cooldown_sec") or 180)
    return max(0.0, cooldown - (time.time() - last))


def mark_local_verify(state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state if state is not None else load_state()
    state["last_local_verify_ts"] = time.time()
    save_state(state)
    return state


def build_next_input(*, quick: bool = False, force_peer: bool = False) -> str | None:
    """Canonical conversation summary + last-cycle retrospect + next peer prompt."""
    import peer_orchestrate as po

    path = find_latest_transcript()
    conversation = entire_conversation_block(path)
    memory = format_harness_memory()
    knowledge_block = ""
    try:
        import peer_memory_span as ms

        knowledge_block = ms.format_cold_tier(
            "orchestrator",
            conversation=conversation,
            max_chars=ms.tier_budget().cold,
        )
    except Exception:  # noqa: BLE001
        pass
    if not knowledge_block.strip():
        try:
            import knowledge_retrieve as kr

            knowledge_block = kr.inject_for_dispatch(conversation=conversation, quick=quick)
        except Exception:  # noqa: BLE001 — retrieval must not block dispatch
            knowledge_block = ""
    knowledge_section = f"\n\n{knowledge_block}\n" if knowledge_block else ""

    try:
        import peer_flaw_scan as flaw

        if flaw.should_dispatch_flaw_scan():
            flaw_body = flaw.build_orchestrator_prompt()
            if flaw_body:
                rules = auto.extract_rules(auto.load_context_md())
                rules_short = "; ".join(rules[:4]) if rules else "consent + compress + Cursor protected"
                memory_block = f"\n\n{memory}\n" if memory else "\n"
                return textwrap.dedent(
                    f"""\
                    Continue {auto.PROJECT_NAME} — **daily flaw detection round** (priority over normal queue).

                    Constraints: {rules_short}.
                    {memory_block}{knowledge_section}
                    ## Entire conversation (canonical — notes/PEER_CONVERSATION.md)

                    {conversation}

                    ---

                    {flaw_body}
                    """
                ).strip()
    except Exception:  # noqa: BLE001 — flaw scan must not block normal dispatch
        pass

    plan = po.build_plan(quick=quick, loop=True, force=force_peer)
    if not plan.stop and plan.role_assignments:
        try:
            import peer_agent_board as board

            board.record_dispatch(plan)
        except Exception:  # noqa: BLE001 — dispatch must not fail on telemetry
            pass
    if plan.stop:
        return po.format_prompt(plan)

    peer_body = po.format_prompt(plan)

    rules = auto.extract_rules(auto.load_context_md())
    rules_short = "; ".join(rules[:4]) if rules else "consent + compress + Cursor protected"

    memory_block = f"\n\n{memory}\n" if memory else "\n"

    return textwrap.dedent(
        f"""\
        Continue {auto.PROJECT_NAME} peer orchestration. Carry decisions forward; do not re-plan completed work.

        Constraints: {rules_short}.
        {memory_block}{knowledge_section}
        ## Entire conversation (canonical — notes/PEER_CONVERSATION.md)

        {conversation}

        ---

        {peer_body}
        """
    ).strip()


def conversation_summary_for_log(path: Path | None, *, max_lines: int = 3) -> str:
    turns = read_conversation(path)
    if not turns:
        return "empty transcript"
    role, text = turns[-1]
    preview = text.replace("\n", " ")[:120]
    return f"{len(turns)} turns · last {role}: {preview}…"


def poke_turn_signal() -> None:
    """Wake a blocked peer loop immediately (touch signal file)."""
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.touch()


@dataclass
class PeerEvent:
    """Why the peer loop woke up."""

    reason: str  # transcript | signal | git | log | timeout | fallback


class PeerEventWatcher:
    """Block on macOS kqueue VNODE events; long sleep fallback elsewhere."""

    _VNODE_FLAGS = (
        getattr(select, "KQ_NOTE_WRITE", 0)
        | getattr(select, "KQ_NOTE_EXTEND", 0)
        | getattr(select, "KQ_NOTE_ATTRIB", 0)
        | getattr(select, "KQ_NOTE_RENAME", 0)
        | getattr(select, "KQ_NOTE_DELETE", 0)
    )

    def __init__(self) -> None:
        self._kq: select.kqueue | None = None
        self._fds: list[int] = []
        self._available = False
        self._mtime_mode = False
        self._transcript_fd: int | None = None
        self._transcript_path: Path | None = None
        self._git_fd: int | None = None
        self._git_path: Path | None = None
        self._extra_paths: list[Path] = []
        # LINUX_MTIME_LOG_EXTRA_REASON_BASELINE_2026_09_08 — per-extra mtime
        # so log watches do not perpetual-wake as signal against _signal_mtime.
        self._extra_mtimes: dict[str, float] = {}
        # Baseline so stale turn_ended does not look like a fresh wake.
        self._last_transcript_event_mtime: float = 0.0
        self._signal_mtime: float = 0.0
        self._git_mtime: float = 0.0

    @property
    def available(self) -> bool:
        return self._available

    def setup(self, *, repo_root: Path | None = None) -> bool:
        if sys.platform == "darwin" and hasattr(select, "kqueue"):
            try:
                self._kq = select.kqueue()
                SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
                if not SIGNAL_PATH.is_file():
                    SIGNAL_PATH.touch()
                self._add_watch(SIGNAL_PATH)
                for root in transcript_roots():
                    if root.is_dir():
                        self._add_watch(root)
                self.refresh_transcript_watch()
                if repo_root is not None:
                    self.watch_git(repo_root)
                self._seed_transcript_baseline()
                self._available = True
                self._mtime_mode = False
                return True
            except OSError:
                self.close()
                # Fall through to mtime poll (rare on macOS).
        return self._setup_mtime(repo_root=repo_root)

    def _setup_mtime(self, *, repo_root: Path | None = None) -> bool:
        """Linux/CLEAN: chunked mtime poll on signal + transcript + git.

        Avoids blind 300s sleeps when kqueue is unavailable. Still event-ish:
        peer-turn.signal / transcript / .git touches wake within ~1s.
        Needle: OVERSEER_LINUX_MTIME_EVENT_WATCH_2026_09_08
        """
        try:
            SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not SIGNAL_PATH.is_file():
                SIGNAL_PATH.touch()
            self._signal_mtime = SIGNAL_PATH.stat().st_mtime
            self.refresh_transcript_watch()
            self._seed_transcript_baseline()
            if repo_root is not None:
                self.watch_git(repo_root)
            self._mtime_mode = True
            self._available = True
            return True
        except OSError:
            self.close()
            return False

    @staticmethod
    def _path_mtime(path: Path | None) -> float:
        if path is None:
            return 0.0
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            return 0.0

    def _seed_transcript_baseline(self) -> None:
        path = self._transcript_path or find_latest_transcript()
        if path is not None and path.is_file():
            try:
                self._last_transcript_event_mtime = path.stat().st_mtime
            except OSError:
                pass

    def watch_path(self, path: Path) -> bool:
        """Add an extra VNODE / mtime watch (logs, signals). Call after setup()."""
        if not self._available:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()
            if self._mtime_mode:
                if path not in self._extra_paths:
                    self._extra_paths.append(path)
                # Seed baseline so an already-fresh log does not wake forever.
                key = str(path.resolve()) if path.exists() else str(path)
                self._extra_mtimes[key] = self._path_mtime(path)
                return True
            if self._kq is None:
                return False
            self._add_watch(path)
            return True
        except OSError:
            return False

    def _add_watch(self, path: Path) -> None:
        if self._kq is None:
            return
        fd = os.open(str(path), os.O_RDONLY)
        self._fds.append(fd)
        self._kq.control(
            [
                select.kevent(
                    fd,
                    filter=select.KQ_FILTER_VNODE,
                    flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                    fflags=self._VNODE_FLAGS,
                )
            ],
            0,
            0,
        )

    def _drop_fd(self, fd: int | None) -> None:
        if fd is None:
            return
        if fd in self._fds:
            self._fds.remove(fd)
        try:
            os.close(fd)
        except OSError:
            pass

    def refresh_transcript_watch(self) -> None:
        """Re-bind VNODE watch to the latest parent transcript file."""
        path = find_latest_transcript()
        if self._mtime_mode:
            self._transcript_path = path if path is not None and path.is_file() else None
            return
        if self._kq is None:
            return
        if path is None or not path.is_file():
            self._drop_fd(self._transcript_fd)
            self._transcript_fd = None
            self._transcript_path = None
            return
        if self._transcript_path == path:
            return
        self._drop_fd(self._transcript_fd)
        self._transcript_fd = None
        self._transcript_path = path
        try:
            fd = os.open(str(path), os.O_RDONLY)
            self._transcript_fd = fd
            self._fds.append(fd)
            self._kq.control(
                [
                    select.kevent(
                        fd,
                        filter=select.KQ_FILTER_VNODE,
                        flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                        fflags=self._VNODE_FLAGS,
                    )
                ],
                0,
                0,
            )
        except OSError:
            self._transcript_fd = None
            self._transcript_path = None

    def watch_git(self, repo_root: Path) -> None:
        git_dir = repo_root / ".git"
        if self._mtime_mode:
            self._git_path = git_dir if git_dir.exists() else repo_root
            self._git_mtime = self._path_mtime(self._git_path)
            return
        if self._kq is None:
            return
        self._drop_fd(self._git_fd)
        self._git_fd = None
        try:
            fd = os.open(str(repo_root), os.O_RDONLY)
            self._git_fd = fd
            self._fds.append(fd)
            self._kq.control(
                [
                    select.kevent(
                        fd,
                        filter=select.KQ_FILTER_VNODE,
                        flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                        fflags=self._VNODE_FLAGS,
                    )
                ],
                0,
                0,
            )
        except OSError:
            self._git_fd = None

    def drain(self) -> int:
        """Discard pending kevents (self-writes during a cycle must not re-wake)."""
        if self._mtime_mode:
            self._signal_mtime = self._path_mtime(SIGNAL_PATH)
            self._git_mtime = self._path_mtime(self._git_path)
            self.refresh_transcript_watch()
            self._seed_transcript_baseline()
            return 0
        if not self._available or self._kq is None:
            return 0
        n = 0
        try:
            while True:
                events = self._kq.control(None, 64, 0)
                if not events:
                    break
                n += len(events)
        except OSError:
            return n
        self.refresh_transcript_watch()
        self._seed_transcript_baseline()
        return n

    def _wait_mtime(self, *, timeout: float | None = None) -> PeerEvent:
        """Chunked mtime poll — wakes on signal / transcript / git / extras."""
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        poll = effective_fallback_poll_sec() if timeout is None else max(0.0, timeout)
        if deadline is None:
            # Cap one wait call so callers still cycle; continuous wake passes timeout.
            deadline = time.monotonic() + poll
        while True:
            self.refresh_transcript_watch()
            path = self._transcript_path or find_latest_transcript()
            meta = read_transcript_meta(path)
            transcript_mtime = self._path_mtime(path)
            if (
                meta is not None
                and meta.turn_ended
                and transcript_mtime > self._last_transcript_event_mtime
            ):
                self._last_transcript_event_mtime = transcript_mtime
                return PeerEvent(reason="transcript")
            sig_m = self._path_mtime(SIGNAL_PATH)
            if sig_m > self._signal_mtime:
                self._signal_mtime = sig_m
                return PeerEvent(reason="signal")
            git_m = self._path_mtime(self._git_path)
            if git_m > self._git_mtime:
                self._git_mtime = git_m
                return PeerEvent(reason="git")
            for extra in self._extra_paths:
                # LINUX_MTIME_LOG_EXTRA_REASON_BASELINE_2026_09_08 — extras are
                # log watches (oversight). Compare to per-path baseline (not
                # _signal_mtime) and emit reason=log so benign appends sleep
                # instead of perpetual signal→rescan theater.
                key = str(extra.resolve()) if extra.exists() else str(extra)
                cur = self._path_mtime(extra)
                baseline = float(self._extra_mtimes.get(key, 0.0))
                if cur > baseline:
                    self._extra_mtimes[key] = cur
                    return PeerEvent(reason="log")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return PeerEvent(reason="timeout")
            time.sleep(min(1.0, remaining))

    def wait(self, *, timeout: float | None = None) -> PeerEvent:
        if not self._available:
            time.sleep(timeout if timeout is not None else effective_fallback_poll_sec())
            return PeerEvent(reason="fallback")
        if self._mtime_mode:
            return self._wait_mtime(timeout=timeout)
        if self._kq is None:
            time.sleep(timeout if timeout is not None else effective_fallback_poll_sec())
            return PeerEvent(reason="fallback")

        signal_before = SIGNAL_PATH.stat().st_mtime if SIGNAL_PATH.is_file() else 0.0
        sec = max(0.0, timeout) if timeout is not None else None
        try:
            events = self._kq.control(None, 1, sec)
        except OSError:
            time.sleep(timeout if timeout is not None else effective_fallback_poll_sec())
            return PeerEvent(reason="fallback")

        self.refresh_transcript_watch()
        path = find_latest_transcript()
        meta = read_transcript_meta(path)
        transcript_mtime = 0.0
        if path is not None and path.is_file():
            try:
                transcript_mtime = path.stat().st_mtime
            except OSError:
                transcript_mtime = 0.0
        # Only treat as transcript when the file advanced past our baseline.
        if (
            meta is not None
            and meta.turn_ended
            and transcript_mtime > self._last_transcript_event_mtime
        ):
            self._last_transcript_event_mtime = transcript_mtime
            return PeerEvent(reason="transcript")

        signal_after = SIGNAL_PATH.stat().st_mtime if SIGNAL_PATH.is_file() else 0.0
        if signal_after > signal_before:
            return PeerEvent(reason="signal")

        if events:
            return PeerEvent(reason="git")

        # kqueue returned without kevent — safety-net timeout elapsed.
        return PeerEvent(reason="timeout")

    def close(self) -> None:
        for fd in list(self._fds):
            self._drop_fd(fd)
        self._fds.clear()
        self._transcript_fd = None
        self._git_fd = None
        self._transcript_path = None
        self._git_path = None
        self._extra_paths.clear()
        self._extra_mtimes.clear()
        self._mtime_mode = False
        if self._kq is not None:
            try:
                self._kq.close()
            except OSError:
                pass
        self._kq = None
        self._available = False
