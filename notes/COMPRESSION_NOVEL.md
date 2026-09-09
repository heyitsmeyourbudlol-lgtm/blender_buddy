# Compression novel hypotheses (Lane C writeups)

**Status:** hypotheses until T-series runs; **T0 packing math measured** 2026-09-05 (`OVERSEER_COMPRESSION_T0_PACK_2026_09_05`) — quality still N/A; **T1 share-factor measured** (`OVERSEER_COMPRESSION_T1_SHARE_2026_09_05`) — mono \(U\downarrow\); weak \(k\) was **arith short of \(S{=}100\)** (misnamed “quality cliff”); high \(k\) clears \(S\); train_unlocked=false.

**North star:** logical MoE expert ~**1B** params → unique store ~**10M @ 1-bit** (**100×** unique-param compression). Comparison bitwidth: **1-bit vs 1-bit** (byte wins = unique-param / packing wins only).  
**Constraints:** ALBERT-style cross-layer sharing + LoRA/SVD + teacher distill welcome; **no data pruning**; Zamba/Mamba-2 SSD is **orthogonal** (compute-graph utilization), usable in hybrids.  
**Catalog table:** [`COMPRESSION_CATALOG.md`](COMPRESSION_CATALOG.md) · **L5 RAM/grain math:** [`BITNET_ARCH_RESEARCH.md`](BITNET_ARCH_RESEARCH.md) L5 · **tasks:** [`BITNET_RESEARCH_TASKS.md`](BITNET_RESEARCH_TASKS.md).

---

## Shared notation

| Symbol | Meaning |
|--------|---------|
| \(N_{\text{logic}}\) | Logical expert parameter count (~1B north-star; tiny in T0) |
| \(U\) | Unique stored parameters (trainable or packed nonzero) |
| \(k\) / \(L\) | Cross-layer share factor / depth |
| \(r\) | LoRA / SVD rank |
| \(E\) | Number of MoE experts sharing a hive/bank |
| \(s\) | Keep-density for **weight** sparsity (\(0<s\le1\)); **not** dataset keep-rate |

**Arith compression (this lane):** at fixed 1-bit,

\[
C_{\text{arith}} \approx \frac{N_{\text{logic}}}{U}
\]

(ignoring scale/zp/index until packing format fixed — same UNKNOWN spirit as L5-U1).

**L5 bridge:** L5 shows far-map **10M @ FP4 ≈ 5 MB** fits ~24 MB L2-class; at **1-bit**, the same unique count is ~**1.25 MB** raw (\(10^7/8\)) — even friendlier for residency **if** unique-param target holds. Near-map **0.61B** remains stream-only; north star is **unique-param fold** of a logical ~1B expert into that far-map-sized store — not claiming FP4 L5 numbers as 1-bit measurements.

---

## Hypothesis writeups

### 1. ALBERT-BitMoE — `hypothesis`

**Arrangement:** One 1-bit expert FFN body shared across layers (ALBERT), plus small per-layer LoRA to restore depth identity.

**Unique-param formula:**

\[
U = \frac{B_{\text{body}}}{L_{\text{share}}} + L \cdot r(d_{\text{in}}+d_{\text{out}})
\]

(with full share \(L_{\text{share}}=L\)). Target \(U\sim10^7\) for \(N_{\text{logic}}\sim10^9\).

**Expected arith compression:** ~50–120× if body dominates and LoRA stays small.

**Quality risk:** Layers become interchangeable; long-context or deep reasoning regresses.

**Distill plan:** Teacher = independent-layer 1-bit (or higher-prec then quant) expert stack → student shared body; KD on logits + optional hidden alignment per layer; freeze body, fit LoRA, then joint BitDistill.

**Serve note:** Body via BitLinear/int1 kernels; LoRA adapters on Tensor Cores (BF16/FP16). SSD optional on **backbone only** (orthogonal).

**Falsifier:** Under quality gate ε, best \(U > 2\times10^7\), or share factor must drop to ~1.

---

### 2. SVD-TieStack — `hypothesis`

**Arrangement:** Factor each expert projection with SVD; **tie** \(U,\Sigma,V\) (or \(U,V\)) across layers; keep a thin ternary/1-bit residual.

**Unique-param formula:** \(U = r(d_{\text{in}}+d_{\text{out}})[+r] + R_{\text{tern}}\) with cross-layer tie.

**Expected arith compression:** ~40–100× for moderate \(r\).

**Quality risk:** Low-rank bias; residual budget creeps past 10M.

