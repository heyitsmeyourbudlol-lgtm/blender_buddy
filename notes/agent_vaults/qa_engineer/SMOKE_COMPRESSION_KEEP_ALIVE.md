# Smoke — compression keep-alive fuel (2026-09-07)

**Role:** QA Engineer · **needle:** `OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05` · **fanout:** #15  
**Items:** Keep-alive fuel · Staff CLEAN fanout · Efficiency pass · Background keep-alive  
**verdict:** **PARTIAL FAIL** (re-smoke 2026-09-07 16:31 EDT / 20:31Z — Staff floor 7&lt;12; fuel/eff/billing/services/unittest PASS)

## Strategy (hallucination guard)

```
Assumption: I will hallucinate unless grounded.
Evidence:   scripts/compression_keep_alive.py --check JSON (agents=7 floor=12 agents_ge_floor=false);
            --check always exit 0 (main:551-553) — Staff AC is agents_ge_floor not rc;
            systemctl --user: 4 compression units active running;
            WQ Staff already [ ] + ASN asn-1788812816-sre_rele
Hypothesis: Efficiency/fuel still green; Staff CLEAN still below floor → keep open + re-ASN SRE
Falsifier:  agents_ge_floor=true (would close Staff) OR S<100 OR wave=true OR unittest fail
Verify:     keep_alive --check; unittest test_compression_keep_alive; systemctl --user
Defy:       output-compare discrepancy + keep Staff [ ] — no hero-spawn / no Shard invent
```

## Plan questions (before edit)

1. Numbered plan ≥3 steps? **Yes**
2. Evidence read myself? **Yes** — `--check` JSON agents=7 floor=12 agents_ge_floor=false exit=0
3. In persona? **Yes** — product smoke + queue acceptance (enqueue/ASN; no SRE respawn)
4. Root vs symptom? **Root for QA:** Staff CLEAN below floor while keep-alive service active; fail-closed reopen until live ≥floor

## Numbered test plan

| # | Action | Paths | Expected | Verify |
|---|--------|-------|----------|--------|
| 1 | Keep-alive smoke | `scripts/compression_keep_alive.py --check` | wave=false; S≥100; agents≥floor | JSON |
| 2 | Unittest | `tests/test_compression_keep_alive.py` | OK | unittest |
| 3 | Services | `systemctl --user list-units 'compression*'` | 4 units active running | systemctl |
| 4 | auto_train | `scripts/compression_auto_train.py --check` | research_complete true | JSON |
| 5 | Queue sync | WQ ↔ self_improve Staff line | keep Staff [ ] on FAIL | twin identical |
| 6 | Smoke doc | this file | expected vs actual | done-gate |

## Expected vs actual (re-smoke 2026-09-07 16:31 EDT / 20:31Z / fanout #15)

| Check | Expected | Actual |
|-------|----------|--------|
| recipe / T4 / train_unlock | locked + unlocked artifact | **PASS** train_unlocked=true recipe_locked=true t4_done=true |
| `keep_alive --check` exit | 0 (file-only) | **0** (soft — does not encode Staff AC) |
| wave / billing | false / billing_ok | **PASS** wave=false billing_ok desktop_free |
| S / pack | ≥100 / measured | **PASS** S≈134.09 pack=37288 |
| agents ≥ floor | true (≥12) | **FAIL** agents=7 floor=12 agents_ge_floor=false |
| compression-*.service ×4 | active running | **PASS** (auto-train, gpu-worker, keep-alive, result-watch) |
| auto_train `--check` | research_complete | **PASS** true + rung0_alive |
| `unittest tests.test_compression_keep_alive` | OK | **OK (14)** |
| Staff CLEAN fanout | agents_ge_floor | **FAIL → keep [ ] + re-ASN sre_release when=now** |
| Efficiency / fuel | stay closed | **PASS** remain [x] |

## Diff / paths

- `notes/WORK_QUEUE.md` — Staff CLEAN stays [ ]; remasure note refreshed; fuel/Efficiency stay [x]
- `scripts/self_improve_context.md` — identical twin
- `notes/agent_vaults/qa_engineer/SMOKE_COMPRESSION_KEEP_ALIVE.md` — this checklist
- ASN → sre_release (when=now; remasure 20:31Z)

## Acceptance decision

- **Product smoke keep-alive fuel (T4 / recipe LOCK / min-RAM NVFP4):** **PASS**
- **Staff CLEAN fanout:** **FAIL** (agents=7 &lt; floor=12) — bug stays open; SRE re-assigned
- **Efficiency pass (measure only):** **PASS** (S≈134 ≥100; nvfp4_pack_bytes=37288)
- **Background keep-alive:** **PASS** (unit active running — count still below floor)
- **Needle:** `OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05`
- **Forbidden skipped:** no Shard-* / T4 microbench fanout invent; no hero-spawn

## Done questions

1. Verify for named root cause? **Yes** — remasure agents_ge_floor=false (Staff AC)
2. Expected vs actual? **Mismatch on Staff** — output-compare discrepancy recorded; fail closed
3. Measurable outcome? **Staff [ ] retained**; fuel/eff [x]; smoke checklist updated; ASN when=now
