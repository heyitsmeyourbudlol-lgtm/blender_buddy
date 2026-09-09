# Niche-of-niches bank (~10M specialists)

**Plan:** `dgx_1-bit_sidequest_05e1d3b8` · **Grain:** ~**10M** each (easy; not the hard part)  
**Hard part:** one **replicable** distill → eval → serve → stress loop, then stamp it across niches.

**Composer:** `niche_composer` (giant) routes → niches → merge → escalate.  
**Stress:** research agents (efficiency / output / fact_checker / standing BitNet) **attack** shipped niches after each run — gaps → next train set.

## Priority lock (2026-09-06)

<!-- OVERSEER_FIRST_MODEL_10M_TEST_2026_09_06 -->
<!-- OVERSEER_MODEL_LOCAL_ONLY_2026_09_06 -->
<!-- OVERSEER_FACTORY_FIRST_OSS_AUTOMATION_2026_09_06 -->

| Lock | Meaning |
|------|---------|
| **P0 success** | **One working ~10M tester** (N01) runnable locally — eval + `--serve` for humans. N03/N08 are stamps of the same recipe. |
| **Local-only** | Weights/checkpoints stay on CLEAN/local disk. **No** HF push, public registry, or public endpoint. |
| **First consumer** | Niches accelerate the **Automation factory** (queue bullets, land-proof, stall class) — local kit use, not “publish the AI as OSS.” |
| **MoE background** | Compression rung0 / unique-param train grows MoE experts **in parallel**; does **not** block 10M test. |
| **Ladder theater** | 10T/1Q maps stay documented; execution parked until 10M stays green. |

**Human test commands:** see [`BITNET_RESEARCH_TASKS.md`](BITNET_RESEARCH_TASKS.md) § How to run the ~10M local tester.

---

## Locked loop (practice → replicate → stress)

```text
1 practice model (N01)
    → prove architecture (data schema, distill recipe, niche eval, serve hook)
2 stamp same recipe across development niches (catalog below)
3 research agents stress-test (heldout + live factory traces)
4 write gaps → notes/niche_distill/STRESS_GAPS.md → next run fixes
5 repeat
```

| Stage | What | Pass bar |
|-------|------|----------|
| **P0 Practice** | **One** ~10M model: **N01** `queue_bullet_parse` | Niche accuracy on heldout JSONL + live WORK_QUEUE sample; recipe documented so a peer can clone it — **landed 2026-09-04** `OVERSEER_NICHE_P0_PRACTICE_N01_2026_09_04` (RECIPE.md + practice_n01 ckpt; heldout 1.0) |
| **P1 Replicate** | Same recipe → remaining **development niches** (no redesign per niche) | Each niche ships only when eval ≥ bar; identical train/serve layout under `notes/niche_distill/` + model dir convention — **N03+N08 landed 2026-09-06** `OVERSEER_NICHE_P1_N03_N08_2026_09_06` |
| **P2 Stress** | Research agents + fact_checker probe failures, overclaim, miss rates | Gap file with falsifiers; queue fixes for next run — **not** silent `[x]` |

**Do not** mass-train all niches before P0 is green. **Do** keep the catalog wide — niches exist so development stays fast once the stamp works.

**First model local test (2026-09-06):** N01/N03/N08 heldout **1.0** on hub + CLEAN. Human path:

```bash
python3 scripts/niche_n01_practice.py --eval-only --json
python3 scripts/niche_n01_practice.py --serve '- [ ] **[kit] … Needle: `OVERSEER_X`.'
```

Needle `OVERSEER_FIRST_MODEL_10M_TEST_2026_09_06`. MoE/expert growth continues via compression rung0 in parallel. **Local only** — no public publish.

---

## Giant agent

| ID | Role | Does | Does not |
|----|------|------|----------|
| **niche_composer** | Router / merge | Pick 1..k shipped niches → merge → escalate | Re-solve niches; invent hardware numbers; skip ledger on numeric claims |

---

## Practice model (start here)

| ID | Niche | Why practice |
|----|-------|--------------|
| **N01** | `queue_bullet_parse` | Highest frequency; structured I/O; schemas already in `notes/niche_distill/N01_*.jsonl` (39 exemplars) |

