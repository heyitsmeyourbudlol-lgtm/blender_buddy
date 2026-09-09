# Agent roles — company teams → niches

Orchestrator launches **hub_worker_pool** parallel workers (default **12**; `max_parallel_peers` caps expand). Roles live in `scripts/peer_tasks.json` → `agent_roles`. Full company catalog + gap audit: `notes/COMPANY_TEAMS.md` · `./scripts/peer company-org`.

**Plan → draft numbered steps → execute** is mandatory for every niche (see `notes/CRITICAL_THINKING.md`).

## Orchestrator (you — primary agent)

- Launch **hub_worker_pool** Task peers in **one** message — one worker per assigned niche
- Assign by strength / job title; each peer must draft a numbered step plan before edits
- Merge outputs; Safety Auditor can BLOCK; Verify Runner gates merge

## Company departments (45 roles)

| Department | Teams | Roles |
|------------|-------|-------|
| Operations | **Progress Review (always-on)** | **progress_monitor** — 24/7 oversight daemon → cursor-agent on stall |
| Engineering | Platform, Product Eng, QA, DevOps, Perf, DX | factory, backend, frontend, verify, qa, adapt, sre_release, compression, command_builder, worktree_manager, parallel_dispatch_coach, **top10_implementer** (owns `TOP10_NEXT`) |
| Security | Security, Trust | safety_auditor, pen_test_researcher, legal_compliance, hallucination_auditor |
| Product | Product, Design | product_manager, design_ux |
| Research | BitNet / compression / DGX train | efficiency_researcher, output_researcher, **fact_checker**, **bitnet_researcher** (owns `COMPRESSION_CATALOG` Lane A curation), **compression_trainer**, **research_speed_engineer**, **niche_distiller**, **architecture_researcher**, **train_eval_runner**, **gpu_profiler**, **model_serve_engineer**, **dataset_curator**, **idea_synthesis**, **dgx_ops**, **recipe_lock_steward**, **claim_ledger_scribe** |
| Research | Flaw / creative / debrief / lessons | flaw_researcher, creative_miner, debrief_optimizer, **lessons_curator** (harvest + lossless squeeze only) |
| GTM | Growth, Support | growth_marketer, customer_success |
| Operations | PMO, Comms, Finance, Analytics, Docs | queue_steward, communications, finance_billing, data_analyst, tech_writer |
| External | Integration | integration_architect |

**Progress Monitor** runs as `com.togi.*.oversight-loop` forever (`./scripts/peer progress-monitor-install`). It is not a timed peer niche only — it reviews every ~15s and dispatches cursor-agent when progress stalls.

## Hub roster (live `agent_roles`)

Run `./scripts/peer company-org` for present/missing. Preview assignments:

```bash
python3 scripts/peer_orchestrate.py --dry-run
./scripts/peer agents
./scripts/peer company-org
open http://127.0.0.1:8765/agents
```

Pool rotation + `pool_guaranteed_roles` keep Product/Backend/Frontend/Pen-test in the active hand when the roster exceeds hub slots.

See `notes/PEER_ORCHESTRATION.md` for phase gates.
