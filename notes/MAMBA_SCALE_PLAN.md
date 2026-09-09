# Mamba scale plan — 2.8B+ reranker on DGX Spark

**Goal:** Run a **much larger** Mamba (2.8B or hybrid Nemotron-class) for knowledge rerank without blowing the 100GB agent RAM cap — using **stacked compression**, not a single quant knob.

**Status:** Phase 1 landed 2026-09-08 (budget carve + abstract backends) · Phases 2–7 open

**Needle:** `OVERSEER_TOP10_NEXT_T10_10_2026_09_07`

**Parent:** [KNOWLEDGE_INDEX.md](KNOWLEDGE_INDEX.md) · [DGX_SPEED_PLAN.md](DGX_SPEED_PLAN.md)

---

## Problem

Today the reranker is **mamba-130m fp16 on CPU** with a **1GB sidecar budget**. That was correct for “invisible + safe” but caps retrieval quality. A 2.8B model in fp16 is ~5.6GB weights alone — blocked by design.

**Insight:** Compression is not only “which quant.” We can compress **weights**, **activations**, **work done at query time**, and **where memory lives** (unified GPU RAM vs agent heap).

---

## Target topology

```
┌─────────────────────────────────────────────────────────────────┐
│  DGX Spark — 128GB unified memory                               │
├──────────────────────────────┬──────────────────────────────────┤
│  Agent pool (capped ~100GB)  │  Knowledge brain (~8–16GB carve) │
│  peer-loop · 48 agents       │  FTS + precomputed vectors       │
│  verify · shm caches         │  + large Mamba rerank (NVFP4)    │
└──────────────────────────────┴──────────────────────────────────┘
```

Separate budgets: `ram_max_used_gb` (agents) vs `knowledge_mamba_budget_gb` (brain).

---

## Compression stack (layers)

Use **multiple mechanisms together**. Order matters — cheapest wins first.

| Layer | What it compresses | Mechanism | Typical savings |
|-------|-------------------|-----------|-----------------|
| **L0 — Retrieve less** | Work at query time | FTS5 top-64 → rerank top-8 only | 8× fewer large-model forwards |
| **L1 — Precompute embeddings** | Query-time compute | Index pass writes chunk vectors to disk/shm; query = 1 encode + cosine | **~99%** of 2.8B work moved offline |
| **L2 — Weight format** | Model size on disk/RAM | NVFP4 / GGUF Q4_K_M / Q8_0 / AWQ | 2.8B: ~5.6GB fp16 → **~1.4GB NVFP4** → **~1.7GB Q4** |
| **L3 — Memory mapping** | Resident RAM | mmap GGUF / `low_cpu_mem_usage` + on-demand pages | Pay only for touched weights |
| **L4 — Runtime backend** | Peak memory + speed | llama.cpp (SM121 build) or vLLM Marlin NVFP4 on GB10 | Avoid broken CUTLASS paths on SM121 |
| **L5 — Architecture choice** | State memory | Mamba SSM fixed state vs Transformer KV | 2.8B Mamba rerank ≠ 2.8B transformer chat |
| **L6 — Cascade** | Large model calls | 130m/370m fast score → 2.8b rescore top-16 | Quality of big, cost of small |
| **L7 — Vector quant** | Stored embeddings | int8 / binary quantize precomputed chunk vectors | 4× smaller index RAM |
| **L8 — Distillation** (later) | Model size | Train 370m student on 2.8b teacher labels | Drop big model entirely |

**Recommended default stack for 2.8B:** L0 + L1 + L2 (NVFP4 or Q4) + L4 + separate budget carve-out.

---

## Model candidates (ranked)

| Model | Role | Compressed size | Notes |
|-------|------|-----------------|-------|
| `state-spaces/mamba-2.8b-hf` | Pure SSM rerank | ~1.4GB NVFP4 / ~1.7GB Q4 | Canonical “bigger Mamba” target |
| `state-spaces/mamba-790m-hf` | Mid tier / cascade stage-1 | ~400MB NVFP4 | Good step before 2.8B |
| `nvidia/Nemotron-3-Nano-NVFP4` | Hybrid Mamba-MoE | ~few GB NVFP4 | Spark-native; agent-grade; shared brain |
| `BAAI/bge-small-en-v1.5` | L1 embed-only (non-Mamba) | ~130MB | Cheap precompute; Mamba still reranks |

**Not the same job:** Nemotron is a **generative agent model**; mamba-2.8b here is an **encoder/reranker**. We may run both: Nemotron for agents, 2.8b/embed for retrieval — or converge on Nemotron-NVFP4 for both if embedding API is exposed.

---

## Runtime backends (pluggable)

New module: `scripts/knowledge_mamba_backends.py`

| Backend | `compression` config | When to use |
|---------|---------------------|-------------|
| `transformers-fp16` | Current CPU path | Mac fallback, tiny models |
| `gguf-llamacpp` | `q4_k_m`, `q8_0` | SM121-optimized local server; mmap weights |
| `vllm-nvfp4` | `nvfp4` + Marlin env | Spark GPU; batched encode endpoint |
| `precomputed` | `none` (vectors on disk) | Production default after L1 |
| `cascade` | `130m + 2.8b-nvfp4` | Best quality/latency tradeoff |

Config shape (`knowledge_index.mamba`):

