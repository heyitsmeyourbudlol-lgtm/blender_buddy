# Smoke — Lane H post-agent verify type=tests (2026-09-07)

**Role:** QA Engineer · **ASN:** asn-1788736852-qa_engin · **cwd:** `.worktrees/peer-15` · **verdict:** PASS

## Strategy (hallucination guard)

```
Evidence:   test-quick first FAIL test_loop_mine_when_pipeline_empty:184 'empty'!='mine'
            + loop_work_items self_sufficient→empty; metrics_green dirty-ok; cache poison; effective wake
Hypothesis: Stale tests vs intentional product behavior (hub tests already aligned)
Falsifier:  ./scripts/peer test-quick → 0 failures after tests-only patch
Verify:     ./scripts/peer test-quick
Defy:       Do not revert product self_sufficient/mine skip or dirty-ok metrics
```

## Plan questions

1. Numbered plan ≥3? **Yes**
2. Evidence read myself? **Yes** — FAIL traceback + `project_automation.loop_work_items` L2731 + hub `tests/test_automation.py`
3. In persona? **Yes** — Lane H ASN assigned minimal fix under `tests/`
4. Root cause? **Stale assertions**, not product regression

## Numbered test plan (executed)

| # | Action | Paths | Expected | Actual |
|---|--------|-------|----------|--------|
| 1 | mine/empty | `test_loop_mine_when_pipeline_empty` | mine if mode=external; empty if self_sufficient | **pass** |
| 2 | metrics dirty-ok | `test_metrics_green` | dirty+tests_ok True; tests fail False | **pass** |
| 3 | cache poison | `test_quick_measure_uses_cache…` | tests_ok=True → cache hit | **pass** |
| 4 | self-check once | `test_quick_measure_runs_self_check…` | one `_run` = quick_test_command | **pass** |
| 5 | wake timeout | `test_continuous_wake_timeout…` | uses `effective_continuous_wake_sec` | **pass** |
| 6 | gate | `./scripts/peer test-quick` | 0 failures | **Ran 69 tests OK EXIT:0** |

## Diff map

- Edited: `tests/test_automation.py` only (5 methods)
- Skipped script edits: product already correct; ASN path `scripts/run_peer_tasks.py` not implicated

## Done questions

1. Same root cause? **Yes** — assertion drift
2. Expected vs actual? **match** — predicted green after tests-only align; got 69 OK
3. Measurable? test-quick failures 5→0; ASN marked done
