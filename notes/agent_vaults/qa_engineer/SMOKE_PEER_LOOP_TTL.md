# Smoke — peer_loop inventory + prepare_prompts TTL (2026-09-06)

**Role:** QA Engineer · **cycle:** ah=493edb07 · **verdict:** FAIL (bugs confirmed; not fixed this cycle)

## Strategy (hallucination guard)

```
Assumption: I will hallucinate unless grounded.
Evidence:   scripts/peer_loop.py:_emit_worktree_inventory still calls list_worktrees after ensure-TTL;
            automation_improve has _write_prompts_cache_fresh only (no write_prompts_age_fresh)
Hypothesis: Active flaw-research items still open — wire/API gap, not flake
Falsifier:  tests.test_emit_inventory_ttl_list_skip + tests.test_prepare_prompts_ttl all green
            AND both modules listed in automation.config.json verify_commands
Verify:     python3 -m unittest tests.test_emit_inventory_ttl_list_skip tests.test_prepare_prompts_ttl -v
Defy:       memory-recall + output-compare + diagnose
```

## Plan questions (answered before edits)

1. Numbered plan ≥3 steps? **Yes** (below).
2. Evidence read myself? **Yes** — peer_loop emit body + unittest FAIL/ERROR + REPO_FLAW_RESEARCH L55–56.
3. In persona? **Yes** — acceptance smoke; no production fix.
4. Root cause vs symptom? **Root:** peer_loop not using inventory_snapshot; public age-fresh API missing.

## Numbered test plan

| # | Action | Paths | Expected | Verify |
|---|--------|-------|----------|--------|
| 1 | Source pin emit path | `scripts/peer_loop.py` `_emit_worktree_inventory` | No `inventory_snapshot` call; TTL skip still porcelain-lists | `rg inventory_snapshot scripts/peer_loop.py` → none |
| 2 | Source pin prepare path | `scripts/peer_loop.py` `_prepare_continuous_prompts`; `scripts/automation_improve.py` | Always gather/write; no `write_prompts_age_fresh` | AttributeError on attr |
| 3 | Unittest emit TTL | `tests/test_emit_inventory_ttl_list_skip.py` | FAIL: `list_worktrees` called 1×; missing "porcelain list deferred" | unittest -v |
| 4 | Unittest prepare TTL | `tests/test_prepare_prompts_ttl.py` | ERROR×4: missing `write_prompts_age_fresh` | unittest -v |
| 5 | Snapshot helper sanity | `tests/test_inventory_snapshot_ttl_list_skip.py` | PASS (helper already lands porcelain defer) | unittest -v |
| 6 | Gate coverage | `automation.config.json` `verify_commands` | Neither emit nor prepare TTL modules listed | rg verify_commands |
| 7 | Record checklist + assign | this file; GLink ASN | Bugs stay Active; assign backend | `./scripts/peer assign` |

## Expected vs actual (executed)

### Step 1–2 source

| Expected | Actual |
|----------|--------|
| `inventory_snapshot` absent from peer_loop | **match** — `inventory_snapshot call in peer_loop: False` |
| `write_prompts_age_fresh` absent | **match** — AttributeError; hint `_write_prompts_cache_fresh` |

### Step 3–5 unittest (exit 1)

| Module | Expected | Actual |
|--------|----------|--------|
| `test_emit…ttl_skip_does_not_call_list_worktrees` | FAIL (list still called) | **FAIL** `AssertionError: Expected 'list_worktrees' to not have been called. Called 1 times.` |
| `test_emit…cold_ensure_still_lists` | ok | **ok** |
| `test_prepare_prompts_ttl` (4 tests) | ERROR AttributeError | **ERROR×4** no `write_prompts_age_fresh` |
| `test_inventory_snapshot_ttl_list_skip` (2) | ok | **ok** |

Command: `python3 -m unittest tests.test_emit_inventory_ttl_list_skip tests.test_prepare_prompts_ttl tests.test_inventory_snapshot_ttl_list_skip -v` → **FAILED (failures=1, errors=4)**

### Step 6 verify_commands

| Expected | Actual |
|----------|--------|
| emit + prepare TTL modules **not** in gate | **match** — lean list ends at `test_adapt_verify_protect`; gate stays green while continuous path still pays porcelain + gather |

## Acceptance decision

- **Product smoke:** FAIL — Active items correctly open.
- **QA action:** do not land fix (persona); bugs already in `notes/WORK_QUEUE.md` Active; assign implementer.
- **Needle for fixer:**
  1. `peer_loop._emit_worktree_inventory` → `peer_worktree.inventory_snapshot(ensure_pool=True)` / early-return deferred log `"porcelain list deferred"`.
  2. Land `automation_improve.write_prompts_age_fresh` (+ `write_prompts_fp_age_sec`); TTL-skip gather in `_prepare_continuous_prompts` with `"gather deferred"`.
  3. Add `tests.test_emit_inventory_ttl_list_skip` + `tests.test_prepare_prompts_ttl` to `verify_commands`.

## Journal note (secondary)

Hot pin: `peer_orchestrate._select_dispatch_items` still **missing** (`hasattr` False). Separate ASN already on factory/verify_runner — not this cycle's Active pair.

## Done questions

1. Same root cause as Plan? **Yes** — wiring/API gap confirmed by FAIL/ERROR.
2. Expected vs actual match Plan? **Yes** — predicted FAIL/ERROR; got FAIL=1 ERROR=4.
3. Measurable outcome? Smoke artifact + ASN; queue items remain open (correct).
