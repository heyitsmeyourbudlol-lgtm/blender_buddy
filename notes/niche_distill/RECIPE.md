# N01 P0 practice recipe — distill → eval → serve

**Needle:** `OVERSEER_NICHE_P0_PRACTICE_N01_2026_09_04`

**Catalog:** [`../BITNET_NICHE_BANK.md`](../BITNET_NICHE_BANK.md) · **Niche:** N01 `queue_bullet_parse` · **Grain:** ~10M (neural swap keeps this layout)

Cloneable practice loop for one niche. **Do not** mass-train the catalog before this recipe is green.

## Layout (stamp as-is)

| Path | Role |
|------|------|
| `N01_queue_bullet_parse.jsonl` | Full synthetic distill traces |
| `N01_queue_bullet_parse_heldout.jsonl` | ~20% heldout (deterministic stride) |
| `schema.md` | Record contract |
| `RECIPE.md` | This file |
| `practice_n01/checkpoint.json` | Practice **checkpoint** manifest |
| `practice_n01/weights/n01_queue_bullet_parse_practice.pt` | Practice **weights** (`.pt`) |
| `scripts/niche_n01_practice.py` | Distill / eval / serve runner |
| `practice_n02/` + `scripts/niche_n02_practice.py` | Stamp — N02 `queue_kit_vs_research` (no corpus prune) |
| `practice_n03/` + `scripts/niche_n03_practice.py` | P1 stamp — N03 `land_proof_needle_match` |
| `practice_n07/` + `scripts/niche_n07_practice.py` | Stamp — N07 `hallucination_block_fill` (no corpus prune) |
| `practice_n08/` + `scripts/niche_n08_practice.py` | P1 stamp — N08 `stall_class_label` |

## Distill

1. Freeze `schema.md` — N01 output = `{kit?, scope, needle}`.
2. Train on JSONL only (one niche_id per model).
3. Heldout = every 5th row (~20%); written by the runner (no RNG).
4. Pass bar = **niche accuracy** ≥ 0.90 on heldout (exact match). Not MMLU.

```bash
python3 scripts/niche_n01_practice.py          # rewrite heldout + checkpoint + weights
python3 scripts/niche_n01_practice.py --eval-only
```

## Practice checkpoint (landed)

- **checkpoint:** `notes/niche_distill/practice_n01/checkpoint.json`
- **weights / ckpt:** `notes/niche_distill/practice_n01/weights/n01_queue_bullet_parse_practice.pt`

Baseline is a deterministic rule `predict` packed into `.pt` (torch-free serve). Neural ~10M replaces the blob only — keep paths + eval + serve CLI identical.

## Eval

```text
for each heldout line:
  pred = niche_model(input)
  score += exact_match(pred, gold.output)
report accuracy; ship only if ≥ 0.90
```

Live sample (optional stress): parse current `notes/WORK_QUEUE.md` Active opens via `--serve`.

## Serve

```bash
python3 scripts/niche_n01_practice.py --serve '- [ ] **[kit] peer_loop: … Needle: `OVERSEER_X_2026_09_04`.'
# → {"kit": true, "scope": "scripts/peer_loop.py", "needle": "OVERSEER_X_2026_09_04"}
```

Composer later merges niche JSON; do not invent hardware numbers.

## Replicate (P1 — landed)

Same recipe → N03 → N08 (schemas already landed). Needle: `OVERSEER_NICHE_P1_N03_N08_2026_09_06`

```text
notes/niche_distill/practice_n03/
  checkpoint.json
  weights/n03_land_proof_needle_match_practice.pt
notes/niche_distill/practice_n08/
  checkpoint.json
  weights/n08_stall_class_label_practice.pt
```

```bash
python3 scripts/niche_n03_practice.py          # rewrite heldout + checkpoint + weights
python3 scripts/niche_n03_practice.py --eval-only
python3 scripts/niche_n08_practice.py
python3 scripts/niche_n08_practice.py --eval-only
```

Heldout bar ≥ 0.90 each. Stress remains → `STRESS_GAPS.md` P1 section.

## Replicate (N02 — landed)

Needle: `OVERSEER_NICHE_PRACTICE_N02_2026_09_07` — uses **existing** heldout JSONL (no corpus prune/rewrite). Explicit cue rule only (as/label=/→/[X]/Factory X); legends must not steal labels.

```bash
python3 scripts/niche_n02_practice.py          # eval heldout + write rule ckpt/weights
python3 scripts/niche_n02_practice.py --eval-only
```

## Replicate (N07 — landed)

Needle: `OVERSEER_NICHE_PRACTICE_N07_2026_09_07` — uses **existing** heldout JSONL (no corpus prune/rewrite).

```bash
python3 scripts/niche_n07_practice.py          # eval heldout + write rule ckpt/weights
python3 scripts/niche_n07_practice.py --eval-only
```

## Anti-theater

- No catalog mass-train from this recipe.
- False `[x]` without this needle + real checkpoint/weights path must not close the queue item (`_niche_p0_practice_landed`).
- GDS / nvidia-fs / brochure tok/s claims stay out of exemplars.
