### 2026-09-04 Repo Flaw Research Agent

**Found:**
- `scripts/peer_transcript.py` `load_state()` — on `TimeoutError` returns `{}`; `peer_loop` / `peer_stall_pivot.note_stall` then `save_state` writes stall-only JSON and wipes `last_cycle` / `cycle_history`. Live witness: hub `~/.config/automation-hub/peer-loop-state.json` briefly held only `stall_reason=noop_backoff` + `stall_since_ts` while `~/.config/automation/peer-loop-state.json` still had full `last_cycle`.
- `scripts/peer_self_heal.py` `_heal_seed_last_cycle` — seeds with `local_only=True`; `peer_oversight_events` then scores +14 ("last cycle was local-only") → cursor-agent thrash after every missing_last_cycle heal.
- `automation.config.json` `quick_test_command` omits `tests.test_peer_self_heal` (present in `verify_commands`) — heal/seed regressions invisible to `./scripts/peer test-quick`.
- Mechanical digest eval()/shell=True hits are catalog/comment echoes (`peer_repo_research` / `_mark_flaw_research_landed` / pen-test skip strings) — not live sinks; live probe open=0 static.

**Severity:** high (state clobber + seed local_only); medium (quick omit self_heal)

**Fix:**
1. `save_state` / stall writers: refuse to persist when loaded state was empty on lock timeout — re-load under lock and merge stall keys only; unittest inject TimeoutError → assert `last_cycle` survives; `./scripts/peer test-quick`
2. `_heal_seed_last_cycle`: pass `local_only=False` (seed is mechanical delivery, not prompt refresh); unittest; `./scripts/peer test-quick`
3. Add `tests.test_peer_self_heal` to `quick_test_command` (+ local overlay); `./scripts/peer test-quick`

