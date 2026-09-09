# Cursor overseer note — 2026-09-04 fanout + healthy-idle soft

## Found
- 8× System Overseer fanout (async spawn invisible in /proc between flock release)
- soft `agent_exit_soft` / verify_ok=False pierced healthy_idle → flat-96% + HEAD theater
- hub-protect restore timer reinstalled mid-land; notes vault poisoned rewound events

## Fixed
- `OVERSEER_FANOUT_PENDING_STAMP_2026_09_04` + `TRIM_SIGKILL` + cycle-start trim (`peer_oversight.py`)
- `OVERSEER_HEALTHY_IDLE_SOFT_VERIFY` / `LOCAL_ONLY_DEMOTE` / `NO_SAFETY_NET` (`peer_oversight_events.py`)
- restore + beat needles; hub + notes + golden vault pin
- trimmed fanout 8→1

## Still broken / needs human
- Mac→DGX can reinstall protect timers / poison notes vault within seconds
- Dirty tree keeps git HEAD flat until human commit
- Leave `factory_meter_mode=self_sufficient`
