### 2026-09-04 08:49 — Repo Flaw Research Agent

**Found:**
- `scripts/peer_last_cycle_poison.py` + `scripts/peer_transcript.py` — `scrub_last_cycle_poison` pops `failure_type=deferred` while leaving `verify_ok=True`; after scrub `_should_spin_after_agent_cycle` returns True → agent re-dispatch spin (OVERSEER_SANITIZE_DEFERRED_VERIFY_OK clobbered by Mac sync).
- `scripts/peer_self_heal.py` — duplicate `_hub_protect_restore_paused` (second weaker def wins); ignores `~/.config/automation-hub/RESTORE_PAUSED` → live `paused=False` with flag present.
- `scripts/peer_repo_research.py` `build_digest` Agent-notes keep was bullet-only — `###` dated research blocks wiped every probe (test existed; impl missing). Re-landed OVERSEER_DIGEST_KEEP_HASH_NOTES this cycle.
- `automation.config.local.json` verify/quick omit `tests.test_peer_last_cycle_poison` — scrub regressions stay green on gate.
- Mechanical eval()/shell=True highs are **false** (comment/title echoes); live `probe_static_flaws()` = 0.

**Severity:** high (scrub→spin, RESTORE_PAUSED false-neg); medium (verify coverage)

**Fix:**
1. Sanitize: deferred ⇒ verify_ok=False (never pop ft under ok); add `tests.test_peer_last_cycle_poison` to verify/quick; `./scripts/peer test-quick`
2. Delete weaker duplicate `_hub_protect_restore_paused`; keep RESTORE_PAUSED+land_hold checks; unittest; `./scripts/peer test-quick`
