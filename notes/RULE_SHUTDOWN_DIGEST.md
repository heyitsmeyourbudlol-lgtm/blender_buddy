# Rule-change digest — human accept/reject only

_Updated 2026-09-08T03:04:08Z_ · safety_auditor / peer_rule_shutdown · Needle `OVERSEER_RULE_CHANGE_PROPOSE_ONLY_2026_09_06`

**Policy:** propose only — do **not** mute, delete, or auto-apply rules. Human accepts/rejects each row.

## Pending proposals

| Action | Rule / path | Rationale | Status |
|--------|-------------|-----------|--------|
| _(none)_ | — | No pending add/remove/modify/suspend | awaiting human |

## How to refresh

```bash
./scripts/peer rule-shutdown-digest
# or: python3 scripts/peer_rule_shutdown.py write-digest
# propose: python3 scripts/peer_rule_shutdown.py propose --action suspend --rule PATH --why "..."
```

## Closed this cycle

- Digest path present (standup no longer FileNotFound).
- Minimal `scripts/peer_rule_shutdown.py` scaffolded (propose-only; no mute).
- Lane D safety_auditor: pending add/remove/modify/suspend = 0; needle `OVERSEER_RULE_CHANGE_PROPOSE_ONLY_2026_09_06`.
