# N01 research stress gaps

**Needle:** `OVERSEER_NICHE_P0_PRACTICE_N01_2026_09_04`  
**Run:** 2026-09-06 · role `niche_distiller` · heldout acc **1.000** (9/9) · full corpus **45**  
**Method:** `--eval-only` on `N01_*_heldout.jsonl` + live WORK_QUEUE / Backlog bullets via `predict`

Do **not** prune the corpus. Append JSONL / tighten rule baseline; neural ~10M swap later.

## Miss classes

| ID | Gap | Evidence | Falsifier | Status |
|----|-----|----------|-----------|--------|
| G1 | **Bare module scope** — `` `peer_watch` `` without `scripts/` → `scope=""` vs gold `scripts/peer_watch.py` | Stall-watch row (`OVERSEER_WATCH_HOLD_PRIMARY`) | Row exact-matches after `_MOD_TICK_RE` | **fixed** 2026-09-05 — `_MOD_TICK_RE` → `scripts/<mod>.py` if file exists |
| G2 | **Unknown bracket tags → kit=null** — `[compression-train]`, `[flaw-research]`, `[comms-improve]`, `[research-speed]` | Live Active + train exemplars | Serve → `kit=false` | **fixed** — tags in `_KIT_TAG_FALSE`; flaw-research gold kit corrected false |
| G3 | **Glob / wildcard paths** — `scripts/compression_t4_*` | Active T4 scale rung | Scope `scripts/compression_t4_*` | **fixed** — `*` allowed in `_SCOPE_BARE_RE` |
| G4 | **Notes-relative bare filenames** — `COMPRESSION_TRAIN_RECIPE.md` | Active Freeze TRAIN recipe | Scope `notes/COMPRESSION_TRAIN_RECIPE.md` | **fixed** — `_NOTES_MD_BARE_RE` |
| G5 | **Tags-only / prose-only → empty scope** — `[comms-improve]` Active lines mention `bus.jsonl` / `peer_loop.` without `scripts/`/`notes/` path | Live Active Compact encodings + GibberLink | Gold `scope=""` exact-match; do **not** invent `notes/COMMS_TRENDS.md` | **fixed** 2026-09-05 — appended 2 JSONL exemplars (no prune); accept empty scope |
| G6 | **`[factory:…]` lane tags → kit=null** — `[factory:grounded_loop]` missing from `_KIT_TAG_FALSE` | Live WORK_QUEUE (2026-09-06) | Serve → `kit=false` (scope still from bare `peer_loop` / paths) | **fixed** 2026-09-06 — `factory:[a-z0-9_]+` in `_KIT_TAG_FALSE`; +2 JSONL (no prune) |
| G7 | **Bare `stress_bars.json` → empty / wrong notes/** — Backlog write lacks `notes/compression_artifacts/` | Live Backlog `OVERSEER_COMPRESSION_STRESS_*`; canonical `notes/COMPRESSION_TRAIN_READY.md` | Serve → `scope=notes/compression_artifacts/stress_bars.json` (not `notes/stress_bars.json`) | **fixed** 2026-09-06 — `_ARTIFACT_JSON_BARE_RE`; +2 JSONL; heldout 9@1.0 |

## Live sample (post-fix 2026-09-06)

| Line tag | pred.kit | pred.scope | Notes |
|----------|----------|------------|-------|
| `[compression-train]` T4 scale | false | `scripts/compression_t4_*` | G2+G3 closed |
| `[compression-train]` Freeze TRAIN | false | `notes/COMPRESSION_TRAIN_RECIPE.md` | G2+G4 closed |
| `[comms-improve]` Compact encodings | false | `""` | G5 closed — tags-only; no invented COMMS_TRENDS path |
| `[factory:grounded_loop]` Harden | false | `scripts/peer_loop.py` | G6 closed — factory lane ≠ kit |
| `[compression-train]` write stress_bars.json | false | `notes/compression_artifacts/stress_bars.json` | G7 closed — TRAIN_READY canonical |
| `[compression-train]` Integrate if bars clear | false | `""` | tags-only; no invented path |
| Stall-watch `` `peer_watch` `` | true | `scripts/peer_watch.py` | G1 closed |

| G8 | **`[top10]` + `paths: docs/…` stolen by done= proof** — kit=null; scope=`notes/INTEGRATION_PROOF_*` | Live Active Hard-Fix #66 Soft + **#82 Soft residual** (privilege SQL CI) full WQ bullets | Serve → `kit=false` · `scope=docs/ops/KILL_SWITCHES.md` / `docs/ops/PRIVILEGE_SQL_CI.md` | **fixed** 2026-09-08 — `top10` in `_KIT_TAG_FALSE`; `docs/` in scope regex; skip `*_PROOF*` / prefer `paths:`; +#66+#82 live JSONL (no prune; curator wave) |
| G9 | **Bare product `src/…ts:line` → empty scope** — CaaS/Newdrop pen-test WQ cites `src/app/…ts:152` outside scripts/notes/docs | Live Active `[pen-test] Webhook signing secret… routes-fail-closed.test.ts:152` (peer-6 WQ) + tip-cover #177 | Serve → `kit=false` · `scope=src/app/api/stripe/routes-fail-closed.test.ts` (strip `:line`); tip-cover → `notes/TOP10_PRODUCTION_POWER_TASKS.md` | **fixed** 2026-09-08 — `src/` in N01 scope regex; `:line` terminator + `_clean_scope_cand` for `.ts`/`.tsx`; +tip-cover+#pen-test JSONL (no prune) |
| G10 | **Landed Soft residual proof-steal / bare ops** — Soft `#38` cites bare `STAGING.md` + done=`notes/INTEGRATION_PROOF_*`; service-role Soft cites only proof → pred fell back to INTEGRATION_PROOF (train gold never uses proof as scope) | Live WQ tip-cover after #172/#170/#175–#176 | Serve → `docs/ops/STAGING.md` for bare Soft ops; proof-only Soft → `scope=""`; open tip-cover Tasks still `notes/TOP10_PRODUCTION_POWER_TASKS.md` | **fixed** 2026-09-08 — `_pick_scope` never falls back to `*_PROOF*`; `_OPS_SOFT_BARE_RE` Soft/top10/newdrop → `docs/ops/`; +live Soft JSONL (no prune); floors rise-only |

## Pass / ship rule

Heldout niche accuracy ≥ **0.90** after each fix wave. Ship stress doc even if some G* remain open — enqueue next-run rows here, do not invent hardware numbers.

## Anti-theater

- Heldout 1.0 alone ≠ production-ready; live Backlog miss classes above are the real stress.
- Closing BITNET_RESEARCH_TASKS “research stress → STRESS_GAPS” requires this file on disk with ≥1 falsifiable gap.
- Do **not** map bare `stress_bars.json` → `notes/stress_bars.json` (duplicate/non-canonical); gold is `notes/compression_artifacts/stress_bars.json`.

---

# P1 replicate — N03 + N08

**Needle:** `OVERSEER_NICHE_P1_N03_N08_2026_09_06`  
**Run:** 2026-09-08 · role `niche_distiller` · N03 heldout **1.000** (8/8) · N08 heldout **1.000** (7/7) · corpora N03=**63** N08=**63**  
**Landed:** `practice_n03/` + `practice_n08/` + `scripts/niche_n03_practice.py` + `scripts/niche_n08_practice.py` (N01 recipe stamp; rule baselines)

Scaffold is green. **P1 stress closed 2026-09-08** (do not prune corpora — append JSONL / tighten rules):

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P1-G1 | N03 | **Twin-needle prefer-order** — land-proof twin + primary in one line; **earliest `OVERSEER_*` by document position** (labeled/`Needle:` is match shape, not priority) | Live twin `LAND_PROOF…` → primary `Needle: KIT_RUN…` stolen under labeled-first; FACTORY proof rows; AWM multi-needle (`FACT_LIBRARIAN`·`LOSSLESS`·`AMNESIA`) | Twin `→` / multi ticks → first by `m.start`; later `Needle:` does not steal | **fixed** 2026-09-08 — `predict` position-sort (`niche_n03_practice.py`); +live twin/FACTORY/AWM JSONL; heldout 8@1.0 |
| P1-G2 | N03 | **Prose “landed overseer:” without ticks** — bare token after colon | Live refuse-ASN + Active-cleared digest rows | Serve → exact needle; null only when no `OVERSEER_` token | **fixed** 2026-09-08 — +live bare-colon JSONL; `_NEEDLE_LABELED_RE` |
| P1-G3 | N03 | **False claimable needle** — essay claims verify passed but no OVERSEER token → must stay `null` | Live false-`[x]` kit/peer_loop essays without token | `--serve` → `null`; never invent needle from path / PR alone | **fixed** 2026-09-08 — +live false-`[x]` JSONL; heldout 8@1.0 |
| P1-G4 | N08 | **Substring trap** — `test_queue_drift` in unittest FAIL log must not → `queue_drift` | Fixed in rule via `failure_type=tests` before queue_drift | Regression if order flips | **fixed** in baseline; keep as falsifier |
| P1-G5 | N08 | **Soft warn vs chicken-egg** — “soft warn ignored” must not collapse to `healthy` | Chicken-egg train row + live `plan-gate soft warn ignored; continuing` | `plan-gate soft` only → healthy; chicken-egg markers win | **fixed** 2026-09-08 — +1 live soft-warn→healthy JSONL |
| P1-G6 | N08 | **Improve STOPPED + “wrong namespace”** — prefer `oversight_down` over `namespace_flip` | Live `improve LaunchAgent STOPPED` + wrong namespace | Serve → `oversight_down` | **fixed** 2026-09-08 — `\bimprove\b…\bstopped\b` before namespace_flip; +1 JSONL |
| P1-G7 | N08 | **Live peer_watch Cycle `rc=0`** — `\brc=\d+` trapped healthy Cycle rows as `verify_fail_agent_exit` | Live peer_watch 2026-09-08 `Cycle rc=0 · verify=ok` + last_cycle + `bottleneck_id=adapt_stale` | Serve → `healthy`; non-zero `rc=255`/`rc=1` still `verify_fail_agent_exit` | **fixed** 2026-09-08 — `rc=[1-9]\d*` only; +last_cycle/Cycle adapt_stale JSONL; heldout 7@1.0 |

## P1 pass / ship rule

Heldout niche accuracy ≥ **0.90** for each of N03 / N08. Closing this needle requires practice dirs + weights + this P1 section — not silent `[x]`. Next: P2 research agents attack live traces → append miss classes here.

---

# P2 live-trace attack — N03 + N08

**Needle:** `OVERSEER_NICHE_P2_LIVE_TRACE_2026_09_08`  
**Run:** 2026-09-08 · role `dataset_curator` · live WORK_QUEUE Soft residual + peer-loop-state / peer status  
**Method:** `--serve` / `predict` on live traces; append JSONL + tighten rules; **no prune**

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P2-G1 | N03 | **Path-fragment bare OVERSEER** — `notes/OVERSEER_NOTES.md` steals earliest bare token before real needle | Live-shaped path trap; Soft residual docs paths | Serve → skip `/OVERSEER_*` and `OVERSEER_*.ext`; real token wins | **fixed** 2026-09-08 — `_bare_path_fragment` in `niche_n03_practice.py`; +JSONL |
| P2-G2 | N03 | **Soft residual open without token** — Hard-Fix #82 privilege SQL → must stay `null` | Live Active #82 | `--serve` → `null` (anti invent from Soft land hash) | **fixed** — +live #82 null JSONL; false invent gold corrected |
| P2-G3 | N08 | **`automation-hub-peer-loop` steals loaded_no_pid** — namespace_flip before loaded-no-pid | Heldout LaunchAgent hub-peer row | Serve → `loaded_no_pid` | **fixed** — reorder predict |
| P2-G4 | N08 | **Live notes-only porcelain phrasing** — `notes-only porcelain` / `porcelain notes/` | Live peer status dirty notes | Serve → `dirty_tree_notes_only` | **fixed** — phrase expand +JSONL |
| P2-G5 | N08 | **peer log quiet + poke no-op** without `no new lines` | Live `updated 69.3h ago peer-loop.log · poke no-op` | Serve → `peer_quiet` | **fixed** — broaden peer_quiet cues |
| P2-G6 | N08 | **last_cycle poison** — `verify_ok True` / bare `verify_ok` + deferred | Train row miss | Serve → `last_cycle_poison` | **fixed** — regex `verify_ok\s*=?\s*true` + last_cycle∧verify_ok |
| P2-G7 | N08 | **False notes-only gold** — `notes+scripts` continue_on_dirty labeled dirty_tree | Train gold vs live continue_on_dirty healthy | Gold → `healthy` (label fix, not prune) | **fixed** 2026-09-08 |

## P2 pass / ship rule

Heldout ≥ **0.90** each; `python3 scripts/niche_distill_validate.py` OK; floors only rise. Do not prune Soft residual demote needles — they are claimable hub tokens.

---

# P2 live stress — N08 residual adapt_stale under green Cycle

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05` · role `dataset_curator` · 2026-09-08  
**Evidence:** live probe `Cycle rc=0 · verify=ok` + log `bottleneck_id=adapt_stale healed` → rule returned `adapt_stale` (substring before healthy).  
**Corpus:** N08 primary append-only (no prune) · heldout ≥7 floor · validate via `python3 scripts/niche_distill_validate.py`

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P2-G1 | N08 | **Residual adapt_stale after heal** — green Cycle / `verify_ok=true` must not lose to bare `adapt_stale` substring when stall is healed | Live peer+improve / continue_on_dirty ticks mentioning prior adapt_stale | `--serve` → `healthy`; active `bottleneck id=adapt_stale` / `should_re_adapt` still `adapt_stale` | **fixed** 2026-09-08 — green short-circuit before substring; +live JSONL; heldout @1.0 |

**Anti-prune:** `gen_all(skip_existing)` skips **any** existing primary+heldout (not only N01/N03/N08). Floors enforced by `niche_distill_validate.py`.

---

---

# P2 live stress — dataset curator anti-prune (2026-09-08)

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · N03 heldout **1.000** · N08 heldout **1.000** · corpora N03=**63** N08=**63**  
**Method:** append-only union hub∪peer-6 (restore below-floor divergence) + live last_cycle / AWM / validate-floor traces — **no prune**

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P2-G1 | N08 | **Anti-prune floor breach** — hub SoT N08 primary/heldout dipped below FLOOR_ROWS (39&lt;40 / 7&lt;8) after P1 divergence vs peer-6 | `niche_distill_validate.py` ISSUES prune forbidden | validate OK with floors bumped to live counts; counts only rise | **fixed** 2026-09-08 — union restore + live append; floors→63/14 |
| P2-G2 | N03 | **AWM multi-needle earliest** — three OVERSEER ticks in AGENT_WORKING_MEMORY → first by document position | Live AWM Needles line FACT_LIBRARIAN·LOSSLESS·AMNESIA | Serve → `OVERSEER_FACT_LIBRARIAN_2026_09_07` | **fixed** — +live JSONL (predict already position-sort) |
| P2-G3 | N08 | **continue_on_dirty last_cycle ≠ stall** — verify_ok + tree dirty note must stay `healthy` | Live last_cycle note continue_on_dirty | Serve → `healthy` | **fixed** — +live JSONL |
| P2-G4 | N08 | **diagnose adapt fingerprint stale** — should_re_adapt / Adapt fingerprint stale → `adapt_stale` | Live `./scripts/peer diagnose` medium row | Serve → `adapt_stale` | **fixed** — +live JSONL |
| P2-G5 | N08 | **peer_up=false improve_up=false snap** — peer-progress-watch last_snap daemons down still predicted `healthy` | Live peer-progress-watch.json peer_up/improve_up False | Serve → `oversight_down` | **fixed** 2026-09-08 — `peer_up=false`/`improve_up=false` → oversight_down |

## P2 pass / ship rule

Heldout niche accuracy ≥ **0.90**. Closing P2-G1 requires validate floors ≥ corpus counts (never lower). P2-G5 closed — progress-watch snap maps to `oversight_down`.

# N02 rule practice re-land

**Needle:** `OVERSEER_NICHE_PRACTICE_N02_2026_09_07`  
**Run:** 2026-09-08 · role `niche_distiller` · heldout acc **1.000** (16/16) · full corpus **96** · **no prune**  
**Landed:** `scripts/niche_n02_practice.py` + `practice_n02/checkpoint.json` + rule `.pt` (journal claimed stamp earlier; durable runner was missing on hub)

| ID | Gap | Evidence | Falsifier | Status |
|----|-----|----------|-----------|--------|
| N02-G1 | **Legend false-hit** — trailing `(kit/research/creative/defer)` must not steal label | Heldout “as kit … (kit/research/creative/defer)” | Serve → `kit` not `research`/`creative`/`defer` from legend | **fixed** — explicit cue regex only |
| N02-G2 | **Theater stamp** — memory pin without `checkpoint.json` / runner on disk | Hub lacked `niche_n02_practice.py` + rule ckpt | Paths exist + `--eval-only` passed=True | **fixed** 2026-09-08 |

**Next vault stamp:** none — N04 rule practice landed below; P1-G1–G7 closed 2026-09-08 (document-order twin + live peer_watch). Prefer stress-driven append over mass mint.

---

# P1 replicate — N02 + N04 rule practice stamps

**Needles:** `OVERSEER_NICHE_PRACTICE_N02_2026_09_07` · `OVERSEER_NICHE_PRACTICE_N04_2026_09_07`  
**Run:** 2026-09-08 · role `niche_distiller` · N02 heldout **1.000** (16/16) · N04 heldout **1.000** (16/16) · full corpora 96 each  
**Landed:** `scripts/niche_n02_practice.py` + `scripts/niche_n04_practice.py` + `practice_n02/checkpoint.json` + `practice_n04/checkpoint.json` (rule baselines; neural `.pt` untouched; **no corpus prune**)

| ID | Niche | Gap / note | Evidence | Falsifier | Status |
|----|-------|------------|----------|-----------|--------|
| N02-G1 | N02 | Trailing `(kit/research/creative/defer)` legend must not steal label | Classify-as-kit rows with legend paren | `--serve` → `kit` not `creative`/`research` | **fixed** — `_LEGEND_RE` strip before cue match |
| N02-G2 | N02 | Prefer explicit `label=` / `as` / `→` / `Factory` / `[tag]` over bare words | Train+heldout cue shapes | heldout ≥0.90 | **fixed** in rule baseline |
| N04-G1 | N04 | Longest label first (`…_escalate` before `…_yes`) | Multi-word seed labels | heldout ≥0.90 | **fixed** in rule baseline |

## N02/N04 pass / ship rule

Heldout niche accuracy ≥ **0.90**. Closing WORK_QUEUE stamp lines requires practice runners + `checkpoint.json` + this section — not neural-only dirs. **2026-09-08 N03+N08 wave:** N03 corpus **63** · heldout **12@1.0** · P1-G1/G2/G3 closed (earliest-position); N08 corpus **63** · heldout **14@1.0** · P1-G7 closed (`rc=0` ≠ agent_exit).

---

# Dataset curator — N08 anti-prune floor restore

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · N08 primary **53** · heldout **11@1.0** · schema 422/18720 bad=0 · **no prune**

| ID | Gap | Evidence | Falsifier | Status |
|----|-----|----------|-----------|--------|
| DC-G1 | Hub N08 under floor (39/7 vs 40/8) after P1 wave | `niche_distill_validate.py --distill` ISSUES prune forbidden | counts ≥ floors; heldout ≥0.90 | **fixed** 2026-09-08 — append-only live adapt_stale + continue_on_dirty healthy; repaired heldout loaded_no_pid (removed hub/namespace cue); floors bumped 53/11 |

**Anti-theater:** never lower FLOOR_ROWS; never drop rows to inflate accuracy. peer-6 `notes/niche_distill` synced from Automation root SoT.

---

# P2 live stress — dataset_curator 2026-09-08 wave (pen-test src:line + last_cycle triad)

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · N01 **68**/heldout **18@1.0** · N08 **67**/heldout **16@1.0** · validate floors rise-only · **no prune**

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P2-G8 | N01 | **Bare `src/…/file.ts:152` not captured** — `:` line suffix killed `_SCOPE_BARE_RE` before `_clean_scope_cand` | Live Active `[pen-test]` Webhook signing secret `routes-fail-closed.test.ts:152` | Serve → `kit=false` · `scope=src/app/api/stripe/routes-fail-closed.test.ts` | **fixed** 2026-09-08 — lookahead allows `:`; +live JSONL (no prune) |
| P2-G9 | N08 | **`last_cycle`+`deferred`+`verify_ok` without `failure_type=`** — triad fell through to `healthy` | Live-shaped deferred poison prose (no `failure_type=deferred` key) | `--serve` → `last_cycle_poison`; continue_on_dirty last_cycle without deferred stays `healthy` | **fixed** 2026-09-08 — triad branch in `niche_n08_practice.predict`; +JSONL |

