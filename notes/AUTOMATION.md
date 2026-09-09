# Automation — self-improving peer loop

Scripts teach themselves via **`--self-check`** (teacher mode).

## Files

| File | Role |
|------|------|
| `scripts/project_automation.py` | Queue parsing, parallel metrics, cache, drift normalization |
| `scripts/automation_adapt.py` | Cross-project adapt/heal — detect stack, sync drift, install kit |
| `scripts/bundle_automation_kit.py` | Export `dist/automation-kit-*.tar.gz` |
| `scripts/factory_kit_run.py` | **A→Z compound** — adapt → verify → worktree (`.worktrees/kit-a-to-z`, dirty-main safe via `peer_worktree`) → PR or blocked receipt → proof writeback (`./scripts/peer kit-run --repo CPT --run`) |
| `scripts/peer_factory_a_to_z.py` | Sequencing-lock status / next open phase (`./scripts/peer a-to-z`) |
| `notes/FACTORY_A_TO_Z_PLAN.md` | Unsupervised kit-run plan (needle `OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07`) |
| `scripts/cursor_self_improve.py` | Build peer prompt; default saves to file (no clipboard/UI) |
| `scripts/peer_orchestrate.py` | Parallel peer plan, merge, self-check |
| `scripts/peer_worktree.py` | Git worktree list/add/remove + prompt hint; peer_loop inventories each continuous cycle — see `notes/AUTOMATION_TRENDS.md` |
| `scripts/run_peer_tasks.py` | Local-only verify/self-check (no LLM dispatch) |
| `scripts/peer_commands.py` | Agent command registry — compound recipes + `notes/AGENT_COMMANDS.md` |
| `scripts/peer_agent_comms.py` | GLink bus + vaults + **A2A task cards** (`build_a2a_task_card` / `a2a_task_card_from_glink`) |
| `notes/COMMS_TRENDS.md` | Comms research map — A2A **HAVE** + GLink→card AC (product contract) |
| `notes/AGENT_COMMANDS.md` | Pivotal `./scripts/peer` recipes for agents (generated) |
| `notes/AGENT_ERROR_PLAYBOOK.md` | Error symptom → instant fix; auto-updated by `peer_playbook.py` |
| `scripts/peer_playbook.py` | Playbook registry + lookup + cycle ingest |
| `scripts/self_improve_context.md` | Stop conditions + archive |
| `notes/WORK_QUEUE.md` | Peer-facing queue (keep in sync) — **Phase 0–6 launch track** |
| `notes/LOOP_STRATEGY.md` | **TIME BOMB + full strategy** — 2027 crown; ladder; keep vs drop; meta-exit |
| `LAUNCH.md` | Phased launch playbook; automation reads when queue source = `launch` |
| `MONETIZATION.md` | Pro pricing, $10k profile, customer-first |
| `notes/GAUGE_UI.md` | Setapp / CleanMyMac Gauge spec — Smart Reclaim, menu bar, motion |
| `notes/GAUGE_TASKS.md` | Gauge peer task breakdown (sync with WORK_QUEUE Phase 0.2) |
| `CONFIG.md` | Ship vs personal config layers |
| `notes/PEER_CONVERSATION.md` | **Entire conversation** — canonical summary for loop input |

## Commands

**Agents:** prefer `./scripts/peer <command>` — see **`notes/AGENT_COMMANDS.md`** for compound recipes (`bootstrap`, `heal-all`, `pre-dispatch`, `noop-break`, etc.). Ecosystem plan: **`notes/COMMAND_ECOSYSTEM_PLAN.md`**. Command Builder: `./scripts/peer commands-cycle`.

