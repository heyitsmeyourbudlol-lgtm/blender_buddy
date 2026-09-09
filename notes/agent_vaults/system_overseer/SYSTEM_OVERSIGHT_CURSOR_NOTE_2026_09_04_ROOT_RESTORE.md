# ROOT_RESTORE

- **2026-09-04 stagnation dispatch (event-triggered)**
  - **Found:** critical tests FAIL theater + 3 Active flaw-research reopen; factory ~90%; `_hub_protect_restore_paused` missed repo-root `RESTORE_PAUSED`; `restore-hub-protect.sh` `vault_ok` had `*)` before `peer_self_heal.py` (dead vault gate).
  - **Fixed:** Active 3→0; `OVERSEER_ROOT_RESTORE_PAUSED_SELF_HEAL_2026_09_04` + unittest; restore vault_ok order + ROOT needle; vault/golden pinned; restore timer stopped + wrap stubbed during land; factory **90%→91–95%**.
  - **Still broken:** Dispatch ~85% dirty tree; hub-protect timer fights WORKING lands when unstubbed.
  - **Needs human:** Commit WORKING scripts; Mac sender must not `--delete-before` hub-protect vault.

