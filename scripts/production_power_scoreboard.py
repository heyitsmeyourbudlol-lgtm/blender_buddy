#!/usr/bin/env python3
"""Refresh notes/PRODUCTION_POWER_SCOREBOARD.md current metrics (Top 10 indie)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

SCOREBOARD = ROOT / "notes" / "PRODUCTION_POWER_SCOREBOARD.md"
EXTERNAL_PROOF = ROOT / "notes" / "EXTERNAL_PROOF.md"
NEWDROP_REPO = "heyitsmeyourbudlol-lgtm/caas-changelog"
# OVERSEER_SCOREBOARD_GH_FALLBACK_2026_09_07 — CLEAN often has no `gh`; private
# caas-changelog 404s unauthenticated API. Fall back to EXTERNAL_PROOF SoT.
_PR_RE = __import__("re").compile(
    r"https?://github\.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/(\d+)"
)
_DATE_HEADING_RE = __import__("re").compile(
    r"^###\s+(\d{4}-\d{2}-\d{2})\b",
)
_TABLE_DATE_RE = __import__("re").compile(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|?\s*$")


def _gh_merges_7d() -> tuple[int, list[str]]:
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                NEWDROP_REPO,
                "--state",
                "merged",
                "--limit",
                "20",
                "--json",
                "number,title,mergedAt,url",
            ],
            capture_output=True,
            text=True,
            timeout=60.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _external_proof_merges_7d(fallback_note=f"gh failed: {exc}")
    if proc.returncode != 0:
        note = (proc.stderr or proc.stdout or "gh error")[:200]
        return _external_proof_merges_7d(fallback_note=note)
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return _external_proof_merges_7d(fallback_note="gh json parse error")
    now = datetime.now(timezone.utc)
    hits: list[str] = []
    for row in rows:
        merged = row.get("mergedAt") or ""
        try:
            ts = datetime.fromisoformat(merged.replace("Z", "+00:00"))
        except ValueError:
            continue
        age_days = (now - ts).total_seconds() / 86400.0
        if age_days <= 7.0:
            hits.append(f"#{row.get('number')} {row.get('title', '')[:60]} ({row.get('url')})")
    return len(hits), hits


def _external_proof_merges_7d(
    *, fallback_note: str = ""
) -> tuple[int, list[str]]:
    """Count Newdrop PR links in EXTERNAL_PROOF dated within 7d (SoT fallback)."""
    if not EXTERNAL_PROOF.is_file():
        return -1, [fallback_note or "EXTERNAL_PROOF missing"]
    text = EXTERNAL_PROOF.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)
    seen: dict[str, str] = {}
    section_date: datetime | None = None
    for ln in text.splitlines():
        hm = _DATE_HEADING_RE.match(ln.strip())
        if hm:
            try:
                section_date = datetime.fromisoformat(hm.group(1)).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                section_date = None
            continue
        # Table Newdrop row: date in last cell
        row_date = section_date
        if "Newdrop" in ln and "caas-changelog/pull/" in ln:
            dm = _TABLE_DATE_RE.search(ln)
            if dm:
                try:
                    row_date = datetime.fromisoformat(dm.group(1)).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pass
        if row_date is None:
            continue
        age_days = (now - row_date).total_seconds() / 86400.0
        if age_days > 7.0:
            continue
        for m in _PR_RE.finditer(ln):
            num = m.group(1)
            url = m.group(0)
            if num not in seen:
                seen[num] = f"#{num} (EXTERNAL_PROOF {row_date.date()} · {url})"
    if not seen:
        note = fallback_note or "no Newdrop PRs in EXTERNAL_PROOF ≤7d"
        return 0, [note]
    hits = [seen[k] for k in sorted(seen, key=int)]
    if fallback_note:
        hits.append(f"(via EXTERNAL_PROOF; {fallback_note[:80]})")
    return len(seen), hits


def _clean_daemons() -> str:
    # OVERSEER_SCOREBOARD_CLEAN_LINUX_2026_09_07 — DGX hub has no mac-offloaded
    # marker; credit local systemd peer+improve (mac-offloaded CLEAN path).
    marker = Path.home() / ".config" / "automation-hub" / "mac-offloaded"
    try:
        import peer_self_heal as sh

        peer_up = bool(sh._peer_daemon_running())
        improve_up = bool(sh._improve_daemon_running())
    except Exception:  # noqa: BLE001
        peer_up = improve_up = False
    if peer_up and improve_up:
        where = "mac-offloaded marker" if marker.is_file() else "local systemd (DGX CLEAN)"
        return f"CLEAN peer+improve up ({where})"
    if marker.is_file():
        try:
            import dgx_watch as dw

            st = dw.remote_service_status()
            return (
                f"CLEAN peer-loop={st.get('peer-loop')} improve-loop={st.get('improve-loop')} "
                f"ssh_rc={st.get('_ssh_rc')}"
            )
        except Exception as exc:  # noqa: BLE001
            return f"CLEAN probe failed: {exc}"
    return "mac-offloaded marker absent — peer/improve not both up"


def _theater_share() -> str:
    wq = ROOT / "notes" / "WORK_QUEUE.md"
    if not wq.is_file():
        return "n/a"
    open_active: list[str] = []
    in_active = False
    for ln in wq.read_text(encoding="utf-8").splitlines():
        if ln.startswith("## Active"):
            in_active = True
            continue
        if in_active and ln.startswith("## "):
            break
        if in_active and ln.startswith("- [ ]"):
            open_active.append(ln)
    if not open_active:
        return "0% (0 open Active)"
    theater_keys = (
        "niche-distill",
        "compression",
        "bitnet",
        "research-speed",
        "asi",
        "time bomb",
        "crown",
    )
    theater = sum(1 for x in open_active if any(k in x.lower() for k in theater_keys))
    pct = 100.0 * theater / len(open_active)
    return f"{pct:.0f}% ({theater}/{len(open_active)} open)"


def _load_peer_loop_state() -> dict:
    """Prefer local hub state; when mac-offloaded, pull CLEAN peer-loop-state."""
    marker = Path.home() / ".config" / "automation-hub" / "mac-offloaded"
    local = Path.home() / ".config" / "automation-hub" / "peer-loop-state.json"
    # Linux/DGX hub writes automation-hub directly.
    if sys.platform != "darwin" and local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    if marker.is_file():
        try:
            import dgx_watch as dw

            # One-line JSON — scan past SSH banners; merge flap-resistant sidecar.
            # Needle: OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07
            rc, out = dw._ssh(
                "python3 <<'PY'\n"
                "import json\n"
                "from pathlib import Path\n"
                "hub = Path.home() / '.config' / 'automation-hub'\n"
                "d = {}\n"
                "p = hub / 'peer-loop-state.json'\n"
                "if p.is_file():\n"
                "    d = json.load(p.open())\n"
                "side = {}\n"
                "s = hub / 'non_noop_by_day.json'\n"
                "if s.is_file():\n"
                "    raw = json.load(s.open())\n"
                "    side = raw.get('by_day', raw) if isinstance(raw, dict) else {}\n"
                "buckets = {}\n"
                "for src in (d.get('non_noop_by_day'), side):\n"
                "    if isinstance(src, dict):\n"
                "        for k, v in src.items():\n"
                "            try:\n"
                "                buckets[str(k)] = max(int(buckets.get(k) or 0), int(v))\n"
                "            except (TypeError, ValueError):\n"
                "                pass\n"
                "if buckets:\n"
                "    d['non_noop_by_day'] = buckets\n"
                "print(json.dumps(d if isinstance(d, dict) else {}))\n"
                "PY",
                timeout=25.0,
            )
            if rc == 0 and out:
                for ln in reversed(out.strip().splitlines()):
                    ln = ln.strip()
                    if ln.startswith("{") and ln.endswith("}"):
                        data = json.loads(ln)
                        if isinstance(data, dict):
                            return data
        except Exception:  # noqa: BLE001
            pass
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _non_noop_day() -> str:
    """Mechanical T10-04 meter — observed today + projected/day from CLEAN state."""
    try:
        import peer_transcript as transcript

        state = _load_peer_loop_state()
        if not state:
            return "n/a (no peer-loop-state)"
        # Scoreboard runs on Mac under mac-offloaded — do NOT merge Mac's local
        # non_noop sidecar into CLEAN buckets (inflates / false-PASS risk).
        # Remote SSH payload already max-merged CLEAN live + CLEAN sidecar.
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", fake):
                transcript.seed_non_noop_day_from_history(state)
                stats = transcript.non_noop_day_stats(state)
        today_n = stats.get("today_non_noop", 0)
        proj = stats.get("projected_per_day", 0)
        week = stats.get("week_avg_per_day", 0)
        bar = stats.get("bar", 8)
        flag = "PASS" if stats.get("meets_bar") else "GAP"
        return (
            f"{today_n} today · proj {proj}/day · week_avg {week} "
            f"(bar ≥{bar:.0f}) [{flag}]"
        )
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


def _agent_cap() -> str:
    try:
        return str(auto.max_parallel_agent_procs())
    except Exception:  # noqa: BLE001
        return "?"


def snapshot() -> dict[str, str]:
    n, hits = _gh_merges_7d()
    merges = str(n) if n >= 0 else "error"
    merge_notes = "; ".join(hits[:5]) if hits else "(none in 7d)"
    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "merges_7d": merges,
        "merge_notes": merge_notes,
        "daemons": _clean_daemons(),
        "theater": _theater_share(),
        "agent_cap": _agent_cap(),
        "non_noop_day": _non_noop_day(),
    }


def render_current_block(snap: dict[str, str]) -> str:
    return (
        f"## Current snapshot ({snap['as_of']})\n\n"
        f"| Metric | Value |\n"
        f"|--------|------:|\n"
        f"| Newdrop merges (7d) | {snap['merges_7d']} |\n"
        f"| Non-noop cycles/day | {snap.get('non_noop_day', 'n/a')} |\n"
        f"| Free-desktop agent cap | {snap['agent_cap']} |\n"
        f"| Theater Active share | {snap['theater']} |\n"
        f"| Brain / daemons | {snap['daemons']} |\n\n"
        f"Merges: {snap['merge_notes']}\n"
    )


def write_scoreboard(snap: dict[str, str]) -> None:
    text = SCOREBOARD.read_text(encoding="utf-8") if SCOREBOARD.is_file() else ""
    marker = "## Current snapshot"
    block = render_current_block(snap)
    if marker in text:
        pre = text.split(marker)[0].rstrip() + "\n\n"
        # keep week log after first ## Week
        rest = text.split(marker, 1)[1]
        if "## Week log" in rest:
            rest = "## Week log" + rest.split("## Week log", 1)[1]
        elif "## Week of" in rest:
            idx = rest.index("## Week of")
            rest = "## Week log\n\n" + rest[idx:]
        else:
            rest = "## Week log\n\n" + rest
        # Actually preserve from ## Week log if present in original
        if "## Week log" in text:
            rest = text.split("## Week log", 1)[1]
            SCOREBOARD.write_text(
                pre + block + "\n## Week log" + rest,
                encoding="utf-8",
            )
            return
    header = (
        "# Production power scoreboard\n\n"
        "_Top 10 indie · gravity Newdrop_ · Policy: [TOP10_PRODUCTION_POWER.md]"
        "(TOP10_PRODUCTION_POWER.md)\n\n"
        "Refresh: `python3 scripts/production_power_scoreboard.py --write`\n\n"
    )
    week = ""
    if "## Week log" in text:
        week = "## Week log" + text.split("## Week log", 1)[1]
    else:
        week = "## Week log\n\n_(none yet)_\n"
    SCOREBOARD.write_text(header + block + "\n" + week, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Update PRODUCTION_POWER_SCOREBOARD.md")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    snap = snapshot()
    if args.json:
        print(json.dumps(snap, indent=2))
    else:
        print(render_current_block(snap))
    if args.write:
        write_scoreboard(snap)
        print(f"wrote {SCOREBOARD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
