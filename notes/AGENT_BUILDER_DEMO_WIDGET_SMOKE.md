# Agent Builder smoke — `demo_widget_sme`

Date: 2026-09-08 · Needle: `OVERSEER_AGENT_BUILDER_2026_09_07` · **NO PAY**

## Queue

No open Active WQ/SIC line for agent-builder smoke (already closed or absent). Queue **not** re-marked.

## Commands (exit 0)

| Step | Command | Result |
|------|---------|--------|
| Dry-run | `./scripts/peer agent-build --dry-run --spec notes/agent_builder_specs/example_demo_widget_sme.json` | `ok: true`, `role/template/match_action: updated`, `other_roles_untouched: true`, vault path present |
| Validate | `./scripts/peer agent-build-validate demo_widget_sme` | `validate ok: demo_widget_sme` |
| Who | `./scripts/peer agent-who "[demo-widget] fix tooltip copy"` | template+role `demo_widget_sme` (score 3.00) |

## Vault README

`notes/agent_vaults/demo_widget_sme/README.md` — title/id match; responsibilities + niche align with role; reads = `AGENT_WORKING_MEMORY` · `SOP_AGENT_BUILDER` · `AGENTS.md`.

## Live SoT

Role + template + match_rule already in `scripts/peer_tasks.json` (listed via `agent-build-list`). Dry-run only — no `--write`.