```json
{
  "budget_gb": 12,
  "device": "cuda",
  "backend": "cascade",
  "teacher_model": "state-spaces/mamba-2.8b-hf",
  "teacher_compression": "nvfp4",
  "student_model": "state-spaces/mamba-130m-hf",
  "student_compression": "fp16",
  "precompute_embeddings": true,
  "vector_store": "lance",
  "vector_quant": "int8",
  "rerank_candidate_k": 64,
  "rerank_top_k": 8,
  "llamacpp": {
    "binary": "/usr/local/bin/llama-server",
    "model_gguf": "/data/models/mamba-2.8b.Q4_K_M.gguf",
    "n_gpu_layers": 99
  },
  "vllm": {
    "model": "nvidia/...-NVFP4",
    "marlin": true,
    "gpu_memory_utilization": 0.15
  }
}
```

---

## L1 — Precomputed embeddings (highest ROI)

**Move 2.8B work from every query to index time.**

1. During `knowledge_index.py --index`, after chunking:
   - Run encoder (2.8b NVFP4 or smaller) over each new chunk
   - Store vector in `vectors.lance` or SQLite blob table keyed by `chunk fingerprint`
2. At query time:
   - Encode **query only** (one forward)
   - ANN / brute cosine over precomputed chunk vectors (top 256)
   - Optional: 2.8b **cross-encoder rerank** on top-16 only

**RAM impact:** Model loaded only during index bursts + query encode; corpus vectors live on **2TB disk**, hot subset in `/dev/shm`.

---

## NVFP4 on DGX Spark (GB10 / SM121)

From Spark community findings (Mar 2026):

- Native CUTLASS NVFP4 on SM121 had shared-mem limits; **Marlin backend** works:  
  `VLLM_NVFP4_GEMM_BACKEND=marlin`, `VLLM_USE_FLASHINFER_MOE_FP4=0`
- Cap KV / util for sidecar: `--enforce-eager`, `--gpu-memory-utilization 0.15`
- Hybrid Mamba models (Nemotron) avoid KV blow-up — better for long agent loops if we later unify brains

**Plan:** NVFP4 is **backend #2**, not a rewrite of `transformers` CPU path.

---

## RAM accounting

| Component | Budget | Enforced by |
|-----------|--------|-------------|
| Agent pool | 100GB | `dgx_ram_budget` / guards |
| Knowledge brain | 12GB default (tunable) | `knowledge_mamba_budget_gb` |
| Precomputed vectors (hot) | 2–4GB shm | LRU + int8 quant |
| 2.8b NVFP4 weights resident | ~1.4–2GB | mmap + idle unload |

Total still under 128GB unified with headroom.

---

## Implementation order

### Phase 1 — Budget + backend interface
- [x] Add `knowledge_mamba_budget_gb` (separate from agent 100GB cap)
- [x] `knowledge_mamba_backends.py` — abstract `encode(texts) -> vectors`
- [x] Config: `backend`, `compression`, `teacher_model`, `budget_gb`
- [x] `peer mamba-status` shows backend + compression + budget

### Phase 2 — Precomputed vectors (L1)
- [ ] Vector store alongside SQLite (`lance` or sqlite blobs)
- [ ] Index pass writes embeddings for new/changed chunks
- [ ] Query path: ANN retrieve → optional rerank
- [ ] `vector_quant: int8` option

### Phase 3 — GGUF / llama.cpp path (L2–L4)
- [ ] `scripts/knowledge_mamba_setup.sh` — download + convert mamba-2.8b → Q4_K_M GGUF
- [ ] Build llama.cpp for `CMAKE_CUDA_ARCHITECTURES=121`
- [ ] `llamacpp` backend: embedding endpoint, mmap weights
- [ ] systemd: `knowledge-embed` sidecar (port 8090)

### Phase 4 — NVFP4 / vLLM path (L2–L4)
- [ ] `vllm` backend with Marlin env for SM121
- [ ] Batch encode API for index + query
- [ ] Load test: index 80k chunks without agent RAM spike

### Phase 5 — Cascade (L6)
- [ ] `cascade` backend: 130m/790m fast → 2.8b rescore top-16
- [ ] Tune `hybrid_sparse_weight` vs dense from precompute

### Phase 6 — Optional distillation (L8)
- [ ] Offline: 2.8b teacher scores on corpus sample → train 370m student
- [ ] Swap teacher for student in production

### Phase 7 — Unified brain (optional)
- [ ] Evaluate Nemotron-3-Nano-NVFP4 as shared embed + agent model
- [ ] MCP `knowledge_search` → local embed server

---

## Success metrics

| Metric | Target |
|--------|--------|
| Rerank model | mamba-2.8b-class (or Nemotron hybrid) |
| Brain RAM carve | ≤12GB sustained |
| Agent pool | Still ≤100GB; no peer-loop restarts from brain |
| Query latency | <2s p95 (precompute + small rerank) |
| Index throughput | Full re-embed 80k chunks <30 min |
| Retrieval quality | Beat 130m on held-out “needle” suite |

---

## Commands (future)

```bash
./scripts/peer mamba-setup --model mamba-2.8b --compression nvfp4
./scripts/peer knowledge-index --reembed          # L1 precompute pass
./scripts/peer mamba-status --json                # backend, compression, budget
ssh CLEAN 'systemctl --user status knowledge-embed'
```

---

## What we are NOT doing

- Loading 2.8b fp16 on CPU in `transformers` (slow, RAM-hostile)
- Stealing from the 100GB agent cap without a separate brain budget
- Relying on a single compression knob — stack L0–L7 instead

See task breakdown: [MAMBA_SCALE_TASKS.md](MAMBA_SCALE_TASKS.md)
