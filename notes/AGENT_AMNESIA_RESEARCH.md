# Agent amnesia — research list + plan

Needle: `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07`  
Audience: CreatePlan / operator brief  
Constraints: factory throughput · **NO PAY** · pack additive only (never delete live SoT)

**Status (2026-09-07):** SCOPE A/B/C MVPs **shipped**. Pack-verify wire into heal/pre-dispatch (**DONE** via `memory-pack-gate`) · role state schema (**DONE**) · niche domain classifier heuristic stub (**DONE**; train T10-09 done) · Mamba carve Phase1 (**DONE** — budget + abstract backends; see `notes/TOP10_NEXT.md` T10-10).

**Already in flight (do not reinvent):** Hot always-read (`AGENT_WORKING_MEMORY` / `MEMORY_SPAN`) · lossless pack (`peer_memory_compress` + `SOP_LOSSLESS_MEMORY_COMPRESSION`) · Fact Librarian (`peer_fact_librarian` / `SOP_AGENT_REMEMBRANCE`) · Cursor rule `file-sot-memory` · last_cycle / GLink / peer transcript / vaults / NO-PAY sticky · cold FTS (`knowledge_index` + optional Mamba) · domain peer roles in `scripts/peer_tasks.json`.

---

## Domain SME agents (prominent)

**Not one mega-librarian.** Partition the repo; each SME owns path globs + SoT; Fact Librarian is a **router**, not the sole memory brain.

```
Main worker
  → Fact Librarian (router: query → domain_id)
    → Domain SME relay (scoped pack index + live SoT + role reads)
      → Compact cited facts
        → Main edits / verifies
```

| Domain id | Path globs (validated) | SoT / reads | Existing `peer_tasks.json` SME approx |
|-----------|------------------------|-------------|----------------------------------------|
| `peer_loop` | `scripts/peer_*.py`, `scripts/run_peer_tasks.py`, `scripts/automation_adapt.py` | `AUTOMATION.md`, `PEER_ORCHESTRATION.md`, `AGENT_SURVIVAL.md`, `AGENT_ERROR_PLAYBOOK.md` | **factory_engineer**, verify_runner, adapt_specialist, communications_engineer, progress_monitor |
| `dashboard` | `dashboard/**`, root `server.py`, `train.html`/`train.js` | dashboard static + API notes | compression_engineer (RSS), data_analyst (meters); **missing** dedicated dashboard SME |
| `compression_niche` | `scripts/compression_*.py`, `scripts/niche_*.py`, `scripts/factory_*.py`, `notes/niche_distill/**`, `COMPRESSION_*`, `BITNET_*` | `COMPRESSION_*`, `niche_distill/README+RECIPE`, `SOP_LOSSLESS_*` | **niche_distiller**, compression_trainer, compression_engineer, bitnet_researcher, train_eval_runner, fact_checker |
| `dgx_clean` | `scripts/dgx_*.py`, `dgx_speed.local.json`, `DGX_*`, CLEAN remote helpers | `DGX_SPEED_PLAN.md`, `DGX_NVFP4_*`, ram budget scripts | **gpu_profiler**, research_speed_engineer, model_serve_engineer, dgx_ops (if present) |
| `queue_improve` | `notes/WORK_QUEUE.md`, `scripts/self_improve_context.md`, `scripts/automation_improve.py`, `scripts/automation_team.py` | WQ twin + improve SOPs | **queue_steward**, progress_monitor |
| `safety_nopay` | `notes/SAFETY_GATES.md`, `scripts/peer_pen_test.py`, AGENTS NO-PAY, export filters | `SAFETY_GATES.md`, `PEN_TEST.md` | **safety_auditor**, pen_test_researcher, legal_compliance, claim_ledger_scribe |
| `docs_sops` | `notes/SOP_*.md`, `notes/SOP_INDEX.md`, `notes/AGENT_*.md`, `AGENTS.md`, `notes/README.md` | SOP_INDEX, AGENT_WORKING_MEMORY | **tech_writer**, fact_checker (ledger docs) |

**Compose rule:** Main never deep-reads another domain’s tree; asks `fact-query --domain <id>` or routes via role strengths already in `peer_tasks.json`. Later: tiny niche classifiers pick `domain_id` + top files.

**OWNERS file:** **shipped** — `notes/DOMAIN_OWNERS.md` via `./scripts/peer domain-owners` (from `scripts/repo_domain_smes.json`).

