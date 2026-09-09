# Automation rules — event → action engine

**Goal:** Cursor Automations-style declarative rules on top of the existing peer kit — trigger at an event, yield one or more actions. No second orchestrator.

**Status:** Active (2026-09-01)

---

## Model

```
Event source → automation_engine.emit(event, payload)
                    ↓ match automation.rules.json
                    ↓ yield actions (wake, enqueue, hook, debrief, …)
```

Events are **thin signals**. Actions call existing kit primitives (`wake_peer`, WORK_QUEUE enqueue, `post_cycle_hook`, GLink, verify, adapt heal).

---

## Rule file

- Repo default: `automation.rules.json`
- Local overlay: `~/.config/automation-hub/automation.rules.local.json`
- Config: `automation_engine.enabled`, `automation_engine.webhook_token`

### Example rule

```json
{
  "id": "ci-green-wake",
  "enabled": true,
  "on": "webhook.ci",
  "when": { "status": "success", "branch": "main" },
  "cooldown_sec": 60,
  "actions": [
    { "type": "wake_peer" },
    { "type": "enqueue", "prefix": "auto", "title": "Review CI green", "detail": "Main passed — advance queue" }
  ]
}
```

### Built-in events

| Event | When emitted |
|-------|----------------|
| `peer.cycle.end` | After each peer cycle records `last_cycle` |
| `peer.verify.ok` | Verify gate passed |
| `peer.verify.fail` | Verify gate failed |
| `improve.cycle.end` | Improve loop finished enqueue pass |
| `webhook.received` | `POST /api/events` (generic) |
| `webhook.ci` | CI webhook payload |

### Action types

| Type | Effect |
|------|--------|
| `wake_peer` | Touch `peer-turn.signal` |
| `enqueue` | Append WORK_QUEUE + context (synced) |
| `post_cycle_hook` | Run `post_cycle_hook` from config |
| `hook` | Run arbitrary shell command |
| `log` | Audit log entry |
| `debrief` | Append to DEBRIEF_LOG |
| `glink_post` | Post to GLink bus |
| `run_verify` | Run verify gate |
| `adapt_heal` | `automation_adapt --heal --write --quick` |

---

## Commands

```bash
./scripts/peer automations --list
./scripts/peer automations --emit peer.verify.fail --payload '{"verify_ok":false}'
curl -X POST http://127.0.0.1:8765/api/events \
  -H 'Content-Type: application/json' \
  -d '{"event":"webhook.ci","payload":{"status":"success","branch":"main"}}'
```

Set `AUTOMATION_WEBHOOK_TOKEN` to require auth on `/api/events`.

---

## Cursor Automations bridge

Native Cursor Automations (schedule, git, Slack, webhooks) remain the long-term UI per `notes/LOOP_STRATEGY.md`. This engine is the **portable kit layer** that works today on Mac + DGX — same semantics, file-based rules, hooks into peer/improve/verify.

When Cursor SDK parity lands, add a thin adapter: Cursor trigger → `automation_engine.emit(...)`.

See also: [AUTOMATION.md](AUTOMATION.md) · [LOOP_STRATEGY.md](LOOP_STRATEGY.md)
