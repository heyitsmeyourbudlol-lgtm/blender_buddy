# Peer work assignment — ETA + deadline

_Updated 2026-09-08 16:16:24_ · assign across niches · respect cursor-agent timeout

**Peer work assignment** — delegate across niches to ship faster:

Agents may **assign each other** scoped work when parallel product speed beats solo hero work.
Every assignment must include **ETA + deadline check** against the **cursor-agent session limit**.

| Field | Meaning |
|-------|---------|
| **task** | Executable scope (file paths + outcome) |
| **eta_sec** | Estimated seconds for assignee to finish |
| **due** | Hard deadline (ISO) — min(your target, cursor-agent timeout) |
| **when** | `now` = take this cycle · `later` = next slot before due · `miss` = escalate BLOCK |
| **slack_sec** | due − (now + eta) — negative means won't meet deadline |

**Assign workflow:**

```
1. Estimate: ./scripts/peer eta --task "..." --role verify_runner [--deadline ISO]
2. If when=now|later → assign: ./scripts/peer assign --from YOU --to ROLE --task "..."
3. Assignee reads vault todo + GLink ASN; posts ACK then DONE
4. If when=miss → split scope, reassign, or post GLink BLOCK — do not pretend on-time
```

## Session limit

- cursor-agent timeout: **120** minutes

## Open assignments

- **asn-1788802752-top10_im** queue_steward→top10_implementer when=now eta=20m · T10-04: prove ≥8 non-noop/day on PRODUCTION_POWER_SCOREBOARD + keep Ac
- **asn-1788803215-sre_rele** customer_success→sre_release when=now eta=17m · Staff CLEAN fanout — agents=5 floor=12 (keep_alive --check agents_ge_f
- **asn-1788805759-sre_rele** customer_success→sre_release when=now eta=19m · Staff CLEAN fanout — agents=7 floor=12 agents_ge_floor=false; respawn 
- **asn-1788805789-sre_rele** customer_success→sre_release when=now eta=17m · Staff CLEAN fanout — agents=8 floor=12 (compression_keep_alive --check
- **asn-1788806173-sre_rele** customer_success→sre_release when=now eta=17m · Staff CLEAN fanout: agents=9 floor=12 agents_ge_floor=false — respawn 
- **asn-1788806850-sre_rele** customer_success→sre_release when=now eta=17m · Staff CLEAN fanout: live agents=7 < floor=12 (keep_alive --check agent
- **asn-1788806864-sre_rele** customer_success→sre_release when=now eta=17m · Staff CLEAN fanout — respawn if agents < floor (live agents=7 floor=12
- **asn-1788807409-sre_rele** customer_success→sre_release when=now eta=19m · Staff CLEAN fanout — restore agents>=floor=12 (live keep_alive --check
- **asn-1788807964-sre_rele** customer_success→sre_release when=now eta=19m · Staff CLEAN fanout#21 — respawn live agents to floor (remasure 7<12 ag
- **asn-1788809373-factory_** output_researcher→factory_engineer when=now eta=32m · [factory:verify_memory] Phase 2 — inject last_cycle deferred/failure_t
- **asn-1788810570-sre_rele** finance_billing→sre_release when=now eta=17m · Staff CLEAN: agents=7 floor=12 agents_ge_floor=false — remasure-affirm
- **asn-1788812816-sre_rele** qa_engineer→sre_release when=now eta=17m · Staff CLEAN: keep_alive --check agents=7 floor=12 agents_ge_floor=fals
- **asn-1788812816-sre_rele** qa_engineer→sre_release_engineer when=now eta=17m · Staff CLEAN: respawn agents so compression-keep-alive agents_ge_floor=
- **asn-1788813100-sre_rele** qa_engineer→sre_release when=now eta=17m · Staff CLEAN fanout remasure 2026-09-07T20:31Z: keep_alive --check agen
- **asn-1788814034-sre_rele** sre_release→sre_release when=later eta=17m · ACK Staff CLEAN remasure — clamp hub peers 96→8 + FANOUT floor=8; no s
- **asn-1788817796-sre_rele** queue_steward→sre_release when=now eta=19m · [research-speed] Staff floor miss — agents=7 < floor=8; remeasure+resp
- **asn-1788863445-factory_** verify_runner→factory_engineer when=now eta=36m · Restore scripts/peer_self_heal.py APIs deleted in WT (~1141 lines vs H
- **asn-1788870380-factory_** verify_runner→factory_engineer when=now eta=36m · [verify unblock] Restore scripts/peer_self_heal.py from HEAD — gutted 
- **asn-1788870588-factory_** verify_runner→factory_engineer when=now eta=32m · Fix tests/test_compact_land_proof.py:31 FAIL test_deferred_poison_scru
- **asn-1788870645-factory_** verify_runner→factory_engineer when=now eta=34m · Needle: scripts/_mark_flaw_research_landed.py:137 — add _land_proof('d

## Niche guidance

### Factory Engineer
- Assign verify_runner for test-only runs; adapt_specialist for profile drift.

### Orchestrator
- Assign disjoint file scopes — never two peers same path.
- Run `./scripts/peer eta` per peer before dispatch; skip when=miss.

### Queue Steward
- Assign sync pairs to self; escalate drift to orchestrator with ETA.

### Verify Runner
- Accept run-only assignments; assign factory_engineer for code fixes.
