# Overseer land — OVERSEER_CLEARED_ACTIVE_NO_FACTORY_GATE_2026_09_04

- **2026-09-04 stagnation dispatch (event-triggered — cleared-Active no factory≥90 gate)**
  - **Found:** verify-ok noop theater score **144** (research_stale 51–55m + queue_fp×6 + factory flat **88%** + ASI flat 83% + HEAD-flat + 14–16 cycles). Live meter was often already ≥99% / Active empty — chicken-egg: research_stale tanks self-sufficiency below 90%, which blocked `healthy_idle` demote, so research_stale + flat/HEAD theater re-armed soft-dispatch forever. Creative-3 on board is deferred under `self_sufficient` (not Active).
  - **Fixed:** permanent `OVERSEER_CLEARED_ACTIVE_NO_FACTORY_GATE_2026_09_04` in `peer_oversight_events.py` — `_healthy_idle_factory` / `_idle_green_pre_snap` demote theater on Active=0 + verify_ok **without** factory≥90; unittest `test_cleared_active_demotes_theater_below_factory_90`; restore/beat needles + vault pin; synced stale `~/.config/automation/IMPROVE_HORIZON.md`; heal-all green; test-quick **186 OK**; factory **99%**.
  - **Still broken:** Dirty tree caps Dispatch ~95%; HEAD flat until human commit; Creative Newdrop/registry verify deferred under `self_sufficient`.
  - **Needs human:** Commit WORKING scripts when safe; leave `factory_meter_mode=self_sufficient`.
