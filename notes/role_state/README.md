# Role state (thin)

JSON per role under this directory — assignment / blocked / files / verify_cmd.

```bash
./scripts/peer role-state list
./scripts/peer role-state set factory_engineer --assignment "…" --files a,b --verify-cmd "…"
./scripts/peer role-state block factory_engineer --reason "…"
```

Needle: `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07` · schema in `scripts/peer_role_state.py`
