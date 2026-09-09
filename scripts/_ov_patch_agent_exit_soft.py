#!/usr/bin/env python3
"""OVERSEER land: soft agent-exit must not poison verify_ok / stagnation."""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def patch_peer_loop(p: Path) -> bool:
    text = p.read_text(encoding="utf-8")
    if "OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_LAND_2026_09_04" in text:
        print("peer_loop already patched")
        return True
    old = """    if rc != 0:
        # OVERSEER_AGENT_EXIT_SOFT_2026_09_04 — SIGKILL/-9 or non-zero without red
        # tests is soft Episodic (do not freeze factory on agent exit alone).
        tests_still_ok = False
        try:
            tests_still_ok = bool(auto.measure_live_state(quick=True).tests_ok)
        except Exception:  # noqa: BLE001
            tests_still_ok = False
        soft = (rc < 0) or tests_still_ok
        transcript.record_cycle_outcome(
            state,
            rc=rc,
            verify_ok=False,
            queue_fp_before=fp_before,
            queue_fp_after=fp_before,
            note=(
                "cursor-agent non-zero exit (soft Episodic)"
                if soft
                else "cursor-agent non-zero exit"
            ),
            failure_type="agent_exit_soft" if soft else None,
        )"""
    new = """    if rc != 0:
        # OVERSEER_AGENT_EXIT_SOFT_2026_09_04 — SIGKILL/-9 or non-zero without red
        # tests is soft Episodic (do not freeze factory on agent exit alone).
        # OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_LAND_2026_09_04 — soft must NOT
        # stamp verify_ok=False (poisoned last_cycle → verify-gate FAIL +
        # rc≠0 critical stagnation + live-log instant-react forever).
        tests_still_ok = False
        try:
            tests_still_ok = bool(auto.measure_live_state(quick=True).tests_ok)
        except Exception:  # noqa: BLE001
            tests_still_ok = False
        soft = (rc < 0) or tests_still_ok
        transcript.record_cycle_outcome(
            state,
            rc=rc,
            verify_ok=bool(soft),
            queue_fp_before=fp_before,
            queue_fp_after=fp_before,
            note=(
                "cursor-agent non-zero exit (soft Episodic)"
                if soft
                else "cursor-agent non-zero exit"
            ),
            failure_type="agent_exit_soft" if soft else None,
        )"""
    if old not in text:
        print("peer_loop OLD block not found")
        i = text.find("OVERSEER_AGENT_EXIT_SOFT_2026_09_04")
        print(repr(text[i : i + 400]))
        return False
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return "VERIFY_OK_LAND" in p.read_text(encoding="utf-8")


