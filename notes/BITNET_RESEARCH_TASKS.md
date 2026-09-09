# BitNet research tasks (DGX 1-bit / NVFP4 sidequest)

Plan: DGX 1-bit/FP4 sidequest (Cursor plan `dgx_1-bit_sidequest_05e1d3b8`).  
**This file is the sidequest task SoT in-repo** — compression research is **the same lane**, not a fork.

## Human locks (2026-09-06) — read first

| Lock | Rule |
|------|------|
| **Sidequest north star** | **1Q** (`10^15`) params @ **≤20GB** resident. Near map = **10T** ladder (2^8). Far map = shrink experts toward ~10M grain. |
| **Hot dtype** | **NVFP4 / FP4** GEMM. **1-bit = optional cold pack only.** |
| **Unique-param lane** | Still 1B logical → ~10M unique (\(S\approx100\)) inside MoE experts — does **not** replace 1Q/10T maps. See [`COMPRESSION_NORTH_STAR.md`](COMPRESSION_NORTH_STAR.md). |
| **First model** | **Working ~10M niche tester** (N01; N03/N08 stamps) — local eval/serve **now**. Needle `OVERSEER_FIRST_MODEL_10M_TEST_2026_09_06`. Do **not** wait for 10T/1Q/full MoE. |
| **MoE growth** | Compression **rung0+** / auto-train adds experts in **background** — parallel to 10M test. |
| **Local-only model** | **No public publish** of weights/endpoints/HF. Serve = CLEAN/local disk only. Needle `OVERSEER_MODEL_LOCAL_ONLY_2026_09_06`. Stress/integrate = **local kit workflow**, not internet release. |
| **First consumer** | **Automation factory** is the first product the local model accelerates (queue parse / stall / land-proof niches) — not “publish AI as OSS.” Needle `OVERSEER_FACTORY_FIRST_OSS_AUTOMATION_2026_09_06` (= first *local* consumer). Kit stays primary under `self_sufficient`. |
| **Honesty** | No GDS fast-path; no fake 10k single-stream decode KPI; 45d→10T = pacing not promise. |

### How to run the ~10M local tester (human)

```bash
# from repo root (Mac or CLEAN)
python3 scripts/niche_n01_practice.py --eval-only
python3 scripts/niche_n01_practice.py --serve '- [ ] **[kit] Example — scripts/peer_loop.py Needle: `OVERSEER_X`.'
# optional stamps
python3 scripts/niche_n03_practice.py --eval-only
python3 scripts/niche_n08_practice.py --eval-only
```

Pass: heldout acc ≥ 0.90. Checkpoints under `notes/niche_distill/practice_n0{1,3,8}/`.

**Gates:** [`COMPRESSION_TRAIN_READY.md`](COMPRESSION_TRAIN_READY.md) · recipe [`COMPRESSION_TRAIN_RECIPE.md`](COMPRESSION_TRAIN_RECIPE.md) · phases [`COMPRESSION_RESEARCH_PHASES.md`](COMPRESSION_RESEARCH_PHASES.md) · novels [`COMPRESSION_NOVEL.md`](COMPRESSION_NOVEL.md) · catalog [`COMPRESSION_CATALOG.md`](COMPRESSION_CATALOG.md) · speed [`RESEARCH_SPEED_TRAINING.md`](RESEARCH_SPEED_TRAINING.md) · arch [`BITNET_ARCH_RESEARCH.md`](BITNET_ARCH_RESEARCH.md) · ledger [`BITNET_FACTCHECK.md`](BITNET_FACTCHECK.md) · niches [`BITNET_NICHE_BANK.md`](BITNET_NICHE_BANK.md) · **ops** [`DGX_NVFP4_SIDE_QUEST_OPS.md`](DGX_NVFP4_SIDE_QUEST_OPS.md) · maps `compression_artifacts/near_map_ladder.json` + `far_map_1q.json`.

**Post-train (human lock):** full train → **all** stress bars PASS → **only then** **local** workflow integrate (`OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06`). Unlock ≠ integrate ≠ public release.

**Billing:** desktop login **$0** only (`force_free_desktop_auth`) — never Cursor API-key paid path.

## Protocol (every agent, every cycle)

