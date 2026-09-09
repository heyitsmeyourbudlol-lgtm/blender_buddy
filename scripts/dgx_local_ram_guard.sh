#!/usr/bin/env bash
# Local RAM guard on DGX — trim unittest storms and excess cursor-agents (no SSH).
set -euo pipefail

ROOT="${HOME}/Automation"
BUDGET="${HOME}/.config/automation-hub/dgx_ram_budget.py"
if [ ! -f "$BUDGET" ]; then
  BUDGET="${ROOT}/scripts/dgx_ram_budget.py"
fi

# Priority governor + unified RAM/GPU poll — agent callback every guard tick.
if [ -f "$BUDGET" ]; then
  python3 "$ROOT/scripts/dgx_resource_poll.py" --once 2>/dev/null || true
fi

if [ -f "$BUDGET" ]; then
  read -r UNITTEST_CAP MAX_AGENTS MIN_AVAIL_GB CRIT_AVAIL_GB MAX_USED_GB FOOTPRINT_GB < <(
    python3 "$BUDGET" --shell-vars 2>/dev/null || echo "8 24 12 6 0 0"
  )
else
  UNITTEST_CAP=8
  MAX_AGENTS=24
  MIN_AVAIL_GB=12
  CRIT_AVAIL_GB=6
  MAX_USED_GB=0
  FOOTPRINT_GB=0
fi

mem_avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
mem_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
used_kb=$((mem_total_kb - mem_avail_kb))
min_kb=$(awk -v g="$MIN_AVAIL_GB" 'BEGIN{printf "%.0f", g*1024*1024}')
crit_kb=$(awk -v g="$CRIT_AVAIL_GB" 'BEGIN{printf "%.0f", g*1024*1024}')

over_budget=0
if [ "${MAX_USED_GB:-0}" != "0" ] && [ "${FOOTPRINT_GB:-0}" != "0" ]; then
  over_budget=$(awk -v fp="$FOOTPRINT_GB" -v cap="$MAX_USED_GB" 'BEGIN{print (fp > cap) ? 1 : 0}')
fi

if [ -f "$BUDGET" ]; then
  selfcheck_n=$(python3 "$BUDGET" --self-check-count 2>/dev/null || echo "0")
else
  selfcheck_n=$(pgrep -cf 'peer_orchestrate.py --self-check' 2>/dev/null || echo "0")
fi
SELF_CHECK_CAP=2
if [ "${selfcheck_n:-0}" -gt "${SELF_CHECK_CAP}" ]; then
  if [ -f "$BUDGET" ]; then
    python3 "$BUDGET" --trim-self-check-storm 2>/dev/null || true
  else
    pgrep -af 'peer_orchestrate.py --self-check' 2>/dev/null | awk '{print $1}' | tail -n +$((SELF_CHECK_CAP + 1)) | xargs -r kill -9 2>/dev/null || true
  fi
  echo "$(date '+%F %T')  dgx_local_guard: trimmed self-check storm ($selfcheck_n > $SELF_CHECK_CAP)"
fi

# Unittest trim — use Python so cursor-agent prompts (which quote "python -m unittest") are never killed.
if [ -f "$BUDGET" ]; then
  unittest_n=$(python3 "$BUDGET" --unittest-count 2>/dev/null || echo "0")
else
  unittest_n=$(pgrep -af '[pP]ython.* -m unittest' 2>/dev/null | grep -vi cursor-agent | wc -l | tr -d ' ')
fi
if [ "${unittest_n:-0}" -gt "${UNITTEST_CAP}" ]; then
  if [ -f "$BUDGET" ]; then
    python3 "$BUDGET" --trim-unittest-storm 2>/dev/null || true
  else
    pgrep -af '[pP]ython.* -m unittest' 2>/dev/null | grep -vi cursor-agent | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true
  fi
  echo "$(date '+%F %T')  dgx_local_guard: trimmed unittest storm ($unittest_n > $UNITTEST_CAP)"
fi

agent_pids=$(pgrep -af 'cursor-agent' 2>/dev/null | grep -E '(^| )-p( |$)' | grep -v worker | awk '{print $1}' || true)
agent_n=0
if [ -n "$agent_pids" ]; then
  agent_n=$(echo "$agent_pids" | wc -l | tr -d ' ')
fi

# Only trim excess agents when RAM is under pressure — not when Spark has headroom.
if [ "${agent_n:-0}" -gt "${MAX_AGENTS}" ] && { [ "$mem_avail_kb" -lt "$min_kb" ] || [ "$over_budget" -eq 1 ]; }; then
  echo "$agent_pids" | tail -n +$((MAX_AGENTS + 1)) | xargs -r kill -9 2>/dev/null || true
  echo "$(date '+%F %T')  dgx_local_guard: trimmed agents ($agent_n > $MAX_AGENTS, low RAM)"
fi

mem_avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
used_kb=$((mem_total_kb - mem_avail_kb))

# Footprint over-cap is handled by --govern (tiered replace). Critical path = true OOM only.
if [ "$mem_avail_kb" -lt "$crit_kb" ]; then
  if [ -f "$BUDGET" ]; then
    python3 "$BUDGET" --trim-unittest-storm 2>/dev/null || true
    python3 "$BUDGET" --govern 2>/dev/null || true
  else
    pkill -9 -f '[pP]ython.* -m unittest' 2>/dev/null || true
  fi
  if [ "$mem_avail_kb" -lt "$crit_kb" ]; then
    pgrep -af 'cursor-agent' 2>/dev/null | grep -E '(^| )-p( |$)' | grep -v worker | awk '{print $1}' | tail -n 2 | xargs -r kill -9 2>/dev/null || true
  fi
  used_gb=$(awk -v fp="${FOOTPRINT_GB:-0}" 'BEGIN{printf "%.1f", fp}')
  echo "$(date '+%F %T')  dgx_local_guard: critical avail — footprint ${used_gb}GB / cap ${MAX_USED_GB}GB (tiered trim, no mass kill)"
elif [ "$over_budget" -eq 1 ]; then
  echo "$(date '+%F %T')  dgx_local_guard: footprint ${FOOTPRINT_GB}GB > cap ${MAX_USED_GB}GB — governor handles replace"
elif [ "$mem_avail_kb" -lt "$min_kb" ]; then
  echo "$(date '+%F %T')  dgx_local_guard: warn RAM ($(awk -v k="$mem_avail_kb" 'BEGIN{printf "%.1f", k/1024/1024}')GB free < ${MIN_AVAIL_GB}GB min)"
fi
