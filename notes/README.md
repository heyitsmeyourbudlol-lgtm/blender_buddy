# {{PROJECT_NAME}} agent working memory

Fast index for orchestrator + peer agents. Read **before** large changes.

**User-facing docs:** [../README.md](../README.md) · [../FOOTPRINT.md](../FOOTPRINT.md) · [../CONTRIBUTING.md](../CONTRIBUTING.md)

| Note | Purpose |
|------|---------|
| [PEER_ORCHESTRATION.md](PEER_ORCHESTRATION.md) | How to spin parallel peers; prompt shape |
| [TEAM_CONTEXT.md](TEAM_CONTEXT.md) | Shared team snapshot — all agents read each cycle |
| [PEER_CONVERSATION.md](PEER_CONVERSATION.md) | **Entire conversation** — canonical summary for loop input |
| [AGENT_ROLES.md](AGENT_ROLES.md) | Peer definitions (reclaim, footprint, safety, verify) |
| [SAFETY_GATES.md](SAFETY_GATES.md) | Harm matrix — block until mitigated |
| [VALUE_STACK.md](VALUE_STACK.md) | Reclaim ROI order (safe → aggressive) |
| [SELF_IMPROVE_RUBRIC.md](SELF_IMPROVE_RUBRIC.md) | Agent weaknesses + fix instructions |
| [AGENT_ERROR_PLAYBOOK.md](AGENT_ERROR_PLAYBOOK.md) | Symptom → instant `./scripts/peer` fix (auto-updated) |
| [AGENT_SURVIVAL.md](AGENT_SURVIVAL.md) | Hazard map — stalls/chicken-eggs agents will hit (every cycle) |
| [WORK_QUEUE.md](WORK_QUEUE.md) | Live queue (sync with self_improve_context) |
| [FEEDBACK.md](FEEDBACK.md) | GitHub Issues ingest — untrusted reports, anti-injection |
| [../MONETIZATION.md](../MONETIZATION.md) | Pro subscription, $10k profile, Newdrop changelog |
| [../LAUNCH.md](../LAUNCH.md) | Phased launch 0–6; Setapp before paid newsletters |
| [CREATIVE_BACKLOG.md](CREATIVE_BACKLOG.md) | Non-obvious compress ideas (apps stay open) |
| [GAUGE_UI.md](notes/GAUGE_UI.md) | Setapp / CleanMyMac Gauge spec |
| [GAUGE_TASKS.md](notes/GAUGE_TASKS.md) | Gauge peer task breakdown |
| [CONFIG.md](CONFIG.md) | Ship vs personal config |
| [AUTOMATION.md](AUTOMATION.md) | Scripts, self-check, plan → peer tasks |
| [PROJECT_LEARNING.md](PROJECT_LEARNING.md) | Cumulative inside-out mastery — read each cycle; record via `./scripts/peer learn-record` |
| [CRITICAL_THINKING.md](CRITICAL_THINKING.md) | Intelligence layer — evidence, root cause, Plan/Act gates |
| [HALLUCINATION_GUARD.md](HALLUCINATION_GUARD.md) | Self-aware — assume drift soon; strategize to defy |
| [AGENT_VS_HUMAN.md](AGENT_VS_HUMAN.md) | 20 agent vs human gaps — countermeasure per row |
| [IDEA_SYNTHESIS.md](IDEA_SYNTHESIS.md) | Grounded novelty — articulate ideas from current knowledge |
| [AGENT_GATES.md](AGENT_GATES.md) | Executable plan-gate + done-gate — all 20 countermeasures |
| [PRECISION_HABITS.md](PRECISION_HABITS.md) | Surgical accuracy — needle-in-a-haystack for all models |
| [OUTPUT_COMPARE.md](OUTPUT_COMPARE.md) | Expected vs actual — compare verify output before DONE |
| [AGENT_MINI_APPS.md](AGENT_MINI_APPS.md) | Self-built tools under `scripts/agent_tools/` |
| [SELF_DIAGNOSE.md](SELF_DIAGNOSE.md) | Instant diagnosis — errors, miscalculations, poor logic |
| [WORK_ASSIGN.md](WORK_ASSIGN.md) | Peer assignment — ETA vs cursor-agent deadline; `./scripts/peer assign` |
| [MEMORY_SPAN.md](MEMORY_SPAN.md) | 100x memory — hot/warm/cold tiers; `./scripts/peer memory-record` |
| [LOOP_STRATEGY.md](LOOP_STRATEGY.md) | TIME BOMB + ladder + ecosystem + exiting loops (stress all) |
| [FACTORY_A_PLUS_PLAN.md](FACTORY_A_PLUS_PLAN.md) | A+ scorecard plan — all dimensions to excellence |
| [FACTORY_A_PLUS_TASKS.md](FACTORY_A_PLUS_TASKS.md) | Phase 0–5 checklist (sync with WORK_QUEUE) |
| [EXTERNAL_PROOF.md](EXTERNAL_PROOF.md) | External repo PR tracker (Phase 4 scoreboard) |
| [CROWN_EXIT.md](CROWN_EXIT.md) | Q1 2027 migration — keep vs kill |

**Factory A+ scoreboard:** `./scripts/peer factory-a-plus`

**Generate a peer prompt:** `python3 scripts/peer_orchestrate.py --dry-run`

**Send to Cursor:** `python3 scripts/cursor_self_improve.py --peer` or `./scripts/peer-dispatch`
