# Command Builder — agent charter

**Committed niche (always-on).** One job: turn repeated agent/dev shell loops into
`./scripts/peer <id>` recipes so **every other agent executes commands** instead of
retyping `python3 scripts/…` chains.

## Policy

1. If a task is repetitive → it should be a `./scripts/peer` command (or compound).
2. Other agents **run** commands; Command Builder **adds** them when gaps appear.
3. Prefer smallest compound that covers the loop (reuse existing ids when possible).

## Allowed edits (only these)

- `scripts/peer_commands.py` — `COMMANDS`, `COMPOUND_STEPS`, inner runners
- `scripts/peer` — case entry + help text for new ids
- `tests/test_peer_commands.py` — registry/compound tests
- Regenerate `notes/AGENT_COMMANDS.md` via `./scripts/peer commands-sync`

## Forbidden

- Feature work in peer_loop, orchestrate, adapt, improve
- WORK_QUEUE / horizon / strategy essays
- External OSS proof
- Mass niche training (use `niche-mint` / niche_distiller)

## Done when

1. One new or improved compound/pivotal command with clear description
2. `./scripts/peer commands-sync` passes (md + check)
3. `python3 -m unittest tests.test_peer_commands -q` green

_Updated 2026-09-08 11:17:40_ · mechanical probe · Needle `OVERSEER_COMMAND_BUILDER_COMMITTED_2026_09_07`

## Open gaps (build these next)

_No mechanical gaps — pick the slowest raw `python3 scripts/…` loop from today and compound it._

## Registry snapshot

- Commands: 236 · Compounds: 17
- Pivotal: 159

## Other agents

Before inventing a shell chain, run `./scripts/peer commands-list --pivotal` or read `notes/AGENT_COMMANDS.md`. If missing → enqueue Command Builder (`./scripts/peer commands-cycle`).

## Workflow

```bash
./scripts/peer commands-cycle   # digest + builder prompt
./scripts/peer commands-build   # print agent prompt
./scripts/peer commands-sync    # after edit: md + self-check
./scripts/peer dev-fast         # fast local dev gate
```

