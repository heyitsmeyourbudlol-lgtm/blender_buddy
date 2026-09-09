# DOMAIN_OWNERS — path → Domain SME

_Auto-generated 2026-09-07 11:58:10 from `scripts/repo_domain_smes.json` — do not hand-edit; regenerate via `./scripts/peer domain-owners --write`._

Needle: `OVERSEER_FACT_LIBRARIAN_2026_09_07`

Fact Librarian routes `fact-query` using this map (same globs/SoT as the JSON). Main agent asks `./scripts/peer fact-query [--domain ID] "…"` — does not deep-read other domains.

## Domains

| Domain id | Role | Globs (summary) | SoT |
|-----------|------|-----------------|-----|
| `peer_runtime` | `factory_engineer` | `scripts/peer_*.py`, `scripts/peer`, `scripts/run_peer_tasks.py`, `scripts/cursor_self_improve.py` | `notes/AUTOMATION.md`, `notes/PEER_ORCHESTRATION.md`, `notes/AGENT_GATES.md` |
| `memory_remembrance` | `factory_engineer` | `scripts/peer_memory_*.py`, `scripts/peer_fact_librarian.py`, `scripts/peer_memory_compress.py`, `scripts/repo_domain_smes.json` (+8) | `notes/AGENT_WORKING_MEMORY.md`, `notes/SOP_AGENT_REMEMBRANCE.md`, `notes/MEMORY_SPAN.md` |
| `queue_sync` | `queue_steward` | `notes/WORK_QUEUE.md`, `scripts/self_improve_context.md`, `notes/WORK_ASSIGN.md`, `scripts/peer_work_assign.py` | `notes/WORK_QUEUE.md`, `scripts/self_improve_context.md` |
| `verify_tests` | `verify_runner` | `tests/**`, `scripts/run_peer_tasks.py`, `scripts/peer_self_diagnose.py`, `scripts/peer_output_compare.py` | `notes/OUTPUT_COMPARE.md`, `notes/AGENT_ERROR_PLAYBOOK.md` |
| `adapt_heal` | `adapt_specialist` | `scripts/automation_adapt.py`, `scripts/peer_self_heal.py`, `scripts/peer_playbook.py`, `scripts/peer_error_adapt.py` (+2) | `notes/AGENT_ERROR_PLAYBOOK.md`, `notes/AGENT_SURVIVAL.md`, `IMPORT.md` |
| `comms_glink` | `communications_engineer` | `scripts/peer_agent_comms.py`, `scripts/automation_comms_*.py`, `notes/COMMS_*.md`, `notes/agent_vaults/**` | `notes/COMMS_HORIZON.md`, `scripts/peer_agent_comms.py` |
| `dashboard_ui` | `frontend_engineer` | `dashboard/**`, `train.html`, `train.js` | `dashboard/server.py`, `notes/GAUGE_UI.md` |
| `safety_rules` | `safety_auditor` | `notes/SAFETY_GATES.md`, `notes/RULE_*.md`, `notes/PEN_TEST.md`, `scripts/peer_rule_shutdown.py` (+2) | `notes/SAFETY_GATES.md`, `notes/RULE_CATALOG.md`, `AGENTS.md` |
| `compression_bitnet` | `compression_engineer` | `scripts/compression_*.py`, `scripts/niche_*.py`, `scripts/factory_*.py`, `notes/COMPRESSION_*.md` (+5) | `notes/COMPRESSION_NORTH_STAR.md`, `notes/BITNET_RESEARCH_TASKS.md` |
| `dgx_ram` | `dgx_ops` | `scripts/dgx_*.py`, `scripts/dgx_*.sh`, `notes/DGX_*.md`, `dgx_speed.local.json` (+1) | `notes/DGX_ROSTER_EXPAND.md`, `ROLE_IMPORTANCE.md` |
| `docs_sops` | `tech_writer` | `notes/SOP_*.md`, `notes/SOP_INDEX.md`, `notes/README.md`, `README.md` (+2) | `notes/SOP_INDEX.md`, `notes/README.md` |
| `oversight_progress` | `progress_monitor` | `scripts/peer_oversight*.py`, `scripts/factory_progress.py`, `scripts/peer_debrief.py`, `notes/SYSTEM_OVERSIGHT.md` (+2) | `notes/SYSTEM_OVERSIGHT.md`, `notes/KIT_PROGRESS.md` |
| `agent_builder` | `agent_builder` | `scripts/peer_agent_builder.py`, `notes/SOP_AGENT_BUILDER.md`, `notes/agent_builder_specs/**`, `.cursor/rules/*_sme.mdc` | `notes/SOP_AGENT_BUILDER.md`, `scripts/peer_tasks.json` |

