#!/usr/bin/env python3
"""Run hub improve-forever with peer-4 compression overlays (priority + lazy-urllib research).

Mac rsync clobbers hub ``scripts/dgx_resource_priority.py``. Prefer peer-4's
poll-latest cache path so improve does not CDLL(libnvidia-ml)/libcuda every
``guard_development`` tick (~+18 MB RSS measured).

Usage (systemd ExecStart):
  python3 ~/.config/automation/run_improve_poll_cache.py --forever --daemon --write --research
"""
from __future__ import annotations

import os as _os_comp
import sys as _sys_comp

if _os_comp.environ.get("MALLOC_ARENA_MAX") is None:
    _os_comp.environ["MALLOC_ARENA_MAX"] = "1"
    _os_comp.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    _os_comp.execve(
        _sys_comp.executable,
        [_sys_comp.executable, *_sys_comp.argv],
        _os_comp.environ,
    )

import importlib.util
import runpy
import sys
from pathlib import Path

# Prefer hub when OVERSEER_HUB_POLL_LATEST landed — peer-N overlays race Path
# imports under Mac rsync and crash improve (NameError: Path). Fall back to
# peer-6/peer-4 only when hub still lacks poll-latest.
# Needle: OVERSEER_IMPROVE_PREFER_HUB_POLL_2026_09_04
PEER6_RP = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-6/scripts/dgx_resource_priority.py"
)
PEER4_RP = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-4/scripts/dgx_resource_priority.py"
)
PEER6_RESEARCH = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-6/scripts/automation_research.py"
)
PEER6_COMMS_RESEARCH = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-6/scripts/automation_comms_research.py"
)
PEER6_DUAL = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-6/scripts/peer_dual_research.py"
)
PEER4_RESEARCH = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-4/scripts/automation_research.py"
)
PEER4_COMMS_RESEARCH = Path(
    "/home/arnavrastogi/Automation/.worktrees/peer-4/scripts/automation_comms_research.py"
)
HUB_IMPROVE = Path("/home/arnavrastogi/Automation/scripts/automation_improve.py")
HUB_SCRIPTS = Path("/home/arnavrastogi/Automation/scripts")
HUB_RP = HUB_SCRIPTS / "dgx_resource_priority.py"
HUB_POLL = HUB_SCRIPTS / "dgx_resource_poll.py"


