# Rule catalog — topic → severity

_Updated 2026-09-06T13:33:36Z_ · inventoried by topic then severity · proposals use the same axes (`notes/SOP_TEMPORARY_RULE_SHUTDOWN.md`)

Agents: when proposing add/remove/modify/suspend, set `--topic` and `--severity` (or let infer run). Human review digests group the same way.

## Topic: `safety`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **critical** | `safety:hard_blocks` | notes/SAFETY_GATES.md | Hard blocks — never automate |
| **critical** | `safety:hitl_red` | notes/SAFETY_GATES.md | RED / HITL human-only |
| **high** | `safety:yellow_guards` | notes/SAFETY_GATES.md | Yellow — allowed with guards |
## Topic: `secrets`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **critical** | `secrets:no_local_export` | notes/PEN_TEST.md | Kit export — no local secrets |
## Topic: `cursor-rules`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **high** | `cursor:plan-to-peer-tasks` | .cursor/rules/plan-to-peer-tasks.mdc | Plan → peer tasks alwaysApply |
## Topic: `agents-prefs`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **critical** | `agents:no_pay` | AGENTS.md | No monetary payment — free desktop/CLEAN only |
| **medium** | `agents:never_solo` | AGENTS.md | Maximize parallel Task peers |
| **medium** | `agents:time_bomb` | AGENTS.md | TIME BOMB / crown strategy |
## Topic: `peer-orchestration`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **high** | `orch:phase_gates` | notes/PEER_ORCHESTRATION.md | Plan → Parallel → Safety → Verify → Merge |
## Topic: `queue-sync`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **high** | `queue:wq_context_sync` | notes/WORK_QUEUE.md | WORK_QUEUE ↔ self_improve_context identical |
## Topic: `verify`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **medium** | `verify:deferred_soft_skip` | notes/SOP_VERIFY_DEFERRED_SOFT_SKIP.md | Deferred soft-skip ≠ FAIL |
## Topic: `adapt`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **medium** | `adapt:heal_write` | scripts/automation_adapt.py | Adapt heal --write |
## Topic: `playbook`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **medium** | `playbook:error_lookup` | notes/AGENT_ERROR_PLAYBOOK.md | playbook-lookup before invent heal |
## Topic: `sop`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **medium** | `sop:rule_change` | notes/SOP_TEMPORARY_RULE_SHUTDOWN.md | Rule-change propose-only |
## Topic: `comms`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **low** | `comms:glink_codes` | notes/COMMS_HORIZON.md | GLink codes on hot path |
## Topic: `factory`

| Severity | Rule id | Ref | Summary |
|----------|---------|-----|---------|
| **low** | `factory:progress_meter` | notes/KIT_PROGRESS.md | Factory readiness meter |

## Commands

```bash
./scripts/peer rule-shutdown write-catalog
./scripts/peer rule-shutdown list --pending --by-topic
./scripts/peer rule-shutdown-digest
```
