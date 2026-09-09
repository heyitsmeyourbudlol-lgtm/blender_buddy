# Cursor overseer note — 2026-09-04 SAVE_PRESERVE clobber

_Stagnation dispatch. Durable copy — SYSTEM_OVERSIGHT.md is mechanically rewritten._

## Found
- Critical `tests: FAIL (failures=1)` = `test_save_state_preserves_last_cycle_on_thin_save`
- Live `scripts/peer_transcript.py` kept `OVERSEER_STATE_SAVE_PRESERVE_*` but lost `_merge_preserve_cycle_memory` + public needle `OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04`
- Hub-protect `live_bad` / beat OR-needles treated partial file as healthy → never restored
- Canonical land-hold is `~/.config/automation-hub/OVERSEER_LAND_HOLD` (repo-root twin ignored)
- `hub-protect-restore.path` re-fired mid-land

## Fixed
- Relanded `_merge_preserve_cycle_memory` + SAVE/STATE needles in `peer_transcript.py`
- Tightened `restore-hub-protect.sh` live_bad/vault_ok to require SAVE + `def _merge_preserve_cycle_memory`
- Pinned hub-protect + notes `.real` vaults + EXPECTED md5; refreshed `mac-clobber-protect` hold
- test-quick **185 OK**; poison suite **10 OK**; heal-all bottlenecks **0**; Active open **0**
- Factory **94–95%**; delivery evidence cites `OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04 land`

## Still broken / needs human
- Dirty tree caps Dispatch ~85%
- Mac→DGX rsync can still rewrite unprotected scripts within seconds
- Commit WORKING scripts when safe; exclude hub-protect vault paths from Mac sender rsync
