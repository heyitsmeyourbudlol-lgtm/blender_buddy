# BitNet / GB10 — architecture research

> **Plan sync 2026-09-06:** `dgx_1-bit_sidequest_05e1d3b8.plan.md` Status includes **compression train path** (T0–T3 done; T4+recipe LOCK open; stress→integrate after full train). Hot dtype **NVFP4**; 1-bit cold optional. Task SoT: [`BITNET_RESEARCH_TASKS.md`](BITNET_RESEARCH_TASKS.md). Gate: [`COMPRESSION_TRAIN_READY.md`](COMPRESSION_TRAIN_READY.md).


**Status:** scavenger wave 0 (temp research mode on hub 8)  
**North star:** 1Q @ ≤20GB resident · Near map: 2^8 → 10T · Hot path: FP4 GEMM · Reading = Writing  
**Protocol:** every section needs sources; numeric claims must appear in `BITNET_FACTCHECK.md`.

## Lanes (append under your heading)

### L1 — Fact ledger summary
_(fact_checker — 2026-09-04)_

**Tally:** PASS **8** · FAIL **2** · UNKNOWN **2** (full rows: `notes/BITNET_FACTCHECK.md`).

- **Hardware PASS:** C1 L3=16+8MB (not 32 shared); C2 GPU L2≈24MB; C3 coherent 128GB LPDDR5X UMA via C2C; C5 ≤1 PFLOP sparse FP4 (5th-gen TE).
- **Serve PASS:** C6 8k–10k+ is prefill not AR decode; C7 ~10B@FP4≈5GB; C8 ~0.61B expert@FP4≫L2/L3; C9 spec/MTP parallel verify; C10 load-spread helps large-N.
- **FAIL strikes:** **C4** — Spark GDS is compatibility-mode only (no NVMe→UMA DMA). **C12** — 2^8 ladder is not a verified executable map.
- **UNKNOWN:** **C11** — NVFP4≈FP8, but BitNet b1.58 vs FP4 quality lacks head-to-head; do not assert FP4≻1-bit absolutely.

### L2 — GB10 hardware roots (FP4 TE, C2C UMA, GDS, L2/L3)
_(efficiency / hardware)_

**Hallucination strategy (pre-edit):**
```
Assumption: I will hallucinate unless grounded in fetched NVIDIA/SPEC/Hot Chips pages.
Evidence:   nvidia.com/dgx-spark specs + footnote; docs.nvidia.com/dgx/dgx-spark/hardware.html;
            nvidianews NVLink-C2C; GDS release notes Spark line; SPEC cpu2026 PDF L3; C&C L3 measure.
Hypothesis: Seed C5/C3/C2 mostly true; C1 true as 8+16=24MB (not 32); C4 GDS fast-path false.
Falsifier:  Official NVIDIA claim of 32MB shared L3, or GDS full/fast-path on Spark.
Verify:     Every numeric row has a URL opened this cycle; no invented citations.
```

**Lane verdict (2026-09-04):** Ship-of-record Spark/GB10 numbers below. Prefer silicon/docs over Hot Chips press when they conflict (L3).

| Spec | True value (as sourced) | Confidence | Notes |
|------|-------------------------|------------|-------|
| FP4 Tensor Cores / ~1 PFLOP sparse | **5th-gen TE; up to 1 PFLOP FP4 with sparsity** (dense ≈½) | High | Product page footnote: *“Theoretical FP4 TOPS using the sparsity feature.”* Hardware guide: *“up to 1 PFLOP at FP4 precision with sparsity”* + *“1,000 TOPS inference”*. |
| NVLink-C2C UMA ~128GB | **Yes: NVLink-C2C coherent CPU↔GPU + 128 GB LPDDR5x UMA** | High | Newsroom: NVLink-C2C → coherent memory, ~5× PCIe Gen5 BW. Product/docs: 128 GB coherent unified LPDDR5x, 256-bit, **273 GB/s** marketed (8533 MT/s class). Hot Chips press also cites ~600 GB/s aggregate C2C fabric (secondary). |
| GPUDirect Storage | **Fast-path GDS: not supported on Spark; compat mode only** | High | Official GDS release notes: *“On DGX Spark, GPUDirect Storage is supported only in compatibility mode. Do not load `nvidia-fs`…”* Forum `gdscheck`: GB10 “Model Not Supported”. GPUDirect **RDMA** also unsupported (UMA/porting guide). Seed “DMA NVMe→UM” as zero-copy GDS is **false**. |
| CPU L3 (24 vs 32MB) | **~24 MB total, split 8 MB + 16 MB per cluster — not one 32 MB pool** | High | SPEC CPU2026 DGX Spark result + `lscpu`: L3 8M / ALL-SIZE 24M; notes “8MB and 16MB”. Chips and Cheese measures Cluster0=8MB, Cluster1=16MB. Hot Chips press (WCCFTech/TPU) said 16+16=32MB — treat as **slide/press error vs silicon**. Also ~16 MB SLC (L4-ish), separate from L3. |
| GPU L2 ~24MB | **~24 MB GPU L2 (Hot Chips coverage)** | Medium–High | TechPowerUp / WCCFTech Hot Chips 2025: GPU **24 MB L2**, coherent with CPU. Not listed on the public Spark product table — no contradiction found, but not in the marketing specs grid. |

**Implication for BitNet scavenger:** Hot path should bank on **FP4 sparse TE peak + 128 GB C2C UMA**, treat **GPU L2 (~24 MB)** as the useful on-die tile bank (not CPU L3), and **do not plan GDS fast-path expert streams** on Spark — use POSIX/compat I/O or host-visible UMA buffers instead.

