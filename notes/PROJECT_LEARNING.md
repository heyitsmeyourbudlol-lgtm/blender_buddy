# Project learning — inside-out mastery

_Updated 2026-09-08 16:16:23_ · all agents read each cycle · record via `./scripts/peer learn-record`

**Learn as you work** — cumulative inside-out mastery (every cycle):

1. **Read before Plan** — `notes/PROJECT_LEARNING.md` + your niche notes in vault; never re-discover documented facts.
2. **Trace before edit** — follow imports/callers in your scope until you can explain the data flow in one paragraph.
3. **Record after work** — append ONE dated learning (non-obvious insight, trap, or file map) via `./scripts/peer learn-record`.
4. **Improve the kit** — mistake patterns → `notes/AGENT_ERROR_PLAYBOOK.md`; process wins → `notes/DEBRIEF_LOG.md` or SOP.
5. **Deepen over time** — each cycle you should know more of the repo than last cycle; teach the team in shared learnings.

## Inside-out map

- `scripts/peer_loop.py` (✓) — Forever driver — dispatch, verify gate, noop, worktrees
- `scripts/peer_orchestrate.py` (✓) — Orchestrator plan — phase gates, Task peer tasks
- `scripts/automation_improve.py` (✓) — Improve forever — horizon, enqueue, hand_out
- `scripts/automation_team.py` (✓) — Improve ↔ peer bridge — worker pool, team gaps
- `scripts/peer_team_context.py` (✓) — Shared brain — TEAM_CONTEXT, team-sync, cycle_id
- `scripts/peer_persona_rules.py` (✓) — Hardwired MUST/MUST NOT per niche
- `scripts/peer_agent_comms.py` (✓) — GLink bus + vaults + per-agent notes.jsonl
- `scripts/peer_critical_thinking.py` (✓) — Intelligence layer — evidence, root cause, Plan/Act gates
- `notes/CRITICAL_THINKING.md` (✓) — Critical thinking canon — read before Plan
- `scripts/peer_hallucination_guard.py` (✓) — Hallucination guard — self-aware strategy to defy drift
- `notes/HALLUCINATION_GUARD.md` (✓) — Assume hallucination soon — strategize before edit
- `scripts/peer_agent_human_gap.py` (✓) — Agent vs human — gap matrix + countermeasures
- `notes/AGENT_VS_HUMAN.md` (✓) — 20 agent weaknesses vs humans — kit fix per row
- `scripts/peer_idea_synthesis.py` (✓) — Grounded idea synthesis — novelty from current knowledge
- `notes/IDEA_SYNTHESIS.md` (✓) — Articulate new ideas with ≥2 anchors — not chat fantasy
- `scripts/peer_agent_gates.py` (✓) — Executable plan-gate + done-gate for all 20 gaps
- `notes/AGENT_GATES.md` (✓) — Run plan-gate before edit; done-gate before DONE
- `scripts/peer_precision_habits.py` (✓) — Precision habits — needle-in-a-haystack for all model tiers
- `notes/PRECISION_HABITS.md` (✓) — Surgical accuracy canon — read before first edit
- `scripts/peer_output_compare.py` (✓) — Expected vs actual output — discrepancy check before DONE
- `notes/OUTPUT_COMPARE.md` (✓) — Output compare canon — expected vs actual side-by-side
- `scripts/peer_agent_mini_apps.py` (✓) — Mini apps — self-built agent tools when repetition hurts
- `notes/AGENT_MINI_APPS.md` (✓) — Mini app charter — scaffold, test, register, promote
- `scripts/agent_tools/` (missing) — Directory for agent-built single-purpose scripts
- `scripts/peer_self_diagnose.py` (✓) — Self-diagnosis — errors, miscalculations, poor logic
- `notes/SELF_DIAGNOSE.md` (✓) — Diagnose canon — instant scan before Plan
- `notes/AGENT_SURVIVAL.md` (✓) — Hazard map — stalls, chicken-eggs, false labels (read every cycle)
- `scripts/peer_agent_survival.py` (✓) — Inject survival briefing into every persona prompt
- `notes/AGENT_ERROR_PLAYBOOK.md` (✓) — Symptom → mechanical fix catalog
- `scripts/peer_playbook.py` (✓) — Playbook match + sync AGENT_ERROR_PLAYBOOK.md
- `scripts/peer_work_assign.py` (✓) — Peer assignment — ETA vs cursor-agent deadline, GLink ASN
- `notes/WORK_ASSIGN.md` (✓) — Assignment canon — assign, eta, when=now|later|miss
- `scripts/peer_memory_span.py` (✓) — Memory span — 100x tiered external memory (hot/warm/cold)
- `notes/MEMORY_SPAN.md` (✓) — Memory canon — journal, retrieve, tier budgets
- `scripts/peer_lessons.py` (✓) — Lessons curator — harvest + lossless squeeze (facts_preserved)
- `scripts/peer_roles.py` (✓) — Job titles — assign_worker_pool, L-shards
- `scripts/peer_tasks.json` (✓) — agent_roles, templates, verify_commands
- `scripts/project_automation.py` (✓) — Config, live state, queue, factory_meter_mode
- `scripts/factory_progress.py` (✓) — Self-sufficient / external-proof readiness meter
- `scripts/peer_dual_research.py` (✓) — Efficiency + output research lanes
- `notes/TEAM_CONTEXT.md` (✓) — Live team snapshot — read every cycle
- `scripts/peer_agent_gates.py` (✓) — Plan-gate + done-gate — executable countermeasures
- `notes/AGENT_GATES.md` (✓) — Run plan-gate before edit; done-gate before DONE
- `scripts/peer_commands.py` (✓) — Agent CLI registry — compound recipes
- `scripts/peer_parallel_dispatch.py` (✓) — Parallel cursor-agent niche dispatch
- `scripts/peer_transcript.py` (✓) — Transcript → next prompt + last_cycle
- `scripts/cursor_self_improve.py` (✓) — Paste/dispatch bridge to orchestrator
- `scripts/peer_command_builder.py` (✓) — Command Builder agent prompt + digest
- `notes/WORK_QUEUE.md` (✓) — Executable queue (sync with self_improve_context)
- `notes/OPERATING_SYSTEM.md` (✓) — Debrief + flaw scan + optimization pillars
- `AGENTS.md` (✓) — Operator preferences and verify commands

