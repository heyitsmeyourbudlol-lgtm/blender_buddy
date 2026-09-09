# Compression → train readiness (pristine gate)

_Needle: `OVERSEER_COMPRESSION_TRAIN_READY_2026_09_05`_  
**Rule:** Do **not** start real model training (1B-scale / quality train rungs beyond packing probes) until this gate is green **and** recipe is LOCKED. T0 packing alone ≠ permission to train.

## North star (locked)

[`COMPRESSION_NORTH_STAR.md`](COMPRESSION_NORTH_STAR.md) — 1B logical → 10M unique @ **same 1-bit** (\(S\approx100\)). No data prune. Distill OK. SSD/Zamba ≠ bytes.

## Wave-1 research status

| Lane | Artifact | Pristine? |
|------|----------|-----------|
| A — Method census | `COMPRESSION_CATALOG.md` A01–A58 | **Done** — top-5 spot-checked 2026-09-05 (footnotes; no row deletes) |
| B — Math / stacks | Lane B + `BITNET_FACTCHECK` C139–C152 | **Arith pristine** (C142 label fixed) — quality UNKNOWN |
| C — Hypotheses | `COMPRESSION_NOVEL.md` | **Hypothesis-labeled**; T0 packing measured (quality N/A) |
| Fact-check wave-14 | C139–C152 | **Spot-audit PASS** — `BITNET_FACTCHECK.md` § Wave-14 pristine audit |
| **T0 packing proof** | `scripts/compression_t0_pack.py` + unittest | **PASS** 2026-09-05 (quality N/A) · pack-cache Lane U sibling `OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05` → `notes/compression_artifacts/t0_pack_report.json` (**not** train unlock) |
| **Dual SoT (pack+logit)** | `compression_t0_pack.py --ensure-dual-sot` / `--dual-sot-check` / `--check-dual-sot-report` / `--probe-keep-alive` / `--check-probe-report` / `--heal-lane-u-sot` | **PASS** 2026-09-08T13:13Z Lane-U post-unittest heal (`OVERSEER_COMPRESSION_LANE_U_SOT_HEAL_2026_09_08` — `--heal-lane-u-sot` = Dual SoT+probe stamp-refresh; clears sticky `ram_soft_skip` after soft-skip tests; falsifier `test_heal_lane_u_sot_clears_sticky_soft`) + Dual SoT stamp-refresh (`OVERSEER_COMPRESSION_DUAL_SOT_STAMP_REFRESH_2026_09_08` + RAM-soft-refresh `OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_REFRESH_2026_09_08` — `--check-dual-sot-report` live soft only; clears sticky `ram_soft_skip`; durable `stamp_refreshed=true`) + worktree-root-bind + CLI `dual_sot_report_path` honesty (redirect before ensure/check load) (`OVERSEER_COMPRESSION_WORKTREE_ROOT_BIND_2026_09_08`) + durable soft-skip RAM stamp (`ram_soft_skip`+`ram_soft_needle`+`mem_available_kb` on `dual_sot_report.json`) + durable probe `stamp_refreshed=true` (set before dump; CLI≠theater) + hub-unlock-ignore + soft-skip dump `hub_unlock_file_needle` (peer-4) — `_resolve_repo_root` / `_redirect_hub_artifact_path` prefer worktree cwd so hub-module import cannot clobber hub Dual SoT; `--dual-sot-check` = pack+canonical only; `--ensure-dual-sot` refreshes logit-expand sidecar (floor `DEFAULT_EXPAND_SNIPS=200`) → `expand_ok` + `dual_sot_report.json` (64→264); `--check-dual-sot-report` live `check_expanded` keep-alive + stamp-refresh (`OVERSEER_COMPRESSION_DUAL_SOT_CACHE_2026_09_07`); `--probe-keep-alive` undersize→heal + dumps `probe_keep_alive_report.json` (`OVERSEER_COMPRESSION_DUAL_SOT_PROBE_KEEP_ALIVE_2026_09_08` + Lane-U `OVERSEER_COMPRESSION_DUAL_SOT_PROBE_CACHE_2026_09_08`); `--check-probe-report` live expand+Dual SoT + RAM-safe stamp-refresh (`OVERSEER_COMPRESSION_PROBE_STAMP_REFRESH_2026_09_08` → durable `stamp_refreshed` + fresh `ts`, no undersize mutation); RAM soft-skip **still dumps** Dual SoT hub_unlock + ram stamps; hub `train_unlock.json=true` → `hub_unlock_ignored` (`OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08`); `train_unlocked=false`; **not** train unlock |
| T1 share-factor | `scripts/compression_t1_share_ablation.py` | **PASS** packing+proxy 2026-09-05 — cliff before S≈100 documented; quality=proxy · share-cache Lane U `OVERSEER_COMPRESSION_T1_SHARE_CACHE_2026_09_05` → `notes/compression_artifacts/t1_share_ablation_report.json` (**not** train unlock) |
| T2 SVD+LoRA | `scripts/compression_t2_svd_lora.py` | **PASS** packing+proxy 2026-09-05 — MSE↓ under \(U\) budget; quality=proxy · svd-cache Lane U `OVERSEER_COMPRESSION_T2_SVD_LORA_CACHE_2026_09_05` → `notes/compression_artifacts/t2_svd_lora_report.json` (**not** train unlock) |
| T3 BitDistill | `scripts/compression_t3_bitdistill.py` | **PASS** packing+KD proxy 2026-09-05 — heldout KD≤ε under \(U\); no prune; quality=proxy; Lane-U logit cache `OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05` GREEN |
| T3 logit-cache (Lane U) | `OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05` dump/load/`--check-cache`/`--ensure-default-bank` | **PASS** 2026-09-05 — KD roundtrip-stable; canonical `notes/compression_artifacts/t3_teacher_logit_bank.json`; refuse prune/unlock; **not** train unlock |
| T3 logit-expand (Lane U) | `scripts/compression_logit_expand.py` `--ensure`/`--check` | **PASS** 2026-09-08 — needle `OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07` → `t3_teacher_logit_bank_expanded.json`; parent=T3 BitDistill; seed=`parent_bank` mean-pool (dim=`d_out`=4); durable floor 200; n_before=64→n_after≈264; `--dual-sot-check` pack+canonical; `--ensure-dual-sot` refreshes expand; **not** train unlock |
| T4 scale | `scripts/compression_t4_scale.py` | **PASS** packing+proxy 2026-09-05 — U/N ±20% @ 1e7→1e8; serve smoke util-only; quality=proxy · scale-cache Lane U `OVERSEER_COMPRESSION_T4_SCALE_CACHE_2026_09_05` → `notes/compression_artifacts/t4_scale_report.json` (**not** train unlock) |
| Train recipe | `COMPRESSION_TRAIN_RECIPE.md` | **Stub filed** — TRAIN-LOCKED (no real train) |