```bash
python3 scripts/peer_orchestrate.py --self-check    # teacher audit — run after edits
python3 scripts/automation_adapt.py --heal --write  # adapt to project + repair kit
python3 scripts/automation_adapt.py --audit         # self-audit script + all outputs
python3 scripts/automation_adapt.py --audit --audit-json  # machine-readable audit
python3 scripts/automation_improve.py --write             # plan → execute improve prompts
python3 scripts/automation_improve.py --forever          # signal→heal→enqueue→wake peer
python3 scripts/bundle_automation_kit.py --tar      # export portable kit
python3 scripts/peer_orchestrate.py --dry-run       # preview peer prompt
python3 scripts/peer_orchestrate.py --json            # machine plan
python3 scripts/run_peer_tasks.py                   # local-only verify tick
python3 scripts/cursor_self_improve.py --peer         # save prompt to file (default)
python3 scripts/cursor_self_improve.py --peer --forever   # foreground forever loop
python3 scripts/peer_loop.py --forever --background   # $0 default (terminal subprocess)
python3 scripts/peer_loop.py --install                # KeepAlive daemon (background default)
python3 scripts/peer_loop.py --watch                  # live terminal: WORKING vs IDLE
python3 scripts/peer_loop.py --status                 # one-shot snapshot
./scripts/peer-watch                                  # same as --watch
python3 scripts/peer_loop.py --once --clipboard-only  # opt-in: single dispatch to clipboard
python3 scripts/peer_loop.py --forever --cursor-ui    # opt-in: activate Cursor + inject
python3 scripts/peer_loop.py --forever --paid-api   # opt-in: CURSOR_API_KEY billing
python3 scripts/cursor_self_improve.py --quick        # cache tests/RSS until git changes
./scripts/peer-dispatch --forever
./scripts/peer-dispatch --dry-run
```

### Is it working or idle?

Background mode never shows up in Cursor chat. Use the terminal dashboard:

| Phase | Meaning |
|-------|---------|
| **WORKING** | `cursor-agent -p` is alive (or log just started a cycle) |
| **WAITING** | Mid-cycle / dirty tree / last verify FAIL |
| **VERIFYING** | Local verify commands running |
| **IDLE** | Daemon up, sleeping on kqueue (or noop backoff) |
| **STOPPED** | LaunchAgent not loaded |

Keys in `--watch`: `q` quit · `r` poke `peer-turn.signal` · space refresh.

### Remembrance / amnesia combat (`./scripts/peer`)

Needle `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07` · SOP `notes/SOP_AGENT_REMEMBRANCE.md` · checklist `notes/AGENT_AMNESIA_RESEARCH.md`.

| Verb | Purpose |
|------|---------|
| `fact-query` / `fact-domains` | Fact Librarian relay (+ domain SME scope); writes receipt |
| `domain-owners` | Regenerate `notes/DOMAIN_OWNERS.md` from `repo_domain_smes.json` |
| `memory-compress` / `memory-compress-verify` / `memory-pack-gate` | Lossless pack + deep verify + cheap heal/pre-dispatch gate |
| `role-state` | Thin role JSON: assignment / blocked / files / verify_cmd |
| `niche-domain-classify` | Heuristic domain classifier (model train Backlog) |
| `session-ledger-append` | Write-through decision → `notes/session_ledger/YYYY-MM-DD.jsonl` |
| `session-distill` | Cited bullets → `PEER_CONVERSATION` / last_cycle pins |
| `session-claim` | OVERCLAIM-style session facts → `session_ledger/claims/` |
| `session-sticky-status` / `session-hub-rules` | Spaced NO-PAY stickies · hub vs worktree scratch |
| `memory-audit` | Flag uncited claims vs pack/SoT (mechanical) |
| `memory-quiz` | Anti-amnesia SoT needle quiz |
| `memory-health` | Pack age / verify / prefer_librarian / Hot vs MEMORY_SPAN |
| `memory-episodic` | Thin episodic jsonl by `cycle_id` |
| `plan-gate --read-ack PATH` | Read-ack + librarian-receipt soft→require when prefer_librarian |

Dashboard: `http://127.0.0.1:8765/api/memory-health` · `/progress` · `/agents`.

### Intelligence gates (loop quality)

