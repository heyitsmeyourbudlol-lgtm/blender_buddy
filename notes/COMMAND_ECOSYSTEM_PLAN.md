# Command-based ecosystem — plan

**Needle:** `OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07`  
**Status:** DONE 2026-09-07 — Phases 0–5 landed  
**North star:** Agents **execute** `./scripts/peer <id>` for repetitive work; the kit **grows** a living command graph; native Cursor Automations eventually wake the same verbs.

Related: `notes/COMMAND_BUILDER.md` · `notes/AGENT_COMMANDS.md` · `notes/COMMAND_COVERAGE.md` · `notes/HUB_PEER_VERBS.md` · `notes/CURSOR_AUTOMATIONS_MIGRATION.md` · `notes/LOOP_STRATEGY.md`

---

## Problem

| Mode | Symptom |
|------|---------|
| Raw scripts | Agents retype `python3 scripts/foo.py …` |
| Ad-hoc compounds | Some loops are peer commands; many are not |
| Knowledge in prompts | Recipes buried in role text instead of callable ids |
| Daemon as brain | peer_loop invents steps instead of calling named verbs |

**Command ecosystem** = every repetitive factory action is a **named, tested, discoverable** command (or compound), with agents obligated to call them.

---

## Principles

1. **Verb first** — If it happens twice, it gets an id.
2. **Execute ≠ invent** — Peers *run* commands; **Command Builder** *adds* them.
3. **Compounds > heroes**
4. **Registry is SoT** — `scripts/peer_commands.py` + `notes/AGENT_COMMANDS.md`
5. **Fail-soft, verify-hard**
6. **Kill the kit when native wins** — same verb ids → Automations later

---

## Implementation order — all landed

### Phase 0 — Norms ✅
- Command Builder committed · AGENTS policy · plan-gate soft warn · niche_task prefix

### Phase 1 — Coverage map ✅
- `scripts/command_ecosystem.py` · `notes/COMMAND_COVERAGE.md` · layer tags · Backlog enqueue

### Phase 2 — Hard contracts ✅
- `command-dispatch-audit` · orchestrator prompt inject · `mini-app-promote` weekly path · compound resolve tests

### Phase 3 — Factory-AI verb pack ✅
- `niche-bank-status` · `niche-bank-eval` · `niche-serve` · `niche-assist-once` · `niche-mint-train` · `factory-dynamics`

### Phase 4 — Product gravity ✅
- `notes/HUB_PEER_VERBS.md` · linked from `HUB_GRAVITY_CHOICE.md` · AGENTS dual-path

### Phase 5 — Native Automations map ✅
- Verb → Automation table in `CURSOR_AUTOMATIONS_MIGRATION.md`

---

## Wake

```bash
./scripts/peer command-ecosystem-finish   # coverage + audit + hub verbs + promote scan
./scripts/peer commands-cycle             # Command Builder
./scripts/peer command-dispatch-audit
./scripts/peer niche-assist-once
./scripts/peer commands-list --pivotal
```

---

## Success metrics

| Metric | Status |
|--------|--------|
| Pivotal discoverable | AGENT_COMMANDS.md via commands-sync |
| Coverage matrix | COMMAND_COVERAGE.md |
| Dispatch audit | COMMAND_DISPATCH_AUDIT.md |
| Factory-AI verbs | registered + peer cases |
| Hub product verbs | HUB_PEER_VERBS.md |
| Automations map | CURSOR_AUTOMATIONS_MIGRATION.md § Verb map |

---

## Honesty

Process infrastructure, not model intelligence. Commands make the factory legible; they do not replace verify, product proof, or niche specialists.
