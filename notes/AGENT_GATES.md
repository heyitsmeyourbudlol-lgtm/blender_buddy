# Agent gates — executable countermeasures

_Updated 2026-09-07 09:53:09_ · mechanical checks for agent-vs-human gaps

## Commands

```bash
./scripts/peer plan-gate --role factory_engineer   # before first edit
./scripts/peer done-gate --role factory_engineer \
  --expected "exit 0" --actual "exit 0"            # before DONE
./scripts/peer pre-dispatch                        # includes plan-gate
./scripts/peer post-cycle                          # includes done-gate
```

## Plan gate (mechanical)

- Refresh TEAM_CONTEXT
- Queue drift scan
- Diagnose quick (block on critical/high)
- Worktree pool floor
- Secret pattern scan on staged files
- **Read-ack** — plan cites Always-read paths (`AGENT_WORKING_MEMORY`, `WORK_QUEUE`, `AGENTS.md`)
- **Librarian receipt** — when prefer_librarian, require fresh `fact-query` receipt **or** always-read ack (soft→hard)
- Print hallucination strategy + human gap + idea synthesis blocks

```bash
./scripts/peer fact-query "noop plan-gate"   # writes receipt
./scripts/peer plan-gate --role factory_engineer \
  --read-ack notes/AGENT_WORKING_MEMORY.md,notes/WORK_QUEUE.md,AGENTS.md
./scripts/peer domain-owners --write           # notes/DOMAIN_OWNERS.md
```

## Done gate (mechanical)

- Diagnose quick
- Queue drift
- Output compare when --expected/--actual provided
- Done self-check + learn-record reminders

_Gap matrix: notes/AGENT_VS_HUMAN.md_ · amnesia: `notes/AGENT_AMNESIA_RESEARCH.md` Scope B
