"""Project config for portable peer automation — read automation.config.json at repo root."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "automation.config.json"
LOCAL_CONFIG_PATH = ROOT / "automation.config.local.json"

_DEFAULTS: dict = {
    "project_name": "my-project",
    "project_slug": "my-project",
    "config_namespace": "my-project",
    "launch_agent_label": "com.example.my-project-peer-loop",
    "cursor_app": "Cursor",
    "post_cycle_hook": None,
    # After verify passes, peer_loop always commits commit-worthy changes
    # (main + coding worktree). Excludes local/weights/locks via pathspecs.
    "auto_commit_after_verify": True,
    # Re-scan + commit again if agents keep writing during the first pass.
    "auto_commit_max_passes": 3,
    # git add/commit timeouts (large trees used to abort and leave WIP dirty).
    "auto_commit_git_timeout_sec": 300,
    # Pathspecs passed as :(exclude)… — keep local/secrets/binaries out of auto-commits.
    "auto_commit_exclude_globs": [
        "*.local.json",
        "*.pt",
        "*.db",
        "*.coachlock",
        ".env",
        ".env.*",
        "notes/peer-turn.signal",
        "scripts/.overseer_land.lock",
        "notes/WORK_QUEUE.md.tmp",
        "notes/WORK_QUEUE.md.tmp/**",
        "notes/WORK_QUEUE.md.coachlock",
        "scripts/self_improve_context.md.coachlock",
        "notes/knowledge.db",
        "notes/niche_distill/**/weights/**",
        "notes/compression_artifacts/rung0_checkpoints/**",
        "**/weights/**",
        "**/rung0_checkpoints/**",
    ],
    # Opt-in: git push after a successful auto-commit (same repo / worktree).
    "auto_push_after_commit": False,
    # Each improve cycle assigns all 8 niches on the agent board + GLink vaults.
    "improve_hand_out_roles": True,
    # Max queue lines improve may add per cycle (default = parallel_peer_floor).
    "improve_enqueue_cap": 8,
    # Launch up to N simultaneous cursor-agent processes (one niche + worktree each).
    "parallel_agent_dispatch": True,
    "max_parallel_agent_procs": 8,
    "verify_quiet_max_agents": 2,
    "rss_budget_mb": None,
    "rss_entrypoint": None,
    "local_only_verify_cooldown_sec": 180,
    "test_cache_ttl_sec": 180,
    # Factory niche bank assist (peer_loop + dashboard /api/niche-chat).
    # Closed-world specialists + retrieval — not a general LLM.
    "factory_niche_assist": True,
    "factory_niche_parallel": True,
    "factory_niche_top_k": 3,
    "factory_niche_workers": 4,
    # Factory dynamics — live CPU/GPU serve balance (OVERSEER_FACTORY_DYNAMICS_2026_09_07).
    # device: auto|balance|cpu|cuda|mps — balance/auto use gpu_share + load heuristics.
    "factory_niche_device": "auto",
    "factory_niche_balance": True,
    "factory_niche_cpu_target_load": 0.70,
    "factory_niche_gpu_vram_floor_mb": 512,
    "factory_niche_serve_cache": True,
    # On-demand niche mint when agents find a closed-world speedup (OVERSEER_NICHE_MINT_ON_DEMAND_2026_09_07).
    "factory_niche_mint_suggest": True,
    "factory_niche_mint_epochs": 8,
    "factory_niche_mint_lr": 3e-4,
  "quick_test_command": None,
  "quick_test_measure_timeout_sec": 30,
  "test_measure_timeout_sec": 600,
  "git_measure_timeout_sec": 60,
    "improve_min_cycle_sec": 45,
    "improve_continuous_wake_sec": 15,
    "improve_continuous_min_cycle_sec": 10,
    "improve_idle_wake_sec": 120,
    "improve_wake_sec": 60,
    "continuous_wake_sec": 90,
    "continuous_agent_min_interval_sec": 30,
    # Never stall coding on a dirty main tree — peer keeps dispatching; optional worktree isolate.
    "continue_on_dirty": True,
    "dirty_wait_sec": 12,
    "coding_worktree": ".worktrees/peer-coding",
    "coding_worktree_branch": "peer/coding",
    "stall_pivot_sec": 3,
    "stall_pivot_enabled": True,
    "stall_pivot_agent_cooldown_sec": 90,
    "max_parallel_peers": 8,
    "parallel_peer_floor": 8,
    # OVERSEER_FORCE_FREE_DESKTOP_2026_09_05 — never select Cursor API-key billing.
    "force_free_desktop_auth": True,
    "merge_same_peer_tasks": False,
    "flaw_scan_enabled": True,
    "flaw_scan_daily_time": "09:00",
    "improve_drives_automation": True,
    "self_heal_enabled": True,
    "self_heal_interval_sec": 60,
    "agent_comms_enabled": True,
    "glink_enforce_compact": True,
    "glink_payload_max_bytes": 200,
    "glink_bus_prune_threshold": 500,
    "glink_bus_prune_keep": 500,
    "comms_improve_enabled": True,
    "comms_improve_wake_sec": 90,
    "comms_improve_continuous_wake_sec": 30,
    "comms_improve_min_cycle_sec": 30,
    "comms_improve_research_interval_cycles": 8,
    "comms_improve_self_test_required": True,
    "parallel_worktree_dir": ".worktrees",
    "parallel_worktree_prefix": "peer",
    "test_command": ["python3", "-m", "unittest", "discover", "-s", "tests", "-q"],
    "idea_mining_item": (
        "Discover clever non-obvious improvements — audit notes/VALUE_STACK.md and "
        "notes/CREATIVE_BACKLOG.md; add ≥3 experiments (clever before obvious); implement the highest-ROI one"
    ),
    "paths": {
        "work_queue": "notes/WORK_QUEUE.md",
        "context": "scripts/self_improve_context.md",
        "tasks": "scripts/peer_tasks.json",
        "launch_plan": "LAUNCH.md",
        "monetization": "MONETIZATION.md",
        "creative_backlog": "notes/CREATIVE_BACKLOG.md",
        "agents_md": "AGENTS.md",
    },
    "task_profile": None,
    "watch_all_cursor_transcripts": False,
    "extra_transcript_roots": [],
    "module_scope": {},
}

# Defined before load_config/CFG so overlay clamp paths never NameError on import.
_DGX_UNITTEST_CAP_CEILING = 24
# Nuclear pace: live may request 48–96; never allow Mac-clobber above ceiling.
_DGX_AGENTS_CAP_CEILING = 96


def _merge_config(cfg: dict, raw: dict) -> None:
    paths = cfg["paths"]
    for key, val in raw.items():
        if key == "paths" and isinstance(val, dict):
            paths.update(val)
        elif key == "agent_remote" and isinstance(val, dict) and isinstance(cfg.get("agent_remote"), dict):
            merged = dict(cfg["agent_remote"])
            merged.update(val)
            cfg["agent_remote"] = merged
        else:
            cfg[key] = val


def cap_dgx_install_limits(
    cfg: dict, *, cap: int = _DGX_AGENTS_CAP_CEILING
) -> dict:
    """Clamp install/runtime caps so Mac-rsync stale highs never survive.

    OVERSEER_LOAD_CONFIG_CAP_2026_09_04 — top-level peers/floor/procs/hub_worker_pool
    plus nested fill/pool must stay ≤ ceiling even when local.json is clobbered to 12/48.
    OVERSEER_HUB_WORKER_CLAMP_2026_09_04 — worktree_pool_size alias clamped too.
    """
    out = dict(cfg)
    for top_key in (
        "max_parallel_peers",
        "parallel_peer_floor",
        "max_parallel_agent_procs",
        "hub_worker_pool",
    ):
        raw = out.get(top_key)
        if raw is not None:
            try:
                out[top_key] = min(int(raw), cap)
            except (TypeError, ValueError):
                out[top_key] = cap
    top_unittest = out.get("dgx_unittest_cap")
    dh = out.get("dgx_host")
    if isinstance(dh, dict):
        dh = dict(dh)
        if top_unittest is not None:
            nested = dh.get("dgx_unittest_cap")
            if nested is not None and int(nested) > int(top_unittest):
                dh["dgx_unittest_cap"] = int(top_unittest)
        nested_ut = dh.get("dgx_unittest_cap")
        if nested_ut is not None and int(nested_ut) > _DGX_UNITTEST_CAP_CEILING:
            dh["dgx_unittest_cap"] = _DGX_UNITTEST_CAP_CEILING
        nested_ag = dh.get("dgx_max_cursor_agents")
        if nested_ag is not None and int(nested_ag) > cap:
            dh["dgx_max_cursor_agents"] = cap
        out["dgx_host"] = dh
    util = out.get("dgx_utilization")
    if isinstance(util, dict):
        util = dict(util)
        for ukey in ("target_agent_fill", "worktree_pool", "worktree_pool_size"):
            val = util.get(ukey)
            if val is not None:
                try:
                    if int(val) > cap:
                        util[ukey] = cap
                except (TypeError, ValueError):
                    util[ukey] = cap
        out["dgx_utilization"] = util
    return out


def load_config() -> dict:
    cfg = dict(_DEFAULTS)
    paths = dict(_DEFAULTS["paths"])
    cfg["paths"] = paths
    for path in (CONFIG_PATH, LOCAL_CONFIG_PATH):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                _merge_config(cfg, raw)
        except (json.JSONDecodeError, OSError):
            pass
    cfg["paths"] = paths
    # Clamp after merge so Mac→DGX clobber of local.json cannot inflate live caps.
    return cap_dgx_install_limits(cfg)


CFG = load_config()


def config_dir() -> Path:
    return Path.home() / ".config" / str(CFG["config_namespace"])


def path_key(key: str) -> Path:
    rel = CFG["paths"].get(key, _DEFAULTS["paths"].get(key, ""))
    return ROOT / str(rel)


def apply_dgx_speed_overlay(
    *,
    root: Path,
    overlay_path: Path,
    local_path: Path,
) -> dict:
    """Merge speed overlay into local config, clamping nested caps.

    Preserve existing local keys and then apply the overlay, clamping
    top-level install caps and factory_grid sub-caps so stale overlay
    values cannot survive.
    """
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))

    # Preserve local keys first (tests rely on this).
    base_cfg: dict = {}
    if local_path.is_file():
        try:
            raw_local = json.loads(local_path.read_text(encoding="utf-8"))
            if isinstance(raw_local, dict):
                base_cfg.update(raw_local)
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: repo-root automation.config.json for missing keys.
    base_config = root / "automation.config.json"
    if base_config.is_file():
        try:
            raw = json.loads(base_config.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k not in base_cfg:
                        base_cfg[k] = v
        except (json.JSONDecodeError, OSError):
            pass

    base_cfg.setdefault("paths", {})

    # Apply overlay (overlay wins).
    for k, v in overlay.items():
        if k == "paths" and isinstance(v, dict):
            base_cfg["paths"].update(v)
        elif k == "factory_grid" and isinstance(v, dict):
            fg = base_cfg.get("factory_grid")
            if not isinstance(fg, dict):
                fg = {}
            fg = dict(fg)
            fg.update(v)
            base_cfg["factory_grid"] = fg
        else:
            base_cfg[k] = v

    # Clamp top-level install caps.
    cap = _DGX_AGENTS_CAP_CEILING
    for top_key in ("max_parallel_peers", "parallel_peer_floor", "max_parallel_agent_procs", "hub_worker_pool"):  # OVERSEER_HUB_WORKER_CLAMP_2026_09_04
        if top_key in base_cfg and base_cfg[top_key] is not None:
            base_cfg[top_key] = min(int(base_cfg[top_key]), cap)

    # Clamp factory_grid sub-caps while preserving local flags (e.g. enabled).
    fg = base_cfg.get("factory_grid")
    if isinstance(fg, dict):
        for sub_key in ("hub_agents", "global_agents", "external_agents"):
            if sub_key in fg and fg[sub_key] is not None:
                fg[sub_key] = min(int(fg[sub_key]), cap)
        base_cfg["factory_grid"] = fg

    # Keep nested dgx_host caps consistent with the clamped peers.
    dh = base_cfg.get("dgx_host")
    if not isinstance(dh, dict):
        dh = {}
    top_ut = base_cfg.get("dgx_unittest_cap")
    if top_ut is not None:
        dh["dgx_unittest_cap"] = int(top_ut)
    peers = (
        base_cfg.get("max_parallel_agent_procs")
        or base_cfg.get("max_parallel_peers")
        or cap
    )
    dh["dgx_max_cursor_agents"] = min(int(peers), _DGX_AGENTS_CAP_CEILING)
    base_cfg["dgx_host"] = dh

    base_cfg = cap_dgx_install_limits(base_cfg, cap=cap)
    local_path.write_text(json.dumps(base_cfg, indent=2) + "\n", encoding="utf-8")
    return base_cfg


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        key = sys.argv[1]
        if key == "launch_agent_label":
            print(CFG["launch_agent_label"])
            raise SystemExit(0)
        if key == "config_namespace":
            print(CFG["config_namespace"])
            raise SystemExit(0)
    print(CFG["project_name"])
