# Expected vs actual — output discrepancy check

_Updated 2026-09-08 16:16:24_ · every agent · compare before DONE

**Expected vs actual** — mandatory discrepancy check (every cycle):

Before you declare success, **write both columns** and diff them. Do not skip because you "feel" it worked.

| Step | Rule |
|------|------|
| **Expect** | Before verify/command: state `{exit, key lines, metric}` you expect. |
| **Run** | Execute the narrowest command/test; capture **full** exit code + stderr/stdout tail. |
| **Compare** | Side-by-side: Expected | Actual — line-by-line for failures. |
| **Discrepancy** | Any mismatch → root-cause before more edits; post GLink BLOCK if unexplained. |
| **DONE** | GLink payload includes `expected_vs_actual: match | discrepancy + summary`. |

**Compare workflow (after every verify / test / script):**

```
1. Write expected (1–3 lines): exit code + substring or metric
2. Run command → capture actual exit + last 20 lines output
3. ./scripts/peer output-compare --compare --expected "..." --actual "..."
4. If discrepancy → read first diff hunk → pinpoint → fix → re-compare
5. Only DONE when compare reports MATCH (or discrepancy explained + filed)
```

## Compare questions

1. What **exact** output do I expect (exit code + key lines or metric) after my change?
2. Did I run the command and capture **actual** output myself — not assume from memory?
3. Expected vs actual side-by-side — what lines differ? (paste or `./scripts/peer output-compare`)
4. If discrepancy exists: is it env/flake, wrong fix, or wrong expectation — which one?
5. Before DONE: does actual output match what I promised in Plan — yes or no with evidence?

## Niche compare focus

### Adapt Specialist
- Expected: audit clean or listed findings — compare `--audit` output to expectation.

### Command Builder
- Expected: compound exit 0 — compare `./scripts/peer commands-sync` output.

### Communications Engineer
- Expected: byte/token count — compare measure before vs after on hot path.

### Compression Engineer
- Expected: RSS MB delta — compare ram-status snapshot before vs after.

### Factory Engineer
- Expected: self-check + targeted test green — compare dispatch metric before/after.

### Orchestrator
- Expected: N peers DONE + verify green — compare GLink bus vs plan task list.

### Queue Steward
- Expected: drift=0 between WORK_QUEUE and self_improve_context — diff the pair.

### Safety Auditor
- Expected: PASS or BLOCK with gate ids — actual review must match stated tier.

### Verify Runner
- Expected: verify exit 0 + self-check OK — actual: paste first failing line if not.
- Compare unittest summary line expected vs actual (Ran N tests / FAILED).