**Pass / ship:** `python3 scripts/niche_distill_validate.py` OK; N01/N08 `--eval-only` heldout ≥0.90; floors never lowered.

---

# Dataset curator — peer-6 N02/N04 floor restore + live last_cycle lock

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · cycle `20260908T1242Z` · N02=**96**/16@1.0 · N04=**96**/16@1.0 · N08 primary **64** · heldout **14@1.0** · schema peer-6 10/449 bad=0 · hub 214/11873 bad=0 · **no prune**

| ID | Gap | Evidence | Falsifier | Status |
|----|-----|----------|-----------|--------|
| DC-G2 | peer-6 distill missing N02/N04 primaries → validate floor FAIL (0&lt;96 / 0&lt;16) while hub SoT OK | `niche_distill_validate.py` ISSUES prune forbidden on peer-6 | validate ok=True; N02/N04 counts ≥ floors; heldout ≥0.90 | **fixed** 2026-09-08 — copy hub SoT N02/N04 primary+heldout into peer-6 (append-only restore; no rewrite) |
| DC-G3 | Live last_cycle continue_on_dirty (queue_fp=ef6b0c5971d3d458 · git_head=bfae3c3) must stay `healthy` | peer-loop-state last_cycle this cycle | `--serve` → `healthy`; floors N08 63→64 rise-only | **fixed** 2026-09-08 — +1 live JSONL on peer-6∪hub; FLOOR_ROWS N08=64 |

