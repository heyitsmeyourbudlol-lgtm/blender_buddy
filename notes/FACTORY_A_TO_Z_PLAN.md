# Factory A→Z — unsupervised kit run (sequencing lock)

Needle: `OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07`  
Owner role: **`kit_a_to_z`**  
Tasks: [`FACTORY_A_TO_Z_TASKS.md`](FACTORY_A_TO_Z_TASKS.md) · SOP: [`SOP_FACTORY_A_TO_Z.md`](SOP_FACTORY_A_TO_Z.md)  
Wake: `./scripts/peer a-to-z` · `./scripts/peer kit-run --help`

## Why this exists

**SEQUENCING LOCK:** Do not jump to distribution, Newdrop polish theater, or Automations migration until the **current** factory capability can run **A→Z without human oversight**. Niches/commands are co-pilot only. Incomplete “full automation kit in factory” = stay here.

Supersedes Top10 “Newdrop-only Active” for kit work until this plan’s **green lock** is stamped.

## Definition of done (A→Z)

For **≥1** registry target (first: **CPT**), a single unsupervised compound must complete:

| Step | Meaning | Fail = stop (receipt, not babysit) |
|------|---------|-------------------------------------|
| **A** Adapt | `automation_adapt --heal --write` on target hub/Mac path | Non-zero adapt → blocked receipt |
| **B** Verify | Native `verify_commands` from `repos/registry.json` | Any fail → blocked receipt |
| **C** Isolate | Peer worktree / branch (dirty-main safe) | Cannot add worktree → blocked receipt |
| **D** Artifact | Irreversible: PR opened **or** merge note **or** explicit blocked receipt with reason | Soft “looks good” without URL/receipt ≠ done |
| **E** Writeback | Update `notes/EXTERNAL_PROOF.md` + `notes/FACTORY_A_TO_Z_PROOF.md` + registry notes | Missing writeback → incomplete |

**Green lock:** one full CPT pass exits 0 with eligible remote artifact (`pr` URL with origin ref **or** `merge_note` + push) — **not** `blocked_receipt` alone (`OVERSEER_FALSE_GREEN_LOCK_2026_09_07`), **zero mid-loop human prompts**. Then second target (Doc2Api or RAM). Only after green lock may ladder jump (Newdrop distribution / Automations migration).

## Implementation order

1. **Phase 0 — Gate + SoT** — plan/tasks/SOP live; Active queue owns A→Z; role dispatch wired.
2. **Phase 1 — Compound** — `factory_kit_run.py` + `./scripts/peer kit-run` dry-run + mechanical A→B.
3. **Phase 2 — CPT prove** — unsupervised A→E on CPT; stamp proof.
4. **Phase 3 — Second target** — Doc2Api or RAM same loop.
5. **Phase 4 — Green lock** — stamp `notes/FACTORY_A_TO_Z_PROOF.md` green; only then resume Newdrop Active policy.

## Non-goals

- Niche bank expansion / Command Builder theater
- Newdrop UI or distribution wedge until green lock
- Paid API / Stripe / credits (NO PAY)

## Status

**GREEN LOCK stamped 2026-09-08** — Phase 4 unlocked: CLEAN CPT A→E + [PR #2](https://github.com/heyitsmeyourbudlol-lgtm/CPT/pull/2) · origin `peer/kit-a-to-z-20260908T023609` @ `e60fddd` · `green_lock_eligible=pr`. Mac `gh` for PR; CLEAN HTTPS push via Mac-provisioned credential helper (prior `push_auth_missing` healed). SoT `notes/FACTORY_A_TO_Z_PROOF.md` Status=**green**. Ladder may advance; prefer kit-run for new registry targets.
