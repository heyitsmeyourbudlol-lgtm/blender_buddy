# Peer orchestration — speed × intelligence

## Objective

**Intersection of speed and intelligence:** parallel specialized agents, single orchestrator merge, safety never traded for MB.

- **Maximize parallel Task peers** — getting to the goal means utilizing as many subagents / parallel Tasks as scopes allow (split aggressively; never collapse independent scopes into one hero agent).

## Prompt shape (orchestrator sends this)

When `peer_orchestrate.py` runs, it emits **phase gates**:

1. **Plan / Orchestrate** — brief, queue, disjoint scopes
2. **Parallel Implement** — Peer A..N in ONE Task message (**maximize parallel Task peers**; split scopes aggressively)
3. **Safety** — when yellow/red (or Safety peer present); veto before merge
4. **Verify** — commands must PASS before merge
5. **Merge** — sync WORK_QUEUE ↔ self_improve_context; memory pointers in peer `reads`

## Execution (Cursor)

```
Orchestrator (phase gates):
  1. Plan — read notes/WORK_QUEUE.md + emitted prompt
  2. Parallel Implement — Task × N in ONE message (maximize peers; full impl set together):
       - Reclaim / Footprint / … scoped implementation
  3. Safety — review impl scopes against SAFETY_GATES.md (when needed)
  4. Verify — unittest + footprint; gate merge
  5. Merge — fix Safety BLOCKs; re-Verify if needed; update WORK_QUEUE + self_improve_context.md
```

## CLI

```bash
# Build peer prompt (stdout)
python3 scripts/peer_orchestrate.py --dry-run

# JSON task plan for tooling
python3 scripts/peer_orchestrate.py --json

# Clipboard + optional Cursor paste
python3 scripts/cursor_self_improve.py --peer
./scripts/peer-dispatch              # --dry-run | --clipboard-only
```

## Task assignment rules

1. **Disjoint scopes** — no two peers edit the same file in the same cycle
2. **Safety reads code** — does not edit until Reclaim produces a diff (or reviews planned paths pre-implementation for yellow tier)
3. **Footprint never touches reclaim logic** in the same files as Reclaim
4. **Verify only runs commands** — no edits

## Stop condition

**Blocking done:** queue empty + tests pass + git clean + import RSS &lt;budget MB → `## Status: complete` (archival).

**Loop done:** only when `## Loop: exhausted` in `self_improve_context.md` **and** metrics green — literally no non-obvious compress-in-place wins left.

**Peer loop** (default with `--peer`):

1. Creative backlog + `CREATIVE_BACKLOG.md` experiments (clever first)
2. Active WORK_QUEUE / context remaining (obvious)
3. Metric fixes (tests/RSS)
4. Idea mining — discover ≥3 new experiments; implement best one
5. Repeat until `## Loop: exhausted`

```bash
python3 scripts/cursor_self_improve.py --peer          # loop on (default)
python3 scripts/cursor_self_improve.py --peer --no-loop  # legacy stop
python3 scripts/peer_orchestrate.py --dry-run --loop
```

## Expand working memory

Add a new `notes/<topic>.md` when:

- A module gets non-obvious guards (link from WORK_QUEUE item)
- A peer repeats the same mistake (add to SELF_IMPROVE_RUBRIC)
- A new reclaim path is added (update RAM_VALUE_STACK + SAFETY_GATES)

Keep each note **&lt;80 lines**; split rather than grow one doc.
