# Design / UX — compression keep-alive (fanout #19)

**Role:** `design_ux` · **needle:** `OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05` · **2026-09-07**

## Keep-alive `--check` (this cycle)

| Signal | Value |
|--------|-------|
| recipe_locked / train_unlocked | true / true |
| S_arith | 134.09 (≥100) |
| nvfp4_pack_bytes | 37288 |
| agents / floor | 9 / 12 (`agents_ge_floor=false`) |
| wave / Shard invent | false / none |

## Queue pick

- Open compression-family Active: only `[research-speed] Staff CLEAN fanout` — **SRE / Release** already ASN'd; design_ux **did not** hero-spawn.
- Fuel / efficiency rows already `[x]` (CS) — **no reopen**, no Shard-* / T4 invent.

## Persona land (elegant statue — delete chrome)

**Needle:** `dashboard/static/progress.html:19-30` had 10 primary topnav links while `index.html:19-22` already used Progress · Commands · Agents.

**Diff:** Slimmed primary topnav on 11 HTML pages to the landing trio; deep pages keep ≤1 local `is-active` crumb (max 4 links).

**Surfaces:** `progress` · `agents` · `commands` · `horizon` · `asi` · `chat` · `train` · `niches` · `rules` · `flaw-scan` · `factory-proof`

**Expected vs actual:** primary pages ≤3 links, deep ≤4 — verified by reading post-edit HTML; `validate_tasks_config` issues=[].

## Non-scope

- No Newdrop UI polish (TOP10 guardrail).
- No product SUPPORT invent (`product-forge` inactive).
- Staff floor → leave to `sre_release`.
