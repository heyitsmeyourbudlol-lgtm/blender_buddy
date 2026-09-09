# Mamba scale tasks

Linked plan: [MAMBA_SCALE_PLAN.md](MAMBA_SCALE_PLAN.md)

## Phase 1 — Budget + backend interface
- [x] Add `knowledge_mamba_budget_gb` separate from `ram_max_used_gb`
- [x] `scripts/knowledge_mamba_backends.py` — pluggable `encode()` backends
- [x] Config keys: `backend`, `compression`, `teacher_model`, `budget_gb`
- [x] Extend `peer mamba-status` with backend/compression/budget

_Landed 2026-09-08 · T10-10 · needle `OVERSEER_TOP10_NEXT_T10_10_2026_09_07`_

## Phase 2 — Precomputed embeddings (L1)
- [ ] Vector store for chunk embeddings (lance or sqlite blobs)
- [ ] Index pass embeds new/changed chunks offline
- [ ] Query: encode query once + ANN over stored vectors
- [ ] Optional `vector_quant: int8`

## Phase 3 — GGUF / llama.cpp (L2–L4)
- [ ] Convert mamba-2.8b → Q4_K_M GGUF; SM121 llama.cpp build
- [ ] `llamacpp` backend + `knowledge-embed` systemd sidecar
- [ ] mmap weights; idle unload

## Phase 4 — NVFP4 / vLLM (L2–L4)
- [ ] vLLM backend with Marlin env for GB10/SM121
- [ ] Batch encode for index + query; `gpu_memory_utilization: 0.15`
- [ ] Verify no agent RAM guard trips during embed burst

## Phase 5 — Cascade rerank (L6)
- [ ] 130m/790m fast filter → 2.8b rescore top-16
- [ ] Tune hybrid sparse/dense weights with precompute

## Phase 6 — Distillation (L8, optional)
- [ ] Teacher 2.8b labels on corpus sample → 370m student
- [ ] A/B needle suite vs full 2.8b

## Phase 7 — Unified brain (optional)
- [ ] Evaluate Nemotron-3-Nano-NVFP4 as shared embed + agent path
- [ ] MCP `knowledge_search` → local embed server
