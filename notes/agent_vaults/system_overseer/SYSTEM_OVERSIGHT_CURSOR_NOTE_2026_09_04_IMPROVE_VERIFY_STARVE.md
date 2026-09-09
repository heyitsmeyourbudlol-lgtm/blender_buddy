# Overseer land — improve verify starvation (2026-09-04)

## Problem
Improve forever blocked on `run_local_cycle` quiet-wait (≤90s) under overseer agent swarm (>verify_quiet_max_agents), then deferred — never reached wake-peer. Factory self-sufficient loops cratered ("Improve loop not waking peer"). Concurrent heal flock-busy path also restarted an already-active improve-loop.

## Fix needles
- `OVERSEER_IMPROVE_SKIP_LOCAL_CYCLE_SWARM_2026_09_04` — skip local-cycle when agents > quiet cap
- `OVERSEER_IMPROVE_WAKE_BEFORE_VERIFY_2026_09_04` — early wake before mechanical verify
- mark_local_verify only on `local-cycle: ok`
- `OVERSEER_PEER_SKIP_RESTART_IF_ACTIVE_2026_09_04` + flock-busy skip

## Proof
- improve-loop.log: early wake + swarm skip + full cycles from 13:08+
- test-quick 185 OK; factory 91%→99%; bottlenecks 0
