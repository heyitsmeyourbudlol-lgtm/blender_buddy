_Cursor overseer appends dated bullets here after each review._

- **2026-09-04 stagnation dispatch (event-triggered — heal research daemon)**
  - **Found:** verify-ok noop theater (board 88% / Creative 3 open / score 144) while live meter was healthy-idle; root cause = `repo-research-loop.service` **disabled+STOPPED** so digest aged >30m → research_stale stagnation; heal-all never scanned/restarted research (only peer/improve); when factory dipped <90% healthy_idle veto failed and flat/HEAD theater piled on.
  - **Fixed:** permanent `OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04` in `peer_self_heal.py` (scan `daemon_research_stopped`, `_heal_research_daemon`, `enable --now` in `_ensure_systemd_repo_research_unit`); `OVERSEER_HEALTHY_IDLE_DEMOTE_RESEARCH_STALE_2026_09_04` in `peer_oversight_events.py`; hub-protect restore/beat needles + vault pin; enable --now research; force research digest; heal-all green; test-quick **185 OK**; factory **88%→99%** (+11); Active **0**; stagnation score **0**.
  - **Still broken:** Dirty tree caps Dispatch ~95%; HEAD flat until human commit; Creative Newdrop/registry verify deferred under `self_sufficient`.
  - **Needs human:** Commit WORKING scripts when safe; leave `factory_meter_mode=self_sufficient`.

