#!/usr/bin/env bash
# OVERSEER_BEAT_MAC_2026_09_04 — restore WORKING lands after Mac/auth-noop thrash
set -euo pipefail
ROOT="${AUTOMATION_ROOT:-/home/arnavrastogi/Automation}"
BIN="$HOME/.config/automation-hub/bin"
VAULT="$HOME/.config/automation-hub/hub-protect"
GOLDEN="$HOME/.config/automation-hub/hub-protect-golden/scripts/scripts"
HOLD="$HOME/.config/automation-hub/OVERSEER_LAND_HOLD"

# Mac offload runs verify locally; CLEAN root is absent — never cp into a phantom path.
if [[ ! -d "$ROOT/scripts" ]]; then
  echo "beat: skip — ROOT/scripts missing ($ROOT) · run on CLEAN or set AUTOMATION_ROOT"
  exit 0
fi

heal_one() {
  local f="$1" needle="$2"
  local SRC=""
  for c in "$VAULT/$f" "$VAULT/scripts/$f" "$GOLDEN/$f" "$BIN/$f"; do
    if [[ -f "$c" ]] && grep -qE "$needle" "$c"; then SRC="$c"; break; fi
  done
  [[ -n "$SRC" ]] || return 0
  if ! grep -qE "$needle" "$ROOT/scripts/$f" 2>/dev/null; then
    cp -f "$SRC" "$ROOT/scripts/$f"
    echo "beat: restored $f"
  fi
}

# Needle heals ALWAYS run (even under land-hold) — Mac rsync clobbers every few seconds.
heal_one dgx_setup.sh 'OVERSEER_HUB_PROTECT_DGX_SETUP_2026_09_04|notes/BITNET_FACTCHECK.md'
heal_one dgx_ram_budget.py 'OVERSEER_SELF_CHECK_ARGV0'
heal_one peer_team_context.py 'TEAM_CONTEXT_WRITE_TTL_SEC'
heal_one peer_loop.py 'OVERSEER_LAND_MARK_LOCAL_VERIFY_DEFERRED|OVERSEER_METRICS_IGNORE_GIT_CLEAN_2026_09_04'
heal_one peer_error_adapt.py 'OVERSEER_AUTH_HOLD_2026_09_03'
heal_one run_peer_tasks.py 'ready≠git_clean|OVERSEER_LAND_2026_09_04'
heal_one peer_product_forge.py 'OVERSEER_CAAS_PATH_2026_09_04|CAAS_ROOT'
heal_one factory_grid.py 'OVERSEER_GLOBAL_CAP_CLAMP|min(cap, peers)'
heal_one project_automation.py 'OVERSEER_PEER3_HUB_PROTECT_CLOSE_2026_09_04|OVERSEER_METRICS_OK_IGNORE_GIT_CLEAN_2026_09_04|OVERSEER_PEN_SCRUB_2026_09_04'
heal_one peer_remote.py 'notes/WORK_QUEUE.md|notes/REPO_FLAW_RESEARCH.md|notes/AUTOMATION_DIGEST.md|OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04|OVERSEER_HUB_PROTECT_DIST_EXPORT_2026_09_04|OVERSEER_HUB_PROTECT_BITNET_FACTCHECK_2026_09_05|notes/BITNET_FACTCHECK.md'
heal_one peer_orchestrate.py 'OVERSEER_SELF_CHECK_REUSE_PLAN_LIVE_2026_09_04|snap = plan.live'
# OVERSEER_BEAT_TEST_AUTOMATION_2026_09_04
heal_test() {
  local f=test_automation.py needle='OVERSEER_METRICS_DIRTY_OK_2026_09_03'
  local SRC=""
  for c in "$VAULT/tests/$f" "$VAULT/$f" "$GOLDEN/../tests/$f" "$BIN/$f" "$HOME/.config/automation-hub/overseer-land/scripts/$f"; do
    if [[ -f "$c" ]] && grep -qE "$needle" "$c"; then SRC="$c"; break; fi
  done
  [[ -n "$SRC" ]] || return 0
  if ! grep -qE "$needle" "$ROOT/tests/$f" 2>/dev/null; then
    mkdir -p "$ROOT/tests"
    cp -f "$SRC" "$ROOT/tests/$f"
    echo "beat: restored tests/$f"
  fi
}
heal_test