**Live probe (this cycle — no miss):** N01 Soft residual #66 → `kit=false` `scope=docs/ops/KILL_SWITCHES.md`; N03 open top10 → `null`; N08 diagnose Adapt fingerprint → `adapt_stale`; green Cycle+healed adapt_stale → `healthy`.

---

# P2 live stress — N08 peer_quiet vs WORKING status chrome

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · cycle `20260908T1244Z` · N08 primary **67** · heldout **16@1.0** · N01 **64**/15 · **no prune**

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P2-G8 | N08 | **`log quiet until` UI chrome → false `peer_quiet`** — live `peer status` STATE●WORKING + Cycle `rc=0 · verify=ok` still matched peer_quiet before green short-circuit | Live hub `./scripts/peer status` blob (`state S (log quiet until subprocess)` · Log updated 71.9h ago) | `--serve` / `predict(status)` → `healthy`; true `poke no-op` / `peer log quiet` still `peer_quiet` | **fixed** 2026-09-08 — green short-circuit before peer_quiet; drop `log quiet until` cue; +live JSONL; floors→67/16 |

**Anti-prune:** floors only rise; do not drop heldout peer_quiet rows to inflate healthy rate.

---

# Dataset curator — tip-cover paths: wins Tasks: (2026-09-08)

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · cycle `20260908T1245Z` · N01 primary **68** · heldout **17@1.0** · N08 **67**/16 · schema peer-6 10/461 bad=0 · **no prune**

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| DC-G4 | N01 | **tip-cover #177 `paths: docs/…` + `Tasks: notes/TOP10_…`** — Tasks path must not steal primary scope | Live-shaped tip-cover mix; Soft residual docs path | `--serve` → `kit=false` · `scope=docs/ops/KILL_SWITCHES.md` | **fixed** 2026-09-08 — +1 train +1 heldout append-only; floors N01 →68/17 (rise-only; concurrent appends kept) |
| DC-G5 | bank | **Set-dedupe union false-prune** — exact-line `set()` collapse of intentional duplicate N02/N04 rows (96→51/58) violates anti-prune | Accidental curator union this cycle | Restore from `git show HEAD:notes/niche_distill/N0{2,4}_*.jsonl`; floors never lower | **fixed** 2026-09-08 — git HEAD restore; FLOOR_ROWS N02/N04 remain 96/16; learn: never unique-collapse corpus |


