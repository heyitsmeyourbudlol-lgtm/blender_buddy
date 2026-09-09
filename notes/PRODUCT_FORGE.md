# Product forge — autonomous strong applications

When you need a **real app**, not hub kit polish, activate **product forge**. It runs agents in the **product repo** (vibe-scale: 1–2 agents, vertical slices), like your CaaS weekend — wired into `product_drive` + `peer_loop` cwd.

## Start

```bash
# Greenfield (creates ~/Projects/my-app, installs kit, seeds [forge] queue)
./scripts/peer product-forge --start "Newdrop-style changelog SaaS" --profile caas --name my-app

# Existing repo (CaaS, CPT, …)
./scripts/peer product-forge --start "Ship billing fix" --path ~/CaaS --no-bootstrap

./scripts/peer product-forge --status
./scripts/peer product-forge --stop
```

## What it does

1. **Bootstrap** — `git init`, `automation_adapt` kit install, profile (`caas`, `node`, …)
2. **Product queue** — `notes/WORK_QUEUE.md` **on the product repo** with `[forge]` slices (scaffold → UX → API → deploy)
3. **Dispatch** — cursor-agent with `cwd=product`, not Automation hub
4. **Loop** — while active, `product_drive` + dirty `peer_loop` prefer product cwd
5. **Hub marker** — `[product-forge] Active` on hub queue so improve wakes peer

## Config (`automation.config.json`)

```json
"product_forge": {
  "enabled": true,
  "default_profile": "caas",
  "greenfield_parent": "~/Projects",
  "max_agents": 4,
  "suppress_hub_enqueue_while_active": true
}
```

## vs hub factory

| Hub factory (default) | Product forge |
|----------------------|---------------|
| Self-heal, oversight, 11 roles | 1–2 agents, product queue |
| Verify = hub self-check | Native npm/pytest on product |
| Optimizes Automation alive | Optimizes **strong application** |

## Related

- [PRODUCT_E2E_GAPS.md](PRODUCT_E2E_GAPS.md) — remaining deploy/billing gates
- [profiles/caas.json](../profiles/caas.json) — Newdrop constraints
- `./scripts/peer product` — product_drive tick (includes forge when active)
