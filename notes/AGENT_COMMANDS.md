# Agent commands — pivotal repetitive tasks

_Generated from `scripts/peer_commands.py`. Prefer `./scripts/peer <id>` — agents should not reinvent these loops._

## Compound (run these first)

| Command | Description |
|---------|-------------|
| `bootstrap` | Cold start: install daemons → self-heal → compact → check → digest |
| `heal-all` | Full mechanical heal: self-heal → compact → sync → memory-pack-gate → verify gate |
| `green` | Health gate: check + progress + self-heal-scan (exit 1 if blocked) |
| `install-all` | Install peer + improve LaunchAgents |
| `pre-dispatch` | Before agent: compact → memory-pack-gate → plan-gate → check → ensure-pool |
| `post-cycle` | After agent cycle: verify → self-heal → digest |
| `standup` | Morning standup: digest → rule-shutdown-digest → improve-status → progress → self-heal-status |
| `noop-break` | Break noop: compact → poke → investigate-force |
| `stagnation-break` | Overseer stagnation: heal-all → noop-break → progress |
| `commands-sync` | After command edits: regenerate AGENT_COMMANDS.md → self-check |
| `commands-cycle` | Wake Command Builder: harvest gaps → write digest + agent prompt |
| `dev-fast` | Fast dev gate: compact → test-quick → check |
| `dev-heal` | Dev recovery: self-heal → commands-sync |
| `idle-gate` | Healthy-idle affirm: progress → compact-queue → pen-test-digest |
| `factory-a-plus-init` | Factory A+ scoreboard → install queue items → compact/sync |
| `compression-ladder` | T0–T6 compression probes as JSON (status ladder; no train/forever) |

## Pivotal one-shots

### adapt

- **`adapt`** — Quick adapt heal (cached verify)
  - `./scripts/peer adapt`
- **`adapt-all`** — Adapt every registry repo
  - `./scripts/peer adapt-all`

### agent

- **`plan-gate`** — Plan gate — all agent-vs-human countermeasures before edit
  - `./scripts/peer plan-gate`
- **`done-gate`** — Done gate — diagnose + compare before DONE
  - `./scripts/peer done-gate`
- **`diagnose`** — Self-diagnosis scan (errors, math, logic)
  - `./scripts/peer diagnose`
- **`diagnose-quick`** — Self-diagnosis quick (critical/high only)
  - `./scripts/peer diagnose-quick`
- **`hallucination-strategy`** — Print defy strategy template
  - `./scripts/peer hallucination-strategy`
- **`idea-articulate`** — Grounded idea template (≥2 anchors)
  - `./scripts/peer idea-articulate`
- **`check-questions`** — Plan/Done self-check questions
  - `./scripts/peer check-questions`
- **`output-compare`** — Expected vs actual output compare
  - `./scripts/peer output-compare`
- **`learn-record`** — Append team learning
  - `./scripts/peer learn-record`
- **`lessons`** — Lessons curator status (institutional memory)
  - `python3 scripts/peer_lessons.py --status`
- **`lessons-harvest`** — Mine logs/journals → fold lessons (no prune)
  - `python3 scripts/peer_lessons.py --harvest`
- **`lessons-squeeze`** — Lossless squeeze shared learnings (facts_preserved)
  - `python3 scripts/peer_lessons.py --squeeze --write`
- **`memory-record`** — Append memory journal fact
  - `./scripts/peer memory-record`
- **`memory-recall`** — Recall memory tiers
  - `./scripts/peer memory-recall`
- **`memory-compress`** — Lossless additive whole-repo memory pack (notes/memory_artifacts)
  - `python3 scripts/peer_memory_compress.py --compress`
- **`memory-compress-verify`** — Verify lossless memory pack round-trip (deep expand)
  - `python3 scripts/peer_memory_compress.py --verify`
- **`memory-pack-gate`** — Cheap pack integrity gate (heal/pre-dispatch; soft if no pack)
  - `(compound: )`
- **`role-state`** — Thin role state JSON (assignment/blocked/files/verify)
  - `./scripts/peer role-state`
- **`niche-domain-classify`** — Domain classifier — free-local NB checkpoint + keyword fallback
  - `./scripts/peer niche-domain-classify`
- **`memory-audit`** — Flag uncited worker claims vs pack/SoT (mechanical grep)
  - `python3 scripts/peer_memory_auditor.py`
- **`memory-quiz`** — Anti-amnesia SoT needle quiz (fail → heal hint)
  - `python3 scripts/peer_memory_quiz.py --self-check`
- **`memory-health`** — Pack age / verify / prefer_librarian / Hot vs MEMORY_SPAN
  - `python3 scripts/peer_memory_health.py`