| Gate | Behavior |
|------|----------|
| Plan gate | `./scripts/peer plan-gate` — mechanical checks for 20 agent-vs-human gaps + strategy blocks (+ librarian receipt / read-ack) |
| Done gate | `./scripts/peer done-gate` — diagnose + output-compare before DONE |
| Agent layers | `peer_team_context`, `peer_hallucination_guard`, `peer_agent_human_gap`, `peer_idea_synthesis`, `peer_agent_gates`, `peer_precision_habits`, `peer_output_compare`, `peer_memory_span`, `peer_fact_librarian`, `peer_session_amnesia`, `peer_memory_auditor`, `peer_memory_quiz`, `peer_memory_health`, `peer_self_diagnose` |
| Hot path | `peer_loop` runs pre-dispatch (compact → plan-gate → check → ensure-pool) and post-cycle (done-gate) around verify |
| Template match | Backtick modules + specific keywords (`jetsam`, `attention`) beat bare `presence` → electron/chrome |
| Per-item guidance | Merged reclaim peers keep each item's scope + prompt |
| Last-cycle retrospect | Injected into next prompt from `peer-loop-state.json` |
| Post-agent verify | `run_verify_commands` before `ram install` / continuous spin |
| Auto-commit | After verify ok → **smart always-commit**: stage all commit-worthy paths (exclude local/weights/locks via `auto_commit_exclude_globs`), retry up to `auto_commit_max_passes`, then commit. Soft residual excludes OK under `continue_on_dirty`. Config: `auto_commit_after_verify` |
| Noop backoff | Same queue fingerprint after ok → 120s hold (no re-plan spin) |
| Continuous heartbeat | Queue open → kqueue wait ≤45s (event OR timeout) — keep working |
| Conversation truncate | Keeps **newest** turns under budget |
| Dirty-tree coding worktree (T10-08) | With `continue_on_dirty`, Dispatch clear stays **≥95%** while hub is dirty when `.worktrees/peer-coding` exists (`peer_worktree.coding_worktree_config`); healthy-idle Active → 100%. `peer_loop._resolve_coding_cwd` isolates agents onto the coding worktree. Proof: live meter + `tests.test_factory_progress.TestFactoryProgress.test_t10_08_dirty_hub_coding_wt_dispatch_ge_95` (needle `OVERSEER_T10_08_CODING_WT_DISPATCH_2026_09_07`). |

### Improve forever (`automation_improve.py --forever`)

Loop: **signal → filter self-targets → mechanical work-kit heal → hand out 8 roles → enqueue `WORK_QUEUE` → wake peer** via `peer-turn.signal`.

**Hard rule: improve does not improve itself.** It upgrades `peer_loop` / orchestrate / transcript / tasks / verify — **not** `automation_improve.py`, horizon cosmetics, or ASI board chrome. Horizon + prompts are **status output only**, not the improvement target.

#### ASI progress %

Horizon % uses the **phased ASI rubric** (`scripts/asi_rubric.py`, `notes/ASI_RUBRIC.md`):

```
pct = (completed phases + active phase partial) / 4 × 100
```

Phases 1–4 are completable (runtime-honest criteria). Phase 5 is asymptotic. True ASI is **not** declared done.

**Complete → plan next (autonomy):** Each improve cycle captures the previous `current_phase_id` from horizon JSON, then:

1. If a phase is **active** — enqueue a work-kit plan to finish it (deduped).
2. If the active phase **advanced** (previous ≠ current) — enqueue `Phase N complete → plan next` for the newly active section so the peer queue never stalls at “phase MET”.

Plans target peer_loop / verify / orchestrate / worktrees only — **improve does not improve itself**.

#### Live web UI

```bash
./scripts/peer dashboard           # foreground http://127.0.0.1:8765/
./scripts/peer dashboard-install   # KeepAlive LaunchAgent (reboot-safe)
./scripts/peer dashboard-status    # RUNNING / STOPPED
./scripts/peer dashboard-uninstall
# /horizon — over the horizon (NOW/NEXT/live log)
# /asi     — toward true ASI + milestones met
```

Polls `/api/snapshot` every 5s (fresh `compute_asi_progress` + horizon JSON + WORK_QUEUE Done). The live board shows a **timestamp** and **tasks completed** alongside progress. Log: `~/.config/{{PROJECT_NAME}}/dashboard.log`.

