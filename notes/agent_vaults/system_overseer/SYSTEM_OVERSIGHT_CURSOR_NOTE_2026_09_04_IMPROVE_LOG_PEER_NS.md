# Overseer land — IMPROVE_LOG_PEER_NS 2026-09-04

- **Needle:** `OVERSEER_IMPROVE_LOG_PEER_NS_2026_09_04` in `scripts/factory_progress.py`
- **Companion:** `OVERSEER_IMPROVE_HUB_ZLIB_FP_2026_09_04` in `scripts/automation_improve.py` (zlib write_prompts fp so poll-cache does not prefer peer-6 body)
- **Symptom:** factory 91% with "Improve loop not waking peer" while peer-6 log was fresh; hub log stale
- **Fix:** freshest improve log scans all `~/.config/*/improve-loop.log`; hub zlib needle keeps forever on automation-hub CONFIG_DIR
- **Verify:** unittest `test_improve_log_path_prefers_freshest_peer_ns`; test-quick 185 OK; factory 99%; bottlenecks 0
