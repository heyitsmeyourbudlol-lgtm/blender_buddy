# SOP — Verify deferred soft-skip (swarm/lock)

Owner niche: **Technical Writer** (doc) · gate code: Verify Runner / Factory Engineer  
Companion: `notes/AGENT_SURVIVAL.md` (hazard row) · fact ledger: `notes/DEFERRED_LEAN_RESTAMP_FACTCHECK.md`  
Needle family: `OVERSEER_LAND_DEFERRED_HOT_MEMORY` / lean-verify restamp (KEEP `failure_type=deferred`)

When Hot memory / diagnose shows **verify deferred (swarm/lock)** or `failure_type=deferred`, that is a **soft-skip** — not a verify gate FAIL storm.

## Symptoms (do not escalate as FAIL)

- Last cycle: `Verify: deferred (soft-skip — not a gate FAIL)` (`scripts/peer_transcript.py`)
- `verify_ok=False` **and** `failure_type=deferred` (atomic coerce — deferred never counts green)
- Diagnose: `[low] Verify deferred soft-skip (not FAIL)` → retry next wake
- Factory / digest: deferred must **not** hold primary dispatch when lean-green / soft swarm note

## Contract

| Signal | Meaning | Operator action |
|--------|---------|-----------------|
| `failure_type=deferred` | Swarm/lock soft-skip (`run_peer_tasks` returns failures=-1) | Keep coding; retry `./scripts/peer verify-gate` next wake |
| Hot instruction “soft-skip only” | Do not invent FAIL storm / re-dispatch theater | Do **not** `heal-all` solely for deferred |
| `holds_primary_dispatch` False on deferred note | Deferred must not HOLD / WAITING dispatch | Confirm lean-green=no-HOLD in status if restamped |
| `effective_verify_ok` False under deferred | Soft-skip ≠ green stamp | Never stamp `verify_ok=True` with `failure_type=deferred` (poison) |

Lean restamp (`restamp_lean_green`) **keeps** `failure_type=deferred` — it clears stall/HOLD only. Do not document “clears failure_type” (OVERCLAIM — see fact ledger H3/H4).

## Operator commands (real `./scripts/peer` only)

```bash
./scripts/peer diagnose          # expect low soft-skip finding, not hard FAIL
./scripts/peer poke              # wake blocked loop if quiet
./scripts/peer verify-gate       # retry gate when swarm drains
./scripts/peer verify-gate-quick # cached verify until git changes
./scripts/peer test-quick        # local unittest when you need a hard signal
./scripts/peer green             # check + progress + self-heal-scan
```

Log token (gate path):

```text
local: verify deferred — swarm/lock; not a gate failure
```

## Code anchors

| Path | Role |
|------|------|
| `scripts/run_peer_tasks.py` (~391–393) | deferred → soft skip log; not gate FAIL |
| `scripts/peer_transcript.py` (~1007–1033) | Hot label + soft-skip instruction |
| `scripts/peer_last_cycle_poison.py` `effective_verify_ok` (~65–71) | deferred never counts green |
| `scripts/peer_last_cycle_poison.py` `holds_primary_dispatch` (~199–218) | deferred/swarm note → no HOLD |
| `tests/test_peer_last_cycle_poison.py` `LastCyclePoisonTests.test_deferred_swarm_note_does_not_hold_when_lean_green` | AC |

## Acceptance / verify

```bash
./scripts/peer diagnose   # low soft-skip OK; not a hard block
python3 -m unittest \
  tests.test_peer_last_cycle_poison.LastCyclePoisonTests.test_deferred_swarm_note_does_not_hold_when_lean_green \
  -q
```

Expected: exit 0; `holds_primary_dispatch` False for deferred swarm note.

QA smoke (peer-5): `notes/INTEGRATION_PROOF_VERIFY_DEFERRED_SOFT_SKIP.md`.

## Do not

- Invent CLI verbs (`verify-soft-skip`, `clear-deferred`, etc.).
- Run `heal-all` / invent Active items solely because verify was deferred.
- Treat playbook “heal-all” rows for `intelligence_verify_deferred` as mandatory — soft-skip first; heal only for real bottlenecks.
- Claim lean restamp clears `failure_type=deferred` or stamps a `lean_green` key on last_cycle.
- Mark factory verify as FAIL storm when Hot memory says soft-skip.