- **`memory-episodic`** — Episodic jsonl by cycle_id (thin append/get/tail)
  - `python3 scripts/peer_memory_episodic.py`
- **`fact-query`** — Fact librarian relay (domain SME scoped)
  - `./scripts/peer fact-query`
- **`fact-domains`** — List repo domain SMEs
  - `./scripts/peer fact-domains`
- **`domain-owners`** — Regenerate notes/DOMAIN_OWNERS.md from repo_domain_smes.json
  - `./scripts/peer domain-owners`
- **`session-ledger-append`** — Write-through session ledger (decision/paths/needle before DONE)
  - `./scripts/peer session-ledger-append`
- **`session-distill`** — Turn-end cited bullets → PEER_CONVERSATION / last_cycle pins
  - `./scripts/peer session-distill`
- **`session-claim`** — Session claim ledger OVERCLAIM-style (session facts)
  - `./scripts/peer session-claim`
- **`eta`** — ETA vs session deadline
  - `./scripts/peer eta`
- **`team-context`** — Refresh TEAM_CONTEXT.md
  - `./scripts/peer team-context`
- **`agent-survival`** — Agent survival briefing compact prompt block
  - `python3 scripts/peer_agent_survival.py --compact`
- **`peer-error-adapt`** — Error adapt from plan-gate (never idle)
  - `python3 scripts/peer_error_adapt.py --from-gate`
- **`peer-glink-paste`** — GLink paste DONE shrink demo JSON (no paste)
  - `python3 scripts/peer_glink_paste.py done --demo --json`

### daemon

- **`comms-improve-install`** — Install comms-improve-loop LaunchAgent
  - `./scripts/peer comms-improve-install`
- **`install`** — Install peer-loop LaunchAgent
  - `./scripts/peer install`
- **`improve-install`** — Install improve-loop LaunchAgent
  - `./scripts/peer improve-install`

### factory

- **`progress`** — Factory readiness score (real outcomes)
  - `./scripts/peer progress`
- **`factory-a-plus`** — Factory A+ phase scoreboard
  - `python3 scripts/peer_factory_a_plus.py`
- **`a-to-z`** — Sequencing lock: next open A→Z factory kit phase
  - `python3 scripts/peer_factory_a_to_z.py`
- **`kit-run`** — Unsupervised kit compound: adapt → verify → worktree → PR/blocked → writeback
  - `python3 scripts/factory_kit_run.py`
- **`kit-heal-false-green`** — Force A→Z PROOF Status red when green lacks eligible PR/merge_note
  - `python3 scripts/factory_kit_run.py --heal-false-green`
- **`niche-mint`** — On-demand tiny niche: propose/start when agents find a local speedup (see niche_mint.py)
  - `python3 scripts/niche_mint.py`
- **`plan`** — Dry-run peer orchestration prompt
  - `./scripts/peer plan`
- **`factory-dynamics`** — Snapshot live niche CPU/GPU balance + assist knobs
  - `python3 scripts/factory_dynamics.py --snapshot`
- **`niche-bank-status`** — Niche bank train status / ready counts
  - `python3 scripts/niche_bank_train.py --status`
- **`niche-bank-eval`** — Niche bank heldout + live WORK_QUEUE smoke
  - `python3 scripts/niche_bank_eval.py`
- **`niche-assist-once`** — Dynamics + route/serve Active WORK_QUEUE head (fail-soft)
  - `python3 scripts/niche_assist_once.py`
- **`top10`** — Print ranked TOP10_NEXT implement-in-order list
  - `python3 scripts/peer_top10_next.py --list`
- **`top10-refresh`** — Mechanical TOP10_NEXT re-rank (open first, renumber, write-back)
  - `python3 scripts/peer_top10_next.py --refresh`
- **`top10-next`** — Print highest-rank open TOP10_NEXT item only
  - `python3 scripts/peer_top10_next.py --next`
- **`production-power`** — Refresh PRODUCTION_POWER_SCOREBOARD.md (honest bars; NO PAY)
  - `python3 scripts/production_power_scoreboard.py --write`
- **`agent-build`** — Agent Builder: provision role+template+match (pass --dry-run/--write/--spec after --)
  - `python3 scripts/peer_agent_builder.py`
- **`agent-who`** — Task→worker map: which role/template pick_role+match would select
  - `python3 scripts/peer_agent_builder.py --who`
- **`compression-keep-alive`** — Compression keep-alive acceptance JSON (--check; no fanout/forever)
  - `python3 scripts/compression_keep_alive.py --check`