## Pristine definition (this kit)

Research is **pristine for proceeding toward training** when:

1. **No unlabeled overclaims** — every numeric train/serve/RAM claim is PASS/SPLIT/FAIL/UNKNOWN in the ledger  
2. **North-star math is arith-clean** — \(S=100\), bytes \(N/8\), B1–B5 marked quality UNKNOWN  
3. **T0 packing proof green** — unique count + pack bytes on ALBERT-BitMoE (+ LoRA-Hive control)  
4. **Train recipe card** exists (one page): architecture stack, bitwidth, distill teacher, data (no prune), eval bar, stop criteria  
5. **Speed plan** for remaining research is filed — [`RESEARCH_SPEED_TRAINING.md`](RESEARCH_SPEED_TRAINING.md)

## Explicitly NOT required before first train rung

- Measured 1B→10M quality (that *is* the training program)  
- Spark 10k tok/s / 1T residency (struck / horizon)  
- Full A01–A58 primary-URL re-fetch (top-5 bets + train-path methods only)

## Go / No-Go

| Gate | Status |
|------|--------|
| Census + math + novel filed | **GO** |
| Wave-14 spot-audit | **GO** (2026-09-05; C142 fixed; B1–B5 quality UNKNOWN) |
| Top-5 catalog spot-check | **GO** (A11/A19/A28/A33/A36/A41 footnotes) |
| T0 packing | **GO** (unittest green; \(S\ge50\); pack≈\(U/8\); quality N/A) · pack-cache `--ensure-default-pack` **GO** (`t0_pack_report.json`; refuse prune/unlock) |
| Dual SoT (pack+logit) | **GO** 2026-09-08T13:13Z Lane-U heal `--heal-lane-u-sot` (`LANE_U_SOT_HEAL` + `test_heal_lane_u_sot_clears_sticky_soft`) + Dual SoT stamp-refresh + CLI hub→peer `dual_sot_report_path` honesty (`test_cli_dual_sot_report_path_honesty_after_worktree_bind` / `test_check_dual_sot_report_stamp_refresh`) + probe keep-alive; `heal_ok`/`dual_sot_ok`/`probe_ok`/`stamp_refreshed`/`train_unlocked=false` — **not** train unlock |
| Recipe card stub | **GO** (exists) — **lock for real train: NO-GO** |
| Research-speed plan | **GO** (S01–S32 + Lane U filed) |
| T1 share-factor ablation | **GO** (unittest; \(U\downarrow\); recon proxy; cliff flag) — quality still proxy · share-cache `--ensure-default-ablation` **GO** (`t1_share_ablation_report.json`; refuse prune/unlock) |
| T2 SVD+LoRA | **GO** (unittest; MSE↓ under \(U\) budget) — quality still proxy · svd-cache `--ensure-default-report` **GO** (`t2_svd_lora_report.json`; refuse prune/unlock) |
| T3 BitDistill | **GO** (unittest; heldout KD≤ε; \(U\) held; no prune) — quality still proxy |
| T3 logit-cache (Lane U) | **GO** (`OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05`; dump/load/`--check-cache`/`--ensure-default-bank` → `notes/compression_artifacts/t3_teacher_logit_bank.json`; refuse prune/unlock) — **not** train unlock |
| T3 logit-expand (Lane U) | **GO** (`OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07`; durable floor 200; seed=`parent_bank` dim=`d_out`) — **not** train unlock · `--ensure-dual-sot` refreshes expand |
| T4 scale path | **GO** (unittest; U/N ±20% stable; serve smoke util-only) — quality still proxy · scale-cache `--ensure-default-report` **GO** (`t4_scale_report.json`; refuse prune/unlock) |

