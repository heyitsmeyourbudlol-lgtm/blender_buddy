# ASI phased rubric

Measure progress toward true ASI in **stages**. Complete one phase, then plan the next. The old flat “code exists” probes inflated the meter; this rubric favors **runtime delivery**.

**North star:** 100% true ASI — generalization, autonomy, and orchestration beyond today's standards. Never check ASI off.

## Scoring

```
pct = (completed phases + active phase partial) / 4 × 100
```

- Phases **1–4** are completable (each criterion must score 1.0).
- Phase **5** is **asymptotic** — coordinator routing, MCP, end-to-end autonomy. It drives planning but never fully completes.
- When a phase completes, improve enqueues a **plan** for the active phase into `WORK_QUEUE.md`.

Implementation: `scripts/asi_rubric.py` · consumed by `scripts/automation_improve.py` · dashboard `/asi`.

## Phases

### Phase 1 — Grounded loop

Daemons run and peer cycles leave footprints in state and logs.

| Criterion | Pass when |
|-----------|-----------|
| Improve forever running | Improve LaunchAgent alive |
| Peer loop running | Peer LaunchAgent alive |
| Cycle memory | `peer-loop-state.json` has `last_cycle` |
| Peer activity | `peer-loop.log` touched in last hour |

**Plan when active:** Stabilize peer + improve daemons; record `last_cycle` after every agent run.

### Phase 2 — Verify & memory

Post-agent verify passes; harness remembers the last cycle.

| Criterion | Pass when |
|-----------|-----------|
| Last verify passed | `last_cycle.verify_ok` is True |
| Self-healing verify | Retry-once gate in peer_loop + run_peer_tasks |
| Harness memory | Transcript injects last_cycle |

**Plan when active:** Fix verify gate failures; persist last_cycle + inject retrospect into next peer prompt.

### Phase 3 — Parallel orchestration

Multiple agents work disjoint scopes without stalling the queue.

| Criterion | Pass when |
|-----------|-----------|
| Worktree isolation | `peer_loop` uses `peer_worktree` |
| Parallel peer prompts | `peer_orchestrate` maximizes Task peers |
| Queue advances | Last cycle not a noop fingerprint |

**Plan when active:** Integrate worktrees; maximize parallel Task peers per cycle; break noop loops.

### Phase 4 — Autonomous improve → work

Improve forever heals, enqueues kit work, and wakes peer without human steering.

| Criterion | Pass when |
|-----------|-----------|
| Improve drives work kit | `apply_mechanical` + `enqueue_work_opportunities` |
| Improve cycling | `improve-loop.log` shows drive/heal |
| Peer woken | Improve touches `peer-turn.signal` |

**Plan when active:** Close improve→enqueue→peer dispatch loop; prove queue items land from improve cycles.

### Phase 5 — General autonomy (asymptotic)

Coordinator routing, MCP, end-to-end autonomy — demanding of time; never fully possessed.

| Criterion | Signal |
|-----------|--------|
| Coordinator routing | `AUTOMATION_TRENDS` kit_status |
| MCP tool layer | trend kit_status |
| End-to-end delivery | verify + log + queue advance composite |

**Plan when active:** Plan next general-autonomy capability after phases 1–4 are green.

## Workflow

1. Improve cycle runs `compute_asi_rubric(signals)`.
2. Horizon + dashboard show phase ladder and active criteria.
3. **Before** rewriting horizon JSON, improve remembers the previous `current_phase_id`.
4. `enqueue_phase_plan`:
   - **Active (no advance):** enqueue “Plan active phase” for the current section (deduped by phase id).
   - **Phase MET → advance:** enqueue `Phase N complete → plan next` for the newly active section so autonomy continues without human steering.
5. Peer loop executes those work-kit queue items; criteria re-probe on the next cycle.

Do not stop at “phase complete.” Completing a section always unlocks planning the next bit.

True ASI is not met until phase 5 trends are green **and** phases 1–4 stay green at runtime — and even then, possession is asymptotic.