- **`bitnet-fp4-expert-rss-smoke`** — CLEAN FP4 expert RSS/mmap smoke meters (--json)
  - `python3 scripts/bitnet_fp4_expert_rss_smoke.py --json`
- **`compression-ablation-schedule`** — OA/Hyperband ablation schedule dry-run (--json; no --write)
  - `python3 scripts/compression_ablation_schedule.py --json`
- **`compression-auto-train`** — Compression auto-train gate status (--check; no --start/--watch)
  - `python3 scripts/compression_auto_train.py --check`
- **`compression-gpu-worker`** — Compression GPU worker one cycle (--once; no --forever)
  - `python3 scripts/compression_gpu_worker.py --once`
- **`compression-logit-expand`** — Expand T3 teacher logit bank from peer/factory text
  - `python3 scripts/compression_logit_expand.py`
- **`compression-result-watch`** — Compression result stall watchdog one tick (--once; no --forever)
  - `python3 scripts/compression_result_watch.py --once`
- **`compression-stress-suite`** — Post-train stress bars JSON (--json; no --write)
  - `python3 scripts/compression_stress_suite.py --json`
- **`compression-t0-pack`** — T0 packing proof (--json)
  - `python3 scripts/compression_t0_pack.py --json`
- **`compression-t1-share`** — T1 share-factor ablation (--json)
  - `python3 scripts/compression_t1_share.py --json`
- **`compression-t2-svd`** — T2 SVD-TieStack probe (--json)
  - `python3 scripts/compression_t2_svd.py --json`
- **`compression-t3-bitdistill`** — T3 BitDistill logit-bank probe (--json)
  - `python3 scripts/compression_t3_bitdistill.py --json`
- **`compression-t4-scale`** — T4 scale U/N rung (--json)
  - `python3 scripts/compression_t4_scale.py --json`
- **`compression-t5-serve`** — T5 serve/residency smoke (--json)
  - `python3 scripts/compression_t5_serve.py --json`
- **`compression-t6-quality`** — T6 heldout quality toy (--json)
  - `python3 scripts/compression_t6_quality.py --json`
- **`compression-train-profile`** — DGX/CLEAN train profile-once meters (--json)
  - `python3 scripts/compression_train_profile.py --json`
- **`github-feedback-fetch`** — Pull sanitized GitHub feedback inbox (gh CLI)
  - `python3 scripts/github_feedback.py fetch`
- **`github-feedback-list`** — List sanitized GitHub feedback inbox
  - `python3 scripts/github_feedback.py list`
- **`github-feedback-render`** — Render untrusted GitHub feedback markdown for peer review
  - `python3 scripts/github_feedback.py render`
- **`production-power`** — Refresh notes/PRODUCTION_POWER_SCOREBOARD.md (--write)
  - `python3 scripts/production_power_scoreboard.py --write`
- **`scoreboard-write`** — Alias: refresh PRODUCTION_POWER_SCOREBOARD (--write)
  - `python3 scripts/production_power_scoreboard.py --write`
- **`niche-bank-compress`** — Compress niche-bank weights to NVFP4-ish packed sidecars
  - `python3 scripts/niche_bank_compress.py`
- **`niche-hot-path`** — Niche hot-path inventory JSON (N01 practice gate status)
  - `python3 scripts/niche_hot_path.py --inventory --json`
- **`factory-niche-runtime`** — Factory niche runtime route+serve snapshot (--json)
  - `python3 scripts/factory_niche_runtime.py --json`
- **`compression-train-rung0`** — Compression rung0 skeleton once (--once; no --train/--forever)
  - `python3 scripts/compression_train_rung0.py --once`
- **`gpu-profile-once`** — DGX util + CLEAN FP4 profile-once meters (--json)
  - `python3 scripts/gpu_profile_once.py --json`
- **`dgx-resource-priority`** — DGX RAM/GPU priority snapshot (--snapshot --json)
  - `python3 scripts/dgx_resource_priority.py --snapshot --json`
- **`niche-domain-classifier-train`** — Domain classifier heldout eval JSON (--eval-only; no --train)
  - `python3 scripts/niche_domain_classifier_train.py --eval-only --json`
- **`niche-n01-neural-train`** — N01 neural niche heldout eval JSON (no --train)
  - `python3 scripts/niche_n01_neural_train.py --eval-only --json`
- **`niche-n01-practice`** — N01 practice heldout eval JSON
  - `python3 scripts/niche_n01_practice.py --eval-only --json`
- **`niche-n02-practice`** — N02 practice heldout eval JSON (--eval-only; no train/corpus prune)
  - `python3 scripts/niche_n02_practice.py --eval-only --json`
