# SOP — Lossless memory compression (additive pack)

Owner: Factory Engineer / Tech Writer  
Needle: `OVERSEER_LOSSLESS_MEMORY_COMPRESS_2026_09_07`  
Script: `scripts/peer_memory_compress.py`

## Goal

Maximize **pack density** of repo memory (notes, scripts text, digests, queues, AGENTS) with a **lossless** codec pack so agents can keep Hot memory thin while facts remain reconstructible.

## Safety (non-negotiable)

1. **Additive only** — write under `notes/memory_artifacts/`. Never delete or overwrite live SoT (`notes/`, `scripts/`, dashboard, peer_*, WORK_QUEUE, niches, digests, SOPs).
2. **Expand → staging only** — temp dir or `notes/memory_artifacts/_expand_*`. Never expand onto live root.
3. **Secrets skipped** — `.env`, `cursor-agent.env`, keys/pem, etc. never enter the pack.
4. **Large binaries** — path + sha256 (`hash_ref`); body omitted. Hash-lossless for blobs; byte-lossless for embedded text.
5. **Live code deletion** — out of scope for this SOP. Aggression = pack density, not gutting the factory.

## Protocol

```text
walk repo → skip secrets/caches → content-address blobs (sha256)
  → embed text (≤2MiB) + small binaries (≤256KiB)
  → large/bin weights = hash_ref only
  → JSON ledger → strongest available codec (zstd > xz > brotli > zlib)
  → notes/memory_artifacts/repo_memory_pack.json.z
```

**Lossless claims:**

| Kind | Guarantee |
|------|-----------|
| Embedded text/binary | Expand bytes == live bytes (verify) |
| hash_ref | Recorded sha256 == live file sha256 |
| Dedupe | Identical bodies stored once; all paths restore same bytes |

## Commands

```bash
python3 scripts/peer_memory_compress.py --compress
python3 scripts/peer_memory_compress.py --verify
python3 scripts/peer_memory_compress.py --expand --out /tmp/mem-expand-$$
./scripts/peer memory-compress
```

## Hot memory

Harness injects Always-read paths + optional pack pointer. Agents **open live files**; pack is archive/density — not a license to delete sources.

## Do not

- Replace Hot memory with pack-only and delete notes
- Expand over live tree
- Call hash_ref “full body lossless” — it is sha-lossless only
- Pack secrets