## Recent team learnings

- **2026-09-08T13:26:24** `efficiency_researcher`: output-compare: match — L126 wake_peer probe metrics
- **2026-09-08T09:24:40** `verify_runner`: output-compare: match — two-run VGQ EXIT:0; first_fail=none; hub verify_ok=True; stale prompt FAIL stamp
- **2026-09-08T09:24:29** `verify_runner`: 2026-09-08 auto-repair type=tests: prompt Last Cycle FAIL[tests] stale vs hub peer-loop-state verify_ok=True continue_on_dirty; two-run VGQ EXIT:0 first_fail=none (self-check+16 suites); no code edit — do not ASN FE on soft/stale stamp alone · paths: `tests/test_automation.py, ~/.config/automation-hub/peer-loop-state.json`
- **2026-09-08T09:14:41** `verify_runner`: 2026-09-08 auto-repair type=tests: prompt last_cycle FAIL was stale; hub verify_ok=True agent_exit_soft rehydrated; VGQ EXIT:0 with deferred -9 on test_run_peer_tasks (DEFER!=FAIL); direct suites green auto=118 rpt=36; first_fail=none — do not ASN FE on soft-skip stamp alone · paths: `tests/test_automation.py, tests/test_run_peer_tasks.py, ~/.config/automation-hub/peer-loop-state.json`
- **2026-09-08T09:14:27** `verify_runner`: output-compare: match — auto-repair: type=tests stamp stale; VGQ deferred swarm DEFER!=FAIL; live suites green
- **2026-09-08T09:14:24** `verify_runner`: output-compare: discrepancy — two-run VGQ after pool_tip_skew FileNotFoundError fix
- **2026-09-08T09:14:11** `verify_runner`: 2026-09-08 type=tests first_fail tests/test_emit_inventory_ttl_list_skip.py:66 AssertionError registered — root=pool_tip_skew_report rev-parse FileNotFoundError on missing /tmp/peer-N cwd (OVERSEER_POOL_READY_FAIL_CLOSED_TIP); wrap run() in OSError/FileNotFoundError → unknown; two-run VGQ PASS · paths: `scripts/peer_worktree.py, tests/test_emit_inventory_ttl_list_skip.py`
- **2026-09-08T08:32:28** `verify_runner`: 2026-09-08 type=tests: first_fail was tests/test_peer_self_heal.py:415 AttributeError clear_dual_namespace_collision_cache — NOT soft-skip. Root=hub-protect vault SoT stale at 3272 lines (md5 3dcb779b); restore-hub-protect timer + verify beat-mac re-clobbered live HEAD 3848 after FE checkout. Fix=git checkout HEAD -- scripts/peer_self_heal.py AND cp live → all ~/.config/automation-hub/hub-protect*/peer_self_heal.py copies; post-sleep timer must keep 3848. Side: test_automation linux mtime already fixed concurrent. compact_land_proof deferred_poison flake when peer_transcript mid-edit.
- **2026-09-08T08:32:11** `verify_runner`: output-compare: match — two-run vgq pass
- **2026-09-08T08:31:56** `verify_runner`: 2026-09-08 two-run VGQ PASS after deferred_poison land_proof restored (_mark_flaw_research_landed OVERSEER_LAND_PROOF_DEFERRED_POISON); prior FAIL was missing deferred_poison branch returning False at fallthrough; self_heal mass FAIL was mid-write race not red tree
- **2026-09-08T08:30:20** `verify_runner`: 2026-09-08 VGQ first_fail tests/test_compact_land_proof.py:31 test_deferred_poison_scrub_on_load_proof_green AssertionError False is not true — _mark_flaw_research_landed._land_proof has no deferred_poison branch (falls through :137 return False); self_heal 17f/4e was mid-write race (symbols present after stable md5). ASN FE asn-1788870588
- **2026-09-08T06:46:39** `verify_runner`: 2026-09-08 auto-repair type=tests: first_fail tests/test_peer_self_heal.py:856 AttributeError progress_stalled — WT gutted peer_self_heal (~1141 lines vs HEAD); not soft-skip stamp. Fix=FE git checkout HEAD -- peer_self_heal + EXPECTED md5; re-verify EXIT:0 · paths: `tests/test_peer_self_heal.py, scripts/peer_self_heal.py`
- **2026-09-08T06:46:04** `factory_engineer`: peer_self_heal WT gut (~1141 LOC) → git checkout HEAD restores APIs; SCAN_ADAPT_FP_GEN_CACHE must store post-git-status index mtime or HIT always remisses (status refreshes index). · paths: `scripts/peer_self_heal.py, scripts/EXPECTED_peer_self_heal.py.md5`
- **2026-09-08T06:12:55** `dataset_curator`: P2-G8: green Cycle rc=0+verify=ok before adapt_stale substring; gen_all skip_existing=any primary+heldout; validate floors N01/N03/N08 only-rise
- **2026-09-08T06:12:48** `dataset_curator`: Live [top10] Soft residual twins (#66 then #82): gold scope is paths: docs/ops/… — never done= notes/INTEGRATION_PROOF_*; append-only JSONL; schema docs/+[top10] kit=false. N01 #82 +2 rows → corpus 60; heldout 12@1.0; schema 214/11872 bad=0. · paths: `notes/niche_distill/N01_queue_bullet_parse.jsonl, notes/niche_distill/STRESS_GAPS.md, notes/niche_distill/schema.md`
- **2026-09-08T06:12:31** `dataset_curator`: output-compare: discrepancy — 6 diff line(s); first change at hunk header or line mismatch.
- **2026-09-08T02:23:22** `product_manager`: output-compare: match — queue-open
- **2026-09-08T02:23:21** `product_manager`: output-compare: match — a2a-unittest-match
- **2026-09-08T00:48:56** `niche_distiller`: 2026-09-08: N03 twin prefer-order = earliest OVERSEER by document position (labeled Needle: is match shape not priority); labeled-first stole LAND_PROOF before KIT_RUN Needle. N08 improve LaunchAgent STOPPED → oversight_down before namespace_flip. · paths: `scripts/niche_n03_practice.py, scripts/niche_n08_practice.py, notes/niche_distill/STRESS_GAPS.md`
- **2026-09-08T00:47:54** `niche_distiller`: output-compare: match — Expected and actual match exactly.

## Niche mastery goals

### Adapt Specialist
- Master: automation_adapt probe/heal/audit + profiles/local.json fingerprint.
- Master: repos/registry.json status fields and should_re_adapt().

_Recent:_
- peer-4 self-heal: Linux critical daemon false-alarms from launchctl-only probe; use systemd peer-loop.service/improve-lo
- Deferred/offline-mac registry rows with no on-disk path must not hide Linux checkouts: _registry_factory_gaps skipped al
- output-compare: match — battery proof + lean hub verify · hits=2 · hits=2 · hits=2 · hits=2 · hits=2

### Command Builder
- Master: peer_commands COMMANDS + COMPOUND_STEPS registry pattern.
- Master: which shell loops in logs repeat → compound candidates.

_Recent:_
- Restored adapt-stale-clear=adapt→audit→adapt-confirm on hub after 4k-line peer_commands truncate; needle COMPOUND_STEPS+
- Wrapped compression_keep_alive.py --check as ./scripts/peer compression-keep-alive (pivotal). Coverage top gap; forever 
- output-compare: match — compression-keep-alive wrap

### Communications Engineer
- Master: GLink message types, vault summary caps, bus append hot path.
- Master: automation_comms_improve verify gate and encoding options.

_Recent:_
- 2026-09-07 CE: MCP REQ schema already hub-landed (mcp:<tool>); serialize ASN was NOTES ONLY — flip automation_comms_rese
- output-compare: match — ce:vault_omit
- output-compare: match — ce-mcp-doc HAVE+horizon

### Compression Engineer
- Master: measure_live_state RSS path + daemon memory in peer/improve loops.
- Master: test_cache_ttl, quick vs full measure tradeoffs.

_Recent:_
- output-compare: match — exact match after measure · hits=2 · hits=2 · hits=2 · hits=2 · hits=2
- output-compare: discrepancy — compression reclaim after sparse cold + unload · hits=2 · hits=2 · hits=2 · hits=2 · hits=
- peer_loop RSS blew to 65GB because cold memory hybrid retrieve loaded mamba-790m into the forever process; fix=retrieve(

### Debrief Optimizer
- Master: DEBRIEF_LOG + peer_debrief kinds (aar/knowledge).
- Learn: convert one debrief into playbook or executable queue item.

### Efficiency Researcher
- Master: probe_efficiency findings and EFFICIENCY_RESEARCH agent notes format.
- Master: pre-dispatch, wake interval, noop-break interactions.

_Recent:_
- output-compare: match — OVERSEER_TRANSCRIPT_PATHS_CACHE_2026_09_07 scandir
- find_latest cold miss: Path.iterdir+max 169ms → os.scandir+os.stat one-pass ~31.6ms (~5.3×) on 17751 UUID dirs; keep TTL
- output-compare: match — L126 wake_peer probe metrics

### Factory Engineer
- Master: peer_loop → orchestrate → parallel_dispatch dispatch path end-to-end.
- Master: worktree pool (peer_worktree), continue_on_dirty, post-agent verify.
- Learn: factory_progress dimensions — what moves self_sufficient %.

_Recent:_
- output-compare: match — deferred soft-skip port · hits=2 · hits=2 · hits=2 · hits=2 · hits=2
- Lock-held verify must return (-1,deferred) not (0,None): false verify_ok auto-commits and arms noop fp loops. Inject fai
- peer_self_heal WT gut (~1141 LOC) → git checkout HEAD restores APIs; SCAN_ADAPT_FP_GEN_CACHE must store post-git-status 

### Integration Architect
- Master: registry → adapt → worktree → native verify → proof artifact chain.
- Master: factory_meter_mode deferral of external proof in self_sufficient mode.

_Recent:_
- needle: dual-research-findings.json item 5cde9ba441123ba5 (status=enqueued) kept re-hand_out Newdrop needs-kit ASN after
- needle: live factory reads hub ROOT registry — peer-3 adapt-verified-dgx never cleared vault ASN; writeback hub status+p
- needle: hub queue_fp is peer_transcript.current_queue_fingerprint on Automation ROOT — worktree [x] on Newdrop never mov

### Lessons Curator
- Master: peer_lessons harvest → squeeze → promote; facts_preserved=true.
- Master: memory journal + PROJECT_LEARNING + playbook as SoT — no parallel stores.
- Learn: squeeze unique store (dedupe/fold); never prune distinct needles.

### Output Researcher
- Master: probe_output + OUTPUT_RESEARCH; RESEARCH_SYNC handoff rules.
- Master: registry ready vs gap repos — when to defer in self_sufficient mode.

_Recent:_
- Go sumdb h1 dirhash must hash FULL zip paths (module@version/...), not stripped paths — strip yields MISMATCH; go.mod al
- CyberActivity fifteenth: kit-run worktree from HEAD misses adapt untracked files — must commit kit onto wt before PR-wor
- output-compare: match — fifteenth CyberActivity MERGED

### Pen Test Researcher
- Master: peer_pen_test scan patterns + PEN_TEST agent notes — defensive harden only.
- Master: product-forge target preferred; never exploit PoCs.

### Queue Steward
- Master: open_work_items sources (launch vs context) and sync_queue_drift.
- Master: theater markers vs factory-shaped queue lines.

_Recent:_
- output-compare: match — Expected and actual match exactly.
- Hub SoT only: CREATIVE wrap compression-keep-alive was false-open after peer:226 + peer_commands PeerCommand landed; clo
- output-compare: match — QS cycle Staff twin + CREATIVE wrap close

### Safety Auditor
- Master: SAFETY_GATES.md tiers (green/yellow/red) and veto workflow.
- Master: flaw-scan scanner persona — 7 reviews per subject niche.

### Verify Runner
- Master: peer_tasks verify_commands + run_peer_tasks.py exit codes.
- Master: verify-gate-quick vs full unittest — when each runs.
- Learn: classify failures — test vs import vs lock vs timeout storm.

_Recent:_
- 2026-09-08 auto-repair type=tests: prompt last_cycle FAIL was stale; hub verify_ok=True agent_exit_soft rehydrated; VGQ 
- 2026-09-08 auto-repair type=tests: prompt Last Cycle FAIL[tests] stale vs hub peer-loop-state verify_ok=True continue_on
- output-compare: match — two-run VGQ EXIT:0; first_fail=none; hub verify_ok=True; stale prompt FAIL stamp

## Debrief peek

## 2026-09-01T10:56:21 — POSTMORTEM: Verify failure — unknown
## 2026-09-01T10:57:01 — POSTMORTEM: Verify failure — self-check
## 2026-09-01T11:07:27 — FLAW_TRIAGE: Flaw scan round 2026-09-01
- **Factory Engineer:** Auto ensure-pool when count < worker_target
- **Factory Engineer:** Run verify gate scoped to worktree cwd before merge
- **Factory Engineer:** Tag worktree slots with registry namespace for OSS handoff
- **Factory Engineer:** Yellow-tier safety gate before foreign-repo worktree add
- **Verify Runner:** Parallelize independent verify_commands with fail-fast
