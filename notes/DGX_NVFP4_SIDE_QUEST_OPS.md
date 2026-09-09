# DGX / NVFP4 sidequest — ops SoT (plan execution)

_Needle: `OVERSEER_DGX_NVFP4_SIDE_QUEST_OPS_2026_09_06`_  
**Do not edit** the Cursor plan file. This note implements plan locks in-repo.

## North star (locked)

| Layer | Target | Status |
|-------|--------|--------|
| **Horizon** | **1 quadrillion** (`10^15`) params @ **≤20GB** resident | Map only — not day-one train |
| **Near map** | 2^8 ladder R0 39B/64 → R8 **10T**/16384 / top-16 (~0.61B/expert) | Shape executable; calendar ≤45d = **pacing not promise** |
| **POC first** | One working **~10M** niche locally (test bar) while MoE/train adds experts | **Primary human test path** |
| **Unique-param lane** | 1B logical → ~10M unique @ **NVFP4** (\(S\approx100\)) | Compression train rung0 — same sidequest, not a fork |
| **Hot dtype** | **NVFP4 / FP4** GEMM | 1-bit = optional **cold** only |
| **Publish** | **LOCAL ONLY** — no public model upload / HF / public endpoint | `OVERSEER_MODEL_LOCAL_ONLY_2026_09_06` |

## First consumer (local)

**Automation factory** is the first **local** product the niche/~10M path serves (kit acceleration).  
**Not** “publish the AI as OSS online.” Needle: `OVERSEER_FACTORY_FIRST_OSS_AUTOMATION_LOCAL_2026_09_06`.

## Standing research (not a stop plan)

- Niches enrolled forever: `fact_checker`, `bitnet-research` / compression curator, efficiency/output researchers (Creative under self_sufficient as needed).
- Ledger: `BITNET_FACTCHECK.md` (C1–C162+).
- Arch map: `BITNET_ARCH_RESEARCH.md` L2–L8 living.
- Train may park; **research does not**. Improve-forever stays independent (kit primary).

## improve-forever continuity

Kit `factory_meter_mode=self_sufficient` stays **primary**. Sidequest T0 / compression is a carved Executable lane — **never pause** improve/peer for ladder theater. CLEAN: `improve-loop` + `peer-loop` active under Mac offload.

## Factory wire (CLEAN)

| Rule | Lock |
|------|------|
| Brain | CLEAN (Mac offloaded) |
| Hot RSS budget | ≤20GB UMA policy |
| Cold experts | NVMe → **pinned/host UMA** → C2C — **no GDS** (C4 FAIL) |
| Auth | desktop login **$0** only |

## Train fail-soft

If a train rung / compression rung fails: **park ladder scale**, resume kit development + standing research redrawing the map. Do not fake R8 green. Research agents keep writing next rung questions.

## Distill path (NVFP4 student)

After recipe **LOCKED** + T4 Done: BitDistill + teacher logit bank (`compression_t3_*`) → rung0 min-RAM NVFP4 student (`compression_train_rung0`). 1-bit cold optional later. ×2 ladder only after T0/T1 gates — not before POC 10M.

## Compression recipe LOCK

`COMPRESSION_TRAIN_RECIPE.md` **Status: LOCKED** — unlock auto-train / rung0. Stress→integrate policy: `compression_artifacts/stress_bars.json` — **local workflow integrate only** after all bars PASS (`OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06`).

## Near map scaffold

See `notes/compression_artifacts/near_map_ladder.json` — R0…R8 table. **Do not** start doubles until T1 GO.

## Far map → 1Q

After R8: shrink experts toward **~10M** default (optional 1M ultra-fine with high k). Living map in ARCH L5 + this ops note — redraw when hardware allows. Never break ≤20GB.

## Cache / hot bank

Priority: (1) embed + LM-head FP4 tiles in GPU L2, (2) leftover → far-map ≤10M winners, (3) near-map 0.61B via UMA stream — never whole-expert L2. Cold: pinned UMA only.

## Time gates

| Gate | Status |
|------|--------|
| T0 toy smoke CLEAN | **PASS** reconfirm 2026-09-06 — meters in ARCH |
| T0 ≤48h envelope | **Armed** for toy-only |
| T1 R0 / doubles | **NO-GO** until T0+C3–C7 comfort for scale |
| 45d → 10T | Pacing label only |
| 1Q | Horizon |

## Niche bank / first 10M test

| Stage | Status |
|-------|--------|
| P0 N01 practice | **Landed** — local test below |
| P1 N03/N08 | **Landed** |
| Stress gaps | `niche_distill/STRESS_GAPS.md` |
| Composer | `niche_composer` routes; claims → fact_checker |

### Local test (human) — first model

```bash
# On CLEAN (or Mac with synced notes/)
python3 scripts/niche_n01_practice.py --eval-only --json
python3 scripts/niche_n01_practice.py --serve '- [ ] **[kit] example** — Needle: `OVERSEER_X`.'
```

Needle: `OVERSEER_FIRST_MODEL_10M_TEST_2026_09_06`. MoE/expert growth continues via compression rung0 in parallel.

## Our trained model (not stock Ollama)

| Artifact | Path |
|----------|------|
| Neural sidequest student (~10M) | `scripts/niche_n01_neural_train.py` → `notes/niche_distill/practice_n01/weights/n01_queue_bullet_parse_neural.pt` |
| Knowledge corpus (locks in weights) | `notes/niche_distill/sidequest_knowledge.json` |
| Train status / loss | `practice_n01/train_status.json` · `train_log.jsonl` · dashboard **/train** |
| Rung0 real KD | `scripts/compression_train_rung0.py --train` → `compression_artifacts/rung0_student.pt` + `rung0_train_log.jsonl` |

