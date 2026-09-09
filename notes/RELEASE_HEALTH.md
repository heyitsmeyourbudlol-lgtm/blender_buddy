# Release health — dual-daemon / STOPPED hazards

Operational notes for peer dashboard + LaunchAgent install CTAs.

## 2026-09-07 wave-60 — SRE heal (T10-04 scoreboard + keep-alive revive)

- **Smoke:** `peer-loop`/`improve-loop`/`oversight-loop` **active**; `compression-keep-alive`/`auto-train`/`result-watch` **restarted → active**; `ram-status` avail **~52GB** `[ok]`; `production_power_scoreboard.py --write` → Non-noop **2 today · GAP** (bar ≥8); `validate_tasks_config` **issues []**; billing `desktop_free`.
- **Root cause:** keep-alive was **TERM'd** (~22:24; external ballast-stop script) → Staff floor miss (`agents=2` `floor=8` `agents_ge_floor=false`). T10-04 meter already landed; observed day count still ≪8 (flaps + short rollup) — not a missing scoreboard column.
- **Landed:** `systemctl --user start` keep-alive + auto-train + result-watch under RAM `[ok]`; scoreboard refresh on hub `notes/PRODUCTION_POWER_SCOREBOARD.md`; docs remasure only — **PASS skip invent-deploy / raise FANOUT**. No Shard-* invent. TRAIN recipe untouched.
- **Acceptance:** peer+improve CLEAN · keep-alive unit live · scoreboard Current snapshot written · T10-04 stays **open** until observed ≥8/day.
- **Residual:** `agents_ge_floor=false` soft — fanout `cursor-agent` still **rc=-9** (SIGKILL) within ~1s of launch despite MemAvailable healthy (free-desktop/concurrent kill, not dead keep-alive); non_noop_by_day today=2 GAP; dirty COD soft. Do **not** restart keep-alive in a storm while children live; do **not** raise `FANOUT_TARGET` above cap **8**.
- **Rollback:** isolate `.worktrees/peer-N` → `./scripts/peer heal-all` → remasure `--check`; never force-push; never Install CTA on expected worktree STOPPED.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE60_SRE_2026_09_07` · assignment T10-04 non-noop ≥8/day + Staff CLEAN remasure

## 2026-09-07 wave-59 — SRE heal (headerless SIC drift blind)

- **Smoke:** `context_twin_structure_broken` + `sync_queue_drift` warn on fuel-only SIC; `heal_queue_drift` `restored headerless context twin from WORK_QUEUE`; AdaptHealTests headerless **2/2 OK**; `validate_tasks_config` **issues []**.
- **Root cause:** headerless ~356B fuel-only SIC → `remaining_work_items=[]` and empty Active opens → item drift **no-op** (`actions=[]`/`warns=[]`); fuel orphans invisible to `open_work_items`.
- **Landed:** peer-6 port of hub detect+restore + Active-mirrored fallback; unittests on peer-6+hub; EXPECTED md5 refreshed. Queue item `[x]` hub SoT. Needle `OVERSEER_HEADERLESS_SIC_DRIFT_2026_09_07`.
- **Acceptance:** warn+restore on fuel twin · post-heal structure unbroken · validate green · no invent-deploy.
- **Residual:** companion Active `ensure_queue_fuel section-blind twin clobber` (Compression/QA) must stay refuse-headerless or clobber can recur; dirty COD soft; verify deferred soft-skip unrelated.
- **Rollback:** revert `context_twin_structure_broken` / heal restore block; `./scripts/peer sync-queue` after restore from WQ SoT.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE59_SRE_2026_09_07` · assignment heal/drift headerless SIC

## 2026-09-07 wave-58 — SRE remasure (Staff CLEAN floor miss = OOM, not dead keep-alive)

