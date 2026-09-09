# TOP10_NEXT — ranked next 10 (implement in order)

_Canonical list for role **`top10_implementer`** · Needle `OVERSEER_TOP10_NEXT_2026_09_07`_  
SOP: [SOP_TOP10_NEXT.md](SOP_TOP10_NEXT.md) · Seeds: [AGENT_AMNESIA_RESEARCH.md](AGENT_AMNESIA_RESEARCH.md) · Factory bars: [TOP10_PRODUCTION_POWER.md](TOP10_PRODUCTION_POWER.md)

**Rules:** Implement highest-rank `status: open` first. When landed → mark `done` → `./scripts/peer top10-refresh`. Do **not** invent outside this list. **NO PAY.** Safe deletes = scratch/temp only (pack ≠ delete live SoT). Top10 Active Newdrop policy still applies for product lanes.

| Rank | Id | Title | Why | Acceptance | Status |
|-----:|----|-------|-----|------------|--------|
| 1 | T10-04 | Non-noop cycles ≥8 / day | Factory throughput gap (scoreboard) | Scoreboard week ≥8 non-noop cycles/day; CLEAN peer+improve up; Active nonempty | done |
| 2 | T10-10 | Mamba brain carve (P3) | Amnesia #19 deferred — larger DGX rerank | `MAMBA_SCALE_PLAN` carve with RAM cap; backends abstract; no paid API | done |
| 3 | T10-09 | Train tiny domain classifier niche | Heuristic stub only — lift heldout vs keyword | Free local niche checkpoint + infer in `niche_domain_classify`; NO PAY | done |
| 4 | T10-06 | Theater Active share ≤10% | Production-power bar — kit theater crowding | Scoreboard theater share ≤10%; compact demotes non-executable kit | done |
| 5 | T10-07 | CLEAN brain uptime ritual | Factory bar — brain flaps kill throughput | Mechanical check: CLEAN peer+improve active under mac-offloaded; meter credits CLEAN | done |
| 6 | T10-08 | Dirty-tree coding worktree path | Factory A+ phase2 — dirty hub caps Dispatch | Dispatch clear ≥95% with dirty main via coding worktree; doc in AUTOMATION.md | done |
| 7 | T10-01 | Pack-verify in heal / pre-dispatch | Amnesia P0 — CLI verify existed; compounds skipped | `heal-all` + `pre-dispatch` include `memory-pack-gate` (cheap integrity); deep expand stays `memory-compress-verify` | done |
| 8 | T10-02 | Role state schema | Amnesia #16 — shared assignment/blocked/files/verify_cmd | `scripts/peer_role_state.py` · `./scripts/peer role-state` · `notes/role_state/*.json` | done |
| 9 | T10-03 | Niche domain classifier (heuristic) | Amnesia #14 — librarian route keyword-only | `scripts/niche_domain_classify.py` hooked in fact relay; train niche = T10-09 | done |
| 10 | T10-05 | task_templates SoT for production_power | Match rules hit empty template — Newdrop prompt lost | `production_power_newdrop` under `task_templates`; dry-run match non-empty prompt | done |

## T10-10 progress (2026-09-08)

- **Landed:** Phase1 brain carve — `knowledge_mamba_budget_gb` (default 12) separate from agent `ram_max_used_gb`
- **Backends:** `scripts/knowledge_mamba_backends.py` — abstract `encode()`; live `transformers-fp16`/`cascade`/`hash`; stubs `gguf-llamacpp`/`vllm-nvfp4`/`precomputed`
- **Status:** `./scripts/peer mamba-status` reports backend + compression + budget_gb + agent cap
- **Config:** `mamba_backend` / `mamba_compression` / `mamba_teacher_model` / `knowledge_mamba_budget_gb`
- **Docs:** `notes/MAMBA_SCALE_PLAN.md` + `MAMBA_SCALE_TASKS.md` Phase1 [x]
- Needle: `OVERSEER_TOP10_NEXT_T10_10_2026_09_07`

## T10-09 progress (2026-09-08)