**Borrowed chat** at `/chat` (llama3.2:1b Ollama) is **not** our trained artifact.

```bash
python3 scripts/niche_n01_neural_train.py --ask "What is the hot dtype?"
python3 scripts/niche_n01_neural_train.py --serve '- [ ] **[kit] … Needle: `OVERSEER_X`.'
```

## Factory niche improve (2026-09-07)

Needle: `OVERSEER_FACTORY_NICHE_RUNTIME_2026_09_07`

Wires the ~10M niche bank into peer_loop + dashboard as **closed-world specialists** (not a general LLM).

| Piece | Path / flag |
| --- | --- |
| Parallel route+serve | `scripts/factory_niche_runtime.py` · `route_and_serve` |
| Composer CLI | `scripts/niche_composer.py --serve "…"` |
| Note/SOP retrieval | `scripts/niche_retrieval.py --rebuild` → `notes/niche_distill/retrieval_index.json` |
| Cold NVFP4-ish pack | `scripts/niche_bank_compress.py` → `*.nvfp4.pt` + `bank_compress_status.json` |
| Heldout + live WQ eval | `scripts/niche_bank_eval.py` → `bank_eval_report.json` |
| T3 logit expand | `scripts/compression_logit_expand.py` → `t3_teacher_logit_bank_expanded.json` |
| Tiny LoRA-LM scaffold | `scripts/factory_lora_train.py --train` → `notes/factory_llm/` |
| Dashboard | `/niches` · `/api/niche-chat` — **AUTO** = full bank; N01/N03/N08 practice kept |
| Config | `factory_niche_assist` / `factory_niche_parallel` / `factory_niche_top_k` / `factory_niche_workers` |
| Factory dynamics | `scripts/factory_dynamics.py` · `/api/factory-dynamics` — live CPU/GPU `gpu_share`, adaptive top_k/workers/escalate floor |
| On-demand niche mint | `./scripts/peer niche-mint` · `scripts/niche_mint.py` — agents start a specialist when work reveals a closed-world speedup |

**peer_loop assist (fail-soft):** pre-dispatch (before plan-gate), verify FAIL, done-gate, stalls `git_clean_wait` / `noop_backoff` / `verify_cooldown`.

### On-demand niche mint (2026-09-07)

Needle: `OVERSEER_NICHE_MINT_ON_DEMAND_2026_09_07`

When an agent hits a **repeated closed-world** job the bank doesn't cover well:

```bash
./scripts/peer niche-mint --propose --name my_gap --io "log line → label" --reason "seen 5x in verify triage"
./scripts/peer niche-mint --start --name my_gap --io "log line → label" --reason "…" [--train] [--example "…"]
./scripts/peer niche-mint --suggest-from-assist   # from last escalate
./scripts/peer niche-mint --list
```

Guardrails: dedupe vs catalog, 1 mint/hour (unless `--force`), enqueue **Backlog** not Active flood, optional `--train`. Escalate paths write `mint_suggestion` into assist payload + `mint_suggestions.jsonl`. Catalog rows live in `notes/niche_distill/minted_catalog.json` (merged into `extra_niches`).

### Factory dynamics (2026-09-07)

Needle: `OVERSEER_FACTORY_DYNAMICS_2026_09_07`

Live **serve/routing/resource policy** (not continuous training, not TE):

| Knob | Source |
| --- | --- |
| Device pick | `pick_optimal_device` — CPU load vs `factory_niche_cpu_target_load`, CUDA util/VRAM floor |
| Balance | `gpu_share` ∈ [0,1] in `notes/niche_distill/factory_dynamics_state.json` (+ mirror `device_balance.json`) |
| Parallel assign | `assign_devices(n)` splits top-k across GPU/CPU |
| Adaptive assist | `adaptive_top_k` / `adaptive_cpu_workers` / `escalate_floor` after `observe_batch` |
| Serve path | `niche_bank_train.serve_one` — no hardcoded CPU; expert cache; `device` + `device_pick_reason` + `latency_ms` |
| Config | `factory_niche_device` (`auto`\|`balance`\|`cpu`\|`cuda`\|`mps`) · `factory_niche_balance` · `factory_niche_cpu_target_load` · `factory_niche_gpu_vram_floor_mb` · `factory_niche_serve_cache` |
| Dashboard | `GET /api/factory-dynamics` → `snapshot()` |

```bash
python3 scripts/factory_dynamics.py --snapshot
python3 scripts/factory_dynamics.py --pick
python3 -c "from factory_niche_runtime import route_and_serve; print(route_and_serve('parse WORK_QUEUE bullets')['dynamics'])"
```

### Honesty limits

- Niches ≠ LLM — structured labels/JSON from specialist experts + hash-token retrieval.
- Compression pack = **cold residency nibble pack** until real TE path; hot serve still float `.pt`.
- `factory_lora_train` = **tiny scaffold**, not a production instruct LLM (and not stock Ollama).
- Torch missing on a host → compress/LoRA/neural serve fail-soft; re-run on CLEAN/brain when torch exists.
- Dynamics = policy only — niches still closed-world specialists.

```bash
python3 scripts/niche_retrieval.py --rebuild
python3 scripts/niche_bank_compress.py --limit 20   # then full bank if fast
python3 scripts/niche_bank_eval.py
python3 scripts/compression_logit_expand.py
python3 scripts/factory_lora_train.py --train --steps 50
python3 scripts/niche_composer.py --serve "parse WORK_QUEUE unchecked bullets"
python3 scripts/niche_composer.py --serve "NVFP4 10k params claim fact check"
```