**Validate harden:** `FLOOR_FLOOR_MIN` + `effective_floor()` in `scripts/niche_distill_validate.py` — N02/N04 never below 96/16 even if FLOOR_ROWS regresses.
**Anti-prune learning:** N02/N04 bank rows intentionally repeat; row-count floors ≠ unique-line floors. Union = append hub-only / peer-only lines only — never `set(lines)`.

**Live probe:** N01 tip-cover+paths → `docs/ops/KILL_SWITCHES.md`; pen-test `src/...ts:152` → `src/app/api/stripe/routes-fail-closed.test.ts`; Soft #66 → `docs/ops/KILL_SWITCHES.md`; N08 last_cycle continue_on_dirty → `healthy`.

---

# P2 live stress — N08 peer_quiet vs WORKING status chrome (dataset_curator)

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05`  
**Run:** 2026-09-08 · role `dataset_curator` · cycle `20260908T1244Z` · N08 **67**/16@1.0 · N02/N04 anti-prune restore **98**/16 · **96**/16 · **no prune**

| ID | Niche | Gap | Evidence | Falsifier | Status |
|----|-------|-----|----------|-----------|--------|
| P2-G10 | N08 | **`log quiet until` UI chrome → false `peer_quiet`** — live `peer status` STATE●WORKING + Cycle `rc=0 · verify=ok` matched peer_quiet before green short-circuit | Live hub `./scripts/peer status` (`state S (log quiet until subprocess)`) | `predict(status)` → `healthy`; `poke no-op` still `peer_quiet` | **fixed** 2026-09-08 — green short-circuit before peer_quiet; drop `log quiet until` cue; +live JSONL |
| DC-G4 | N02/N04 | **Primary row-count prune** — corpora dipped 96→51/58 while floors lowered to match (score-inflation risk) | git HEAD + peer-7/coding still held 96-line blobs | validate floors ≥ restored line counts; never lower floors | **fixed** 2026-09-08 — byte-line union restore → N02=98 N04=96; floors rise-only |

**Anti-prune:** floors only rise; do not collapse duplicate-input rows to shrink corpora.

---

# Dataset curator — tip-cover Tasks: meta empty-scope (cycle 20260908T1249Z)

**Needle:** `OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05` · role `dataset_curator` · dataset_curator 20260908T1249Z tip-cover Tasks meta  
**Landed:** `_PROOF_SCOPE_RE` += `TOP10_PRODUCTION_POWER_TASKS`/`_TASKS.md`; N01 tip-cover gold `scope=""`; N02/N04 anti-prune restore floors ≥96/16; validate ok=True; **no prune**

| ID | Gap | Falsifier | Status |
|----|-----|-----------|--------|
| N01-G10b | tip-cover after #177 `Tasks: notes/TOP10_*_TASKS.md` must not be primary scope | `--serve` → `scope=""`; Soft `paths: docs/ops/…` still docs | **fixed** 2026-09-08 |
