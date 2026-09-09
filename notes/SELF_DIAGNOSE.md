# Self-diagnosis — instant system scan

_Updated 2026-09-08 16:16:24_ · self-sufficient · errors + miscalculations + poor logic

**Self-diagnosis (self-sufficient — run instantly):**

Before Plan and whenever output surprises you, **diagnose the system** — do not guess.

| Class | What to catch | Instant command |
|-------|---------------|-----------------|
| **Errors** | verify fail, daemon down, locks, timeouts, import breaks | `./scripts/peer diagnose` |
| **Miscalculations** | queue drift, noop claimed as progress, ETA miss, wrong metric | `./scripts/peer diagnose` |
| **Poor logic** | theater queue, scope creep, symptom-only fix, hero collapse | `./scripts/peer check-questions` + diagnose |

**Rule:** If diagnose returns critical/high findings → fix or `./scripts/peer heal-all` before new feature work.

**Instant diagnose workflow:**

```
1. ./scripts/peer diagnose          # full scan (errors + math + logic hints)
2. Read first finding + evidence    # file:line or bottleneck id
3. ./scripts/peer playbook-lookup "<symptom>"  # mechanical fix
4. Re-run targeted verify           # narrowest test first
5. memory-record / learn-record     # teach the team the root cause
```

## Self-diagnosis report

**Error:**
- **[medium] Noop cycle — queue fingerprint unchanged after ok verify** (error) — playbook:noop_cycle → `./scripts/peer noop-break` · `./scripts/peer compact-queue` · `./scripts/peer poke`
  - Logic: Demote theater queue lines; land one minimal diff that changes queue_fp or factory %.

**Miscalculation:**
- **[medium] Noop cycle — queue did not advance** (miscalculation) — queue_fp 8cd615b0e0c8fafe → 8cd615b0e0c8fafe → `./scripts/peer noop-break` · `./scripts/peer diagnose`
  - Logic: Diagnose why open items stayed open — wrong scope or BLOCK.

## Error checks

1. Did verify/self-check pass on the **same** root cause I named?
2. First failing line only — not rerunning full suite in a loop?
3. Any open self-heal bottleneck with severity high/critical?
4. Daemon + last_cycle present — or am I dispatching into a dead loop?

## Miscalculation checks

1. Did queue_fp or factory % **actually move** — or did I claim progress without metric?
2. Expected vs actual: did I run `./scripts/peer output-compare` before DONE?
3. Peer assign ETA: did I run `./scripts/peer eta` before promising when=now?
4. Are WORK_QUEUE and self_improve_context **identical** for open items?

## Logic checks

1. Am I fixing **root cause** or patching a symptom visible in logs only?
2. Does my Plan cite **evidence I read** — not a summary I assumed?
3. Is this assignment **executable** (file path + verify) or theater?
4. Did I confuse **correlation** with cause (noop + green verify ≠ queue advance)?
5. Would another niche call this **scope creep** or wrong persona?

## Niche guidance

### Factory Engineer
- Dispatch path: peer_loop → orchestrate → parallel_dispatch — which link broke?
- self-check must pass after orchestration edits.

### Orchestrator
- Hero collapse = poor logic — split scopes before implementing.
- Run diagnose before dispatch when last_cycle verify_ok=false.

### Queue Steward
- Drift pair sync before demoting lines — miscalculation if only one file updated.

### Safety Auditor
- PASS without file:line list = poor logic — BLOCK or cite gates.

### Verify Runner
- Classify: flake vs env vs code — evidence for each before editing.
- Run-only: do not edit production code unless assignment explicitly scopes it.
