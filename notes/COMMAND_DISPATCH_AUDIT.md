# Command dispatch audit

_Generated 2026-09-08T15:17:07Z_ · Needle `OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07`

**Status:** `improve` · peer/(peer+raw) ratio = **0.533**

| Signal | Hits |
|--------|------|
| pre-dispatch / plan-gate | 54 |
| post-cycle / done-gate | 4 |
| `./scripts/peer …` | 8 |
| raw `python3 scripts/` | 7 |

Agents should call ./scripts/peer pre-dispatch before spawn and post-cycle after land; prefer peer verbs over raw python3 scripts/.

```bash
./scripts/peer command-dispatch-audit
./scripts/peer pre-dispatch
./scripts/peer post-cycle
```