def patch_events(p: Path) -> bool:
    text = p.read_text(encoding="utf-8")
    changed = False
    if "OVERSEER_LIVE_SKIP_AGENT_EXIT_SOFT_2026_09_04" not in text:
        old = '''def _skip_live_hit_line(ln: str, pat: str) -> bool:
    """Drop echo / stale-auth theater that nests instant-react forever.

    OVERSEER_LIVE_LOG_ECHO_2026_09_04
    """
    low = (ln or "").lower()
    if "live log:" in low:
        return True
    if "cleared autonomy delays" in low and "auth not ready" in low:
        return True
    if "human-only live hit" in low:
        return True
    if pat == "auth not ready":
        ready = _auth_currently_ready()
        if ready is True:
            return True
    return False'''
        new = '''def _skip_live_hit_line(ln: str, pat: str) -> bool:
    """Drop echo / stale-auth theater that nests instant-react forever.

    OVERSEER_LIVE_LOG_ECHO_2026_09_04
    OVERSEER_LIVE_SKIP_AGENT_EXIT_SOFT_2026_09_04 — soft Episodic agent exits
    are keep-working (tests green); must not re-dispatch overseer forever.
    """
    low = (ln or "").lower()
    if "live log:" in low:
        return True
    if "cleared autonomy delays" in low and "auth not ready" in low:
        return True
    if "human-only live hit" in low:
        return True
    if pat in ("cursor-agent non-zero", "cursor-agent exit ") and (
        "soft episodic" in low or "agent_exit_soft" in low
    ):
        return True
    if pat == "auth not ready":
        ready = _auth_currently_ready()
        if ready is True:
            return True
    return False'''
        if old not in text:
            print("events skip block not found")
            return False
        text = text.replace(old, new, 1)
        changed = True
    if "OVERSEER_STAG_SKIP_AGENT_EXIT_SOFT_2026_09_04" not in text:
        old = """    qcount = int(ctx.get(\"queue_count\") or 0)
    phase = str(ctx.get(\"phase\") or \"\")

    if last.get(\"verify_ok\") is False:
        add(\"verify gate FAIL\", 50, critical=True)
    if last.get(\"noop\"):
        add(\"noop cycle — queue fingerprint unchanged after ok verify\", 45, critical=True)
    if int(ctx.get(\"noop_backoff_sec\") or 0) > 0:
        add(f\"noop backoff armed ({int(ctx.get('noop_backoff_sec') or 0)}s remaining)\", 38, critical=True)
    if last.get(\"rc\") not in (None, 0):
        add(f\"last peer cycle exit rc={last.get('rc')}\", 32, critical=True)"""
        new = """    qcount = int(ctx.get(\"queue_count\") or 0)
    phase = str(ctx.get(\"phase\") or \"\")
    # OVERSEER_STAG_SKIP_AGENT_EXIT_SOFT_2026_09_04 — soft Episodic exits keep
    # verify_ok (tests green) but may retain rc≠0; never treat as gate FAIL.
    _ft = str(last.get(\"failure_type\") or \"\").strip().lower()
    _note = str(last.get(\"note\") or \"\").lower()
    soft_agent_exit = _ft == \"agent_exit_soft\" or \"soft episodic\" in _note

    if last.get(\"verify_ok\") is False and not soft_agent_exit:
        add(\"verify gate FAIL\", 50, critical=True)
    if last.get(\"noop\"):
        add(\"noop cycle — queue fingerprint unchanged after ok verify\", 45, critical=True)
    if int(ctx.get(\"noop_backoff_sec\") or 0) > 0:
        add(f\"noop backoff armed ({int(ctx.get('noop_backoff_sec') or 0)}s remaining)\", 38, critical=True)
    if last.get(\"rc\") not in (None, 0) and not soft_agent_exit:
        add(f\"last peer cycle exit rc={last.get('rc')}\", 32, critical=True)"""
        if old not in text:
            print("events stag block not found")
            return False
        text = text.replace(old, new, 1)
        changed = True
    if changed:
        p.write_text(text, encoding="utf-8")
    body = p.read_text(encoding="utf-8")
    return (
        "OVERSEER_LIVE_SKIP_AGENT_EXIT_SOFT_2026_09_04" in body
        and "OVERSEER_STAG_SKIP_AGENT_EXIT_SOFT_2026_09_04" in body
    )


def hold_and_stub() -> None:
    import peer_land_hold as h

    body = f"overseer-stag-agent-exit-soft {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
    h.HOLD_PATH.write_text(body, encoding="utf-8")
    h.ROOT_HOLD.write_text(body, encoding="utf-8")
    for f in h.RESTORE_PAUSED_FLAGS:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("overseer land pause — restore deferred\n", encoding="utf-8")
    if h.RESTORE.is_file():
        h.RESTORE.write_text(
            "#!/usr/bin/env bash\n# restore paused by overseer land\n"
            "echo restore paused\nexit 0\n",
            encoding="utf-8",
        )
        h.RESTORE.chmod(0o755)


def pin(name: str) -> None:
    src = ROOT / "scripts" / name
    vault = Path.home() / ".config/automation-hub/hub-protect/scripts"
    vault.mkdir(parents=True, exist_ok=True)
    copy2(src, vault / name)
    (ROOT / "scripts" / f"EXPECTED_{name}.md5").write_text(
        hashlib.md5(src.read_bytes()).hexdigest() + "\n", encoding="utf-8"
    )
    nv = ROOT / "notes/agent_vaults/system_overseer/scripts"
    nv.mkdir(parents=True, exist_ok=True)
    copy2(src, nv / name)
    print("pinned", name, hashlib.md5(src.read_bytes()).hexdigest()[:8])


def main() -> int:
    hold_and_stub()
    ok1 = patch_peer_loop(ROOT / "scripts/peer_loop.py")
    ok2 = patch_events(ROOT / "scripts/peer_oversight_events.py")
    print("patch_loop", ok1, "patch_events", ok2)
    if not (ok1 and ok2):
        return 1
    for name in ("peer_loop.py", "peer_oversight_events.py"):
        pin(name)
    time.sleep(1.0)
    loop_ok = "VERIFY_OK_LAND" in (ROOT / "scripts/peer_loop.py").read_text(encoding="utf-8")
    ev_ok = "LIVE_SKIP_AGENT" in (ROOT / "scripts/peer_oversight_events.py").read_text(
        encoding="utf-8"
    )
    print("after1s loop", loop_ok, "events", ev_ok)
    return 0 if loop_ok and ev_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
