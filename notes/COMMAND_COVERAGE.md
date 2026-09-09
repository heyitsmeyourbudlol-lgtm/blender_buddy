# Command coverage

_Generated 2026-09-08T15:15:53Z_ · Needle `OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07`

Agents **execute** `./scripts/peer <id>`. Gaps = CLI scripts without a peer wrapper (rank by log hits). Plan: `notes/COMMAND_ECOSYSTEM_PLAN.md`.

## Snapshot

- CLI scripts: **125**
- Wrapped: **125**
- Unwrapped gaps: **0**
- Peer commands: **236** · compounds: **17**

## Layers

- **life** (69): `bootstrap`, `heal-all`, `green`, `install-all`, `standup`, `noop-break`, `stagnation-break`, `soft-hub-writeback`, `idle-gate`, `digest`, `oversight`, `oversight-force`, `oversight-digest`, `oversight-status`, `oversight-install`, `progress-monitor`, `progress-monitor-once`, `progress-monitor-force`, `progress-monitor-install`, `repo-research`, `repo-research-digest`, `repo-research-status`, `repo-research-install`, `pen-test`…
- **dispatch** (55): `pre-dispatch`, `post-cycle`, `plan-gate`, `done-gate`, `diagnose`, `diagnose-quick`, `hallucination-guard`, `hallucination-strategy`, `agent-gap`, `idea-articulate`, `idea-record`, `idea-synthesis`, `agent-gates`, `think`, `check-questions`, `precision`, `output-compare`, `learn`, `learn-record`, `lessons`, `lessons-harvest`, `lessons-squeeze`, `memory`, `memory-record`…
- **dev** (23): `commands-sync`, `commands-cycle`, `dev-fast`, `dev-heal`, `comms-improve`, `comms-improve-status`, `improve-plan`, `improve-run`, `improve-write`, `improve-status`, `improve-watch`, `trends`, `research`, `commands-md`, `commands-build`, `commands-harvest`, `command-coverage`, `coverage-gate`, `command-coverage-enqueue`, `command-ecosystem-finish`, `mini-app-promote`, `cursor-self-improve`, `improve-poll-cache`
- **factory-ai** (60): `progress`, `factory-a-plus`, `factory-a-plus-install`, `a-to-z`, `kit-run`, `kit-run-list`, `kit-heal-false-green`, `factory-a-plus-init`, `product-status`, `factory-sprint`, `factory-fanout`, `agents`, `niche-mint`, `plan`, `factory-dynamics`, `niche-bank-status`, `niche-bank-eval`, `niche-serve`, `niche-mint-train`, `top10`, `top10-refresh`, `top10-next`, `production-power`, `scoreboard-write`…
- **product** (6): `product`, `github-feedback-fetch`, `github-feedback-list`, `github-feedback-render`, `production-power`, `scoreboard-write`
- **meta** (10): `autonomous-repair`, `debrief`, `flaw-scan`, `flaw-scan-preview`, `comms-init`, `comms-bus`, `export-kit`, `commands-list`, `commands-digest`, `land-hold`
- **unlayered** (13): `check`, `test`, `test-quick`, `verify-gate`, `audit`, `audit-json`, `comms-verify`, `compact-queue`, `sync-queue`, `queue-status`, `adapt`, `adapt-deep`, `adapt-all`

## Top unwrapped gaps (by log hits)

_No gaps — all CLI scripts have a peer mapping (or none are CLI)._

## Harvest (Command Builder)

_No mechanical harvest gaps._

## Workflow

```bash
./scripts/peer command-coverage   # regenerate this doc
./scripts/peer commands-cycle     # wake Command Builder
./scripts/peer commands-list --pivotal
```

