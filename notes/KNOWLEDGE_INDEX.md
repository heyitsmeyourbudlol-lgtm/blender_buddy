# Knowledge index — Mamba hybrid + 2TB corpus

**Goal:** Give every peer agent needle-in-haystack recall across transcripts, notes, debriefs, GLink, registry repos, and a dedicated library corpus — without re-reading whole files each cycle.

**Status:** Active (2026-09-01)

---

## Architecture

| Layer | Role | Storage |
|-------|------|---------|
| **FTS5 (sparse)** | Exact token / phrase recall | SQLite on `/data/knowledge-index` |
| **Dense hybrid** | Semantic similarity | Hash embed fallback; Mamba/Transformer mean-pool when model loaded |
| **Mamba rerank** | Re-order top candidates | `KNOWLEDGE_MAMBA_MODEL` on DGX |
| **Hot cache** | Repeat query hits | `/dev/shm/automation-cache/knowledge` (90s TTL) |
| **Corpus budget** | Cap growth | `max_storage_gb: 2048` |

Agents receive a `## Retrieved knowledge` block from `peer_transcript.build_next_input()` before orchestration.

---

## What gets indexed

- Cursor agent transcripts (all workspaces when `watch_all_cursor_transcripts`)
- `notes/`, `scripts/`, debrief wiki, GLink bus
- Work queue + self-improve context + PEER_CONVERSATION
- Registry repos (CPT, CaaS, RAM, Doc2Api, …)
- **`/data/knowledge-corpus`** — drop Python/stdlib/framework docs here (2TB target)

---

## Commands

```bash
./scripts/peer knowledge-index --index          # one pass
./scripts/peer knowledge-index --status
./scripts/peer knowledge-search "peer orchestrate drift cache"
./scripts/peer knowledge-index --ingest /data/knowledge-corpus/pytorch
ssh CLEAN 'python3 ~/Automation/scripts/knowledge_index.py --forever'  # daemon
```

---

## Mamba cascade — 130m → 790m → 2.8b (brain carve)

**Mode:** `mamba_mode: cascade` — student-teacher chain, **one model in RAM at a time**.

| Tier | Model | Compression | Top-K |
|------|-------|-------------|-------|
| Student | mamba-130m | fp16 (~260MB) | 48 |
| Teacher 1 | mamba-790m | fp16 (~1.6GB) | 16 |
| Teacher 2 | mamba-2.8b | **4bit** (~1.4GB) | 8 |

**Brain carve:** `knowledge_mamba_budget_gb` (default **12**) — separate from agent `ram_max_used_gb`. Per-load ceiling `mamba_max_ram_mb` is capped by the carve. Backends: `scripts/knowledge_mamba_backends.py` (`transformers-fp16` / `cascade` live; gguf/vllm/precomputed stubs).

```bash
./scripts/peer mamba-status
# requires bitsandbytes for teacher_2 4bit:
pip install bitsandbytes
```

Teacher 2 uses 4-bit (`bitsandbytes`) so 2.8B fits in the load cap. Without it, cascade stops after 790m.

Scale-up path: [MAMBA_SCALE_PLAN.md](MAMBA_SCALE_PLAN.md) · needle `OVERSEER_TOP10_NEXT_T10_10_2026_09_07`

---

## Implementation order

1. [x] `knowledge_index.py` — FTS5 + hybrid rerank + 2TB cap
2. [x] Inject retrieval in `peer_transcript.build_next_input`
3. [x] DGX `knowledge-indexer` systemd daemon
4. [ ] Seed `/data/knowledge-corpus` with library docs (Python, numpy, pytest, Cursor SDK, …)
5. [ ] GLink bus archive → vault SUM → indexer ingest
6. [ ] MCP `knowledge_search` tool for interactive agents

See [KNOWLEDGE_INDEX_TASKS.md](KNOWLEDGE_INDEX_TASKS.md).
