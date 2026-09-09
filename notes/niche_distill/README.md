# Niche distill — schemas + synthetic traces

**Needle:** `OVERSEER_NICHE_DISTILL_N01_N03_N08_2026_09_04`

Catalog: [`../BITNET_NICHE_BANK.md`](../BITNET_NICHE_BANK.md) · Grain: **~10M params each** · Pass bar: **niche accuracy only** (not MMLU).

This directory lands **schemas + synthetic I/O traces** for the first three top-20% niches.

**P0 practice (N01):** cloneable distill/eval/serve — see [`RECIPE.md`](RECIPE.md) + `practice_n01/` checkpoint + `weights/*.pt` (`OVERSEER_NICHE_P0_PRACTICE_N01_2026_09_04`). Catalog mass-train stays deferred.

**P1 replicate (N03 + N08):** same recipe under `practice_n03/` + `practice_n08/` (`OVERSEER_NICHE_P1_N03_N08_2026_09_06`); runners `scripts/niche_n03_practice.py` / `niche_n08_practice.py`. Remaining stress → [`STRESS_GAPS.md`](STRESS_GAPS.md) P1.

**Research stress (after P0):** live Active/Backlog + heldout miss classes → [`STRESS_GAPS.md`](STRESS_GAPS.md) (G1–G7 fixed through 2026-09-06; G6 factory lane kit=false; G7 bare `stress_bars.json` → `notes/compression_artifacts/`).

## First wave (this land)

| File | Niche | In → Out |
|------|-------|----------|
| `N01_queue_bullet_parse.jsonl` | `queue_bullet_parse` | WORK_QUEUE line → `{kit?, scope, needle}` |
| `N03_land_proof_needle_match.jsonl` | `land_proof_needle_match` | item text → OVERSEER needle \| null |
| `N08_stall_class_label.jsonl` | `stall_class_label` | status+log → stall class enum |

Shared record shape: [`schema.md`](schema.md) — every line is `{ "niche_id", "input", "output" }`.

## How to distill (~10M)

1. **Freeze schema** — treat `schema.md` as the contract; do not widen fields mid-run.
2. **Train on JSONL only** — supervised I/O for one niche_id per model; no multi-task mix with chat corpora.
3. **Hold out ~20%** of each JSONL (or mint a sibling `*_heldout.jsonl`) for niche eval.
4. **Pass bar** = niche accuracy (exact match on structured output / enum / needle string). Ignore general benchmarks.
5. **Serve later** via hot committee ≤20GB; composer merges niche JSON — see bank open work for prefer-order wire.
6. **Do not** invent GB10/hardware numbers; route numeric claims through Fact Checker + ledger.
7. **Do not** expand beyond the bank train set (N=11). Next distill after this wave: N04 → N02 → N05.

## Eval recipe (conceptual)

```text
for each heldout line:
  pred = niche_model(input)
  score += exact_match(pred, gold.output)   # niche accuracy
report accuracy; ship only if ≥ niche bar (team-set; start ≥0.90 on synthetic)
```

## Anti-theater

N03 exists so false `[x]` without a live OVERSEER needle fails. Distill traces teach **null** when no needle is claimable.

## Non-goals

- Training / exporting weights in-repo
- Expanding deferred niches (N06+)
- Hardware RSS / tok/s claims in exemplars
