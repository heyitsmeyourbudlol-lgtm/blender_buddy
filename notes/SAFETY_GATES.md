# Safety gates — no harm without full mitigation

Goal: **maximize RAM value** only when mitigations reduce risk to acceptable.

## Hard blocks (never automate)

| Action | Why | Enforcement |
|--------|-----|-------------|
| Quit / kill **Cursor** | User closes agent IDE | `HARD_NEVER`, `experience.is_agent_app()` |
| Auto-quit apps or tabs | Consent model | `require_permission_to_close` — picker/Gauge only |
| E-core demote **browsers** | Stutter on tab switch | `never_demote_browsers` |
| E-core demote **media** | Playback stutter | `never_demote_music` |
| Freeze tab with unsaved work | Data loss | Chrome presence + dirty detection |
| Jetsam / SIGSTOP frontmost | UX break | `only_background`, front guards |

If a task requires any of the above → **STOP** or redesign to user-initiated only.

## Yellow — allowed with guards

| Action | Risk | Required mitigation |
|--------|------|---------------------|
| Page sweep / dylib invalidate | Crash if wrong VM region | Skip executable; sudo only; skip self PID; experience + game defer |
| Locality demote | Slow resume | Never front, Cursor, browsers, media; restore on focus |
| Chrome tab freeze | Lost scroll/state | `thaw.html` self-restore; learned return time; AFK path |
| WKdm / compact / purge | System churn | Battery defer; dry_run default; `should_purge` safety |
| Idle wire-budget throttle | Sysctl churn / wake hitch | AFK≥90s + warn; browsers left frontmost only; restore on focus (+ hold ticks); never Cursor; never E-core demote browsers |
| Presence file-cache mark | Crash if wrong region | File-backed only; skip executable; presence gate + idle floor; game defer |
| Idle shared-cache advise | Crash if wrong dyld region | Path filter dyld/shared_cache only; skip browsers/media/Cursor; presence + idle floor; game defer |
| Jetsam soft hint | UX interrupt | Critical+AFK only; picker consent; never auto-quit; overflow cooldown shared; rising-RSS filter before picker |
| XPC diet (presence) | Kill wrong helper / wake hitch | launchctl proxies only (host untouched); presence + AFK; skip Cursor/browsers/media; `only_background` + workload protect |
| Compress-stagger skip-recent | Miss reclaim / wake hitch | Skip apps hit by wire-budget (same tick) / file-cache/shared-cache (prior tick); clear hits **after** stagger, never before; critical processes all |
| Mach IPC choked purge | Lost queued messages | `purge_choked_at_critical` only; `only_background` + idle; dead names at warn |
| Coalition duplicate invalidate | Crash if wrong VM region | AFK-only on warn (`duplicate_invalidate_afk_only_on_warn`); skip executable; idle threshold |
| Electron CDP discard | Tab reload | Only idle background; consent for relaunch |

Peer **Safety** must confirm guards exist in code before **Reclaim** merges.

## Green — safe to parallelize

- Lazy imports, slim status, snapshot-only Gauge reads
- Config externalization, pass-runner refactors (behavior-preserving)
- Tests, footprint RSS checks, docs/notes updates
- Telemetry (`ram status`, metrics only)

## Pre-merge checklist (Safety peer)

```
[ ] No new auto-quit / auto-close paths
[ ] Cursor still in HARD_NEVER + is_agent_app blocks
[ ] Browsers/media still never_demote_*
[ ] Game session defer unchanged for visual/heavy passes
[ ] dry_run respected where config says so
[ ] tests/test_ram_core.py + test_ram_footprint.py pass
```

If any box fails → fix mitigation first, then continue.
