# Cursor overseer note — 2026-09-04 SYNC_VERIFY_CMDS

- **2026-09-04 stagnation dispatch (event-triggered — sync_verify_commands_state)**
  - **Found:** dispatch red (peer/improve STOPPED + dual-namespace LaunchAgents) was stale/Mac-shaped — live Linux systemd `peer-loop`/`improve-loop`/`oversight-loop` were UP; real blocker = ADAPT_STALE: `run_peer_tasks` called missing `sync_verify_commands_state` (AttributeError skipped notes-only sync path) + local.json lean drift (missing `test_peer_remote`) while hub-protect restore refused incomplete vault (`refuse bad vault automation_adapt.py`) and rewrote lands every 5s.
  - **Fixed:** permanent `OVERSEER_SYNC_VERIFY_CMDS_2026_09_04` — `sync_verify_commands_state` aligns lean local.json + adapt-state (+ demoted `~/.config/automation` twin) and syncs git fingerprint before audit; vault_ok/beat-mac needles require SYNC; promoted good overseer-land adapt with `OVERSEER_LEAN_OCTET_STICKY`; bottlenecks **0**; `should_re_adapt=False`; SyncVerify unittest green; test-quick green; factory **99%**.
  - **Still broken:** dirty tree caps Dispatch ~95%; hub-protect-restore.path/timer can be reinstalled by peer/oversight mid-land; Mac rsync still fights unprotected scripts.
  - **Needs human:** Commit WORKING scripts when safe; keep Mac rsync from `--delete`-clobbering hub-protect vault.