**Distill plan:** SVD-init from teacher W; distill residual; quantize factors/residual to 1-bit schedule.

**Serve note:** Factors = dense GEMM (TC); residual = 1-bit kernel.

**Falsifier:** Cannot hit reconstruction or task ε with \(U\le10\mathrm{M}\).

---

### 3. LoRA-Hive — `hypothesis`

**Arrangement:** Single shared 1-bit hive expert; each routed expert is hive + LoRA delta (expert tying / multi-LoRA MoE).

**Unique-param formula (amortized per expert):** \(U_e \approx B_{\text{hive}}/E + r(d_{\text{in}}+d_{\text{out}})\).

**Expected arith compression:** Approaches **100×** when \(E\) is large and hive is ~10M total shared.

**Quality risk:** Experts collapse to hive; load-balance / specialty dies.

**Distill plan:** Average or SVD-merge teacher experts → hive; fit per-expert LoRA to residuals; BitDistill with router frozen then unfrozen.

**Serve note:** Hive may sit whole in L2-class at ~10M@1-bit (~1.25 MB raw); adapters TC. Cross-check L5 far-map residency intuition (different bitwidth — do not treat as measured).

**Falsifier:** Heldout specialty mix requires near-independent experts (\(U_e \to N_{\text{logic}}\)).

---

### 4. Zamba-Ternary-Hive — `hypothesis`

**Arrangement:** **Zamba / Mamba-2 SSD** trunk for sequence mixing (**GPU utilization of compute graph**); **ternary/1-bit MoE experts** with **shared** low-rank adapters (weight path). Explicitly: SSD ≠ weight-byte compression.

**Unique-param formula:** Expert-side \(U_{\text{exp}} = T_{\text{shared}} + A_{\text{LoRA}}\) (backbone counted separately for serve, not in 1B→10M expert ratio).

**Expected arith compression:** Expert unique ~100× vs logical 1B expert; backbone ratio out of scope for north-star expert metric.

**Quality risk:** SSM/transformer mismatch; hybrid training instability.

**Distill plan:** Freeze or lightly adapt SSD trunk; distill MoE experts from teacher transformer-MoE into ternary hive+adapters.

**Serve note:** SSD kernels for backbone; ternary Bit kernels for experts; adapters on TC. Use when decode is compute-bound on mix, not when weight I/O dominates.

**Falsifier:** No expert \(U\) win **or** SSD hybrid slower/worse than BitMoE-only under same weight budget.

---

### 5. Distill-Fold — `hypothesis`

**Arrangement:** Progressive ALBERT fold (\(k=2,4,8,\ldots\)) under BitDistill/KD into 1-bit student.

**Unique-param formula:** \(U \approx N_{\text{logic}}/k +\) untied norms/adapters.

**Expected arith compression:** Primarily \(k\times\); combine with LoRA-Hive/SVD to chase 100×.

**Quality risk:** Folded depth loses capacity faster than KD can recover.

**Distill plan:** Teacher → fold-\(k/2\) student → fold-\(k\); logit KD + feature KD on surviving blocks.

**Serve note:** Vanilla BitLinear stack; fewer unique weights → better cache behavior (L5 spirit).

**Falsifier:** Required \(k\) for \(U\le10\mathrm{M}\) breaks quality gate.

---

### 6. BasisBank — `hypothesis`

**Arrangement:** Shared 1-bit dictionary \(D\); each expert stores sparse codes (+ micro-LoRA).

**Unique-param formula:** \(U_e = \|D\|/E + \text{codes} + r_\mu(\cdot)\).

**Expected arith compression:** 50–200× with heavy amortization.

**Quality risk:** Codebook collapse; **index/pack overhead** destroys byte wins.

**Distill plan:** Dictionary learning on teacher expert weights; KD on outputs; freeze \(D\), train codes+LoRA.

**Serve note:** Keep \(D\) hot; packed gathers. Byte math must include indices (L5-U1-style honesty).

**Falsifier:** Packed bytes ≥ dense \(10\mathrm{M}@1\)-bit store.

---

### 7. Twin-Rank Cascade — `hypothesis`

**Arrangement:** Shared BitLinear body + nested LoRA ranks (coarse then fine) instead of one wide LoRA.

**Unique-param formula:** \(U = B_{\text{share}} + \sum_i r_i(d_{\text{in}}+d_{\text{out}})\).

**Expected arith compression:** ~100× if share dominates.

**Quality risk:** Nested adapter optimization fails vs single rank.

**Distill plan:** Stage-wise: body from teacher → r_hi → r_lo; BitDistill last.

