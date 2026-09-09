# SOP — TOP10_NEXT durable implementer

Owner: **`top10_implementer`**  
Needle: `OVERSEER_TOP10_NEXT_2026_09_07`  
Canonical list: `notes/TOP10_NEXT.md`

## Job

Maintain and **implement** the ranked top 10 next things — nothing else.

1. Read `notes/TOP10_NEXT.md` + `notes/AGENT_WORKING_MEMORY.md` + Active `notes/WORK_QUEUE.md`.
2. Implement the highest-rank item with `status: open` only.
3. Mark done → `./scripts/peer top10-refresh` → re-rank.
4. Sync identical queue lines in `WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` when enqueue/close.
5. **NO PAY.** Safe deletes = scratch/temp only.

## Do not

- Invent work outside `TOP10_NEXT.md`
- Steal Newdrop production Active (`TOP10_PRODUCTION_POWER`) unless an item explicitly says so
- Delete live SoT because a memory pack exists
- Collapse independent scopes into one hero agent when peers can fan out

## Dispatch pick

| Signal | Result |
|--------|--------|
| Queue contains `TOP10_NEXT` / `top10_next` / `top10_implementer` | `match_rules` → template **`top10_next`** (priority 0) |
| Role strengths hit those needles | `peer_roles.pick_role` → **`top10_implementer`** |
| Bare `[top10]` Newdrop lines (no `TOP10_NEXT`) | stay on **`production_power_newdrop`** |

```bash
./scripts/peer top10
./scripts/peer top10-next         # highest-rank open only
./scripts/peer top10-refresh      # after a land — do not run to “promote” while T10-04 still GAP
./scripts/peer production-power   # restamp non-noop bar
python3 scripts/peer_orchestrate.py --dry-run   # confirm role_id + template
```

## Related

- Amnesia seeds: `notes/AGENT_AMNESIA_RESEARCH.md`
- Remembrance: `notes/SOP_AGENT_REMEMBRANCE.md`
- Newdrop production (separate): `notes/TOP10_PRODUCTION_POWER.md`
