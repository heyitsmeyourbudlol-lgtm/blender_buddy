# SOP — Agent remembrance protocol (main + Fact Librarian)

Owner: Factory Engineer / Tech Writer  
Needles: `OVERSEER_FACT_LIBRARIAN_2026_09_07` · `OVERSEER_LOSSLESS_MEMORY_COMPRESS_2026_09_07` · `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07`

## Model

| Role | Job | Does not |
|------|-----|----------|
| **Main agent** | Plan / edit / verify / DONE | Keep whole-repo or long chat as SoT |
| **Fact Librarian** | Scan compressed pack index + thin live SoT → compact relay | Edit code, mutate queue, paid APIs |

Chat truncates. Files + pack remember. Librarian relays **necessary facts only**.

## Domain SMEs

Route facts to one path-owner niche — see `notes/REPO_DOMAIN_SMES.md` · `notes/DOMAIN_OWNERS.md`.

```bash
./scripts/peer fact-domains
./scripts/peer domain-owners                 # regenerate DOMAIN_OWNERS.md
./scripts/peer fact-query --domain queue_sync "Active"
./scripts/peer fact-query "noop plan-gate"    # --auto picks peer_runtime
python3 scripts/peer_fact_librarian.py --threshold-status
python3 scripts/peer_fact_librarian.py --query "…" --agent   # librarian-only prompt (free desktop)
```

## When to invoke librarian

- Pack JSON ledger ≥ **512 KB** or file_count ≥ **200** (Hot / `--threshold-status`)
- Before large Plan / multi-file work without the needles in hand
- Anytime you are about to re-read "all of notes/"

## Always-read (main, every turn)

Open `notes/AGENT_WORKING_MEMORY.md` — paths only. Do not rely on chat memory.

## Lossless pack (additive archive)

- Artifact: `notes/memory_artifacts/repo_memory_pack.json.z`
- Compress/verify: `./scripts/peer memory-compress` · `memory-compress-verify`
- Heal/pre-dispatch pack gate (cheap): `./scripts/peer memory-pack-gate` (wired into `heal-all` / `pre-dispatch`)
- Role state: `./scripts/peer role-state`
- Domain classify stub: `./scripts/peer niche-domain-classify "…"`
- Board: `notes/TOP10_NEXT.md`
- **Never delete live SoT** because a pack exists — pack is density/archive only
- Details: `notes/SOP_LOSSLESS_MEMORY_COMPRESSION.md`

## Amnesia combat commands

| Verb | Purpose |
|------|---------|
| `session-ledger-append` | Write-through decision → `notes/session_ledger/YYYY-MM-DD.jsonl` before DONE |
| `session-distill` | Cited bullets → `PEER_CONVERSATION` / last_cycle pins |
| `session-claim` | OVERCLAIM-style session facts → `session_ledger/claims/` |
| `session-sticky-status` | Spaced sticky reinject counter (NO-PAY / factory-works / pack≠delete) |
| `session-hub-rules` | Hub SoT vs worktree scratch rules |
| `domain-owners` | Regenerate `notes/DOMAIN_OWNERS.md` |
| `memory-audit` | Flag uncited claims vs pack/SoT (mechanical) |
| `memory-quiz` | Anti-amnesia SoT needle quiz (fail → heal hint) |
| `memory-health` | Pack age / verify / prefer_librarian / Hot vs MEMORY_SPAN |
| `memory-pack-gate` | Cheap pack integrity (heal/pre-dispatch) |
| `memory-episodic` | Thin episodic jsonl by `cycle_id` |
| `role-state` | Thin role assignment/blocked/files/verify JSON |
| `niche-domain-classify` | Free-local NB domain classifier + keyword fallback |
| `plan-gate --read-ack PATH` | Read-ack + librarian-receipt soft→require when prefer_librarian |

```bash
./scripts/peer session-ledger-append --decision "…" --paths a,b --needle NEEDLE
./scripts/peer session-distill --target both --text $'- bullet `path:line`'
./scripts/peer session-claim --claim "verify green" --source "path:line"
./scripts/peer memory-audit --claim "WQ Active has 0 open"
./scripts/peer memory-quiz
./scripts/peer memory-health
./scripts/peer plan-gate --read-ack notes/AGENT_WORKING_MEMORY.md
```

Dashboard: `http://127.0.0.1:8765/api/memory-health` · panels on `/progress` and `/agents`.

Research checklist: `notes/AGENT_AMNESIA_RESEARCH.md`.

## TOP10_NEXT implementer

Durable role **`top10_implementer`** owns `notes/TOP10_NEXT.md` only — implement open items in rank order; `./scripts/peer top10` · `top10-refresh`. SOP: `notes/SOP_TOP10_NEXT.md`. Do not invent outside the list. Distinct from Newdrop `TOP10_PRODUCTION_POWER`.

## Hot memory contract

Harness injects:

1. Always-read path list + NO PAY sticky
2. Pack pointer (size/codec) when present
3. Librarian prefer flag + `fact-query` invoke line
4. Spaced sticky trio every N Hot refreshes (NO-PAY · factory-works · pack≠delete)

## Hub vs worktree

- **Hub SoT:** WQ twin, Hot/pack, `session_ledger/`, Always-read — never fork per worktree
- **Worktree OK:** ephemeral `notes/worktree_scratch/` only
- See `./scripts/peer session-hub-rules`

## Do not

- Stuff full pack JSON into the main prompt
- Spawn paid API librarian (`force_free_desktop_auth`)
- Treat librarian relay as license to skip Active WQ / verify gates