- **`niche-distill-validate`** — Niche distill schema + anti-prune floor JSON (no row prune/train)
  - `python3 scripts/niche_distill_validate.py --json`
- **`research-claim-arith`** — Arith-only research stack prefilter cache check (--check-cache --json; no train/write)
  - `python3 scripts/research_claim_arith.py --check-cache --json`
- **`niche-n03-practice`** — N03 practice heldout eval JSON
  - `python3 scripts/niche_n03_practice.py --eval-only --json`
- **`niche-n07-practice`** — N07 practice heldout eval JSON
  - `python3 scripts/niche_n07_practice.py --eval-only --json`
- **`niche-n08-practice`** — N08 practice heldout eval JSON
  - `python3 scripts/niche_n08_practice.py --eval-only --json`
- **`niche-retrieval`** — Niche retrieval over bank index (query Active)
  - `python3 scripts/niche_retrieval.py Active`
- **`kit-progress`** — Kit progress JSON snapshot (no --write)
  - `python3 scripts/peer_kit_progress.py --json`

### health

- **`digest`** — Refresh notes/AUTOMATION_DIGEST.md (mechanical snapshot)
  - `./scripts/peer digest`
- **`oversight`** — Progress Monitor one cycle (24/7 niche)
  - `./scripts/peer oversight`
- **`oversight-force`** — Force Progress Monitor → cursor-agent
  - `./scripts/peer oversight-force`
- **`oversight-status`** — Progress Monitor daemon status
  - `./scripts/peer oversight-status`
- **`oversight-install`** — Install Progress Monitor forever LaunchAgent
  - `./scripts/peer oversight-install`
- **`progress-monitor`** — 24/7 Progress Monitor status
  - `./scripts/peer progress-monitor`
- **`progress-monitor-install`** — Ensure Progress Monitor LaunchAgent 24/7
  - `./scripts/peer progress-monitor-install`
- **`repo-research`** — Mechanical repo flaw probe + digest
  - `./scripts/peer repo-research`
- **`pen-test`** — Defensive pen-test scan + enqueue + optional harden agent
  - `./scripts/peer pen-test`
- **`dual-research`** — Efficiency + output research probe
  - `./scripts/peer dual-research`
- **`company-org`** — Company teams→roles gap audit + digest
  - `./scripts/peer company-org`
- **`investigate-force`** — Overseer now (ignore cooldown)
  - `./scripts/peer investigate-force`
- **`self-heal`** — Scan bottlenecks + apply mechanical heals
  - `./scripts/peer self-heal`
- **`rule-shutdown`** — Rule-change proposals (propose/ack/list/accept/reject) — human closes
  - `python3 scripts/peer_rule_shutdown.py`
- **`rule-shutdown-digest`** — Refresh notes/RULE_SHUTDOWN_DIGEST.md (daily human review)
  - `python3 scripts/peer_rule_shutdown.py write-digest`
- **`progress-watch`** — Time+result progress stall → self-heal run_cycle (once)
  - `python3 scripts/peer_progress_watch.py --once`
- **`playbook`** — Ingest errors + show instant fixes from live context
  - `./scripts/peer playbook`
- **`playbook-lookup`** — Match error text to playbook fixes
  - `./scripts/peer playbook-lookup`
- **`watch`** — Live peer-loop terminal dashboard
  - `./scripts/peer watch`

### improve

- **`comms-improve`** — Comms-kit one-shot: write plan+execute + research (local GLink/bus)
  - `python3 scripts/automation_comms_improve.py --write --research`
- **`comms-improve-status`** — Comms improve daemon + COMMS_HORIZON board
  - `./scripts/peer comms-improve-status`
- **`improve-write`** — Plan + execute + write + research (one shot)
  - `python3 scripts/automation_improve.py --write --research --plan --execute`
- **`improve-status`** — Improve daemon + horizon board
  - `./scripts/peer improve-status`
- **`trends`** — Refresh industry trends doc
  - `python3 scripts/automation_research.py --refresh --write`
- **`cursor-self-improve`** — Cursor self-improve suggestion dry-run (no paste/AX)
  - `python3 scripts/cursor_self_improve.py --dry-run`
- **`improve-poll-cache`** — Improve poll-cache launcher status (CLEAN overlay path)
  - `python3 scripts/run_improve_poll_cache.py --status`

### meta

- **`commands-build`** — Command Builder agent prompt (peer CLI recipes only)
  - `python3 scripts/peer_command_builder.py --prompt`
- **`commands-harvest`** — Harvest repeated shell loops → Command Builder gaps + prompt
  - `python3 scripts/peer_command_builder.py --harvest`
