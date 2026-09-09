#!/usr/bin/env python3
"""Kit progress snapshot — factory meter, research lanes, LOC totals.

Usage:
  python3 scripts/peer_kit_progress.py
  python3 scripts/peer_kit_progress.py --json
  python3 scripts/peer kit-progress
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_improve as improve  # noqa: E402
import factory_progress as fp  # noqa: E402
import project_automation as auto  # noqa: E402

STATE_PATH = auto.CONFIG_DIR / "kit-progress-state.json"
DIGEST_PATH = ROOT / "notes" / "KIT_PROGRESS.md"

_SKIP_DIRS = {
    ".git",
    ".worktrees",
    "node_modules",
    "__pycache__",
    ".cursor",
    "dist",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
}

_LOC_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scripts_py", (".py",)),
    ("tests_py", (".py",)),
    ("notes_md", (".md",)),
    ("shell", (".sh",)),
    ("config_json", (".json",)),
)


@dataclass
class LocBucket:
    name: str
    files: int = 0
    lines: int = 0
    blank: int = 0


@dataclass
class KitProgress:
    as_of: float = 0.0
    factory_pct: int = 0
    factory_label: str = ""
    asi_pct: int = 0
    asi_label: str = ""
    loc_total: int = 0
    loc_code: int = 0
    loc_buckets: list[LocBucket] = field(default_factory=list)
    command_builder_open_gaps: int | None = None
    research_efficiency_retired: bool = False
    research_output_retired: bool = False
    research_efficiency_stale: int = 0
    research_output_stale: int = 0
    compounds: int = 0
    peer_commands: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["loc_buckets"] = [asdict(b) for b in self.loc_buckets]
        return d


def _should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".")


def _count_file_lines(path: Path) -> tuple[int, int]:
    """Return (non-blank lines, blank lines)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0
    lines = text.splitlines()
    blank = sum(1 for ln in lines if not ln.strip())
    return len(lines) - blank, blank


def count_loc_under(root: Path, *, suffixes: tuple[str, ...]) -> LocBucket:
    bucket = LocBucket(name=root.name)
    if not root.is_dir():
        return bucket
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        code, blank = _count_file_lines(path)
        bucket.files += 1
        bucket.lines += code
        bucket.blank += blank
    return bucket


def count_repo_loc() -> tuple[list[LocBucket], int, int]:
    """Count LOC by bucket + whole-repo non-blank total."""
    buckets: list[LocBucket] = []
    buckets.append(count_loc_under(ROOT / "scripts", suffixes=(".py",)))
    buckets[0].name = "scripts_py"
    buckets.append(count_loc_under(ROOT / "tests", suffixes=(".py",)))
    buckets[1].name = "tests_py"
    buckets.append(count_loc_under(ROOT / "notes", suffixes=(".md",)))
    buckets[2].name = "notes_md"

    total_code = 0
    total_all = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(_should_skip_dir(p) for p in rel_parts[:-1]):
            continue
        if rel_parts[0] in _SKIP_DIRS:
            continue
        code, blank = _count_file_lines(path)
        total_code += code
        total_all += code + blank
    return buckets, total_code, total_all


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _research_lane_meta() -> dict[str, Any]:
    state = _load_json(auto.CONFIG_DIR / "dual-research-state.json")
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    eff = lanes.get("efficiency") if isinstance(lanes.get("efficiency"), dict) else {}
    out = lanes.get("output") if isinstance(lanes.get("output"), dict) else {}
    return {
        "efficiency_retired": bool(eff.get("retired")),
        "output_retired": bool(out.get("retired")),
        "efficiency_stale": int(eff.get("stale_cycles") or 0),
        "output_stale": int(out.get("stale_cycles") or 0),
    }


def _command_builder_gaps() -> int | None:
    try:
        import peer_command_builder as cb

        state = _load_json(auto.CONFIG_DIR / "command-builder-state.json")
        if "open_gaps" in state:
            return int(state.get("open_gaps") or 0)
        return len(cb.probe_gaps())
    except Exception:  # noqa: BLE001
        return None


def _peer_registry_counts() -> tuple[int, int]:
    try:
        import peer_commands as pc

        return len(pc.COMMANDS), len(pc.COMPOUND_STEPS)
    except Exception:  # noqa: BLE001
        return 0, 0


