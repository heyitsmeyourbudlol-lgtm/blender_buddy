# deferred_lean_restamp heal-dispatch — fact-check ledger

**Owner niche:** `fact_checker`  
**Assignment:** `[kit] peer_self_heal: bottleneck deferred_lean_restamp maps to _heal_deferred_lean_restamp in heal dispatch table`  
**Anchors:** hub `scripts/peer_self_heal.py` (`_HEALERS`, `_heal_deferred_lean_restamp`); hub `scripts/peer_last_cycle_poison.py` (`restamp_lean_green`)  
**Checked:** 2026-09-04 · role `fact_checker` · peer-5 (hub SoT; peer-5 tree lacks `peer_self_heal.py`)

## Hallucination strategy (this cycle)

```
Assumption: I invent missing mapping, or that restamp_lean_green clears failure_type / stamps lean_green= on last_cycle.
Evidence:   hub peer_self_heal.py:2362 _HEALERS; live probe PASS_MAP True; poison:163 never pops ft; restamp keys={failure_type,note,verify_ok}
Hypothesis: H1 PASS (map live); H2/H3 FAIL OVERCLAIM; Active twin steward-closed but land_proof was False → reopen risk until needles land
Falsifier:  _HEALERS['deferred_lean_restamp'] is not _heal_deferred_lean_restamp; restamp pops failure_type under lean_green
Verify:     python probe; _land_proof_present(True); unittest Rules§9 subset
Defy:       memory-recall + output-compare + diagnose if unsure
```

## Plan gate (answered)

1. **Problem:** Kit Active reopened “maps to _heal_…” and “clears failure_type… writes lean_green=True” after Stall-watch already landed KEEP-ft contract.
2. **Smallest change:** One ledger (H1–H4) + land_proof needles so seed cannot reopen inverted/stale twins; no healer rewrites.
3. **Falsifier:** Mapping absent from `_HEALERS`; restamp clears `failure_type`.

### Plan self-check (before edit)

1. Numbered plan ≥3 with paths+verify? **Yes**
2. Evidence read this cycle? **Yes** — hub heal dispatch + poison restamp + land_proof probe
3. Persona scope? **Yes** — fact_checker ledger + land_proof close only
4. Root vs symptom? **Root** — claim twins lacked land_proof; steward refuse alone does not block seed
5. Other niche on path? Queue steward already `[x]`; Fact Checker owns claim truth + land_proof
6. Smallest change? Ledger + needles; reject re-implementing healers
7. Falsifier checked? PASS_MAP True; restamp keeps ft=deferred; no lean_green key
8. Pre-mortem: fails if H1 marked FAIL while `_HEALERS` maps, or H2 PASS as “clears”
9. Expected verify: land_proof True on both claim strings; unittest OK
10. Hallucination signal: confident “clears failure_type” from queue wording

### Numbered execute plan (≥3)

1. **Write** this ledger · path `notes/DEFERRED_LEAN_RESTAMP_FACTCHECK.md` · verify `rg '^\| H[1-4] ' … | wc -l` → 4
2. **Add** land_proof needles · path hub `scripts/project_automation.py` · expect mapping + clears/lean_green twins → True
3. **Annotate** hub WORK_QUEUE ↔ self_improve closed lines with fact_checker land-proof · verify sync
4. **Verify + DONE** · unittest Rules§9; done-gate; GLink DONE

## Master ledger

| ID | Claim | Verdict | Source | Evidence (one line) | Checked by |
|----|-------|---------|--------|---------------------|------------|
| H1 | Bottleneck id `deferred_lean_restamp` maps to `_heal_deferred_lean_restamp` in heal dispatch table | **PASS** | hub `scripts/peer_self_heal.py:2362` (`_HEALERS`); live `PASS_MAP True` | `_HEALERS["deferred_lean_restamp"] is _heal_deferred_lean_restamp` → True; botttleneck emit `:1547`. | fact_checker 2026-09-04 |
| H2 | Scan emits bottleneck `deferred_lean_restamp` when deferred+lean needs restamp | **PASS** | hub `scripts/peer_self_heal.py:1542-1554` (`_needs_deferred_lean_restamp`) | `Bottleneck(id="deferred_lean_restamp", … auto_healable=True)` under `_needs_deferred_lean_restamp`. | fact_checker 2026-09-04 |
| H3 | `restamp_lean_green` **clears** `failure_type=deferred` | **FAIL** + **OVERCLAIM** | hub `scripts/peer_last_cycle_poison.py:163,181-182`; heal `OVERSEER_DEFERRED_LEAN_KEEP_FT_2026_09_04` | Doc+code: **never pops** `failure_type=deferred`; sets/keeps it. Clears stall/HOLD only. | fact_checker 2026-09-04 |
| H4 | `restamp_lean_green` **writes** `lean_green=True` onto last_cycle | **FAIL** + **OVERCLAIM** | hub `scripts/peer_last_cycle_poison.py:155-187`; live restamp keys | `lean_green` is a **parameter**, not a stamped key; keys=`failure_type,note,verify_ok` only. | fact_checker 2026-09-04 |

### Strike / split text (FAIL / OVERCLAIM)

| ID | Action |
|----|--------|
| **H3** | **Strike** “clears failure_type=deferred”. Prefer: “KEEP `failure_type=deferred` after lean-green; clear stall/HOLD only (`OVERSEER_DEFERRED_LEAN_KEEP_FT_2026_09_04`).” |
| **H4** | **Strike** “writes lean_green=True” as a last_cycle field. Prefer: “call with `lean_green=True`; annotate note; do not stamp `lean_green` key.” |
| **H1** | Already true on hub; Active reopen was stale — close with land_proof `OVERSEER_LEAN_VERIFY_RESTAMP_SELF_HEAL_2026_09_04` (not re-implement). |

## Live probe excerpt (this cycle)

```
PASS_MAP True
name _heal_deferred_lean_restamp
keys ['failure_type', 'note', 'verify_ok']
ft deferred
lean_green_in False
verify_ok False
```

## Done self-check

1. Evidence paths read this cycle? Yes — hub heal + poison + land_proof.
2. Expected vs actual: H1/H2 PASS; H3/H4 FAIL OVERCLAIM; `_land_proof_present` True on both claim strings (needles already live via `OVERSEER_DEFERRED_LEAN_HEAL_DISPATCH_2026_09_04` / `OVERSEER_RESTAMP_LEAN_GREEN_KEEP_FT_2026_09_04`).
3. Did not invent URLs; kit claims grounded in file:line + live probe.
4. Did not orchestrate other niches; ledger + queue annotate only (overseer/steward already `[x]` Active + needles).