### Audit result (2026-09-05)

**Research pristine (path toward training):** **YES** — ledger audit + top-5 footnotes + T0 packing + recipe stub + speed catalog.  
**Real model training:** **NO-GO** — do not start.

### Remaining blockers (real train)

1. **Recipe TRAIN-LOCK** — freeze hyperparams after T4+ toys; stub ≠ locked train card  
2. **T1** share-factor — **done** (cliff before S≈100)  
3. **T2** SVD+LoRA — **done** (MSE↓ under \(U\) budget; quality=proxy) · svd-cache Lane U **done** (`OVERSEER_COMPRESSION_T2_SVD_LORA_CACHE_2026_09_05`)  
4. **T3** BitDistill — **done** (heldout KD≤ε under \(U\); no prune; quality=proxy) · logit-cache Lane U **done** (`OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05`)  
5. **T4** scale rung — **done** (U/N ±20% stable @ 1e7→1e8; quality=proxy) · scale-cache Lane U **done** (`OVERSEER_COMPRESSION_T4_SCALE_CACHE_2026_09_05`)  
6. No upgrade of Lane-C / B1–B5 from hypothesis → measured without ledger rows  

_T0–T4 packing/proxy + T0 pack-cache + Dual SoT (pack+logit `--dual-sot-check`) + T1 share-cache + T2 svd-cache + T3 logit-cache + T4 scale-cache are **done** (not train unlocks). Needles T0-cache `OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05` · Dual SoT via T0 `--dual-sot-check` · T1 `OVERSEER_COMPRESSION_T1_SHARE_2026_09_05` · T1-cache `OVERSEER_COMPRESSION_T1_SHARE_CACHE_2026_09_05` · T2 `OVERSEER_COMPRESSION_T2_SVD_LORA_2026_09_05` · T2-cache `OVERSEER_COMPRESSION_T2_SVD_LORA_CACHE_2026_09_05` · T3 `OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05` · T3-cache `OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05` · T4 `OVERSEER_COMPRESSION_T4_SCALE_2026_09_05` · T4-cache `OVERSEER_COMPRESSION_T4_SCALE_CACHE_2026_09_05`._
