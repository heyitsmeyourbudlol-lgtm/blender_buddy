# SOP index — standard operating procedures

Version-controlled via git. Update when debriefs lock in new best practices.

| SOP | Location | Owner niche |
|-----|----------|-------------|
| Peer orchestration | `notes/PEER_ORCHESTRATION.md` | Factory Engineer |
| Agent roles (8 workers) | `notes/AGENT_ROLES.md` | Orchestrator |
| Work queue sync | `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` | Queue Steward |
| Verify gate | `scripts/run_peer_tasks.py`, `peer_tasks.json` verify_commands | Verify Runner |
| Adapt / heal | `scripts/automation_adapt.py`, `IMPORT.md` | Adapt & Heal Specialist |
| Agent bootstrap / cold start | `./scripts/peer bootstrap` · `./scripts/peer heal-all` · `IMPORT.md` · `notes/SOP_DUAL_NAMESPACE_SELF_HEAL.md` | Adapt & Heal / Factory |
| External proof | `repos/registry.json`, worktree flow | OSS Integration Architect |
| Daily flaw scan | `scripts/peer_flaw_scan.py`, `notes/AGENT_ROLES.md` | All 8 scanners |
| Debriefs & AAR | `scripts/peer_debrief.py`, `notes/DEBRIEF_LOG.md` | Queue Steward |
| Agent error playbook | `notes/AGENT_ERROR_PLAYBOOK.md`, `scripts/peer_playbook.py` | Verify Runner |
| Factory KPIs | `scripts/factory_progress.py`, `/progress` | Queue Steward |
| Agent comms | `scripts/peer_agent_comms.py`, `automation_comms_improve` | Communications Engineer |
| Safety gates | `notes/SAFETY_GATES.md` | Safety Auditor |
| Kit export — no local secrets / weights | `scripts/automation_adapt.py` `_kit_export_tarinfo_filter` + `_kit_basename_is_weight` · `install_kit` skip · Needles `OVERSEER_KIT_EXPORT_NO_LOCAL_SECRETS_2026_09_05` · `OVERSEER_KIT_EXPORT_NO_WEIGHTS_2026_09_07` · `OVERSEER_KIT_INSTALL_NO_WEIGHTS_2026_09_07` · `OVERSEER_MODEL_LOCAL_ONLY_2026_09_06` · verify `python3 -m unittest tests.test_automation_adapt.AdaptExportTests` · see `notes/PEN_TEST.md` | Legal / Safety |
| Dual-namespace self-heal | `notes/SOP_DUAL_NAMESPACE_SELF_HEAL.md` · `notes/SOP_SELF_HEAL_SUCCESS_LOG.md` | Factory / Tech Writer |
| Rule-change proposals (add/remove/modify/suspend) | `notes/SOP_TEMPORARY_RULE_SHUTDOWN.md` · `notes/RULE_SHUTDOWN.md` · `notes/RULE_SHUTDOWN_DIGEST.md` · `notes/RULE_CATALOG.md` · `./scripts/peer rule-shutdown` · UI `/rules` | Progress Monitor / Tech Writer |
| Performance | `automation.config.json` cooldowns/cache | Compression Engineer |
| Compression north star (1B→10M@1-bit) | `notes/COMPRESSION_NORTH_STAR.md`, `COMPRESSION_CATALOG.md` | bitnet-research / fact_checker |
| Train readiness / research speed | `notes/COMPRESSION_TRAIN_READY.md`, `RESEARCH_SPEED_TRAINING.md` | fact_checker / efficiency |
| DGX roster / prefer_remote | `notes/DGX_ROSTER_EXPAND.md`, `ROLE_IMPORTANCE.md` | dgx_ops / parallel_dispatch_coach |
| Operating system map | `notes/OPERATING_SYSTEM.md` | Optimization Unit |
| Lossless memory compression (additive pack) | `notes/SOP_LOSSLESS_MEMORY_COMPRESSION.md` · `scripts/peer_memory_compress.py` · `notes/memory_artifacts/` · Needle `OVERSEER_LOSSLESS_MEMORY_COMPRESS_2026_09_07` | Factory / Tech Writer |
| Agent working memory (always-read index) | `notes/AGENT_WORKING_MEMORY.md` · Hot inject `peer_memory_span.format_always_read_block` | All agents |
| Agent remembrance + Fact Librarian + domain SMEs | `notes/SOP_AGENT_REMEMBRANCE.md` · `notes/REPO_DOMAIN_SMES.md` · `notes/DOMAIN_OWNERS.md` · `scripts/repo_domain_smes.json` · `scripts/peer_fact_librarian.py` · `./scripts/peer fact-query` · `domain-owners` · Needle `OVERSEER_FACT_LIBRARIAN_2026_09_07` | Factory / domain roles |
| Amnesia combat (ledger / receipt / owners / audit / quiz / health) | `notes/AGENT_AMNESIA_RESEARCH.md` · `scripts/peer_session_amnesia.py` · `peer_memory_auditor.py` · `peer_memory_quiz.py` · `peer_memory_health.py` · `notes/session_ledger/` · `./scripts/peer session-ledger-append` · `memory-audit` · `memory-quiz` · `memory-health` · Needle `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07` | Factory / claim_ledger_scribe |
| TOP10_NEXT durable implementer | `notes/TOP10_NEXT.md` · `notes/SOP_TOP10_NEXT.md` · role `top10_implementer` · `./scripts/peer top10` · `top10-refresh` · Needle `OVERSEER_TOP10_NEXT_2026_09_07` | top10_implementer |