## CODEOWNERS-like rules

```
# path-pattern → domain_id (role_id)
# domain:peer_runtime role:factory_engineer
scripts/peer_*.py  @peer_runtime/factory_engineer
scripts/peer  @peer_runtime/factory_engineer
scripts/run_peer_tasks.py  @peer_runtime/factory_engineer
scripts/cursor_self_improve.py  @peer_runtime/factory_engineer
notes/AUTOMATION.md  @peer_runtime/factory_engineer
notes/PEER_ORCHESTRATION.md  @peer_runtime/factory_engineer
notes/AGENT_GATES.md  @peer_runtime/factory_engineer
AGENTS.md  @peer_runtime/factory_engineer

# domain:memory_remembrance role:factory_engineer
scripts/peer_memory_*.py  @memory_remembrance/factory_engineer
scripts/peer_fact_librarian.py  @memory_remembrance/factory_engineer
scripts/peer_memory_compress.py  @memory_remembrance/factory_engineer
scripts/repo_domain_smes.json  @memory_remembrance/factory_engineer
notes/memory_artifacts/**  @memory_remembrance/factory_engineer
notes/AGENT_WORKING_MEMORY.md  @memory_remembrance/factory_engineer
notes/MEMORY_SPAN.md  @memory_remembrance/factory_engineer
notes/SOP_AGENT_REMEMBRANCE.md  @memory_remembrance/factory_engineer
notes/SOP_LOSSLESS_MEMORY_COMPRESSION.md  @memory_remembrance/factory_engineer
notes/REPO_DOMAIN_SMES.md  @memory_remembrance/factory_engineer
notes/DOMAIN_OWNERS.md  @memory_remembrance/factory_engineer
notes/AGENT_AMNESIA_RESEARCH.md  @memory_remembrance/factory_engineer
notes/AGENT_WORKING_MEMORY.md  @memory_remembrance/factory_engineer
notes/SOP_AGENT_REMEMBRANCE.md  @memory_remembrance/factory_engineer
notes/MEMORY_SPAN.md  @memory_remembrance/factory_engineer
notes/DOMAIN_OWNERS.md  @memory_remembrance/factory_engineer

# domain:queue_sync role:queue_steward
notes/WORK_QUEUE.md  @queue_sync/queue_steward
scripts/self_improve_context.md  @queue_sync/queue_steward
notes/WORK_ASSIGN.md  @queue_sync/queue_steward
scripts/peer_work_assign.py  @queue_sync/queue_steward
notes/WORK_QUEUE.md  @queue_sync/queue_steward
scripts/self_improve_context.md  @queue_sync/queue_steward

# domain:verify_tests role:verify_runner
tests/**  @verify_tests/verify_runner
scripts/run_peer_tasks.py  @verify_tests/verify_runner
scripts/peer_self_diagnose.py  @verify_tests/verify_runner
scripts/peer_output_compare.py  @verify_tests/verify_runner
notes/OUTPUT_COMPARE.md  @verify_tests/verify_runner
notes/AGENT_ERROR_PLAYBOOK.md  @verify_tests/verify_runner

# domain:adapt_heal role:adapt_specialist
scripts/automation_adapt.py  @adapt_heal/adapt_specialist
scripts/peer_self_heal.py  @adapt_heal/adapt_specialist
scripts/peer_playbook.py  @adapt_heal/adapt_specialist
scripts/peer_error_adapt.py  @adapt_heal/adapt_specialist
notes/AGENT_ERROR_PLAYBOOK.md  @adapt_heal/adapt_specialist
notes/AGENT_SURVIVAL.md  @adapt_heal/adapt_specialist
notes/AGENT_ERROR_PLAYBOOK.md  @adapt_heal/adapt_specialist
notes/AGENT_SURVIVAL.md  @adapt_heal/adapt_specialist
IMPORT.md  @adapt_heal/adapt_specialist

# domain:comms_glink role:communications_engineer
scripts/peer_agent_comms.py  @comms_glink/communications_engineer
scripts/automation_comms_*.py  @comms_glink/communications_engineer
notes/COMMS_*.md  @comms_glink/communications_engineer
notes/agent_vaults/**  @comms_glink/communications_engineer
notes/COMMS_HORIZON.md  @comms_glink/communications_engineer
scripts/peer_agent_comms.py  @comms_glink/communications_engineer

# domain:dashboard_ui role:frontend_engineer
dashboard/**  @dashboard_ui/frontend_engineer
train.html  @dashboard_ui/frontend_engineer
train.js  @dashboard_ui/frontend_engineer
dashboard/server.py  @dashboard_ui/frontend_engineer
notes/GAUGE_UI.md  @dashboard_ui/frontend_engineer

# domain:safety_rules role:safety_auditor
notes/SAFETY_GATES.md  @safety_rules/safety_auditor
notes/RULE_*.md  @safety_rules/safety_auditor
notes/PEN_TEST.md  @safety_rules/safety_auditor
scripts/peer_rule_shutdown.py  @safety_rules/safety_auditor
scripts/peer_pen_test.py  @safety_rules/safety_auditor
.cursor/rules/**  @safety_rules/safety_auditor
notes/SAFETY_GATES.md  @safety_rules/safety_auditor
notes/RULE_CATALOG.md  @safety_rules/safety_auditor
AGENTS.md  @safety_rules/safety_auditor

# domain:compression_bitnet role:compression_engineer
scripts/compression_*.py  @compression_bitnet/compression_engineer
scripts/niche_*.py  @compression_bitnet/compression_engineer
scripts/factory_*.py  @compression_bitnet/compression_engineer
notes/COMPRESSION_*.md  @compression_bitnet/compression_engineer
notes/BITNET_*.md  @compression_bitnet/compression_engineer
notes/niche_distill/**  @compression_bitnet/compression_engineer
notes/compression_artifacts/**  @compression_bitnet/compression_engineer
COMPRESSION_*.md  @compression_bitnet/compression_engineer
BITNET_*.md  @compression_bitnet/compression_engineer
notes/COMPRESSION_NORTH_STAR.md  @compression_bitnet/compression_engineer
notes/BITNET_RESEARCH_TASKS.md  @compression_bitnet/compression_engineer

# domain:dgx_ram role:dgx_ops
scripts/dgx_*.py  @dgx_ram/dgx_ops
scripts/dgx_*.sh  @dgx_ram/dgx_ops
notes/DGX_*.md  @dgx_ram/dgx_ops
dgx_speed.local.json  @dgx_ram/dgx_ops
scripts/dgx_speed.local.json  @dgx_ram/dgx_ops
notes/DGX_ROSTER_EXPAND.md  @dgx_ram/dgx_ops
ROLE_IMPORTANCE.md  @dgx_ram/dgx_ops

# domain:docs_sops role:tech_writer
notes/SOP_*.md  @docs_sops/tech_writer
notes/SOP_INDEX.md  @docs_sops/tech_writer
notes/README.md  @docs_sops/tech_writer
README.md  @docs_sops/tech_writer
CONTRIBUTING.md  @docs_sops/tech_writer
notes/AUTOMATION.md  @docs_sops/tech_writer
notes/SOP_INDEX.md  @docs_sops/tech_writer
notes/README.md  @docs_sops/tech_writer

# domain:oversight_progress role:progress_monitor
scripts/peer_oversight*.py  @oversight_progress/progress_monitor
scripts/factory_progress.py  @oversight_progress/progress_monitor
scripts/peer_debrief.py  @oversight_progress/progress_monitor
notes/SYSTEM_OVERSIGHT.md  @oversight_progress/progress_monitor
notes/KIT_PROGRESS.md  @oversight_progress/progress_monitor
notes/DEBRIEF_LOG.md  @oversight_progress/progress_monitor
notes/SYSTEM_OVERSIGHT.md  @oversight_progress/progress_monitor
notes/KIT_PROGRESS.md  @oversight_progress/progress_monitor

# domain:agent_builder role:agent_builder
scripts/peer_agent_builder.py  @agent_builder/agent_builder
notes/SOP_AGENT_BUILDER.md  @agent_builder/agent_builder
notes/agent_builder_specs/**  @agent_builder/agent_builder
.cursor/rules/*_sme.mdc  @agent_builder/agent_builder
notes/SOP_AGENT_BUILDER.md  @agent_builder/agent_builder
scripts/peer_tasks.json  @agent_builder/agent_builder

```

## Invoke

```bash
./scripts/peer domain-owners --write   # refresh this file
./scripts/peer fact-domains
./scripts/peer fact-query "noop plan-gate"
./scripts/peer fact-query --domain queue_sync "Active"
```
