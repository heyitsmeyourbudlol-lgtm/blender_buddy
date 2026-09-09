# Registry-status / native_verify DEFERRED — fact-check ledger

**Owner niche:** `fact_checker`  
**Assignment:** `registry-status native_verify DEFERRED` — CLI nv=0+DEFERRED prevents Active reopen of Mac leftovers  
**Anchors:** `scripts/factory_fanout.py:registry_status_summary`; `scripts/project_automation.py:_creative_deferred_under_self_sufficient`  
**Checked:** 2026-09-04 · role `fact_checker` · peer-5 (hub SoT read; peer-5 tree lacks `factory_fanout.py`)

## Hallucination strategy (this cycle)

```
Assumption: I will hallucinate that the CLI banner alone prevents Active reopen, or that nv=0 means zero Mac leftovers.
Evidence:   Automation/scripts/factory_fanout.py:360-371; project_automation.py:1926-1990;
            live `python3 scripts/factory_fanout.py --registry-status` → nv=0 offline_mac=3 + DEFERRED banner
Hypothesis: SPLIT — nv=0+DEFERRED PASS as operator signal; Active reopen blocked by deferred markers + land_proof;
            causal wording "CLI … prevents" is OVERCLAIM
Falsifier:  No DEFERRED line under factory_meter_mode=self_sufficient; land_proof false on assignment text;
            [output-research] Mac creative lines not deferred
Verify:     --registry-status; deferred/land_proof probes; unittest test_land_proof_registry_status_deferred
Defy:       memory-recall + output-compare + diagnose if unsure
```

## Plan gate (answered)

1. **Problem:** Creative/IDEA still sell “CLI nv=0+DEFERRED prevents Active reopen” as a causal fact; risk of treating banner text as the gate.
2. **Smallest change:** One ledger file with R1–R5 + strike OVERCLAIM on Creative wording.
3. **Falsifier:** Any R-row without file:line or CLI excerpt; R4 marked full PASS.

### Numbered execute plan (≥3)

1. **Write** this ledger (strategy + R1–R5) · path `notes/REGISTRY_DEFERRED_FACTCHECK.md` · verify `rg '^\| R[1-5] ' notes/REGISTRY_DEFERRED_FACTCHECK.md | wc -l` → 5
2. **Strike** OVERCLAIM causal wording · path hub `notes/CREATIVE_BACKLOG.md` registry-status line · verify line cites this ledger
3. **Verify + DONE** · expect `--registry-status` shows `nv=0` + `DEFERRED`; unittest land-proof PASS · `./scripts/peer done-gate`

## Master ledger

| ID | Claim | Verdict | Source | Evidence (one line) | Checked by |
|----|-------|---------|--------|---------------------|------------|
| R1 | Under current hub registry, `native_verify_remaining=0` (no `git`/`unaudited`/`needs-kit-install`) | **PASS** | `scripts/factory_fanout.py:160-196` (`registry_status_summary`); live CLI 2026-09-04 | `python3 scripts/factory_fanout.py --registry-status` → `native_verify_remaining=0` (offline_mac_on_disk=3 separate). | fact_checker 2026-09-04 |
| R2 | When `factory_meter_mode=self_sufficient`, CLI prints a **DEFERRED** banner telling operators not to Active-enqueue Mac offline leftovers | **PASS** | `scripts/factory_fanout.py:366-371` | Live: `DEFERRED (factory_meter_mode=self_sufficient) — do not Active-enqueue Mac offline leftovers / husks; Creative backlog only`. | fact_checker 2026-09-04 |
| R3 | Assignment text is deferred under self_sufficient and has land-proof so Active twin closes | **PASS** | `scripts/project_automation.py:1926-1990`; `factory_progress.py:_DEFERRED_MARKERS` (`registry-status`); `_LAND_PROOF_NEEDLES` + `OVERSEER_REGISTRY_NATIVE_VERIFY_SUMMARY_2026_09_04` | `_creative_deferred_under_self_sufficient(claim)=True`; `_land_proof_present(claim)=True`; hub `WORK_QUEUE` / `self_improve_context` already `[x]`. | fact_checker 2026-09-04 |
| R4 | **Causal:** “CLI nv=0+DEFERRED **prevents** Active reopen of Mac leftovers” | **SPLIT** — signal **PASS**; causation **FAIL** / **OVERCLAIM** | R1–R3 sources; `loop_work_items` filter (not CLI) | Banner is **display**. Prevention is `_is_deferred` / `_creative_deferred_under_self_sufficient` + land-proof close — not the print path. | fact_checker 2026-09-04 |
| R5 | All Mac leftover Creative lines are blocked from becoming Active under self_sufficient | **SPLIT** — tagged `[output-research]` / `external_proof` / `registry-status` lines **PASS** (deferred); unmarked Mac-adjacent Creative **LEAK** | `notes/CREATIVE_BACKLOG.md`; deferred probe 2026-09-04 | DEFER: SaaS Health / CPT / Newdrop output-research + registry-status item. LEAK examples: `SaaS offline-mac honesty`, `Mac product-green without kit stays adapted` (no deferred marker). | fact_checker 2026-09-04 |

### Strike / split text (FAIL / OVERCLAIM)

| ID | Action |
|----|--------|
| **R4** | **Strike** causal “CLI … prevents”. Prefer: “CLI reports nv=0 + DEFERRED under self_sufficient; Active reopen blocked by deferred markers + land_proof (`_creative_deferred_under_self_sufficient`).” |
| **R5** | Do not claim blanket “all Mac leftovers”. Marker-tagged Creative only; untagged Mac-adjacent lines can still surface when Active is empty. |
| **R1** | Keep nv=0 distinct from `offline_mac_on_disk` / `actionable_on_disk` (observed 3 / 12) — Mac leftovers remain visible, just not native_verify Active. |

## Live CLI excerpt (this cycle)

```
registry-status: native_verify_remaining=0 offline_mac_on_disk=3 actionable_on_disk=12
  DEFERRED (factory_meter_mode=self_sufficient) — do not Active-enqueue Mac offline leftovers / husks; Creative backlog only
  offline_mac: F.I.R.E. Project, Marketplace, SaaS Health Dashboard
```

## Done self-check

1. Evidence paths read this cycle? Yes — hub `factory_fanout.py`, `project_automation.py`, `factory_progress.py`, live CLI.
2. Expected vs actual: expect nv=0 + DEFERRED + land_proof True → observed match.
3. Did not invent URLs; kit claims grounded in file:line + CLI.
4. Did not orchestrate other niches; ledger + Creative strike only.