| Queue compact (cap Active) | `./scripts/peer compact-queue` · efficiency research | Queue Steward / Progress |
| GLink / comms-verify | `./scripts/peer comms-verify` · `scripts/peer_agent_comms.py` · Needle `ph`/`cid`/`bref` | Communications Engineer |
| Idle gate (compound) | `./scripts/peer idle-gate` · `commands-sync` · `notes/COMMAND_BUILDER.md` | Command Builder |
| KPI digest | `notes/KPI_DIGEST.md` · `./scripts/peer progress` | Data Analyst |
| Release health | `notes/RELEASE_HEALTH.md` | SRE / QA |

_Wave-26 tech_writer restamp: idle-gate + KPI_DIGEST + RELEASE_HEALTH links present; no invent docs._
_Wave-27 tech_writer restamp (in-process): same links present; RELEASE_HEALTH wave-27 needle; no invent docs._
_Wave-28 tech_writer restamp (in-process): same links present; RELEASE_HEALTH wave-28 needle; KPI 99%/open=0; no invent docs._
_Wave-29 tech_writer restamp (in-process): same links present; RELEASE_HEALTH wave-29 needle; KPI 99%/open=0; no invent docs._
_Wave-30 remasure: RELEASE_HEALTH wave-30 needle; KPI 99%/open=0; Design/Growth/CS PASS skip; no invent docs._
_Wave-33 remasure (in-process Data Analyst/Tech Writer): RELEASE_HEALTH wave-33 needle; KPI 99%/open=0; peer caps 24→8; Finance PASS skip; no invent docs._
_Wave-35 remasure (in-process Data Analyst/Tech Writer): RELEASE_HEALTH wave-35 needle; KPI 98%/open=0; caps≤8; Finance PASS skip; no invent docs._
_Wave-37 remasure (Data Analyst/Tech Writer): RELEASE_HEALTH wave-37 needle; KPI 99%/open=0; Finance PASS skip; CB/Efficiency/Pen-test/Output skip_land; no invent docs._
_Wave-39 remasure (Data Analyst/Tech Writer): RELEASE_HEALTH wave-39 needle; KPI 98%/open=0; Finance PASS skip; CB/Efficiency/Pen-test/Output skip_land; no invent docs._
_Wave-40 remasure (in-process Data Analyst/Tech Writer): RELEASE_HEALTH wave-40 needle; KPI live 80%/KIT~99%/open=0; Finance PASS skip; Factory/Adapt/Comms skip_land; no invent docs._
_Wave-42 remasure (Data Analyst/Tech Writer): RELEASE_HEALTH wave-42 needle; KPI live 82%/open=0; Finance PASS skip; Queue/OSS/Compression skip_land; Adapt/heal + bootstrap SOPs still cite `./scripts/peer`; no invent docs._
_Wave-44 remasure (in-process Data Analyst/Tech Writer): RELEASE_HEALTH wave-44 needle; KPI live 99%/open=0; Finance PASS skip; Queue drift=0; OSS/Compression skip_land; Adapt/heal + bootstrap SOPs still cite `./scripts/peer`; no invent docs._
_Wave-45 remasure (Data Analyst/Tech Writer): RELEASE_HEALTH wave-45 needle; KPI live 98%/open=0; Finance PASS skip; Queue open-drift=0; OSS/Compression skip_land; Adapt/heal + bootstrap SOPs still cite `./scripts/peer`; no invent docs._
_Wave-53 remasure (Data Analyst/Tech Writer): RELEASE_HEALTH wave-53 needle; KPI live 82%/open=0; Finance PASS skip; Queue drift=0; OSS/Compression skip_land; Adapt/heal + bootstrap SOPs still cite `./scripts/peer`; no invent docs._
_Wave-51 remasure (Data Analyst/Tech Writer): RELEASE_HEALTH wave-51 needle; KPI live 99%/open=0; Finance PASS skip; Queue drift=0; OSS/Compression skip_land; Adapt/heal + bootstrap SOPs still cite `./scripts/peer`; no invent docs._

Cross-department clearinghouse: `notes/DEBRIEF_LOG.md` + `notes/CREATIVE_BACKLOG.md`.