**Sources (L2):**
1. [NVIDIA DGX Spark product / specs](https://www.nvidia.com/en-us/products/workstations/dgx-spark/) — 1 PFLOP FP4 (sparsity footnote), 128 GB coherent UMA, 273 GB/s, 5th-gen TE
2. [DGX Spark Hardware Overview](https://docs.nvidia.com/dgx/dgx-spark/hardware.html) — 1 PFLOP FP4 w/ sparsity, 128 GB LPDDR5x, 273 GB/s, 6144 CUDA cores
3. [NVIDIA Newsroom: DGX Spark / Station announce](https://nvidianews.nvidia.com/news/nvidia-announces-dgx-spark-and-dgx-station-personal-ai-computers) — GB10 **NVLink-C2C** coherent memory model
4. [NVIDIA NVLink-C2C (DGX Spark callout)](https://www.nvidia.com/en-us/data-center/nvlink-c2c/)
5. [GPUDirect Storage Release Notes](https://docs.nvidia.com/gpudirect-storage/release-notes/index.html) — Spark = compatibility mode only; do not load `nvidia-fs`
6. [DGX Spark Porting Guide — CUDA / GPUDirect RDMA](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/porting/cuda.html) — GDR not supported on UMA Spark
7. [Forum: GDS support for DGX Spark](https://forums.developer.nvidia.com/t/gds-support-for-dgx-spark/350328) — `gdscheck` Model Not Supported; NVIDIA mod: GDS not supported on Spark
8. [SPEC CPU2026: NVIDIA DGX Spark (GB10)](https://www.spec.org/cpu2026/results/res2026q2/cpu2026-20260210-00022.pdf) — L3 8 MB + 16 MB; `lscpu` ALL-SIZE 24M
9. [Chips and Cheese: GB10 memory subsystem](https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem) — measured 8/16 MB L3 clusters; ~16 MB SLC
10. [WCCFTech Hot Chips GB10](https://wccftech.com/nvidia-gb10-superchip-soc-3nm-20-arm-v9-2-cpu-cores-nvfp4-blackwell-gpu-lpddr5x-9400-memory-140w-tdp/) — NVLINK C2C / UMA; GPU 24 MB L2; (press also claimed 32 MB L3 — superseded by SPEC/silicon)
11. [TechPowerUp Hot Chips GB10](https://www.techpowerup.com/340385/nvidia-dissects-gb10-superchip-soc-with-20-cpu-cores-and-6-144-cuda-gpu-cores) — 24 MB GPU L2; ~600 GB/s inter-die C2C (press)


### L3 — Reading = Writing (MTP / speculative / tree verify → 10k+ class)
_(output / serve)_

**Hallucination strategy (pre-edit):**
```
Assumption: I will hallucinate tok/s ceilings unless grounded in papers + measured GB10 notes.
Evidence:   Leviathan arXiv:2211.17192; Medusa arXiv:2401.10774; EAGLE arXiv:2401.15077;
            DeepSeek-V3 arXiv:2412.19437 MTP §; Gloeckle arXiv:2404.19737; SGLang EAGLE-3 table;
            NVIDIA DGX Spark specs (273 GB/s, 1 PFLOP sparse FP4); dgx-spark-field-notes README.
Hypothesis: Spec/tree verify = prefill-shaped GEMM (C9 true as mechanism); ≥10k accepted
            single-stream tok/s on GB10 is marketing/theater, not measured class.
Falsifier:  Peer-reviewed or on-box measured ≥10k *accepted* decode tok/s @ batch=1 on GB10.
Verify:     Every number below has a URL opened this cycle; flag marketing vs measured.
```

**Lane verdict (2026-09-04):** Mechanism of Reading=Writing is real and well-sourced. Absolute **≥10k accepted tok/s single-stream on GB10-class** is **not honest** as a measured serve target — treat as brochure / prefill-or-aggregate conflation until CLEAN measures otherwise. Realistic GB10 decode with MTP/spec sits **~tens–~100 tok/s** single-stream; aggregate@8 can reach **~300 tok/s**. Even H100 EAGLE-3 Llama-8B is **~373 tok/s** (measured engine table), still ≪10k.

#### Mechanism — how Writing becomes prefill-shaped parallel GEMM

| Step | What happens | Why GEMM looks like Reading (prefill) |
|------|--------------|----------------------------------------|
| 1. Draft | Cheap heads / draft model / MTP module propose γ future tokens (chain or tree) | Draft itself may still be AR; cost must stay ≪ target |
| 2. Verify | Target LLM runs **one** forward over the drafted sequence (seqlen≈γ+1 or tree nodes) | Linear layers become `(d_out×d_in)·(d_in×N)` with **N≫1** — same shape family as prefill, not decode’s matrix–vector |
| 3. Accept | Rejection sampling / typical accept / tree walk keeps a prefix; discard rest | Only **accepted** tokens count as Writing throughput; rejected FLOPs are “free” only while still memory-bound |

**Roofline link (Reading=Writing factor table):** Vanilla decode intensity ≈ `2 / bytes_per_param` (~1 FLOP/byte FP16) → memory-bound. Prefill intensity scales with sequence length `L`. Speculative verify raises effective tokens per weight load by ~acceptance length τ, so Writing reuses the **same weight read** for multiple tokens — Leviathan explicitly: target weights/KV can be read once per speculative step while arithmetic concurrency grows by γ+1 ([Leviathan et al., ICML 2023 / arXiv:2211.17192](https://arxiv.org/html/2211.17192v2)). Pedagogical derivation of intensity `2B/bytes` and verify-as-prefill: [ametric speculative deep dive](https://ametric.sh/paths/ai-systems/deep-dives/10-speculative-disaggregation/).

#### Priors by family (mechanism + measured speedups)

| Family | Draft | Verify | Reported acceleration | Class |
|--------|-------|--------|----------------------|-------|
| **Classic speculative** | Separate smaller LM | Parallel target over γ drafts | **2×–3×** walltime on T5-XXL vs T5X (identical distribution) | **Measured** paper |
| **Medusa** | K extra LM heads on last hidden; Cartesian/tree candidates | Tree attention → one target forward | Medusa-1 **>2.2×**; Medusa-2 **2.3–2.8×** (Vicuna/Zephyr; batch=1) | **Measured** paper |
| **EAGLE / EAGLE-2/3** | Autoregress features (2nd-to-top) + shifted tokens; tree verify | One target forward + tree attention | LLaMA2-Chat 70B **2.7×–3.5×** latency, ~2× throughput; τ≈3.2–4.5 tokens/forward | **Measured** paper |
| **Gloeckle MTP** | n independent heads on shared trunk (train-time) | Speculative use of heads | Up to **~3×** inference for 4-token prediction models | **Measured** paper (train+infer) |
| **DeepSeek-V3 MTP** | Sequential MTP modules (causal chain; EAGLE-like); optional at infer | Repurpose MTP for speculative decode | Report: MTP mainly for **training quality**; infer can discard or use for speculation — **no V3 tok/s number in tech report** | Mechanism **PASS**; absolute tok/s **UNKNOWN** in paper |
| **SGLang EAGLE-3** | EAGLE3 draft | Engine verify | Llama-3.1-8B Instruct MT-bench, **1×H100**: baseline **158.34** → EAGLE-2 **244.10** → EAGLE-3 **373.25** tok/s | **Measured** engine docs |

SGLang also exposes `--speculative-attention-mode` = `prefill` or `decode` for speculative ops — explicit acknowledgment that verify can run in **prefill attention mode** ([SGLang speculative decoding](https://docs.sglang.io/docs/advanced_features/speculative_decoding)).

#### GB10-class honesty (≥10k accepted tok/s?)

**Hardware anchors (marketing vs silicon — cross-check L2):**
- Memory bandwidth **273 GB/s** LPDDR5x UMA; Tensor performance **up to 1 PFLOP FP4** with **sparsity** footnote ([NVIDIA DGX Spark specs](https://www.nvidia.com/en-us/products/workstations/dgx-spark/)).
- Decode on Spark is **bandwidth-bound**; generation ≈ bytes-per-token / bandwidth ([dgx-spark-field-notes](https://github.com/sergioamsilva/dgx-spark-field-notes)).

**Rough BW ceiling (order-of-magnitude, not a promise):**  
`tok/s ≲ BW / active_bytes_per_token`. At 273 GB/s:
- ~3 GB active/token → ~90 tok/s ceiling  
- ~1 GB active → ~270 tok/s  
- **~27 MB** active → ~10k tok/s only if every token streams that tiny footprint **and** acceptance≈1  

So ≥10k **accepted** Writing tok/s on GB10 requires either (a) toy active weight streams, (b) counting **prefill** tok/s or multi-request **aggregate**, or (c) brochure PFLOP→tok/s conversion — not measured serve of a ~10B-active FP4 student.

**Measured on-box priors (GB10 / Spark):**
| Config | tok/s | Metric | Flag |
|--------|------:|--------|------|
| Best single-stream: Qwen3.6-35B-A3B NVFP4 + MTP | **101.1** | single-stream | **Measured** field notes |
| Qwen3-30B-A3B Ollama Q4 | **85.2** | single-stream | **Measured** |
| vLLM INT4 coding MoE | **74.8** | single-stream | **Measured** |
| Same models @ 8 concurrent (vLLM) | **289–313** | **aggregate** | **Measured** — do not sell as single-user Writing |
| Speculative decoding called out as “biggest single-stream win” (+81% in their guide) | still ≪10k | single-stream | **Measured** qualitative |

**H100 contrast (still ≪10k):** EAGLE-3 **373 tok/s** on Llama-3.1-8B ([SGLang](https://docs.sglang.io/docs/advanced_features/speculative_decoding)). Third-party cloud blogs quoting multi-k tok/s on H200/B200 with Eagle-3 are **marketing/ops blogs** until reproduced; even those cited peaks (~6–8.5k on B200 in one blog) are **not** GB10 and often mix serving settings — do not import as Spark priors.

#### Claim map → Fact Checker

| Seed | L3 stance | Notes |
|------|-----------|-------|
| **C9** Spec/MTP block verify → Writing uses parallel GEMM like Reading | **Mechanism PASS** (prior art) | Leviathan parallel target; Medusa/EAGLE tree attention; DeepSeek MTP-for-spec; SGLang prefill attention mode |
| **C6** Marketed 8k–10k+ = prefill-shaped multi-token GEMM, not naive AR | **Partially true framing, dangerous as KPI** | Shape story OK; treating 10k as achievable GB10 **accepted** decode is FAIL until measured |
| Absolute ≥10k accepted tok/s @ batch=1 on GB10 | **FAIL / UNKNOWN-as-false-prior** | Contradicted by BW math + field measurements (~10², not ~10⁴) |

#### Design implications for BitNet scavenger

1. Keep Reading=Writing as a **shape invariant** (reject AR-as-center): draft → tree/block verify → accept.  
2. Success metrics on CLEAN: **accepted tok/s**, acceptance length τ, and bytes/token — **not** brochure PFLOPs or unscoped “10k class.”  
3. Expect **~2–4×** over naive AR from good MTP/EAGLE-class drafts if still BW-bound; crossing into true compute-bound Writing needs high τ **and** tiny active bytes (BitLinear/FP4 MoE grain) — still unlikely to hit 10k on 273 GB/s without toy widths.  
4. Defer absolute tok/s PASS/FAIL rows to Fact Checker with CLEAN logs; L3 only locks the **mechanism** and the **honesty flag**.

**Sources (L3):**
1. [Leviathan et al. — Fast Inference via Speculative Decoding (arXiv:2211.17192)](https://arxiv.org/html/2211.17192v2) — parallel target verify; memory vs arithmetic
2. [Medusa (arXiv:2401.10774)](https://arxiv.org/html/2401.10774v3) — multi-heads + tree attention; 2.2–2.8×
3. [EAGLE (arXiv:2401.15077)](https://arxiv.org/html/2401.15077v3) — feature draft + tree; 2.7–3.5× on 70B; τ tables
4. [Gloeckle et al. — Multi-token Prediction (arXiv:2404.19737)](https://arxiv.org/abs/2404.19737) — n heads; up to ~3× infer
5. [DeepSeek-V3 Technical Report (arXiv:2412.19437)](https://arxiv.org/pdf/2412.19437) — sequential MTP; infer speculative optional
6. [SGLang speculative decoding docs](https://docs.sglang.io/docs/advanced_features/speculative_decoding) — EAGLE-3 H100 table; prefill attention mode
7. [NVIDIA DGX Spark specifications](https://www.nvidia.com/en-us/products/workstations/dgx-spark/) — 273 GB/s; 1 PFLOP FP4 sparse footnote
8. [dgx-spark-field-notes (measured GB10)](https://github.com/sergioamsilva/dgx-spark-field-notes) — ~101 tok/s best MTP single-stream; ~300 aggregate@8
9. [ametric: Speculative Decoding deep dive](https://ametric.sh/paths/ai-systems/deep-dives/10-speculative-disaggregation/) — intensity / verify-as-prefill pedagogy
10. [Together AI — Medusa blog](https://www.together.ai/blog/medusa) — tree attention explanation (secondary)

### L4 — MoE expert grain + load-spread
_(integration / MoE)_

**Lane:** MoE / integration · scavenger wave 0 · 2026-09-04  
**Task:** expert-parallel load distribution — many experts as **throughput capacity**; **quality-first** then spread among **near-ties**; risks of **celebrity-expert collapse**.  
**Numeric claims for Fact Checker:** seed **C10** (load-spread → throughput when N large). No new PASS/FAIL invented here.

#### Hallucination strategy (pre-edit)

```
Assumption: I will hallucinate unless grounded.
Evidence:   BITNET_ARCH_RESEARCH.md L4 empty heading; plan dgx_1-bit_sidequest_05e1d3b8
            (Expert load distribution locked); DeepSeek-V3 §aux-loss-free / EP deploy;
            DeepSeekMoE fine-grain; Megatron Core MoE EP docs; Switch capacity factor;
            Shazeer 2017 routing collapse cited by DeepSeek-V3.
Hypothesis: For 10k+ class, large N is parallel expert GEMM capacity; balance must not
            corrupt affinity (quality-first); celebrity collapse is the primary throughput killer.
Falsifier:  Primary papers say aux-loss is required for quality, or EP prefers serializing
            on hot experts; or L4 already filled by peer this cycle.
Verify:     rg -n "### L4|Design rules \(10k" notes/BITNET_ARCH_RESEARCH.md
Defy:       only cite URLs opened / agent-tool fetches this cycle
```

#### Verdict (one paragraph)

For BitNet serve toward **≥10k tok/s class**, large expert count \(N\) is not only specialization — it is **expert-parallel (EP) throughput capacity**: concurrent tokens / draft positions / batch rows must land on **different experts at once** so FP4 expert GEMMs run in parallel instead of serializing on one **celebrity** expert ([plan lock](file:///Users/togi/.cursor/plans/dgx_1-bit_sidequest_05e1d3b8.plan.md); [DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2) EP prefilling EP32 + redundant experts). **Quality-first:** keep gate weights from raw affinity; push balance into **selection-only** bias / capacity / redundant replicas so LM quality is not traded for fairness ([DeepSeek-V3 aux-loss-free](https://arxiv.org/pdf/2412.19437v2); [Wang et al. 2024a](https://doi.org/10.48550/arXiv.2408.15664)). **Near-tie spread:** when several experts are within a small affinity band, prefer underloaded / different EP ranks / redundant copies — DeepSeek’s selection-vs-gating split is the production pattern; forced random reassignment (“pseudo-balance”) hurts specialization ([MAR / pseudo-balancing](https://aclanthology.org/2026.findings-acl.857.pdf)). **Celebrity collapse** (routing collapse) wastes parameters and creates EP stragglers ([Shazeer et al. 2017 via DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2); [Switch capacity factor](https://arxiv.org/pdf/2101.03961v3)).

#### 1) Experts as throughput capacity (EP view)

| Mechanism | What it does | Implication for BitNet 10k+ |
|-----------|--------------|-----------------------------|
| **Expert Parallelism** | Shard experts across ranks; All-to-All dispatch/combine | Each concurrent token can hit a different EP rank → many expert GEMMs at once ([Megatron Core MoE](https://docs.nvidia.com/megatron-core/developer-guide/0.19.0/user-guide/features/moe.html)) |
| **Prefer EP over TP on MoE layers** | Lower MoE-layer comm than TP; local permute vanishes when `EP = num_experts` | Prefer spreading experts, not tensor-splitting one expert ([Megatron guideline 4](https://docs.nvidia.com/megatron-core/developer-guide/0.19.0/user-guide/features/moe.html)) |
| **Keep EP×TP in NVLink domain** | Cross-node EP is expensive | On multi-node: PP across nodes; DualPipe / A2A overlap if EP must cross IB ([DeepSeek DualPipe](https://arxiv.org/pdf/2412.19437v2); Megatron EP A2A overlap) |
| **Batch / microbatch for EP** | Prefill wants large tokens/expert; decode is memory-bound with small tokens/expert | Prefill: EP + redundant experts; decode: EP wide + overlap attention↔dispatch ([DeepSeek-V3 §3.4](https://arxiv.org/pdf/2412.19437v2)) |
| **EP A2A can be 30–40% of step** | Must hide with overlap / DeepEP / shared-expert overlap | Shared expert compute overlaps token transfer ([Megatron](https://docs.nvidia.com/megatron-core/developer-guide/0.19.0/user-guide/features/moe.html)) |

DeepSeek-V3 prefilling: **EP32** so each expert sees a large enough batch; **32 redundant experts** so hot experts are duplicated and rearranged **within a node** without raising cross-node A2A ([DeepSeek-V3 §3.4.1](https://arxiv.org/pdf/2412.19437v2)). Decoding: **EP320**, often **1 expert/GPU**, plus GPUs hosting redundant/shared experts ([§3.4.2](https://arxiv.org/pdf/2412.19437v2)).

**Plan alignment:** “huge N is not only specialization — it is parallel capacity… different tokens / draft positions / batch rows should land on different experts at once” ([plan](file:///Users/togi/.cursor/plans/dgx_1-bit_sidequest_05e1d3b8.plan.md)).

#### 2) Quality-first, then spread among near-ties

**Problem:** Classical aux load-balance loss competes with LM loss; too large → quality drop ([DeepSeek-V3 citing Wang et al. 2024a](https://arxiv.org/pdf/2412.19437v2); [HF MoE balance review](https://huggingface.co/blog/NormalUhr/moe-balance)).

**DeepSeek-V3 pattern (canonical):**

1. Affinity \(s_{i,t}\) from router (sigmoid + normalize among selected — V3).
2. **Selection:** top-\(K_r\) on \(s_{i,t} + b_i\) (bias only for who wins).
3. **Gating:** multiply FFN by **unbiased** \(s_{i,t}\) — quality signal stays clean.
4. After each step: if expert overloaded → \(b_i \leftarrow b_i - \gamma\); underloaded → \(b_i + \gamma\).
5. Tiny **sequence-wise** aux loss only as guardrail against per-sequence extremes.
6. Result: **no token dropping** in V3 train/infer when balance holds ([DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2)).

Megatron Core exposes the same idea: `--moe-router-enable-expert-bias` / `--moe-router-bias-update-rate 1e-3` (“aux loss free”) ([Megatron MoE](https://docs.nvidia.com/megatron-core/developer-guide/0.19.0/user-guide/features/moe.html)).

**Near-tie rule (design, sourced components):**

- Sort experts by raw affinity (quality).
- If top scores are within a small ε band (near-ties), **break ties toward**: underloaded experts, different EP ranks / nodes (under node-limit), or **redundant replicas** of hot experts — *without* changing gate weights on the chosen set.
- Do **not** randomly reshuffle identical tokens across steps solely for global balance (“pseudo-balance”) — that breeds redundant experts and unstable specialization ([Memory-Aware Routing](https://aclanthology.org/2026.findings-acl.857.pdf); [SimBal / similarity-preserving](https://arxiv.org/html/2506.14038v2)).
- Optional systems path: MaxScore / flow-based assignment maximizes affinity under capacity (quality under hard load caps) ([MaxScore Routing](https://arxiv.org/html/2508.12801v1)).

**Fine grain amplifies near-tie usefulness:** DeepSeekMoE splits FFN width → \(mN\) experts, activate \(mK\) → combinatorial explosion of committees (e.g. 16 choose 2 vs 64 choose 8) so many near-equally-good committees exist to spread load without diluting the best specialists ([DeepSeekMoE](https://arxiv.org/html/2401.06066); V3 config: **1 shared + 256 routed, top-8, expert intermediate 2048** ([DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2))).

#### 3) Celebrity-expert collapse — risks & mitigations

| Risk | Mechanism | Mitigations (sourced) |
|------|-----------|----------------------|
| **Routing / celebrity collapse** | Early lucky expert gets more tokens → better → attracts more tokens; others starve ([Shazeer 2017 via DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2); [EngineersOfAI router notes](https://engineersofai.com/docs/llms/mixture-of-experts/Router-Mechanisms)) | Aux-loss-free bias controller; light seq-aux; shared experts for common knowledge ([DeepSeekMoE shared isolation](https://arxiv.org/html/2401.06066)) |
| **EP stragglers** | Hot expert’s GPU finishes last → whole All-to-All waits | Capacity factor + drop/pad ([Switch](https://arxiv.org/pdf/2101.03961v3); Megatron `--moe-expert-capacity-factor`); **or** dropless + bias so CF≈1 ([DeepSeek-V3 no drop](https://arxiv.org/pdf/2412.19437v2)); **redundant experts** at serve ([V3 §3.4](https://arxiv.org/pdf/2412.19437v2)) |
| **OOM early train** | Router undertrained → severe imbalance | Temporary capacity_factor≈1.0 or more TP / less EP for first ~200 steps ([Megatron MoE package notes](https://docs.nvidia.com/megatron-core/developer-guide/0.15.0/api-guide/moe.html)) |
| **Over-balancing** | Heavy aux → routers ignore content; experts become interchangeable | Prefer bias-on-selection; keep α tiny; monitor specialization / domain load skew ([DeepSeek-V3 Fig.9 discussion](https://arxiv.org/pdf/2412.19437v2); [APXML specialization collapse](https://apxml.com/courses/mixture-of-experts/chapter-3-moe-training-dynamics-optimization/expert-specialization-collapse)) |
| **Comm hotspots** | Token fans to many nodes | Device/node-limited routing: ≤\(M\) devices/nodes per token (\(M{\ge}3\) V2; V3 ≤4 nodes) + device/comm balance losses (V2) or node-limited + DualPipe (V3) ([DeepSeek-V2](https://arxiv.org/html/2405.04434v5); [DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2)) |
| **Serve celebrity** | Online traffic skew ≠ train batch | Periodic load stats → duplicate hot experts; rearrange within node; explore dynamic redundancy ([DeepSeek-V3 §3.4](https://arxiv.org/pdf/2412.19437v2)) |

**Capacity factor (Switch):**  
\(\text{expert\_capacity} = (\text{tokens}/\text{experts}) \times \text{capacity\_factor}\). CF \(>1\) buffers imbalance; excess tokens **dropped** (residual). Empirically Switch likes **CF 1.0–1.25** with aux balance ([Switch Transformers](https://arxiv.org/pdf/2101.03961v3); [HF MoE explainer](https://huggingface.co/blog/moe)). Megatron: `capacity = num_tokens_per_rank * topk * capacity_factor / num_experts` when EP>1 ([Megatron MoE API](https://docs.nvidia.com/megatron-core/developer-guide/0.15.0/api-guide/moe.html)).

#### 4) Expert grain vs load-spread (map)

| Grain | Prior | Load-spread note |
|-------|-------|------------------|
| Near-map ~0.61B / expert, N→16k | Plan R0–R8 | Fat experts → fewer concurrent GEMMs unless batch/draft width is large; **must** still fan draft/verify across experts |
| DeepSeek-V3 intermediate **2048**, N=256 routed, k=8 | Production MoE | Fine enough for EP32/320 + node limit 4 |
| Far-map **10M** (plan default) / **1M** optional | Plan | Huge \(N\) → EP capacity + near-ties abound; raise \(k\) when experts shrink so active mass stays ~10B |

Shared experts: always-on common knowledge → routed experts stay distinct → less forced celebrity on “generic” tokens ([DeepSeekMoE](https://arxiv.org/html/2401.06066)).

#### Design rules (10k+ class, large \(N\))

1. **N = capacity, not decoration.** Concurrent positions (batch × draft × verify) must target **disjoint experts / EP ranks** whenever affinity allows; never serialize independent tokens on one celebrity ([plan](file:///Users/togi/.cursor/plans/dgx_1-bit_sidequest_05e1d3b8.plan.md); Megatron EP).
2. **Quality-first affinity; balance on selection.** Gate with raw \(s\); balance with \(b_i\) / capacity / redundancy — not a heavy aux that warps quality ([DeepSeek-V3](https://arxiv.org/pdf/2412.19437v2)).
3. **Near-tie → spread.** Within ε of top affinity, prefer underloaded / other EP ranks / redundant replicas; avoid random pseudo-balance ([DeepSeek selection/gating split](https://arxiv.org/pdf/2412.19437v2); [MAR](https://aclanthology.org/2026.findings-acl.857.pdf)).
4. **Detect celebrity early.** Track tokens/expert, max/mean load, EP wait time; alarm if a few experts dominate (routing collapse) ([Shazeer 2017 via V3](https://arxiv.org/pdf/2412.19437v2)).
5. **Serve redundancy for hot experts.** Duplicate celebrities; rearrange within NVLink domain; refresh on a timer from live stats ([DeepSeek-V3 §3.4](https://arxiv.org/pdf/2412.19437v2)).
6. **Node/device-limited routing.** Cap nodes/devices per token (\(M{\approx}3{-}4\)) so A2A stays overlapable ([DeepSeek-V2/V3](https://arxiv.org/pdf/2412.19437v2)).
7. **Prefill vs decode EP shapes differ.** Prefill: fewer GPUs, many tokens/expert, EP medium + pad/redundant. Decode: many GPUs, 1 expert/GPU class, hide A2A behind attention ([DeepSeek-V3 §3.4](https://arxiv.org/pdf/2412.19437v2)).
8. **Capacity policy:** prefer **dropless + bias** when possible; else CF∈[1.0, 1.25] and drop lowest affinity overflow ([Switch](https://arxiv.org/pdf/2101.03961v3); Megatron). Early train may need hard CF≈1 to avoid OOM.
9. **Fine grain + shared trunk.** Shrink expert width as \(N\) grows (plan 10M); keep shared/hot FP4 trunk; raise \(k\) so active ≈≤10B ([DeepSeekMoE](https://arxiv.org/html/2401.06066); plan).
10. **Reading=Writing uses the same fan-out.** Draft block + parallel verify must issue a **union of experts** once per block and run GEMMs concurrently — load-spread is a serve invariant for 10k+ class, not a train-only concern ([plan](file:///Users/togi/.cursor/plans/dgx_1-bit_sidequest_05e1d3b8.plan.md); C10).
11. **Overlap shared-expert compute with EP transfer.** Free bandwidth while specialists run ([Megatron shared-expert overlap](https://docs.nvidia.com/megatron-core/developer-guide/0.19.0/user-guide/features/moe.html); DeepSeek-V2 train note).
12. **Do not steal I/O L2 for fat celebrities.** Pin embed/LM-head; stream/stage near-map experts; far-map ≤10M may sit in leftover L2 after I/O ([plan cache hierarchy](file:///Users/togi/.cursor/plans/dgx_1-bit_sidequest_05e1d3b8.plan.md); L5 math).

#### Sources (L4)

1. [DeepSeek-V3 Technical Report (arXiv:2412.19437v2)](https://arxiv.org/pdf/2412.19437v2) — aux-loss-free bias, node-limited routing, no token drop, EP32/EP320, redundant experts, DualPipe  
2. [Wang et al. 2024a — Auxiliary-loss-free load balancing (arXiv:2408.15664)](https://doi.org/10.48550/arXiv.2408.15664)  
3. [DeepSeekMoE (arXiv:2401.06066)](https://arxiv.org/html/2401.06066) — fine-grained segmentation + shared expert isolation  
4. [DeepSeek-V2 (arXiv:2405.04434)](https://arxiv.org/html/2405.04434v5) — device-limited routing; expert/device/comm balance losses; device token-drop  
5. [Megatron Core — Mixture of Experts (0.19 user guide)](https://docs.nvidia.com/megatron-core/developer-guide/0.19.0/user-guide/features/moe.html) — EP guidelines, expert bias, DeepEP, A2A overlap  
6. [Megatron Core — MoE API (0.15)](https://docs.nvidia.com/megatron-core/developer-guide/0.15.0/api-guide/moe.html) — capacity formula, dropless vs CF, early-train OOM  
7. [Switch Transformers (arXiv:2101.03961)](https://arxiv.org/pdf/2101.03961v3) — capacity factor, dropped tokens, aux balance  
8. [Hugging Face — Mixture of Experts Explained](https://huggingface.co/blog/moe) — capacity / CF tradeoffs  
9. [HF blog — MoE load balancing pitfalls](https://huggingface.co/blog/NormalUhr/moe-balance) — aux vs bias timeline  
10. [Shazeer et al. 2017 — Outrageously Large Neural Networks](https://arxiv.org/abs/1701.06538) — routing collapse (via DeepSeek-V3 citation)  
11. [Memory-Aware Routing / pseudo-balancing (ACL Findings)](https://aclanthology.org/2026.findings-acl.857.pdf)  
12. [MaxScore Routing (arXiv:2508.12801)](https://arxiv.org/html/2508.12801v1)  
13. [Similarity-preserving load balance (arXiv:2506.14038)](https://arxiv.org/html/2506.14038v2)  
14. Plan lock: [`dgx_1-bit_sidequest_05e1d3b8.plan.md`](file:///Users/togi/.cursor/plans/dgx_1-bit_sidequest_05e1d3b8.plan.md) — expert load distribution + celebrity avoid for ≥10k class  

### L5 — ≤20GB FP4 RAM model + I/O cache fit
_(compression / RAM)_

**Lane:** Compression/RAM · scavenger wave 0 · 2026-09-04  
**Sources:** plan seeds C7/C8 in `notes/BITNET_FACTCHECK.md`; L2/L3 sizes treated as plan assumptions (~24MB each) pending L2 hardware lane PASS.  
**Wave-1 unique-param north star (1B→10M unique @ NVFP4 hot):** [`COMPRESSION_NORTH_STAR.md`](COMPRESSION_NORTH_STAR.md) · [`COMPRESSION_CATALOG.md`](COMPRESSION_CATALOG.md) Lane C · [`COMPRESSION_NOVEL.md`](COMPRESSION_NOVEL.md) — unique-count KPI is orthogonal to serve quality; byte arith below ≠ measured KD/task. Hot dtype lock: [`NVFP4_LOCK_APPLICABILITY.md`](NVFP4_LOCK_APPLICABILITY.md).

#### Hallucination strategy (pre-edit)

```
Assumption: I will hallucinate unless grounded.
Evidence:   notes/BITNET_FACTCHECK.md:C7–C8; notes/BITNET_ARCH_RESEARCH.md L5 heading;
            notes/BITNET_RESEARCH_TASKS.md L5 line
Hypothesis: FP4 bytes = N×0.5; 10B active ≈5GB; 0.61B expert ≈305MB ≫ L2/L3;
            10M/1M experts fit L2; ≤20GB hot has ~15GB headroom after weights
Falsifier:  Any PASS source showing FP4 packing ≠0.5 B/param, or L2/L3 ≠~24MB,
            or expert grain ≠0.61B/10M/1M as plan-stated
Verify:     python3 one-liner: print(10e9*0.5/1e9, 0.61e9*0.5/1e6, 10e6*0.5/1e6)
Defy:       memory-recall + output-compare + diagnose if unsure
```

#### Unit convention

| Symbol | Meaning |
|--------|---------|
| \(N\) | parameter count |
| \(b\) | bits/param (FP4 ⇒ \(b=4\)) |
| \(B_{\text{param}}\) | bytes/param = \(b/8 = 0.5\) |
| \(V\) | vocab size |
| \(D\) | model / embedding width |
| \(E\) | params in one expert |
| \(H_{\text{hot}}\) | hot UMA budget = 20 GiB-class ≈ \(20 \times 10^9\) B (decimal GB used below) |

**Core weight equation (FP4, no scale overhead):**

\[
W_{\text{bytes}}(N) = N \cdot \frac{b}{8} = N \cdot 0.5
\]

Scale/zp metadata and sparse/index overhead are **excluded** here → mark UNKNOWN until packing format is fixed (see L5-U1).

#### 1) Active ~10B @ FP4 vs ≤20GB hot

\[
W_{\text{act}} = 10\times10^9 \cdot 0.5 = 5.0\times10^9\,\text{B} = \mathbf{5.00\,\text{GB}}
\]

\[
H_{\text{residual}} = 20\,\text{GB} - W_{\text{act}} = \mathbf{15.00\,\text{GB}}
\]

**Fit conclusion:** active FP4 weights alone consume **25%** of the ≤20GB hot budget → **fits with large headroom** for embed, KV, activations, workspace (C7 directionally confirmed by arithmetic; quality/overhead still UNKNOWN).

#### 2) Embed + LM head — \(V \times D \times 0.5\)

Tied embed (= LM head share):

\[
W_{\text{tied}} = V \cdot D \cdot 0.5
\]

Untied (separate embed + LM head):

\[
W_{\text{untied}} = 2 \cdot V \cdot D \cdot 0.5 = V \cdot D
\]

| Example (illustrative \(V,D\)) | Tied \(W\) | Untied \(W\) | vs 15GB residual |
|--------------------------------|------------|--------------|------------------|
| Llama-3-ish \(V{=}128256,\,D{=}4096\) | **262.7 MB** | **525.3 MB** | trivial |
| DeepSeek-V3-ish \(V{=}129280,\,D{=}7168\) | **463.3 MB** | **926.7 MB** | trivial |
| Qwen2-large-ish \(V{=}152064,\,D{=}8192\) | **622.9 MB** | **1.25 GB** | still ≪ residual |
| Small \(V{=}32000,\,D{=}4096\) | **65.5 MB** | **131.1 MB** | trivial |

After Llama-3-ish tied + active:

\[
20 - 5.00 - 0.263 \approx \mathbf{14.74\,\text{GB}}
\]

left for KV / acts / MoE staging / CUDA workspace.

#### 3) Near-map expert ~0.61B @ FP4 vs L2 / L3

\[
W_{0.61\text{B}} = 0.61\times10^9 \cdot 0.5 = 3.05\times10^8\,\text{B} = \mathbf{305\,\text{MB}}
\]

Plan-assumed banks (pending L2 lane): \(L2 \approx L3 \approx 24\,\text{MB}\).

\[
\frac{W_{0.61\text{B}}}{L2} = \frac{305}{24} \approx \mathbf{12.7}\times \quad(\text{same order vs } L3)
\]

**Fit conclusion:** whole-expert residency of a **0.61B** FP4 expert in L2 or L3 is **impossible** — must stream / tile / GDS-stage (C8). Near-map I/O is bandwidth-bound at expert grain, not cache-resident.

#### 4) Far-map expert grain — 10M / 1M @ FP4

\[
W_{10\text{M}} = 10\times10^6 \cdot 0.5 = 5.0\times10^6\,\text{B} = \mathbf{5.00\,\text{MB}}
\]

\[
W_{1\text{M}} = 1\times10^6 \cdot 0.5 = 5.0\times10^5\,\text{B} = \mathbf{0.50\,\text{MB}}
\]

| Expert | FP4 size | Fit in ~24MB L2? | Fit in ~24MB L3? | Headroom (L2) |
|--------|----------|------------------|------------------|---------------|
| 10M | 5.00 MB | **YES** (~4.8×) | **YES** | ~19 MB |
| 1M | 0.50 MB | **YES** (~48×) | **YES** | ~23.5 MB |
| 0.61B (near) | 305 MB | **NO** (~12.7× over) | **NO** | n/a |

**Fit conclusion:** far-map **10M / 1M** experts are the first grains that can sit **whole** in L2/L3-class SRAM; near-map **0.61B** cannot. Hot-path design should treat ≤10M as cache-friendly tiles and 0.61B as streamed.

#### 4b) T5 — NVFP4 unique-param residency (north star + T4 arith)

_Needle: `OVERSEER_COMPRESSION_T5_SERVE_2026_09_06`_  
**Lane:** serve/residency sketch only · parallel with train · **does not** rewrite LOCKED recipe.  
**Sources:** L5 §§3–4 above; [`COMPRESSION_NORTH_STAR.md`](COMPRESSION_NORTH_STAR.md) \(S{=}N/U{\approx}100\) @ \(U{=}10^7\); T4 stamp [`t4_scale_result.json`](compression_artifacts/t4_scale_result.json) (`OVERSEER_COMPRESSION_T4_SCALE_2026_09_06`); dtype notes [`NVFP4_LOCK_APPLICABILITY.md`](NVFP4_LOCK_APPLICABILITY.md) (~4.5 bit/value + scales); smoke `scripts/compression_t5_serve.py`.

North-star unique store is the **same grain** as far-map **10M** in §4 — re-expressed as **unique params** under locked **NVFP4**, not a new architecture claim:

| Store | Unique \(U\) | Raw NVFP4 \(U{\times}0.5\) | Packed sketch ~4.5 bit/val | Fit ~24 MB L2/L3? |
|-------|--------------|----------------------------|----------------------------|-------------------|
| North-star unique (1B→10M) | \(10^7\) | **5.00 MB** | **~5.63 MB** (+ scales UNKNOWN / L5-U1) | **YES** (~4–4.8× headroom) |
| Logical 1B if all unique | \(10^9\) | **500 MB** | ~563 MB | **NO** — stream / share required |
| Near-map 0.61B (L5 §3) | \(0.61{\times}10^9\) | **305 MB** | — | **NO** (unchanged) |
| T4 toy \(N{=}10^7\) row | \(U{=}74576\) | **~37.3 KB** | — | **YES** (trivial; arith \(S{\approx}134\)) |
| rung0 skeleton (toy) | \(U{=}25076\) | **~12.5 KB** pack field | — | **YES** (toy; \(S{\approx}4\) — not north-star) |

**Honesty locks (arith ≠ quality):**
- Byte fit of a **10M-unique NVFP4** body in L2-class SRAM is **arithmetic**, same class as L5 far-map §4 — **not** a measured 1B→10M KD/task serve proof.
- T4 `S≥100` / ratio-stable is **unique-count arith** on toys (`train_unlocked` was false at stamp); do not upgrade to measured quality.
- Stock **native NVFP4 MoE** on sm121 remains immature (**C27** / L7) — residency sketch ≠ production-native MoE GEMM readiness.
- Optional cold 1-bit path is **not** the locked hot dtype; do not mix 1-bit MB figures into NVFP4 serve claims.

**Smoke:** `python3 scripts/compression_t5_serve.py` reads `notes/compression_artifacts/rung0_model_skeleton.json` and prints the table above (no architecture churn, no 1B train).

#### 5) Hot budget sketch (weights-only + typical tied embed)

\[
\begin{aligned}
W_{\text{hot,min}} &= W_{\text{act}} + W_{\text{tied}} \\
&\approx 5.00\,\text{GB} + 0.26\text{–}0.62\,\text{GB} \\
&\approx \mathbf{5.3\text{–}5.6\,\text{GB}} \ll 20\,\text{GB}
\end{aligned}
\]

Remaining ~14–15GB must cover: KV cache, activations, expert staging buffers, GDS bounce tiles, allocator fragmentation. **Does not** prove end-to-end 1Q@20GB — only that **FP4 active weights are not the bottleneck** under plan numbers.

#### L5 deliverable checklist

- [x] Active 10B FP4 → 5.00 GB; ≤20GB residual 15.00 GB  
- [x] Embed/LM \(V{\times}D{\times}0.5\) worked examples  
- [x] Near 0.61B → 305 MB ≫ 24MB L2/L3  
- [x] Far 10M/1M → 5.00 / 0.50 MB fit L2/L3  
- [x] T5 NVFP4 unique residency cross-link @ 10M / T4 toys (`OVERSEER_COMPRESSION_T5_SERVE_2026_09_06`)  
- [x] New numeric claims → `BITNET_FACTCHECK.md` UNKNOWN rows  

#### Kit RSS audit (peer-6 compression · 2026-09-04) — wake vs resident

Analog to L5 “stream large experts”: peer wake must not parse a full conversation buffer for a boolean role check.

| Probe | BEFORE (MB Δ) | AFTER (MB Δ) | Note |
| --- | --- | --- | --- |
| `has_new_assistant_since_dispatch` 20× fat EOF | 0.250 | **0.016** (−0.234) | 64 KiB reverse + `_jsonl_role_with_content` (no text join) · `scripts/peer_transcript.py` |
| `read_conversation` 256 KiB | 0.891 | — | still needed for prompt format; not for `output_generated` gate |
| hub `read_transcript_meta` 6.3MB JSONL cold | 44.250 | **2.281** (−41.97) | stream `_count_file_lines` + `_meta_memo` · `OVERSEER_STREAM_TRANSCRIPT_META_MEMO_2026_09_04` · hub `scripts/peer_transcript.py` |
| hub meta warm ×50 (same mtime/size) | (re-read +481 peak) | **0.000** | memo hit — never re-stream |
| Hub live `peer_loop` / `automation_improve` RSS | ~679 / ~1155 | — | **steady-state resident** — separate from wake spike; hub `has_new` still calls `read_conversation` until merge |

Falsifier for wake claim: unittest `test_has_new_assistant_slim_eof` + identical boolean vs extract path.

### L6 — Chinese open priors (DeepSeek / Qwen / Kimi / GLM MTP+MoE)
_(output research — Chinese-priors lane; hallucination guard: only published numbers)_

**Scope:** open Chinese MoE / MLA / MTP priors useful for **FP4 MoE + MTP distill/serve**. No unpublished or inferred FP4 footprints claimed. Low-prec notes only where authors publish (e.g. FP8 train / block-fp8 weights).

#### Catalog (expert grain · active params · MTP)

| Model | Total / active | Expert grain | MTP / serve hook | Open refs |
| --- | --- | --- | --- | --- |
| **DeepSeek-V3** | 671B / **37B** per token | MoE after first **3** dense layers; **1 shared + 256 routed**; expert intermediate **2048**; **top-8** routed; node-limited routing (≤4 nodes); **MLA** (128 heads, \(d_h=128\), KV compress \(d_c=512\)) | **MTP depth \(D=1\)** (sequential causal modules, shared emb/out head); discard MTP at infer or reuse for speculative decode; published 2nd-token accept **~85–90%**, ~**1.8×** TPS; aux-**loss-free** load balance + sigmoid affinity | [DeepSeek-V3 Technical Report](https://arxiv.org/pdf/2412.19437) · [github.com/deepseek-ai/DeepSeek-V3](https://github.com/deepseek-ai/DeepSeek-V3) |
| **Qwen3-MoE** | **30B-A3B:** ~30.5B / **~3.3B** (HF); **235B-A22B:** **235B / 22B** | **128** routed experts, **8** active/token; **no shared experts** (unlike Qwen2.5-MoE); fine-grained expert segmentation; 30B: 48 layers, `moe_intermediate_size=768`; 235B: 94 layers | **No MTP** described in Qwen3 tech report; strong-to-weak **logit distill** (+ think/no_think) is the published student path | [Qwen3 Technical Report](https://arxiv.org/html/2505.09388v1) · [HF Qwen3MoE](https://huggingface.co/docs/transformers/en/model_doc/qwen3_moe) · [Qwen3-30B-A3B config](https://huggingface.co/Qwen/Qwen3-30B-A3B) |
| **Qwen1.5-MoE-A2.7B** (grain prior) | **14.3B** total / **2.7B** active | Config defaults: **60** routed, **top-4**, shared expert `intermediate_size=5632`, routed `moe_intermediate_size=1408` | No MTP in HF/Qwen2MoE docs | [HF Qwen2MoE](https://huggingface.co/docs/transformers/main/model_doc/qwen2_moe) |
| **Kimi K2** | **1.04T** (≈1T) / **32B** | DeepSeek-like MLA MoE; **384** experts, **8** selected, **1** shared; expert dim **2048**; hidden **7168**; **64** attn heads; **61** layers (**1** dense); sparsity **48** (=384/8) | **# MTP layers = 0** in published arch table vs DeepSeek/GLM; checkpoints shipped **block-fp8** (HF); vLLM/SGLang/TRT-LLM | [Kimi K2 paper](https://arxiv.org/html/2507.20534v2) · [MoonshotAI/Kimi-K2 README](https://github.com/MoonshotAI/Kimi-K2) · [kimi.ai blog](https://www.kimi.ai/blog/kimi-k2) |
| **GLM-4.5 / Air** | **355B / 32B**; Air **106B / 12B** | **Deeper/narrower** vs DeepSeek/Kimi: 4.5 → **160** experts, Air → **128**; **8** active/token; **1** shared; MoE intermediate **1536** / Air **1408**; 89 / 45 MoE layers; GQA + partial RoPE; loss-free balance + **sigmoid** gates | **1 MTP layer** = extra **MoE** block for speculative decode (Gloeckle-style); open weights HF/ModelScope; vLLM/SGLang | [GLM-4.5 paper](https://arxiv.org/html/2508.06471) · [z.ai/blog/glm-4.5](https://z.ai/blog/glm-4.5) · [github.com/zai-org/GLM-4.5](https://github.com/zai-org/GLM-4.5) |

**Cross-check (same table in GLM-4.5 paper):** DeepSeek-V3 MTP=1, Kimi K2 MTP=0, experts 256 vs 384, active 37B vs 32B — treat GLM Table 1 as the multi-lab comparison surface ([arXiv HTML](https://arxiv.org/html/2508.06471)).

**Explicit non-claims:** no published **FP4** W/A sizes or ≤20GB resident numbers for these full priors; DeepSeek reports **FP8** training; Kimi publishes **block-fp8** weights — useful for low-prec *serve* engineering, not as BitNet FP4 proofs.

#### Leverage table (model → what to steal for FP4 MoE + MTP distill/serve)

| Prior | Steal for BitNet / GB10 lane |
| --- | --- |
| **DeepSeek-V3** | **Canonical MTP+MoE stack:** sequential \(D=1\) MTP with shared emb/LM-head (train densify + optional speculative); **MLA** KV compress for resident budget; fine expert grain **2048** + **1 shared / 256 routed / top-8**; aux-loss-free + node-limited routing for load-spread; published accept-rate / TPS as MTP verify targets |
| **Qwen3-MoE** | **Small-active MoE skeleton** for ≤20GB experiments: **128/8**, **no shared**, tiny expert FFN (**768** on 30B-A3B); **3.3B / 22B** active scales as distill students; **on-policy logit distill** recipe (think/no_think) instead of inventing MTP |
| **Qwen1.5-MoE-A2.7B** | **Upcycled fine-grain + shared-expert** micro prior for unit tests / FP4 GEMM MoE kernels (60+shared, top-4, 2.7B active) |
| **Kimi K2** | **Sparsity scaling** (more experts @ fixed top-8 → better loss); **MLA + fewer heads (64)** for long-context decode FLOPs; **shared+384** ultra-sparse EP layout; **block-fp8** checkpoint + production serve stacks — **not** MTP (explicitly 0) |
| **GLM-4.5 / Air** | **MTP-as-MoE-layer** alternate to DeepSeek sequential TRM modules (steal if serve prefers one extra MoE expert block); **deep/narrow** MoE (more layers, smaller expert dim **1536**, **160** experts) for reasoning-biased grain; Air **12B** active as mid-size FP4-MoE candidate; hybrid think/direct modes for distill targets |

**Distill/serve playbook (sourced patterns only):**
1. **MTP teacher:** DeepSeek sequential MTP or GLM MoE-MTP layer → student keeps main trunk; MTP discarded or kept as draft head ([DeepSeek-V3 §MTP](https://arxiv.org/pdf/2412.19437), [GLM-4.5 §2.1](https://arxiv.org/html/2508.06471)).
2. **MoE grain for FP4 hot path:** prefer published expert intermediate dims (768 / 1408–1536 / 2048) and top-8 routing; do not invent expert counts.
3. **Attention resident:** MLA (DeepSeek/Kimi) vs GQA (Qwen/GLM) — pick from open configs, not rumor.
4. **Low-prec weights:** start from Kimi **block-fp8** / DeepSeek **FP8 train** literature; FP4 BitNet mapping is **this kit’s** work, not claimed by these papers.

#### Sources (L6)
- [DeepSeek-V3 Technical Report (arXiv:2412.19437)](https://arxiv.org/pdf/2412.19437) / [v2 PDF](https://arxiv.org/pdf/2412.19437v2)
- [Qwen3 Technical Report (arXiv:2505.09388)](https://arxiv.org/html/2505.09388v1)
- [Hugging Face — Qwen3MoE](https://huggingface.co/docs/transformers/en/model_doc/qwen3_moe)
- [Hugging Face — Qwen2MoE / Qwen1.5-MoE-A2.7B defaults](https://huggingface.co/docs/transformers/main/model_doc/qwen2_moe)
- [Kimi K2: Open Agentic Intelligence (arXiv:2507.20534)](https://arxiv.org/html/2507.20534v2)
- [MoonshotAI/Kimi-K2 README](https://github.com/MoonshotAI/Kimi-K2)
- [Kimi K2 blog](https://www.kimi.ai/blog/kimi-k2)
- [GLM-4.5 Technical Report (arXiv:2508.06471)](https://arxiv.org/html/2508.06471)
- [GLM-4.5 blog (z.ai)](https://z.ai/blog/glm-4.5)
- [zai-org/GLM-4.5](https://github.com/zai-org/GLM-4.5)


### L7 — GDS stream + parallel verify kernels on SM 12.1
_(backend / kernels — 2026-09-04 scavenger)_

**Protocol:** hallucination guard. Claims below are source-tied. Anything not measured on CLEAN this wave is **UNKNOWN** or **FAIL** as labeled.

#### Verdict (one paragraph)

On **DGX Spark / GB10**, classic **GPUDirect Storage fast-path is not supported** — treat GDS-as-serve-I/O as **vapor for this SoC**. Expert / cold-weight “streaming” must be **NVMe → host-accessible UMA (pinned / page cache / mmap) → GPU kernels over C2C**, not `cuFile` DMA into `cudaMalloc` device memory. **SM 12.1 native FP4 GEMM is real silicon** (warp-level `mma.sync` / `kind::mxf4nvf4`, target `sm_121a`), but **production MoE serve today often still dequants via Marlin**; native FP4 MoE grouped-GEMM in stock vLLM/FlashInfer is **UNKNOWN / immature**. Parallel verify for Reading=Writing should plan **FP4 GEMM on-chip**, not GDS.

#### GDS on Spark / Grace-Blackwell (GB10)

| Claim | Status | Evidence |
|-------|--------|----------|
| GDS fast-path on Spark | **FAIL (unsupported)** | User `gdscheck`: `NVIDIA GB10: Model Not Supported`, NVMe/NVMeOF Unsupported, `use_compat_mode: true` (CUDA 13.0, libcufile 1.15.1.6, driver 580.95.05). NVIDIA moderator: “GDS is not supported on Spark” citing FAQ. ([GDS support for DGX Spark](https://forums.developer.nvidia.com/t/gds-support-for-dgx-spark/350328)) |
| GPUDirect RDMA on Spark | **FAIL (unsupported)** | Official FAQ + Porting Guide: `cudaMalloc` memory for iGPU CUDA contexts is **not coherently accessible** by CPU or PCIe devices → no nvidia-peermem / dma-buf / GDRCopy. Introspect `CU_DEVICE_ATTRIBUTE_GPU_DIRECT_RDMA_SUPPORTED` / `DMA_BUF_SUPPORT`; fallback `cudaHostAlloc` + `ib_reg_mr`. ([DGX Spark / GB10 FAQ](https://forums.developer.nvidia.com/t/dgx-spark-gb10-faq/347344), [DGX Spark Porting Guide](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/dgx-spark-porting-guide.pdf)) |
| Spark-only vs GH200/GB200 | **PASS (as stated by NVIDIA)** | Moderator: GDS/GPUDirect limitation “applies to Gb10 Spark only” — not blanket all C2C systems. ([GDS forum thread](https://forums.developer.nvidia.com/t/gds-support-for-dgx-spark/350328)) |
| Timeline for GDS enablement on GB10 | **UNKNOWN** | No public roadmap in cited sources; architectural UMA/iGPU coherency wording suggests firmware alone is unlikely to flip classic GDS. |

**Architecture implication (cite-backed, not brochure):** GB10 has **no discrete GPU HBM**; CPU+GPU share **128 GB LPDDR5x UMA** (~273 GB/s) over C2C. NVMe sits on **PCIe**; classic GDS wants storage DMA into GPU-local buffers. On Spark those `cudaMalloc` buffers are **not** PCIe-DMA-coherent → GDS/RDMA fail for the same reason. ([Porting Guide §4.6.1](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/dgx-spark-porting-guide.pdf), [FAQ GPUDirect RDMA](https://forums.developer.nvidia.com/t/dgx-spark-gb10-faq/347344), community topology notes on no GPU-local DRAM for NIC DMA ([GPU Direct RDMA clustering thread](https://forums.developer.nvidia.com/t/enabling-gpu-direct-rdma-for-dgx-spark-clustering/352051)).

#### NVMe → UMA DMA — what to actually build

**Do (CLEAN host):**

1. **Cold experts / BitNet packs on NVMe** with `O_DIRECT` or `mmap` into **CPU-visible** buffers (`cudaHostAlloc` / pinned host / file-backed pages).
2. Let GPU kernels **read UMA host pointers** (or stage with `cudaMemcpyAsync` into hot expert slots) — same virtual address space is the UMA pitch; avoid assuming zero-copy from NVMe into `cudaMalloc`.
3. **Expert cache = pinned-host LRU + small GPU scratch** (vLLM-class `CachedWeightProvider` / `--moe-expert-cache-size` pattern: experts in CPU pinned memory, N hottest mirrored on GPU; needs eager path when dynamic). ([vLLM MoE offload commit](https://github.com/vllm-project/vllm/commit/71ed1fc8086778f086417f62b5a6dcbfe3cb0d56))
4. Prefetch next experts on a **host I/O thread** overlapped with current FP4 verify GEMM — **not** `cuFile` GDS.

**Do not:**

- Gate T0 / BitNet serve on `nvidia-gds` / `gdscheck` green.
- Assume GH200-style “storage DMA into HBM” exists on Spark.
- Pin whole 0.61B FP4 experts in L2/L3 (already C8) or expect GDS to hide that.

**UNKNOWN until CLEAN measure:** end-to-end NVMe→pinned→kernel GB/s vs LPDDR STREAM (~273 GB/s device), and whether `cudaHostAlloc`-registered RDMA helps multi-Spark expert pull (FAQ suggests it for NIC paths only).

#### SM 12.1 / GB10 CUDA for FP4 GEMM + expert streaming

| Topic | Known | UNKNOWN |
|-------|-------|---------|
| Arch ID | GB10 = **compute capability 12.1 (`sm_121`)**; family with SM120 consumer Blackwell, **≠** datacenter `sm_100` | Exact official “SM 12.1 feature table” beyond community + Colfax — treat PTX ISA docs as source of truth when coding |
| FP4 programming model | SM12x uses **warp-level `mma.sync`**, **not** `tcgen05`/TMEM. SM10x kernels **do not run** on SM12x. NVFP4: `kind::mxf4nvf4`, shape **m16n8k64**, block scales (e.g. `scale_vec::4X` + `ue4m3`). ([Colfax NVFP4 SM12x](https://research.colfax-intl.com/cutlass-tutorial-nvfp4-blockscaled-gemm-on-nvidia-rtx-pro-blackwell-gpus-sm12x/)) | Whether every GB10 SKU matches Colfax SM120 numbers 1:1 (clocks/SM count differ) |
| Build gate | Target **`sm_121a`** (plain `sm_121` → INVALID_PTX / missing block_scale). Native path needs **PTX 9.1+** → **CUDA 13.1+ driver** for JIT (13.0 assemble-then-fail reported). ([modular#6597](https://github.com/modular/modular/issues/6597), [nvfp4bench DESIGN](https://github.com/secYOUre/nvfp4bench/blob/main/DESIGN.md)) | Ship-default DGX OS driver version on CLEAN at T0 — **verify on box** |
| Silicon peak | Community microbench: packed `mxf4nvf4` dense ~**511 TFLOPS**, sparse 2:4 ~**1 PFLOP** issue-rate; real GEMMs bandwidth/thermal limited (~**356–386 TFLOPS** dense CUTLASS class; LPDDR **~273 GB/s**). ([nvfp4bench DESIGN](https://github.com/secYOUre/nvfp4bench/blob/main/DESIGN.md), forum CUTLASS 356 TFLOPS cites in DESIGN) | CLEAN-box replicate — **UNKNOWN until measure** |
| Serve stack FP4 today | Production MoE often **Marlin W4A16 dequant** (`--moe-backend marlin`); FlashInfer CUTLASS FP4 MoE / SM100 paths crash or mis-dispatch on sm120/121 (`Failed to run cutlass FP4 gemm on sm120`). Dense layers may use FLASHINFER_CUTLASS. ([DGX Spark + vLLM playbook](https://vlaicu.io/posts/dgx-vllm/), [SM121 native NVFP4 forum](https://forums.developer.nvidia.com/t/sm121-gb10-native-nvfp4-compute-seeking-guidance-on-software-support/364607)) | Official timeline for **native** NVFP4 MoE grouped GEMM in stock vLLM/FlashInfer — **UNKNOWN** |
| Parallel verify | Reading=Writing wants **draft block + parallel FP4 verify GEMMs**. Correct kernel family = **SM12x `mma.sync` NVFP4** (CUTLASS/CuTe SM12x path), optionally PDL/CLC for dependency overlap ([Colfax](https://research.colfax-intl.com/cutlass-tutorial-nvfp4-blockscaled-gemm-on-nvidia-rtx-pro-blackwell-gpus-sm12x/)). Verify does **not** need GDS. | Accept-rate γ / tok/s on CLEAN — C6/C9 **UNKNOWN** |

#### Practical serve stack — CLEAN host (recommendations)

**Assumptions:** single DGX Spark, Ubuntu 24.04 / DGX OS, CUDA 13.x aarch64, no GDS dependency, BitNet/FP4-MoE research serve.

1. **I/O plane (cold experts / far packs)**  
   - NVMe filesystem + `mmap`/`O_DIRECT` → **pinned host** expert store.  
   - Hot set: GPU-resident FP4 tiles sized to active top-k only (~≤20GB RSS budget elsewhere).  
   - Prefetch with host threads / `io_uring`; **never** require `nvidia-fs` GDS.

2. **Compute plane (hot GEMM + parallel verify)**  
   - Custom / research: **CUTLASS ≥ 4.2.1 / 4.4.x**, compile **`sm_121a`**, NVFP4 blockscaled `mma.sync` (not SM100 `tcgen05`).  
   - Driver: prefer **CUDA 13.1+** if shipping PTX 9.1 NVFP4.  
   - Production interim: **vLLM** `vllm/vllm-openai:cu130-nightly` or NGC `nvcr.io/nvidia/vllm:26.02-py3`+ with **`--moe-backend marlin`** for MoE; keep `--max-num-seqs` low (1–4); NVFP4 MoE with few-B active. ([vLLM playbook](https://vlaicu.io/posts/dgx-vllm/), [Nemotron Spark instructions](https://build.nvidia.com/spark/nemotron/instructions-super))  
   - Alt engines: **TensorRT-LLM** / **SGLang** from [NVIDIA dgx-spark-playbooks](https://github.com/NVIDIA/dgx-spark-playbooks) when chasing single-stream latency or RadixAttention — still no GDS.

3. **Expert streaming**  
   - Prefer **CPU-pinned expert cache + GPU scratch slots** over storage→GPU DMA fantasy.  
   - Overlap: I/O of next experts ‖ FP4 verify of current draft block.  
   - Optional later: multi-Spark via `cudaHostAlloc` RDMA registration (FAQ), **not** peermem.

4. **CLEAN hygiene**  
   - Flush page cache when diagnosing false OOM (`drop_caches` per FAQ).  
   - Do not trust `nvidia-smi` VRAM; use `free`/`htop`/Dashboard.  
   - Query GPUDirect attributes and **assert fallback path** in harness so CI fails closed if someone re-enables GDS.

5. **T0 scope (align L8)**  
   - Prove: tiny MoE + FP4/BitLinear path + mmap/RSS envelope **without** GDS.  
   - Do **not** put “GDS stream” or “10k tok/s” on the smoke success bar.

#### L7 deliverable checklist

- [x] GDS on Spark = unsupported (FAQ + moderator + gdscheck)  
- [x] NVMe→UMA practical path = host-pinned / mmap, not cuFile fast-path  
- [x] SM 12.1 FP4 = `sm_121a` + `mma.sync` NVFP4; ≠ SM100 tcgen05  
- [x] Serve stack recs for CLEAN without GDS  
- [ ] CLEAN-box measure: NVMe→pinned→kernel BW, native vs Marlin MoE tok/s, verify accept-rate → Fact Checker  

#### L7 sources

- [GDS support for DGX Spark](https://forums.developer.nvidia.com/t/gds-support-for-dgx-spark/350328) (Nov 2025)  
- [DGX Spark / GB10 FAQ — GPUDirect RDMA](https://forums.developer.nvidia.com/t/dgx-spark-gb10-faq/347344)  
- [NVIDIA DGX Spark Porting Guide (PDF)](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/dgx-spark-porting-guide.pdf) (May 2026)  
- [Enabling GPU Direct RDMA for DGX Spark Clustering](https://forums.developer.nvidia.com/t/enabling-gpu-direct-rdma-for-dgx-spark-clustering/352051)  
- [Colfax — NVFP4 blockscaled GEMM on SM12x](https://research.colfax-intl.com/cutlass-tutorial-nvfp4-blockscaled-gemm-on-nvidia-rtx-pro-blackwell-gpus-sm12x/)  
- [modular#6597 — sm_121 native NVFP4 mma.sync](https://github.com/modular/modular/issues/6597)  
- [nvfp4bench DESIGN.md](https://github.com/secYOUre/nvfp4bench/blob/main/DESIGN.md)  
- [SM121 native NVFP4 compute — software support](https://forums.developer.nvidia.com/t/sm121-gb10-native-nvfp4-compute-seeking-guidance-on-software-support/364607)  
- [DGX Spark + vLLM Playbook](https://vlaicu.io/posts/dgx-vllm/)  
- [Nemotron on DGX Spark](https://build.nvidia.com/spark/nemotron/instructions-super)  
- [NVIDIA dgx-spark-playbooks](https://github.com/NVIDIA/dgx-spark-playbooks)  
- [vLLM CachedWeightProvider MoE offload](https://github.com/vllm-project/vllm/commit/71ed1fc8086778f086417f62b5a6dcbfe3cb0d56)  

### L8 — Near-map 2^8 honesty + time gates
_(factory / map — 2026-09-04 scavenger)_

**Strategy (hallucination defy):** Evidence = plan `dgx_1-bit_sidequest_05e1d3b8.plan.md` + seed claims C7/C8/C11/C12 in `notes/BITNET_FACTCHECK.md` (ledger still empty of PASS/FAIL). Hypothesis: ladder arithmetic is coherent; 45d→10T and ≥10k tok/s as *commits* are overclaims. Falsifier: Fact Checker PASS on C5/C7/C12 + measured T0 RSS/tok/s. Verify: no training this cycle — honesty only.

#### Ladder arithmetic (grounded — keep)

| Check | Math | Status |
|-------|------|--------|
| Expert width | `39.0625B / 64 = 0.6103515625B ≈ 0.61B` | Coherent |
| Active @ top-16 | `16 × 0.61B ≈ 9.8B` every rung if width+k fixed | Coherent |
| Eight doubles | `64 × 2^8 = 16384`; `39.0625B × 256 = 10T` | Coherent |
| Hot FP4 mass | `~10B × 0.5 B/param ≈ 5GB` weights (C7) | Plausible on paper; **unmeasured** |
| Whole expert vs L2/L3 | `~0.61B @ FP4 ≈ 305MB` ≫ ~24MB banks (C8) | Coherent → UMA/GDS, not L3 residency |

**Keep:** active-mass invariant + ×2 replace-ckpt story as the *map rule*. Doubling N without growing active set is the only reason ≤20GB can survive to 10T on paper.

#### Executable vs map-only fantasy

| Item | Class | Why |
|------|-------|-----|
| T0 smoke: tiny MoE + BitLinear/FP4 path + mmap/RSS envelope ≤48h | **PASS (CLEAN meters)** | Toy scale; proves accounting, not intelligence — see `OVERSEER_T0_CLEAN_HOST_METERS_2026_09_04` |
| Policy: FP4 hot / optional 1-bit cold-only (C11) | **Executable as design lock** | Silicon-aligned; quality claim still needs Fact Checker |
| Reading=Writing *factor table* as serve invariant | **Executable as reject-AR design** | Spec/MTP/verify shape is real prior class; **≥10k tok/s is not proven** |
| R0 = 39.0625B/64 distill “perf signal” ≤10d | **Fragile / borderline fantasy** | Still ~10B-active student on one Spark; 10d is a stretch goal, not a law |
| Eight doubles → 10T packed+serve ≤20GB in ≤45d (≤4d/double) | **Map-only fantasy as calendar commit** | Packing/serve shape ≠ suite-holding train; 8 quality rungs in ~33d residual is hero calendar |
| 1Q / 10M-expert far spine | **Horizon map only** | Explicitly not near-committed — correct labeling; do not schedule |
| Brochure ~1 PFLOP sparse FP4 / marketed 8–10k+ tok/s (C5/C6) | **Marketing until PASS** | Must not gate T0; must not be success criteria for smoke |

#### Time gates — stress test

| Gate | Plan commit | Honesty |
|------|-------------|---------|
| **T0** ≤48h | Tiny MoE + RSS | **Keep** if scoped *tiny*; **FAIL the gate** if anyone slips R0-39B into “smoke” |
| **T1** ≤10d | R0 distill signal | **Improve:** redefine as “measurable student>random on fixed suite” *or* slip to 14–21d; do not block factory on miss |
| **≤4d/double** → 10T ≤45d | Near-map capital | **Demote to aspirational map pacing.** Fail-soft already says park train — treat miss as expected, not scandal |
| **1Q** | Horizon | **Keep** as label only |

**Pre-mortem:** 45d clock fails if (1) T0 bloated to R0, (2) no async CLEAN/RSS gate, (3) GDS path vapor, (4) accept-rate γ too low so Writing never compute-bound, (5) Fact Checker strikes C3/C4 and UMA/GDS story collapses.

#### Reading=Writing invariant — what is / isn’t locked

- **Locked (keep):** ban naive single-token GEMV as *happy path*; draft-block + parallel FP4 verify; same I/O cache path for read/write positions; expert load-spread across concurrent tokens.
- **Not locked (fragile):** effective ≥10k tok/s on CLEAN; that MTP accept-rate will make Writing *compute-bound* at R0 widths; that Chinese MTP priors transfer to this student.
- **Fact Checker marks:** C6, C9, and any “10k+ class” success bullet → treat as **UNKNOWN** until measured on CLEAN (not brochure).

#### FP4 hot vs 1-bit cold

- **Keep:** hot GEMM = FP4; 1-bit/ternary only optional NVMe cold if quality+GDS gates pass.
- **Improve:** never let “BitNet” branding pull 1-bit onto TE hot path; rename mental model to **FP4-MoE near map** with optional BitNet-style cold pack.
- **Fragile (→ Fact Checker):** C11 retention claim; C7 5GB fit under *real* KV/act/router RSS (20GB is budget, not proof).

#### Failure modes (factory)

1. **Calendar laundering** — calling the 2^8 table “executable” (C12) without separating *shape executable* vs *45d train executable*.
2. **Smoke inflation** — T0 becomes 39B; blows 48h and poisons T1.
3. **Throughput theater** — AR fallback quietly becomes default; dashboard still claims Reading=Writing.
4. **Cache category error** — pinning 0.61B experts into L2/L3 (C8 already warns).
5. **North-star bleed** — scheduling 1Q rungs before R8 serve is boring.
6. **Scavenger without ledger** — research prose lands while `BITNET_FACTCHECK.md` has zero PASS/FAIL rows → plan locks treated as truth prematurely.

#### Keep / improve list

**Keep**
- 2^8 near map numbers + active≈9.8B invariant
- FP4-hot / lower-bit-cold precision split
- Reading=Writing as *design reject of AR-as-center*
- Fail-soft park-train / research-never-stops / improve-forever independent
- T0 as *tiny* smoke before any rung train

**Improve**
- Rewrite C12 / success copy: “ladder shape is executable; 45d→10T is map pacing, not a promise”
- Split factory milestones: **Serve-shape green** (RSS≤20GB, GEMM write path) vs **Quality green** (suite across doubles)
- Require Fact Checker rows on C3–C7, C11–C12 before treating hardware/speed locks as dispatch truth
- Cap T0 definition in queue text: max param/expert counts for smoke (toy), explicit “not R0”

#### Fragile claims → Fact Checker

| ID | Fragility | Ask |
|----|-----------|-----|
| **C5** | Brochure PFLOP | PASS only with NVIDIA Spark/GB10 primary source; else UNKNOWN |
| **C6** | 8–10k+ class | Prefill vs decode disambiguation mandatory |
| **C7** | ~5GB @ FP4 | Confirm bitwidth accounting (FP4 vs FP8 TE) + exclude/include scales |
| **C8** | 0.61B vs L2/L3 | Confirm GB10 L2/L3 sizes (ties C1/C2) |
| **C9** | Spec/MTP = Writing GEMM | Prior art OK; CLEAN accept-rate UNKNOWN until measure |
| **C11** | FP4≫1-bit quality | Needs cited BitNet/NVFP4 retention evidence — not vibe |
| **C12** | “Executable near map” | **Strike or split:** shape-exec vs calendar-exec; L8 votes **UNKNOWN/overclaim** as written |

#### L8 verdict — T0 smoke after scavenger

**GO (narrow) / NO-GO (ladder).**

- **GO** start **T0 smoke after scavenger wave-0 briefs land**, only if T0 stays **tiny MoE + FP4/BitLinear path + RSS/mmap envelope** on CLEAN, ≤48h, **no R0-39B train**, no 10k tok/s success bar.
- **NO-GO** on starting **T1 / near-map doubles / 45d→10T clock** until T0 shows (1) RSS gate machinery works, (2) generate path is block-verify GEMM-shaped at least once, (3) Fact Checker has non-empty verdicts on C3–C7 (hardware+budget) — FAIL ⇒ rewrite locks before scale.
- Scavenger incomplete ledger is **not** a hard stop for toy T0; it **is** a hard stop for treating plan PFLOPs/10k+/45d as committed truth.

#### T0 CLEAN host meters (2026-09-04 overseer)

<!-- OVERSEER_T0_CLEAN_HOST_METERS_2026_09_04 -->

Ran `python3 scripts/bitnet_fp4_expert_rss_smoke.py --json` on **CLEAN** (`aarch64`) after syncing the hub harness. Toy scale only (4 experts × 4096 FP4 params; no GDS; no R0). Prompt vs accepted Writing stay separate — brochure 10k+ is not a success bar.

| Meter | CLEAN value | Notes |
|-------|-------------|-------|
| `prompt_tok_s` | **5 760 254.548** | Prefill-shaped toy mmap touch (accounting, not serve claim) |
| `accepted_writing_tok_s` | **4 801 864.072** | Accepted Writing only (`accept_rate=0.75`) |
| `accept_rate` | 0.75 | Toy verifier stub |
| `rss_before_mb` / `rss_after_mb` | 14.59 / 14.59 | ΔRSS **0.0** MiB |
| `expert_bytes_mmap` | 8192 | 4 × 2 KiB FP4 bank via `mmap` |
| `gds_forbidden_ok` | **True** | No `nvidia-fs` / cuFile / cupy |

**Verdict:** T0 RSS/mmap envelope + separate prompt/Writing meters **PASS** on CLEAN. T1 / near-map clock remains **NO-GO**.

#### T0 CLEAN host meters reconfirm (2026-09-06)

<!-- OVERSEER_T0_CLEAN_HOST_METERS_2026_09_06 -->

Re-ran `python3 scripts/bitnet_fp4_expert_rss_smoke.py --json` on **CLEAN** after offload. Same toy harness (4×4096 FP4; mmap; no GDS). High tok/s figures are **accounting touch rates** on tiny mmap banks — **not** a serve KPI and **not** brochure 10k decode.

| Meter | CLEAN value | Notes |
|-------|-------------|-------|
| `prompt_tok_s` | **2 915 676.009** | Prefill-shaped toy mmap touch |
| `accepted_writing_tok_s` | **2 263 481.163** | Accepted Writing only (`accept_rate=0.75`) |
| `accept_rate` | 0.75 | Toy verifier stub |
| `rss_before_mb` / `rss_after_mb` | 14.418 / 14.418 | ΔRSS **0.0** MiB |
| `expert_bytes_mmap` | 8192 | mmap FP4 bank |
| `gds_forbidden_ok` | **True** | No nvidia-fs / cuFile |

**T0 clock:** **GO (narrow)** envelope may start ≤48h from this reconfirm for *toy* work only. **T1 / 2^8 doubles / 45d→10T calendar:** still **NO-GO** until RSS comfort + C3–C7 ledger comfort for scale (L8). Ops SoT: [`DGX_NVFP4_SIDE_QUEST_OPS.md`](DGX_NVFP4_SIDE_QUEST_OPS.md).

## Locked decisions (from plan — fact-check before treating as truth)

- Hot path FP4; lower-bit optional cold only
- Reading = Writing factor table (parallel, GEMM, compute-bound **shape**; Writing tok/s = **accepted** meter — not brochure “thousands”; **C28 FAIL**)
- Expert load distribution for throughput
- Standing research — not a stop plan
- improve-forever stays independent

## Output-research scavenger — Mac/CPU correctness (2026-09-05T00:03Z)

_(output_researcher peer-6 — live `gh` + raw `main`)_

- **ARM i2_s layout (prior):** `src/ggml-bitnet-mad.cpp` still `#define QK_I2_S 128` (x86) vs `64` (`__ARM_NEON`); [#585](https://github.com/microsoft/BitNet/issues/585)/[#586](https://github.com/microsoft/BitNet/pull/586)/[#551](https://github.com/microsoft/BitNet/pull/551) OPEN — CPU ternary garbage on Apple Silicon until land.
- **NEW — F16/F32 converter dequant:** `utils/convert-hf-to-gguf-bitnet.py` on `main` still does `data_torch / scale_map[...]` for absmean reconstruct (~L807 LlamaModel path; ~L1108 BitnetModel F16/F32 branch). Correct is `*` (`ternary * weight_scale`). [#616](https://github.com/microsoft/BitNet/pull/616) OPEN `mergedAt=null` (updated 2026-08-26). Wrong path → weights ~2.4× too small → garbled F16/F32 GGUF even when kernels are fine.
- **Factory implication:** external-proof sprint needs **both** PRs (or superseding fork commits); I2_S-only path may skip the F16 `/` bug, but any F16/F32 export / eval harness stays broken until #616. Deferred Creative under `self_sufficient` — do not Active-enqueue.

## Output-research scavenger — Mac Metal+BLAS + TL1 stock gap (2026-09-05T01:29Z)

_(output_researcher peer-6 — live `gh` + raw `main`)_

- **NEW — Metal+BLAS ubatch trap:** [#512](https://github.com/microsoft/BitNet/issues/512) OPEN — Apple Silicon Metal+BLAS segfaults on `i2_s` when physical `ubatch≥32` (BLAS claims generic `MUL_MAT`; `I2_S` external scale invisible). Fix [#533](https://github.com/microsoft/BitNet/pull/533) OPEN `mergedAt=null` (reject `GGML_TYPE_I2_S` from BLAS support + `to_float` wrapper). Falsifies “just use Metal on Mac” as clean #586 workaround.
- **NEW — TL1 compile gap:** `setup_env.py` lists arm64 quant `["i2_s","tl1"]` but `COMPILER_EXTRA_ARGS["arm64"] = ["-DBITNET_ARM_TL1=OFF"]` (L73) always — `-q tl1` may copy LUT headers / codegen yet cmake still disables TL1. Not a zero-friction escape hatch under stock setup.
- **Factory implication:** external-proof Mac sprint is now **triple** (#586 + #616 + #533) plus optional setup_env TL1 ON when `-q tl1`. Deferred Creative under `self_sufficient` — do not Active-enqueue.

## Output-research scavenger — ReLU² FFN every-backend wall (2026-09-05T01:37Z)

_(output_researcher peer-6 — live `gh` + raw pinned + ggml master)_

- **NEW — SiLU vs relu² graph bug:** Official `bitnet-b1.58-2B-4T` declares `hidden_act=relu2`, but BitNet graph hardcodes `LLM_FFN_SILU` at pinned submodule `isHuangXin/llama.cpp@390c3077` `src/models/bitnet.cpp:133` **and** still at `ggml-org/llama.cpp` master `:132`. microsoft [#588](https://github.com/microsoft/BitNet/issues/588)/[#602](https://github.com/microsoft/BitNet/issues/602) OPEN; fix PRs [#604](https://github.com/microsoft/BitNet/pull/604)/[#605](https://github.com/microsoft/BitNet/pull/605) OPEN `mergedAt=null`; canonical ggml PR [#25885](https://github.com/ggml-org/llama.cpp/pull/25885) **CLOSED** without merge. Measured impact (issue #588): x86 I2_S PPL **99.82→17.11**; ARM TL1 **78.69→14.96** — wrong-but-finite on **every** backend (distinct from #586 ARM layout / #512 Metal crash / #616 F16 `/`).
- **Factory implication:** external-proof Mac sprint is now **quadruple** (#586 + #616 + #533 + #604/#605). Landing kernels alone still leaves ~6× PPL regression. Deferred Creative under `self_sufficient` — do not Active-enqueue.

## Output-research scavenger — AVX-only GEMM multi-token + HF zero-MLP (2026-09-05T02:09Z)

_(output_researcher peer-6 — live `gh` + raw pin `390c3077` + BitNet `main` HEAD `0b341e5`)_

- **NEW — I2_S GEMM multi-token wall (#617):** On AVX-only CPUs (no AVX2), prompt eval with ≥~5 tokens garbles KV (`??????`) while 1–3 token / GEMV path stays coherent. Needle still live: pinned `isHuangXin/llama.cpp@390c3077` `ggml/src/ggml-cpu/ggml-cpu.c:1492` gates `GGML_TYPE_I2_S && ggml_n_dims==2` into `ggml_gemm_i2_i8_s` (`:1518`). [#617](https://github.com/microsoft/BitNet/issues/617) OPEN `mergedAt=n/a` (issue; **no fix PR**). Distinct from [#547](https://github.com/microsoft/BitNet/issues/547)/[#580](https://github.com/microsoft/BitNet/pull/580) (empty-body scalar `vec_dot`) — after those, GEMM `nr>1` still wrong. Issue body requires #588+#616 for coherent F16 too.
- **NEW — official checkpoint zero-MLP wall (#608):** Current `microsoft/bitnet-b1.58-2B-4T` / `-bf16` / `-gguf` reported with **all-zero MLP** tensors on several layers (attn may still be nonzero); [#608](https://github.com/microsoft/BitNet/issues/608) OPEN — comments claim even original GGUF lineage broken. Kernel-perfect external-proof still fails if HF artifact is zeroed → need pinned known-good revision or rebuild before Mac/CPU sprint counts.
- **Reconfirm (unchanged):** #586/#616/#533/#604/#605 OPEN; convert still `/ scale_map` ~L807/~L1108; `setup_env.py:73` TL1 OFF; SILU at pin `:133` + ggml master `:132`.
- **Factory implication:** correctness sprint is now **quintuple** kernels/graph (#586+#616+#533+#604/#605+#617) **plus** artifact gate (#608). Deferred Creative under `self_sufficient` — do not Active-enqueue.

## Output-research scavenger — Darwin I2_S link ownership wall (2026-09-05T02:25Z)

_(output_researcher peer-6 — live `gh` + raw pin `390c3077`)_

- **NEW — Mac M2 link failure before any runtime proof (#611):** `setup_env.py` dies linking `bin/libggml-base.*.dylib` with undefined `_dequantize_row_i2_s` (from `type_traits`) and `_quantize_i2_s` (from `ggml_quantize_chunk`). [#611](https://github.com/microsoft/BitNet/issues/611) OPEN (created 2026-08-14). Same class as Windows [#595](https://github.com/microsoft/BitNet/issues/595); fix PR [#606](https://github.com/microsoft/BitNet/pull/606) OPEN `mergedAt=null` moves platform-neutral impls into ggml-base (`ggml-quants.c`).
- **Needles (still live on pin):** callers in ggml-base `ggml/src/ggml.c:936` (`.to_float = dequantize_row_i2_s`) and `:7787` (`case GGML_TYPE_I2_S: quantize_i2_s`); definitions in ggml-cpu `ggml/src/ggml-cpu/quants.c:1335` / `:1358` — Darwin shared-lib link surfaces the split.
- **Factory implication:** Mac external-proof is now **link-before-run** (#611/#606) **then** quintuple+#608. Without #606, stock Darwin never reaches #586/#533 eval. Deferred Creative under `self_sufficient` — do not Active-enqueue.

## Output-research scavenger — CPU+Accelerate ubatch twin of Metal (#601) (2026-09-05T02:41Z)

_(output_researcher peer-6 — live `gh`)_

- **NEW — CPU `-ngl 0` + Accelerate BLAS also SIGSEGVs at ub≥32 (#601):** [#601](https://github.com/microsoft/BitNet/issues/601) OPEN (updated 2026-08-19). Not Metal-only: any BLAS-linked build (macOS default = Accelerate) crashes prompt processing at `n_ubatch≥32`. Repro: `llama-bench -m ggml-model-i2_s.gguf -ngl 0 -p 64 -ub 32` → SIGSEGV; `-ub 16` fine. Single-token generation / `tg` benches miss it. Cause: BLAS dequant uses row stride **4×** the packed `i2_s` row; threshold = `min_batch=32` in `ggml_backend_blas_device_supports_op`.
- **Relation to prior walls:** Expands [#512](https://github.com/microsoft/BitNet/issues/512)/[#533](https://github.com/microsoft/BitNet/pull/533) from “Metal+BLAS” narrative to **stock Darwin CPU path**. Fix class still BLAS reject/`to_float` guard (#533) or equivalent.
- **Freshness:** ARM layout fix PR [#551](https://github.com/microsoft/BitNet/pull/551) still OPEN `mergedAt=null` (updated 2026-09-02) — newest AdvSIMD/word-salad candidate alongside #586.
- **Reconfirm (unchanged):** link-before-run #611/#606; #586/#616/#604/#605/#617/#608 OPEN; `setup_env.py:73` `-DBITNET_ARM_TL1=OFF`.
- **Factory implication:** After #606 links, interim Mac smoke must use `-ub 16` (or land #533/#601-class) even with `-ngl 0`. Deferred Creative under `self_sufficient` — do not Active-enqueue.

## Output-research scavenger — #610 pin ARM constant + Metal type-36 abort (2026-09-05T02:47Z)

_(output_researcher peer-6 — live `gh` issue #610 + isHuangXin/llama.cpp#6 + submodule sha)_

- **NEW — submodule pin wall (#610):** On `3rdparty/llama.cpp` pin `isHuangXin/llama.cpp@390c3077`, ARM CPU `i2_s` emits constant prompt-independent `@@@@` while x86 AVX2 is coherent. [#610](https://github.com/microsoft/BitNet/issues/610) OPEN (updated 2026-08-12).
- **Metal is not a Mac oracle here:** same pin **aborts on tensor type 36** — cannot fall back to Metal to validate CPU after #611 links.
- **Needles:** ARM fallback of `ggml_vec_dot_i2_i8_s` in `ggml/src/ggml-cpu/quants.c` (sequential unpack + remapped ternary + single calling convention); `ggml-cpu.c` needs `src1_cont` hoisted above `GGML_USE_LLAMAFILE` guard. Fix PR [isHuangXin/llama.cpp#6](https://github.com/isHuangXin/llama.cpp/pull/6) OPEN `mergedAt=null` (updated 2026-08-15) — BitNet must **bump submodule** after merge; not fixed by BitNet AdvSIMD PRs alone.
- **Distinct from:** #585/#586/#551 (BitNet-side QK 64/128 AdvSIMD layout); #600 (ARM64/NEON scalar garbage sibling on RK3588); #611/#606 (link ownership).
- **Factory implication:** Mac external-proof order is now **link (#611/#606) → pin+#610 (#6 bump) → quintuple+#601+#608**. Deferred Creative under `self_sufficient` — do not Active-enqueue.