def compute_kit_progress() -> KitProgress:
    signals = improve.gather_signals(quick=True, research=False, refresh_trends=False)
    asi = improve.compute_asi_progress(signals)
    factory = fp.compute_factory_progress()
    buckets, total_code, _total_all = count_repo_loc()
    research = _research_lane_meta()
    cmds, compounds = _peer_registry_counts()
    return KitProgress(
        as_of=time.time(),
        factory_pct=factory.pct,
        factory_label=factory.label,
        asi_pct=asi.pct,
        asi_label=asi.label,
        loc_total=total_code,
        loc_code=total_code,
        loc_buckets=buckets,
        command_builder_open_gaps=_command_builder_gaps(),
        research_efficiency_retired=research["efficiency_retired"],
        research_output_retired=research["output_retired"],
        research_efficiency_stale=research["efficiency_stale"],
        research_output_stale=research["output_stale"],
        compounds=compounds,
        peer_commands=cmds,
    )


def persist_snapshot(kit: KitProgress) -> None:
    prev = _load_json(STATE_PATH)
    history = prev.get("history") if isinstance(prev.get("history"), list) else []
    history.append(
        {
            "ts": kit.as_of,
            "factory_pct": kit.factory_pct,
            "asi_pct": kit.asi_pct,
            "loc_total": kit.loc_total,
            "scripts_py": next((b.lines for b in kit.loc_buckets if b.name == "scripts_py"), 0),
            "tests_py": next((b.lines for b in kit.loc_buckets if b.name == "tests_py"), 0),
        }
    )
    history = history[-48:]
    payload = {"last": kit.to_dict(), "history": history}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def format_loc_table(kit: KitProgress) -> str:
    lines = [
        "## Lines of code",
        "",
        f"| Scope | Files | Non-blank lines |",
        f"|-------|------:|----------------:|",
    ]
    for b in kit.loc_buckets:
        label = b.name.replace("_", " ")
        lines.append(f"| {label} | {b.files} | {b.lines:,} |")
    lines.append(f"| **repo total (non-blank)** | — | **{kit.loc_total:,}** |")
    return "\n".join(lines)


def format_kit_progress_md(kit: KitProgress) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(kit.as_of))
    eff_status = "retired (marginal value exhausted)" if kit.research_efficiency_retired else f"active (stale={kit.research_efficiency_stale})"
    out_status = "retired (marginal value exhausted)" if kit.research_output_retired else f"active (stale={kit.research_output_stale})"
    gaps = kit.command_builder_open_gaps
    gaps_line = str(gaps) if gaps is not None else "?"
    part_block = ""
    try:
        import peer_roles as pr

        snap = pr.participation_snapshot()
        active_n = snap.get("active_last_cycle", 0)
        roster_n = snap.get("roster_size", 0)
        standby_n = max(0, roster_n - active_n)
        part_block = (
            f"\n## Team participation\n\n"
            f"- Full roster: **{roster_n}** niches · last cycle **{active_n}** active · **{standby_n}** standby (rotation)\n"
            f"- Replacement order: `notes/ROLE_IMPORTANCE.md`\n"
        )
    except Exception:  # noqa: BLE001
        part_block = ""
    return f"""# Kit progress

_Updated {ts}_ · Automation hub · **~{kit.loc_total:,} non-blank LOC** in this repo alone

## Outcome meters

| Meter | Value | Label |
|-------|------:|-------|
| Factory readiness | {kit.factory_pct}% | {kit.factory_label[:80]} |
| ASI harness | {kit.asi_pct}% | {kit.asi_label[:80]} |

## Automation lanes

| Lane | Status |
|------|--------|
| Command Builder | {gaps_line} open mechanical gap(s) |
| Efficiency research | {eff_status} |
| Output research | {out_status} |
| Peer registry | {kit.peer_commands} commands · {kit.compounds} compounds |
{part_block}
{format_loc_table(kit)}

## Commands

```bash
./scripts/peer progress      # factory meter + this digest
./scripts/peer kit-progress    # refresh KIT_PROGRESS.md only
./scripts/peer agents          # active + standby roster
./scripts/peer dual-research   # research cycle
./scripts/peer commands-loop   # compound cycle
```
"""


def write_kit_progress_digest(*, kit: KitProgress | None = None) -> Path:
    kit = kit if kit is not None else compute_kit_progress()
    persist_snapshot(kit)
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(format_kit_progress_md(kit) + "\n", encoding="utf-8")
    return DIGEST_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Kit progress — LOC + lane status")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--write", action="store_true", help="Write notes/KIT_PROGRESS.md")
    args = parser.parse_args()
    kit = compute_kit_progress()
    if args.write or not args.json:
        path = write_kit_progress_digest(kit=kit)
        if not args.json:
            print(format_kit_progress_md(kit))
            print(f"\n→ {path}")
    if args.json:
        print(json.dumps(kit.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
