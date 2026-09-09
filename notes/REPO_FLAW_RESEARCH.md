# Repo flaw research

_Updated 2026-09-08 16:22:05. Continuous mechanical + agent research on this repo._

## Summary

| Open flaws | 0 |
| New this cycle | 0 |
| Agent review | mechanical only |

## Actions this cycle

- probed 0 flaw(s); 0 new

## Open flaws by severity

## Agent notes

_Cursor-agent appends dated findings here after deep repo research._

- `automation.config.local.json` still **9** `verify_commands` vs lean/root **18** / `profiles/local.json` **18**. Live `run_peer_tasks.load_verify_commands` prefers `auto.CFG` (local-last merge) → continuous gate skips 9 OVERSEER modules (pool_ensure_fastpath, dual_research_linux, adapt_verify_protect, emit_inventory_ttl, prepare_prompts_ttl, auth_live_soft, parse_phased_ttl, cache_path_fallback, self_check_dedup). `sync_verify_commands_state` (called every verify) never rewrites `automation.config.local.json`; `_sync_lean_verify_to_hub_configs` only runs inside `heal_verify_commands(--write)`. Paths: `scripts/run_peer_tasks.py`, `scripts/automation_config.py`, `scripts/automation_adapt.py`, `automation.config.local.json`.
- `scripts/peer_loop.py` `_emit_worktree_inventory` — **zero** `inventory_snapshot` call sites; TTL skip = `_hub_parallel_floor_ready` (is_dir only). `peer_worktree.inventory_snapshot` docstring still claims emit uses it + `_pool_fs_inventory_healthy` (OVERSEER_POOL_TTL_HEALTHY_INV). Nested `peer-*/.worktrees/…` can stick across EMIT TTL while porcelain deferred. Live now nested=0 / healthy=True (latent).
- Medium (not queued): `_mark_flaw_research_landed._land_proof("deferred_poison")` → False (key absent; falls through); `tests/test_compact_land_proof.py::test_deferred_poison_scrub_on_load_proof_green` expects True. WQ↔SIC open-set drift (WQ-only: Pre-dispatch / Oversight+playbook / Re-adapt backlog; timestamp mismatch on research-speed Staff CLEAN fanout). Mechanical `adapt_state` fingerprint stale (`should_re_adapt` True) already backlog-queued.

**Severity:** high / high / medium

**Fix:** (1) `./scripts/peer heal-all` (or `python3 scripts/automation_adapt.py --heal --write`) so `_sync_lean_verify_to_hub_configs` pins local to lean 18; extend `sync_verify_commands_state` to heal `automation.config.local.json` too; confirm `load_verify_commands` len==18; `./scripts/peer test-quick`. (2) Replace emit body with `peer_worktree.inventory_snapshot(ensure_pool=True, …)` (or gate TTL on `_pool_fs_inventory_healthy`); extend `tests/test_emit_inventory_ttl_list_skip.py`; `./scripts/peer test-quick`.

### 2026-09-07 19:39 agent (Repo Flaw Research)

**Found:**
- `scripts/factory_kit_run.py` `green_lock_eligible` (~L82–101) — PR mode returns `(True, "pr")` when `pr_url` matches but `branch`/`worktree_path` absent or path missing (skips `git ls-remote`). Live: `{"artifact_mode":"pr","pr_url":"https://…/CPT/pull/1"}` → eligible. `tests/test_factory_kit_run.py` asserts PR URL alone is enough — contradicts `OVERSEER_FALSE_GREEN_LOCK_2026_09_07` / sequencing lock. Related: `notes/FACTORY_A_TO_Z_PROOF.md` Lock row corrupted (`P26-09-07 CPT A→E…` missing `| Last compound |`) + CPT Notes still say `Phase4 green` while Status **red**.
- `scripts/_mark_flaw_research_landed.py` — hub `_land_proof` has **no** `deferred_poison` branch (falls through False); vault `notes/agent_vaults/system_overseer/scripts/_mark_flaw_research_landed.py` L144–155 has it. Scrub already live in `scripts/peer_transcript.py`. `tests.test_compact_land_proof` **FAIL**; **not** in `verify_commands` (18) → verify theater.
- Medium (not queued): `project_automation.creative_backlog_items` looks for heading `Creative backlog (optional — does not block stop)` but WQ/SIC use `## Creative backlog` → always 0 items (dead path). Prior verify/emit/parse/cache/self-check/auth lands **healed** (CFG/local/root all 18; emit→`inventory_snapshot`). Digest keep `kept[-40:]` can drop newest-first Agent notes — append dated blocks at end.

**Severity:** high / high / medium

**Fix:** (1) Fail-closed in `green_lock_eligible`: require origin ref (`pr_remote_ref_missing` if path gone / ls-remote empty); flip unittest; repair Lock `Last compound` + scrub stale Phase4-green Notes; `./scripts/peer test-quick`. (2) Port vault `deferred_poison` proof into hub `_mark_flaw_research_landed.py`; add `tests.test_compact_land_proof` to lean verify; `./scripts/peer test-quick`.