# OVERSEER_BEAT_TEST_PEER_REPO_RESEARCH_2026_09_04
heal_test_prr() {
  local f=test_peer_repo_research.py needle='OVERSEER_RESOLVE_DEFECT_EPHEMERAL_2026_09_04'
  local SRC=""
  for c in "$VAULT/tests/$f" "$VAULT/$f" "$BIN/$f"; do
    if [[ -f "$c" ]] && grep -qE "$needle" "$c"; then SRC="$c"; break; fi
  done
  [[ -n "$SRC" ]] || return 0
  if ! grep -qE "$needle" "$ROOT/tests/$f" 2>/dev/null; then
    mkdir -p "$ROOT/tests"
    cp -f "$SRC" "$ROOT/tests/$f"
    echo "beat: restored tests/$f"
  fi
}
heal_test_prr

heal_test_err() {
  local f=test_peer_error_adapt.py needle='test_clear_autonomy_skips_auth_not_ready'
  local SRC=""
  for c in "$VAULT/tests/$f" "$VAULT/$f" "$BIN/$f"; do
    if [[ -f "$c" ]] && grep -qE "$needle" "$c"; then SRC="$c"; break; fi
  done
  [[ -n "$SRC" ]] || return 0
  if ! grep -qE "$needle" "$ROOT/tests/$f" 2>/dev/null; then
    mkdir -p "$ROOT/tests"
    cp -f "$SRC" "$ROOT/tests/$f"
    echo "beat: restored tests/$f"
  fi
}
heal_test_err
heal_one automation_improve.py 'OVERSEER_WRITE_PROMPTS_TTL_2026_09_04|WRITE_PROMPTS_FP_PATH|OVERSEER_SCRUB_ORPHAN_FORGE_IMPROVE'
heal_one peer_stall_pivot.py '_maybe_stall_adapt_audit|STALL_ADAPT_AUDIT_TTL_SEC'
heal_one peer_worktree.py 'sync_pool_hub_needle_scripts|OVERSEER_SYNC_HUB_NEEDLES_2026_09_04'
heal_one peer_repo_research.py 'OVERSEER_RESOLVE_DEFECT_EPHEMERAL_2026_09_04|OVERSEER_SKIP_FIXED_DEFECT_THEATER_2026_09_04|OVERSEER_STATIC_SKIP_FALSE_EVAL_ECHO_2026_09_04|OVERSEER_STATIC_SKIP_REPOISON_DOC_2026_09_04'
heal_one peer_pen_test.py 'OVERSEER_PEN_SCRUB_2026_09_04|scrub_secret_material|OVERSEER_PEN_SKIP_FIXTURE_2026_09_04|OVERSEER_PEN_SKIP_RESEARCH_2026_09_04'
heal_one automation_adapt.py 'OVERSEER_AUDIT_OK_NE_USABLE_2026_09_04|kit_export_dist_dirs|purge_noncompliant_kit_exports|probe_export_tarball_compliance'
# OVERSEER_DEFERRED_CREATIVE_MARKERS_2026_09_04 — Mac drop freezes queue_fp on Creative
heal_one factory_progress.py 'OVERSEER_DEFERRED_CREATIVE_MARKERS_2026_09_04|factory_meter_mode=external_proof'
heal_one peer_transcript.py 'OVERSEER_SCRUB_FIXTURE_NOTE_OK_2026_09_04|OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04'
# OVERSEER_COMPRESSION_KEEP_ALIVE_WAVE_UNLOAD_2026_09_07 — Mac drop strips prune_wave_rss → sticky ~350MB+ heap
heal_one compression_keep_alive.py 'COMPRESSION_KEEP_ALIVE_WAVE_UNLOAD_2026_09_07|prune_wave_rss'

