# Team context — shared by all agents

_Updated 2026-09-08 16:16:23_ · read before Plan/Implement — includes low-importance facts that can change output

## Learning

## Project learning (cumulative — read every cycle)

**Learn as you work** — cumulative inside-out mastery (every cycle):

1. **Read before Plan** — `notes/PROJECT_LEARNING.md` + your niche notes in vault; never re-discover documented facts.
2. **Trace before edit** — follow imports/callers in your scope until you can explain the data flow in one paragraph.
3. **Record after work** — append ONE dated learning (non-obvious insight, trap, or file map) via `./scripts/peer learn-record`.
4. **Improve the kit** — mistake patterns → `notes/AGENT_ERROR_PLAYBOOK.md`; process wins → `notes/DEBRIEF_LOG.md` or SOP.
5. **Deepen over time** — each cycle you should know more of the repo than last cycle; teach the team in shared learnings.

**Inside-out map** — learn these paths over time (trace imports, read on demand):
- `scripts/peer_loop.py` ✓ — Forever driver — dispatch, verify gate, noop, worktrees
- `scripts/peer_orchestrate.py` ✓ — Orchestrator plan — phase gates, Task peer tasks
- `scripts/automation_improve.py` ✓ — Improve forever — horizon, enqueue, hand_out
- `scripts/automation_team.py` ✓ — Improve ↔ peer bridge — worker pool, team gaps
- `scripts/peer_team_context.py` ✓ — Shared brain — TEAM_CONTEXT, team-sync, cycle_id
- `scripts/peer_persona_rules.py` ✓ — Hardwired MUST/MUST NOT per niche
- `scripts/peer_agent_comms.py` ✓ — GLink bus + vaults + per-agent notes.jsonl
- `scripts/peer_critical_thinking.py` ✓ — Intelligence layer — evidence, root cause, Plan/Act gates
- `notes/CRITICAL_THINKING.md` ✓ — Critical thinking canon — read before Plan
- `scripts/peer_hallucination_guard.py` ✓ — Hallucination guard — self-aware strategy to defy drift
- `notes/HALLUCINATION_GUARD.md` ✓ — Assume hallucination soon — strategize before edit
- `scripts/peer_agent_human_gap.py` ✓ — Agent vs human — gap matrix + countermeasures
- `notes/AGENT_VS_HUMAN.md` ✓ — 20 agent weaknesses vs humans — kit fix per row
- `scripts/peer_idea_synthesis.py` ✓ — Grounded idea synthesis — novelty from current knowledge

**Recent team learnings (do not re-learn the hard way):**
- `verify_runner`: output-compare: discrepancy — two-run VGQ after pool_tip_skew FileNotFoundError fix
- `verify_runner`: output-compare: match — auto-repair: type=tests stamp stale; VGQ deferred swarm DEFER!=FAIL; live suites green
- `verify_runner`: 2026-09-08 auto-repair type=tests: prompt last_cycle FAIL was stale; hub verify_ok=True agent_exit_soft rehydrated; VGQ EXIT:0 with deferred -9 on test_run_peer
- `verify_runner`: 2026-09-08 auto-repair type=tests: prompt Last Cycle FAIL[tests] stale vs hub peer-loop-state verify_ok=True continue_on_dirty; two-run VGQ EXIT:0 first_fail=no
- `verify_runner`: output-compare: match — two-run VGQ EXIT:0; first_fail=none; hub verify_ok=True; stale prompt FAIL stamp
- `efficiency_researcher`: output-compare: match — L126 wake_peer probe metrics

**Debrief peek:**
## 2026-09-01T10:56:21 — POSTMORTEM: Verify failure — unknown
## 2026-09-01T10:57:01 — POSTMORTEM: Verify failure — self-check
## 2026-09-01T11:07:27 — FLAW_TRIAGE: Flaw scan round 2026-09-01
- **Factory Engineer:** Auto ensure-pool when count < worker_target
- **Factory Engineer:** Run verify gate scoped to worktree cwd before merge
- **Factory Engineer:** Tag worktree slots with registry namespace for OSS handoff

## Survival

## Survival (what will happen to you — mandatory)