**Serve note:** Multiple small TC GEMMs vs one larger; body 1-bit.

**Falsifier:** Cascade \(U\) exceeds single-LoRA+share for same quality.

---

### 8. Mirror-Expert — `hypothesis`

**Arrangement:** Tie experts in groups of \(g\) (mirror twins); SVD/LoRA residual per member.

**Unique-param formula:** \(U_e = W_{\text{tie}}/g + \mathrm{SVD}_r\).

**Expected arith compression:** \(g\times\) times low-rank factor.

**Quality risk:** Twins cannot specialize.

**Distill plan:** Init ties from nearest teacher experts; residual KD; optional router co-train.

**Serve note:** One tied weight copy in memory; residuals streamable.

**Falsifier:** Best \(g\to1\) under quality gate.

---

### 9. HyperSeed — `hypothesis`

**Arrangement:** Compact 1-bit (or ternary) hypernetwork maps per-expert seed → LoRA on shared body.

**Unique-param formula:** \(U = H + B_{\text{share}} + E\cdot\|s\|\) amortized per expert.

**Expected arith compression:** ~100× if \(H+B\) shared and seeds tiny.

**Quality risk:** Hypernet cannot express teacher diversity; seed collisions.

**Distill plan:** Collect teacher LoRA bank → supervise hypernet; freeze body; BitDistill.

**Serve note:** Run hypernet at expert-load / compile time; serve body+materialized LoRA.

**Falsifier:** \(H+\)seeds+\(B > 10\mathrm{M}\) unique **or** quality ≪ static LoRA-Hive.

---

### 10. PackSparse-1b — `hypothesis`

**Arrangement:** Structured **weight** sparsity (N:M / block) on ALBERT-shared 1-bit expert + **packing** of nonzeros. **Not** training-data pruning. Unstructured SparseGPT-style masks allowed only with explicit pack+index byte math.

**Unique-param formula:** \(U_{\text{nz}} = s\cdot N_{\text{logic}}/k_{\text{share}}\); store = pack(\(U_{\text{nz}}\)) + index.

**Expected arith compression:** Unique \(1/(s)\times k\); **bytes** only if pack beats dense 1-bit.

**Quality risk:** Index tax; immature sparse-1bit kernels.

**Distill plan:** Dense teacher → mask from weight magnitudes / SparseGPT-on-weights → KD (**weights only**; dataset unchanged).

**Serve note:** Sparse Bit GEMM or TC sparse paths if present.

**Falsifier:** Packed size ≥ dense 10M@1-bit **or** method requires dropping training data → **reject recipe**.

---

### 11. MLA-ShareBit — `hypothesis`

**Arrangement:** Borrow MLA-style low-rank latent bottlenecks on expert FFN projections; ALBERT-share latents; outer maps 1-bit.

**Unique-param formula:** \(U =\) latent maps + shared core.

**Expected arith compression:** ~30–100× by latent rank.

**Quality risk:** Bottleneck floor on expert capacity.

**Distill plan:** SVD warm-start latents from teacher; KD; quantize.

**Serve note:** Latent dense on TC; outer BitLinear.

**Falsifier:** Latent rank inflates \(U>10\mathrm{M}\) to meet ε.

---

### 12. Teacher-SVD-ALBERT — `hypothesis`

**Arrangement:** **Combo stack** (preferred integration hypothesis): teacher KD → SVD factors → ALBERT cross-layer tie → LoRA polish → 1-bit schedule. Optional Zamba SSD backbone as **serve-only** orthogonal add-on.

**Unique-param formula:** \(U = B_{\text{SVD,share}} + L\cdot r_{\text{LoRA}}(\cdot)\).

**Expected arith compression:** Design target **100×** (1B→10M@1-bit).

**Quality risk:** Error compounds across stages.

**Distill plan:** Multi-stage gates — each stage must pass local ε before next.

**Serve note:** Factors TC; body/residual 1-bit; SSD trunk optional (compute, not bytes).

**Falsifier:** Any stage fails its local falsifier; final \(U\not\le10\mathrm{M}\) at quality gate.

---

## Explicit rejects

- **Data pruning / example dropping / token deletion** as a compression lever — out of scope for Lane C.
- Claiming **SSD/Zamba** as weight compression — allowed only as compute-graph hybrid note.
- Claiming any codename **measured** — all `hypothesis` until T-series falsifiers run.

---

## Research agent work plan (peer-loop executable)

