# Crown exit — migrate brain, murder boilerplate

_Draft 2026-09-02_ · target: **Q1 2027** when Cursor-native loops reach top 5–15% parity

See [LOOP_STRATEGY.md](LOOP_STRATEGY.md) for full strategy frame.

## Keep (migrate to native Cursor)

| Primitive | Native equivalent (when ready) | Migration trigger |
|-----------|-------------------------------|-------------------|
| Queue semantics | WORK_QUEUE + rules | Native queue or project tasks |
| Verify gates | `--self-check` + unittest | CI / native verify hooks |
| Product “done” definition | SAFETY_GATES + output-compare | Agent rules + skills |
| WORK_QUEUE ↔ context sync | plan-to-peer-tasks rule | Native plan decomposition |
| last_cycle retrospect | peer-loop-state.json | Native session memory |

## Kill (when native ~80% parity)

| Component | Kill when |
|-----------|-----------|
| kqueue daemon + peer-turn.signal | Cursor `/loop` or Automations stable |
| `peer_loop.py` LaunchAgent | Cloud Agents or native forever loop |
| Custom orchestrate merge | Native parallel Task / subagents default |
| prompt plumbing in cursor_self_improve | Native agent orchestration |

## Checklist (complete by Q1 2027)

- [ ] Map each Keep row to shipped Cursor feature
- [ ] Run factory on native loop for 7d without custom daemon
- [ ] Export queue + verify recipes as portable skill/rule bundle
- [ ] Archive peer_loop daemon; retain scripts as library only
- [ ] Product revenue/users metric exceeds kit maintenance hours

**A+ exit:** dated checklist with owner and native feature mapping per row.
