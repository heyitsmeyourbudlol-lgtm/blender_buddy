# Overseer stagnation land 2026-09-04

- **healthy-idle dispatch clear** — `OVERSEER_HEALTHY_IDLE_DISPATCH_CLEAR_2026_09_04`; Active cleared + continue_on_dirty → dispatch 1.0; hub-protect restore watches factory_progress; factory 96%→100%.
- **worktree epilog soft** — `OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_2026_09_04`; self-check tip-only for `pass --execute`/`never uses --force`; factory 96%→99%.

- **worktree-epilog self-check** — `OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_SELF_CHECK_2026_09_04`; self-check soft-passes peer_worktree `(pass --execute…)` FAIL tails; restore live_bad requires epilog; factory 96%→99%.

- **skip-restart + healthy-idle wake** — `OVERSEER_IMPROVE_SKIP_RESTART_IF_ACTIVE` / `OVERSEER_HORIZON_SKIP_RESTART` / `OVERSEER_HEALTHY_IDLE_WAKE_CREDIT`; factory 91%→99%.

- **heal research daemon** — `OVERSEER_HEAL_RESEARCH_DAEMON` + demote research_stale on healthy idle; factory 88%→99%.