File-scoped, start **synthetic tiny** (not 1B). Prove packing / unique math before scale. Point artifacts at `notes/COMPRESSION_CATALOG.md` + this file; log numbers in `notes/BITNET_FACTCHECK.md` as UNKNOWN→PASS/FAIL when measured.

### T0 — Packing math on toy experts (first experiment)

**Scope files:** `scripts/compression_t0_pack.py` + `tests/test_compression_t0_pack.py`; **do not** train 1B.  
**Setup:** Synthetic expert with \(N_{\text{logic}}\in\{10^5,10^6\}\) (scale proxy of 1B→10M is still **100×**). Implement **ALBERT-BitMoE** share+LoRA and **LoRA-Hive** control.  
**Measure:** counted \(U\), packed bytes @1-bit, \(C_{\text{arith}}=N_{\text{logic}}/U\).  
**Pass:** \(C_{\text{arith}}\ge50\) with pack bytes ≈ \(U/8\) (±metadata bound).  
**Fail:** unique count or pack bytes miss target by >2×.  
**Codename focus:** ALBERT-BitMoE (primary), LoRA-Hive (control).

<!-- OVERSEER_COMPRESSION_T0_PACK_2026_09_05 -->

**T0 measured packing (2026-09-05)** — probe `scripts/compression_t0_pack.py`; unittest green. **Quality: N/A** (no train / no loss). Meta header = 16 B; bound ±64 B vs \(U/8\).

| Stack | \(N_L\) | \(U\) | \(S=N_L/U\) | payload (\(U/8\) ceil) | packed bytes | Pass? | Quality |
|-------|--------:|------:|------------:|-----------------------:|-------------:|:-----:|:-------:|
| ALBERT-BitMoE (primary) | 100 000 | 1 200 | 83.33 | 150 | 166 | **PASS** | N/A |
| LoRA-Hive (control) | 100 000 | 1 002 | 99.80 | 126 | 142 | **PASS** | N/A |
| ALBERT-BitMoE (primary) | 1 000 000 | 10 200 | 98.04 | 1 275 | 1 291 | **PASS** | N/A |
| LoRA-Hive (control) | 1 000 000 | 10 002 | 99.98 | 1 251 | 1 267 | **PASS** | N/A |

Geometry (synthetic): ALBERT \(L=L_{\text{share}}=100\), \(B_{\text{body}}=N_L/L\), LoRA \(r=1,d_{\text{in}}=d_{\text{out}}=1\); Hive \(E=100\), \(U_e=B_{\text{hive}}/E+r(d_{\text{in}}+d_{\text{out}})\). All rows \(S\ge50\) and packed ≈ \(U/8\) (+16 B meta). **Hypothesis quality still untested** — packing/unique math only.

### T1 — Share-factor ablation

<!-- OVERSEER_COMPRESSION_T1_SHARE_2026_09_05 -->

**Sweep** \(k\in\{2,4,8,16\}\) on Distill-Fold / ALBERT-BitMoE toy.  
**Pass:** monotonic unique ↓ with \(k\); quality proxy (toy recon or tiny LM loss) documented.  
**Falsifier:** recon/KD quality proxy collapses while chasing \(S\) (distinct from mere **arith short** \(S{<}100\) on a weak \(k\) grid).

**T1 measured (2026-09-05)** — `scripts/compression_t1_share.py`; unittest green.  
\(N_L=10^5\), \(L=16\), \(U=N_L/k+L\cdot r\cdot(d_{\mathrm{in}}+d_{\mathrm{out}})\). **train_unlocked=false**. No data prune.  
**Cliff:** all \(k\le16\) have \(S\ll100\) (max \(S\approx15.9\)) — matches C163; share alone ≠ north star.

| \(k\) | \(U\) | \(S=N_L/U\) | recon MSE (toy) | packed | Cliff before \(S{=}100\)? |
|------:|------:|------------:|----------------:|-------:|:-------------------------:|
| 2 | 50 032 | 1.999 | 7.83e-4 | ✓ | **yes** |
| 4 | 25 032 | 3.995 | 8.13e-4 | ✓ | **yes** |
| 8 | 12 532 | 7.980 | 1.13e-3 | ✓ | **yes** |
| 16 | 6 282 | 15.919 | 1.85e-3 | ✓ | **yes** |

Monotonic \(U\downarrow\) with \(k\): **PASS**. Toy recon MSE rises slowly with \(k\) (capacity fold) — document only; not a train unlock.

### T2 — SVD + LoRA on shared body