## Forever loop

Each cycle (until `## Loop: exhausted`):

**Default: background terminal** — no clipboard, no Cursor.app activation, no focus steal.

**Event-driven wake** (macOS kqueue — no poll timer):

1. Loop **blocks** on transcript dir + repo root (git) + `~/.config/{{PROJECT_NAME}}/peer-turn.signal` (touch to wake manually)
2. When Cursor chat writes `turn_ended` to agent transcript JSONL → dispatch next cycle (**continue_on_dirty:** dirty main does not stall — coding worktree or dirty-main fallback)
3. If `cursor-agent` desktop login works → run agent in background subprocess (`-p --force`)
4. Else → local-only keep-working: refresh peer + improve prompts, verify/self-check, re-adapt
5. **Continuous:** while queue has open work, kqueue wait uses a **heartbeat timeout** — wakes on event OR timeout and keeps cycling (no busy-spin; noop backoff still applies)
6. **Stall pivot (default 3s):** when blocked (noop backoff, verify cooldown, git wait), ask *what else can I do?* — local kit refresh + optional agent on alternate queue items; resume primary when unblocked (`stall_pivot_sec` in config)
7. Never pbcopy, never osascript into Cursor

Fallback: if kqueue unavailable (Linux/CI), sleeps **300s** between checks — no shorter poll.

```bash
touch ~/.config/{{PROJECT_NAME}}/peer-turn.signal   # manual wake
./scripts/peer-loop-run                              # foreground background loop
python3 scripts/peer_loop.py --forever --background
python3 scripts/peer_loop.py --install               # KeepAlive daemon (background default)
python3 scripts/peer_loop.py --install --clipboard-only  # opt-in: manual paste
python3 scripts/peer_loop.py --install --paid-api    # opt-in: CURSOR_API_KEY billing
```

**Opt-in modes:**

| Mode | Flag | Cost | Clipboard | Focus steal |
|------|------|------|-----------|-------------|
| Background terminal (default) | `--background` | $0 desktop or local-only | Never | Never |
| Parallel niche dispatch | `parallel_agent_dispatch` | $0 desktop | Never | Never — up to 8 simultaneous `cursor-agent` processes |
| Clipboard + transcript | `--from-transcript --clipboard-only` | $0 | Yes (pbcopy) | No |
| Direct UI inject | `--from-transcript --cursor-ui` | $0 desktop | Never | Yes |
| Terminal cursor-agent (API key) | `--paid-api` | **Bills API quota** | No | No |

**Do not use `CURSOR_API_KEY` unless you explicitly pass `--paid-api`.** Desktop login via `cursor-agent login` is preferred ($0).

**Per-role DGX prefer_remote:** Roles in `peer_tasks.json` may set `"prefer_remote": true` (optional `"host"`). Dispatch uses `peer_remote.should_dispatch_remote(prefer_remote=…)` — SSH when a host is resolvable (`agent_remote.ssh_host` / `dgx_host.ssh_host` / default `CLEAN`) even if committed `agent_remote.enabled` stays false. Set `ssh_host` in `automation.config.local.json` only; do not enable global remote in the committed config. `PEER_AGENT_LOCAL=1` forces local.

State: `~/.config/{{PROJECT_NAME}}/peer-loop-state.json` (last processed transcript line)

Signal: `~/.config/{{PROJECT_NAME}}/peer-turn.signal` (touch to wake blocked loop)

Log: `~/.config/{{PROJECT_NAME}}/peer-loop.log`

Prompt file (background fallback): `~/.config/{{PROJECT_NAME}}/next-peer-prompt.md`

## Task templates (`peer_tasks.json`)

