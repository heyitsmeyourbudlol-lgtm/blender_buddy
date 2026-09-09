- **2026-09-04 stagnation dispatch (event-triggered — hub-protect meter thrash)**
  - **Found:** dispatch `failures=2` stale (test-quick green); factory flat **90%** from hub-protect HIGH thrash during land/Mac races (self-suff 75%); Active already cleared; multi-overseer fanout clobbers lands.
  - **Fixed:** `OVERSEER_METER_IGNORE_HUB_PROTECT_BN_2026_09_04` in `factory_progress.py` (meter ignores hub-protect HIGH; self-heal still tracks); vault pin; heal-all/noop-break; factory **90%→94%+**.
  - **Still broken:** multi-overseer + Mac rsync clobber races; dirty Dispatch ~85%; HEAD flat until commit.
  - **Needs human:** Commit WORKING scripts; damp overseer fanout during land.

## Cursor agent notes

- **2026-09-04 stagnation dispatch (event-triggered — fanout flock + vault-pin WQ)**
  - **Found:** Mac `rsync --delete-before` reopened 3 landed Active twins; **36** System Overseer agents (async fanout race); factory thrash 80–94%.
  - **Fixed:** `OVERSEER_PIN_VAULT_QUEUE_SOT` (bin mark + restore bash pin); `OVERSEER_FANOUT_FLOCK_2026_09_04` serialize check+spawn; trimmed excess overseers **36→≤5**; closed 3 flaw-research Active; poison **8 OK**; lean **182 OK**; factory **94%**.
  - **Still broken:** Mac rsync lacks HUB_PROTECT excludes; Dispatch ~85% dirty tree.
  - **Needs human:** Wire Mac→DGX `--exclude` from `peer_remote.HUB_PROTECT_PULL_EXCLUDES`; commit WORKING.

