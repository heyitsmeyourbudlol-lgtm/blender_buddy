# Product E2E — can automation build end-to-end products?

_Assessment 2026-09-01. Read when deciding whether the kit ships **products** or only **factory capability**._

## Short answer

**Not reliably today.** The automation kit is a strong **dev factory** (queue → peers → verify → worktrees) but it optimizes for **OSS-monster factory readiness**, not **product completion**. It can contribute slices of product work (code, tests, launch templates) when a repo already has a profile and open launch items — but it cannot autonomously close **idea → deployed → paying → distributed** without human steering and missing gates.

## What it can do today

| Layer | Capability | Evidence |
|-------|------------|----------|
| Code | Scoped implement peers, parallel Task dispatch, worktrees | `peer_orchestrate.py`, `peer_worktree.py` |
| Verify (code) | Native test/lint/build per profile | `profiles/caas.json`, `run_peer_tasks.py` |
| Launch intent | Phase 0–6 templates, billing/landing/stripe peers | `peer_tasks.json` launch_* templates |
| Multi-repo intent | Registry, `factory_sprint.py`, adapt profiles | `repos/registry.json`, `automation_adapt.py` |
| Product rules | Constraints in peer briefs (ship before spike, RED paid gates) | `product_constraints`, `LAUNCH.md` |

## What blocks end-to-end product builds

### 1. Factory north star ≠ product north star

Improve forever enqueues **work-kit** items (peer_loop, adapt, verify, worktrees). Success is measured as **irreversible factory artifacts** (PR-shaped diffs on OSS), not **shipped products with users**. See `INVESTMENT_NORTH_STAR` in `scripts/automation_improve.py`.

### 2. Verify gates are code-centric, not product-centric

`verify_ok` means self-check + profile tests passed. It does **not** require:

- Deploy smoke (Vercel/production URL live)
- Billing smoke (Stripe test checkout)
- Changelog / publish proof
- Queue item checked off in the **target product repo**

Phase 5 “End-to-end delivery” in `asi_rubric.py` only composites verify + log + queue advance — still factory-shaped, not product-shaped.

### 3. Runtime factory is unstable

Live horizon signals (2026-09-01): improve LaunchAgent not running, peer LaunchAgent not running, noop loops (queue fingerprint unchanged), dirty tree blocking dispatch. A factory that does not reliably cycle cannot ship products end-to-end.

### 4. Hub-centric dispatch

Default `peer_loop` dispatches from the Automation hub. Registry repos (RAM, CaaS, CPT) need **cwd translation** and per-repo queues. `factory_sprint.py` exists for DGX external lanes but is not the default Mac peer path. CaaS status: `needs-kit-install`; 0 external paying customers.

### 5. No closed product pipeline

Missing wiring:

| Gap | Why it matters |
|-----|----------------|
| **Product ship gate** | Cycle success should require deploy + live URL for ship-priority repos |
| **Per-repo product queue** | `LAUNCH.md` / product WORK_QUEUE on target repo, not only hub queue |
| **Bootstrap revenue repos** | Profiles must be installed (`automation_adapt --heal`) before peers can ship |
| **Billing + deploy verify template** | Stripe/Vercel smoke as verify_commands for revenue profiles |
| **Distribution handoff** | Phases 4–6 correctly human-gated — but agents should auto-prepare assets |

### 6. Parallel capacity under-specified

`parallel_peer_floor=48` but only **8/48** agent roles defined. Full product builds (UI + API + billing + deploy + docs) need disjoint niche peers, not one hero agent.

### 7. Human-only steps (by design)

`launch_paid_gate` (newsletter, paid ads) is RED tier. Product Hunt / Show HN require human post. Automation prepares; it does not replace distribution.

## Path to product E2E

```
Today:     hub queue → factory verify → kit artifact
Target:    registry repo → product queue → code verify → deploy proof → billing smoke → launch handoff
Keep:      peer orchestration, worktrees, template match, safety tiers
Add:       product ship gate, per-repo dispatch, deploy/billing verify, revenue repo bootstrap
```

## Improve goals (executable)

Tracked in `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` under **Product E2E**. Improve forever surfaces these via `_product_e2e_gaps()` in `automation_improve.py`.

## Related

- [LOOP_STRATEGY.md](LOOP_STRATEGY.md) — bank products/users before 2027 parity
- [AUTOMATION.md](AUTOMATION.md) — launch track, product_constraints
- [VALUE_STACK.md](VALUE_STACK.md) — launch peer owns Tier 3
- [IMPROVE_HORIZON.md](IMPROVE_HORIZON.md) — live factory vs product gap board
