# Improve horizon — major changes coming

_Updated 2026-09-08 16:22:07_ · cycle 1515 · rewritten each improve forever tick

## Current build — self-sufficient automation

**Target:** Self-sufficient automation: peer + improve forever, mechanical heal, verify gates, oversight — runs without babysitting

Improve forever enqueues **executable kit work** only (peer loop, verify, self-heal, oversight, queue hygiene). External OSS proof is deferred until the self-sufficient meter is green.

## Secondary meter — harness rubric (not the mission)

**Progress (phased rubric):** `100%`  `████████████████████`  **not the investment goal**

_100% phased rubric complete — phase 5 (general autonomy) remains asymptotic; true ASI not possessed yet_

_Legacy ASI destination (board only): 100% true Artificial Super Intelligence (ASI) — generalization, autonomy, and orchestration beyond any system achievable by today's standards_

## Live

| Signal | Value |
|--------|-------|
| Git | git: 21 changed path(s) (21 modified, 0 untracked) (cached) |
| Tests | tests: skipped (automation guard) |
| Queue | launch · 1 open |
| Adapt audit | ok |
| Drift warnings | 0 |
| Harness rubric | 100% (secondary) |
| Active phase | `general_autonomy` |

## Phased rubric (secondary)

Complete one phase, then plan the next. `pct = (completed phases + active phase partial) / 4 × 100` — phase 5 (general autonomy) is asymptotic. See `notes/ASI_RUBRIC.md`. Prefer factory opportunities in NOW/NEXT over chasing this meter.

**Next plan:** Plan next general-autonomy capability after phases 1–4 are green. Execute via work kit only (peer_loop, verify, orchestrate, worktrees, tasks) — do not edit automation_improve / horizon / ASI chrome.

### ✓ Phase 1 — Grounded loop (complete, 100%)

_Daemons run and peer cycles leave footprints in state and logs._

- [x] **Improve forever running** — improve daemon running=True
- [x] **Peer loop running** — peer daemon running (com.togi.automation-hub-peer-loop)
- [x] **Cycle memory** — last_cycle present (failure_type, git_head, local_only, noop, note, queue_fp…)
- [x] **Peer activity** — last_cycle age=26s — peer loop active

### ✓ Phase 2 — Verify & memory (complete, 100%)

_Post-agent verify passes; harness remembers the last cycle._

- [x] **Last verify passed** — last_cycle.verify_ok=True
- [x] **Self-healing verify** — verify retry gate wired
- [x] **Harness memory** — harness memory + last_cycle

### ✓ Phase 3 — Parallel orchestration (complete, 100%)

_Multiple agents work disjoint scopes without stalling the queue._

- [x] **Worktree isolation** — peer_loop uses peer_worktree
- [x] **Parallel peer prompts** — maximize parallel peers in orchestrate prompts
- [x] **Queue advances** — last cycle advanced queue (noop=false or unset after work)

### ✓ Phase 4 — Autonomous improve → work (complete, 100%)

_Improve forever heals, enqueues kit work, and wakes peer without human steering._

- [x] **Improve drives work kit** — improve heal + enqueue implemented
- [x] **Improve cycling** — improve-loop.log age=0s; 'drive work kit'=True
- [x] **Peer woken** — improve-loop.log age=0s; 'wake peer'=True

### → Phase 5 — General autonomy (asymptotic) (active, 67%)

_Coordinator routing, MCP, end-to-end autonomy — demanding of time; never fully possessed._

- [ ] **Coordinator routing** — coordinator routing: partial
- [ ] **MCP tool layer** — MCP layer: partial
- [x] **End-to-end delivery** — verify=1.0 log=1.0 advance=1.0

_raw=1.000 → 100%_

## NOW — prove self-sufficiency

_Daemons, improve→peer loop, verify, self-heal, noop break — no external OSS required_

1. **[smooth]** Unblock dirty tree for peer_loop dispatch
   - git: 21 changed path(s) (21 modified, 0 untracked) (cached) — continue_on_dirty keeps coding (worktree isolate or dirty-main fallback). Still commit/stash WIP when safe.
   - priority `4`