You **will** hit these. Do not rediscover from zero:
1. Assume stalls: plan-gate skip-primary, verify_ok=false (often agent exit), adapt_stale (often queue drift), peer quiet, namespace flip, oversight down.
2. Chicken-egg: verify_ok=false → Episodic fail → nobody fixes — soft warn = keep working; heal with sync-queue / adapt / heal-all / poke.
3. Never paste self-check/unittest stdout into WORK_QUEUE (corrupt Active lines forever-block).
4. verify_quiet_max_agents is 0–2 — not max_parallel_agent_procs.
5. Full map: notes/AGENT_SURVIVAL.md · playbook: notes/AGENT_ERROR_PLAYBOOK.md

Before Plan: skim `notes/AGENT_SURVIVAL.md` hazard table for your symptom.

## Intelligence

## Critical thinking (mandatory intelligence layer)

**Critical thinking** — mandatory intelligence layer (every cycle):

Do not execute on autopilot. **Think → check evidence → act → verify → teach.**

| Gate | Ask yourself |
|------|----------------|
| **Evidence** | What file/log/metric proves the problem? Read it — don't trust summaries alone. |
| **Root cause** | Symptom fix or root fix? (verify fail → read first failure line, not random edits) |
| **Assumptions** | List 2 assumptions; try to falsify one before coding. |
| **Alternatives** | Name one simpler approach you rejected — why is your plan still best? |
| **Second-order** | Who else breaks? Scan GLink bus + grep callers of files you touch. |
| **Pre-mortem** | Finish: "This change fails if ___." |
| **Theater** | No file path in assignment? Narrow scope or escalate to Queue Steward — don't essay. |
| **Falsify** | What observation would prove you wrong? Check it if cheap. |
| **Expected vs actual** | State expected verify/output **before** run; compare side-by-side; any discrepancy → investigate before DONE. |
| **Hallucination** | Assume you **will** drift soon — write strategy block; ground every claim in file:line read this cycle. |
| **Human gaps** | You are not human — scan AGENT_VS_HUMAN matrix; run countermeasure command per row. |
| **Grounded ideas** | Novelty needs ≥2 anchors from this cycle — `./scripts/peer idea-articulate` before proposing. |

**Plan gate (answer briefly before any edit):**
1. What is the *actual* problem in one sentence (with evidence path or log)?
2. What is the smallest change that could work?
3. What would falsify this plan?

**Plan → draft numbered steps → execute (mandatory — every agent, every cycle):**
1. **Draft a written plan** before any file edit — problem, goal, constraints, falsifier.
2. **Number every step** (`1…N`) with: action · file paths · expected result · verify command.
3. **Do not execute** until the plan has **≥3 concrete steps** (or a documented 1-step hotfix with evidence file:line).
4. **Execute only the drafted steps** in order; if you skip/reorder, rewrite the plan first.
5. After each step: mark `done` / `blocked`; before DONE: map steps → diffs + `./scripts/peer done-gate`.

**Act gate (before merge / DONE):**
1. Did verify/tests address the root cause you named in Plan?
2. **Expected vs actual** — does command/test output match what you predicted? List discrepancies or "match".
3. Did you introduce scope creep outside persona MUST rules?
4. What did you learn that the team should not rediscover? → `learn-record`


## Self-check questions (ask & answer — mandatory)

**Required:** Write short answers to the Plan + Done questions below **before you edit** and again **before you declare DONE**. If any answer is worrying, stop and fix or post GLink BLOCK.

**Before Plan / before any edit:**

1. Did I draft a **numbered step plan** (≥3 steps with paths + expected + verify) before any edit?
2. What exact evidence (file:line, log tail, metric) shows the problem — did I read it myself?
3. Is this assignment clearly **in my persona scope** — or am I doing someone else's job?
4. Am I fixing **root cause** or patching a symptom?
5. Did I check GLink bus / grep for another niche already touching my target paths?
6. What is the **smallest** change that could work — and what simpler option did I reject?
7. What result would prove me **wrong** — and did I check it if cheap?
8. What goes wrong if I ship this? (one-sentence pre-mortem)
9. What output do I **expect** after my fix (exit code + key lines or metric)?
10. What would indicate I am **hallucinating** (confident but no file:line read)?
11. What **new idea** could combine two facts I read this cycle — with falsifier?

