# Operating system — three structural pillars

How the Automation Hub institutionalizes learning and optimization (not one-off hero agents).

## 1. Data capture & debriefs

| Mechanism | Kit implementation |
|-----------|-------------------|
| **After-Action Reviews** | `scripts/peer_debrief.py --capture-cycle` — blameless AAR stubs after each peer cycle |
| **Post-mortems** | Auto-triggered on `verify_ok=false` — root cause = **process**, not people |
| **Blameless culture** | Templates in `peer_debrief.py`; prompts say "SOP/gate flaw" |
| **KPIs** | `scripts/factory_progress.py` — dispatch, delivery, external proof, queue quality · **throughput** (mass×speed: non-noop/h, rate, parallel busy, last cycle age) |

**Where to look:** `notes/DEBRIEF_LOG.md`, `~/.config/automation-hub/debrief-entries.jsonl`

```bash
./scripts/peer debrief --status
./scripts/peer debrief --capture-cycle
./scripts/peer debrief --preview   # Optimization Unit orchestrator prompt
```

## 2. Knowledge management systems

| Mechanism | Kit implementation |
|-----------|-------------------|
| **Centralized wiki** | `notes/DEBRIEF_LOG.md` — append-only debrief history |
| **Standard Operating Procedures** | `notes/SOP_INDEX.md` — links to canonical docs + owner niche |
| **Version control** | All SOPs live in git; debriefs propose diffs, peers land minimal changes |
| **Cross-department clearinghouse** | Daily **flaw scan** triage → Queue Steward syncs upgrades to WORK_QUEUE |

**Drift check:** `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` (must match).

## 3. Dedicated optimization units

| Unit | Kit implementation |
|------|-------------------|
| **Center of Excellence** | 8 niche agents + `notes/AGENT_ROLES.md` — specialized lenses |
| **Agile transformation office** | `automation_improve.py` forever loop — enqueue executable factory work |
| **Internal audit** | Daily flaw scan — 56 cross-reviews, 7 reviews per niche |
| **Six Sigma / defect elimination** | Verify Runner + factory blockers — quantify and drive structural fixes |

Optimization work is **isolated** from feature delivery:

- Normal queue → Factory Engineer niches
- Daily flaw scan → Scanner personas (scheduled)
- Debrief / KPI → Optimization Unit prompt (`peer debrief --preview`)

## Daily rhythm

```
09:00  Flaw scan (8 scanners × 7 reviews)     → peer_flaw_scan.py
       ↓ triage complete
       Debrief capture + queue sync             → peer_debrief.py
Peer loop cycles                               → AAR/post-mortem on noop/fail
Dashboard                                      → /progress (KPIs + throughput), /agents, /flaw-scan
```

## Implementation order

1. [x] KPI meter — `factory_progress.py`, `/progress`
1b. [x] Throughput (mass×speed) — `factory.throughput` + `/api/snapshot` · `/api/agents` · brain=CLEAN when mac-offloaded
2. [x] Cross-review audit — `peer_flaw_scan.py`, `/flaw-scan`
3. [x] Debrief + wiki — `peer_debrief.py`, `DEBRIEF_LOG.md`, `SOP_INDEX.md`
4. [x] Improve ↔ team bridge — `automation_team.py` (improve forever enqueues team gaps, prompts include roster)
5. [ ] Queue Steward: promote debrief upgrades to open WORK_QUEUE items each cycle
6. [ ] Auto-capture cycle debrief when `last_cycle` changes (peer_loop hook)

See `notes/AGENT_ROLES.md`, `notes/PEER_ORCHESTRATION.md`.