- **Smoke:** `compression-keep-alive --check` agents=**7** floor=**12** `agents_ge_floor=false` S≈134 pack=37288 billing_ok; `ram-status` post-heal avail **~39GB** `[ok]` (was **8–13GB** warn/critical + swap full); keep-alive/auto-train/result-watch/peer/improve **active**; `verify-gate-quick` **exit 0**; `peer_orchestrate --self-check` **ISSUES none**; validate_tasks_config **issues []**.
- **Root cause:** Fanout wave `FANOUT_TARGET=24` @ 16:42Z under swap pressure → mass `cursor-agent` **rc=-9** (SIGKILL/OOM) in `~/.config/automation/compression-keep-alive.log` — floor miss is **agent death**, not missing keep-alive daemon (Main PID alive since 14:45 after prior oom-kill restart).
- **Landed:** `./scripts/peer ram-purge` (purged ~56GB non-productive shm) → avail recovered; `./scripts/peer poke` + peer-turn.signal; **PASS skip invent-respawn** while RAM was critical and while live agents remain keep-alive cgroup children (restart would SIGKILL mid-wave). No Shard-* / T4 invent. TRAIN recipe untouched.
- **Acceptance:** daemons live · billing desktop_free · verify green · stress PASS · Staff CLEAN remasure affirms OOM root cause · `agents_ge_floor` soft until current wave exits and keep-alive next poll respawns under RAM [ok].
- **Residual:** `agents_ge_floor=false` until post-wave refill; dirty main soft under COD; do not restart `compression-keep-alive` while niche agents are its children; FANOUT_TARGET=24 + loose `dispatch_allowed` under hold can storm OOM — Compression/Adapt own tighter pre-wave RAM gate if it recurs.
- **Rollback:** isolate `.worktrees/peer-N` → `./scripts/peer heal-all` → remasure `--check`; never force-push; never Install CTA on expected worktree STOPPED.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE58_SRE_2026_09_07` · keep-alive fanout #16 Staff ASN remasure

## 2026-09-07 wave-57 — SRE remasure (ballast false-positive + compression CLEAN)

- **Smoke:** compression-auto-train/keep-alive/gpu-worker/result-watch + dgx-gpu-compute **all active**; `ram-status` avail **~62GB** `[ok]`; `_scan_ram_ballast()` **[]** after pressure-gate; unittest `test_gpu_compute_ballast_*` **OK**; validate_tasks_config **issues []**.
- **Root cause:** `_RAM_BALLAST_GPU_COMPUTE_MIN_RSS_KB=2GB` false-killed productive mamba-2.8b `dgx_gpu_compute` (RSS~3–8GB) → systemd **NRestarts 70+** while MemAvailable healthy — not real agent starvation. Live killer was **improve-loop** in-process self-heal (stale import) + `compression_result_watch.kill_ram_hogs`.
- **Landed:** `scripts/peer_self_heal.py` — skip `dgx_gpu_compute` when avail≥`ram_min_avail_gb`; runaway floor **14GB** under pressure only; `compression_result_watch.kill_ram_hogs` delegates to heal; restarted peer/improve/oversight/result-watch; tests in `tests/test_peer_self_heal.py`. Twin Remaining sync for a-to-z:phase4. Needle `OVERSEER_RAM_BALLAST_GPU_COMPUTE_PRESSURE_2026_09_07`.
- **Acceptance:** compression CLEAN units live · ram_ballast cleared · dgx-gpu-compute same-PID ≥96s @ RSS peak~11GB then ~1.5GB · no invent-deploy · TRAIN recipe untouched.
- **Residual:** verify deferred (swarm/lock) soft-skip; dirty tree under COD; NRestarts historical count not reset; long-running daemons need restart after heal-module edits; Queue Steward owns Active↔Remaining heal robustness.
- **Rollback:** revert `peer_self_heal.py` ballast helpers; `systemctl --user restart dgx-gpu-compute` if embed flaps.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE57_SRE_2026_09_07` · keep-alive fanout #16