| Key | Peer | When matched |
|-----|------|----------------|
| gauge_ia | launch | gauge ia, sidebar + smart reclaim |
| gauge_smart_reclaim | reclaim | gauge smart reclaim, bundled api |
| gauge_motion | launch | gauge motion, animation |
| gauge_menubar | launch | menu bar popover |
| gauge_settings | launch | gauge settings, presets |
| config_ship | verify | config ship, config.local |
| gauge_lazy | footprint | gauge, ui_api, snapshot |
| launchd_rss | footprint | launchd, ram once |
| reclaim_crash | reclaim | tlb, coalition imports |
| idle_attention | reclaim | idle, 999, attention |
| gauge_cleanup | reclaim | gauge cleanup |
| battery_defer | footprint | battery, defer |
| creative_presence | reclaim | presence, electron |
| creative_coalition | reclaim | coalition, duplicate mmap |
| creative_gpu | reclaim | gpu, metal, texture |
| creative_xpc | reclaim | xpc proxy |
| creative_launchd | footprint | launchd tick budget |
| git_hygiene | verify | commit, git dirty |
| automation_audit | verify | automation, self-check |
| kit_adapt | verify | adapt, heal, probe, local profile |
| kit_export | verify | export, bundle, tarball |
| kit_bootstrap | launch | bootstrap, import kit, install.sh |
| crown_time_bomb | launch | time bomb, crown-era, loop strategy, 2027 |
| factory_a_plus | implement | factory-a-plus, a+ plan, FACTORY_A_PLUS |
| external_proof_sprint | implement | external proof sprint, factory-proven, irreversible artifact |
| production_power_newdrop | implement | top10, production power, Newdrop merges, FACTORY_PROOF |
| top10_next | implement | TOP10_NEXT, top10_implementer, [top10-next] |
| demo_widget_sme | implement | Demo Widget SME, demo_widget, [demo-widget], demo_widget_sme |
| agent_builder | implement | Agent Builder, agent_builder, agent-builder, [agent-builder] |
| noop_break | implement | break noop loop, noop shrink |
| flaw_research | implement | flaw-research, repo defect land |
| pen_test | safety | pen-test, harden secrets/authz (defensive; no exploit PoCs) |
| progress_monitor | verify | progress-monitor, 24/7 monitor, always-on oversight |
| rule_shutdown_review | verify | rule-shutdown, RULE_SHUTDOWN_DIGEST, rule proposals |
| company_org | implement | company-org, staff missing roles |
| product_manager | launch | product manager, roadmap, acceptance criteria |
| design_ux | implement | design-ux, elegant statue, a11y |
| efficiency_research | footprint | efficiency-research, hot path, per-worker yield |
| fact_check | verify | fact-check, BITNET_FACTCHECK, claim ledger, OVERCLAIM |
| bitnet_research | footprint | bitnet-research, BITNET_ARCH, niche_distill |
| compression_train | footprint | compression-train, TRAIN_READY, T0–T4, BitDistill |
| compression_research | footprint | compression-research → bitnet_researcher lane |
| research_speed | footprint | research-speed, RESEARCH_SPEED_TRAINING, successive halving |
| output_research | implement | output-research, monster factory |
| registry_hub | implement | registry.json, repo audit |
| creative_loop | verify | automation loop / fresh chat |
| launch_newdrop | launch | newdrop, changelog |
| launch_pro_gauge | launch | gauge pro, menu bar |
| launch_billing | launch | stripe, paddle, billing |
| launch_landing | launch | landing, demo assets |
| launch_github | launch | repo public, release |
| launch_setapp | launch | setapp |
| launch_spike | launch | product hunt, show hn |
| launch_paid_gate | launch | newsletter, paid (RED — human only) |
| launch_ops | launch | refund, customer-first |

## Agent comms (GLink → A2A task cards)

Shared bus: `scripts/peer_agent_comms.py` · trends: `notes/COMMS_TRENDS.md` · horizon: `notes/COMMS_HORIZON.md`.

**A2A cards (landed, PROTOCOL=1):** map GLink `REQ`/`ACK`/`ASN` → structured task cards via `a2a_task_card_from_glink` / `build_a2a_task_card`. Required: `id`, `from`, `to`, `task`, `cid`. Field map (REQ→`st=req`/`task=need`; ACK→`st=ack`; ASN→`st=asn`) + PM AC in `notes/COMMS_TRENDS.md` § Agent2Agent. Open unacked REQs: `materialize_a2a_open_cards()`. Verify: `python3 -m unittest tests.test_peer_agent_comms.TestPeerAgentComms.test_a2a_task_card_from_req_ack_asn -q` (or full `tests.test_peer_agent_comms`). Product Manager owns AC in COMMS_TRENDS; Communications Engineer owns code — do not dual-edit `peer_agent_comms.py` from PM lane.

