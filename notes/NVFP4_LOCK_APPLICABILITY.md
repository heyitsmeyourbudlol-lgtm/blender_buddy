# NVFP4 lock + lossless-claim applicability

_Needle: `OVERSEER_NVFP4_LOCK_APPLICABILITY_2026_09_05`_  
**User lock:** trained/served **weights = NVFP4** (NVIDIA microscaling FP4), not BF16-as-native and not “1-bit as the hot dtype.”

Cross-links: [`COMPRESSION_NORTH_STAR.md`](COMPRESSION_NORTH_STAR.md) · [`COMPRESSION_CATALOG.md`](COMPRESSION_CATALOG.md) · [`BITNET_FACTCHECK.md`](BITNET_FACTCHECK.md) C153+ · GB10 serve notes in [`BITNET_ARCH_RESEARCH.md`](BITNET_ARCH_RESEARCH.md) L7.

## How NVFP4 relates to the 1B→10M north star

| Layer | Rule |
|-------|------|
| **Dtype / hot GEMM** | **NVFP4** (TE / `mxf4nvf4` class; Spark needs `sm_121a`, prefer CUDA 13.1+) |
| **Unique-param KPI** | Still \(S=N_{\mathrm{logical}}/N_{\mathrm{unique}}\approx100\) (share / low-rank / hive) |
| **Byte sketch @ NVFP4** | Raw \(N\times0.5\) B/param; packed NVFP4 ≈ **~4.5 bit/value** + scales (**C7 / L5-U1**) — not pure 0.5 B |
| **1-bit / ternary** | Optional **cold / research** path only — **not** the locked hot model format |
| **Forbidden** | Data/dataset pruning |

Ideal unique store @ NVFP4 (ignore scales): \(10^7\times0.5\,\mathrm{B}\approx\mathbf{5\,\mathrm{MB}}\) raw — still **100×** below \(10^9\) unique at same dtype.

Stock **native NVFP4 MoE** on sm121 remains **not mature** (**C27 FAIL**) — interim Marlin/W4A16 or emerging FlashInfer paths; do not claim production-native MoE FP4 on Spark yet.

---

## Applicability matrix (your claim list)

Legend: **Y** = use on our NVFP4+Spark path · **P** = partial / wrong axis · **N** = does not apply (or OVERCLAIM) · **?** = needs primary source before train.

| # | Claim | Axis | NVFP4 kit? | Verdict |
|---|--------|------|------------|---------|
| 1 | Gzip / BZIP2 / **zstd** on weight binaries (10–30% smaller files) | **Disk / transfer** | **P** | **Lossless for files only.** Must decompress (or mmap-decompress) before GEMM. Does **not** cut unique params or resident NVFP4 working set. Gains often **smaller** once weights are already NVFP4-packed vs BF16. OK as artifact codec; **never** count toward \(S\approx100\). |
| 2 | Zamba speed = custom CUDA (`mamba-ssm`, `causal-conv1d`) | Serve util | **Y** if Zamba/Mamba trunk | Real for hybrid backbone. **Not** a weight compressor. |
| 3 | Hidden-state contiguity + `torch.compile` / graph compile | Serve util | **Y** | Runtime hygiene — applies to any SSM path. Zero effect on \(N_{\mathrm{unique}}\). |
| 4 | Shared-layer fusion (Zamba ABAB shared attn) → HBM→SRAM reuse | Serve BW | **Y** if shared blocks | Helps **shared-weight** stacks (ALBERT/Zamba-shell). Compiler/cache behavior — not unique-param math by itself. |
| 5 | Zstd level-19 on **BF16** safetensors → 10–25% | Disk | **P** | Mechanism OK; **BF16 % does not transfer** to NVFP4 packs. Re-measure on NVFP4 tensors before quoting %. |
| 6 | **PagedAttention** (vLLM) saves 20–30% KV VRAM | **KV cache** | **Y** for attn/hybrid | Lossless vs fragmentation / block alloc — **not** weight compression. Zamba already shrinks KV vs full Transformer; paging still helps long context. |
| 7 | SSM-MoE “single state trajectory” / shared hidden state across experts | Arch / VRAM | **?** / **P** | Only if **our** MoE-Mamba design actually shares one SSM state. Not universal; do **not** assume Zyphra marketing = our MoE grain. Mark UNKNOWN until arch spec + kernel proof. |
| 8 | Shared base + **LoRA projectors**; pin base in L2/SRAM | Unique + serve | **Y** | Aligns with **LoRA-Hive / DELTA-SHARE**. Base = NVFP4 shared; adapters small. Pinning = BW win; unique cut = adapter math. |
| 9 | All-to-All / **NVLink** topology-aware expert routing | Multi-GPU | **N** on single Spark | DGX Spark = **one GB10** + C2C UMA — not a multi-GPU NVLink expert fabric. Keep for future multi-box only. |
| 10 | Router masks in **BF16 exponent bits** | Runtime hack | **?** / likely **N** | High OVERCLAIM risk; BF16-centric story conflicts with **NVFP4** token/weight path. Require a primary paper/runtime before any train dependency. |

---

## What to keep in the train recipe

**Keep (NVFP4 path):**
1. NVFP4 weights as dtype lock  
2. Structural \(S\approx100\) (share × low-rank / hive) — same as before, measured in **unique count**  
3. Shared + LoRA (claim 8)  
4. Optional Zamba/Mamba-2 trunk for util (claims 2–4) — credit **tok/s / BW**, not \(S\)  
5. PagedAttention / vLLM for KV (claim 6)  
6. zstd only for **checkpoint shipping** (claims 1, 5) — separate meter `disk_codec_ratio`

**Defer / reject for Spark-now:**
- Multi-GPU NVLink All-to-All (9)  
- Exponent-bit routing masks (10) until sourced  
- “zstd = model compression toward 10M” (1, 5) — **strike** as north-star lever  
- Blind “SSM-MoE single state always lossless” (7)

---

## Fact-check IDs (wave 15)

See `BITNET_FACTCHECK.md` **C153–C162**.
