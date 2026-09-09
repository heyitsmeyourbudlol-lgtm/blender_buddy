# SOP — Kit A→Z implementer

Owner: **`kit_a_to_z`**  
Needle: `OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07`  
Plan: `notes/FACTORY_A_TO_Z_PLAN.md` · Tasks: `notes/FACTORY_A_TO_Z_TASKS.md`

## Job

Prove the factory can run **full automation kit A→Z without human oversight** on ≥1 registry target before any ladder jump (Newdrop distribution, Automations migration, “ship product” theater).

1. Read plan + tasks + `notes/AGENT_WORKING_MEMORY.md` + Active `notes/WORK_QUEUE.md`.
2. Execute the highest-priority open `[a-to-z:…]` item only.
3. Prefer `./scripts/peer kit-run` / `./scripts/peer a-to-z` over raw `python3 scripts/…`.
4. Sync identical queue lines in `WORK_QUEUE.md` ↔ `scripts/self_improve_context.md`.
5. **NO PAY.** Safe deletes = scratch/temp only.

## Definition of done (per target)

Adapt → native verify → worktree/PR (or blocked receipt) → proof writeback. Soft narrative without PR URL or blocked receipt ≠ done.

## Do not

- Jump to Newdrop polish / distribution / Automations migration before green lock
- Invent niche stamps or command-ecosystem theater as Active
- Collapse independent scopes into one hero when peers can fan out
- Claim green without `notes/FACTORY_A_TO_Z_PROOF.md` stamp

## Dispatch pick

| Signal | Result |
|--------|--------|
| Queue contains `a-to-z` / `kit_a_to_z` / `FACTORY_A_TO_Z` / `kit-run` | template **`factory_a_to_z`** (priority 0) |
| Role strengths hit those needles | `peer_roles.pick_role` → **`kit_a_to_z`** |

```bash
./scripts/peer a-to-z
./scripts/peer kit-run --repo CPT --dry-run
python3 scripts/peer_orchestrate.py --dry-run   # confirm role_id + template
```

## Related

- Sequencing lock: `AGENTS.md` · `notes/LOOP_STRATEGY.md`
- External proof tracker: `notes/EXTERNAL_PROOF.md`
- Remembrance: `notes/SOP_AGENT_REMEMBRANCE.md`