- **Landed:** free-local multinomial NB niche — `python3 scripts/niche_domain_classifier_train.py --train`
- **Checkpoint:** `notes/niche_distill/domain_classifier/checkpoint.json` · train/heldout JSONL beside it
- **Infer:** `niche_domain_classify.classify` uses model when checkpoint present (`source=model`); `--no-model` → keyword
- **Heldout lift:** model≈0.69 vs keyword≈0.13 (soft paraphrases); unittest `test_heldout_lift_vs_keyword`
- Needle: `OVERSEER_TOP10_NEXT_T10_09_2026_09_07`

## T10-04 progress (2026-09-08)

- **Meter landed:** `non_noop_by_day` rollup + flap-resistant sidecar `~/.config/automation-hub/non_noop_by_day.json` + thin-save max-merge (`OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07`). Excludes `local_only` soft-skip ticks.
- **Anti-flap landed:** bash `trap '' USR1` in free-desktop peer unit; `peer_loop` SIGUSR1→poke (no exit); `dgx_watch` skips peer restart when unit active (trim-only) + cooldown 3600s; CLEAN drop-ins `KillMode=process` (peer+improve) + `improve-loop` **enabled**; paid `--api-key` worker killed (NO PAY).
- **Verify-deferred cut (2026-09-08):** free-desktop saturate (`trim_agents_over_cap=false`) no longer forever-defers hub verify on `agents>2` — unittest/self-check still gate (`OVERSEER_T10_04_FREE_DESKTOP_VERIFY_QUIET_2026_09_08`). Heal CONT for job-stopped peer/improve (`STAT=T`) via `daemon_peer_job_stopped`.
- **Measured (scoreboard 04:45Z):** peer+improve **active**; Active nonempty; **9 today · proj 45.4/day · week_avg 9.0 [PASS]** — `meets_bar=true` (observed today≥8).
- **CLEAN reconcile (04:45Z):** durable sidecar lagged (side=2 vs hist=9) because Mac scoreboard rehydrates hist into a temp sidecar and never wrote CLEAN. Brain-path hist-rehydrate wrote `~/.config/automation-hub/non_noop_by_day.json` + live `non_noop_by_day` → **side=9 · live=9 · hist=9**. Close allowed only after CLEAN meter agreed ≥8.
- **Confirm (04:48Z):** SSH recheck CLEAN sidecar `by_day.2026-09-08=9` + live=9 + `meets_bar=true`; scoreboard restamp **9 today · proj ~45/day · week_avg 9.0 [PASS]**; Mac sidecar (~4) ignored; WQ↔SIC Active identical with T10-04 `[x]`.
- **Clear-deferred fix (2026-09-08):** `_clear_deferred_stamp_after_ready` mutates `last_cycle` in place — no `local_only` `record_cycle_outcome` overwrite (`OVERSEER_T10_04_CLEAR_DEFERRED_NO_LOCAL_ONLY_2026_09_08`). Root/hub shadow `run_peer_tasks.py` synced to CLEAN.
- **Status:** `done` · queue closed · `top10-refresh` open=0.
- **Promote gate (2026-09-08 ~05:04Z):** `top10-refresh` → open=0. No TOP10_NEXT GAP to Active. Backlog seeds (episodic→Hot / deep pack-verify) held — kit theater under production-power freeze. Kit fuel: eighteenth+nineteenth closed → twentieth Congressional App Challenge Active alongside Newdrop after tip. Do not reopen T10-04 on Mac-only meter while CLEAN SSH flaps.

## Commands

```bash
./scripts/peer top10              # print ranked list
./scripts/peer top10-next         # print #1 open item only
./scripts/peer top10-refresh      # mechanical: open first, renumber, write-back (run after a land)
./scripts/peer production-power   # restamp scoreboard (T10-04 meter)
./scripts/peer heal-all           # includes memory-pack-gate
./scripts/peer pre-dispatch       # includes memory-pack-gate
./scripts/peer role-state list
./scripts/peer niche-domain-classify "…"
python3 scripts/production_power_scoreboard.py --write
```

## Dispatch

Queue: **`[top10] … TOP10_NEXT …`** → template **`top10_next`** (priority 0) → role **`top10_implementer`**.  
Bare `[top10]` Newdrop lines (no `TOP10_NEXT`) → **`production_power_newdrop`**.

## Backlog seeds (not invent — already listed above as open / done)

- Episodic → Hot cascade (thin) — promote only if an open slot frees after refresh
- Full deep `memory-compress-verify` hard-fail in heal — optional strict mode later
