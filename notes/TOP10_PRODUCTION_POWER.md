# Top 10 indie production power (90 days)

_Canonical plan · started 2026-09-07_ · Tasks: [TOP10_PRODUCTION_POWER_TASKS.md](TOP10_PRODUCTION_POWER_TASKS.md) · Scoreboard: [PRODUCTION_POWER_SCOREBOARD.md](PRODUCTION_POWER_SCOREBOARD.md) · Gravity: [HUB_GRAVITY_CHOICE.md](HUB_GRAVITY_CHOICE.md) (Newdrop)

## Target

**Top 10 among indie/solo autonomous factories** by **production power**: sustained irreversible Newdrop lands per week + unattended CLEAN uptime.

**Non-goals:** Devin/Cursor-fleet volume under free-desktop lock; kit LOC; niche-stamp theater; ASI %.

## Scoreboard bars (90d)

| Metric | Bar |
|--------|-----|
| Newdrop merged PRs / week | ≥3 meaningful |
| Non-noop cycles / day (Active nonempty) | ≥8 |
| CLEAN peer+improve uptime | ≥95% of days |
| Kit-theater Active share | ≤10% |
| External proof | ≥1 merged product PR / month |

Update weekly: `python3 scripts/production_power_scoreboard.py --write`

## Queue policy (hard)

**Active = Newdrop production + factory uptime only.**

Demote to Backlog unless it unblocks a Newdrop land this week:

- niche-distill stamp runners
- compression / BitNet research as Active
- research-speed fanout theater
- kit polish without a Newdrop PR in the done definition

Cycle **done** = PR opened or merged on Newdrop (`/Users/togi/CaaS`), not a hub needle.

### Newdrop product guardrails (human)

- **Do not change UI** unless a real flaw is detected (broken a11y, layout bug, security leak in the surface, broken CTA). Prefer backend/verify/security/ops lands.
- Prefer remove chrome only when fixing a flaw — no drive-by redesign, support-page restyles, or “elegant statue” polish as Active theater.
- Always verify: `npm test` + `check:controls` before merge.

## Full free capacity

- Brain: **CLEAN** under `mac-offloaded` (do not re-enable Mac peer/improve).
- Dispatch cap: `max_parallel_agent_procs` = **measured free-desktop concurrent max** (see scoreboard / config), not phantom 96.
- Worktree pool may stay large; **agents dispatched** must match free-desktop reality.

## Phases

0. Lock scoreboard + Newdrop-only Active (this doc)  
1. Saturate free agents on Newdrop verify→PR  
2. Cadence + distribution wedge  
3. 4-week streak + public [FACTORY_PROOF.md](FACTORY_PROOF.md)

## Freeze

Kit features that do not raise Newdrop merges/week are **frozen** until scoreboard bars hold 4 consecutive weeks.
