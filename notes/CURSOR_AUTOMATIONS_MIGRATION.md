# Cursor Automations migration sketch

_As of 2026-09-07_ · Standings §4 · see `notes/FACTORY_PUBLIC_STANDINGS_TASKS.md` · [factory public standings](/Users/togi/.cursor/projects/Users-togi-Automation/canvases/factory-public-standings.canvas.tsx)

Public reference: [Cursor Automations / Cloud Agents](https://cursor.com/docs/cloud-agent/automations) — schedule or event wake (GitHub/GitLab/Slack/Linear/webhooks), cloud isolate, PR handoff, `/automate` setup skill.

## Constraint (kit)

**Prefer $0 local / free Cursor desktop.** Automations run as Cloud Agents (Max Mode billing). This doc is a **thinning map**, not a mandate to pay. Dual path:

| Path | When |
|------|------|
| **Local forever loop** (default) | Daily factory; free desktop; multi-repo hub on this machine |
| **Optional Automations** | Event/cron work that benefits from cloud isolate + PR defaults when you explicitly opt in |

## TODAY → TOMORROW → KEEP

```
TODAY:     WORK_QUEUE → peer_orchestrate → peer_loop (kqueue/LaunchAgent) → cursor-agent
TOMORROW:  WORK_QUEUE → Cursor Automations / native wake for dispatch slices
KEEP:      WORK_QUEUE semantics, verify gates, peer_tasks.json constraints, product “done,” taste
DROP:      transcript kqueue hack, prompt-file plumbing, daemon babysitting — when native is ~80%
```

Aligns with `notes/LOOP_STRATEGY.md` time bomb: crown is the loop; survival is outcomes + willingness to kill kit boilerplate.

## What Automations already cover

- Schedule / cron wake
- Source-control and chat/issue triggers
- Background agent in isolated cloud env
- Repo (or multi-repo) scope + PR-oriented handoff

## What they do not encode (your edge)

- Queue as source of truth + drift sync (`WORK_QUEUE` ↔ `self_improve_context`)
- Factory-shaped vs theater filters
- Done gates, noop backoff, self-heal playbooks
- Multi-project `automation_adapt` profiles + registry proof rules
- Free-desktop / no paid-API policy

## DROP list (when native ≥80%)

1. Custom transcript kqueue wake as the only trigger
2. Hand-built peer prompt file merge for generic “run agent” cases
3. Forever daemon as identity (“I’m the automation guy”) instead of adapter
4. Duplicate cloud-like isolate once Automations sandboxes are good enough for that slice

## Verb → Automation map (Phase 5)

Needle `OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07` · SoT verbs: `scripts/peer_commands.py`

| Peer verb (KEEP) | Suggested Automation trigger | Keep local? | Notes |
|------------------|------------------------------|-------------|--------|
| `bootstrap` / `heal-all` / `green` | Cron daily health (opt-in paid) | **Yes default** | Local LaunchAgent / CLEAN services |
| `pre-dispatch` / `post-cycle` | PR opened / agent session start | **Yes** | Must stay on hub before spawn |
| `standup` | Cron morning | Optional | Docs digest OK in cloud |
| `noop-break` / `stagnation-break` | Queue idle webhook | **Yes** | Needs live WORK_QUEUE |
| `commands-cycle` / `command-coverage` | Cron weekly | Optional | Command Builder harvest |
| `command-dispatch-audit` | Cron weekly | Optional | Compliance metric |
| `niche-assist-once` / `factory-dynamics` | Timer on CLEAN | **Yes** | Torch/GPU on brain host |
| `niche-mint` / `niche-mint-train` | Manual / escalate hint | **Yes** | Local-only models |
| `product` / `factory-sprint` | PR label / Linear | Dual | Proof lanes; verify stays native |
| `a-to-z` / `kit-run` | Cron / scheduled | Dual | Sequencing lock A→Z; local default until green |
| `progress` | Cron | Dual | Meter only |

**Rule:** Automations may **wake** the same verb; they must not redefine verify/done. When native wake ≥~80% for a row, drop duplicate daemon babysitting for that row only.

## Checklist (thin the kit)

1. [ ] Inventory wake sources in `peer_loop.py` (transcript, git, signal, timer)
2. [ ] Map each wake to Automations trigger **or** keep-local (label why)
3. [ ] Keep `WORK_QUEUE` + verify as the brain; never move “what done means” into a vague prompt
4. [ ] Pilot one non-critical cron Automation (docs digest / stale issue) — paid path opt-in only
5. [ ] Document dual-path in `AGENTS.md` (local default / Automations optional)
6. [ ] Delete or gate kqueue paths that only duplicate Automations triggers
7. [ ] Re-run standings: factory readiness must not depend on dead LaunchAgents alone
8. [ ] Exit criterion: daemon is optional adapter; queue+verify still ship without heroics

## Non-goals

- Replacing product verify with “Cloud Agent said LGTM”
- Forcing Max Mode spend to feel modern
- Competing with Devin on hosted ARR