**Add** SVD-TieStack init + LoRA polish on T0 winner.  
**Pass:** same \(U\) budget, lower recon/task loss than T0.  
**Falsifier:** SVD+LoRA needs extra unique params beyond 10M-proxy.

### T3 — Teacher→student BitDistill (still tiny→small)

**Teacher:** denser or independent-layer toy. **Student:** best of T0–T2.  
**Dataset:** full toy corpus — **no** example pruning.  
**Pass:** student within ε of teacher on heldout; \(U\) held.  
**Falsifier:** KD gap irreducible without raising \(U\) or pruning data (if only fix is data prune → **stop / redesign**).

<!-- OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05 -->

**T3 measured packing+proxy (2026-09-05)** — probe `scripts/compression_t3_bitdistill.py`; unittest green. Needle `OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05`. Durable Lane-U teacher logit cache needle `OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05` (`--write-bank` / `--read-bank` / `--check-cache`; dump→load KD match; refuse prune / train_unlocked / missing cache_needle). **Quality: proxy** (toy KD MSE on logit bank — not LM). Teacher = independent-layer linear heads; student = SVD-TieStack + LoRA (\(r_{\mathrm{svd}}=2\), \(r_{\mathrm{lora}}=2\)); full corpus \(N=64\), 50% heldout; BitDistill GD vs teacher logit bank; **no data prune**. **TRAIN still LOCKED.**

| Stack | \(U\) | \(U_{\mathrm{teacher}}\) | packed | KD heldout (ε=0.15) | Pass? | Quality |
|-------|------:|-------------------------:|-------:|--------------------:|:-----:|:-------:|
| BitDistill-logit-bank+LoRA | 218 | 256 | 44 | 0.114 (baseline 0.439) | **PASS** | proxy |
| prune_control (¼ corpus cheat) | 218 | 256 | 44 | forbidden path | **FAIL** | proxy |

Pass: heldout KD ≤ ε; \(U\) held at student budget; `data_prune=false`; prune control must not pass. Falsifier (prune-only / raise-\(U\)) **not** tripped. **Logit-cache advance (2026-09-05):** durable dump/load (`OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05`) — KD roundtrip-stable; still no real 1B train. Next: T4 scale rung — still no real 1B train.

### T4 — Scale rung + serve note

**Scale** \(N_{\text{logic}}\) toward \(10^7\!\to\!10^8\) (still below 1B); re-check \(U/N\) ratio.  
**Optional:** Zamba-Ternary-Hive backbone **smoke** (latency/util only — do not credit as weight compression).  
**Pass:** ratio stable ±20%; L5-style residency sketch updated for 1-bit unique sizes.  
**Falsifier:** ratio collapses with scale; or SSD hybrid regresses serve without expert \(U\) benefit.

### T6 — Quality falsifiers (primary vs control toys)

<!-- OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06 -->

**T6 measured proxy (2026-09-06)** — probe `scripts/compression_t6_quality.py`; unittest green. Needle `OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06`. **Quality: proxy** (toy logit KD MSE — not LM). Teacher = independent dense heads per slot; students = shared mean body/hive + per-slot LoRA (\(r{=}2\)); full corpus \(N{=}64\), 50% heldout; **no data prune**. Recipe stack unchanged. **Does not unlock train / raise \(U\).**

| Stack | Role | \(U\) | \(U_{\mathrm{teacher}}\) | packed | KD heldout (ε=0.15) | baseline | Pass? | Quality |
|-------|------|------:|-------------------------:|-------:|--------------------:|---------:|:-----:|:-------:|
| ALBERT-BitMoE | primary | 224 | 256 | 44 | 0.094 | 0.412 | **PASS** | proxy |
| LoRA-Hive | control | 224 | 256 | 44 | 0.094 | 0.412 | **PASS** | proxy |
| prune_control (¼ corpus cheat) | forbidden | 224 | 256 | 44 | forbidden path | — | **FAIL** | proxy |

Toy geometry is isomorphic (slots=8 layers↔experts); both clear ε under shared+LoRA. Falsifier (prune-only / raise-\(U\)) **not** tripped. Proxy ≠ LM quality / 1B delivery.

### Peer execution notes

1. One codename per cycle when possible; mark results `hypothesis→tested` in catalog footnotes (do not upgrade to “measured SOTA”).  
2. Route numeric serve/RAM claims through fact_checker → `BITNET_FACTCHECK.md`.  
3. Cross-link L5 when discussing expert grain vs L2 (~24 MB plan assumption).  
4. Sync any new queue lines to `WORK_QUEUE.md` ↔ `self_improve_context.md` if enqueued for peers.
