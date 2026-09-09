# Agent survival — what will happen to you

_Read every cycle. You will hit these. Do not rediscover them from zero._

This is the kit’s **hazard map**: stalls, chicken-eggs, false labels, and the mechanical exit for each. Full recipes: `notes/AGENT_ERROR_PLAYBOOK.md` · `./scripts/peer playbook-lookup "<symptom>"`.

## Stance

1. **Assume the loop will try to idle you** — plan-gate fail, soft warn, verify_ok=false, quiet peer, namespace flip, oversight down.
2. **Assume labels lie** — `adapt_stale` often means queue drift; `verify_ok=false` often means cursor-agent non-zero, not a red tree.
3. **Heal → clear gate → land one executable diff** — never essay while primary is skipped.
4. **Never enqueue raw CLI/self-check output** into WORK_QUEUE (truncated “✗ tests not ok…” lines forever-block Institutional memory).

## Hazard table

| What you will see | What it actually is | Do this |
|-------------------|---------------------|---------|
| `plan-gate BLOCKED` / `skip primary` | Episodic / Self-correction / Institutional hard-fail | `./scripts/peer sync-queue` → `./scripts/peer adapt` → `./scripts/peer heal-all` → `./scripts/peer poke`. Soft warns = **keep working**. |
| `verify_ok=false` + note `cursor-agent non-zero` | Agent exit, not necessarily tests red | Re-run `./scripts/peer test-quick` / verify-gate. Soft Episodic — **do not freeze**. Fix real FAIL lines only. |
| `ADAPT_STALE` / `should_re_adapt` | Fingerprint vs dirty tree **or** mislabeled queue drift | `./scripts/peer adapt` + `sync_notes_only_fingerprint` path. Queue errors are **not** adapt_state — `./scripts/peer sync-queue`. |
| Queue drift that heal cannot clear | Corrupt Active line (truncated self-check / FAIL paste) | **Delete** the junk Active line; sync both files. Never paste verify stdout into queue titles. |
| `verify quiet` always “quiet” under full swarm | Old bug: agent cap = `max_parallel_agent_procs` | Cap is `verify_quiet_max_agents` (0–2). Do not “fix” by raising dispatch cap. |
| Peer log silent >3 min, poke no-op | Event wait / hung forever loop | `launchctl kickstart -k gui/$(id -u)/com.togi.<ns>-peer-loop` (+ improve/oversight if missing). |
| Oversight missing after “everything fine” | `config_namespace` flipped `automation` ↔ `automation-hub` | Reinstall matching label: `python3 scripts/peer_oversight.py --install`. Check `automation.config.json` + local overlay. |
| Improve “not 24/7” | LaunchAgent stopped or wrong namespace | `./scripts/peer improve-install` / `cmd_install(force=True)`; confirm KeepAlive + `--forever --daemon --write --research`. |
| Dirty tree / notes-only porcelain | Notes writes look like adapt churn | Fingerprint **ignores notes/**; verify calls `sync_notes_only_fingerprint`. Don’t treat notes-only dirty as prove-red. |
| Self-correction “Verify gate FAIL” soft warn | Diagnose high finding while dispatch must continue | Soft — dispatch to clear. Hard block only for Secret hygiene. |
| Niche agent `rc=255` / non-zero | One worker died; loop must continue | Playbook + heal; **do not** mark whole factory dead. Re-dispatch that niche if item still open. |
| Dual log / dual LaunchAgent | Hub vs non-hub labels both loaded | Prefer canonical `config_namespace` agents; bootout rogues. |
| HITL / human-only queue | Autonomy mode | `hitl_enabled=false` — execute when gates/creds exist; secrets stay mechanical. |

## Chicken-eggs (never sit idle)

```
verify_ok=false ──► plan-gate Episodic fail ──► skip primary ──► nobody fixes verify
adapt_stale      ──► verify fail              ──► same deadlock
queue drift      ──► labeled adapt_stale      ──► heal runs adapt not sync-queue
```

**Break:** soft gate for recoverable stalls + mechanical error-adapt + one real verify seed. Your job when you see the loop: **clear the chicken-egg**, then do the assigned niche work.

## Pre-flight (10 seconds)

```bash
./scripts/peer plan-gate --role <your_role>   # soft warn OK; hard fail → heal first
./scripts/peer playbook-lookup "<last error>"
./scripts/peer diagnose                       # optional when verify_ok=false
```

## Post-land

```bash
./scripts/peer test-quick    # or verify-gate
./scripts/peer sync-queue    # both files identical
./scripts/peer learn-record --role <you> --text "<trap you hit>"
```

## Never do

- Paste self-check / unittest stdout into WORK_QUEUE Active lines.
- Edit only WORK_QUEUE or only `self_improve_context.md`.
- Treat soft Self-correction / agent-exit Episodic as “stop all work”.
- Raise `max_parallel_agent_procs` to “fix” verify quiet-wait.
- Ignore oversight/improve LaunchAgent death when namespace flips.

## Meter that matters

Automation loop health = **commits after real verify**, **queue_fp advance**, **plan-gate not hard-blocked**, **peer+improve+oversight alive**. Not product theater unless the assignment says so.