- **`command-coverage`** — Regenerate command coverage matrix + optional Backlog enqueue
  - `python3 scripts/command_ecosystem.py --write`
- **`coverage-gate`** — Fail-closed CLI wrap coverage (exit 1 if unwrapped gaps)
  - `python3 scripts/peer_commands.py inner coverage-gate`
- **`command-dispatch-audit`** — Audit pre-dispatch/post-cycle vs raw python3 scripts/ in logs
  - `python3 scripts/command_ecosystem.py --dispatch-audit`
- **`command-ecosystem-finish`** — Write coverage + dispatch audit + hub verbs + mini-app promote scan
  - `python3 scripts/command_ecosystem.py --finish`

### ops

- **`autonomous-repair`** — Mechanical repair pass (dedupe, cache, git)
  - `python3 scripts/peer_commands.py inner autonomous-repair`
- **`land-hold`** — Land-hold age/pause status
  - `python3 scripts/peer_land_hold.py`

### queue

- **`compact-queue`** — Strip adapt dupes, dedupe, cap Active to 12
  - `python3 scripts/peer_commands.py inner compact-queue`
- **`sync-queue`** — Heal WORK_QUEUE ↔ context drift
  - `python3 scripts/peer_commands.py inner sync-queue`

### ram

- **`dgx-gpu-compute`** — DGX GPU compute worker status JSON
  - `python3 scripts/dgx_gpu_compute.py --status --json`
- **`dgx-gpu-events`** — DGX GPU event mode snapshot JSON
  - `python3 scripts/dgx_gpu_events.py --snapshot --json`
- **`dgx-local-ram-guard`** — On-DGX RAM guard once (trim storms; no forever)
  - `python3 scripts/dgx_local_ram_guard.py --once`
- **`dgx-ram-events`** — DGX RAM event mode snapshot JSON
  - `python3 scripts/dgx_ram_events.py --snapshot --json`
- **`dgx-ram-priority`** — DGX RAM priority snapshot JSON
  - `python3 scripts/dgx_ram_priority.py --snapshot --json`
- **`dgx-utilization`** — DGX utilization snapshot JSON
  - `python3 scripts/dgx_utilization.py --snapshot --json`

### verify

- **`check`** — peer_orchestrate self-check (primary verify gate)
  - `./scripts/peer check`
- **`test`** — Full unittest discover -s tests
  - `python3 -m unittest discover -s tests -q`
- **`test-quick`** — Fast automation + worktree/constraints/grid/last_cycle_poison + agent_exit_soft + self_check_fail_ttl_soft tests
  - `python3 -m unittest tests.test_automation tests.test_run_peer_tasks tests.test_peer_worktree tests.test_peer_pen_test tests.test_peer_tasks_constraints tests.test_factory_grid tests.test_peer_last_cycle_poison tests.test_peer_self_heal tests.test_agent_exit_soft_land tests.test_self_check_fail_ttl_soft tests.test_overseer_stag_active_fp -q`
- **`verify-gate`** — Run configured verify_commands from config
  - `python3 scripts/run_peer_tasks.py`
- **`audit`** — Adapt self-audit (script + config + outputs)
  - `./scripts/peer audit`
- **`comms-verify`** — Comms kit self-test gate
  - `./scripts/peer comms-verify`

### worktree

- **`ensure-pool`** — Create parallel worktree pool
  - `./scripts/peer ensure-pool --count 8`

## Agent recipes

| When | Run |
|------|-----|
| Cold start / after reboot | `./scripts/peer bootstrap` |
| Before spawning cursor-agent | `./scripts/peer pre-dispatch` (includes memory-pack-gate + plan-gate) |
| Before first edit in session | `./scripts/peer plan-gate --role ROLE` |
| Before marking DONE | `./scripts/peer done-gate --expected "..." --actual "..."` |
| After agent cycle lands diff | `./scripts/peer post-cycle` (includes done-gate) |
| Noop / queue fingerprint stuck | `./scripts/peer noop-break` |
| Overseer stagnation dispatch | `./scripts/peer stagnation-break` |
| Daily standup / human update | `./scripts/peer standup` |
| Verify gate red | `./scripts/peer heal-all` then `./scripts/peer test-quick` |
| Pack integrity (cheap) | `./scripts/peer memory-pack-gate` (deep: `memory-compress-verify`) |
| Role assignment state | `./scripts/peer role-state list` / `set` |
| Full health check | `./scripts/peer green` |

## Meta

```bash
./scripts/peer commands-list
./scripts/peer commands-list --pivotal
python3 scripts/peer_commands.py run heal-all --dry-run
python3 scripts/peer_commands.py --write-md
```
