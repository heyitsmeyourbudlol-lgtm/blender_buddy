# DGX Speed Plan — burn RAM for factory throughput

**Goal:** Use the DGX Spark's ~121GB RAM as the primary compute pool. Speed is the currency — maximize parallel agents, shorten wake intervals, fan out factory work across external repos.

**Status:** Active (2026-09-01)

---

## Current bottleneck

| Signal | Before turbo |
|--------|----------------|
| DGX RAM available | ~110GB |
| cursor-agents running | 1 (stall pivot) |
| Parallel cap | 8 peers / 8 agents |
| Wake heartbeat | 90s continuous / 30s agent min |
| External repos | 6+ unaudited — idle |

The machine was **RAM-rich, agent-poor**. Caps and slow heartbeats left most capacity unused.

---

## Turbo profile (DGX local overlay)

Applied via `scripts/dgx_speed.local.json` → `automation.config.local.json` on DGX:

| Knob | Mac default | DGX turbo |
|------|-------------|-----------|
| `max_parallel_peers` | 8 | **16** |
| `parallel_peer_floor` | 8 | **16** |
| `max_parallel_agent_procs` | 8 | **16** |
| `improve_enqueue_cap` | 8 | **16** |
| `continuous_wake_sec` | 90 | **20** |
| `continuous_agent_min_interval_sec` | 30 | **10** |
| `improve_min_cycle_sec` | 45 | **20** |
| `local_only_verify_cooldown_sec` | 180 | **60** |
| RAM guard `dgx_max_cursor_agents` | 8 | **18** |
| RAM guard `dgx_unittest_cap` | 20 | **32** |

Worktree pool target: **16** trees (`peer-0` … `peer-15`).

---

## New daemon: factory-fanout

`scripts/factory_fanout.py` — parallel `--probe --audit` on registry repos with status `unaudited`, `needs-kit-install`, or `git`. Runs every 5 minutes, 6 repos in parallel. Burns idle cycles on **external proof** work without blocking peer-loop.

```bash
./scripts/peer factory-fanout          # one shot
./scripts/peer factory-fanout --forever  # systemd on DGX
```

---

## Implementation order

1. [x] Turbo config overlay (`dgx_speed.local.json`)
2. [x] Factory fanout script + systemd service
3. [x] **48-agent factory grid** — 32 hub + 16 external lanes (`factory_sprint`)
4. [x] RAM guard raised to 48 agents
5. [ ] Ensure 32 worktrees on DGX (`peer ensure-pool --count 32`)
6. [ ] **External proof sprint** — adapt + native verify on CPT, Newdrop, RAM, Doc2Api
7. [x] **Hot path** — cache metrics in `--quick`; parallelize peer_orchestrate self-check — landed 2026-09-08 `OVERSEER_ADAPT_GIT_FP_HEAD_INDEX_GENERATION_2026_09_08` + `OVERSEER_SELF_CHECK_PARALLEL_ADAPT_2026_09_08` · adapt `_git_fingerprint` HEAD+index gen-cache BEFORE **7.087ms**/2 shells → HIT **0.035ms**/0 (~**202×**) · self-check **13.47→7.15ms** · proof `notes/compression_artifacts/research_speed_adapt_git_fp_gen.json`
8. [ ] Dashboard: factory grid status panel

---

## What stays on Mac

- `ram-park`, `ram-guard`, `ram-gauge-hotkey` (macOS reclaim)
- `dgx-watch` + `dgx-sync` (health + rsync pull)
- Cursor IDE + human steering

---

## Success metrics

| Metric | Target |
|--------|--------|
| DGX cursor-agents during work | ≥12 sustained |
| Factory fanout cycles/day | ≥50 repo probes |
| Queue items closed/day | ↑ vs pre-turbo baseline |
| RAM available floor | never below 12GB (guard heals) |

---

## RAM acceleration layer (spare ~90GB)

Agents use ~15–27GB at full grid load. **Remaining RAM** goes to dev-speed infrastructure (not more agents):

| Layer | What | RAM |
|-------|------|-----|
| **Linux page cache** | Automatic — hot repo files stay in RAM | ~70GB (already) |
| **`/dev/shm` build caches** | pip, npm, ccache, pytest, turbo, next | up to 61GB tmpfs |
| **`dgx-ram-accel`** | Parallel native verify across all synced repos every 90s | burst during tests |
| **Repo warm** | Pre-read hot paths into page cache on boot | ~1–2GB transient |

```bash
./scripts/peer ram-accel --caches-only
./scripts/peer ram-accel --verify-only
```


```bash
./scripts/peer dgx-status
./scripts/peer factory-fanout --json
ssh CLEAN 'systemctl --user status peer-loop factory-fanout'
ssh CLEAN 'python3 ~/Automation/scripts/peer_worktree.py ensure-pool --count 16'
```

See also: [LOOP_STRATEGY.md](LOOP_STRATEGY.md) · [PEER_ORCHESTRATION.md](PEER_ORCHESTRATION.md) · [KNOWLEDGE_INDEX.md](KNOWLEDGE_INDEX.md)

## Agent notes

- **2026-09-08 research_speed_engineer** — Hot path item 7 landed: adapt `_git_fingerprint` HEAD+index gen-cache BEFORE **7.087ms** → HIT **0.035ms** (~**202×**, 0 shells) + self-check parallel adapt **13.47→7.15ms**. Needles `OVERSEER_ADAPT_GIT_FP_HEAD_INDEX_GENERATION_2026_09_08` · `OVERSEER_SELF_CHECK_PARALLEL_ADAPT_2026_09_08`. Proof `notes/compression_artifacts/research_speed_adapt_git_fp_gen.json`.
