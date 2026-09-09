# Memory span — 100x effective context

_Updated 2026-09-08 16:16:24_ · tiered external memory for every agent

**Memory span (100x)** — you have ~128k tokens; the kit has terabytes.

Never rely on chat history alone. **Open files → retrieve → act:**

| Tier | Budget | Source | Rule |
|------|--------|--------|------|
| **Hot** | ~3.5k | Always-read paths + last_cycle + journal pins | Open listed files first every cycle |
| **Warm** | ~12k | learnings, vault, GLink, team slice | Role-scoped; don't re-discover |
| **Cold** | ~45k | knowledge_index FTS + hybrid | Query before reading whole files |

**Effective recall ≈ 100×** conversation tail when all tiers are used.

## Tier budgets

- Hot: 3500 chars
- Warm: 12000 chars
- Cold: 45000 chars
- **Total:** ~60k chars/cycle

## Habits

1. Do not rely on chat memory — open Always-read paths every turn (Hot block lists them)
2. After non-obvious work: `./scripts/peer memory-record --role ROLE --text "file:line fact"`
3. Before Plan: read Hot tier + Active WQ; run `./scripts/peer memory-recall --query "..."` if gap
4. Before reading a whole module: Cold tier should already cite the needle — grep index first
5. Do not repeat last_cycle facts — they are in Hot tier on purpose
6. Promote repeated journal facts to PROJECT_LEARNING via learn-record when team-wide

## Always-read paths (Hot inject every cycle)

Chat memory is not SoT. Open these before acting:

- `notes/AGENT_WORKING_MEMORY.md`
- `notes/REPO_DOMAIN_SMES.md`
- `notes/DOMAIN_OWNERS.md`
- `notes/MEMORY_SPAN.md`
- `notes/WORK_QUEUE.md`
- `scripts/self_improve_context.md`
- `notes/PEER_CONVERSATION.md`
- `AGENTS.md`

- Sticky: `NO PAY: free desktop/local/CLEAN only — never paid API/Stripe/credits`

## Commands

```bash
./scripts/peer memory              # refresh this doc
./scripts/peer memory-pack --role factory_engineer --task "..."
./scripts/peer memory-record --role ROLE --text "path:line fact"
./scripts/peer memory-recall --role ROLE --query "peer_loop wake"
./scripts/peer knowledge-search "query"   # cold tier source
```
