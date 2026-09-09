# Agent working memory — always-read SoT index

_Thin pointer index. Chat memory is not SoT — open these files every turn._

Needles: `OVERSEER_FACT_LIBRARIAN_2026_09_07` · `OVERSEER_LOSSLESS_MEMORY_COMPRESS_2026_09_07` · `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07`

## Remembrance (main vs librarian vs domain SME)

| Who | Does |
|-----|------|
| **Main agent** | Work (edit, verify, DONE) — not whole-repo in head |
| **Fact Librarian** | Compact fact relay — `./scripts/peer fact-query "…"` |
| **Domain SME** | Same librarian scoped to one domain — `--domain <id>` |

Domain map: `notes/REPO_DOMAIN_SMES.md` · `notes/DOMAIN_OWNERS.md` · `scripts/repo_domain_smes.json`

## Start every turn

1. Open this file.
2. **Sequencing lock:** Do not jump ladder rungs until current factory path is A→Z without oversight (`AGENTS.md` · `OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07`). **Status green** (`notes/FACTORY_A_TO_Z_PROOF.md`) — Phase4 unlocked 2026-09-08 CPT [PR #2](https://github.com/heyitsmeyourbudlol-lgtm/CPT/pull/2) + origin ref (`green_lock_eligible=pr`); still prefer kit-run for new targets.
3. Read Active `notes/WORK_QUEUE.md` (twin: `scripts/self_improve_context.md`).
4. Skim last_cycle in Hot memory (incl. amnesia pins when present).
5. If pack large / scattered facts → `./scripts/peer fact-query [--domain ID] "<task>"`.
6. On error → `notes/AGENT_ERROR_PLAYBOOK.md`.
7. Pack (additive): `notes/memory_artifacts/repo_memory_pack.json.z` — never delete live SoT.
8. Before DONE: `./scripts/peer session-ledger-append --decision "…" --paths …` (write-through).

## Keep going (user lock)

**Do not stop until the user explicitly says stop.** Every completion → worker-done refill + ≤8 Task peers. Never treat a quiet chat as permission to idle.

## Worker done → forever refill

Needle: `OVERSEER_WORKER_DONE_REFILL_2026_09_07`

While `peer-loop` + `improve-loop` run forever (CLEAN brain): **a finished worker is not an exit** — it is a handoff.

1. Mark the Active line `[x]` and keep **WQ ↔ SIC Active identical**.
2. Before ending the turn, ensure **≥1 open Active** remains (refuse empty Active / empty CLEAN). Prefer order: **Newdrop after #N** → next **TOP10_NEXT open** → agent/command builder (A→Z Phase4 **green**).
3. Sync Mac→CLEAN (`rsync` WQ+SIC); `touch notes/peer-turn.signal`.
4. Launch the next wave **≤8** parallel Task peers in **one** message for remaining opens — do not wait for the human.
5. Improve forever heals+enqueues+wakes; chat must still refill when Desktop Tasks finish outside the daemon.

Meta (`LOOP_STRATEGY`): infinite loop of **exiting** loops — A→Z Status **green**; keep ≥1 Active fuel (Newdrop → TOP10 → builders).

## Hub SoT vs worktree scratch

| Location | Rule |
|----------|------|
| **Hub** | Always-read + WQ twin + Hot/pack + `notes/session_ledger/` — single SoT; do not fork per worktree |
| **Worktree** | Ephemeral `notes/worktree_scratch/` only — never promote scratch into Always-read |
| **Deletes** | Pack ≠ delete live SoT; safe deletes = scratch/temp only |

## Always-read (canonical)

| Path | Why |
|------|-----|
| `notes/AGENT_WORKING_MEMORY.md` | This index |
| `notes/REPO_DOMAIN_SMES.md` | Domain SME ownership |
| `notes/DOMAIN_OWNERS.md` | CODEOWNERS-like path → SME (auto-gen) |
| `notes/MEMORY_SPAN.md` | Hot/warm/cold tiers |
| `notes/WORK_QUEUE.md` | Live queue (Active) |
| `scripts/self_improve_context.md` | Queue twin |
| `notes/PEER_CONVERSATION.md` | Canonical conversation |
| `AGENTS.md` | Prefs + NO PAY |

## Amnesia combat commands

```bash
# Ledger / distill / claims / stickies
./scripts/peer session-ledger-append --decision "…" --paths a,b --needle NEEDLE
./scripts/peer session-distill --target both --text $'- bullet `path:line`\n- …'
./scripts/peer session-claim --claim "verify green" --source "path:line"
./scripts/peer session-sticky-status
./scripts/peer session-hub-rules

# Owners / receipt / gates
./scripts/peer domain-owners
./scripts/peer fact-query "…"          # writes receipt for plan-gate
./scripts/peer plan-gate --read-ack notes/AGENT_WORKING_MEMORY.md

# Audit / quiz / health / episodic
./scripts/peer memory-audit --claim "…"
./scripts/peer memory-quiz
./scripts/peer memory-health
./scripts/peer memory-episodic
```

Spaced stickies (NO-PAY · factory-works · pack≠delete) re-emit every N Hot refreshes via `peer_transcript.format_harness_memory`.  
Dashboard: `/api/memory-health` · `/progress` · `/agents`. SOP: `notes/SOP_AGENT_REMEMBRANCE.md`.

## Example fact-queries

```bash
./scripts/peer fact-query "noop plan-gate"                 # auto → peer_runtime
./scripts/peer fact-query --domain queue_sync "Active"
./scripts/peer fact-query --domain compression_bitnet "NVFP4"
./scripts/peer fact-domains
./scripts/peer domain-owners
```

## NO PAY

Free desktop / local / CLEAN only — never paid API / Stripe / credits.

## Newdrop product (Top10)

Do **not** change Newdrop UI unless a real flaw is detected. Prefer backend/security/ops. Canonical: `notes/TOP10_PRODUCTION_POWER.md` guardrails.

## TOP10_NEXT (kit next-10)

Durable implementer role: **`top10_implementer`**. SoT: `notes/TOP10_NEXT.md` · SOP: `notes/SOP_TOP10_NEXT.md` · `./scripts/peer top10`.

## Agent Builder (task→worker)

Role **`agent_builder`**. SoT: `notes/SOP_AGENT_BUILDER.md` · `./scripts/peer agent-build` · `agent-who "task"` · Needle `OVERSEER_AGENT_BUILDER_2026_09_07`.

## Factory A→Z (sequencing lock)

Durable role: **`kit_a_to_z`**. SoT: `notes/FACTORY_A_TO_Z_PLAN.md` · Tasks: `notes/FACTORY_A_TO_Z_TASKS.md` · SOP: `notes/SOP_FACTORY_A_TO_Z.md` · `./scripts/peer a-to-z` · `./scripts/peer kit-run --repo CPT`. **Phase 4 Status green** — CPT [PR #2](https://github.com/heyitsmeyourbudlol-lgtm/CPT/pull/2); prefer kit-run for new registry targets.