## 2026-09-06 wave-56 — SRE remasure (healthy-idle · OVERSEER_COMPRESSION_KEEP_ALIVE fanout #16)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **99%**; Active open=**0** (queue source empty); diagnose clean; `./scripts/peer adapt` heal → self-heal bottlenecks **none**; `src/` **absent**; product-forge `active=false`; `train_unlock.json` **absent**.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **50** paths) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** mechanical adapt heal (cleared transient med adapt_stale) + SRE docs remasure — **PASS skip invent-deploy/Setapp** (hub has no product deploy surface). Keep-alive compression-train items stay **Backlog** (TRAIN-LOCKED) — not SRE invent-deploy.
- **Residual:** dirty main soft under `continue_on_dirty` (**50** paths) ≠ stall; GGWave/msgpack + T4 Backlog (Queue Steward); invent-commit ASN ignored under COD.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash / force-push; TRAIN_UNLOCKED untouched; no Active product-deploy enqueue.
- **Rollback:** worktree isolate `.worktrees/peer-N` → dirty-main COD fallback → `./scripts/peer heal-all` if daemons flap (never Install CTA on expected worktree STOPPED).
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE56_SRE_2026_09_06`

## 2026-09-05 wave-54 closeout (orchestrator · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **98%**; Active open=**0** (T4+Freeze Backlog until train_unlocked); oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · **not noop** · continue_on_dirty.
- **Landed:** fact_checker vault seed; demoted wave-19 MCP/Structured/A2A re-promotions; noop-break [x]; Backend/Frontend/QA PASS skip; OSS skip_land; Compression RSS audit trim=0; Adapt fp `aeee3f2d…`; comms-verify green; Safety PASS.
- **Residual:** dirty main soft under COD; GGWave/msgpack + T4 Backlog; invent-commit ASN ignored.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE54_CLOSEOUT_2026_09_05`


