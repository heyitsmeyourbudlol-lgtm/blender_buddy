# Factory public standings — task breakdown

Canonical reassessment: [factory-public-standings.canvas.tsx](/Users/togi/.cursor/projects/Users-togi-Automation/canvases/factory-public-standings.canvas.tsx) · as-of **2026-09-07**.

Linked from `LAUNCH.md` Phase Standings and `notes/LOOP_STRATEGY.md`.

**Next track:** Top 10 indie production power — `notes/TOP10_PRODUCTION_POWER.md` · `LAUNCH.md` Phase Top10.

## Implementation order

1. **Restart daemons** — peer + improve forever; prove `./scripts/peer progress` loops alive (not 0 cycles/h).
2. **Queue hygiene** — demote niche-distill stamp theater from Active; keep factory-shaped unblockers only.
3. **External proof** — ≥1 irreversible artifact on a product repo (merged PR / public pin); update `notes/EXTERNAL_PROOF.md`.
4. **Cursor Automations migration sketch** — wake/dispatch → native Automations; keep WORK_QUEUE + verify as thin brain.
5. **Hub product gravity** — pick one user-facing product (Newdrop vs RAM vs other); write choice into `LAUNCH.md`.

## Done when

- [x] `./scripts/peer progress` credits CLEAN peer+improve when mac-offloaded (daemons live on CLEAN)
- [ ] Active queue ≤ factory-shaped standings items + ensure-pool (no stamp-N** theater flood)
- [x] EXTERNAL_PROOF has ≥1 non-pending row with PR/merge or pin — Newdrop PR #16 merged 2026-09-07
- [x] `notes/CURSOR_AUTOMATIONS_MIGRATION.md` exists and is linked from LOOP_STRATEGY
- [x] `LAUNCH.md` names the hub gravity product (Newdrop)

## Non-goals

- More niche-distill stamp runners as Active work
- Kit polish that does not unblock 1–5
- Competing with Devin/Cursor on LOC or ARR