def _load_peer4_module(name: str, path: Path) -> None:
    """Prefer peer-4 script over Mac-rsync hub clobber (compression overlays).

    Peer-N scripts do ``sys.path.insert(0, SCRIPTS)`` then ``import automation_config``
    which pins peer-N ROOT/namespace into the improve process. Restore hub ns after.
    Needle: OVERSEER_IMPROVE_HUB_NS_RESTORE_2026_09_04
    """
    if not path.is_file():
        return
    hub = str(HUB_SCRIPTS)
    if hub not in sys.path:
        sys.path.insert(0, hub)
    path_before = list(sys.path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        _restore_hub_config_ns(path_before=path_before)


def _restore_hub_config_ns(*, path_before: list[str] | None = None) -> None:
    """Drop peer-N path inserts and re-bind hub automation_config / project_automation.

    Needle: OVERSEER_IMPROVE_HUB_NS_RESTORE_2026_09_04
    """
    hub = str(HUB_SCRIPTS)
    if path_before is not None:
        sys.path[:] = path_before
    else:
        sys.path[:] = [
            p
            for p in sys.path
            if "/.worktrees/peer-" not in str(p).replace("\\", "/")
        ]
    if hub not in sys.path:
        sys.path.insert(0, hub)

    def _poisoned(mod: object) -> bool:
        f = str(getattr(mod, "__file__", "") or "").replace("\\", "/")
        if "/.worktrees/peer-" in f:
            return True
        cfg_dir = str(getattr(mod, "CONFIG_DIR", "") or "")
        return "/.config/peer-" in cfg_dir.replace("\\", "/")

    for name in ("project_automation", "automation_config"):
        mod = sys.modules.get(name)
        if mod is not None and _poisoned(mod):
            sys.modules.pop(name, None)

    if "automation_config" not in sys.modules:
        import automation_config  # noqa: F401
    if "project_automation" not in sys.modules:
        import project_automation  # noqa: F401
    else:
        mod = sys.modules["project_automation"]
        if _poisoned(mod):
            sys.modules.pop("project_automation", None)
            sys.modules.pop("automation_config", None)
            import automation_config  # noqa: F401
            import project_automation  # noqa: F401


def _hub_has_lazy_research() -> bool:
    path = HUB_SCRIPTS / "automation_research.py"
    try:
        return "COMPRESSION_LAZY_URLLIB_RESEARCH_2026_09_04" in path.read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False


def _hub_has_poll_latest(path: Path) -> bool:
    """Hub tip only needs poll-latest markers (normal ``from pathlib import Path``)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "POLL_LATEST_PATH" in text or "_read_poll_latest" in text


def _overlay_safe(path: Path) -> bool:
    """Peer-N overlay must have Path-local-import — else NameError crash-loop."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if "POLL_LATEST_PATH" not in text and "_read_poll_latest" not in text:
        return False
    # OVERSEER_IMPROVE_REQUIRE_PATH_LOCAL_2026_09_04
    return (
        "OVERSEER_PATH_LOCAL_IMPORT_2026_09_04" in text
        or "from pathlib import Path as _Path" in text
    )


def _smoke_priority_module(name: str = "dgx_resource_priority") -> bool:
    """Return True when loaded module can resolve poll-latest paths."""
    mod = sys.modules.get(name)
    if mod is None:
        return False
    try:
        # Drop module Path to prove local-import (overlay race).
        saved = mod.__dict__.pop("Path", None)
        try:
            paths = mod._poll_latest_paths()  # type: ignore[attr-defined]
            return bool(paths)
        finally:
            if saved is not None:
                mod.Path = saved
    except Exception:  # noqa: BLE001
        return False


def _load_peer4_priority() -> None:
    """Prefer hub scripts — never peer-N overlay when hub has poll-latest.

    Needle: OVERSEER_IMPROVE_PREFER_HUB_POLL_2026_09_04 + OVERSEER_IMPROVE_NEVER_PEER_OVERLAY_2026_09_04
    """
    hub = str(HUB_SCRIPTS)
    if hub not in sys.path:
        sys.path.insert(0, hub)
    # OVERSEER_IMPROVE_NEVER_PEER_OVERLAY_2026_09_04 — hub poll-latest wins always.
    if HUB_RP.is_file() and _hub_has_poll_latest(HUB_RP):
        return
    for path in (PEER6_RP, PEER4_RP):
        if not path.is_file() or not _overlay_safe(path):
            continue
        _load_peer4_module("dgx_resource_priority", path)
        if _smoke_priority_module():
            return
        sys.modules.pop("dgx_resource_priority", None)


def _load_peer4_research() -> None:
    """Prefer hub lazy-urllib research; fall back to peer-6 only when hub lacks needle.

    Needle: COMPRESSION_LAZY_URLLIB_RESEARCH_2026_09_04 — preload is safe after
    urllib is deferred to _fetch. OVERSEER_IMPROVE_HUB_NS_RESTORE_2026_09_04 —
    peer-N research path-insert must not pin peer CONFIG_DIR into improve forever.
    """
    if _hub_has_lazy_research():
        # Hub already lazy — do not exec peer-N research (avoids ns poison).
        return
    for name, path in (
        ("automation_research", PEER6_RESEARCH),
        ("automation_comms_research", PEER6_COMMS_RESEARCH),
        ("peer_dual_research", PEER6_DUAL),
        ("automation_research", PEER4_RESEARCH),
        ("automation_comms_research", PEER4_COMMS_RESEARCH),
    ):
        if name in sys.modules:
            continue
        _load_peer4_module(name, path)
    _restore_hub_config_ns()


def _stamp_poll_force_live() -> None:
    """Best-effort: ensure hub poll writer uses snapshot(force_live=True)."""
    if not HUB_POLL.is_file():
        return
    try:
        text = HUB_POLL.read_text(encoding="utf-8")
    except OSError:
        return
    if "force_live=True" in text:
        return
    needle = "snap = rp.snapshot()"
    if needle not in text:
        return
    try:
        HUB_POLL.write_text(
            text.replace(
                needle,
                "snap = rp.snapshot(force_live=True)  # compression: never echo poll-latest",
                1,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_config_stamp(name: str):
    """Load ~/.config/automation/<name>.py (None if unavailable)."""
    stamp_path = Path.home() / ".config" / "automation" / f"{name}.py"
    if not stamp_path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location(name, stamp_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001
        return None


def _load_adapt_ttl_stamp():
    """Load compression_adapt_ttl_stamp helper (None if unavailable)."""
    return _load_config_stamp("compression_adapt_ttl_stamp")


def _load_lazy_asi_stamp():
    """Load compression_lazy_asi_stamp — defer asi_rubric until ASI attr access."""
    return _load_config_stamp("compression_lazy_asi_stamp")


def _stamped_improve_text() -> str:
    """Hub improve source with compression stamps applied in-memory (rsync-safe)."""
    stamp = _load_adapt_ttl_stamp()
    lazy_asi = _load_lazy_asi_stamp()
    # Disk stamp is best-effort only — Mac rsync --delete-before undoes within seconds.
    try:
        if stamp is not None and hasattr(stamp, "stamp"):
            stamp.stamp(HUB_IMPROVE)
        if lazy_asi is not None and hasattr(lazy_asi, "stamp"):
            lazy_asi.stamp(HUB_IMPROVE)
    except Exception:  # noqa: BLE001
        pass
    text = HUB_IMPROVE.read_text(encoding="utf-8")
    if stamp is not None and hasattr(stamp, "apply_to_text"):
        text = stamp.apply_to_text(text)
    if lazy_asi is not None and hasattr(lazy_asi, "apply_to_text"):
        text = lazy_asi.apply_to_text(text)
    # Last resort: peer-4 improve body when hub disk lost compression lands
    # (Mac rsync --delete-before reclobbers within seconds).
    peer4 = Path(
        "/home/arnavrastogi/Automation/.worktrees/peer-4/scripts/automation_improve.py"
    )
    need_peer4 = (
        "COMPRESSION_LAZY_ASI_EMPTY_2026_09_04" not in text
        or "COMPRESSION_WRITE_PROMPTS_ASI_SHARE_2026_09_04" not in text
    )
    if need_peer4 and peer4.is_file():
        try:
            p4 = peer4.read_text(encoding="utf-8")
            if "COMPRESSION_WRITE_PROMPTS_ASI_SHARE_2026_09_04" in p4 or (
                "COMPRESSION_LAZY_ASI_EMPTY_2026_09_04" not in text
                and "COMPRESSION_LAZY_ASI_EMPTY_2026_09_04" in p4
            ):
                text = p4
        except OSError:
            pass
    # Prefer peer-6 zlib write_prompts fp — drop hashlib→libcrypto (~3–6 MB).
    # Needle: COMPRESSION_ZLIB_WRITE_PROMPTS_FP_2026_09_04
    # Also prefer peer-6 when ADAPT_TTL missing (hub may keep zlib but lose TTL).
    # Needle: COMPRESSION_ADAPT_TTL_2026_09_04
    # OVERSEER_IMPROVE_HUB_ZLIB_FP_2026_09_04 — when hub already has zlib fp, never
    # swap the full peer-6 improve body (peer research path-insert poisoned ns).
    peer6 = Path(
        "/home/arnavrastogi/Automation/.worktrees/peer-6/scripts/automation_improve.py"
    )
    need_peer6 = (
        "COMPRESSION_ZLIB_WRITE_PROMPTS_FP_2026_09_04" not in text
        or "COMPRESSION_ADAPT_TTL_2026_09_04" not in text
        or "def should_live_adapt_audit" not in text
    )
    if need_peer6 and peer6.is_file():
        try:
            p6 = peer6.read_text(encoding="utf-8")
            if (
                "COMPRESSION_ZLIB_WRITE_PROMPTS_FP_2026_09_04" in p6
                and "COMPRESSION_ADAPT_TTL_2026_09_04" in p6
                and "def should_live_adapt_audit" in p6
            ):
                text = p6
        except OSError:
            pass
    return text


def _exec_improve(text: str) -> None:
    glb = {
        "__name__": "__main__",
        "__file__": str(HUB_IMPROVE),
        "__builtins__": __builtins__,
    }
    exec(compile(text, str(HUB_IMPROVE), "exec"), glb)  # noqa: S102


def main() -> None:
    _stamp_poll_force_live()
    _load_peer4_priority()
    # Preload peer-6 lazy-urllib research so hub eager urllib never wins.
    # Needle: COMPRESSION_LAZY_URLLIB_RESEARCH_2026_09_04
    _load_peer4_research()
    if not HUB_IMPROVE.is_file():
        raise SystemExit(f"missing hub improve: {HUB_IMPROVE}")
    # Preserve argv for argparse inside automation_improve.
    sys.argv = [str(HUB_IMPROVE), *sys.argv[1:]]

    # Compression: zlib queue/git fp — drop hashlib→libcrypto (~4–6 MB).
    # Needle: COMPRESSION_ZLIB_FP_STAMP_2026_09_04
    hub = str(HUB_SCRIPTS)
    if hub not in sys.path:
        sys.path.insert(0, hub)
    try:
        import project_automation  # noqa: F401 — keep ROOT on hub checkout

        _zlib = _load_config_stamp("compression_zlib_fp_stamp")
        if _zlib is not None:
            if hasattr(_zlib, "stamp"):
                _zlib.stamp()
            if hasattr(_zlib, "preload"):
                _zlib.preload()
    except Exception:  # noqa: BLE001 — never block improve start
        pass
    # Defense in depth — peer overlays must never leave improve on peer-N CONFIG_DIR.
    _restore_hub_config_ns()

    # Durable path: never runpy unstamped hub disk (rsync restores eager _ASI_EMPTY).
    # COMPRESSION_IMPROVE_NO_RAW_RUNPY_2026_09_04
    try:
        text = _stamped_improve_text()
        durable = (
            "COMPRESSION_ADAPT_TTL_2026_09_04" in text
            and "adapt-heal: ttl-skip" in text
        ) or ("COMPRESSION_LAZY_ASI_EMPTY_2026_09_04" in text) or (
            "COMPRESSION_WRITE_PROMPTS_ASI_SHARE_2026_09_04" in text
        ) or ("COMPRESSION_ZLIB_WRITE_PROMPTS_FP_2026_09_04" in text)
        if durable:
            _exec_improve(text)
            return
        # Stamps missed markers — still prefer in-memory text over raw disk.
        _exec_improve(text)
        return
    except Exception:  # noqa: BLE001 — last resort only
        pass
    # Absolute last resort: re-read + stamp once more, never trust raw hub alone.
    try:
        _exec_improve(_stamped_improve_text())
        return
    except Exception:  # noqa: BLE001
        pass
    runpy.run_path(str(HUB_IMPROVE), run_name="__main__")


if __name__ == "__main__":
    main()
