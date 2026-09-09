# Compression research phases (parallel with train)

_Needle: `OVERSEER_COMPRESSION_PARALLEL_PHASES_2026_09_06`_  
**Policy:** Wave-1 + T0–T4 packing research is **closed**. Real train (rung0+) runs **now**. Next research phases run **in parallel** on file-disjoint scopes — they must **not** change the LOCKED recipe primary stack mid-rung.

**Recipe (frozen):** [`COMPRESSION_TRAIN_RECIPE.md`](COMPRESSION_TRAIN_RECIPE.md) — ALBERT-BitMoE primary · LoRA-Hive control · NVFP4 · no data prune.  
**Train SoT:** [`BITNET_RESEARCH_TASKS.md`](BITNET_RESEARCH_TASKS.md) · unlock `notes/compression_artifacts/train_unlock.json`.  
**Rung0 status (2026-09-06):** `--train --min-ram` live · `rung0_heartbeat.json` mtime fresh (≤30s) · recipe LOCKED untouched.

## Parallel map (same calendar day)

| Lane | Owner tags | Writes | Blocks train? |
|------|------------|--------|---------------|
| **Train** | `[compression-train]` | `compression_train_rung0*` · `rung0_*` · later stress_bars | — (primary) |
| **T5 Serve / residency** | `[compression-research]` | `notes/BITNET_ARCH_RESEARCH.md` L5 NVFP4 cross-link · optional `scripts/compression_t5_serve.py` + unittest | No |
| **T6 Quality falsifiers** | `[compression-research]` | toy heldout ε vs teacher (ALBERT vs Hive); ledger C-rows only | No — do not raise \(U\) on recipe |
| **Niche P1** | `[niche-distill]` | `notes/niche_distill/practice_n03/` · `practice_n08/` · STRESS_GAPS P1 | No |
| **HPO speed** | `[research-speed]` | `scripts/compression_ablation_schedule.py` (OA/Hyperband) for future rungs | No |
| **Deferred novels** | — | BasisBank / Twin-Rank / … | **Parked** until T6 or train falsifies \(U\) |

```text
  TRAIN rung0 ──────────────────────────► scale KD / stress bars ──► integrate
       │
       ├── T5 serve/residency (docs + smoke)
       ├── T6 quality falsifier toys (ledger)
       ├── Niche N03/N08 practice
       └── ablation_schedule script (S03/S16/S32)
```

## Phase definitions

### T5 — Serve / residency (parallel)
- Cross-link L5 RAM sketches @ NVFP4 unique sizes after T4 stamp.
- Optional smoke: pack-bytes + residency estimate from `rung0_model_skeleton.json` (no architecture churn).
- Falsifier: claiming sm_121 native NVFP4 MoE mature without ledger row.

### T6 — Quality falsifiers (parallel)
<!-- OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06 -->
- Heldout recon/task ε on **toys** for primary vs control — upgrade hypothesis→measured only with new C-rows.
- Must not prune data; must not change LOCKED stack fields.
- **Measured 2026-09-06** (`scripts/compression_t6_quality.py`): ALBERT-BitMoE + LoRA-Hive heldout KD≈0.094 ≤ ε=0.15 @ \(U{=}224\); quality=**proxy**; prune-control FAIL; `train_unlocked=false`. Needle `OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06`.

### T7 — Combo stack (gated)
- Teacher-SVD-ALBERT staged gates — **only if** T6 or rung stress shows quality cliff under current recipe.
- Default: **do not start** while rung0 is green.

### T8 — Deferred novels (parked)
- Novels 6–11 in `COMPRESSION_NOVEL.md` — park until T7 needed.

### Niche P1 (parallel)
- Replicate N01 recipe → N03 / N08 under `practice_n03/` / `practice_n08/`.
- Append live miss classes to `STRESS_GAPS.md` (no corpus prune).

## Anti-thrash rules

1. One architecture lock per train rung (S09) — peers **read** recipe; do not rewrite Status/stack.  
2. File-disjoint peers: train ≠ T5 ≠ niche paths.  
3. Stress bars + workflow integrate stay **serial after** full train (`OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06`).  
4. Free desktop auth only on CLEAN — never paid Cursor API for this lane.
