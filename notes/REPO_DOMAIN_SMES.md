# Repo domain SMEs — path ownership for remembrance

Needle: `OVERSEER_FACT_LIBRARIAN_2026_09_07`  
Machine map: `scripts/repo_domain_smes.json`

Main agent stays free of whole-repo load. Route facts through **Fact Librarian** scoped to a domain SME.

## Domains

| Domain id | Role | Owns (summary) |
|-----------|------|----------------|
| `agent_builder` | `agent_builder` | Agent Builder / task→worker |
| `peer_runtime` | factory_engineer | peer_loop, orchestrate, gates, worktrees |
| `memory_remembrance` | factory_engineer | memory pack, librarian, Always-read, DOMAIN_OWNERS |
| `queue_sync` | queue_steward | WORK_QUEUE ↔ self_improve_context |
| `verify_tests` | verify_runner | tests/, verify-gate |
| `adapt_heal` | adapt_specialist | adapt, self-heal, playbook |
| `comms_glink` | communications_engineer | GLink bus, vaults |
| `dashboard_ui` | frontend_engineer | dashboard/ |
| `safety_rules` | safety_auditor | SAFETY_GATES, RULE_*, .cursor/rules |
| `compression_bitnet` | compression_engineer | compression_*, niche_distill, BitNet |
| `dgx_ram` | dgx_ops | dgx_*, RAM/GPU |
| `docs_sops` | tech_writer | SOP_*, README |
| `oversight_progress` | progress_monitor | oversight, factory progress, debrief |

CODEOWNERS-like map (auto-gen): `notes/DOMAIN_OWNERS.md` — `./scripts/peer domain-owners --write`

## Invoke

```bash
./scripts/peer fact-query "noop plan-gate"                 # --auto domain
./scripts/peer fact-query --domain queue_sync "Active"
./scripts/peer fact-query --domain compression_bitnet "NVFP4"
./scripts/peer domain-owners --write
python3 scripts/peer_fact_librarian.py --list-domains
```

## SME spawn (optional)

Queue item matching `domain_sme` / `[domain-sme]` → niche reads **only** its globs + SoT (see `peer_tasks.json` template `domain_sme`).