**Next after P0 green (same recipe, no architecture churn):** N03 → N08 (schemas already landed) → then catalog order below.

---

## Development niche catalog (growing — stamp after P0; currently N01–N100)

Full list for **replication**, not “train tomorrow.” Research stress may **add/remove** rows each run.

### Factory dispatch

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N01 | `queue_bullet_parse` | line → {kit?, scope, needle} | compact / dispatch |
| N02 | `queue_kit_vs_research` | bullet → kit/research/creative/defer | demote / meter mode |
| N03 | `land_proof_needle_match` | item → needle / null | anti false-`[x]` |
| N04 | `active_empty_seed_pick` | empty Active → kit seed | kit-seed thrash |
| N05 | `done_gate_checklist` | diff+claim → allow `[x]`? | false done |
| N06 | `plan_gate_self_check` | plan blob → missing answers | plan-gate loops |
| N07 | `hallucination_block_fill` | task → Evidence/Hypothesis/Falsifier/Verify | strategy ritual |
| N08 | `stall_class_label` | status+log → stall class | stall-watch |
| N09 | `verify_fail_triage` | last_cycle → class | dirty-tree paint |
| N10 | `peer_log_skip_reason` | log → structured skip | improve debug |
| N11 | `launchagent_loaded_nopid` | launchctl → bootout/reinstall/ignore | peer_self_heal |
| N12 | `worktree_path_safe` | cwd → ok/collision | parallel peers |

### Fact / honesty

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N13 | `claim_row_extract` | prose → claim rows | fact_checker |
| N14 | `verdict_pass_fail_unknown` | claim+snippets → verdict | ledger |
| N15 | `overclaim_phrase_spot` | sentence → overclaim span | honesty |
| N16 | `gds_forbidden_scan` | code/docs → GDS hits | C4 lock |
| N17 | `meter_prompt_vs_writing` | JSON/log → meter split | anti brochure-10k |
| N18 | `rss_envelope_read` | smoke JSON → RSS Δ | T0 meters |
| N19 | `fp4_byte_arith` | N_params → FP4 bytes | L5 |
| N20 | `expert_grain_arith` | total,N,k → grain+active | ladder |
| N21 | `citation_url_shape` | URL → ok/junk | fact hygiene |
| N22 | `bitnet_upstream_issue_triage` | GH blurb → class | Darwin pins |

### CLEAN / serve

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N23 | `sm121_flag_spot` | build snippet → missing sm_121a? | FP4 builds |
| N24 | `uma_stream_plan` | expert size → l2/uma/nvme | no-GDS path |
| N25 | `moe_celebrity_score` | router hist → risk | load-spread |
| N26 | `mtp_gamma_sanity` | γ,τ,batch → shape OK? | Reading=Writing |
| N27 | `topk_active_budget` | size,k → active GB | ≤20GB |
| N28 | `ladder_rung_validate` | rung row → arith OK | R0–R8 |
| N29 | `clean_host_cmd_pick` | intent → exact cmd | CLEAN ops |
| N30 | `cuda_error_classify` | stderr → class | train/serve |

### Repo velocity

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N31 | `unittest_name_suggest` | behavior → test+needle | kit land-proof |
| N32 | `diff_risk_label` | files → risk bucket | review |
| N33 | `commit_msg_style` | diff → why-msg | ship |
| N34 | `pr_summary_bullets` | commits → PR body stubs | PR factory |
| N35 | `playbook_error_lookup` | error → playbook key | AGENT_ERROR_PLAYBOOK |
| N36 | `peer_command_suggest` | symptom → `./scripts/peer …` | AGENT_COMMANDS |
| N37 | `template_match_key` | title → peer_tasks key | orchestrate |
| N38 | `sync_wq_context_diff` | WQ vs context → drift | sync |
| N39 | `python_inline_import_spot` | patch → inline imports | team rule |
| N40 | `secret_leak_scan` | text → secret-shaped spans | safety |

