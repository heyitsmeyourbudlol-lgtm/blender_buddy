# Factory A→Z tasks

Linked from [FACTORY_A_TO_Z_PLAN.md](FACTORY_A_TO_Z_PLAN.md). Sync open items to `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md`.

Needle: `OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07`

## Phase 0 — Gate + SoT

- [x] **[a-to-z:phase0] Land plan + SOP + role `kit_a_to_z` + Active queue** — landed 2026-09-07 `notes/FACTORY_A_TO_Z_PLAN.md` · `SOP_FACTORY_A_TO_Z.md` · peer template; Newdrop Active deferred under sequencing lock
- [x] **[a-to-z:phase0] Proof stub + status verb** — landed 2026-09-07 `notes/FACTORY_A_TO_Z_PROOF.md` + `./scripts/peer a-to-z`

## Phase 1 — Compound

- [x] **[a-to-z:phase1] `factory_kit_run` A→B mechanical** — landed 2026-09-07 dry-run A→C + receipt JSON; home mirrors via `Path.home()`/`AUTOMATION_MAC_HOME` (no `/Users/…`) Needle `OVERSEER_KIT_RUN_HOME_MIRRORS_2026_09_07`
- [x] **[a-to-z:phase1] Wire worktree step C** — landed Phase1 receipt (`C_worktree` dirty-main safe probe); full worktree add deferred to Phase 2 unsupervised path
- [x] **[a-to-z:phase1] Peer verb `kit-run` + compound smoke** — `./scripts/peer kit-run --repo CPT --dry-run`; unittest dry-run + home-mirror guard

## Phase 2 — CPT prove (first green)

- [x] **[a-to-z:phase2] CPT unsupervised A→E** — landed 2026-09-07 overseer: live `--run --stop-after E` · adapt `--target` · worktree `CPT-kit-a-to-z-20260907T161926` · D=blocked_receipt (`no_origin_remote`,`gh_cli_missing`) · E writeback · Needle `OVERSEER_KIT_RUN_AE_2026_09_07`
- [x] **[a-to-z:phase2] Stamp CPT row green or honest block** — stamped `notes/FACTORY_A_TO_Z_PROOF.md` + `EXTERNAL_PROOF` CPT row; lock stays **red** until Phase 4

## Phase 3 — Second target

- [x] **[a-to-z:phase3] Second registry target A→E** — landed 2026-09-07 CLEAN Doc2Api A→E (+ claimed PR; lock remains **red** until Phase 4 eligible artifact) · native pytest 9 · wt=`Doc2Api-kit-a-to-z-20260907T165929`

## Phase 4 — Green lock

- [ ] **[a-to-z:phase4] Stamp green lock** — blocked: push_auth_missing on CLEAN (no SSH/gh); false green healed OVERSEER_FALSE_GREEN_LOCK_2026_09_07; FACTORY_A_TO_Z_PROOF.md status=**red**
- [ ] **[a-to-z] Factory A→Z sequencing lock** — red until real PR/merge_note; blocked: push_auth_missing on CLEAN (no SSH/gh); do not jump ladder — OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07