## Plan → peer tasks

When a plan doc is approved or updated (`notes/GAUGE_UI.md`, `LAUNCH.md`, `CONFIG.md`), agents **decompose it into WORK_QUEUE + self_improve_context** without asking the user to repeat. Rule: **`.cursor/rules/plan-to-peer-tasks.mdc`**.

| Plan | Breakdown doc |
|------|----------------|
| Gauge UI | `notes/GAUGE_TASKS.md` |
| Ship config | `CONFIG.md` |
| Launch | `notes/WORK_QUEUE.md` phases |
| Top 10 production power | `notes/TOP10_PRODUCTION_POWER_TASKS.md` |

After `peer_tasks.json` edits: `python3 scripts/peer_orchestrate.py --self-check`.

## Launch track (automation)

When `notes/WORK_QUEUE.md` has open **Phase 0–6** items, `open_work_items()` returns `source: launch`.

| Rule | Enforcement |
|------|-------------|
| Read `LAUNCH.md` + `MONETIZATION.md` + `notes/GAUGE_UI.md` + `CONFIG.md` | In peer brief + launch peer `reads` |
| Phase order | 0 ship before 4 spikes — in product_constraints |
| Phase 6 paid newsletters | `launch_paid_gate` RED tier — agents must not buy ads |
| Check off | Sync `WORK_QUEUE.md` ↔ `self_improve_context.md` Phase sections |
| Ship | `CHANGELOG.md` → Newdrop Publish |

## Teacher loop

1. Edit code or automation
2. `python3 scripts/peer_orchestrate.py --self-check`
3. `python3 -m unittest tests.test_automation -v`
4. Sync `WORK_QUEUE.md` ↔ `self_improve_context.md`
5. Log weakness in `notes/SELF_IMPROVE_RUBRIC.md` § Automation

## Defaults (speed × intelligence)

- **TIME BOMB + full strategy (early–mid 2027):** crown ends for top 5–15% parity — every cycle bank **product/users**; also stress ladder **speed → distribution → ecosystem**, keep queue/verify not daemon, **exit each loop** when table stakes; canonical: `notes/LOOP_STRATEGY.md` (whole file)
- **2+ open items** → peer mode (merged same-peer tasks)
- **Git dirty** → prepend commit hygiene peer
- **Tests + RSS** parallel; `--quick` caches until git fingerprint changes
- **Drift** compares normalized queue keys (ignores `([x] …)` parentheticals)
- **Stop (blocking)** when queue empty + tests pass + git clean + RSS <budget MB → `## Status: complete`
- **Stop (loop)** only when `## Loop: exhausted` in self_improve_context + metrics green
- **Peer loop** (`--peer`, default): **launch phases first** (if open) → clever → obvious queue → metrics → mine next clever
- **Priority:** LAUNCH.md Phase 0–3 before CREATIVE_RECLAIM when launch track active
- **Disable loop:** `--no-loop`

## Cache

`~/.config/{{PROJECT_NAME}}/automation_cache.json` (gitignored) — invalidated on git HEAD or porcelain change, not wall clock.

## Timers kept (time superior)

| Timer | Where | Why |
|-------|-------|-----|
| 300s fallback sleep | `peer_transcript` when no kqueue | No VNODE watch API off macOS |
| 45s continuous wake | `peer_loop` when queue has work | Timed kqueue wait — keep working without busy-spin |
| `--done-timeout-sec` (7200s) | `peer_loop` git-clean wait, `peer_terminal` agent subprocess | Safety net on hung agent / never-clean tree |
| subprocess timeouts | `ram install`, verify, `cursor-agent status` | Cannot event on external process completion |