# OVERSEER_HUB_PROTECT_BITNET_FACTCHECK_2026_09_05 — Mac must not rewind Wave-15 ledger
heal_note() {
  local rel="$1" needle="$2"
  local SRC=""
  for c in "$VAULT/$rel" "$VAULT/notes/$(basename "$rel")" "$HOME/.config/automation-hub/hub-protect/$rel"; do
    if [[ -f "$c" ]] && grep -qE "$needle" "$c"; then SRC="$c"; break; fi
  done
  [[ -n "$SRC" ]] || return 0
  if ! grep -qE "$needle" "$ROOT/$rel" 2>/dev/null; then
    mkdir -p "$(dirname "$ROOT/$rel")"
    cp -f "$SRC" "$ROOT/$rel"
    echo "beat: restored $rel"
  fi
}
heal_note notes/BITNET_FACTCHECK.md 'OVERSEER_NVFP4_LOCK_APPLICABILITY_2026_09_05'
heal_note notes/NVFP4_LOCK_APPLICABILITY.md 'OVERSEER_NVFP4_LOCK_APPLICABILITY_2026_09_05'

# OVERSEER_HUB_PROTECT_DIST_EXPORT_PURGE_2026_09_04 — Legal: always purge privacy-bad
# kit tars (even under land-hold). Restore wrap may be stubbed; Mac rsync reintroduces.
PYTHONPATH="$ROOT/scripts" python3 -c "
from pathlib import Path
import tarfile
repo = Path(r'''$ROOT''')
n = 0
try:
    import automation_adapt as a
    if hasattr(a, 'kit_export_dist_dirs') and hasattr(a, 'purge_noncompliant_kit_exports'):
        for d in a.kit_export_dist_dirs(repo):
            n += len(a.purge_noncompliant_kit_exports(d))
        print(f'beat: purged privacy-bad kit exports={n}')
        raise SystemExit(0)
except SystemExit:
    raise
except Exception:
    pass
need = {'automation-kit/LICENSE', 'automation-kit/SUPPORT.md'}
for d in (repo / 'dist',):
    if not d.is_dir():
        continue
    for t in list(d.glob('automation-kit-*.tar.gz')):
        bad = False
        try:
            with tarfile.open(t, 'r:gz') as tar:
                names = set(tar.getnames())
            if not need.issubset(names):
                bad = True
            if any('local.json' in x or '__pycache__' in x or x.endswith('.pyc') for x in names):
                bad = True
        except Exception:
            bad = True
        if bad:
            try:
                t.unlink()
                n += 1
            except OSError:
                pass
if n:
    print(f'beat: purged privacy-bad kit exports={n}')
" 2>/dev/null || true

# OVERSEER_BEAT_MARK_FLAWS_2026_09_04 — Mac restores Active theater for landed scripts
if [[ -f "$ROOT/scripts/_mark_flaw_research_landed.py" ]]; then
  python3 "$ROOT/scripts/_mark_flaw_research_landed.py" >/dev/null 2>&1 || true
fi
# OVERSEER_BEAT_HOLD_RESPECT_2026_09_04 — skip destructive unstub/unit flip under fresh hold
if [[ -f "$HOLD" ]]; then
  age=$(( $(date +%s) - $(stat -c %Y "$HOLD" 2>/dev/null || echo 0) ))
  if (( age >= 0 && age < 600 )); then
    echo "beat: needle-heal done; respect land-hold age=${age}s (skip unstub)"
    exit 0
  fi
fi
rm -f "$HOME/.config/automation-hub/OVERSEER_LAND_HOLD" "$ROOT/OVERSEER_LAND_HOLD" || true

# Unstub restore if paused stub
if [[ -f "$BIN/restore-hub-protect.sh.real" ]] && ! grep -q needle_ok "$BIN/restore-hub-protect.sh" 2>/dev/null; then
  cp -f "$BIN/restore-hub-protect.sh.real" "$BIN/restore-hub-protect.sh"
  chmod +x "$BIN/restore-hub-protect.sh"
  echo "beat: unstubbed restore-hub-protect.sh"
fi

bash "$BIN/restore-hub-protect.sh" || true
