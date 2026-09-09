# Compression Catalog (Automation hub)

**Scope:** Weight / structure / packing methods that reduce **stored unique parameters** or packed bytes for neural LMs (esp. MoE experts).  
**Forbidden:** dataset / example pruning as a compression cheat.

**North star (logical expert):**
- Logical expert size: **1B parameters**
- Start: **1-bit** (ternary/binary BitNet-class)
- Target packed footprint ≈ **10M unique 1-bit params** worth of storage per granular MoE expert
- Implies ≈ **100× structural unique-param compression on top of 1-bit** (tying, low-rank, shared backbones, etc.), or equivalent math documented honestly
- Teacher distill OK; no data/example pruning
- Soft preference: MoE grain + later Zamba / Mamba-2 SSD serve (noted per method)

**North-star arithmetic (honest):**
| Quantity | Formula | Value |
| --- | --- | --- |
| Logical expert | \(N\) | \(10^9\) |
| Packed @ 1-bit if all unique | \(N/8\) bytes | 125 MB |
| Target unique 1-bit params | \(N'\) | \(10^7\) |
| Target packed | \(N'/8\) | ~1.25 MB |
| Required unique-param ratio | \(N/N'\) | **100×** |
| BitNet-class alone (vs FP16 bytes) | \(16 / 1.58 \approx 10\times\) storage vs FP16 | does **not** reduce unique count |
| Gap after 1-bit | still need ~**100×** fewer unique slots | structural / sharing / rank |

No claim of measured Spark/1T delivery anywhere in this catalog.

---

### Lane A — Weight / structure compression census (2026-09-05)

Census agent: web research (Bright Data often 401 this hub; sources from live WebSearch/WebFetch + prior scrape). Status labels: **measured** = paper reports empirical compression/accuracy; **paper** = method published, factor cited from abstract or clear statement; **hypothesis** = stack proposal only.

**S-axis tag (north-star \(S\approx100\)):** Only rows whose **Axis** starts with `unique-param` count toward unique-parameter compression. Tags **`bytes-quant (≠S)`**, **`KV (≠S)`**, **`disk/codec (≠S)`**, and **`serve-util (≠S)`** must not be summed into \(S\). Hot dtype lock = **NVFP4** ([`NVFP4_LOCK_APPLICABILITY.md`](NVFP4_LOCK_APPLICABILITY.md)); 1-bit = optional cold/research. **Forbidden:** data/example pruning.

| ID | Method | Axis | Typical compression factor (vs dense FP16 or vs unique params) | MoE-grain fit | 1-bit compatible? | Sources (URL/arXiv) | Status: measured / paper / hypothesis |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A01 | GPTQ | quant-PTQ | ~3–4 bit weights (~4–5.3× vs FP16 bytes); 175B in ~4 GPU-hours claimed | Good (per-expert PTQ) | Partial (paper explores 2-bit/ternary regime; quality UNKNOWN at true W1) | [arXiv:2210.17323](https://arxiv.org/abs/2210.17323v2) | measured |
| A02 | AWQ | quant-PTQ | 4-bit weight-only; TinyChat ~3× speedup / ~4× memory vs FP16 reported | Good | Poor at W1 (activation-aware INT3–4 focus) | [arXiv:2306.00978](https://arxiv.org/abs/2306.00978) | measured |
| A03 | SmoothQuant | quant-PTQ | W8A8; up to ~2× memory reduction + 1.56× speedup reported | OK (acts+weights) | No (INT8 target) | [arXiv:2211.10438](https://arxiv.org/pdf/2211.10438) | measured |
| A04 | OmniQuant | quant-PTQ/QAT-lite | Low-bit weight PTQ with learnable clipping/scales; vs FP16 factor ≈ 16/b (b typically 2–4) | Good | Partial | [arXiv:2308.13137](https://arxiv.org/abs/2308.13137) | measured |
| A05 | SpQR | quant-PTQ | Near-lossless 3–4 bit + sparse outliers; **>4×** memory vs 16-bit reported | Good | No (3–4 bit + FP outliers) | [arXiv:2306.03078](https://arxiv.org/abs/2306.03078) | measured |
| A06 | QuIP# | quant-PTQ | Lattice/incoherence 2-bit class; vs FP16 ≈ 8× bytes if W2 holds | Good | Partial (extreme low-bit; not native BitNet) | [arXiv:2402.04396](https://arxiv.org/abs/2402.04396) | measured |
| A07 | AQLM | quant-PTQ | Additive codebook quant; competitive **≤3 bit** Pareto claimed | Good | Partial (vector codes ≠ binary experts) | [alphaXiv/AQLM 2401.06118](https://www.alphaxiv.org/abs/2401.06118) | measured |
| A08 | HQQ | bytes-quant (≠S) / quant-PTQ | Calibration-free half-quadratic weight recon; Llama-2-70B **&lt;5 min** (~**50×** faster than GPTQ claimed); 2–8 bit; vs FP16 ≈ 16/b (**≠** unique \(S\)) | Good | Partial at 2-bit; **NVFP4** still preferred hot GEMM | [Dropbox HQQ blog](https://dropbox.tech/machine-learning/halfquadratic-quantization-of-large-machine-learning-models); [dropbox/hqq](https://github.com/dropbox/hqq) | measured |
| A09 | Bitsandbytes NF4 / FP4 (QLoRA) | quant-PTQ + PEFT | **4-bit** NormalFloat / FP4; ~4× weight memory vs FP16 | OK (adapter on frozen expert) | No (4-bit) | [arXiv:2305.14314](https://arxiv.org/abs/2305.14314); [HF Linear4bit](https://huggingface.co/docs/bitsandbytes/v0.47.0/reference/nn/linear4bit) | measured |
| A10 | NVFP4 | quant-format | 4-bit microscaling (block-16 + FP8 scales); ~4× vs FP16 storage for weights/acts when packed | OK | No | [NVIDIA NVFP4 blog](https://developer.nvidia.com/blog/nvfp4-trains-with-precision-of-16-bit-and-speed-and-efficiency-of-4-bit/); [arXiv:2509.25149](https://arxiv.org/html/2509.25149v1) | measured |
| A11 | BitNet b1.58 | quant-native / arch | Ternary \(\{-1,0,+1\}\); storage vs FP16 ≈ **16/1.58 ≈ 10×** (unique count unchanged) [^fn-a11] | Excellent if experts are BitLinear | **Yes (north-star start)** | [arXiv:2402.17764](https://arxiv.org/html/2402.17764); [2B4T report](https://arxiv.org/html/2504.12285v2) | measured |
| A12 | BiLLM | quant-PTQ | PTQ binarization; pushes W1 PTQ vs PB-LLM baselines | Good | **Yes (binary)** | [arXiv:2402.04291](https://arxiv.org/html/2402.04291v2) | measured |
| A13 | OneBit | quant-QAT/KD | W1 via SVID + KD; ≥81% of FP performance on LLaMA claimed | Good | **Yes** | [arXiv:2402.11295](https://arxiv.org/html/2402.11295v4) | measured |
| A14 | PB-LLM | bytes-quant (≠S) / quant-PTQ/QAT | Partial binarization (salient weights higher bits); avg bitwidth >1 (**≠** unique \(S\)) | Fair (mixed precision) | Partial | [arXiv:2310.00034](https://arxiv.org/abs/2310.00034) | paper |
| A15 | LQ-LoRA | quant + low-rank | \(W \approx Q + L_1 L_2\); PEFT memory down vs full FT (factor task-dep.; UNKNOWN fixed ×) | Good (per-expert adapters) | Partial (Q can be low-bit) | [arXiv:2311.12023](https://arxiv.org/html/2311.12023v4) | measured |
| A16 | SqueezeLLM | bytes-quant (≠S) / quant-PTQ | Dense-and-sparse / sensitivity-based; typically 3–4 bit class (**≠** unique \(S\)) | Good | Poor at W1; survivors packable **NVFP4** | [arXiv:2306.07629](https://arxiv.org/abs/2306.07629) | measured |
| A17 | QuIP (base) | bytes-quant (≠S) / quant-PTQ | Incoherence processing + LDLQ; **2-bit** class; precursor to QuIP# (**≠** unique \(S\)) | Good | Partial | [arXiv:2307.13304](https://arxiv.org/abs/2307.13304); QuIP# follow-on [arXiv:2402.04396](https://arxiv.org/abs/2402.04396) | measured |
| A18 | QuaRot / FlatQuant (rotation family) | bytes-quant (≠S) / quant-PTQ | Orthogonal transforms for outlier-free **W4** (QuaRot); vs FP16 ≈ 16/b (**≠** unique \(S\)); FlatQuant related rotation PTQ | Good | Partial; W4 path adjacent to locked **NVFP4** serve | [QuaRot arXiv:2404.00456](https://arxiv.org/abs/2404.00456) | measured |
| A19 | LoRA | low-rank / PEFT | Trainable params **≪** full; GPT-3 example **10,000×** fewer trainable (not unique base weights) [^fn-lora] | Excellent (expert deltas) | Yes if base is 1-bit | [arXiv:2106.09685](https://arxiv.org/pdf/2106.09685v1) | measured |
| A20 | DoRA | low-rank / PEFT | Magnitude+direction decomp; same merge-as-LoRA storage at infer | Excellent | Yes (on 1-bit base) | [arXiv:2402.09353](https://arxiv.org/pdf/2402.09353) | measured |
| A21 | LoHA (Hadamard / FedPara-style) | low-rank / PEFT | Hadamard of low-rank factors; trainable ≪ full (factor UNKNOWN vs LoRA) | Good | Yes | Cited in DoRA related work [arXiv:2402.09353](https://arxiv.org/html/2402.09353v3) | paper |
| A22 | LoKr / Kronecker adapters | low-rank / PEFT | Kronecker factors; parameter ↓ vs LoRA at similar rank budgets (exact × UNKNOWN) | Good | Yes | Family cited via Kronecker LM compression [KroneckerBERT](https://aclanthology.org/2022.naacl-main.154.pdf) | paper |
| A23 | ASVD | low-rank / SVD | Training-free; **10–30%** network compression; also **~50%** KV channels claimed | Good on expert FFN mats | Yes (structure then pack) | [arXiv:2312.05821](https://arxiv.org/html/2312.05821) | measured |
| A24 | Basis Sharing | low-rank + share | Cross-layer shared SVD bases + unique coeffs; strong at **20–50%** compression ratios vs layerwise SVD | Excellent for stacked experts | Yes | [arXiv:2410.03765](https://arxiv.org/html/2410.03765v1) | measured |
| A25 | Monarch / MoRe | structured / PEFT | Monarch-class adapters; MoRe claims **as few as 5% of LoRA params** | Good | Yes | [alphaXiv MoRe 2408.17383](https://www.alphaxiv.org/abs/2408.17383) | measured |
| A26 | KroneckerBERT | factorization | **7.7×** and **21×** compression factors reported on BERT_BASE | Fair (encoder-era; port to MoE UNKNOWN) | Yes after decomp | [ACL Anthology](https://aclanthology.org/2022.naacl-main.154.pdf) | measured |
| A27 | Tensor Train / Tensor Ring | factorization | TT cores ≪ dense; PTNN reports up to **5%** accuracy *gain* under tensorization (size factor UNKNOWN, task-dep.) | Fair–Good | Yes | [arXiv:2310.20077](https://arxiv.org/pdf/2310.20077) | measured |
| A28 | ALBERT cross-layer share | param-share | BERT-large-like config: **18× fewer params**; ~1.7× train speedup claimed [^fn-albert] | Excellent (L-way share on expert tower) | Yes | [arXiv:1909.11942](https://arxiv.org/html/1909.11942v6) | measured |
| A29 | MobileBERT | distill + thin | Compact BERT student; parameter ↓ vs BERT_BASE (exact × UNKNOWN here) | Fair | Yes | Cited alongside KroneckerBERT baselines [ACL](https://aclanthology.org/2022.naacl-main.154.pdf) | paper |
| A30 | Universal Transformers | param-share / recur | Depth via recurrence → params **independent of depth** (unique ≈ 1 block) | Excellent if expert = recurrent block | Yes | Cited in Subformer related work [arXiv:2101.00234](https://arxiv.org/abs/2101.00234) | paper |
| A31 | Subformer | param-share | Generative Transformer weight sharing for param efficiency | Good | Yes | [arXiv:2101.00234](https://arxiv.org/abs/2101.00234) | measured |
| A32 | DictFormer | dict-share | **>3.6×** params and **~3×** Mult-Adds vs matched Transformer accuracy claimed | Good | Yes | [OpenReview DictFormer PDF](https://openreview.net/references/pdf?id=H4et8t4A-c) | measured |
| A33 | VeRA | param-share / PEFT | Single shared frozen random pair + scaling vectors; **≪ LoRA** trainable storage [^fn-vera] | Excellent | Yes | [arXiv:2310.11454](https://arxiv.org/abs/2310.11454); [VeRA project](https://dkopi.github.io/vera/); [ICLR PDF](https://proceedings.iclr.cc/paper_files/paper/2024/file/1b53ad08de383a049e9668a9d0b6a053-Paper-Conference.pdf) | measured |
| A34 | (IA)³ / IA3 | unique-param / PEFT-scale | Learned activation scales \((IA)^3\); tiny unique params vs LoRA (few-shot PEFT paper) | Excellent | Yes on **NVFP4**/1-bit base | [arXiv:2205.05638](https://arxiv.org/abs/2205.05638) | measured |
| A35 | Tied embeddings | param-share | Input/output embed tie ≈ halves embed unique params (classic) | N/A to expert FFN; keep for LM shell | Yes | Standard practice; factor = vocab-dependent | paper |
| A36 | DeepSeekMoE shared + fine-grain experts | MoE-arch | Shared experts absorb common knowledge; fine segmentation; DeepSeekMoE 2B ≈ GShard 2.9B quality while GShard has **1.5×** expert params/compute [^fn-dsmoe] | **Native** | Yes with binary experts | [arXiv:2401.06066](https://arxiv.org/html/2401.06066) | measured |
| A37 | Switch Transformers | MoE-arch | Top-1 routing; scales total params with sparse activate-1 | Native | Yes | Cited throughout [DeepSeekMoE](https://arxiv.org/html/2401.06066); SoftMoE compare [arXiv:2606.17952](https://arxiv.org/html/2606.17952v1) | measured |
| A38 | Soft MoE (Google / sparse→soft) | MoE-arch | Soft assignment; Soft MoE Huge/14 **>40×** params vs ViT-H/14 with ~2% infer time ↑ (vision) | Good (grain differs) | Yes | [arXiv:2308.00951](https://arxiv.org/pdf/2308.00951) | measured |
| A39 | SoftMoE (LLM LapSum variant) | MoE-arch | Differentiable soft top-k; fewer active experts at matched quality claimed | Native | Yes | [arXiv:2606.17952](https://arxiv.org/html/2606.17952v1) | measured |
| A40 | ModuleFormer | MoE-arch | SMoE modular FFN + stick-breaking attn; sparse module activate | Native | Yes | [arXiv:2306.04640](https://export.arxiv.org/pdf/2306.04640v2.pdf) | measured |
| A41 | MoBiE | MoE + binary | Binary experts under PTQ; MoE-aware binarization without (re)training [^fn-mobie] | **Excellent for 1-bit MoE path** (not alone for 100× unique) | **Yes** | [arXiv:2604.06798](https://arxiv.org/html/2604.06798v2) | measured |
| A42 | Sub-MoE (subspace expert merging) | MoE-merge | Joint SVD merge; Mixtral **25%/50%** expert reduction keeps **96%/86%** zero-shot claimed | Compresses expert count (not per-expert 100×) | Yes after merge | [arXiv:2506.23266](https://arxiv.org/pdf/2506.23266) | measured |
| A43 | MergeMoE | MoE-merge | Output-merge LS optimization; same compression ratios beat prior mergers | Same as A42 | Yes | [arXiv:2510.14436](https://arxiv.org/html/2510.14436v1) | measured |
| A44 | Expert Choice routing | MoE-routing | Experts choose tokens (capacity balance); enables more experts / better util (unique storage unchanged unless paired with merge) | Native | Yes | Surveyed in [arXiv:2407.06204](https://arxiv.org/pdf/2407.06204); Soft MoE cites Tokens/Experts Choice [arXiv:2308.00951](https://arxiv.org/pdf/2308.00951) | paper |
| A45 | MLA (Multi-head Latent Attention) | KV (≠S) | DeepSeek-V2 MLA; interpretability study cites **81% KV-cache reduction** (**≠** unique-param \(S\)) | Serve-side; **not weight compression** | N/A | [TransMLA / DeepSeek-V2 cite](https://arxiv.org/html/2502.07864v2); [MLA bottleneck study](https://arxiv.org/html/2607.23054); [attention comparison note](https://cyk1337.github.io/blog/2024/memory-efficient-attention/) | measured |
| A46 | GQA | KV (≠S) | Grouped KV heads; cache ↓ vs MHA by `#KV_heads/#Q_heads` (**≠** unique \(S\)) | Not weight | N/A | [attention comparison note](https://cyk1337.github.io/blog/2024/memory-efficient-attention/) (cites arXiv:2305.13245) | measured |
| A47 | MQA | KV (≠S) | Single KV head; max KV compression among head-sharing (**≠** unique \(S\)) | Not weight | N/A | [attention comparison note](https://cyk1337.github.io/blog/2024/memory-efficient-attention/) | paper |
| A48 | YOCO | KV (≠S) / arch | Cache KV **once** (decoder–decoder); orders-of-magnitude infer memory vs long context claimed (**≠** unique \(S\)) | Not weight | N/A | [arXiv:2405.05254](https://arxiv.org/html/2405.05254v1) | measured |
| A49 | CLA (Cross-Layer Attention) | KV (≠S) | Share KV across adjacent layer groups (**≠** unique \(S\)) | Not weight | N/A | Surveyed in [NAACL CLA study PDF](https://aclanthology.org/2025.naacl-short.34.pdf) | paper |
| A50 | Mamba-2 SSD | arch / SSM | SSD duality; core layer **2–8× faster** than Mamba-1 | Soft prefer for later serve | Orthogonal to 1-bit weights | [HF paper 2405.21060](https://huggingface.co/papers/2405.21060) | measured |
| A51 | Zamba | arch / hybrid | Mamba backbone + **shared** global attention (params of attn amortized) | Soft prefer | Orthogonal | [Zamba 2405.16712](https://www.emergentmind.com/papers/2405.16712) | measured |
| A52 | Jamba | arch / hybrid | Transformer–Mamba hybrid MoE-capable family | Soft prefer | Orthogonal | Cited [Hymba related](https://arxiv.gg/abs/2411.13676) as 2403.19887 | paper |
| A53 | Hymba | arch / hybrid | Hybrid-head attn+SSM; **11.67×** cache ↓ and **3.49×** throughput vs Llama-3.2-3B claimed (1.5B model) | Soft prefer | Orthogonal | [arXiv:2411.13676](https://arxiv.gg/abs/2411.13676) | measured |
| A54 | BitDistiller | distill + QAT | Self-distill for **sub-4-bit** (2–3 bit) LLMs | Good | Partial→Yes path | [arXiv:2402.10631](https://github.com/OpenBitSys/BitDistiller); [ACL PDF](https://aclanthology.org/2024.acl-long.7.pdf) | measured |
| A55 | MiniLLM | distill | On-policy reverse-KL distill to smaller LM | Student size = unique ↓ | Yes on student | [arXiv:2306.08543](https://arxiv.org/pdf/2306.08543) | measured |
| A56 | DistillSpec | distill | On-policy KD for speculative draft; **10–45%** SD speedups; combo **6–10×** latency vs no distill claimed | Serve, not expert unique | N/A | [arXiv:2310.08461](https://arxiv.org/pdf/2310.08461) | measured |
| A57 | On-policy / reverse-KL logit distill (family) | distill | Same axis as MiniLLM/GKD; unique params set by student width | Good | Yes | [MiniLLM](https://arxiv.org/pdf/2306.08543); DistillSpec cites GKD/f-Distill | paper |
| A58 | Mamba-in-Llama distill | distill + arch | Distill Transformer→hybrid SSM; FFN freeze stages | Soft prefer Zamba/Mamba path | Orthogonal then 1-bit | [arXiv:2408.15237](https://arxiv.org/pdf/2408.15237) | measured |
| A59 | SVD-LLM | unique-param / low-rank | Truncation-aware whitening + sequential low-rank update; evaluated at **20–80%** compression ratios (e.g. LLaMA-7B tables) — unique slots ↓ with rank \(r\) | Good on expert FFN mats; then pack survivors **NVFP4** | Yes (structure then 1-bit/NVFP4 pack) | [arXiv:2403.07378](https://arxiv.org/abs/2403.07378) | measured |
| A60 | SVD-LLM V2 | unique-param / low-rank | Heterogeneous per-matrix rank + loss-optimized truncation; claims better PPL than SVD-LLM at same ratios (exact × task-dep.) | Good; NVFP4 on low-rank factors | Yes | [arXiv:2503.12340](https://arxiv.org/html/2503.12340v1) | measured |
| A61 | LASER (layer-selective rank reduction) | unique-param / low-rank | Post-hoc SVD rank keep fraction \(\rho\) (paper examples include \(\rho\) as low as **0.01** on selected mats); quality-focused, not a fixed global \(S\) | Excellent selective expert MLP | Yes after rank cut; NVFP4 factors OK | [arXiv:2312.13558](https://arxiv.org/abs/2312.13558) | measured |
| A62 | SliceGPT | unique-param / structure | Delete rows/cols after orthogonal transform; **up to 25%** params removed (LLaMA-2 70B / OPT 66B keep ~99% zero-shot; Phi-2 ~90%) | Good (shrunk dense expert) | Yes; sliced dense → **NVFP4** hot | [arXiv:2401.15024](https://arxiv.org/abs/2401.15024) | measured |
| A63 | ShortGPT (BI layer removal) | unique-param / depth-share | Drop low Block-Influence layers; ACL report: remove **10/40** layers (**25%**) LLaMA2-13B with modest MMLU drop (55.0→52.2) | Excellent (fewer unique blocks ≈ share) | Yes; remaining layers **NVFP4** | [arXiv:2403.03853](https://arxiv.org/abs/2403.03853); [ACL Findings](https://aclanthology.org/2025.findings-acl.1035.pdf) | measured |
| A64 | MC-SMoE (Merge-then-Compress) | unique-param / MoE-merge | Routing-guided expert merge + low-rank/sparse compress; **up to 80% memory** and **20% FLOPs** reduction claimed w/ virtually no loss | **Native** MoE; survivors → NVFP4 | Yes after merge | [arXiv:2310.01334](https://arxiv.org/abs/2310.01334) | measured |
| A65 | HC-SMoE | unique-param / MoE-merge | Hierarchical clustering on expert outputs + frequency-weighted merge; evaluated at **25% / 37.5% / 50%** expert-parameter reduction on Qwen-MoE (Fig.1) | **Native**; compresses expert cardinality (same axis caveat as Sub-MoE) | Yes; pack merged experts NVFP4 | [arXiv:2410.08589](https://arxiv.org/abs/2410.08589) | measured |
| A66 | SpinQuant | bytes-quant (≠S) / quant-PTQ | Learned rotations; **W4A4KV4** path; LLaMA-2 7B zero-shot gap to FP only **2.9** pts claimed — bytes ≈ **4×** vs FP16 if W4 holds (**not** unique-count \(S\)) | Good per-expert PTQ | No W1; **NVFP4-adjacent** W4/microscaling serve (hot lock prefers NVFP4 over INT4) | [arXiv:2405.16406](https://arxiv.org/abs/2405.16406) | measured |
| A67 | QTIP | bytes-quant (≠S) / quant-PTQ | Trellis-coded + incoherence; ultra-high-dim VQ; SOTA quality/speed claimed at extreme low bit (exact bitwidth task-dep.; UNKNOWN fixed × vs NVFP4) | Good | Partial (≤2–3 bit class); alternate to NVFP4 for cold store | [arXiv:2406.11235](https://arxiv.org/abs/2406.11235) | measured |
| A68 | VPTQ | bytes-quant (≠S) / quant-PTQ | Vector PTQ + residual/outlier; **2-bit** SOTA PPL/acc deltas vs priors; example VQ math ~**15.97×** vs FP16 for one \(4096^2\) config (**≠** unique \(S\)); **1.6–1.8×** throughput vs SOTA | Good | Partial at W2; NVFP4 still preferred hot GEMM | [arXiv:2409.17066](https://arxiv.org/abs/2409.17066) | measured |
| A69 | NOLA | unique-param / PEFT | Random-basis reparam of LoRA factors; on **LLaMA-2 70B** almost **20×** more compact than best LoRA (r=1) w/o accuracy drop claimed — *adapter* unique, not base \(S\) alone | Excellent (hive deltas on shared NVFP4 base) | Yes on 1-bit/NVFP4 base | [arXiv:2310.02556](https://arxiv.org/abs/2310.02556) | measured |
| A70 | LoftQ | bytes-quant + PEFT (≠S base) | Alternating quant + low-rank init for QLoRA gap; strong in **2-bit / 2–4 mixed** regimes vs QLoRA | Good (expert adapters) | Partial; init story ports to **NVFP4+LoRA** hive | [arXiv:2310.08659](https://arxiv.org/abs/2310.08659) | measured |
| A71 | QA-LoRA | bytes-quant + PEFT (≠S base) | Group-wise quant-aware LoRA; merge into **INT4** without FP upcast at infer | Good | No W1; mergeable low-bit aligns with locked **NVFP4** serve better than QLoRA FP dequant | [arXiv:2309.14717](https://arxiv.org/abs/2309.14717) | measured |
| A72 | Compacter | unique-param / PEFT | Kronecker hypercomplex adapters; trains **0.047%** of PLM params (GLUE/SuperGLUE) | Excellent thin expert deltas | Yes | [arXiv:2106.04647](https://arxiv.org/abs/2106.04647) | measured |
| A73 | AdaLoRA | unique-param / PEFT | SVD-form \(\Delta=P\Lambda Q\) + importance rank budget; best in low-budget PEFT (no single global ×) | Excellent | Yes on NVFP4/1-bit base | [arXiv:2303.10512](https://arxiv.org/abs/2303.10512) | measured |
| A74 | PiSSA / QPiSSA | unique-param / PEFT (+ quant) | Principal-SVD init of LoRA; same storage as LoRA rank \(r\); QPiSSA **4-bit** reduces init quant error vs QLoRA (LLaMA-3-70B GSM8K 86.05% vs QLoRA 81.73%) | Excellent | Yes; QPiSSA **4-bit** path ↔ NVFP4 adapter stacks | [arXiv:2404.02948](https://arxiv.org/abs/2404.02948) | measured |
| A75 | BitNet a4.8 | bytes-quant + serve-util (≠S) | W1.58 + **4-bit acts** (INT4/FP4 kernels); activates **~55%** params; **3-bit KV** — unique count unchanged; FP4 acts ≠ locked weight NVFP4 | Good on BitLinear experts | **Yes (weights)**; acts FP4/INT4 | [arXiv:2411.04965](https://arxiv.org/abs/2411.04965) | measured |
| A76 | EfficientQAT | bytes-quant (≠S) / QAT | Block-AP then e2e quant-param train; strong **2–3 bit** QAT vs PTQ (memory/time claims hardware-dep.; UNKNOWN single ×) | Good | Partial→Yes path; NVFP4 QAT still immature on sm121 | [arXiv:2407.11062](https://arxiv.org/abs/2407.11062) | measured |
| A77 | MoEfication | serve-util (≠S) / MoE-arch | Split dense FFN→experts; use **10–30%** FFN params conditional; **~2×** speedup @ **25%** FFN — *activation* sparsity, **not** unique-param \(S\) | Native grain after split | Yes | [arXiv:2110.01786](https://arxiv.org/abs/2110.01786); [ACL Findings](https://aclanthology.org/2022.findings-acl.71.pdf) | measured |
| A78 | HydraLoRA | unique-param / PEFT + MoE | Asymmetric shared **A** + multiple **B** MoE experts; parameter-efficient multi-component adapters (exact × vs LoRA UNKNOWN here) | **Excellent** for LoRA-Hive on NVFP4 shared base | Yes | [arXiv:2404.19245](https://arxiv.org/abs/2404.19245) | measured |
| A79 | Wanda | unique-param / unstructured-pruning | Activation-magnitude prune; **~2×** unique weights at **50%** sparsity (also 2:4 / 4:8); no retraining — pruned LLM usable as-is | Fair (per-weight inside experts; not whole-expert cut) | Partial if composed with separate 1-bit/NVFP4 pack on survivors | [arXiv:2306.11695](https://arxiv.org/abs/2306.11695) | measured |
| A80 | OATS | unique-param / sparse+low-rank | Outlier-aware sparse + low-rank decomp; up to **~60%** param compression (~**2.5×**) on Llama-3 / Phi-3 w/o retraining; up to **1.37×** CPU vs comparable prune claimed | Fair (layerwise mats; no router logic) | No native W1; survivors → **NVFP4** hot | [arXiv:2409.13652](https://arxiv.org/abs/2409.13652) | measured |
| A81 | REAP | unique-param / MoE-expert-prune | Router-weighted one-shot **expert** prune; near-lossless code-gen claimed on Qwen3-Coder-480B / Kimi-K2 at **50%** experts (~**2×** expert cardinality) | **Native** SMoE | No (deletes experts); pack survivors **NVFP4** | [arXiv:2510.13999](https://arxiv.org/abs/2510.13999) | measured |
| A82 | CAMERA-P | unique-param / MoE-micro-expert-prune | Joint up/gate/down micro-expert redundancy prune; beats strong baselines at **20–60%** prune (~**1.25–2.5×**); Camera-Q = mixed-precision sibling (≠ this row) | **Excellent** coordinated micro-experts | No W1; kept micro-experts → **NVFP4** | [arXiv:2508.02322](https://arxiv.org/abs/2508.02322) | measured |
| A83 | FourierFT | unique-param / PEFT-spectral | Discrete Fourier ΔW; LLaMA2-7B instruct: **0.064M** trainable vs LoRA **33.5M** (~**500×** adapter compact) — *adapter* unique (math-gap #2) | Fair (module PEFT; not expert merge) | No; freeze **NVFP4** base + tiny spectral adapters | [arXiv:2405.03003](https://arxiv.org/abs/2405.03003) | measured |
| A84 | D²-MoE (Delta Decompression) | unique-param / MoE-delta-SVD | Shared base + per-expert low-rank deltas + semi-dynamic base prune; table lists up to **80%** param compression (~**5×**); strong at **60%** too | **Excellent** share+delta MoE | Partial (SVD deltas further quantizable); shared base → **NVFP4** lock | [arXiv:2502.17298](https://arxiv.org/abs/2502.17298) | measured |
| A85 | CALDERA | bytes-quant (≠S) / Q+LR-decomp | \(W\approx Q+LR\); SOTA claimed in **&lt;2.5 bits/param** on LLaMA-2 7B/13B/70B + LLaMA-3 8B (**≠** unique \(S\); bpp meter) | Fair (layerwise; no MoE router) | Partial (aggressive Q e.g. 2-bit + higher-bit LR); Q may align to **NVFP4** blocks | [arXiv:2405.18886](https://arxiv.org/abs/2405.18886) | measured |
| A86 | ResMoE | unique-param / MoE-residual-share | Wasserstein barycenter expert + compressed residuals (prune/SVD); up to **75%** expert-param reduction (~**4×**) at comparable quality claimed | **Excellent** residual-share MoE | No native W1; barycenter+residuals → **NVFP4** after restore | [arXiv:2503.06881](https://arxiv.org/abs/2503.06881) | measured |
| A87 | SparseGPT | unique-param / one-shot prune | ≥**50%** unstructured sparsity one-shot on OPT/BLOOM-175B w/ minor PPL rise; **60%** still “negligible” PPL on 175B; also 2:4/4:8; joint **50%+4-bit** OK on OPT-175B (~**2–2.5×** unique-nonzero) | Fair (layerwise inside expert linears; not expert-share) | Partial — prune axis; paper shows compat with weight quant; survivors → **NVFP4** | [arXiv:2301.00774](https://arxiv.org/abs/2301.00774) | measured |
| A88 | OWL (Outlier Weighed Layerwise sparsity) | unique-param / non-uniform layerwise prune | Layer sparsity ∝ outlier ratio on Wanda/SparseGPT metrics; beats uniform at **70%** sparsity (paper: +61.22 / +6.80 PPL vs Wanda/SparseGPT); **2.6×** DeepSparse e2e claimed (~**3.3×** unique-nonzero @70%) | Fair (improves dense/expert-linear prune; not MoE-native) | Partial — sparsity only; pack survivors **NVFP4** | [arXiv:2310.05175](https://arxiv.org/abs/2310.05175) | measured |
| A89 | Sheared-LLaMA | unique-param / structured prune + continued pretrain | Targeted prune (layers/heads/intermediate+hidden); **~2.6×** (7B→2.7B) and **~5.4×** (7B→1.3B) unique vs LLaMA2-7B; **~3%** compute vs train-from-scratch claimed | Fair (dense shearing; MoE needs expert-aware targets) | No as method (smaller dense FP); bits orthogonal post-step → **NVFP4** hot | [arXiv:2310.06694](https://arxiv.org/abs/2310.06694) | measured |
| A90 | QMoE | disk/codec (≠S) / sub-1-bit MoE encode | SwitchTransformer-c2048 **1.6T → <160GB** (~**0.8 bit/param**, ~**20×** vs FP16); **<5%** runtime overhead vs ideal uncompressed claimed | **Excellent** (trillion-param Switch MoE; entropy coding + GPU decode) | Yes path (ternary/2-bit grids + lossless codec to sub-1-bit/param) — **≠** replacing locked **NVFP4** hot GEMM | [arXiv:2310.16795](https://arxiv.org/abs/2310.16795) | measured |
| A91 | NAEE (Not All Experts Are Equal) | unique-param / MoE expert prune + dynamic skip | Post-training drop **2/8** Mixtral experts → ~**25%** expert-param cut; **2→1×80GB** A100 mem + ~**1.2×** infer; mild drop ~**2.9** agnostic / ~**6.2** task-specific (recoverable) | **Native** expert-grain prune/skip | N/A (cardinality cut, not bit-width); survivors → **NVFP4** | [arXiv:2402.14800](https://arxiv.org/abs/2402.14800) | measured |
| A92 | BitStack | unique-param / residual ~1-bit SVD stack | Training-free iterative abs-SVD residual blocks ≈**1 bit/param**/block; any-size RAM↔disk load; matches/beats GPTQ/AWQ at aligned memory esp. extreme ratios (× vs FP16 = budget-dep.) | Good (per-linear stacks on expert FFNs) | **Yes** (sign matrix + few FP singular vectors / block); variable load orthogonal to fixed **NVFP4** hot lock | [arXiv:2410.23918](https://arxiv.org/abs/2410.23918) | measured |
| A93 | TernaryLLM | bytes-quant (≠S) / ternary QAT | Dual-path: abs-mean (TWN) + learnable scaling for ternary LLM weights; competitive W1.58-class quality claimed on LLaMA family (exact × vs FP16 ≈ **16/1.58** storage arith if ternary holds; **≠** unique \(S\)) | Good (per-expert ternary pack) | **Yes (ternary)** — research/cold; hot serve still prefers locked **NVFP4** | [arXiv:2406.07177](https://arxiv.org/abs/2406.07177) | measured |
| A94 | ZipLM | unique-param / structured prune | Latency-aware structured pruning for LMs; compresses to match hardware targets with recovery fine-tune (exact global × task-dep.; UNKNOWN single fixed \(S\)) | Fair (structured width/depth cuts inside blocks) | No native W1; pruned dense → **NVFP4** | [arXiv:2302.04089](https://arxiv.org/abs/2302.04089) | measured |
| A95 | LaCo | unique-param / depth-collapse | Layer Collapse merge; **25–30%** prune keeps **>80%** avg task performance claimed | Good (depth cut; MoE needs router/expert align) | Yes after collapse; remaining layers **NVFP4** | [arXiv:2402.11187](https://arxiv.org/abs/2402.11187) | measured |
| A96 | APT | unique-param / prune+PEFT | Adaptive prune+tune; RoBERTa/T5 keep **≤98%** task @ **40%** params left; LLaMA **86.4%** @ **70%** remained; FT up to **8×** faster / train mem **↓70%** claimed | Good (salience on expert/shared; router usually kept) | Partial; pruned structure → **NVFP4** Linear | [arXiv:2401.12200](https://arxiv.org/abs/2401.12200) | measured |
| A97 | Prefix-Tuning | unique-param / PEFT-prefix | Continuous prefixes; task adapter ≈ **0.1%** of params vs full FT (math-gap #2 — base unique unchanged unless shared) | Fair (shared/task prefixes; does not shrink experts) | Yes on frozen 1-bit/**NVFP4** base; prefixes higher-prec side tensors | [arXiv:2101.00190](https://arxiv.org/abs/2101.00190) | measured |
| A98 | LLM Surgeon | unique-param / curvature-prune | K-FAC-style unstructured / semi / structured prune; structured row/col **20–30%** on OPT + Llama-2-7B negligible loss claimed | Fair (per linear/expert mat; costly at large \(E\)) | No native W1; width cuts help **NVFP4** GEMM shapes | [arXiv:2312.17244](https://arxiv.org/abs/2312.17244) | measured |
| A99 | LLM-Pruner | unique-param / structural-prune | Dependency-aware structural prune; ~**20%** param removal with modest recovery (exact × task-dep.; paper LLaMA/Vicuna class) | Fair (group prune inside blocks; not expert-share) | No native W1; survivors → **NVFP4** | [arXiv:2305.11627](https://arxiv.org/abs/2305.11627) | measured |
| A100 | MoE-SVD | unique-param / MoE-SVD-share | Training-free SVD on MoE experts: selective decomp + **shared V** across experts + top-k **U** trim; claims **60%** compression ratio (~**2.5×** unique) and **1.5×** faster infer w/ minimal loss (Mixtral / Phi-3.5 / DeepSeek / Qwen2 MoE) | **Excellent** MoE-native share+rank | No native W1; low-rank factors → **NVFP4** hot | [PMLR ICML 2025](https://proceedings.mlr.press/v267/li25az.html); [OpenReview](https://openreview.net/forum?id=acJ3vdFljk); [lliai/MoE-SVD](https://github.com/lliai/MoE-SVD) | measured |
| A101 | LightMoE | unique-param / MoE-expert-replace | Expert *replacing* (not prune/merge): adaptive select → hierarchical shared bases + LoRA-style adapters + anneal; matches LoRA FT @ **30%** compress; @ **50%** claims **+5.6%** avg vs prior methods (5 tasks) | **Excellent** share+thin-delta MoE | Yes path on adapters; shared bases → **NVFP4** | [arXiv:2603.12645](https://arxiv.org/abs/2603.12645); [HTML](https://arxiv.org/html/2603.12645) | measured |
| A102 | DERN | unique-param / MoE-neuron-recombine | Drop Experts, Recombine Neurons: router prune → neuron-segment reassign → merge into retained experts; retraining-free; **>5%** avg gain vs priors @ **50%** expert sparsity (Mixtral/Qwen/DeepSeek); Mixtral 8→6 keeps near-full acc @ **~25%** mem ↓ | **Native** expert+neuron grain | N/A bit-width; survivors → **NVFP4** | [arXiv:2509.10377](https://arxiv.org/abs/2509.10377); [HTML](https://arxiv.org/html/2509.10377) | measured |
| A103 | CAT-Q | bytes-quant (≠S) / ternary-PTQ | Post-training ternarization (LM+softened ST); 512 calib samples; claims beat BitNet b1.58 v1/v2 @ 1.7–8B w/ ~**100,000×** fewer tokens; scales to **14B–235B** in 8–60h / 8×A100 — storage ≈ **16/1.58** if ternary holds (**≠** unique \(S\)) | Good (dense+MoE PTQ) | **Yes (ternary weights)**; research/cold — hot serve still prefers locked **NVFP4** | [arXiv:2606.26650](https://arxiv.org/abs/2606.26650); [HTML](https://arxiv.org/html/2606.26650v1); [BitTern](https://github.com/IntelChina-AI/BitTern) | measured |
| A104 | BitsMoE | bytes-quant (≠S) / MoE-spectral-mixed | SVD shared basis (kept **unquantized**) + ILP bit-alloc on expert spectral factors; Qwen3-30B-A3B @ **2-bit**: **12.3×** faster quant, **+27.83** pp avg acc, **1.76×** decode vs GPTQ claimed — bpp meter (**≠** unique \(S\)); shared basis is orthogonal unique-share hook | **Excellent** MoE PTQ grain | Partial (mixed ≤2-bit factors); shared basis / survivors → **NVFP4** preferred hot GEMM | [arXiv:2606.00079](https://arxiv.org/abs/2606.00079); [HTML](https://arxiv.org/html/2606.00079); [BitsMoE code](https://github.com/zjiayu064/BitsMoE) | measured |

**Count this lane:** **104** distinct method rows (A01–A104). Prior wave A59–A78: **20** IDs (2026-09-05; `OVERSEER_COMPRESSION_CATALOG_CURATE_2026_09_05`). Prior A79–A86: **8** IDs (`BITNET_COMPRESSION_CATALOG_A79_A86_2026_09_06`). Prior A87–A94: **8** IDs (`BITNET_COMPRESSION_CATALOG_A87_A94_2026_09_06`). Curate wave A95–A99 + source harden A08/A14/A16–A18: **5** new IDs (2026-09-06; needle `BITNET_COMPRESSION_CATALOG_A95_A99_2026_09_06`). Curate wave A100–A104 + axis harden A45–A49 → `KV (≠S)`: **5** new IDs + **5** axis fixes (2026-09-08; needle `BITNET_COMPRESSION_CATALOG_A100_A104_2026_09_08`).

**Axis legend:**  
- **`unique-param / …`** — counts toward north-star \(S\approx100\) (share, low-rank, structure prune, MoE-merge cardinality, PEFT *adapter* unique — still subject to math-gap #2 for PEFT).  
- **`bytes-quant (≠S)`** — bit-width / VQ packing; does **not** cut unique count.  
- **`KV (≠S)`** / **`disk/codec (≠S)`** / **`serve-util (≠S)`** — orthogonal meters (PagedAttention, zstd, kernel speed, activation sparsity).  
- Legacy shorthand: `quant-*`, `low-rank`, `MoE-*`, `arch`, `distill` as before.

#### MoE-grain + Zamba/Mamba-2 notes (soft preference)

| Fit | Methods |
| --- | --- |
| Strong MoE grain | A11–A14, A19–A24, A28, A33, A36–A44, A59–A65, A69, A72–A74, A78, A81–A82, A84, A86, A90–A91, A95–A96, A98–A102, A104 |
| Later SSD/hybrid serve | A50–A53, A58; KV A45–A49 for decode mem |
| Do not confuse with unique-param north star | A45–A49 (KV ≠S), A08/A14/A16–A18/A66–A68/A70–A71/A75–A76/A85/A93/A103–A104 (bytes-quant ≠S), A77 (serve-util), A90 (disk/codec ≠S), pure speed claims on A50; never zstd/PagedAttention as \(S\) |

#### Novel stack hypotheses

Each labeled **hypothesis** — **not measured**. Aimed at ≈100× unique-param reduction *on top of* 1-bit packing for a 1B logical expert → ~10M unique 1-bit slots.

| ID | Stack (sketch) | Rough unique-param math | Risks / gaps |
| --- | --- | --- | --- |
| H1 | ALBERT-style **L-way** full block share × BitNet b1.58 experts | If \(L=32\) layers share 1 block: **32×** unique ↓; still need ~**3×** more (rank/dict) to hit 100× | Quality of deep recurrence on generative MoE UNKNOWN; ALBERT factor was encoder MLM |
| H2 | Shared DeepSeek-style backbone FFN + **MoBiE** binary routed experts + VeRA/IA3 deltas | Shared trunk removes most per-expert mass; routed expert = thin binary residual; unique ≈ trunk/\(E\) + residual | Residual rank must be tiny; routing under W1 distortion (MoBiE addresses some) |
| H3 | Basis Sharing across expert layers × ASVD rank \(r \ll d\) × ternary pack | Example: share bases over \(G=8\) layers + keep \(r/d=1/4\) → order **8×4=32×** structure; need another **~3×** (dict/Kronecker) | Basis Sharing measured 20–50% ratios, **not** 100× alone ([arXiv:2410.03765](https://arxiv.org/html/2410.03765v1)) |
| H4 | DictFormer dictionary for all expert FFNs × Kronecker/TT cores × BitDistiller/OneBit | Dict coeffs per expert + shared atoms; TT on atoms; 1-bit on coeffs | DictFormer MT numbers (**3.6×**) far below 100×; stacking factors may not multiply cleanly |
| H5 | Sub-MoE merge to fewer logical experts **then** H1/H2 per survivor × Zamba shared-attn serve | Merging cuts expert count (storage pool), not per-expert 1B→10M; combine with share/rank | Merge retains 86–96% at 25–50% expert cut ([Sub-MoE](https://arxiv.org/pdf/2506.23266)) — wrong axis alone for 100× |

**Illustrative product (H1×rank):** \(32_{\text{share}} \times 4_{\text{rank}} = 128\) ≈ north-star **100×** unique reduction **if** quality holds — **hypothesis only**.

#### Math gaps (call out)

1. **Bit-width ≠ unique count:** BitNet ~10× vs FP16 bytes leaves unique params at 1B; north star needs **another ~100×** unique collapse.
2. **PEFT ≠ deployment unique:** LoRA/VeRA 10k× claims are *trainable* adapters, not compressed base expert storage unless base itself is shared/factored.
3. **No multiplicative theorem:** Paper factors (ALBERT 18×, DictFormer 3.6×, ASVD 10–30%, Sub-MoE 2× expert cut) **must not** be naively multiplied without interaction experiments.
4. **MoE merge ≠ per-expert 10M:** Sub-MoE/MergeMoE shrink expert *cardinality*; per-expert footprint can stay large.
5. **KV methods (MLA/GQA/YOCO/CLA)** do not advance the 1B→10M weight north star.
6. **SEEP** as a named merger was **not** located as a canonical paper this run; closest measured mergers now in Lane A: Sub-MoE (A42), MergeMoE (A43), **MC-SMoE (A64)**, **HC-SMoE (A65)**.
7. **UNKNOWN** markers retained wherever a numeric × was not explicitly verified in fetched text.

#### Top-5 north-star spot-check footnotes (2026-09-05 pristine audit)

[^fn-a11]: **BitNet b1.58** — ternary \(\{-1,0,+1\}\) confirmed ([arXiv:2402.17764](https://arxiv.org/abs/2402.17764)). **16/1.58≈10×** is kit storage-vs-FP16 arith, **not** unique-param \(S\). Does **not** satisfy 1B→10M@same-1-bit alone (**C147**).
[^fn-mobie]: **MoBiE** — PTQ MoE binarization confirmed ([arXiv:2604.06798](https://arxiv.org/abs/2604.06798)). Fit column must not be read as measured **100×** unique delivery; W1 path only.
[^fn-albert]: **ALBERT** — “18× fewer params” / “~1.7×” train speed vs BERT-large-like config confirmed in paper HTML ([arXiv:1909.11942](https://arxiv.org/abs/1909.11942)). Encoder MLM era — MoE generative quality at extreme \(L\) = **UNKNOWN**.
[^fn-lora]: **LoRA** — “10,000× fewer **trainable**” on GPT-3 example confirmed ([arXiv:2106.09685](https://arxiv.org/abs/2106.09685)). **OVERCLAIM** if sold as unique *base* expert storage without share/factor base (**math gap 2**).
[^fn-vera]: **VeRA** — shared frozen random pair + scaling vectors; trainable ≪ LoRA confirmed ([arXiv:2310.11454](https://arxiv.org/abs/2310.11454)). Same PEFT caveat as LoRA for north-star unique count.
[^fn-dsmoe]: **DeepSeekMoE** — abstract: DeepSeekMoE 2B ≈ GShard 2.9B while GShard has **1.5×** the expert params/compute ([arXiv:2401.06066](https://arxiv.org/abs/2401.06066)). Wording fixed from ambiguous “1.5× fewer.” Architecture helps grain/share; **not** alone 100× unique.

---

*End Lane A (2026-09-08; curate waves A59–A78 + A79–A86 + A87–A94 + A95–A99 + A100–A104).*

---

### Lane B — North-star math (1B → 10M @ 1-bit) (2026-09-05)

**Ledger:** `BITNET_FACTCHECK.md` **C139–C152**. Arith **PASS**; quality at extreme stacks **UNKNOWN**.

#### Same-bitwidth footprint

\[
\mathrm{bytes}(N @ 1\text{-bit packed}) = N/8
\]

| View | Params | Bytes @ 1-bit |
|------|-------:|--------------:|
| Logical expert | \(10^9\) | **125 MB** |
| Target unique | \(10^7\) | **1.25 MB** |
| Required \(S\) | \(10^9/10^7\) | **100×** |

FP16→1-bit alone ≈ **16×** bytes — secondary meter only (**C147**).

#### Stacks that arithmetically hit ~100× (quality = HYPOTHESIS)

| ID | Stack | \(S\) (arith) | Notes |
|----|--------|--------------:|-------|
| **B1** | Cross-layer share \(L{=}100\) alone | **100×** | ALBERT-class mechanism; quality UNKNOWN (**C143**) |
| **B2** | \(L{=}48\) (**~48×**; rem. ~20.8M) × mild rank ~2.08× (\(r\approx983\) @ \(d{=}4096\), \(f{=}1\)) | **~100×** | Needs near-full factorizable mass; do not label rem. 20.8M as “20.8×” (**C142**) |
| **B3** | \(L{=}10\) × rank ~10× (\(r\approx205\) @ \(d{=}4096\)) | **100×** | Same independence caveat (**C146**) |
| **B4** | \(L{=}4\) × rank ~25× (\(r\approx82\)) | **100×** | Aggressive rank |
| **B5** | \(L{=}20\) × ~5× low-rank (honest fraction) | **~100×** | Prefer when \(f{<}1\) |

Rank-only 100× on all-square \(d{=}4096\) needs \(r\approx20.5\); with dense remainder \(f\le0.99\), rank-alone **cannot** hit 0.01 unique fraction (**C145**).

#### Orthogonal / non-byte levers

- **Mamba-2 SSD / Zamba:** utilization / linear-attention dual — **not** unique-param cut (**C148–C149**).
- **Distill (BitDistill / MiniLLM class):** quality into constrained student — **not** the 100× equation (**C150**).
- **Data prune:** **FORBIDDEN** (**C151**).
- **Lane C named stacks as measured delivery:** **FAIL** until T0+ (**C152**).

#### Open UNKNOWN (math lane)

1. Quality of any ~100× stack on a 1B granular MoE expert @ 1-bit  
2. Whether real experts are \(f\approx1\) factorizable (embed/norms/routers)  
3. Share × rank independence in training  
4. Hub-measured SSD/Zamba util (papers ≠ kit KPI)  
5. Distill recovery at exactly 100× unique cut  
6. Scale/ABS overhead vs perfect-pack 125 / 1.25 MB  

*End Lane B (2026-09-05).*
