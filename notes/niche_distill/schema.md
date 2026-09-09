# Niche distill exemplar schema

**Needle:** `OVERSEER_NICHE_DISTILL_N01_N03_N08_2026_09_04`

Shared JSON Lines format for ~10M niche specialists. One object per line.

## Record shape

```json
{
  "niche_id": "N01",
  "input": "<string or structured object — see niche>",
  "output": "<string or structured object — see niche>"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `niche_id` | string | yes | Catalog ID from `notes/BITNET_NICHE_BANK.md` train set only |
| `input` | string \| object | yes | Niche-specific; keep short (≤2k chars) |
| `output` | string \| object \| null | yes | Gold label; `null` only where niche allows (e.g. N03 no needle) |

## Niche contracts

### N01 `queue_bullet_parse`

- **input:** one WORK_QUEUE / Remaining-work bullet line (with or without `- [ ]` / `- [x]`).
- **output:** object:
  - `kit` (bool | null) — true if `[kit]` / kit-shaped; false if research/creative/defer/`[compression-train]`/`[research-speed]`/`[comms-improve]`/`[flaw-research]`/`[top10]`/`[factory:…]`; null if ambiguous
   - `scope` (string) — primary path or module (`scripts/peer_loop.py`, `notes/BITNET_NICHE_BANK.md`, `docs/ops/…`, `src/app/…` product paths, `scripts/compression_t4_*`, bare `COMPRESSION_*.md` → `notes/…`, bare `stress_bars.json` → `notes/compression_artifacts/stress_bars.json`; strip `:line` suffixes on `.py`/`.ts`/`.tsx`) or `""` if none
    - Resolve: explicit `paths:` / title / after em-dash **before** `AC:` path soup; prefer `docs/` product paths over later `done=` `notes/INTEGRATION_PROOF_*` / Tasks soup; never gold-scope `INTEGRATION_PROOF`/`EXTERNAL_PROOF`/`FACTORY_PROOF` alone (empty scope); Soft residual bare `STAGING.md` → `docs/ops/STAGING.md`; prefer non-`tests/` over later AC `tests/*.py`; strip `./`; bare `peer_loop:` → `scripts/peer_loop.py`; include `.sh` primaries; bare compression artifact JSON → `notes/compression_artifacts/` (not `notes/<name>` alone)
  - `needle` (string | null) — `OVERSEER_*` land-proof token if present, else null

### N03 `land_proof_needle_match`

- **input:** unchecked or checked item title text (no checkbox required).
- **output:** string | null — exact `OVERSEER_…` needle to expect on disk, or `null` if no land-proof needle is claimable (anti false-`[x]` theater).

### N08 `stall_class_label`

- **input:** object `{ "status": string, "log": string }` — peer-watch / last_cycle / heal snippet.
- **output:** one enum string (stall class):

| Class | Meaning |
|-------|---------|
| `plan_gate_blocked` | plan-gate hard BLOCK / skip primary |
| `verify_fail_agent_exit` | verify_ok=false from cursor-agent non-zero (not necessarily tests red) |
| `verify_fail_tests` | verify_ok=false with real test/verify FAIL evidence |
| `adapt_stale` | should_re_adapt / ADAPT_STALE fingerprint |
| `queue_drift` | WORK_QUEUE ↔ self_improve_context drift (often mislabeled adapt_stale) |
| `peer_quiet` | peer log silent / poke no-op / hung event wait (not UI chrome `log quiet until subprocess` under STATE●WORKING + Cycle rc=0) |
| `namespace_flip` | config_namespace automation ↔ automation-hub; wrong LaunchAgent |
| `oversight_down` | oversight daemon missing / STOPPED |
| `loaded_no_pid` | LaunchAgent loaded but no PID |
| `noop_stall` | noop_backoff / idle theater with open work |
| `deferred_lean_restamp` | failure_type=deferred + lean green needs restamp |
| `last_cycle_poison` | verify_ok=True with failure_type=deferred poison |
| `chicken_egg` | verify_fail ↔ plan-gate skip loop |
| `dirty_tree_notes_only` | notes-only porcelain misread as prove-red |
| `healthy` | no stall — keep dispatching |

## Pass bar

Niche accuracy on held-out JSONL of the same schema. **Not** MMLU / general chat.

## Non-goals

- No catalog mass-train weights here (P0/P1 practice ckpts under `practice_n01/` / `practice_n03/` / `practice_n08/` — see RECIPE.md).
- No GB10 / hardware numeric invention.
- Train set stays **11** niches; do not expand distill beyond queued IDs.
