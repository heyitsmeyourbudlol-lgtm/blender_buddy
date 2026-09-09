# GitHub + IDE support (factory track)

_Human ask 2026-09-07_ · Gravity Newdrop + Automation Hub · UI guardrail: no UI unless flaw

## Goal

Use the factory to deepen **dev-native** ship paths:

1. **GitHub** — App webhook / install / sync reliability (Connect GitHub → CHANGELOG → What’s New).
2. **IDE** — Cursor/agents/MCP/CLI write path stays automatic; hub peers get first-class `gh` + feedback verbs.

Canonical Newdrop DX: `CaaS/docs/playbooks/DEV_DX_PLAN.md` (Wave 0–2 done; Wave 3 demand-gated — prefer harden over new surface).

## Factory Active (executable)

| Track | Done when |
|-------|-----------|
| Newdrop GitHub harden | **done** — [#26](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/26) `0df1f28` |
| Newdrop IDE ingest | **done** — same PR (`.cursor` / `docs` / `.github` changelog paths) |
| Hub IDE/GitHub DX | **done** — `github-feedback-*` + `production-power`/`scoreboard-write`; AGENTS tip |

### Hub peer verbs

```bash
./scripts/peer github-feedback-fetch    # pull open feedback/bug issues → sanitized inbox
./scripts/peer github-feedback-list     # inbox summary
./scripts/peer github-feedback-render   # markdown for peer review (stdout)
./scripts/peer production-power         # write notes/PRODUCTION_POWER_SCOREBOARD.md
./scripts/peer scoreboard-write         # alias of production-power
```

Registry: `scripts/peer_commands.py` · full list: `notes/AGENT_COMMANDS.md` · product gravity: `notes/HUB_PEER_VERBS.md`.

## Non-goals

- Wave 3 Marketplace / VS Code extension / uniqueness theater
- Dashboard redesign
- Paid Cursor Automations by default

## Verify

- Newdrop: `npm test` + `check:controls`
- Hub: `python3 scripts/peer_orchestrate.py --self-check`

### Closeout (2026-09-08)

- PR [#26](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/26) **MERGED** `0df1f28`
- Mac `/Users/togi/CaaS` main: `npm test` **356 PASS** · `check:controls` **13ok** · UI untouched · NO PAY
- Active `[top10] Newdrop GitHub+IDE support track` → **WORKER-DONE**
