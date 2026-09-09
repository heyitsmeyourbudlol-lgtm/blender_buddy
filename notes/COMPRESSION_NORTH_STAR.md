# Compression north star (user lock · 2026-09-05)

## Wave-keep-alive fanout#7 daemon RSS (compression_engineer · 2026-09-07)

Live improve `VmRSS` before/after hub `include_research=bool(audit)` land + improve-loop restart:

| Process | Before MB | After MB | Δ MB |
|---------|----------:|---------:|-----:|
| improve poll-cache | 54.49 | 40.87 | **−13.62** |
| dashboard lazy | 16.85 | 16.85 | 0 (untouched) |
| peer_loop gitfile | ~37.4 | ~37.4 | 0 (untouched) |

Needle `COMPRESSION_SKIP_DUAL_ON_AUDIT_TTL_2026_09_07` — hub `rank_opportunities` skipped dual merge on audit TTL-skip (peer-6 already had gate; live daemon ran hub). Unittest `test_rank_skips_dual_research_when_include_research_false` green. TRAIN_UNLOCKED untouched.

## Wave-34 daemon RSS audit (compression_engineer · healthy-idle)

Live `ps` RSS (MB) — audit-only, **0 MB trimmed** (no safe trim without feature risk):

| Process | RSS MB |
|---------|-------:|
| peer_loop gitfile `--forever` | ~29.6 |
| oversight `--forever` | ~43.7 |
| dashboard lazy :8765 | ~21.4 |
| dgx-dashboard-service | ~20.1 |
| dgx-dashboard-admin | ~14.5 |
| peer_loop `--once` (transient) | ~33.6 |
| **Sum (kit daemons, excl. NVIDIA dashboard)** | **~95** |
| **Sum (incl. NVIDIA dashboard + transient once)** | **~163** |

Stance: prefer cache/prune/lazy already landed; TRAIN_UNLOCKED untouched; no speculative cuts. Needle `OVERSEER_COMPRESSION_RSS_WAVE34_2026_09_05`.

## Wave-29 daemon RSS audit (compression_engineer · healthy-idle)

Live `ps` RSS (MB) — audit-only, **0 MB saved** (no safe trim without feature risk):

| Process | RSS MB |
|---------|-------:|
| peer_loop `--forever` | ~29.6 |
| improve poll-cache | ~37.9 |
| oversight | ~35.8 |
| comms_improve | ~33.5 |
| dashboard lazy | ~21.4 |
| peer_loop `--once` (transient) | ~32.5 |
| **Sum (incl. transient once)** | **~191** |

Stance: prefer cache/prune/lazy already landed; no speculative cuts this cycle. Needle `OVERSEER_COMPRESSION_RSS_WAVE29_2026_09_05`.

**KPI (one sentence):** Each granular MoE expert that is logically **~1B parameters** must keep only **~10M unique parameters**, stored and served as **NVFP4** — i.e. **~100× unique-param compression**, with **NVIDIA NVFP4** as the locked hot dtype (not BF16-native; not 1-bit-as-hot).

**Horizon (user lock · 2026-09-06):** **1 quadrillion** (`10^15`) total params @ **≤20GB** resident. Near map = 2^8 ladder → **10T**. Unique-param 1B→10M lane stays **orthogonal inside** the same sidequest (not a competing north star). Ops: [`DGX_NVFP4_SIDE_QUEST_OPS.md`](DGX_NVFP4_SIDE_QUEST_OPS.md). Maps: `compression_artifacts/near_map_ladder.json`, `far_map_1q.json`. **Local only** — no public model publish.

**Applicability audit:** [`NVFP4_LOCK_APPLICABILITY.md`](NVFP4_LOCK_APPLICABILITY.md) · Needle `OVERSEER_NVFP4_LOCK_APPLICABILITY_2026_09_05`.

## The 100× equation (unique params)

\[
S \;=\; \frac{N_{\mathrm{logical}}}{N_{\mathrm{unique}}} \;=\; \frac{10^{9}}{10^{7}} \;=\; \mathbf{100\times}
\]

Same-dtype packed bytes (NVFP4 raw sketch \(0.5\) B/param; real pack ≈ **4.5 bit/value** + scales):

| View | Unique params | Raw @ 0.5 B/param | Notes |
|------|--------------:|------------------:|-------|
| Logical if all unique | 1B | ~500 MB | Before share/rank |
| Target unique store | 10M | **~5 MB** | Still \(S=100\) |
| Disk zstd/gzip | — | extra 10–30% file only | **Not** resident \(S\); decompress for GEMM |

## Locked vs optional

| Item | Status |
|------|--------|
| **NVFP4** hot weights / GEMM | **LOCKED** |
| Unique-param \(S\approx100\) (ALBERT share, LoRA/SVD, hive) | **LOCKED KPI** |
| Teacher distill | Allowed (quality) |
| Zamba / Mamba-2 SSD trunk | Allowed **serve util** only |
| PagedAttention / vLLM KV paging | Allowed **KV RAM** |
| zstd/gzip on checkpoints | Allowed **disk/transfer** only |
| 1-bit / ternary | Optional **cold/research** — not hot dtype |
| Data / dataset pruning | **Forbidden** |
| Multi-GPU NVLink expert All-to-All | **N/A** on single DGX Spark |
| BF16-exponent router-mask tricks | **Blocked** until primary source (conflicts with NVFP4 path) |

## Honesty lock

- Arith PASS ≠ quality PASS.  
- zstd ≠ unique-param compression.  
- SSD/Zamba ≠ weight \(S\).  
- Stock native NVFP4 MoE on sm121 ≠ mature (**C27**).  
- Spark: prefer **`sm_121a`** + CUDA **13.1+** for native NVFP4 PTX.

Full math stacks: [`COMPRESSION_CATALOG.md`](COMPRESSION_CATALOG.md) Lane B. Ledger: [`BITNET_FACTCHECK.md`](BITNET_FACTCHECK.md) **C139–C162**.
