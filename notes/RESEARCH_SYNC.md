# Research sync — team handoff

_Updated 2026-09-08 15:26:30_ · both lanes · dispatched=False

> **For:** peer orchestrator, cursor-agent, automation_improve, full 8-worker team.
> Efficiency + output research run **synchronously** each cycle.

## Efficiency lane (speed × yield)

- **[done]** Hub+peer CLEAR_DELAYS_LITE_STATE + WAKE_NO_COLD_IMPROVE (L135) — clean clear **13.47→0.048ms** (~**278×**); tx/improve **False**; EXPECTED `0fc1060e…`
- **[done]** Hub+peer SCAN_LIVE_ERROR_HITS_CTX_SKIP_DISK (confirm L135) — ctx MISS **0.023ms** vs disk **0.835ms** (~**36×**); `_log_tail` seek **0.035ms** (OLD read_text **214.8ms**) — residual closed
- **[done]** Hub+peer SCAN_LIVE_ERROR_HITS_TAIL_64K (L134) — MISS remiss **~0.99–1.6ms→0.791ms** (improve append defeats mtime HIT); tip EXPECTED peer `87d6b9d7…` hub `d93c5fd4…`
- **[done]** Hub+peer SCAN_LIVE_ERROR_HITS_MTIME_MEMO (L133) — remiss HIT med **0.014ms** (MISS **3.06ms**; OLD read_text **233.7ms**); unittest `test_scan_live_error_hits_mtime_memo_skips_reseek`
- **[done]** Hub+peer SCAN_LIVE_ERROR_HITS_SEEK_TAIL (L132) — green verify_ok cooldown scan hub **218.5→1.60ms** (~**136×**); no `Path.read_text`
- **[done]** Hub+peer QUEUE_FP_LITE_DRY_PROJECT_AUTOMATION (L131) — auto SoT lite med **0.035ms**; tx/improve/peer_loop parity **True**; tip EXPECTED hub `50177507…`
- **[done]** Peer-1 COMPACT_SKIP_MET_TRANSCRIPT_NO_OPEN (L130) — cold compact **18.6→4.4ms**; tx/wt **False** (L127 was peer-coding only; peer-1 still paid)
- **[info]** Next residual — optional `peer_oversight` kevent `scan_live_error_hits` without ctx (MISS ~0.8ms on log write; mtime HIT already 0.016ms)
- **[done]** Hub+peer VERIFY_COOLDOWN_BYPASS_NO_TX_IMPORT (L129) — cold **5.39→0.079ms** (~**68×**); HIT **0.002ms**; tx_in=**False**; tip EXPECTED `89249682…`
- **[done]** Hub+peer PRE_DISPATCH_NOOP_CLEAR_LITE_FP (L129) — pre-dispatch noop-clear cold **~13.3→0.384ms**; tx_in=**False**; peer-1 blind-clear fixed; EXPECTED `93b27288…`
- **[done]** Hub+peer NOOP_CLEAR_FP_NO_TX_IMPORT (L128) — improve noop-clear lite fp **~16.8→0.45ms** (~**37×**); tx_in=**False**; tip EXPECTED `ff0607d2…`
- **[done]** Hub+peer-coding COMPACT_SKIP_MET_TRANSCRIPT_NO_OPEN (L127) — remiss **~7.1→~6.4ms**; cold MET **~13ms→0** (peer-1 port = L130)
- **[done]** Hub `wake_peer` WAKE_PEER_NO_COLD_TEAM_TX_IMPORT (L126) — cold wake **~89→~0.05ms**; team/tx **False**
- **[done]** Hub RANK_TEAM_STATUS_LITE + CACHE + TEAM_STATUS_SKIP_PORCELAIN (L125) — rank_team **90.6→HIT 0.032ms**; rank_opportunities MISS **76→6.2ms**
- **[done]** Hub+peer RANK_KEY_NO_TEAM_COLD_IMPORT + `_team_rank_mtime_fp` (L123) — remiss_drop_team **~1.4–1.65ms→0.031ms**; team_in=**False**; tip EXPECTED `ad2bc7bd…`
- **[done]** Hub RANK_MERGE_NO_DUAL_IMPORT + `_dual_findings_mtime_fp` (L122) — cold merge **73.4→4.5ms** / HIT **0.046ms**; rank_key **9.5→1.65ms**; dual_in=**False**; tip EXPECTED `51285046…`
- **[done]** Hub GATHER_ADAPT_AUDIT_GEN_TTL (L121) — audit MISS **11.36→HIT 0.217ms** (~**52×**); gather remiss **110→7ms**; dual skip now receives `audit_cache_hit`
- **[done]** Hub find_latest ROOT_FP gen confirmed (L121 probe) — past-TTL **0.089ms** scans=**0**
- **[done]** Hub DUAL_GATHER_SKIP_ON_AUDIT_HIT + COOLDOWN_DISK_BRIEF (L120) — audit_hit **0.009ms**; cooldown brief **0.04ms** (was force **~280–315ms**); tip `3ee5b4d9…`
- **[done]** Hub SKIP_POST_WAIT find_latest+measure on timeout/fallback (L119) — cold remiss **~32ms→0**; gate **0.0024ms**; hub-protect+golden synced
- **[done]** Hub+peer QUEUE_KNOWN_KEYS_MD_INDEX + CONTENT_FP (L118) — cold miss → `queue_md_known_keys`; GEN HIT **~0.005ms**; CONTENT_FP remiss **~0.015ms** scans=**0** (~**130×**)
- **[done]** Hub+peer QUEUE_KNOWN_KEYS_CONTENT_FP + hub GENERATION re-land (L117) — peer remiss_after_touch **2.03→0.049ms**; hub always-scan **~3.7ms→HIT 0.007ms** / remiss **0.070ms**
- **[done]** Hub+peer SOFT_REFRESH_DEFER_WARM_GATHER_DAEMON_UP + SKIP_WHEN_HORIZON_FRESH (L116) — daemon-up **~70ms→0.004ms**; fresh remiss **~22–54ms→0.08ms** gather=**0**; `HORIZON_STALE_SEC=900` shared with scan
- **[done]** Hub+peer ASI_DAEMON_PROBE_TTL_WAKE_FLOOR (L115) — age30.5 daemon probe HIT **0.004ms** (eff=35); shares heal SoT
- **[done]** Hub+peer PROBE_TTL_WAKE_FLOOR (L114) — wake-boundary scan **~10–33ms→0.009ms** (~**1150×**); effective TTL=wake+5 (**35s** when wake=30)
- **[done]** Hub+peer PROC_LAZY_RSS_BALLAST_NEEDLES (L113) — /proc walk med **~4.35→~2.62ms**; cold scan **~41–58→~32.6ms**; status opens **1** (ballast only)
- **[done]** Hub+peer PROGRESS_FP_HEAD_GEN_CACHE (L112) — warm remiss git shells **1→0**; HIT **~0.08–0.21ms** (~**15–40×** vs ~3ms rev-parse)
- **[done]** Hub+peer HEAL_IMPROVE_DARWIN_NO_COLD_IMPROVE_IMPORT (L111) — Darwin kickstart-ok **~0.5–0.9ms** / improve unloaded (~14–80ms cold import→0); lazy install_fn only
- **[done]** Hub+peer SOFT_REFRESH_NO_COLD_IMPROVE_IMPORT (L109) — cold soft_refresh **~250ms→0.001ms**; wake writes when improve unloaded
- **[done]** Hub+peer PROGRESS_FP_SHARE_PS_AXO + NO_TRANSCRIPT (L110) — warm fp **~27.6→~2.2ms** (~**12×**); ps -u **0**; cold transcript **0**
- **[done]** Hub+peer SCAN_ADAPT_FP_GEN_CACHE (L108/L108b/L108c) — lite fp miss **~12–14ms**/2 shells → HIT **~0.024ms**/0 (~**560×**); clear_scan NameError fixed; hub+protect synced; unittest pins gen vs index churn
- **[done]** Hub+peer SNAPSHOT_FACTORY_SKIP_SCAN + SNAPSHOT_LAST_CYCLE_NO_TRANSCRIPT (L107) — ops miss med **~0.9ms**; scan/tx **0**
- **[done]** Hub+peer HUB_PROTECT_PAUSE_NO_LAND_HOLD_IMPORT (L106) — clear pause **~7→0.27ms**; cold scan `peer_land_hold` **0**
- **[done]** Hub+peer SCAN_ADAPT_NO_COLD_IMPORT + SCAN_POISON_NO_TRANSCRIPT (L104) — cold scan **~72→~19ms**; no adapt/transcript import
- **[done]** Hub+peer EFFICIENCY_SNAPSHOT_OPS_ONLY (L103) — miss format cold **~60.6ms** / warm **~0.24ms** vs full **~224ms**; `build_team_context` not on miss
- **[done]** Hub+peer RANK_MERGE_NO_DUAL_IMPORT (L102) — rank merge **~17.7→~2.4ms**; no `peer_dual_research` import; disk JSON parity
- **[done]** Hub+peer FACTORY_STATE_SCRUB_POISON_LIGHT + LINUX_NO_DGX_IMPORT (L101) — `_load_state` **~75→0.60ms**; Linux dgx_watch **0**
- **[done]** Hub+peer ASI_PROBE_CTX_NO_IMPROVE_IMPORT (L100) — `_probe_ctx` **0.187ms** (~**61×** vs import **11.44ms**); improve stays unloaded
- **[done]** Hub+peer COMPACT_SKIP_DAEMON_SNAP (L99) — open-marker gate; live snaps **2→0**; needed path **2→1** (~**4.8ms**/snap)
- **[done]** Hub+peer PROC_SNAPSHOT_REPLACE_PS_AXO (L98) — Linux cold scan **ps shells 1→0**; snapshot **~6.9ms** (was **~23–40ms**)
- **[done]** Hub+peer IMPROVE_LABEL_NO_IMPORT (L97) — dual_ns cold **~19→0.79ms**; no automation_improve import
- **[done]** Hub+peer ASI_SHARE_SYSTEMD_IS_ACTIVE_BATCH (L96) — ASI/factory peer+improve **2→1** is-active (~16→11ms); **0** after heal warm
- **[done]** Hub+peer PS_AXO_RSS_SHARE_BALLAST (L93) — cold scan **2×ps→1**; total **~172→~80ms**; subs **7→2**
- **[done]** Hub+peer SYSTEMD_IS_ACTIVE_BATCH (L92) — is-active **5→1** (durable TTL; supersedes PREFETCH)
- **[done]** Hub+peer L94/L95 confirm — cold shells=**2** (batch+axo-rss); ps_u=0; remiss body **~2ms**
- **[done]** Hub+peer LOG_HAS_RECENT_ANY_MTIME_MEMO (L91) — remiss wake-credit **0.553→0.0025ms** (~**219×**); tail re-seek **0** on mtime HIT
- **[done]** Hub+peer IMPROVE_LOG Path.home correctness (L90) — prefers-freshest mock green; cold **0.118ms**; Path.__eq__ **0**
- **[done]** Hub+peer IMPROVE_LOG_PATH_BOUNDED_PEERS (L89) — miss **~1.6ms → ~0.025ms** (~**64×**); no ~/.config scandir
- **[done]** Hub+peer IMPROVE_LOG_PATH_CANDIDATE_STRSET + BOUNDED_PEERS (L88) — Path.__eq__ **1384→0**; scandir **0**; cold **1.172→0.154ms** (~**7.6×**)
- **[done]** Hub+peer FOREVER_PYTHON_PS_AXO_TTL (L88) — 4× `ps -axo` → **1** within TTL (was ~56.8ms shell tax on job_stopped / scan remiss)
- **[done]** Peer-1 L85 port (L87) — clear_factory keep improve-log TTL; registry mtime memo; remiss improve_log **~2.0ms→0.0008ms**; remiss tick **~3.0→~0.5ms**
- **[done]** Hub+peer MAC_OFFLOADED_TTL (L86) — MISS **2.24ms** → HIT **0.00019ms** (~**11800×**)
- **[done]** Hub+peer OPEN_AND_DONE_QUEUE_MD_INDEX_SHARE (L84) — mtime HIT **0.0025ms** (~**32×**)
- **[done]** Hub REGISTRY_STATS_MTIME_MEMO + FACTORY_CLEAR_KEEP_IMPROVE_LOG_TTL (L85) — registry HIT **0.003ms** (~**25×**); peer-1 re-landed L87
- **[done]** Hub+peer GIT_HEAD_REF_PACKED_REFS (L83) — past-hard soft HIT **0.137ms** / snap=0 vs raw **4.23ms** (~**31×**)
- **[done]** Hub PEER_TRANSCRIPT_ROOT_SHIM (L82) — cwd past_ttl **55.91→0.581ms** (~**96×**)
- **[done]** Hub GIT_SOFT_DIRTY_HEAD_ONLY (L80) — past-hard soft HIT **0.072ms** vs raw snap **12ms** (~**167×**); residual was packed-refs on peer-N

## Output lane (monster factory)

- **[info]** Fifteenth kit-run CyberActivity MERGED PR #1 `2b24eb7` — next residual HumanTyper deferred self_sufficient Backlog
- **[medium]** Factory progress below self-sufficient target — ./scripts/peer progress

## Executable enqueue (improve + peer)

- (none this cycle)

## Team instructions

1. **Orchestrator** — read this file + lane digests before Phase 1 Plan.
2. **Factory Engineer** — implement efficiency findings (hot path, queue, pre-dispatch).
3. **OSS Integration Architect** — implement output findings (external proof, PR).
4. **Queue Steward** — ensure enqueued `[efficiency-research]` / `[output-research]` items stay executable.
5. **Improve loop** — `./scripts/peer improve --write --research` consumes sync on next tick.

## Linked digests

- Efficiency: `notes/EFFICIENCY_RESEARCH.md`
- Output: `notes/OUTPUT_RESEARCH.md`
- Industry trends: `notes/AUTOMATION_TRENDS.md`