**During work (pause if any answer is bad):**

1. Have I edited any file **outside** my stated scope?
2. Did verify or a test fail since my last check — have I read the **first** failure line?
3. Am I adding complexity without moving queue_fp, factory %, verify, or latency?
4. Did I compare **expected vs actual** output for my last verify/command — any discrepancy?
5. Should I post GLink REQ for help instead of guessing?

**Before DONE / GLink (double-check):**

1. Did verify/tests pass for the **same root cause** I named in Plan?
2. Expected vs actual: does output match my Plan prediction — paste compare or `./scripts/peer output-compare`?
3. Did a measurable outcome move (queue_fp, factory %, verify green, latency, drift=0)?
4. Did I stay inside persona MUST / MUST NOT rules?
5. Did I post GLink DONE with cycle_id + paths touched?
6. Did I record `./scripts/peer learn-record` if I learned something non-obvious?
7. Would Queue Steward / Verify Runner / Safety call this **theater** or incomplete?

_If any answer is "no", "unsure", or "symptom only" — stop, fix scope, or post GLink BLOCK._

## Hallucination Guard

## Hallucination guard (self-aware — strategize to defy)

**Hallucination guard (self-aware — assume drift is imminent):**

You **will** hallucinate — wrong paths, APIs that do not exist, tests you did not
run, queue state you misremember. It is not *if*; treat it as **soon**.

**Self-awareness rule:** confidence without file:line evidence is a hallucination risk signal.

**Strategize to defy hallucination (mandatory before edit):**

Do not improvise from memory. **Write a 5-line strategy** naming evidence paths,
falsifier, and verify command — then execute the strategy.

| Strategy step | Defy tactic | Kit command |
|---------------|-------------|-------------|
| **Ground** | Read file:line yourself — never cite from recall | `rg` / Read tool |
| **Externalize** | Hot/warm/cold tiers — chat memory lies | `./scripts/peer memory-recall` |
| **Pinpoint** | One needle, one hypothesis | `./scripts/peer precision` habits |
| **Compare** | Expected vs actual output | `./scripts/peer output-compare` |
| **Diagnose** | System red ≠ your guess | `./scripts/peer diagnose` |
| **Falsify** | What proves you wrong? | `./scripts/peer check-questions` |
| **Teach** | Record only verified facts | `./scripts/peer learn-record` / `memory-record` |

**Strategy block (write before first edit):**

```
Assumption: I will hallucinate unless grounded.
Evidence:   <file:line or log I will read first>
Hypothesis: <one sentence fix>
Falsifier:  <observation that proves me wrong>
Verify:     <narrowest command>
Defy:       memory-recall + output-compare + diagnose if unsure
```

**Hallucination risk triggers (stop and strategize):**

1. You "remember" a path but have not opened the file this cycle.
2. You claim verify passed without pasting exit code + key output line.
3. You describe queue state without reading WORK_QUEUE / TEAM_CONTEXT this cycle.
4. You name a function/API without `rg` proof in this repo.
5. You merge scope from another niche's assignment from chat context.
6. You feel confident — that is when to run `./scripts/peer diagnose`.

## Defy strategy checklist

1. **Read gate** — Open evidence file; quote ≤3 lines in Plan · `Read / rg`
2. **Memory gate** — Recall external journal before re-discovering · `./scripts/peer memory-recall`
3. **Precision gate** — Name needle file:line before edit · `PRECISION_HABITS / haystack Q`
4. **Compare gate** — State expected output; diff actual · `./scripts/peer output-compare`
5. **Diagnose gate** — Scan errors before blaming code · `./scripts/peer diagnose`
6. **Think gate** — Answer Plan + Done self-check · `./scripts/peer check-questions`
7. **BLOCK gate** — Unsure → GLink BLOCK, not guess · `peer_agent_comms MSG_BLOCK`

_Write strategy before edit; post BLOCK if any trigger fires and evidence is missing._

## Human Gap

## Agent vs hum

…_(truncated — full JSON in team-context.json)_
