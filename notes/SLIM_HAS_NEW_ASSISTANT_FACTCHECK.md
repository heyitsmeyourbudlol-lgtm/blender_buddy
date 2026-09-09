# slim has_new_assistant EOF — fact-check ledger

**Owner niche:** `fact_checker`  
**Assignment:** **slim has_new_assistant EOF** — 64KiB reverse role scan replaces 256KiB conversation parse on peer wake  
**Anchors:** `scripts/peer_transcript.py:has_new_assistant_since_dispatch`; `scripts/project_automation.py:TAIL_READ_MAX_BYTES`  
**Checked:** 2026-09-04 · role `fact_checker` · peer-5 (hub SoT + peer-6 WIP compare)

## Hallucination strategy (this cycle)

```
Assumption: I invent that slim 64KiB landed on hub because compression_engineer learnings say DONE.
Evidence:   hub peer_transcript.py:456-467 `turns = read_conversation(path)`; peer-6:313 `_HAS_NEW_ASSISTANT_MAX_BYTES = 64 * 1024` uncommitted
Hypothesis: Hub/peer-5 SoT still full conversation parse; peer-6 WIP matches design; learning OVERCLAIM for peer wake
Falsifier:  hub defines `_HAS_NEW_ASSISTANT_MAX_BYTES` or has_new body lacks read_conversation(
Verify:     python probe PROBES_OK; rg '^\| S[1-7] ' notes/SLIM_HAS_NEW_ASSISTANT_FACTCHECK.md | wc -l → 7
Defy:       memory-recall + output-compare + diagnose if unsure
```

## Plan gate (answered)

1. **Problem:** Queue + compression learnings claim 64KiB reverse role scan replaced 256KiB parse on peer wake — hub SoT still calls full `read_conversation` / `path.read_text()`.
2. **Smallest change:** One ledger (S1–S7) + keep Active `[ ]` open; do not port peer-6 or close queue.
3. **Falsifier:** Hub `has_new_assistant_since_dispatch` uses `tail_text_lines(..., max_bytes=64*1024)`.

### Plan self-check (before edit)

1. Numbered plan ≥3 with paths+verify? **Yes**
2. Evidence read this cycle? **Yes** — hub `:405-467`, peer-6 `:311-438`, hub `project_automation.py:124`
3. Persona scope? **Yes** — fact_checker ledger + claim strike only
4. Root vs symptom? **Root** — false “landed” claim vs SoT
5. Other niche on path? **compression_engineer** peer-6 WIP — do not merge/orchestrate
6. Smallest change? Ledger; reject implementing slim here
7. Falsifier checked? Hub lacks `_HAS_NEW_ASSISTANT_MAX_BYTES`; still `turns = read_conversation(path)`
8. Pre-mortem: fails if Active marked `[x]` without hub land
9. Expected verify: S1/S2/S4/S6 FAIL hub; S5 PASS; S3 UNKNOWN; S7 PASS peer-6 WIP
10. Hallucination signal: confident DONE from TEAM_CONTEXT learning alone

### Numbered execute plan (≥3)

1. **Write** this ledger · path `notes/SLIM_HAS_NEW_ASSISTANT_FACTCHECK.md` (+ hub twin) · verify `rg '^\| S[1-7] ' … | wc -l` → 7
2. **Annotate** hub Active slim line — keep `[ ]`; add fact_checker OVERCLAIM note · verify still open
3. **Verify + DONE** · probe PROBES_OK; unittest Rules§9 subset; done-gate; GLink DONE

## Master ledger

| ID | Claim | Verdict | Source | Evidence (one line) | Checked by |
|----|-------|---------|--------|---------------------|------------|
| S1 | On **peer wake (hub SoT)**, 64KiB reverse role scan **replaces** 256KiB conversation parse in `has_new_assistant_since_dispatch` | **FAIL** + **OVERCLAIM** | hub `scripts/peer_transcript.py:456-467` | Still `turns = read_conversation(path)` then `turns[-1]`; no `_HAS_NEW_ASSISTANT_MAX_BYTES`. | fact_checker 2026-09-04 |
| S2 | `has_new_assistant_since_dispatch` **must not** call `read_conversation` (learning 21:51:51) — **landed** | **FAIL** + **OVERCLAIM** (hub/peer-5) | hub `:463`; peer-5 `:220`; learning `notes/PROJECT_LEARNING.md` | Hub+peer-5 still call `read_conversation`; only peer-6 WIP avoids it. | fact_checker 2026-09-04 |
| S3 | Slim scan ΔRSS **1.203→0.172 MB** on 6.3MB JSONL | **UNKNOWN** | peer-6 docstring `:409-410` (~1.2/~0.16); learning 1.203→0.172 | No reproducible probe artifact / log this cycle; numbers only in learning+docstring. | fact_checker 2026-09-04 |
| S4 | `CONVERSATION_READ_MAX_BYTES=auto.TAIL_READ_MAX_BYTES` prevents 512 drift **on hub** | **FAIL** + **OVERCLAIM** | hub `peer_transcript.py` (rg miss); peer-6 `:311` | Symbol **absent** on hub; present only on peer-6 uncommitted WIP. | fact_checker 2026-09-04 |
| S5 | `project_automation.TAIL_READ_MAX_BYTES = 256 * 1024` exists (anchor) | **PASS** | hub `scripts/project_automation.py:124` | Constant live; used by `tail_text_lines`. peer-5 seed lacks symbol. | fact_checker 2026-09-04 |
| S6 | Done queue **Align conversation JSONL tail** — `CONVERSATION_READ_MAX_BYTES` @ `:309` = 256KiB | **FAIL** + **OVERCLAIM** | hub WQ `[x]` Align…; hub file has **no** `CONVERSATION_READ_MAX_BYTES` | Closed without landing; peer-6 WIP has alias @`:311` → `TAIL_READ_MAX_BYTES`. | fact_checker 2026-09-04 |
| S7 | peer-6 WIP implements 64KiB reverse role scan via `tail_text_lines` + `reversed(lines)` | **PASS** (WIP only) | peer-6 `scripts/peer_transcript.py:313-438` (`git status` M, uncommitted) | `_HAS_NEW_ASSISTANT_MAX_BYTES=64*1024`; body uses `tail_text_lines` + reverse role walk; not hub. | fact_checker 2026-09-04 |