---

## What else (top 10 — NOW)

Beyond Hot / pack / librarian / domain SMEs / read-SoT rule:

1. **Write-through decision ledger** — **shipped** `notes/session_ledger/YYYY-MM-DD.jsonl` via `./scripts/peer session-ledger-append`.
2. **Session claim ledger (OVERCLAIM style)** — **shipped** `./scripts/peer session-claim` → `notes/session_ledger/claims/`.
3. **Librarian-receipt preflight** — **shipped** plan-gate soft→require when prefer_librarian (`fact-query` receipt or `--read-ack`).
4. **Turn-end conversation distill** — **shipped** `./scripts/peer session-distill`.
5. **Memory auditor dual-agent** — **shipped** mechanical MVP `./scripts/peer memory-audit` (no paid spawn).
6. **Spaced constraint reinject** — **shipped** every N Hot refreshes (NO-PAY + factory-works + pack≠delete).
7. **`DOMAIN_OWNERS.md` auto-gen** — **shipped** `./scripts/peer domain-owners`.
8. **Dashboard memory health** — **shipped** `/api/memory-health` + `/progress` + `/agents` panels; `./scripts/peer memory-health`.
9. **Worktree-local vs hub SoT sync** — **shipped** documented in Hot + `session-hub-rules`.
10. **Anti-amnesia eval quiz** — **shipped** `./scripts/peer memory-quiz`.

---

## Fit snapshot

| Layer | Status |
|-------|--------|
| Hot + last_cycle + file-sot rule | **have** |
| Lossless pack + verify | **have** (CLI verify = have; heal/pre-dispatch `memory-pack-gate` = **have**) |
| Fact librarian MVP | **have** (domain router + receipt) |
| Domain SME *roles* | **have** (peer_tasks); *router* = **have** |
| OVERCLAIM claim ledger | **have** (BitNet + session-claim) |
| learn-record / PROJECT_LEARNING | **have** (opt-in; not write-through) |
| Read-ack / librarian receipt gate | **have** |
| Memory health dashboard | **have** |
| Anti-amnesia evals | **have** |
| Tiny niche domain classifiers | **have** (heuristic stub + librarian hook; train T10-09 done) |
| Episodic by cycle_id | **have** (thin `memory-episodic`) |

---

## Research list (prioritized extras + core)

| # | Name | How (1 line) | Fit | Risk | P | Ship |
|---|------|--------------|-----|------|---|------|
| 1 | Domain SME router | Librarian classifies query → domain SME relay → compact facts | have | wrong domain | P0 | **DONE** |
| 2 | Librarian Hot wire | Inject prefer-librarian + fact-query into Hot/pre-dispatch | have | prompt bloat | P0 | **DONE** |
| 3 | Pack verify in heal | `--verify` / cheap gate on pack during heal/pre-dispatch | have | false red | P0 | **DONE** (`memory-pack-gate`) |
| 4 | Write-through ledger | Append decision jsonl before reply | have | noise/secrets | P0 | **DONE** |
| 5 | Librarian receipt gate | No edit without fact-query receipt when prefer=true | have | gate theater | P1 | **DONE** |
| 6 | Turn-end distill | Cited lossy summary → PEER_CONVERSATION / last_cycle | have | bad citations | P1 | **DONE** |
| 7 | Session claim ledger | OVERCLAIM rows for session assertions | have | scribe load | P1 | **DONE** |
| 8 | Spaced sticky reinject | Re-emit NO-PAY / factory-works / safe-delete every N | have | annoyance | P1 | **DONE** |
| 9 | DOMAIN_OWNERS.md | Auto CODEOWNERS-like domain map | have | drift | P1 | **DONE** |
| 10 | Memory auditor peer | Second agent checks Plan vs pack/SoT | have | 2× agents | P2 | **DONE** (mechanical) |
| 11 | Dashboard memory health | Pack age, hit rate, Hot stale meters | have | vanity UI | P2 | **DONE** |
| 12 | Worktree memory rules | Hub SoT only; scratch local; sync discipline | have | fork SoT | P1 | **DONE** |
| 13 | Anti-amnesia quiz | Eval SoT recall after N turns | have | flake | P2 | **DONE** |
| 14 | Tiny niche classifiers | Niche models: domain_id + file hint | partial | train cost | P2 | **DONE** (heuristic; train Backlog) |
| 15 | Cold-before-read | knowledge-search before whole-module Read | have | miss | P1 | **DONE** |
| 16 | Role state schema | Tiny JSON: assignment, blocked, files, verify_cmd | have | schema churn | P2 | **DONE** (`peer_role_state`) |
| 17 | Read-ack gate | Plan cites opened always-read paths | have | soft-ignore | P1 | **DONE** |
| 18 | Episodic by cycle_id | Store/retrieve per wave | have | storage | P3 | **DONE** (thin) |
| 19 | Mamba brain carve | Larger rerank on DGX (`MAMBA_SCALE_PLAN`) | partial | RAM | P3 | **DONE** Phase1 (budget+backends; Phases 2–7 open) |
| 20 | Free-desktop librarian spawn | `--agent` side cursor-agent, never paid | have | spawn storms | P3 | **DONE** (opt-in `--agent`) |
| A | **Anti:** full-repo stuffing | Never expand pack / dump notes into chat | — | amnesia ironically | — | **sticky** |
| B | **Anti:** delete live SoT | Pack is additive archive only | — | factory death | — | **sticky** |

