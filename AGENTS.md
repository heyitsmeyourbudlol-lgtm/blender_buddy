# Agent preferences

**TIME BOMB (early–mid 2027):** Custom orchestration crown expires when Cursor-native loops become top 5–15% norm. Prefer **shipping products + distribution** over kit polish. Read `notes/LOOP_STRATEGY.md`.

**Investment thesis:** this kit is **capex** for an OSS-monster factory — adapt → native verify → worktree/PR → irreversible artifact on top-tier open source. `automation_improve` must enqueue executable factory work only (not ASI/strategy theater).

**Full strategy (stress all of it — not just the deadline):**
- Ladder: intelligence → speed → distribution → ecosystem (hub with gravity; 10 apps ≠ ecosystem)
- Keep after commoditization: queue semantics, verify gates, product constraints — not the daemon
- Meta-skill: **exit each loop** when it becomes table stakes; migrate the brain, murder the boilerplate
- Moat: users + shared primitives + habits + willingness to kill the kit

**Peer orchestration:** Read `notes/AUTOMATION.md` and `notes/PEER_ORCHESTRATION.md` before multi-file changes.
**Survival:** Read `notes/AGENT_SURVIVAL.md` — hazard map for stalls, chicken-eggs, false labels (plan-gate, adapt_stale, queue junk, namespace flip). Playbook: `notes/AGENT_ERROR_PLAYBOOK.md`.
**Never solo:** maximize parallel Task peers when scopes allow — prefer launching the full implementation peer set in ONE message; never collapse independent scopes into one hero agent.

```bash
./scripts/peer bootstrap                    # cold start: daemons + heal + verify + digest
./scripts/peer heal-all                     # mechanical heal + compact + verify gate
./scripts/peer pre-dispatch                 # before cursor-agent (compact + check + pool)
./scripts/peer commands-list --pivotal      # all pivotal agent commands → notes/AGENT_COMMANDS.md
python3 scripts/peer_orchestrate.py --self-check
python3 scripts/automation_adapt.py --heal --write   # adapt kit to this repo
python3 scripts/automation_adapt.py --audit          # self-audit script + outputs
python3 scripts/automation_improve.py --write --research  # plan + industry trends
python3 scripts/automation_research.py --refresh --write # update notes/AUTOMATION_TRENDS.md
python3 scripts/peer_orchestrate.py --dry-run
python3 scripts/cursor_self_improve.py --peer
python3 scripts/peer_loop.py --forever --background
./scripts/peer-loop-run
```

**Working memory:** `notes/README.md` · queue: `notes/WORK_QUEUE.md` (sync with `scripts/self_improve_context.md`) · errors: `notes/AGENT_ERROR_PLAYBOOK.md` (`./scripts/peer playbook-lookup "<error>"`)

**Config:** Edit `automation.config.json` for project name, test command, optional RSS budget, post-cycle hook.
