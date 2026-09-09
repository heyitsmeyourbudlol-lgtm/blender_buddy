# Compression → train readiness (pristine gate)

_Needle: `OVERSEER_COMPRESSION_TRAIN_READY_2026_09_05`_  
**Rule:** Do **not** start real model training (1B-scale / quality train rungs beyond packing probes) until this gate is green **and** recipe is LOCKED. T0 packing alone ≠ permission to train.

## North star (locked)

[`COMPRESSION_NORTH_STAR.md`](COMPRESSION_NORTH_STAR.md) — 1B logical → 10M unique @ **NVFP4** (\(S\approx100\)). No data prune. Distill OK. SSD/Zamba ≠ bytes. See [`NVFP4_LOCK_APPLICABILITY.md`](NVFP4_LOCK_APPLICABILITY.md).  
**Same DGX sidequest** as Cursor plan `dgx_1-bit_sidequest_05e1d3b8` / task SoT [`BITNET_RESEARCH_TASKS.md`](BITNET_RESEARCH_TASKS.md) — compression is not a fork.

## Wave-1 research status

| Lane | Artifact | Pristine? |
|------|----------|-----------|
| A — Method census | `COMPRESSION_CATALOG.md` A01–A58 | **Done** — top-5 spot-checked 2026-09-05 (footnotes; no row deletes) |
| B — Math / stacks | Lane B + `BITNET_FACTCHECK` C139–C152 | **Arith pristine** (C142 label fixed) — quality UNKNOWN |
| C — Hypotheses | `COMPRESSION_NOVEL.md` | **Hypothesis-labeled**; T0 packing measured (quality N/A) |
| Fact-check wave-14 | C139–C152 | **Spot-audit PASS** — `BITNET_FACTCHECK.md` § Wave-14 pristine audit |
| **T0 packing proof** | `scripts/compression_t0_pack.py` + unittest | **PASS** 2026-09-05 (quality N/A) |
| T1 share ablation | `compression_t1_share.py` + unittest | **Done** 2026-09-05 — mono \(U\downarrow\); **arith** short at weak \(k\le16\); **\(S\ge100\) clears at \(k{=}200\)** (not a quality cliff); train_unlocked=false |
| T2 SVD-TieStack toy | `compression_t2_svd.py` + unittest | **Done** 2026-09-05 — Needle `OVERSEER_COMPRESSION_T2_SVD_2026_09_05`; real truncated-SVD residual; **\(S\ge100\) at \(r{=}1\)**; higher \(r\) spends unique; train_unlocked=false |
| T3 BitDistill | `scripts/compression_t3_bitdistill.py` + unittest | **PASS** packing+KD proxy 2026-09-05 — heldout KD≤ε under \(U\); no prune; quality=proxy; Lane-U logit cache `OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05` GREEN; train_unlocked=false |
| T4 | scale rung | **Done** 2026-09-06 — Needle `OVERSEER_COMPRESSION_T4_SCALE_2026_09_06`; N=1e7→1e8; S stable ±20%; S≥100; train_unlocked=false |
| Train recipe | `COMPRESSION_TRAIN_RECIPE.md` | **LOCKED** 2026-09-06 — Status LOCKED (T4 Done); unlock path open for `compression_auto_train` |

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
| T0 packing | **GO** (unittest green; \(S\ge50\); pack≈\(U/8\); quality N/A) |
| Recipe card LOCKED | **GO** (2026-09-06 — `**Status:** **LOCKED**`; T4 Done) |
| Research-speed plan | **GO** (S01–S32 + Lane U filed) |
| T1 share ablation | **GO** (measured; weak-\(k\) arith short ≠ quality cliff; \(k{=}200\) clears \(S\ge100\); no train unlock) |
| T2 SVD-TieStack toy | **GO** (real SVD residual; \(r{=}1\) clears \(S\ge100\); train_unlocked=false) — `OVERSEER_COMPRESSION_T2_SVD_2026_09_05` |
| T3 BitDistill + logit-cache | **GO** (KD proxy; `OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05` + `OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05`; train_unlocked=false) |
| T4 quality/scale path | **GO** (2026-09-06 — `OVERSEER_COMPRESSION_T4_SCALE_2026_09_06`; ratio stable; S≥100; recipe still stub LOCK pending) |

### Audit result (2026-09-05)

**Research pristine (path toward training):** **YES** — ledger audit + top-5 footnotes + T0 packing + recipe stub + speed catalog.  
**Real model training:** **NO-GO** — do not start.

### Remaining blockers (real train)

1. **Recipe TRAIN-LOCK** — freeze `**Status:** **LOCKED**` on recipe card (blocks auto-train)  
2. ~~**T1**~~ … ~~**T4**~~ — probes done (see strikethrough history below)  
3. No upgrade of Lane-C / B1–B5 from hypothesis → measured without ledger rows  

~~T1~~ `OVERSEER_COMPRESSION_T1_SHARE_2026_09_05` · ~~T2~~ `…T2_SVD…` · ~~T3~~ `…T3_BITDISTILL…` · ~~T4~~ `OVERSEER_COMPRESSION_T4_SCALE_2026_09_06`

## Auto-train (CLEAN) — 2026-09-05

Needle: `OVERSEER_COMPRESSION_AUTO_TRAIN_2026_09_05` · keep-alive: `OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05`

1. **`compression_keep_alive.py`** — forever fanout (target 96); respawn if agents &lt; floor; mandate = max \(S\) / min unique \(U\) + RAM @ **NVFP4**; no data prune.  
2. **`compression_auto_train.py`** — when **T4 Done/PASS/GO** + recipe **LOCKED** + T0–T3 unittests green → write `notes/compression_artifacts/train_unlock.json` and **instantly** start **`compression_train_rung0.py --train --min-ram`**.  
3. Peers must land T4 + freeze recipe as `**Status:** **LOCKED**` (not stub) before unlock fires.  
4. Rung0 = efficient shared-expert + LoRA skeleton (minimize \(U\)/NVFP4 bytes) — not a fat dense 1B.  
5. **GPU (CLEAN GB10):** `compression_gpu_worker.service` runs local CUDA SVD/KD/T4 arith forever (**$0**, not Cursor API). Speeds probes agents cannot; cursor-agent fanout stays desktop-login free.

## Post-train gate (human-locked policy — 2026-09-06)

Needle: `OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06`

**After the model is fully trained** (unlock + train rungs complete — not packing toys alone):

1. **Run all stress tests** — quality / \(S\) / unique-\(U\) / NVFP4 pack bytes / RAM residency / no-data-prune / KD heldout / serve smoke. Bars live in recipe + `notes/compression_artifacts/stress_bars.json` (create when train completes).  
2. **Clear every bar** — any FAIL = no integrate; redesign or retrain.  
3. **Only then** integrate into the automation workflow (peer dispatch / product path / registry proof).  

**Forbidden:** shipping into workflow from T0–T4 probes or unlock alone. Train complete ≠ integrate.

### Auto-train GO (OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05)

**Real model training:** **GO** — unlocked 2026-09-06 09:06Z by `OVERSEER_COMPRESSION_AUTO_TRAIN_2026_09_05`.
First rung: min-RAM unique store @ NVFP4 (rung0 scaffold).
