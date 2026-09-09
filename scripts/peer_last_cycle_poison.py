"""OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04 — last_cycle poison helpers.

OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04 — invariant:
failure_type=deferred ⇒ verify_ok=False.
Never pop failure_type while leaving verify_ok=True (greases delivery meters).

Needle: OVERSEER_SCRUB_FIXTURE_NOTE_OK_2026_09_04 — note="ok" does not clear
synthetic ts<=1.0 fixtures (still missing queue_fp/git_head).
"""
from __future__ import annotations

from typing import Any


def sanitize_last_cycle(lc: dict[str, Any] | None) -> dict[str, Any] | None:
    """failure_type=deferred ⇒ verify_ok=False (copy on change)."""
    if not isinstance(lc, dict) or not lc:
        return lc
    ft = str(lc.get("failure_type") or "").strip()
    if ft != "deferred" or lc.get("verify_ok") is not True:
        return lc
    fixed = dict(lc)
    fixed["verify_ok"] = False
    note = str(fixed.get("note") or "").strip()
    tag = "sanitized: deferred clears verify_ok"
    if tag not in note.lower():
        fixed["note"] = ((note + "; " if note else "") + tag)[:240]
    return fixed


def effective_verify_ok(lc: dict[str, Any] | None) -> bool:
    """True only for a real verify pass — deferred soft-skip never counts green."""
    if not isinstance(lc, dict) or not lc:
        return False
    if str(lc.get("failure_type") or "").strip() == "deferred":
        return False
    return lc.get("verify_ok") is True


def is_last_cycle_poison(lc: Any) -> bool:
    """Needle: OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04"""
    if not isinstance(lc, dict) or not lc:
        return False
    ft = str(lc.get("failure_type") or "").strip()
    if lc.get("verify_ok") is True and ft == "deferred":
        return True
    # OVERSEER_CLEAR_BAD_SEED_STAMP_2026_09_04 — soft seed stamped verify_ok=False
    # (pre-skip-fail heal) → verify_fail_hold forever even when tests are green.
    # OVERSEER_SEED_FAIL_NOT_POISON_2026_09_04 — poison ONLY when rc==0 and no
    # failure_type; real failed seeds (rc!=0) must NOT be poison.
    note = str(lc.get("note") or "").lower()
    if lc.get("verify_ok") is False and "self-heal seeded" in note:
        if not ft:
            try:
                rc_raw = lc.get("rc")
                rc = 0 if rc_raw is None else int(rc_raw)
            except (TypeError, ValueError):
                rc = 0
            if rc == 0:
                return True
            return False
    try:
        ts = float(lc.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    # OVERSEER_SCRUB_FIXTURE_NOTE_OK_2026_09_04 — note alone is not enough.
    if 0 < ts <= 1.0 and not lc.get("queue_fp") and not lc.get("git_head"):
        return True
    return False


def scrub_last_cycle_poison(state: dict[str, Any]) -> str | None:
    """OVERSEER_HEAL_SCRUB_FALLBACK_2026_09_04 — clear fixtures first; sanitize deferred.

    OVERSEER_SCRUB_FIXTURE_BEFORE_SANITIZE_2026_09_04 — ts<=1.0 fixtures must
    pop even when failure_type=deferred (sanitize-first left half-fixed poison).
    """
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
        fixed = sanitize_last_cycle(lc)
        if fixed is not None:
            state["last_cycle"] = fixed
            return "sanitized deferred clears verify_ok"
    state.pop("last_cycle", None)
    return "cleared poison last_cycle"


def safe_scrub(transcript: Any, state: dict[str, Any]) -> str:
    """Prefer transcript.scrub_* when present; else local scrub (rsync-safe)."""
    scrub = getattr(transcript, "scrub_last_cycle_poison", None) if transcript is not None else None
    if callable(scrub):
        try:
            return scrub(state) or "no-op scrub"
        except Exception:  # noqa: BLE001
            pass
    return scrub_last_cycle_poison(state) or "no-op scrub (module)"


def coerce_deferred_verify_ok(verify_ok: bool, failure_type: str | None) -> bool:
    """Atomic coerce for record_cycle_outcome."""
    if str(failure_type or "").strip() == "deferred":
        return False
    return bool(verify_ok)