## NEXT — harden autonomy

_Oversight events, playbook, pre-dispatch, queue hygiene, flaw scan_

_None this cycle._

## OVER THE HORIZON — deferred

_External OSS proof + registry monster sprints — after self-sufficient meter is green_

1. **[ease]** [trend] MCP / tool protocol layer
   - Self-check tip when MCP namespaces error; document peer + MCP workflow.
   - priority `45`

## 100% ASI — secondary destination (not the mission)

_Harness meter only — current build targets self-sufficient automation_

1. **[asi]** [ASI 100%] True artificial superintelligence
   - 100% true Artificial Super Intelligence (ASI) — generalization, autonomy, and orchestration beyond any system achievable by today's standards. Secondary meter only — investment north star is the OSS monster factory: Robust outcome machine: adapt → native verify → worktree/PR isolation → irreversible artifact on top-tier open source — repeatedly, without babysitting.
   - priority `99`

## Industry map

Curated **8** · gaps **0** · partial **2**

- **[PARTIAL]** Coordinator-first specialist routing: Optional coordinator pass before template_match for ambiguous queue items.
- **[PARTIAL]** MCP / tool protocol layer: Self-check tip when MCP namespaces error; document peer + MCP workflow.

Full sources: `notes/AUTOMATION_TRENDS.md`

## Queue peek

- **[top10] Newdrop tip-cover Soft Soft #37 seat-cap-concurrency** — next meaningful non-UI Soft Soft residual (Seat-cap concurrency Soft Soft tip stamp for tip Soft Soft `invite_team_editor` RPC Soft Soft-ship; Debt/ops); file-scoped `/home/arnavrastogi/CaaS` (CLEAN mirror); verify soft vitest + `check:controls`; **no UI unless flaw**; prefer backend/security/ops; Soft Soft-land OK; PR when CLEAN git auth · NO PAY · Tasks: `notes/TOP10_PRODUCTION_POWER_TASKS.md`

## Automation team (improve ↔ peer orchestration)

Improve forever **must** drive this setup — not kit polish in isolation.

| Pillar | Kit | Status |
|--------|-----|--------|
| 8 niches | `notes/AGENT_ROLES.md`, `peer_tasks.json` | 50/8 roles |
| Agent board | `/agents`, `peer_agent_board.py` | phase `WORKING` |
| GLink comms | `peer_agent_comms.py`, `/api/comms` | shared bus + per-agent vaults |
| Flaw scan | `peer_flaw_scan.py`, `/flaw-scan` | `complete` · reviews 56/56 |
| Debriefs / KPIs | `peer_debrief.py`, `/progress` | factory None% · 2460 debrief(s) |
| Operating system | `notes/OPERATING_SYSTEM.md` | SOP index + DEBRIEF_LOG |

**Peer dispatch rules for improve cycles:**

1. **Every improve cycle** calls `hand_out_worker_pool` — all 8 niches get assignments on the board + GLink.
2. Launch **8 Task peers** — one niche each (`parallel_peer_floor`).
3. Respect daily **flaw scan** when `should_dispatch` (priority over normal queue).
4. **Queue Steward** syncs debrief + flaw-scan upgrades → WORK_QUEUE.
5. **Optimization Unit** (`./scripts/peer debrief --preview`) after flaw round or verify fail.
6. Never solo — orchestrate parallel peers in ONE message.

```bash
./scripts/peer agents          # birds-eye
./scripts/peer flaw-scan --status
./scripts/peer debrief --status
./scripts/peer progress
./scripts/peer ensure-pool
```


## Where to dig

- Combined prompt: `/home/arnavrastogi/.config/automation-hub/automation-improve.md`
- Plan only: `/home/arnavrastogi/.config/automation-hub/automation-improve-plan.md`
- Execute: `/home/arnavrastogi/.config/automation-hub/automation-improve-execute.md`
- Loop log: `/home/arnavrastogi/.config/automation-hub/improve-loop.log`

```bash
./scripts/peer improve-status   # horizon + daemon
./scripts/peer improve-watch    # live refresh of this board
```

