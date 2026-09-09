# Cursor overseer note — 2026-09-04 skip-restart + healthy-idle wake

_Stagnation dispatch. Durable copy — SYSTEM_OVERSIGHT.md is mechanically rewritten._

## Found
- Improve systemd unit restarted every heal (`_ensure_systemd_improve_unit` always restart)
- Horizon-stale heal compounded thrash → no wake-peer log lines → factory self_sufficiency cratered
- Healthy idle (Active=0) still required 1800s wake evidence

## Fixed
- `OVERSEER_IMPROVE_SKIP_RESTART_IF_ACTIVE_2026_09_04`
- `OVERSEER_HORIZON_SKIP_RESTART_2026_09_04` + `_append_improve_wake`
- `OVERSEER_HEALTHY_IDLE_WAKE_CREDIT_2026_09_04`
- beat-mac + restore-hub-protect vault pins
- factory 91%→99%; test-quick 185 OK

## Still broken / needs human
- Dirty Dispatch ~95%; commit WORKING when safe
