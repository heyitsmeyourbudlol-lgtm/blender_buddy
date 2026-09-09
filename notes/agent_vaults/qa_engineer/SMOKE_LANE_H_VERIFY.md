# Smoke — Lane H post-agent verify type=tests (2026-09-07)

**Role:** QA Engineer · **ASN:** `asn-1788736852-qa_engin` · **cycle:** Lane H · **verdict:** PASS (after minimal restore)

## Strategy (hallucination guard)

```
Assumption: I will hallucinate unless grounded.
Evidence:   CFG verify_commands=18 vs local=9; missing suite item
            tests.test_self_check_dedup_measure FAIL×2; peer_orchestrate.py:753
            orphan measure; git 82fc8ab regresses 3bfa83b OVERSEER_SELF_CHECK_REUSE
Hypothesis: Restore LiveState-from-plan.live greens dedup module; no second measure
Falsifier:  unittest still FAIL after restore
Verify:     python3 -m unittest tests.test_self_check_dedup_measure -v
Defy:       output-compare + diagnose
```

## Plan questions (answered before edits)

1. Numbered plan ≥3 steps? **Yes** (below).
2. Evidence read myself? **Yes** — FAIL AssertionError + git show 82fc8ab.
3. In persona? **Yes** — ASN assigns first FAIL + minimal fix; smoke + restore.
4. Root cause vs symptom? **Root:** 82fc8ab reintroduced orphan `measure_live_state` before `build_plan`.

## Numbered test plan

| # | Action | Paths | Expected | Verify |
|---|--------|-------|----------|--------|
| 1 | Baseline test-quick / local verify | `./scripts/peer test-quick`; local 9 cmds | OK (gate blind to OVERSEER suite) | exit 0 |
| 2 | Diff CFG vs local verify_commands | `automation.config.json` vs `.local.json` | CFG=18 local=9; 9 missing | python count |
| 3 | Run truncated CFG suite (9) | missing unittest modules | first FAIL = `test_self_check_dedup_measure` | RC=1 |
| 4 | Pinpoint needle | `scripts/peer_orchestrate.py` `_run_self_check_body` | `live = auto.measure_live_state` present; needles absent | rg / inspect |
| 5 | Minimal restore | same file — reuse `plan.live` → `LiveState` | needles + no orphan measure | unittest -v OK |
| 6 | Regression | `test-quick` + all 9 missing + self-check | all OK; ISSUES: none | exit 0 |

## Expected vs actual

### Before fix

| Check | Expected | Actual |
|-------|----------|--------|
| test-quick | OK | **OK** (194) |
| local verify 9 | OK | **OK** |
| CFG-missing #9 `test_self_check_dedup_measure` | FAIL (orphan measure) | **FAIL×2** measure called; source has `live = auto.measure_live_state` |

### After fix

| Check | Expected | Actual |
|-------|----------|--------|
| `tests.test_self_check_dedup_measure -v` | OK | **OK** (2) |
| `./scripts/peer test-quick` | OK | **OK** (194) |
| CFG missing 9 suite | all RC=0 | **all RC=0** |
| `peer_orchestrate --self-check` | ISSUES: none | **ISSUES: none** |

## Acceptance decision

- **Product smoke:** PASS after restore of `OVERSEER_SELF_CHECK_REUSE_PLAN_LIVE_2026_09_04`.
- **Needle:** `scripts/peer_orchestrate.py` `_run_self_check_body` — build_plan owns measure; reconstruct `LiveState` from `plan.live`.
- **Gate blindness (not fixed this cycle — already Active):** `automation.config.local.json` verify_commands 9→18 hides this FAIL from continuous verify. Flaw-research item remains open.

## Done questions

1. Same root cause as Plan? **Yes** — orphan measure regression restored.
2. Expected vs actual match? **Yes** — predicted OK after restore; got OK.
3. Measurable outcome? Truncated CFG suite first FAIL cleared; self-check green.