1. `./scripts/peer hallucination-strategy` — write evidence / falsifier / verify block  
2. Read `notes/TEAM_CONTEXT.md` + `notes/HALLUCINATION_GUARD.md` + `notes/CRITICAL_THINKING.md`  
3. `./scripts/peer plan-gate` before first write  
4. Treat all pivotal `./scripts/peer` recipes in `notes/AGENT_COMMANDS.md` as required discipline  
5. Route hardware/speed/RAM claims through Fact Checker → `notes/BITNET_FACTCHECK.md`  
6. Append lane findings to `notes/BITNET_ARCH_RESEARCH.md` with sources  
7. `./scripts/peer done-gate` before marking queue item done  
8. Sync `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` if enqueue/checkoff  

## Compression census + north star (wave 1) — DONE

- [x] Lane C novels → `COMPRESSION_NOVEL.md` + T0–T4 packing-proof plan  
- [x] Lane B north-star math + stacks → catalog + fact-check **C139–C152**  
- [x] Lane A census → `COMPRESSION_CATALOG.md` A01–A58+  
- [x] Wave-14 spot-audit pristine  
- [x] T0 packing probe `compression_t0_pack.py` — `OVERSEER_COMPRESSION_T0_PACK_2026_09_05`  

## Research speed + pristine → train (wave 2) — DONE

- [x] TRAIN_READY gate filed; research pristine YES  
- [x] RESEARCH_SPEED_TRAINING S01–S32 + Lane U  
- [x] COMPRESSION_TRAIN_RECIPE **LOCKED**  
- [x] Wave-15 NVFP4 C153–C162 confirm  

## Compression T-series + auto-train (wave 3) — TRAIN LIVE ∥ 10M TEST FIRST

Parallel map: [`COMPRESSION_RESEARCH_PHASES.md`](COMPRESSION_RESEARCH_PHASES.md).

| Step | Status |
|------|--------|
| T1–T4 packing/scale | **Done** |
| Recipe LOCKED + unlock | **Done** |
| Auto-train rung0 | **GO** — keep systemd alive on CLEAN (MoE-add background) |
| T5 serve/residency | **Done** |
| T6 quality falsifiers | **Done** — C167–C169 proxy |
| Niche P0/P1 10M | **Done** — local tester green |
| Near-map 10T ladder | **Parked** — NO-GO until 10M stay green + T0 meters + RSS comfort; map documented |
| 1Q far map | **Horizon** — living map only |
| Stress bars → local integrate | **Armed** — after full train; never public publish |

Open work:

- [x] Recipe LOCK + T4 stamp + unlock  
- [x] Keep rung0 / compression-* systemd **active** on CLEAN (ops) — reconfirmed 2026-09-07 live during KD train  
- [x] After full train: fill `stress_bars.json` → **local** integrate only if all PASS — landed 2026-09-07 (`INTEGRATION_PROOF_COMPRESSION_RUNG0.md`; `north_star_1b_complete=false`)  
- [ ] Scale toward 1B→10M north-star (next rung; new C-rows on new meters)  
- [x] T5 / T6 / ablation schedule / niche P1  

## Niche-of-niches bank (~10M + composer)

Catalog: [`BITNET_NICHE_BANK.md`](BITNET_NICHE_BANK.md).

- [x] Distill schemas N01/N03/N08  
- [x] niche_composer prefer-order  
- [x] P0 practice N01 — local testable  
- [x] P1 N03+N08  
- [x] STRESS_GAPS G1–G7 + P1 section  
- [x] **First model 10M test lock** — `OVERSEER_FIRST_MODEL_10M_TEST_2026_09_06`  

## Plan-todo landings (sidequest ops)

- [x] Standing research + fact_checker cadence (prefer-order RESEARCH MODE)  
- [x] T0 CLEAN smoke meters (reconfirmed 2026-09-06)  
- [x] Factory wire policy: RSS≤20GB; NVMe→pinned UMA; no GDS (ARCH L7)  
- [x] improve-forever continuity (kit primary; sidequest secondary)  
- [x] Train fail-soft: park ladder, keep research (ARCH L8)  
- [x] Distill path: BitDistill+logit bank → NVFP4 student after LOCK  
- [x] Cache hotbank policy: embed/LM-head + hot FP4 tiles; cold pinned UMA  
- [x] Time gates: T0 GO(narrow); T1/45d NO-GO / pacing  
- [x] Near-map + 1Q maps documented; execution parked behind 10M tester  

## Fact-check waves (ledger)

- [x] Waves 0–15 + T6 C167–C169  
- [ ] When train emits new numbers: new C-rows before hypothesis→measured  

## Arch L-lanes

- [x] L2–L8 landed  

## Kit harness

- [x] T0 executable lane carve; CLEAN FP4 RSS smoke  
- [x] Compression probes + free desktop auth  
- [ ] CLEAN RAM headroom ops (ongoing)  
