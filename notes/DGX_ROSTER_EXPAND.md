# DGX roster expand + prefer_remote (2026-09-05)

Needle: `OVERSEER_DGX_ROSTER_EXPAND_2026_09_05`

## What changed

| Change | Detail |
|--------|--------|
| Roster | **25 → 45** niches in `scripts/peer_tasks.json` |
| `prefer_remote` | **34** roles prefer DGX/SSH when host resolvable |
| Agent ceiling | `_DGX_AGENTS_CAP_CEILING` **96** (live target **96**) |
| Live pool | `max_parallel_peers` / hub pool / worktrees → **24** (local.json) |
| Match templates | `fact_check`, `bitnet_research`, `compression_train`, `research_speed`, `niche_distill` |
| Dispatch | `should_dispatch_remote(prefer_remote=…)` in peer_remote → peer_terminal → parallel_dispatch |

## New DGX-heavy niches (examples)

fact_checker · bitnet_researcher · compression_trainer · research_speed_engineer · niche_distiller · architecture_researcher · train_eval_runner · gpu_profiler · model_serve_engineer · dataset_curator · dgx_ops · …

## Offload reality

- **Mac is already `mac-offloaded`** — peer/improve loops run on Spark systemd.
- Raising pool to **24** uses Spark RAM/agents harder (was capped at 8).
- Per-role `prefer_remote` lets Mac-as-brain SSH remaining heavy niches to CLEAN even if global `agent_remote.enabled` is false (needs `ssh_host`, default CLEAN).

## Ops

```bash
./scripts/peer agents
python3 scripts/peer_orchestrate.py --self-check
./scripts/peer ensure-pool   # grow worktrees to 24 if needed
./scripts/peer dgx-status
```
