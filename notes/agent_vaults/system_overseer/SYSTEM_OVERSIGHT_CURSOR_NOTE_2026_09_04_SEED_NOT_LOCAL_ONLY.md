# Overseer land — SEED_NOT_LOCAL_ONLY 2026-09-04

- **Root cause:** `_heal_seed_last_cycle` stamped `local_only=True` → oversight stagnation +14 even when factory healthy.
- **Fix needle:** `OVERSEER_SEED_NOT_LOCAL_ONLY_2026_09_04` in `peer_self_heal.py`, `peer_oversight_events.py`, `restore-hub-protect.sh`, `beat-mac-clobber.sh`.
- **Proof:** unit tests `test_heal_seed_not_local_only` + `test_self_heal_seeded_local_only_ignored` green; factory 95%; Active 0.