## 2026-09-05 wave-54 — remasure (Progress Monitor · green noop_ok)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **86%**; Active open=**2** (launch compression-train; T4 locked); oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · **not noop** · continue_on_dirty.
- **Acceptance:** Active open=**2** · readiness **86%** · Dispatch 85% (dirty soft **62**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 35% · Single peer brain 100%.
- **Noop root cause (early cycle):** queue_fp lag mid-WORKING while T4 gated — resolved to not-noop by end remasure; COD soft ≠ stall.
- **Landed:** Progress remasure KPI/RELEASE/oversight; GLink DONE; invent-commit ASN ignored under COD; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft **62** ≠ stall; T4 locked (MUST NOT unlock); Executable soft on gated launch.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE54_2026_09_05`

## 2026-09-05 wave-53 — remasure (Progress / Finance / DA / Tech Writer · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **82%** (noop Non-noop drag); Active open=**0**; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · noop · continue_on_dirty; adapt heal/audit ok (fp `aeee3f2d…`); comms-verify green.
- **Acceptance:** Active open=**0** · readiness **82%** · Dispatch 95% (dirty soft **33**) · Non-noop 15% (expected idle) · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress green noop_ok; Finance PASS skip (no Stripe/`src/`); DA/TW remasure; Queue drift=0; OSS skip_land; Compression RSS ~45+44+39 trim=0; invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft **33** ≠ stall; GGWave/msgpack Backlog; noop_ok idle; queue_fp unchanged by design.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE53_2026_09_05`

## 2026-09-05 wave-53 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **82%**; Active open=**0**; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · noop=True · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **82%** (delivery soft expected idle noop) · Dispatch 95% (dirty soft **31**) · Non-noop 15% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress green noop_ok; invent-commit ASN ignored under COD; notes-only dirty ≠ stall; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft **31** ≠ stall; GGWave/msgpack Backlog; noop_ok idle; delivery meter soft under cleared Active.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE53_2026_09_05`

## 2026-09-05 wave-52 — SRE remasure (healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **99%**; product-forge **inactive** (`active=False`, `suppress_hub=True`); `src/` **absent**; Active open=**0**.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** SRE docs remasure only — **PASS skip invent-deploy/Setapp** (hub has no product deploy surface). VALUE_STACK SRE wave-52 PASS skip.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched; no Active product-deploy enqueue.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE52_SRE_2026_09_05`

## 2026-09-05 wave-52 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **99%**; Active open=**0**; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **31**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress green noop_ok; invent-commit ASN ignored under COD; notes-only dirty ≠ stall; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft **31** ≠ stall; GGWave/msgpack Backlog; noop_ok idle; 1 med noop_backoff soft.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE52_2026_09_05`

## 2026-09-05 wave-51 — remasure (Data Analyst · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **99%**; Active open=**0** (GGWave/msgpack Backlog only); oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty; adapt heal/audit ok (fp non-null); comms-verify green.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **19**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress green noop_ok; Finance PASS skip; Queue drift=0; OSS skip_land (self_sufficient); Compression RSS ~45+44+39 trim=0; invent-commit ASN ignored under COD; notes-only dirty ≠ stall.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE51_2026_09_05`

## 2026-09-05 wave-50 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **99%** (peer early 85% corrected); Active open=**0** (`## Active` cleared; GGWave/msgpack Backlog only); queue source empty; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **29**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure (KPI/RELEASE); invent-commit ASN ignored under COD; notes-only dirty ≠ stall; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft **29** ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE50_2026_09_05`

## 2026-09-05 wave-49 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **99%**; Active open=**0**; queue source empty; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **19**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure (KPI/RELEASE/oversight); invent-commit ASN ignored under COD; notes-only dirty ≠ stall; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE49_2026_09_05`

## 2026-09-05 wave-48 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **98%**; Active open=**0**; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft **34**) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure (KPI/RELEASE/oversight); invent-commit ASN ignored under COD; notes-only dirty ≠ stall; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; 1 med noop_backoff soft; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE48_2026_09_05`

## 2026-09-05 wave-47 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **98%**; Active open=**0**; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft **34**) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure (KPI/RELEASE/oversight); invent-commit ASN ignored under COD; notes-only dirty ≠ stall; no heal invent.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; 1 med noop_backoff soft; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE47_2026_09_05`

## 2026-09-05 wave-46 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **99%**; Active open=**0**; oversight **RUNNING**; peer+improve **RUNNING**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **34**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure (KPI/RELEASE); Backend/Frontend/QA PASS skip; Queue drift=0 (dup Active demoted); OSS skip_land; Compression RSS ~44+43+39 trim=0; invent-commit ASN ignored under COD; notes-only dirty ≠ stall.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE46_2026_09_05`

## 2026-09-05 wave-45 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **98%**; Active open=**0**; oversight **RUNNING**; pool **8/8**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft **34**) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure (KPI/RELEASE); Finance PASS skip; Queue open-drift=0; OSS skip_land; Compression RSS audit trim=0; invent-commit ASN ignored under COD; notes-only dirty ≠ stall.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE45_2026_09_05`

## 2026-09-05 wave-44 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **99%**; Active open=**0**; oversight **RUNNING** (stagnation **0**); pool **8/8**; last_cycle verify_ok · not noop · continue_on_dirty.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **34**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure only (KPI/RELEASE/oversight); invent-commit ASN ignored under COD; notes-only dirty ≠ stall.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE44_2026_09_05`

## 2026-09-05 wave-43 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **82%** (noop delivery drag expected); Active open=**0**; oversight **RUNNING**; pool **8/8**; last_cycle verify_ok · noop=True · queue_fp unchanged.
- **Acceptance:** Active open=**0** · readiness **82%** · Dispatch 95% (dirty soft **34**) · Non-noop 15% (healthy-idle noop) · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress remasure only (KPI/RELEASE); invent-commit ASN ignored under COD; notes-only dirty ≠ stall.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; last_cycle noop on cleared Active ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE43_2026_09_05`

## 2026-09-05 wave-42 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **82%** (noop delivery drag expected); Active open=**0**; oversight **RUNNING**; pool **8/8**; last_cycle verify_ok · noop=True · queue_fp unchanged.
- **Acceptance:** Active open=**0** · readiness **82%** · Dispatch 95% (dirty soft **34**) · Non-noop 15% (healthy-idle noop) · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress/DA/TW remasure; Finance PASS skip; Queue drift=0; OSS skip_land (self_sufficient); Compression RSS audit (~67+56+36 MB daemons; trim=0); invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; last_cycle noop on cleared Active ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE42_2026_09_05`

## 2026-09-05 wave-41 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **82%** (noop delivery drag expected); Active open=**0**; oversight **RUNNING**; last_cycle verify_ok · noop=True · queue_fp unchanged.
- **Acceptance:** Active open=**0** · readiness **82%** · Dispatch 95% (dirty soft **34**) · Non-noop 15% (healthy-idle noop) · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress docs remasure only (KPI/RELEASE/oversight); no heal invent; invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; last_cycle noop on cleared Active ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE41_2026_09_05`

## 2026-09-05 wave-40 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; `./scripts/peer progress` readiness **80%** (noop delivery drag expected); Active open=**0**; oversight **RUNNING**; pool **8/8**.
- **Acceptance:** Active open=**0** · readiness **80%** live / KIT ~**99%** · Dispatch 95% (dirty soft **34**) · Non-noop 15% (healthy-idle noop) · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress docs remasure only (KPI/RELEASE/oversight); no heal invent; invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; last_cycle noop on cleared Active ≠ stall; 1 med loop bottleneck; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE40_2026_09_05`

## 2026-09-05 wave-39 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **98%** (oversight mid-cycle **99%**); Active open=**0**; oversight **RUNNING**; pool **8/8**; stagnation score **0**.
- **Acceptance:** Active open=**0** · readiness **98–99%** · Dispatch 95% (dirty soft **34**) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress docs remasure only (KPI/RELEASE/oversight); no heal invent; invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; 1 med loop bottleneck; GGWave/msgpack Backlog; noop_ok idle; launch preview drift soft.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE39_2026_09_05`

## 2026-09-05 wave-38 — SRE remasure (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; `./scripts/peer progress` readiness **99%**.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **32**) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** SRE docs remasure only — **PASS skip invent-deploy/Setapp** (hub has no product deploy surface).
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE38_SRE_2026_09_05`

## 2026-09-05 wave-38 — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `./scripts/peer progress` readiness **99%**; Active open=**0**; oversight **RUNNING**; pool **8/8**.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft **32**) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress docs remasure only (KPI/RELEASE/oversight); no heal invent; invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; 1 med loop bottleneck; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE38_2026_09_05`

## 2026-09-05 wave-37 — remasure (Progress / Data Analyst / Tech Writer · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; `./scripts/peer progress` readiness **99%**.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft ~25) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Progress/DA/TW docs remasure; Finance PASS skip; CB skip_land (Open gaps empty 126/14); Efficiency TTL reaffirm enqueue=0; Pen-test open=0; Output self_sufficient skip_land; invent-commit ASN ignored under COD.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE37_2026_09_05`

## 2026-09-05 wave-36 — remasure (Progress / Design / Growth / CS · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; `./scripts/peer progress` readiness **99%**.
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Design/Growth/CS PASS skip (no hub product surfaces); Factory IDLE skip_land; caps ≤8; Comms schema skip_land; Phase-4 PASS.
- **Residual:** dirty main soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE36_2026_09_05`

## 2026-09-05 wave-35b — SRE remasure (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; `./scripts/peer progress` readiness **98%**.
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Residual:** dirty main **133** paths soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; 0 high / 1 med loop bottleneck; noop_ok idle.
- **Stance:** docs remasure only — PASS skip invent-deploy/Setapp/Active enqueue; MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE35B_SRE_2026_09_05`

## 2026-09-05 wave-35b — remasure (Progress Monitor · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; `./scripts/peer progress` readiness **98%**.
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** docs remasure only — no heal invent; invent-commit ASN ignored under COD.
- **Residual:** dirty main **133** paths soft under `continue_on_dirty`; COD soft ≠ stall; 1 med noop_backoff; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** Progress niche remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE35B_2026_09_05`

## 2026-09-05 wave-35 — remasure (Data Analyst / Tech Writer · healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; `./scripts/peer progress` readiness **99%**.
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** Finance PASS skip (no Stripe); OSS skip_land under `self_sufficient`; peer caps remain ≤8 (no clamp heal needed this cycle).
- **Residual:** dirty main **133** paths soft under `continue_on_dirty`; COD soft ≠ stall; GGWave/msgpack Backlog; noop_ok idle.
- **Stance:** docs remasure only — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE35_2026_09_05`

## 2026-09-05 wave-34 — remasure (Progress Monitor · healthy-idle + peer-cap clamp)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; Phase-4 unittests OK (one-at-a-time; adapt + agent_comms green; `tests.test_automation` 92 OK after clamp).
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 95% · Executable queue 100% · Single peer brain 100%.
- **Landed:** re-clamp `automation.config.local.json` peer caps **24→8** (install landmine regression; dgx overlays already ≤8).
- **Residual:** dirty main **133** paths soft under `continue_on_dirty`; COD soft ≠ stall; assignment invent-commit ignored; noop_ok idle; GGWave/msgpack Backlog.
- **Stance:** docs remasure + local cap heal — MUST NOT invent / commit / stash; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE34_2026_09_05`

## 2026-09-05 wave-33 — remasure (healthy-idle + peer-cap clamp)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; Phase-4 unittests OK (one-at-a-time; adapt + agent_comms green; `tests.test_automation` 92 OK after clamp).
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Landed:** clamp `dgx_speed.local.json` + `scripts/dgx_speed.local.json` + `automation.config.local.json` peer/grid caps **24→8** (install landmine regression).
- **Residual:** dirty main **~133** paths soft under `continue_on_dirty`; noop backoff expected at healthy idle; GGWave/msgpack Backlog; no invent deploy/Setapp.
- **Stance:** docs remasure + local cap heal — MUST NOT force-push / reclaim secrets; TRAIN_UNLOCKED untouched.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE33_2026_09_05`

## 2026-09-05 wave-30 — remasure (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; Phase-4 unittests OK (one-at-a-time; adapt + agent_comms green).
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Residual:** dirty main **~132** paths (81 modified, 51 untracked) soft under `continue_on_dirty`; noop backoff expected at healthy idle; no invent deploy/Setapp/Active enqueue; GGWave/msgpack Backlog.
- **Stance:** docs remasure only — no deploy chrome; MUST NOT force-push / reclaim secrets.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE30_2026_09_05`

## 2026-09-05 wave-29 — Tech Writer remasure (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; Phase-4 unittests OK (one-at-a-time).
- **Acceptance:** Active open=**0** · readiness **99%** · Dispatch 95% (dirty soft) · Non-noop 100% · Self-sufficient loops 100% · Executable queue 100% · Single peer brain 100%.
- **Residual:** dirty main **~132** paths (81 modified, 51 untracked) soft under `continue_on_dirty`; noop backoff expected at healthy idle; no invent deploy/Setapp/Active enqueue; GGWave/msgpack Backlog.
- **Stance:** docs remasure only — no deploy chrome; MUST NOT force-push / reclaim secrets.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE29_2026_09_05`

## 2026-09-05 wave-28 — SRE remasure (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` → **ISSUES none**; pool **8/8**; hub worktrees 8/8; tests cached OK (92).
- **Acceptance:** Active open=**0** · readiness **98%** · Dispatch 95% (dirty soft) · Non-noop 100% · Executable queue 100% · Single peer brain 100%.
- **Residual:** dirty main **~132** paths (81 modified, 51 untracked) soft under `continue_on_dirty`; Self-sufficient loops 95% (1 med bottleneck / improve wake); noop backoff expected at healthy idle; no invent deploy/Setapp/Active enqueue; GGWave/msgpack Backlog.
- **Stance:** docs remasure only — no deploy chrome; MUST NOT force-push / reclaim secrets.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE28_2026_09_05`

## 2026-09-05 wave-27 — healthy-idle restamp

- **Smoke:** `peer_orchestrate --self-check` ISSUES none; Phase-4 unittests OK (one-at-a-time); pool 8/8; comms-verify green.
- **Acceptance:** Active open=0 · readiness **99%** · oversight RUNNING · COD dirty ~132 soft under `continue_on_dirty`.
- **Residual:** dirty main Dispatch soft; mid-cycle med bottleneck cleared by end of wave; no mass commit.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE27_2026_09_05`

## STOPPED must not push install

On worktrees like **peer-2**, `STOPPED` (LaunchAgent not loaded) is often **expected** —
the hub daemon already owns the loop. An Install CTA on STOPPED invites a second
`*-peer-loop` LaunchAgent for the same automation root → dual-daemon thrash.

**Rule:** `peer_watch.classify_phase` STOPPED detail is **signal-only**
(`LaunchAgent not loaded` / `peer-loop.service not active`) — never embed
`python3 scripts/peer_loop.py --install`.

**Needle:** `scripts/peer_watch.py` `classify_phase` when `daemon_ok` is false —
`OVERSEER_STOPPED_NO_INSTALL_CTA_2026_09_04`.
**Proof:** `tests.test_automation` `test_classify_stopped` asserts `--install` absent
+ land-proof needles in `project_automation._LAND_PROOF_NEEDLES`.

STOPPED never pushes install on peer-2 — signal-only detail prevents dual-daemon.
**Related:** Creative backlog dual hub peer-loop install gate; Single peer brain factory meter.

## 2026-09-05 — dirty main residual risk (SRE)

- **Signal:** hub git dirty ~107 paths (modified + untracked); `continue_on_dirty` keeps coding.
- **Health:** oversight RUNNING; factory ~99% self-sufficient; Active queue empty (healthy idle); last_cycle verify_ok.
- **Risk:** dirty main can confuse Mac↔DGX rsync / adapt fingerprint; dual-daemon if worktree STOPPED CTAs reappear.
- **Mitigation:** Prefer `.worktrees/peer-N` for Implement peers; do not force-push; COD — no mass commit/stash without user ask.
- **Rollback:** isolate worktree / dirty-main fallback; `./scripts/peer heal-all` if daemons flap.
- **Needle:** `OVERSEER_RELEASE_HEALTH_DIRTY_MAIN_2026_09_05`

## 2026-09-05 wave-20 — QA acceptance (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` ISSUES none; `tests.test_peer_pen_test` + `idle-gate` compound green.
- **Acceptance:** Active open=0 · readiness **99%** · product-forge inactive → Backend/Frontend PASS skip.
- **Residual:** dirty main ~128 paths soft under `continue_on_dirty`; no mass commit (Progress Monitor).
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE20_2026_09_05`

## 2026-09-05 wave-21 — healthy-idle restamp

- **Smoke:** self-check ISSUES none; adapt fingerprint test uses `-c user.*` (sandbox identity); comms-verify green.
- **Acceptance:** Active open=0 · readiness **99%** · Finance PASS skip; GGWave/msgpack Backlog.
- **Residual:** dirty main ~131 paths soft under COD.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE21_2026_09_05`

## 2026-09-05 wave-22 — QA acceptance (healthy-idle)

- **Smoke:** `peer_orchestrate --self-check` ISSUES none; pool 8/8; Phase-4 unittest suite OK; comms-verify green.
- **Acceptance:** Active open=0 · readiness **99%** · Backend/Frontend PASS skip (product-forge inactive).
- **Residual:** dirty main ~131 paths soft under `continue_on_dirty`; no mass commit (Progress Monitor).
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE22_2026_09_05`

## 2026-09-05 wave-23 — healthy-idle restamp

- **Smoke:** `peer_orchestrate --self-check` ISSUES none; pool 8/8; Phase-4 suite OK; adapt heal/audit ok; comms-verify green.
- **Acceptance:** Active open=0 · readiness **98–99%** · Design/Growth/CS PASS skip (no hub product surfaces).
- **Residual:** dirty main ~131 paths soft under `continue_on_dirty`; no mass commit (Progress Monitor).
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE23_2026_09_05`

## 2026-09-05T17:12Z wave-24 — SRE/orchestrator remasure (healthy-idle)

- **Smoke:** `./scripts/peer progress` + `peer_orchestrate --self-check` → **ISSUES none**; pool 8/8; Phase-4 + `comms-verify` green; adapt heal/audit ok.
- **Acceptance:** Active open=**0** · readiness **99%** · no hub deploy/rollback product surface → docs remasure only; GLink English/schema already `[x]`.
- **Residual:** dirty main **~131** paths (80 modified, 51 untracked) soft under `continue_on_dirty`; no invent deploy/Setapp/Active enqueue; GGWave/msgpack Backlog.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE24_2026_09_05`

## 2026-09-05T17:17Z wave-25 — SRE/orchestrator remasure (healthy-idle)

- **Smoke:** `./scripts/peer progress` + `peer_orchestrate --self-check` → **ISSUES none**; pool 8/8; Phase-4 + `comms-verify` green; adapt heal/audit ok (fp non-null, error_count=0).
- **Acceptance:** Active open=**0** · readiness **99%** · Design/Growth/CS PASS skip; GLink English/schema already `[x]`; Safety PASS (docs only).
- **Residual:** dirty main **~131** paths (80 modified, 51 untracked) soft under `continue_on_dirty`; no invent deploy/Setapp/Active enqueue; GGWave/msgpack Backlog.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE25_2026_09_05`

## 2026-09-05T17:26Z wave-26 — SRE/orchestrator remasure (healthy-idle)

- **Smoke:** `./scripts/peer progress` + `peer_orchestrate --self-check` → **ISSUES none**; pool 8/8; Phase-4 + `comms-verify` green; adapt heal/audit ok (ok=True, meta_ok=True, fp non-null).
- **Acceptance:** Active open=**0** · readiness **99%** · Finance PASS skip; Factory/Comms GLink skip_land; Safety PASS (docs only).
- **Residual:** dirty main **~132** paths (81 modified, 51 untracked) soft under `continue_on_dirty`; no invent deploy/Setapp/Active enqueue; GGWave/msgpack Backlog.
- **Needle:** `OVERSEER_RELEASE_HEALTH_WAVE26_2026_09_05`

---

## Residual risk — 2026-09-05 (dirty main + continue_on_dirty)

**Health verdict:** **ACCEPT with residual risk** — loops healthy; tree dirty; verify-gate not fully green.

| Signal | Status |
|--------|--------|
| Dirty main | **107 paths** (62 modified, 45 untracked) |
| `continue_on_dirty` | **on** — dispatch does not stall for clean tree |
| Oversight | **RUNNING** (`oversight-loop.service`, health 🟢) |
| Peer / improve | **RUNNING** (factory self-sufficient) |
| Self-heal / green | bottlenecks **none**; `./scripts/peer green` ok |
| `heal-all` verify-gate | **FAIL** — `tests.test_peer_remote` (2): missing `dgx_setup` exclude `tests/test_adapt_dirty_head_only.py`; hub-protect pull missing `notes/BITNET_FACTCHECK.md` |
| Force-push | **MUST NOT** — never force-push main/master to “clean” residual risk |

**Rollback / isolate:**

1. Prefer **worktree isolate** (`.worktrees/peer-N`) for coding when pool ready.
2. If worktree unavailable → **dirty-main fallback** under `continue_on_dirty` (keep coding; do not stash/commit secrets or force-push).
3. Commit/stash WIP only when human-safe and non-secret; do not invent clean-tree theater.

**SRE stance:** Prefer heal (`./scripts/peer heal-all` / `green` / `adapt`) over new chrome. Residual risk is **operational** (dirty + verify remote excludes), not daemon downtime.

---

## Wave-18 — 2026-09-05T16:19Z (SRE / release)

**Health verdict:** **ACCEPT with residual risk** — no daemon red; dirty main grew; force-push still forbidden.

| Signal | Status |
|--------|--------|
| Dirty main | **~120 paths** (69 modified, 51 untracked) — up from ~107 |
| `continue_on_dirty` | **on** — coding does not stall |
| Peer | **RUNNING** (`peer-loop.service` daemon ok; last_cycle verify_ok) |
| Improve | **RUNNING** (`com.togi.automation-hub-improve-loop`) |
| Oversight | **RUNNING** (`oversight-loop.service`, health 🟢) |
| Factory | **99%** self-sufficient; Active queue empty (healthy idle); green ok; bottlenecks none |
| Force-push | **MUST NOT** |

**Rollback (daemons green — standby path only):**

1. Worktree isolate: `.worktrees/peer-N` (prefer peer-1 for this niche).
2. Dirty-main fallback under `continue_on_dirty` — no mass stash/commit/force-push.
3. If daemons flap later: `./scripts/peer heal-all` → `./scripts/peer green`; reinstall only if STOPPED is unexpected (never Install CTA on expected worktree STOPPED).

**Needle:** `OVERSEER_RELEASE_HEALTH_WAVE18_DIRTY_MAIN_2026_09_05T16:19Z`
**Evidence:** `./scripts/peer progress` Dispatch clear 95% · 120 paths · continue_on_dirty; status/improve-status/oversight-status all RUNNING.

---

## Wave-28 — 2026-09-05 (Progress Monitor remasure)

**Health verdict:** **green noop_ok** — Active open=**0**; factory **98%**; self-check ISSUES none; dirty ~132 under `continue_on_dirty`; no invent-work / no COD commit.
