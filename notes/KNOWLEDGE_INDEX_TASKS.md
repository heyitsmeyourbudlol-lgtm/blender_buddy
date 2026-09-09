# Knowledge index tasks

Linked plan: [KNOWLEDGE_INDEX.md](KNOWLEDGE_INDEX.md)

## Phase 1 — Core (done)

- [x] FTS5 + hybrid dense/Mamba rerank indexer
- [x] 2TB storage cap (`max_storage_gb: 2048`)
- [x] Prompt injection in `peer_transcript.build_next_input`
- [x] DGX `knowledge-indexer` systemd service

## Phase 2 — Corpus seeding

- [ ] Create `/data/knowledge-corpus` on DGX (2TB mount)
- [ ] Ingest Python 3.12 stdlib + typing docs
- [ ] Ingest pytest, unittest, requests, pydantic reference docs
- [ ] Ingest Automation kit notes + AUTOMATION.md + PEER_ORCHESTRATION.md
- [ ] Mirror synced repos into indexer (`extra_index_roots`)

## Phase 3 — Comms + memory

- [ ] GLink bus archive → vault SUM → indexer ingest
- [ ] Auto-refresh `notes/PEER_CONVERSATION.md` from indexer summary
- [ ] Similar past-cycle retrieval for verify failures

## Phase 4 — Tooling

- [ ] MCP `knowledge_search(query, repo?, top_k)` bridge
- [ ] Dashboard panel: chunk count, storage GB, last index pass
