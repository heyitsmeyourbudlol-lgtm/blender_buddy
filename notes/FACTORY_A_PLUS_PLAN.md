# Factory A+ plan — full scorecard to excellence

_Updated 2026-09-02_ · canonical plan · tasks: [FACTORY_A_PLUS_TASKS.md](FACTORY_A_PLUS_TASKS.md)

**Goal:** Every factory dimension at **A+** with measurable exit criteria.

**Horizon:** 6–8 weeks focused execution (kit expansion frozen except blockers).

**North star:** adapt → native verify → worktree/PR → irreversible artifact on external OSS.

## Scorecard

| Dimension | A+ metric |
|-----------|-----------|
| Loop mechanics | dispatch ≥95%, noop=0 for 7d |
| Orchestration | 10 parallel cycles, zero merge collisions |
| Self-repair | 0 high/med bottlenecks 7d; digest matches live |
| Memory / cognition | ASI Phases 1–3 green; knowledge index injects |
| Autonomous operation | peer + improve up 7d; improve→peer closed loop |
| Factory outcomes | ≥3 registry repos `factory-proven`; external_proof mode ≥90% |
| Strategic positioning | product hours ≥60%; CROWN_EXIT dated Q1 2027 |

## Phases (dependency order)

```
Phase 0 Stabilize → Phase 1 Queue discipline → Phase 2 Orchestration
       ↓                    ↓
Phase 3 Memory ──────────→ Phase 4 External proof → Phase 5 Crown exit
```

**Do not start Phase 4 until Phase 0 exit criteria are green.**

## Phase 0 — Stabilize (Week 1)

1. Dual-daemon proof — Mac + hub both WORKING/IDLE
2. Close improve→peer closed loop (ASI Phase 4)
3. Break noop loop + tune wake intervals (45–90s)
4. Self-repair zero-defect steady state

## Phase 1 — Queue discipline (Week 2)

1. Demote theater; Active ≤12 executable items only
2. Freeze kit expansion until external proof lands

## Phase 2 — Orchestration (Week 3)

1. Prove 48-peer parallel dispatch — 10 cycles zero collisions
2. Dirty-tree production path via coding worktree

## Phase 3 — Memory & cognition (Week 4)

1. ASI Phases 1–3 runtime green (≥75% rubric)
2. Enable knowledge index on hub (notes + transcripts)
3. Mandatory plan-gate + done-gate in orchestrator flow

## Phase 4 — Factory outcomes (Weeks 5–7)

1. Switch `factory_meter_mode` to `external_proof`
2. External proof #1 — CPT or smallest adapted repo
3. External proof #2 — RAM
4. External proof #3 — Newdrop kit install + native verify

Track proofs in [EXTERNAL_PROOF.md](EXTERNAL_PROOF.md).

## Phase 5 — Strategic positioning (Week 8+)

1. [CROWN_EXIT.md](CROWN_EXIT.md) — dated Q1 2027 migration checklist
2. GitHub public + CONTRIBUTING (LAUNCH Phase 1)
3. ≥1 external kit install off-machine

## Weekly scoreboard

```bash
./scripts/peer factory-a-plus          # phase scoreboard
./scripts/peer bootstrap               # if STOPPED
python3 scripts/factory_progress.py
python3 scripts/asi_rubric.py
./scripts/peer self-heal-status
python3 scripts/peer_orchestrate.py --self-check
```

## What to stop

- New `peer_*` cognitive modules until external proof
- ASI/strategy essays in Active queue
- Hyper-poll wake intervals
- Improving `automation_improve.py` itself