### Strike / split text (FAIL / OVERCLAIM)

| ID | Action |
|----|--------|
| **S1** | **Strike** “replaces … on peer wake” as landed. Prefer: “**Open** — implement on hub SoT; peer-6 WIP only (`_HAS_NEW_ASSISTANT_MAX_BYTES`).” |
| **S2** | **Strike** learning as landed fact. Prefer: “Design intent: has_new must not call read_conversation — **not** on hub until merge.” |
| **S4** | **Strike** “CONVERSATION_READ_MAX_BYTES=auto.TAIL…” as hub fact. Prefer: “peer-6 WIP only; hub `read_conversation` still full `read_text()`.” |
| **S6** | **Strike** Align `[x]` as complete. Prefer: reopen or demote until hub defines `CONVERSATION_READ_MAX_BYTES` / bounded `read_conversation`. |
| **S3** | Keep **UNKNOWN** until compression re-runs measurable probe with log path. |
| **S5/S7** | Keep; S7 does **not** close Active until hub land_proof. |

## Live probe excerpt (this cycle)

```
PROBES_OK
hub: turns = read_conversation(path) present; _HAS_NEW_ASSISTANT_MAX_BYTES absent; CONVERSATION_READ_MAX_BYTES absent
peer-6: _HAS_NEW_ASSISTANT_MAX_BYTES = 64 * 1024; CONVERSATION_READ_MAX_BYTES = auto.TAIL_READ_MAX_BYTES; has_new body uses tail_text_lines + reversed(lines)
hub_TAIL True (TAIL_READ_MAX_BYTES = 256 * 1024)
peer-6 git: M scripts/peer_transcript.py (uncommitted vs seed)
```

## Restamp (same cycle — overseer landed mid-audit)

_After initial FAIL probe, hub SoT gained `OVERSEER_SLIM_HAS_NEW_ASSISTANT_EOF_2026_09_04`. Re-read; do not keep stale FAIL._

| ID | Claim | Verdict (restamp) | Source | Evidence (one line) | Checked by |
|----|-------|-------------------|--------|---------------------|------------|
| S1′ | On peer wake (hub SoT), 64KiB reverse role scan replaces full/256KiB conversation parse in `has_new_assistant_since_dispatch` | **PASS** | hub `peer_transcript.py:458-511`; `HAS_NEW_ASSISTANT_SCAN_MAX_BYTES=64*1024`; land_proof True; `SlimHasNewAssistantEofTests` OK | `has_new` → `_last_conversation_role_eof` seek EOF 64KiB + reverse role walk; no `read_conversation(` in body. | fact_checker 2026-09-04 restamp |
| S2′ | `has_new` must not call `read_conversation` — **landed hub** | **PASS** | hub `:498-511`; unittest patches `read_conversation` → AssertionError | `test_assistant_tail_true_without_read_conversation` PASS. | fact_checker 2026-09-04 restamp |
| S3 | ΔRSS 1.203→0.172 MB | **UNKNOWN** (unchanged) | learning only | Still no probe log artifact. | — |
| S4 | `CONVERSATION_READ_MAX_BYTES=auto.TAIL…` on hub | **FAIL** (unchanged) | hub rg miss | Align path still unbound; `read_conversation` still full `read_text()`. | — |
| S5 | `TAIL_READ_MAX_BYTES=256KiB` | **PASS** (unchanged) | hub `:124` | — | — |
| S6 | Align conversation `[x]` / `CONVERSATION_READ_MAX_BYTES` | **FAIL OVERCLAIM** (unchanged) | hub `read_conversation:405-428` | Symbol still absent; full-file parse remains for prompt path. | — |
| S7 | peer-6 WIP shape | **PASS** (superseded) | peer-6 WIP + hub land | Hub land is SoT; peer-6 parallel WIP ok. | — |

### Strike update

| ID | Action |
|----|--------|
| **S1/S2** | Initial FAIL was correct **pre-land**; restamp **PASS** after `OVERSEER_SLIM_HAS_NEW_ASSISTANT_EOF_2026_09_04`. Active `[x]` with land_proof OK. |
| **S4/S6** | **Keep FAIL** — do not conflate slim has_new with Align/`CONVERSATION_READ_MAX_BYTES`. |

### Restamp probe

```
HAS_NEW_ASSISTANT_SCAN_MAX_BYTES 65536
has_new body calls read_conversation( → False
land_proof(slim item) → True
unittest SlimHasNewAssistantEofTests → Ran 3 OK
```

## Done self-check

1. Evidence paths read this cycle? Yes — hub pre-land FAIL + post-land restamp + peer-6 + Align.
2. Expected vs actual: S1′/S2′ PASS hub land; S4/S6 FAIL Align; S3 UNKNOWN; S5 PASS; queue slim `[x]` land_proof True.
3. Did not invent URLs; kit claims grounded in file:line + probe + unittest.
4. Did not orchestrate compression merge; ledger only (overseer landed slim SoT).
