# Agent mini apps — self-built tools

_Updated 2026-09-08 16:16:24_ · any agent · build when repetition beats manual work

**Mini apps** — build tools for yourself when needed (every agent):

You are allowed — and expected — to build **small single-purpose applications** when:
- You repeat the same manual steps **2+ cycles**, and
- No `./scripts/peer` command or existing script already solves it, and
- A ≤200-line script with `--help` + one test is faster than another essay.

**Not** a license for kit bloat — build the **smallest** app that removes your repetition.

**Mini app rules (non-negotiable):**

| Rule | Detail |
|------|--------|
| **Location** | `scripts/agent_tools/<snake_name>.py` only |
| **Interface** | `argparse` + `--help`; stdin/stdout friendly |
| **Size** | Target ≤200 lines; split if larger |
| **Deps** | Stdlib + existing repo imports — no new pip deps without Safety |
| **Secrets** | Never embed tokens; env vars only |
| **Test** | `tests/test_agent_tools_<name>.py` or row in `tests/test_agent_tools.py` |
| **Register** | `./scripts/peer mini-apps --register --name X --purpose "..."` |
| **Promote** | Team repeats it → Command Builder adds `./scripts/peer` compound |

## Build when

1. Same grep/diff/measure loop appeared twice in your debrief or GLink notes.
2. Expected-vs-actual compare needs a niche-specific formatter (build on peer_output_compare).
3. You need a read-only probe (status, tail, count) before you can pinpoint a fix.
4. Command Builder backlog is full but **you** need the tool **this cycle** in your niche scope.

## Do not build when

1. One-off task — inline shell is enough.
2. A peer compound already exists — use `./scripts/peer commands-list --pivotal`.
3. The app would edit queue, strategy, or cross-niche orchestration (wrong persona).
4. No test and no `--help` — that is a scratch script, not a mini app.

## Workflow

```bash
./scripts/peer mini-apps --scaffold --name diff_tail --purpose "Compare log tails"
python3 scripts/agent_tools/diff_tail.py --help
./scripts/peer mini-apps --register --name diff_tail --role verify_runner --purpose "..."
python3 -m unittest tests.test_agent_tools_diff_tail -q  # add test
# Team repeats it → Command Builder → ./scripts/peer commands-sync
```

## Registered apps

- _No registered mini apps yet — build when repetition hurts._


## Niche examples

### Adapt Specialist
- Mini app: diff adapt audit JSON between two runs.

### Command Builder
- Promote proven agent_tools scripts to peer_commands compounds.

### Communications Engineer
- Mini app: byte count on vault summary hot path.

### Compression Engineer
- Mini app: RSS delta from two ram-status snapshots.

### Factory Engineer
- Mini app: dispatch timeline from peer-loop-status + bus tail.

### Orchestrator
- Do not build mini apps in Plan — assign niche peer to build in their scope.

### Queue Steward
- Mini app: WORK_QUEUE ↔ self_improve_context line diff.

### Verify Runner
- Mini app: parse first failing test line from unittest output.
- Mini app: flake classifier (env vs code) from two run captures.