---

## Plan (phased)

### Near — finish pack + librarian — **DONE**
1. Additive pack only; `peer_memory_compress --verify` CLI — **have**; heal/pre-dispatch `memory-pack-gate` — **DONE**.
2. Wire `format_hot_librarian_block` + `should_prefer_librarian` into Hot — **DONE**.
3. Document `./scripts/peer fact-query` as fact path — **DONE** (`SOP_AGENT_REMEMBRANCE`).
4. Write-through `session_ledger` — **DONE**.
5. Pointer-only updates to `AGENT_WORKING_MEMORY` — **DONE**.

### Next — domain routers + high-leverage gates — **DONE**
1. **`notes/DOMAIN_OWNERS.md`** + librarian `--domain` / auto-route — **DONE**.
2. Map router targets to existing roles — **DONE** (`repo_domain_smes.json`).
3. **Librarian-receipt preflight** — **DONE**.
4. **Turn-end distill** + **spaced sticky** — **DONE**.
5. **Session claim ledger** — **DONE**.
6. **Worktree vs hub** — **DONE**.
7. Read-ack + cold-before-read — **DONE**.

### Later — heavier / eval / niches
1. Memory auditor dual-agent — **DONE** (mechanical MVP).
2. Dashboard memory health panel — **DONE**.
3. Anti-amnesia quiz harness — **DONE**.
4. Tiny niche models as domain/file classifiers — **DONE** (heuristic stub; train Backlog).
5. Episodic store — **DONE** (thin); Mamba cascade — **deferred** (`TOP10_NEXT.md`).
6. Role state schema — **DONE** (`peer_role_state`).

---

## Commands

```bash
./scripts/peer memory
./scripts/peer memory-compress
./scripts/peer memory-compress-verify
./scripts/peer memory-pack-gate
./scripts/peer role-state list
./scripts/peer niche-domain-classify "…"
./scripts/peer fact-query "…"
./scripts/peer fact-domains
./scripts/peer domain-owners
./scripts/peer session-ledger-append --decision "…" --paths a,b --needle NEEDLE
./scripts/peer session-distill --target both --text $'- bullet `path:line`'
./scripts/peer session-claim --claim "…" --source "path:line"
./scripts/peer session-sticky-status
./scripts/peer session-hub-rules
./scripts/peer memory-audit --claim "…"
./scripts/peer memory-quiz
./scripts/peer memory-health
./scripts/peer memory-episodic
./scripts/peer knowledge-search "…"
./scripts/peer learn-record --role ROLE --text "path:line fact"
./scripts/peer plan-gate --read-ack notes/AGENT_WORKING_MEMORY.md
python3 scripts/peer_memory_compress.py --verify
python3 scripts/peer_fact_librarian.py --threshold-status
```

Dashboard: `http://127.0.0.1:8765/api/memory-health` · `/progress` · `/agents`

## Related SoT

`MEMORY_SPAN.md` · `HALLUCINATION_GUARD.md` · `SOP_LOSSLESS_MEMORY_COMPRESSION.md` · `SOP_AGENT_REMEMBRANCE.md` · `KNOWLEDGE_INDEX.md` · `BITNET_FACTCHECK.md` (OVERCLAIM pattern) · `peer_tasks.json` · `LOOP_STRATEGY.md` · `DOMAIN_OWNERS.md` · `session_ledger/README.md`
