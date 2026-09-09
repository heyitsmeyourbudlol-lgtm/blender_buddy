# Team development — what we have vs what was lacking

_Updated 2026-09-02 · self-sufficient build · command_builder focus_

## North star for the team

**Make the dream work:** every niche reads the **same** facts, shares the **same** cycle_id, and aligns on **one team focus** (verify gate, flaw scan, daemons, or normal execute) before touching code.

Not 48 solo heroes — one orchestra with job titles.

---

## What was already there (pillars)

| Pillar | Kit | Role |
|--------|-----|------|
| **Job titles** | `peer_tasks.json` → `agent_roles` | Strength-based assignment per queue line |
| **Orchestrator** | `peer_orchestrate.py` | Phase gates: Plan → Implement → Safety → Verify → Merge |
| **Improve ↔ peer bridge** | `automation_team.py` | `hand_out_worker_pool` each improve cycle |
| **Agent board** | `peer_agent_board.py` | Roster + phase + worktrees |
| **GLink comms** | `peer_agent_comms.py` | `bus.jsonl` + per-agent vaults (STAT/DONE/DIFF) |
| **Shared reads** | `TEAM_CONTEXT.md` | Factory, queue, playbook, research sync |
| **Research sync** | `peer_dual_research.py` | Efficiency + output lanes each cycle |
| **Flaw scan** | `peer_flaw_scan.py` | 8 niches cross-review |
| **Debrief / KPIs** | `peer_debrief.py`, `factory_progress.py` | AAR + self-sufficient meter |

---

## What was lacking (fixed this pass)

1. **No shared cycle_id** — improve hand_out and peer dispatch could diverge; agents could not tell if they were on the same wave.
   - **Fix:** `team-cycle.json` + `cycle_id` on every vault + GLink SYNC broadcast (`sync_team_cycle`).

2. **One-way context** — vaults got assignments but not coordinated **focus** when verify failed (every niche still chased feature work).
   - **Fix:** `detect_team_focus()` → verify_gate / flaw_scan / daemon_recovery / normal; OWNER vs SUPPORT rules in vault + niche prompts.

3. **Peer dispatch skipped team sync** — only improve loop wrote `TEAM_CONTEXT`; parallel niche launch did not refresh vaults.
   - **Fix:** `peer_parallel_dispatch` calls `sync_team_cycle` before launching agents.

4. **Duplicate vault writes** — hand_out updated tasks twice (plain then full).
   - **Fix:** single `sync_team_cycle` path sets todo + summary + cycle.

5. **Daemon status contradictions** — launchctl false-negatives showed DOWN while status json showed RUNNING.
   - **Fix:** `_daemon_status()` trusts `peer-loop-status.json` when launchctl disagrees.

6. **No team ops command** — no manual “force everyone onto same page.”
   - **Fix:** `./scripts/peer team-sync` rebuilds cycle from roster.

---

## How to operate the team (daily)

```bash
./scripts/peer team-sync      # force cycle_id + vaults + TEAM_CONTEXT
./scripts/peer team-context   # refresh digest only
./scripts/peer agents           # birds-eye roster + phase
./scripts/peer comms            # vault todo/done + last GLink
./scripts/peer comms-bus        # tail structured bus
```

**Agent rules (every niche):**

1. Read `notes/TEAM_CONTEXT.md` — includes **Team sync** + **Efficiency** at top.
2. Note **cycle_id** — cite in GLink DONE/DIFF payloads.
3. **Complete efficiency** — measurable outcome every cycle; minimal diff; `./scripts/peer` compounds.
4. If **verify_blocked** — SUPPORT niches do not open new feature scopes.
5. Post GLink when done — not English prose on the bus.

---

## Still to develop (honest gaps)

| Gap | Impact | Next step |
|-----|--------|-----------|
| **Complete efficiency not enforced post-cycle** | Agents can ignore mandate without hook penalty | Post-cycle check: cycle must cite outcome metric |
| **Agents rarely post DONE/DIFF back** | Bus is mostly orchestrator → niche; weak closed loop | Enforce in verify gate / post-cycle hook |
| **Serial DGX execution** | floor=8 but remote runs one niche at a time | RAM budget + hub cap tuning; or accept serial |
| **External-proof queue noise** | Theater items still in Active launch queue | Demote to Backlog in self_sufficient mode |
| **Flaw scan 0/N reviews** | Cross-review not completing | Dedicated flaw-scan dispatch when `should_dispatch` |
| **WORK_QUEUE ↔ context drift** | Two sources diverge | `./scripts/peer sync-queue` each cycle |

---

## Links

- Shared brain: `notes/TEAM_CONTEXT.md`
- Cycle state: `~/.config/automation-hub/team-cycle.json`
- Operating system: `notes/OPERATING_SYSTEM.md`
- Orchestration: `notes/PEER_ORCHESTRATION.md`
