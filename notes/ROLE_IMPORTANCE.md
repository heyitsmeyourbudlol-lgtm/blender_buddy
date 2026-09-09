# Role importance — replacement order

When the active dispatch pool is smaller than the full roster, rotation keeps every role participating. If you must **drop** a niche permanently, cut from the **bottom** of this list first.

**Policy:** `scripts/peer_roles.py` · config: `role_importance_order`, `pool_guaranteed_roles`, `pool_rotation`  
**DGX:** Most research/train niches set `prefer_remote: true` — Spark is the default compute plane (`mac-offloaded` + prefer_remote). Ceiling + live target: `automation_config._DGX_AGENTS_CAP_CEILING` (**96**).

## Guaranteed (always active when pool < roster)

1. Progress Monitor  
2. **Command Builder** — committed: other agents run `./scripts/peer`; this niche builds recipes  
3. Fact Checker  
4. BitNet Research Agent  
5. Compression Trainer  
6. Efficiency Research Agent  
7. Output Research Agent  
8. Research Speed Engineer  
9. DGX Ops  

## Ranked — cut from bottom first

| Rank | Role | Why it matters |
|------|------|----------------|
| 1 | Verify Runner | Hard gate — no trustworthy land without verify |
| 2 | **Command Builder** | Repetitive work → peer commands; kills shell theater |
| 3 | Fact Checker | Stops overclaims before train |
| 4 | Compression Trainer | T0–T4 / train rungs on Spark |
| 5 | BitNet Research Agent | Catalog + arch → recipe |
| 6 | Queue Steward | WORK_QUEUE ↔ context is shared brain |
| 7 | Factory Engineer | peer_loop, orchestrate, improve |
| 8 | Research Speed Engineer | Cuts research wall-clock to train |
| 9 | Niche Distiller | ~10M niche models |
| 10 | Adapt & Heal Specialist | Profiles, audit drift, self-heal |
| 11 | Safety Auditor | Veto before merge |
| 12 | DGX Ops | Keep Spark healthy / offload intact |
| 13 | OSS Integration Architect | External proof |
| 14 | Architecture / GPU / Serve / Dataset | Train-path specialists |
| 15 | Compression Engineer (RSS) | Daemon footprint |
| 16 | Communications Engineer | GLink at scale |

## Participation model

- **Active pool** — cursor-agent dispatch + worktree slot (size = `max_parallel_peers`, DGX target **24**)
- **Standby** — rotates via `pool_rotation`
- **Full roster** — **45** niches after `OVERSEER_DGX_ROSTER_EXPAND_2026_09_05`

```bash
./scripts/peer agents
python3 scripts/peer_orchestrate.py --self-check
```
