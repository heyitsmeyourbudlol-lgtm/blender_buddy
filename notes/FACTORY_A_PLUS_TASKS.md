# Factory A+ tasks — implementation checklist

Linked from [FACTORY_A_PLUS_PLAN.md](FACTORY_A_PLUS_PLAN.md). Sync open items to `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md`.

## Phase 0 — Stabilize

- [ ] **[factory-a-plus:phase0] Dual-daemon proof — Mac + hub WORKING/IDLE 7d** — `./scripts/peer bootstrap`; confirm peer + improve LaunchAgents on Mac and hub; document topology in TEAM_CONTEXT
- [ ] **[factory-a-plus:phase0] Close improve→peer closed loop** — 3 cycles: improve touches peer-turn.signal + peer executes enqueued item + verify ok; ASI Phase 4 criteria green
- [ ] **[factory-a-plus:phase0] Break noop loop + tune wake intervals** — fingerprint advances after ok cycles; `continuous_wake_sec` 45–90 when queue ≤12
- [ ] **[factory-a-plus:phase0] Self-repair zero-defect 7d** — 0 high/med bottlenecks; digest matches `peer_loop.py --status`; remove shadow `test_autonomous_repair` dupes

## Phase 1 — Queue discipline

- [ ] **[factory-a-plus:phase1] Demote theater — Active ≤12 executable only** — `./scripts/peer factory-a-plus --demote-theater`; no crown/ASI/meta-exit in Active
- [ ] **[factory-a-plus:phase1] Freeze kit expansion until external proof** — no new `peer_*` modules; track kit LOC in DEBRIEF_LOG weekly

## Phase 2 — Orchestration

- [x] **[factory-a-plus:phase2] Prove parallel dispatch 10 cycles zero collisions** — landed 2026-09-07 Needle `OVERSEER_PARALLEL_SCOPE_OVERLAP_REJECT_2026_09_07` — `peer_parallel_dispatch.filter_disjoint_assignments` + unique cwd; unittest 10-cycle prove + scope overlap rejection; hub_cap=46
- [ ] **[factory-a-plus:phase2] Dirty-tree coding worktree path** — dispatch clear ≥95% with dirty main; document in AUTOMATION.md

## Phase 3 — Memory & cognition

- [ ] **[factory-a-plus:phase3] ASI Phases 1–3 runtime green** — `asi_rubric` ≥75%; all phase criteria green 7d
- [ ] **[factory-a-plus:phase3] Enable knowledge index on hub** — `knowledge_index.enabled` true on DGX; sources notes+transcripts; inject ≤6000 chars
- [ ] **[factory-a-plus:phase3] Mandatory agent gates in orchestrator** — plan-gate before edit; done-gate before DONE; wired in peer_orchestrate prompt

## Phase 4 — Factory outcomes

- [ ] **[factory-a-plus:phase4] Switch factory_meter_mode to external_proof** — flip config when Phase 0–1 green; deferred markers become scored blockers
- [ ] **[factory-a-plus:phase4] External proof #1 — CPT or smallest adapted repo** — adapt + native verify + PR; record in EXTERNAL_PROOF.md
- [ ] **[factory-a-plus:phase4] External proof #2 — RAM** — merged reclaim/footprint diff on external repo
- [ ] **[factory-a-plus:phase4] External proof #3 — Newdrop kit install** — registry `factory-proven`; native verify green

## Phase 5 — Strategic positioning

- [ ] **[factory-a-plus:phase5] Crown exit plan dated Q1 2027** — notes/CROWN_EXIT.md complete with keep/kill/migrate rows
- [ ] **[factory-a-plus:phase5] GitHub public + CONTRIBUTING** — LAUNCH Phase 1; LICENSE + CONTRIBUTING
- [ ] **[factory-a-plus:phase5] External kit install proof** — ≥1 off-machine install logged