### Map / research micro + glue

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N41 | `l2_cache_priority` | tensors → pin order | cache hierarchy |
| N42 | `near_vs_far_grain` | width → near/far bucket | map |
| N43 | `chinese_prior_tag` | model → leverage tag | L6 |
| N44 | `spec_paper_mech_tag` | abstract → Medusa/EAGLE/MTP/… | L3 |
| N45 | `quality_vs_serve_split` | text → serve vs quality gate | honesty |
| N46 | `poc_param_budget` | proposal → too fat / OK | anti-inflate |
| N47 | `distill_slice_spec` | niche ID → teacher prompt schema | data gen |
| N48 | `committee_merge` | k niche JSONs → one action | composer |

### Scalpels

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N49 | `json_only_extract` | dump → single JSON | parse thrash |
| N50 | `checkbox_flip_safe` | bullet+proof → allow `[x]`? | false land |
| N51 | `needle_mint` | title → OVERSEER_* candidate | kit twins |
| N52 | `status_box_compress` | peer status → 5-field snap | stall ticks |
| N53 | `creative_vs_executable` | item → demote/keep | meter mode |
| N54 | `t0_lane_exempt_spot` | item → T0-exempt? | ensure_t0 |
| N55 | `improve_opp_file_scope` | title → scripts/*.py or reject | kit-seed |
| N56 | `rss_cap_reject` | RSS proposal → reject if >20GB | hard gate |

### Wave G — Factory thrash / queue integrity (added 2026-09-04)

Pain from live stall-watch + P0 ensure fights.

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N57 | `false_checkbox_reject` | `[x]` line + land proof → keep / reopen | anti false-close |
| N58 | `p0_lane_protect` | queue edit → allow close P0? | RECIPE+ckpt gate |
| N59 | `open_done_dupe_exempt` | item → strip-open-done exempt? | compact thrash |
| N60 | `demote_note_scrub` | bullet → strip demoted theater | self_sufficient lies |
| N61 | `ensure_lane_needed` | Active snapshot → which ensure_* to run | peer_loop ticks |
| N62 | `continue_on_dirty_classify` | git status + config → wait / skip / HOLD paint | verify FAIL paint |
| N63 | `lean_green_hold_paint` | Cycle row → imply HOLD? | peer_watch |
| N64 | `kit_seed_fallback_pick` | known+landed → next peer-script seed | empty Active |
| N65 | `last_resort_stamp_seed` | exhausted fallbacks → stamped kit line | kit-seed skip |
| N66 | `queue_fingerprint_stall` | status snaps → stall class | overseer dispatch |
| N67 | `worktree_dispatch_dirty` | dirty tree → worktree vs hub | continue_on_dirty |
| N68 | `peer_turn_signal_poke` | symptom → touch peer-turn.signal? | wake daemon |
| N69 | `launchagent_label_resolve` | host → com.togi… label | heal/kickstart |
| N70 | `daemon_pid_alive` | label+pid → live / zombie / missing | peer_self_heal |
| N71 | `oversight_vs_peer_edit` | WQ diff author → overseer/peer/human | thrash debug |
| N72 | `land_needle_premature` | needle in README without artifact → pending | false land-proof |
| N73 | `jsonl_count_gate` | niche dir → enough exemplars? | distill done-gate |
| N74 | `heldout_split_ok` | train/heldout → leak? | eval honesty |
| N75 | `recipe_ckpt_path_parse` | RECIPE.md → ckpt path or missing | P0 land proof |
| N76 | `replicate_niche_scaffold` | niche_id → copy RECIPE layout paths | P1 stamp |
| N77 | `stress_gap_row` | miss class → STRESS_GAPS line | P2 loop |
| N78 | `composer_route_pick` | task → top-k niche IDs | niche_composer |
| N79 | `composer_escalate` | niche confidences → escalate to big model? | committee |
| N80 | `numeric_claim_divert` | sentence → fact_checker required? | honesty |

### Wave H — Broader factory / product velocity (added 2026-09-04)

| ID | Niche | In → Out | Helps |
|----|-------|----------|-------|
| N81 | `test_quick_fail_spot` | unittest stderr → failing test id | kit loops |
| N82 | `self_check_issue_parse` | self-check output → issue list | peer_orchestrate |
| N83 | `automation_config_key` | intent → automation.config.json key | config edits |
| N84 | `notes_vs_scripts_scope` | task → notes-only / scripts / both | peer scope |
| N85 | `phase_heading_normalize` | WQ heading → Active/Creative/Done/Backlog | compact |
| N86 | `remaining_work_sync_line` | Active bullet → context twin line | drift |
| N87 | `agent_role_strength_match` | queue title → agent_roles id | assign |
| N88 | `subagent_type_pick` | task → Task subagent_type | parallel peers |
| N89 | `max_parallel_peers_cap` | pool status → how many to launch | never solo |
| N90 | `plan_doc_decompose` | plan section → WQ `[ ]` bullets | plan-to-peer |
| N91 | `todo_merge_safe` | todo write → merge vs replace | TodoWrite |
| N92 | `secret_env_name_only` | text → redact to ENV_NAME | safety |
| N93 | `commit_scope_kit_vs_product` | diff → kit / BitNet / product | commit msg |
| N94 | `pr_test_plan_stub` | change type → test-plan checklist | PR factory |
| N95 | `dgx_vs_hub_path` | path → hub / CLEAN / wrong host | remote |
| N96 | `rss_smoke_json_validate` | smoke JSON → schema ok/fail | T0 meters |
| N97 | `gds_import_ban` | python file → forbidden import hits | C4 |
| N98 | `active_budget_tok_s_split` | log line → prompt vs Writing field | meters |
| N99 | `factory_meter_mode_read` | config → self_sufficient / external_proof | demote policy |
| N100 | `niche_bank_expand_propose` | stress gap → new N### niche draft | growing catalog |
| N106 | `verify_log_snippet_class` | verify log snippet → class | agent on-demand |
| N107 | `domain_classifier_train` | text → label | agent on-demand |

**Count:** **N01–N100** = **100** niches (+ `niche_composer`). Catalog grows when stress adds N101+.

**Neural bank stamp (2026-09-06):** N01 neural **DONE** (`practice_n01/checkpoint_neural.json`). Stamp/train N02–N105 via:

```bash
python3 scripts/niche_bank_train.py --train --all --epochs 12 --device cuda   # or cpu
python3 scripts/niche_bank_train.py --status
python3 scripts/niche_composer.py "verify fail dirty tree"
```

Needle `OVERSEER_NICHE_BANK_STAMP_TRAIN_2026_09_06`. Live board: dashboard `/train`.

---

## Research stress-test (after models exist)

**Owners:** efficiency_researcher, output_researcher, fact_checker, standing bitnet-research, niche_composer (triage only).

**Each run:**
1. Holdout JSONL + **live** factory traces (peer-loop.log, WORK_QUEUE, last_cycle).
2. Score niche accuracy; log miss classes.
3. Append `notes/niche_distill/STRESS_GAPS.md` — gap, falsifier, fix for next run.
4. Enqueue next-run fixes (data, recipe, or niche split) — do not inflate params to “feel smarter.”
5. If gap needs a **new** slice → propose **N101+** via N100 **or** agent on-demand mint:
   `./scripts/peer niche-mint --start --name <slug> --io "in → out" --reason "…"`  
   (dedupe + rate-limit; see `scripts/niche_mint.py` / Needle `OVERSEER_NICHE_MINT_ON_DEMAND_2026_09_07`).

**Success for architecture:** a new niche is mostly **copy recipe + new JSONL**, not a new training stack.

---

## Open work

- [x] Catalog + composer wire + N01/N03/N08 **schemas/traces**
- [x] **P0:** practice ~10M on **N01** (RECIPE + practice_n01 ckpt)
- [x] Expand catalog **56 → 100** (waves G–H factory thrash + velocity)
- [x] P0 green → replicate **N03, N08** with same recipe — `OVERSEER_NICHE_P1_N03_N08_2026_09_06`
- [x] Research stress harness → `STRESS_GAPS.md` after first model — landed 2026-09-05 (`notes/niche_distill/STRESS_GAPS.md`; G1–G7 fixed through 2026-09-06; heldout 9@1.0)
- [ ] Stamp remaining niches after recipe stable; grow past 100 when stress demands
