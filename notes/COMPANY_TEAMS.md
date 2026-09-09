# Company teams → roles

_Updated 2026-09-05 22:27:05. Gap audit: catalog vs `peer_tasks.json` → `agent_roles`._

## Summary

| Catalog roles | 25 |
| Live agent_roles | 45 |
| Present | 25 |
| Missing | 0 |
| Extra (not in catalog) | 20 |

## Plan → steps → execute (all agents)

Every niche **must** draft a numbered step plan before editing, then execute only those steps.
See `notes/CRITICAL_THINKING.md` · `PLAN_EXECUTE_MANDATE`.

## Departments / teams

### Engineering

- **DevOps / Platform** — STAFFED; present=['adapt_specialist', 'sre_release']; missing=—
- **Developer Experience** — STAFFED; present=['command_builder']; missing=—
- **Performance** — STAFFED; present=['compression_engineer']; missing=—
- **Platform Engineering** — STAFFED; present=['factory_engineer']; missing=—
- **Product Engineering** — STAFFED; present=['backend_engineer', 'frontend_engineer']; missing=—
- **Quality Engineering** — STAFFED; present=['verify_runner', 'qa_engineer']; missing=—

### External

- **External Integration** — STAFFED; present=['integration_architect']; missing=—

### GTM

- **Growth** — STAFFED; present=['growth_marketer']; missing=—
- **Support** — STAFFED; present=['customer_success']; missing=—

### Operations

- **Analytics** — STAFFED; present=['data_analyst']; missing=—
- **Documentation** — STAFFED; present=['tech_writer']; missing=—
- **Finance** — STAFFED; present=['finance_billing']; missing=—
- **Internal Comms** — STAFFED; present=['communications_engineer']; missing=—
- **Program Management** — STAFFED; present=['queue_steward']; missing=—
- **Progress Review** — STAFFED; present=['progress_monitor']; missing=—

### Product

- **Design** — STAFFED; present=['design_ux']; missing=—
- **Product** — STAFFED; present=['product_manager']; missing=—

### Research

- **Research** — STAFFED; present=['efficiency_researcher', 'output_researcher']; missing=—

### Security

- **Security** — STAFFED; present=['safety_auditor', 'pen_test_researcher']; missing=—
- **Trust & Safety** — STAFFED; present=['legal_compliance']; missing=—

## Extra live roles (keep)

- `architecture_researcher`
- `bitnet_researcher`
- `claim_ledger_scribe`
- `compression_trainer`
- `creative_miner`
- `dataset_curator`
- `debrief_optimizer`
- `lessons_curator`
- `dgx_ops`
- `fact_checker`
- `flaw_researcher`
- `gpu_profiler`
- `hallucination_auditor`
- `idea_synthesis`
- `model_serve_engineer`
- `niche_distiller`
- `parallel_dispatch_coach`
- `recipe_lock_steward`
- `research_speed_engineer`
- `train_eval_runner`
- `worktree_manager`

## Commands

- `./scripts/peer company-org` — audit + print JSON summary
- `./scripts/peer company-org-md` — refresh this digest
- `./scripts/peer company-org-enqueue` — enqueue staffing gaps