### 2026-09-07 20:21 agent (Repo Flaw Research)

**Found:**
- `scripts/self_improve_context.md` clobbered to **356B / 3 fuel lines** (no `## Active` / `## Remaining` / `## Creative`) — reproduced: whitespace twin + `compression_keep_alive.ensure_queue_fuel` appends section-blind orphans while WQ `[x]` titles block restock on WQ only. Recurring (peer log prior restore from 350B/3 lines). Paths: `scripts/compression_keep_alive.py` (`ensure_queue_fuel` ~L314–352), live SIC, `notes/WORK_QUEUE.md`.
- `automation_adapt.heal_queue_drift` + `project_automation.sync_queue_drift` are **blind** on that state: `remaining_work_items` only reads `## Remaining work (priority order)`; Active opens empty → `actions=[]` / `warns=[]` / `./scripts/peer sync-queue` no-op. Fuel orphans invisible to `open_work_items` → keep-alive fuel theater. Paths: `scripts/automation_adapt.py` (`heal_queue_drift`), `scripts/project_automation.py` (`sync_queue_drift`, `remaining_work_items`).
- Medium (not queued): `creative_backlog_items` still extracts heading `Creative backlog (optional — does not block stop)` but WQ/SIC use `## Creative backlog` → always `[]` (stall_pivot / creative fallback dead). Prior green_lock / deferred_poison lands **reconfirmed**. Twin restored this cycle from WQ SoT after probe.

**Severity:** critical / high / medium

**Fix:** (1) Gate `ensure_queue_fuel` to insert only under `## Active` (create heading if missing); refuse write when twin lacks Active/Remaining structure vs WQ; unittest empty-twin→must not yield headerless 356B file; `./scripts/peer test-quick`. (2) `sync_queue_drift` / `heal_queue_drift` fail-closed: if WQ has `## Active` and context lacks Active+Remaining headings (or ctx bytes≪WQ), restore twin from WQ / warn; `./scripts/peer sync-queue` then `./scripts/peer test-quick`.

### 2026-09-08 09:22Z agent (Repo Flaw Research)

**Found:**
- `scripts/factory_kit_run.py` `run_kit` still orders **A→B→C** (`step_verify` before `step_worktree` ~L1103–1116) while `tests/test_factory_kit_run.py::test_dry_run_creates_worktree_before_verify` requires **A→C→B** + `NEEDLE_B_CLEAN_WT`. Same suite **ERROR×5**: missing `_worktree_start_ref`, `heal_missing_verify_paths_from_head`, `_verify_cmd_paths`, `ensure_node_modules_for_verify` (OVERSEER_KIT_RUN_C_ORIGIN_MAIN / B_ON_CLEAN_WT / HEAL_DONOR). Live `python3 -m unittest tests.test_factory_kit_run` → FAILED (1 fail, 5 errors). **Not** in lean `verify_commands` (19) → continuous verify theater while factory A→Z compound regresses. Paths: `scripts/factory_kit_run.py`, `tests/test_factory_kit_run.py`, `scripts/run_peer_tasks.py` / `automation.config*.json`.
- `project_automation.creative_backlog_items` still extracts `Creative backlog (optional — does not block stop)` but WQ/SIC/`demote_to_creative` use `## Creative backlog` → always `[]`. Live: Active all `[x]` → `loop_work_items`/`open_work_items` source=empty; Creative Soft-push line exists but invisible to stall_pivot / orchestrate creative fallback. No unittest covers the live heading. Paths: `scripts/project_automation.py` (~L3844), `scripts/peer_stall_pivot.py`, `scripts/peer_orchestrate.py`.
- Medium (not queued): WQ `## Remaining` still has open Soft-push while SIC Remaining all `[x]`; `sync_queue_drift` / dual-brain probe only compare Active/phased → Remaining twin drift invisible. Soft-push also in Creative (human-auth demote) — close or mirror Remaining. Prior verify/emit/green_lock/deferred_poison/fuel-header lands **reconfirmed** (CFG verify len=19; `green_lock_eligible` fail-closed; `ensure_queue_fuel` headerless SKIP).

**Severity:** high / high / medium

**Fix:** (1) Restore A→C→B + helpers in `factory_kit_run` (or realign tests to intentional A→B→C) until `tests.test_factory_kit_run` green; add `python3 -m unittest tests.test_factory_kit_run -q` to lean verify via `./scripts/peer heal-all` / adapt sync; `./scripts/peer test-quick`. (2) In `creative_backlog_items`, try short `Creative backlog` then long optional heading; unittest sample WQ section → ≥1 item; `./scripts/peer test-quick`.

## Commands

```bash
./scripts/peer repo-research              # one probe cycle
./scripts/peer repo-research-force        # ignore cooldown + dispatch
./scripts/peer repo-research-status
./scripts/peer heal-all                   # mechanical heal after fixes
```
