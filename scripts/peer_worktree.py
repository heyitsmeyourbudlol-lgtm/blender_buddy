#!/usr/bin/env python3
"""Git worktree helpers for parallel peer tasks.

Industry pattern: isolate agents in separate worktrees to avoid file conflicts.
``peer_loop`` inventories worktrees each continuous cycle and, when
``continue_on_dirty`` is on (default), auto-ensures a coding worktree so dirty
main trees never stall agent cycles.

Usage:
  python3 scripts/peer_worktree.py list
  python3 scripts/peer_worktree.py spawn --slot 3          # one parallel tree for peer 3
  python3 scripts/peer_worktree.py spawn --label fix-auth  # ad-hoc divide-and-conquer tree
  python3 scripts/peer_worktree.py ensure-pool           # peer-0..N pool for 8 peers
  python3 scripts/peer_worktree.py add ../Automation-peer-a --branch peer/a --dry-run
  python3 scripts/peer_worktree.py remove ../Automation-peer-a   # dry-run by default
  python3 scripts/peer_worktree.py remove ../Automation-peer-a --execute
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import project_automation as auto

ROOT = auto.ROOT

# Injected in tests. Default remove() stays force-off; nested/excess prune use force.
GitRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
_GITDIR_PREFIX = "gitdir:"

# OVERSEER_POOL_ENSURE_FASTPATH_2026_09_06 — skip prune/align when floor ready.
POOL_ENSURE_FASTPATH_TTL_SEC = 60.0
_pool_ensure_fastpath_at: float = 0.0


def clear_pool_ensure_fastpath_cache() -> None:
    """Drop ensure-pool TTL stamp (tests + forced pool refresh)."""
    global _pool_ensure_fastpath_at
    _pool_ensure_fastpath_at = 0.0


def _pool_ensure_ttl_warm() -> bool:
    if _pool_ensure_fastpath_at <= 0.0:
        return False
    return (time.monotonic() - _pool_ensure_fastpath_at) < POOL_ENSURE_FASTPATH_TTL_SEC


def _hub_parallel_floor_dirs_ready(
    hub: Path,
    n: int,
    *,
    rel_base: str | None = None,
    prefix: str | None = None,
) -> bool:
    """True when hub ``.worktrees/peer-0..N-1`` directories exist (cheap is_dir)."""
    want = max(0, int(n or 0))
    if want <= 0:
        return True
    if rel_base is None or prefix is None:
        rel_base, prefix = parallel_pool_config()
    base = Path(hub) / rel_base
    for i in range(want):
        if not (base / f"{prefix}-{i}").is_dir():
            return False
    return True


def _pool_fs_inventory_healthy(
    hub: Path,
    *,
    cap: int | None = None,
    rel_base: str | None = None,
    prefix: str | None = None,
) -> bool:
    """Cheap FS health: no nested ``peer-*/.worktrees`` and no ``peer-N`` with ``N>=cap``.

    OVERSEER_POOL_TTL_HEALTHY_INV_2026_09_06 — dir-only floor skip is unsafe when
    nested/excess pollution exists; TTL fast-path must refuse until prune runs.
    """
    limit = auto.max_parallel_peers() if cap is None else max(1, int(cap))
    if rel_base is None or prefix is None:
        rel_base, prefix = parallel_pool_config()
    base = Path(hub) / rel_base
    if not base.is_dir():
        return False
    pref = f"{prefix}-"
    try:
        children = list(base.iterdir())
    except OSError:
        return False
    for child in children:
        if not child.is_dir():
            continue
        nest = child / ".worktrees"
        if nest.is_dir():
            try:
                if any(nest.iterdir()):
                    return False
            except OSError:
                return False
        name = child.name
        if name.startswith(pref):
            suffix = name[len(pref) :]
            if suffix.isdigit() and int(suffix) >= limit:
                return False
    return True


def pool_inventory_healthy(
    entries: Sequence[WorktreeEntry] | None = None,
    *,
    root: Path | None = None,
    cap: int | None = None,
) -> bool:
    """True when porcelain shows nested=0 and excess=0 (Phase 3 pool health)."""
    nested = nested_pool_pollution_count(entries, root=root)
    if nested:
        return False
    excess = list_excess_parallel_slots(entries, root=root, cap=cap)
    return not excess


def _resolve_maybe_relative(raw: str, *, base: Path) -> Path:
    p = Path(raw.strip())
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def _git_common_dir_from_gitfile(root: Path) -> Path | None:
    """Resolve git-common-dir from ``.git`` + ``commondir`` — no subprocess."""
    marker = root / ".git"
    try:
        if marker.is_file():
            git_dir: Path | None = None
            text = marker.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith(_GITDIR_PREFIX):
                    raw = stripped[len(_GITDIR_PREFIX) :].strip()
                    if raw:
                        git_dir = _resolve_maybe_relative(raw, base=marker.parent)
                    break
            if git_dir is None or not git_dir.exists():
                return None
        elif marker.is_dir():
            git_dir = marker
        else:
            return None
        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            raw = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
            if raw:
                first = raw.splitlines()[0].strip()
                if first:
                    return _resolve_maybe_relative(first, base=git_dir)
        return git_dir.resolve()
    except OSError:
        return None


def _git_common_dir_spawn(root: Path) -> Path | None:
    """Fallback ``git rev-parse --git-common-dir`` (fork + git startup)."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        if proc.returncode != 0:
            return None
        raw = (proc.stdout or "").strip()
        if not raw:
            return None
        common = Path(raw)
        if not common.is_absolute():
            common = (root / common).resolve()
        else:
            common = common.resolve()
        return common
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_common_dir(root: Path) -> Path | None:
    """Resolved git-common-dir for ``root`` (gitfile/commondir first, else rev-parse)."""
    parsed = _git_common_dir_from_gitfile(root)
    if parsed is not None:
        return parsed
    if not (root / ".git").exists():
        return None
    return _git_common_dir_spawn(root)


# OVERSEER_ALIGN_FS_HEAD_2026_09_04 — align no-op tax: FS HEAD vs rev-parse (~34×).
# OVERSEER_SYNC_REQUIRE_FS_HEAD_2026_09_04 — hub-protect vault_ok + pool sync skip
# require this needle so Mac tip without FS-HEAD align cannot be treated complete.
def _git_dir_from_gitfile(root: Path) -> Path | None:
    """Resolve this checkout's git dir (``.git`` dir or ``gitdir:`` target) — no subprocess."""
    marker = root / ".git"
    try:
        if marker.is_file():
            text = marker.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith(_GITDIR_PREFIX):
                    raw = stripped[len(_GITDIR_PREFIX) :].strip()
                    if raw:
                        git_dir = _resolve_maybe_relative(raw, base=marker.parent)
                        if git_dir.exists():
                            return git_dir
                    break
            return None
        if marker.is_dir():
            return marker.resolve()
        return None
    except OSError:
        return None


def _packed_ref_sha(common: Path, ref: str) -> str | None:
    """Lookup ``ref`` in ``common/packed-refs`` (first matching line)."""
    packed = common / "packed-refs"
    try:
        if not packed.is_file():
            return None
        needle = f" {ref}"
        for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            if line.endswith(needle):
                sha = line[: -len(needle)].strip()
                if sha:
                    return sha
    except OSError:
        return None
    return None


def _git_head_sha_from_fs(root: Path) -> str | None:
    """Read HEAD SHA via gitdir/HEAD + refs (Turborepo-style) — no ``rev-parse``."""
    git_dir = _git_dir_from_gitfile(root)
    if git_dir is None:
        return None
    try:
        head_file = git_dir / "HEAD"
        if not head_file.is_file():
            return None
        raw = head_file.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return None
        if raw.startswith("ref:"):
            ref = raw[4:].strip()
            if not ref:
                return None
            common = _git_common_dir_from_gitfile(root) or git_dir
            for base in (git_dir, common):
                ref_path = base / ref
                if ref_path.is_file():
                    sha = ref_path.read_text(encoding="utf-8", errors="replace").strip()
                    if sha:
                        return sha.split()[0]
            return _packed_ref_sha(common, ref)
        # Detached HEAD — first token is the SHA.
        return raw.split()[0]
    except OSError:
        return None


@dataclass(frozen=True)
class WorktreeEntry:
    path: str
    head: str = ""
    branch: str = ""
    bare: bool = False
    detached: bool = False


def _hub_tip_from_entries(
    anchor: Path, entries: Sequence[WorktreeEntry]
) -> str:
    """Hub tip SHA from a shared ``git worktree list --porcelain`` snapshot."""
    want = Path(anchor).resolve()
    for e in entries:
        if Path(e.path).resolve() == want:
            tip = (e.head or "").strip()
            if tip:
                return tip
    return ""


def _all_pool_heads_at_tip(
    paths: Sequence[Path],
    tip: str,
    entries: Sequence[WorktreeEntry],
) -> bool:
    """True when every path's porcelain ``head`` equals *tip* (align is a no-op)."""
    if not tip or not paths or not entries:
        return False
    by = {Path(e.path).resolve(): (e.head or "").strip() for e in entries}
    for p in paths:
        if by.get(Path(p).resolve(), "") != tip:
            return False
    return True


def _default_runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def parse_worktree_porcelain(text: str) -> list[WorktreeEntry]:
    """Parse `git worktree list --porcelain` output."""
    entries: list[WorktreeEntry] = []
    path = ""
    head = ""
    branch = ""
    bare = False
    detached = False

    def flush() -> None:
        nonlocal path, head, branch, bare, detached
        if path:
            entries.append(
                WorktreeEntry(
                    path=path,
                    head=head,
                    branch=branch,
                    bare=bare,
                    detached=detached,
                )
            )
        path = ""
        head = ""
        branch = ""
        bare = False
        detached = False

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line:
            flush()
            continue
        if line.startswith("worktree "):
            flush()
            path = line[len("worktree ") :]
        elif line.startswith("HEAD "):
            head = line[len("HEAD ") :]
        elif line.startswith("branch "):
            ref = line[len("branch ") :]
            branch = ref.removeprefix("refs/heads/")
        elif line == "bare":
            bare = True
        elif line == "detached":
            detached = True
    flush()
    return entries


def list_worktrees(
    root: Path | None = None,
    *,
    runner: GitRunner | None = None,
) -> list[WorktreeEntry]:
    """Return worktrees for the repo at ``root`` (default: Automation hub)."""
    cwd = (root or ROOT).resolve()
    run = runner or _default_runner
    proc = run(["git", "worktree", "list", "--porcelain"], cwd)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git worktree list failed").strip()
        raise RuntimeError(err)
    return parse_worktree_porcelain(proc.stdout or "")


def add_worktree(
    path: Path | str,
    *,
    branch: str | None = None,
    create_branch: bool = False,
    root: Path | None = None,
    dry_run: bool = False,
    runner: GitRunner | None = None,
) -> list[str]:
    """Build (and optionally run) ``git worktree add`` argv.

    Returns the argv that would be / was executed.
    """
    cwd = (root or ROOT).resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = (cwd / target).resolve()
    else:
        target = target.resolve()

    argv: list[str] = ["git", "worktree", "add"]
    if branch and create_branch:
        argv.extend(["-b", branch])
    argv.append(str(target))
    if branch and not create_branch:
        argv.append(branch)

    if dry_run:
        return argv

    run = runner or _default_runner
    proc = run(argv, cwd)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git worktree add failed").strip()
        raise RuntimeError(err)
    return argv


def remove_worktree(
    path: Path | str,
    *,
    root: Path | None = None,
    dry_run: bool = True,
    force: bool = False,
    runner: GitRunner | None = None,
) -> list[str]:
    """Build (and optionally run) ``git worktree remove``.

    Default: no ``--force`` (refuse dirty/locked trees). Nested-pool and
    excess-slot prune pass ``force=True`` so dirty pollution cannot stick
    forever (flaw-research).
    Destructive by default: ``dry_run=True`` unless caller passes ``dry_run=False``.
    """
    cwd = (root or ROOT).resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = (cwd / target).resolve()
    else:
        target = target.resolve()

    argv = ["git", "worktree", "remove"]
    if force:
        argv.append("--force")
    argv.append(str(target))

    if dry_run:
        return argv

    run = runner or _default_runner
    proc = run(argv, cwd)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git worktree remove failed").strip()
        raise RuntimeError(err)
    return argv


def format_list(entries: Sequence[WorktreeEntry]) -> str:
    if not entries:
        return "(no worktrees)"
    lines: list[str] = []
    for e in entries:
        label = e.branch or ("(detached)" if e.detached else "(bare)" if e.bare else e.head[:12])
        lines.append(f"{e.path}\t{label}")
    return "\n".join(lines)


def primary_worktree_root(
    root: Path | None = None,
    *,
    runner: GitRunner | None = None,
) -> Path:
    """Primary (hub) checkout — common-dir parent, else first ``git worktree list``.

    When peer_loop runs inside a linked worktree (e.g. ``.worktrees/peer-3``),
    config-relative paths like ``.worktrees/peer-coding`` must resolve against
    the hub tree, not the nested checkout ROOT. Prefer ``--git-common-dir`` so a
    failed porcelain list never falls back to nesting under the caller cwd.
    """
    cwd = (root or ROOT).resolve()
    common = _git_common_dir(cwd)
    # Linked worktrees: common dir is ``<hub>/.git`` (or ``<hub>/.git/worktrees/...``
    # parent chain ends at hub ``.git``). Trust ``.git`` parent as the pool anchor.
    if common is not None and common.name == ".git":
        return common.parent.resolve()
    if common is not None:
        # ``…/hub/.git/worktrees/peer-N`` → walk up to the ``.git`` directory.
        for parent in common.parents:
            if parent.name == ".git":
                return parent.parent.resolve()
    try:
        entries = list_worktrees(cwd, runner=runner)
        if entries:
            return Path(entries[0].path).resolve()
    except RuntimeError:
        pass
    # Last resort: if cwd itself sits under ``.worktrees/``, peel to the hub above it.
    parts = cwd.parts
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        if idx > 0:
            return Path(*parts[:idx])
    return cwd


def hub_path(
    rel: str,
    *,
    root: Path | None = None,
    runner: GitRunner | None = None,
) -> Path:
    """Resolve a config-relative path against the primary worktree root."""
    hub = primary_worktree_root(root, runner=runner)
    p = Path(rel).expanduser()
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (hub / p).resolve()
    _refuse_nested_pool_target(resolved, hub=hub)
    return resolved


def _refuse_nested_pool_target(target: Path, *, hub: Path) -> None:
    """Raise when ``target`` would nest a pool under another ``.worktrees/peer-*``."""
    try:
        rel = target.resolve().relative_to(hub.resolve()).as_posix()
    except ValueError as exc:
        # Outside hub is allowed for explicit foreign paths; nesting check N/A.
        if target.parts.count(".worktrees") >= 2:
            raise RuntimeError(
                f"refuse nested worktree pool path: {target} "
                "(≥2 .worktrees segments)"
            ) from exc
        return
    if rel.count(".worktrees/") >= 2 or target.parts.count(".worktrees") >= 2:
        raise RuntimeError(
            f"refuse nested worktree pool path: {target} "
            "(must be hub/.worktrees/…, not peer-*/.worktrees/…)"
        )


def coding_worktree_path(
    *,
    root: Path | None = None,
    runner: GitRunner | None = None,
) -> Path:
    """Absolute path to the configured coding worktree (hub-relative)."""
    rel, _ = coding_worktree_config()
    return hub_path(rel, root=root, runner=runner)


def _pool_rel_pattern() -> re.Pattern[str]:
    rel_base, prefix = parallel_pool_config()
    return re.compile(rf"^{re.escape(rel_base)}/{re.escape(prefix)}-\d+$")


def _pool_slot_index(path: Path | str) -> int:
    """Numeric index from ``peer-N``, or -1 when not a pool slot name."""
    name = Path(path).name
    _, prefix = parallel_pool_config()
    m = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", name)
    return int(m.group(1)) if m else -1


def is_hub_pool_path(
    path: Path | str,
    *,
    root: Path | None = None,
    hub: Path | None = None,
) -> bool:
    """True when path is hub ``.worktrees/peer-N`` (not a nested peer-*/.worktrees clone)."""
    anchor = hub if hub is not None else primary_worktree_root(root)
    try:
        rel = Path(path).resolve().relative_to(Path(anchor).resolve()).as_posix()
    except (OSError, ValueError):
        return False
    return bool(_pool_rel_pattern().match(rel))


def list_nested_pool_pollution(
    entries: Sequence[WorktreeEntry] | None = None,
    *,
    root: Path | None = None,
) -> list[Path]:
    """Nested clones under ``.worktrees/peer-*/.worktrees/…`` (should be empty)."""
    cwd = (root or ROOT).resolve()
    try:
        rows = list(entries) if entries is not None else list_worktrees(cwd)
    except RuntimeError:
        return []
    out: list[Path] = []
    for e in rows:
        try:
            path = Path(e.path).resolve()
        except OSError:
            continue
        if path.parts.count(".worktrees") < 2:
            continue
        out.append(path)
    return out


def nested_pool_pollution_count(
    entries: Sequence[WorktreeEntry] | None = None,
    *,
    root: Path | None = None,
) -> int:
    """Count nested worktrees under another pool slot (should be 0)."""
    return len(list_nested_pool_pollution(entries, root=root))


def prune_nested_pool_pollution(
    *,
    root: Path | None = None,
    dry_run: bool = False,
    force: bool = True,
    log_fn: Callable[[str], None] | None = None,
    runner: GitRunner | None = None,
    entries: Sequence[WorktreeEntry] | None = None,
) -> dict[str, Any]:
    """Remove nested ``peer-*/.worktrees/…`` clones so the pool stays hub-only.

    Nested pollution must not stick forever when dirty: default ``force=True``
    (``git worktree remove --force``). Ordinary CLI ``remove`` stays force-off.
    Pass ``entries=`` from a shared porcelain list to avoid a second ``list_worktrees``.
    """
    anchor = primary_worktree_root(root, runner=runner)
    found = list_nested_pool_pollution(entries, root=root)
    removed: list[str] = []
    failed: list[str] = []
    for path in found:
        try:
            remove_worktree(
                path, root=anchor, dry_run=dry_run, force=force, runner=runner
            )
            removed.append(str(path))
            if log_fn:
                verb = "would prune" if dry_run else "pruned"
                flag = " --force" if force else ""
                log_fn(f"worktree pool: {verb} nested {path.name}{flag} ({path})")
        except RuntimeError as exc:
            failed.append(str(path))
            if log_fn:
                log_fn(f"worktree pool: prune failed {path} ({exc})")
    return {
        "found": len(found),
        "removed": removed,
        "failed": failed,
        "dry_run": dry_run,
        "force": force,
    }


def list_excess_parallel_slots(
    entries: Sequence[WorktreeEntry] | None = None,
    *,
    root: Path | None = None,
    cap: int | None = None,
    runner: GitRunner | None = None,
) -> list[Path]:
    """Hub ``.worktrees/peer-N`` paths where ``N >= max_parallel_peers`` (excess).

    Numbered slots above the effective cap accumulate when spawn(slot=N) was
    uncapped or a prior local override (e.g. floor/max=48) inflated the pool.
    Labeled trees (``peer-coding``, ``peer-fix-auth``) are not excess.
    """
    limit = auto.max_parallel_peers() if cap is None else max(1, int(cap))
    anchor = primary_worktree_root(root, runner=runner)
    try:
        rows = (
            list(entries)
            if entries is not None
            else list_worktrees(anchor, runner=runner)
        )
    except RuntimeError:
        return []
    out: list[Path] = []
    for e in rows:
        try:
            path = Path(e.path).resolve()
        except OSError:
            continue
        if not is_hub_pool_path(path, hub=anchor):
            continue
        idx = _pool_slot_index(path)
        if idx >= limit:
            out.append(path)
    out.sort(key=lambda p: (_pool_slot_index(p), str(p)))
    return out


def _hub_pool_dir(hub: Path) -> Path:
    """``hub/.worktrees`` (or configured ``parallel_worktree_dir``)."""
    rel_base, _ = parallel_pool_config()
    return (Path(hub) / rel_base)


def _assert_under_pool(path: Path, hub: Path) -> Path:
    """Resolve ``path`` and refuse anything outside the hub pool directory."""
    pool = _hub_pool_dir(hub).resolve()
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(pool)
    except ValueError as exc:
        raise RuntimeError(
            f"refuse fs reap outside pool: {resolved} (pool {pool})"
        ) from exc
    if resolved == pool:
        raise RuntimeError(f"refuse removing pool root {resolved}")
    return resolved


def list_orphan_excess_dirs(
    *,
    root: Path | None = None,
    cap: int | None = None,
    runner: GitRunner | None = None,
) -> list[Path]:
    """Filesystem ``peer-N`` (N>=cap) dirs git does not register (often no ``.git``).

    ``list_excess_parallel_slots`` only sees ``git worktree list`` porcelain, so
    leftover dirs after a failed/partial remove (or never-registered spawn)
    stick forever. Numbered floor slots and labeled trees are not orphans.
    """
    limit = auto.max_parallel_peers() if cap is None else max(1, int(cap))
    anchor = primary_worktree_root(root, runner=runner)
    pool = _hub_pool_dir(anchor)
    if not pool.is_dir():
        return []
    out: list[Path] = []
    try:
        children = list(pool.iterdir())
    except OSError:
        return []
    for child in children:
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        idx = _pool_slot_index(child)
        if idx < limit:
            continue
        try:
            if (child / ".git").exists():
                # Git-owned — ``git worktree remove`` in prune_excess owns this.
                continue
        except OSError:
            continue
        out.append(child.resolve())
    out.sort(key=lambda p: (_pool_slot_index(p), str(p)))
    return out


def list_empty_nested_worktree_dirs(
    *,
    root: Path | None = None,
    runner: GitRunner | None = None,
) -> list[Path]:
    """Empty ``hub/.worktrees/peer-*/.worktrees`` leftovers after nested git prune.

    Nested prune only removes registered worktrees; empty nest directories
    remain on disk and are not porcelain entries.
    """
    anchor = primary_worktree_root(root, runner=runner)
    pool = _hub_pool_dir(anchor)
    if not pool.is_dir():
        return []
    out: list[Path] = []
    try:
        children = list(pool.iterdir())
    except OSError:
        return []
    for child in children:
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        nest = child / ".worktrees"
        try:
            if not nest.is_dir():
                continue
            if any(nest.iterdir()):
                continue
        except OSError:
            continue
        out.append(nest.resolve())
    out.sort(key=lambda p: str(p))
    return out


def prune_excess_parallel_pool(
    *,
    root: Path | None = None,
    cap: int | None = None,
    dry_run: bool = False,
    force: bool = True,
    log_fn: Callable[[str], None] | None = None,
    runner: GitRunner | None = None,
    entries: Sequence[WorktreeEntry] | None = None,
) -> dict[str, Any]:
    """Retire hub ``peer-N`` worktrees with ``N >= max_parallel_peers``.

    Excess slots above the cap must not stick forever when dirty: default
    ``force=True`` (``git worktree remove --force``), matching nested prune.
    Ordinary CLI ``remove`` stays force-off. Canonical ``peer-0..cap-1`` are
    never listed by ``list_excess_parallel_slots``.
    Pass ``entries=`` from a shared porcelain list to avoid a second ``list_worktrees``.
    """
    limit = auto.max_parallel_peers() if cap is None else max(1, int(cap))
    anchor = primary_worktree_root(root, runner=runner)
    found = list_excess_parallel_slots(
        entries, root=anchor, cap=limit, runner=runner
    )
    removed: list[str] = []
    failed: list[str] = []
    for path in found:
        try:
            remove_worktree(
                path, root=anchor, dry_run=dry_run, force=force, runner=runner
            )
            removed.append(str(path))
            if log_fn:
                verb = "would prune" if dry_run else "pruned"
                flag = " --force" if force else ""
                log_fn(
                    f"worktree pool: {verb} excess {path.name}{flag} "
                    f"(slot {_pool_slot_index(path)} >= cap {limit})"
                )
        except RuntimeError as exc:
            failed.append(str(path))
            if log_fn:
                log_fn(f"worktree pool: excess prune failed {path} ({exc})")
    # Porcelain-only list misses leftover dirs (no .git) and empty nested
    # ``peer-*/.worktrees`` after git prune — reap those from the filesystem.
    orphan_removed: list[str] = []
    orphans = list_orphan_excess_dirs(root=anchor, cap=limit, runner=runner)
    for path in orphans:
        try:
            target = _assert_under_pool(path, anchor)
            if not dry_run:
                shutil.rmtree(target)
            orphan_removed.append(str(target))
            if log_fn:
                verb = "would reap" if dry_run else "reaped"
                log_fn(
                    f"worktree pool: {verb} orphan excess {target.name} "
                    f"(slot {_pool_slot_index(target)} >= cap {limit}, no .git)"
                )
        except (OSError, RuntimeError) as exc:
            failed.append(str(path))
            if log_fn:
                log_fn(f"worktree pool: orphan excess reap failed {path} ({exc})")
    nest_removed: list[str] = []
    nests = list_empty_nested_worktree_dirs(root=anchor, runner=runner)
    for path in nests:
        try:
            target = _assert_under_pool(path, anchor)
            if target.name != ".worktrees":
                raise RuntimeError(f"refuse nest rmdir of non-.worktrees {target}")
            if not dry_run:
                target.rmdir()
            nest_removed.append(str(target))
            if log_fn:
                verb = "would rmdir" if dry_run else "rmdir"
                log_fn(f"worktree pool: {verb} empty nested {target}")
        except (OSError, RuntimeError) as exc:
            failed.append(str(path))
            if log_fn:
                log_fn(f"worktree pool: empty nest rmdir failed {path} ({exc})")
    return {
        "found": len(found),
        "removed": removed,
        "failed": failed,
        "orphans_found": len(orphans),
        "orphans_removed": orphan_removed,
        "empty_nests_found": len(nests),
        "empty_nests_removed": nest_removed,
        "cap": limit,
        "dry_run": dry_run,
        "force": force,
    }


def clamp_parallel_slot(slot: int, *, cap: int | None = None) -> int:
    """Clamp a pool slot index into ``[0, max_parallel_peers)``."""
    limit = auto.max_parallel_peers() if cap is None else max(1, int(cap))
    return max(0, min(int(slot), limit - 1))


def _refuse_slot_out_of_cap(slot: int, *, cap: int | None = None) -> int:
    """Refuse numbered slots outside ``[0, max_parallel_peers)``.

    Silent clamp recreates peer-N after prune (live peer-20/22). Returns ``slot``
    when in range so spawn can use the value.
    """
    limit = auto.max_parallel_peers() if cap is None else max(1, int(cap))
    n = int(slot)
    if n < 0 or n >= limit:
        raise RuntimeError(
            f"refuse slot {n} outside [0, {limit}) (max_parallel_peers={limit})"
        )
    return n


def parallel_entries(
    entries: Sequence[WorktreeEntry],
    *,
    root: Path | None = None,
) -> list[WorktreeEntry]:
    """Worktrees other than the primary repo root (candidates for isolated peers)."""
    if entries:
        primary = Path(entries[0].path).resolve()
    else:
        primary = primary_worktree_root(root)
    out: list[WorktreeEntry] = []
    for e in entries:
        try:
            if Path(e.path).resolve() != primary:
                out.append(e)
        except OSError:
            out.append(e)
    return out


def coding_worktree_config() -> tuple[str, str]:
    """Return (relative path, branch) from automation.config.json."""
    rel = str(auto.CFG.get("coding_worktree") or ".worktrees/peer-coding").strip()
    branch = str(auto.CFG.get("coding_worktree_branch") or "peer/coding").strip()
    return rel or ".worktrees/peer-coding", branch or "peer/coding"


def continue_on_dirty_enabled() -> bool:
    """When True, peer_loop must not stall coding on a dirty main tree."""
    return bool(auto.CFG.get("continue_on_dirty", True))


def solved_dirty_dispatch_item(text: str) -> bool:
    """True when this queue line asked to unblock dirty-tree dispatch and already did.

    Optional WIP commit/stash stays a Queue Steward hygiene item. Stale
    "Unblock dirty tree for peer_loop dispatch — git: N paths" lines must not
    consume orchestrate/hand_out slots or keep the queue fingerprint stuck.
    """
    if not continue_on_dirty_enabled():
        return False
    low = str(text or "").lower()
    if "unblock dirty tree" in low:
        return True
    return "dirty tree" in low and ("dispatch" in low or "peer_loop" in low)


def dirty_wait_sec() -> float:
    """Short safety wait when continue_on_dirty (default 12s)."""
    try:
        return max(0.0, float(auto.CFG.get("dirty_wait_sec", 12)))
    except (TypeError, ValueError):
        return 12.0


def ensure_coding_worktree(
    *,
    root: Path | None = None,
    rel_path: str | None = None,
    branch: str | None = None,
    runner: GitRunner | None = None,
    entries: Sequence[WorktreeEntry] | None = None,
) -> Path:
    """Ensure a dedicated coding worktree exists; return its absolute path.

    Used when main is dirty so agents can keep shipping on a clean checkout.
    Creates ``.worktrees/peer-coding`` (config) on ``peer/coding`` when missing.
    Always hub-anchors so a caller cwd under ``.worktrees/peer-N`` cannot nest.
    Pass ``entries=`` (shared porcelain) to skip a per-slot ``list_worktrees``.
    """
    cwd = (root or ROOT).resolve()
    run = runner or _default_runner
    hub = primary_worktree_root(cwd, runner=run)
    rel, br = coding_worktree_config()
    if rel_path:
        rel = rel_path
    if branch:
        br = branch
    target = hub_path(rel, root=cwd, runner=run)

    rows = list(entries) if entries is not None else list_worktrees(hub, runner=run)
    for e in rows:
        try:
            if Path(e.path).resolve() == target:
                return target
        except OSError:
            continue

    target.parent.mkdir(parents=True, exist_ok=True)
    # Prefer new branch; if branch exists, attach worktree to it; else detached HEAD.
    attempts: list[tuple[str | None, bool]] = [
        (br, True),
        (br, False),
        (None, False),
    ]
    last_err = ""
    for branch_name, create in attempts:
        try:
            add_worktree(
                target,
                branch=branch_name,
                create_branch=create and bool(branch_name),
                root=hub,
                dry_run=False,
                runner=run,
            )
            return target
        except RuntimeError as exc:
            last_err = str(exc)
            continue
    raise RuntimeError(last_err or f"could not ensure coding worktree at {target}")


def parallel_pool_config() -> tuple[str, str]:
    """Return (relative dir, worktree name prefix) for parallel peer pool."""
    rel = str(auto.CFG.get("parallel_worktree_dir") or ".worktrees").strip()
    prefix = str(auto.CFG.get("parallel_worktree_prefix") or "peer").strip()
    return rel or ".worktrees", prefix or "peer"


def _sanitize_worktree_label(label: str) -> str:
    """Filesystem-safe label for ad-hoc parallel trees."""
    safe = re.sub(r"[^\w.-]+", "-", label.strip()).strip("-")
    return (safe[:48] if safe else "task")


def _worktree_slot_paths(
    slot: int,
    *,
    root: Path | None = None,
    runner: GitRunner | None = None,
) -> tuple[str, str]:
    """Return (relative path, branch) for a numbered parallel slot."""
    rel_base, prefix = parallel_pool_config()
    return f"{rel_base}/{prefix}-{slot}", f"peer/{slot}"


def _next_free_slot(
    *,
    root: Path | None = None,
    runner: GitRunner | None = None,
) -> int:
    """Lowest unused slot index below max_parallel_peers."""
    cap = auto.max_parallel_peers()
    cwd = (root or ROOT).resolve()
    run = runner or _default_runner
    try:
        entries = list_worktrees(cwd, runner=run)
    except RuntimeError:
        entries = []
    rel_base, prefix = parallel_pool_config()
    used: set[int] = set()
    for e in entries:
        name = Path(e.path).name
        m = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", name)
        if m:
            used.add(int(m.group(1)))
    for i in range(cap):
        if i not in used:
            return i
    return 0


def spawn_parallel_worktree(
    slot: int | None = None,
    *,
    label: str | None = None,
    root: Path | None = None,
    runner: GitRunner | None = None,
    dry_run: bool = False,
) -> Path:
    """Spawn (or return) one parallel-peer worktree for divide-and-conquer.

  - ``slot`` 0..N → ``.worktrees/peer-{n}`` on branch ``peer/{n}``
    (refuses N outside ``[0, max_parallel_peers)`` — never silent-clamp)
  - ``label`` → ``.worktrees/peer-{label}`` on branch ``peer/{label}`` (sanitized);
    pure-numeric labels are slot aliases and use the same refuse
  - neither → next free slot below ``max_parallel_peers()``

    Returns the absolute worktree path. Idempotent when the tree already exists.
    """
    cwd = (root or ROOT).resolve()
    run = runner or _default_runner
    rel_base, prefix = parallel_pool_config()

    if label:
        tag = _sanitize_worktree_label(label)
        if tag.isdigit():
            _refuse_slot_out_of_cap(int(tag))
        rel = f"{rel_base}/{prefix}-{tag}"
        branch = f"peer/{tag}"
    elif slot is not None:
        n = _refuse_slot_out_of_cap(int(slot))
        rel, branch = _worktree_slot_paths(n, root=cwd, runner=run)
    else:
        free = _next_free_slot(root=cwd, runner=run)
        rel, branch = _worktree_slot_paths(free, root=cwd, runner=run)

    target = hub_path(rel, root=cwd, runner=run)
    if dry_run:
        return target

    return ensure_coding_worktree(
        root=cwd,
        rel_path=rel,
        branch=branch,
        runner=run,
    )


def _hub_config_namespace(hub: Path) -> str:
    cfg = hub / "automation.config.json"
    if cfg.is_file():
        try:
            ns = json.loads(cfg.read_text()).get("config_namespace")
            if isinstance(ns, str) and ns.strip():
                return ns.strip()
        except (json.JSONDecodeError, OSError):
            pass
    return str(auto.CFG.get("config_namespace") or "automation-hub")


def _slot_effective_namespace(slot: Path) -> str | None:
    """Effective config_namespace for a pool slot — local overlay wins.

    Isolate writes gitignored ``automation.config.local.json`` so tracked
    ``automation.config.json`` stays clean (align hard-reset safe).
    """
    local = slot / "automation.config.local.json"
    if local.is_file():
        try:
            ns = json.loads(local.read_text()).get("config_namespace")
            if isinstance(ns, str) and ns.strip():
                return ns.strip()
        except (json.JSONDecodeError, OSError):
            pass
    cfg = slot / "automation.config.json"
    if cfg.is_file() or cfg.is_symlink():
        try:
            ns = json.loads(cfg.read_text()).get("config_namespace")
            if isinstance(ns, str) and ns.strip():
                return ns.strip()
        except (json.JSONDecodeError, OSError):
            pass
    return None


def isolate_pool_adapt_namespaces(
    paths: Sequence[Path],
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[str]:
    """Stop pool slots from sharing hub ``adapt-state.json`` via copied namespace.

    Stale peer-N trees often keep ``config_namespace=automation-hub`` and pre-fix
    ``save_adapt_state`` (raw null fp). Their writes poison
    ``~/.config/automation-hub/adapt-state.json`` → adapt_stale dispatch hold.

    Write isolation into gitignored ``automation.config.local.json`` so tracked
    ``automation.config.json`` stays clean (align hard-reset must not permanently
    dirty slots). Symlinks to hub config are broken into a real file first.
    """
    anchor = primary_worktree_root(hub, runner=runner)
    hub_ns = _hub_config_namespace(anchor)
    hub_cfg = (anchor / "automation.config.json").resolve()
    shared = {hub_ns, "automation-hub", "automation"}
    changed: list[str] = []
    for path in paths:
        slot = Path(path)
        name = slot.name
        if not name.startswith("peer-"):
            continue
        want = name  # peer-0 … peer-N / peer-coding
        cfg_path = slot / "automation.config.json"
        local_path = slot / "automation.config.local.json"
        if not cfg_path.exists() and not cfg_path.is_symlink() and not local_path.is_file():
            continue
        is_link = cfg_path.is_symlink()
        points_at_hub = False
        if is_link:
            try:
                points_at_hub = cfg_path.resolve() == hub_cfg
            except OSError:
                points_at_hub = False
        # Break hub symlink so slot has its own tracked file (hub identity safe).
        if points_at_hub:
            try:
                data = json.loads(cfg_path.read_text())
                if not isinstance(data, dict):
                    data = {}
                cfg_path.unlink()
                # Keep hub ns in tracked file; isolation goes to local overlay.
                data["config_namespace"] = hub_ns
                cfg_path.write_text(json.dumps(data, indent=2) + "\n")
            except (json.JSONDecodeError, OSError) as exc:
                if log_fn:
                    log_fn(f"worktree pool: {name} break hub symlink failed ({exc})")
                continue
        cur = _slot_effective_namespace(slot)
        if cur == want:
            continue
        if cur not in shared and cur is not None:
            # Already isolated (or intentionally distinct) — leave alone.
            continue
        # Overlay-only write — tracked config untouched.
        local_data: dict = {}
        if local_path.is_file():
            try:
                raw = json.loads(local_path.read_text())
                if isinstance(raw, dict):
                    local_data = raw
            except (json.JSONDecodeError, OSError):
                local_data = {}
        local_data["config_namespace"] = want
        try:
            local_path.write_text(json.dumps(local_data, indent=2) + "\n")
        except OSError as exc:
            if log_fn:
                log_fn(f"worktree pool: {name} local namespace write failed ({exc})")
            continue
        changed.append(name)
        if log_fn:
            via = " (broke hub symlink + local overlay)" if points_at_hub else " (local overlay)"
            log_fn(f"worktree pool: {name} config_namespace {cur!r} → {want!r}{via}")
    return changed


def pool_tip_skew_report(
    paths: Sequence[Path],
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
) -> dict[str, Any]:
    """Count floor HEADs vs hub tip (FS-first; no porcelain).

    Needle: ``OVERSEER_POOL_READY_FAIL_CLOSED_TIP_2026_09_08`` — dir-exists is not
    tip-ready. When heads are readable and any ``HEAD≠hub``, callers must set
    ``pool_ready=False``. Unreadable heads → ``checked=False`` (do not fail-closed
    on fixture/missing gitdirs).
    """
    run = runner or _default_runner
    try:
        anchor = primary_worktree_root(hub, runner=run)
    except (RuntimeError, OSError, FileNotFoundError):
        anchor = Path(hub) if hub is not None else ROOT
    tip = _git_head_sha_from_fs(anchor) or ""
    if not tip:
        try:
            hub_head = run(["git", "rev-parse", "HEAD"], anchor)
            if hub_head.returncode == 0:
                tip = (hub_head.stdout or "").strip()
        except (OSError, FileNotFoundError):
            tip = ""
    slots = [Path(p) for p in paths]
    if not tip:
        return {
            "tip": "",
            "matched": 0,
            "skew": 0,
            "unknown": len(slots),
            "checked": False,
        }
    matched = 0
    skew = 0
    unknown = 0
    for slot in slots:
        head = _git_head_sha_from_fs(slot) or ""
        if not head:
            # Missing cwd → FileNotFoundError from subprocess; treat as unknown
            # (fixtures / uncreated pool slots) — do not raise into emit inventory.
            try:
                head_p = run(["git", "rev-parse", "HEAD"], slot)
                if head_p.returncode == 0:
                    head = (head_p.stdout or "").strip()
            except (OSError, FileNotFoundError):
                head = ""
        if not head:
            unknown += 1
            continue
        if head == tip:
            matched += 1
        else:
            skew += 1
    return {
        "tip": tip,
        "matched": matched,
        "skew": skew,
        "unknown": unknown,
        "checked": (matched + skew) > 0,
    }


def align_parallel_pool_to_hub(
    paths: Sequence[Path],
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, list[str]]:
    """Reset *clean* pool slots to hub tip so they pick up refuse-null adapt.

    Dirty trees are skipped (agents keep WIP). Hard-reset restores hub
    ``automation.config.json`` (shared ``config_namespace``) — callers must
    re-run ``isolate_pool_adapt_namespaces`` *after* align. Dirty poisoners
    that skip reset still need a pre-align isolate so they stop sharing hub
    adapt-state.
    """
    run = runner or _default_runner
    anchor = primary_worktree_root(hub, runner=run)
    # FS HEAD first (linked worktrees): avoid N× rev-parse on the common no-op path.
    tip = _git_head_sha_from_fs(anchor)
    if not tip:
        hub_head = run(["git", "rev-parse", "HEAD"], anchor)
        if hub_head.returncode != 0 or not (hub_head.stdout or "").strip():
            return {"aligned": [], "skipped_dirty": [], "skipped_other": list(map(str, paths))}
        tip = hub_head.stdout.strip()
    aligned: list[str] = []
    skipped_dirty: list[str] = []
    skipped_other: list[str] = []
    for path in paths:
        slot = Path(path).resolve()
        name = slot.name
        head = _git_head_sha_from_fs(slot)
        if not head:
            head_p = run(["git", "rev-parse", "HEAD"], slot)
            if head_p.returncode != 0:
                skipped_other.append(name)
                continue
            head = (head_p.stdout or "").strip()
        if head == tip:
            continue
        porcelain = run(["git", "status", "--porcelain"], slot)
        if porcelain.returncode != 0:
            skipped_other.append(name)
            continue
        if (porcelain.stdout or "").strip():
            skipped_dirty.append(name)
            if log_fn:
                log_fn(f"worktree pool: {name} HEAD≠hub — skip reset (dirty)")
            continue
        reset = run(["git", "reset", "--hard", tip], slot)
        if reset.returncode != 0:
            skipped_other.append(name)
            if log_fn:
                log_fn(f"worktree pool: {name} reset failed ({(reset.stderr or '').strip()})")
            continue
        aligned.append(name)
        if log_fn:
            log_fn(f"worktree pool: {name} reset → hub tip {tip[:12]}")
    return {
        "aligned": aligned,
        "skipped_dirty": skipped_dirty,
        "skipped_other": skipped_other,
    }


def sync_pool_adapt_refuse_null(
    paths: Sequence[Path],
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[str]:
    """Copy hub ``automation_adapt.py`` into pool slots that still raw-dump null fp.

    Stale peer-N trees hub-anchor adapt-state to ``automation-hub`` but lack
    refuse-null ``save_adapt_state`` — one quick heal writes ``git_fingerprint:
    null`` and holds dispatch. Prefer hub scripts for CLI; this sync covers
    ``import automation_adapt`` from dirty worktrees that cannot hard-reset.
    """
    anchor = primary_worktree_root(hub, runner=runner)
    src = anchor / "scripts" / "automation_adapt.py"
    if not src.is_file():
        return []
    try:
        hub_text = src.read_text()
    except OSError as exc:
        if log_fn:
            log_fn(f"worktree pool: adapt sync skip ({exc})")
        return []
    marker = "Never write git_fingerprint: null"
    if marker not in hub_text:
        if log_fn:
            log_fn("worktree pool: hub automation_adapt.py missing refuse-null — skip sync")
        return []
    synced: list[str] = []
    for path in paths:
        slot = Path(path).resolve()
        name = slot.name
        dest = slot / "scripts" / "automation_adapt.py"
        if not dest.is_file():
            continue
        try:
            cur = dest.read_text()
        except OSError:
            continue
        if marker in cur:
            continue
        try:
            dest.write_text(hub_text)
        except OSError as exc:
            if log_fn:
                log_fn(f"worktree pool: {name} adapt sync failed ({exc})")
            continue
        synced.append(name)
        if log_fn:
            log_fn(f"worktree pool: {name} synced hub automation_adapt.py (refuse-null)")
    return synced


def _peer_worktree_source_complete(text: str) -> bool:
    """True when *text* can safely drive ensure-pool / pool sync (no re-poison)."""
    return (
        "_refuse_nested_pool_target" in text
        and "OVERSEER_SYNC_SIBLING_FALLBACK_2026_09_04" in text
        and "OVERSEER_SYNC_REFUSE_POISON_SOURCE_2026_09_04" in text
        and "OVERSEER_SYNC_POOL_TIP_FALLBACK_2026_09_04" in text
        # OVERSEER_HEAL_HUB_NEEDLE_SOT_2026_09_04 — without hub research/remote
        # SoT heal, Mac-clobbered hub tips re-seed false-eval on fresh slots.
        and "OVERSEER_HEAL_HUB_NEEDLE_SOT_2026_09_04" in text
        # OVERSEER_SYNC_LANDED_FLAW_NEEDLES_2026_09_04 — tip without LANDED
        # needle list skips peer-N sync → hub research re-poisons false-eval.
        and "OVERSEER_SYNC_LANDED_FLAW_NEEDLES_2026_09_04" in text
        # OVERSEER_SYNC_REFUSE_INCOMPLETE_SOURCE_2026_09_04 — full complete()
        # refuse (not SIBLING-only) so Mac tips cannot re-poison the pool.
        and "OVERSEER_SYNC_REFUSE_INCOMPLETE_SOURCE_2026_09_04" in text
    )


# OVERSEER_HEAL_VAULT_DONOR_2026_09_04 — Mac rsync --delete-before clobbers hub
# (and sometimes the running tip). When Path(__file__) is incomplete, fall back
# to hub-protect vault copies that carry SIBLING+REFUSE+POOL_TIP+HEAL.
_PEER_WORKTREE_VAULT_DONORS: tuple[Path, ...] = (
    Path.home() / ".config/automation-hub/hub-protect/scripts/peer_worktree.py",
    Path.home() / ".config/automation-hub/hub-protect/peer_worktree.py",
    Path.home() / ".config/automation-hub/hub-protect-vault/scripts/peer_worktree.py",
    Path.home() / ".config/automation-hub/vault/scripts/peer_worktree.py",
)


def _complete_peer_worktree_donor(preferred: Path | None = None) -> Path | None:
    """Return first complete peer_worktree.py among preferred, __file__, vaults."""
    cands: list[Path] = []
    if preferred is not None:
        cands.append(Path(preferred))
    cands.append(Path(__file__).resolve())
    cands.extend(_PEER_WORKTREE_VAULT_DONORS)
    seen: set[Path] = set()
    for cand in cands:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file():
            continue
        try:
            text = resolved.read_text()
        except OSError:
            continue
        if _peer_worktree_source_complete(text):
            return resolved
    return None


def heal_hub_peer_worktree_sot(
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
    donor: Path | None = None,
) -> bool:
    """Write complete donor ``peer_worktree.py`` onto hub primary when Mac-clobbered.

    OVERSEER_HEAL_HUB_PEER_WORKTREE_SOT_2026_09_04 — ``./scripts/peer ensure-pool``
    always prefers hub tip; a 58k clobber without SIBLING/REFUSE re-poisons pool
    false-eval needles. When the running (or explicit) donor is complete and hub
    primary is not, restore SoT before pool sync.

    OVERSEER_HEAL_VAULT_DONOR_2026_09_04 — if preferred/__file__ tip is incomplete
    (Mac clobber mid-cycle), use hub-protect vault donor instead of no-op.
    """
    anchor = primary_worktree_root(hub, runner=runner)
    hub_dest = Path(anchor) / "scripts" / "peer_worktree.py"
    preferred = Path(donor).resolve() if donor is not None else None
    src = _complete_peer_worktree_donor(preferred)
    if src is None:
        return False
    try:
        donor_text = src.read_text()
    except OSError:
        return False
    if not _peer_worktree_source_complete(donor_text):
        return False
    if hub_dest.is_file():
        try:
            if hub_dest.resolve() == src.resolve():
                return False
            cur = hub_dest.read_text()
        except OSError:
            cur = ""
        if _peer_worktree_source_complete(cur):
            return False
    try:
        hub_dest.parent.mkdir(parents=True, exist_ok=True)
        hub_dest.write_text(donor_text)
    except OSError as exc:
        if log_fn:
            log_fn(f"worktree pool: hub peer_worktree SoT heal failed ({exc})")
        return False
    if log_fn:
        log_fn("worktree pool: healed hub peer_worktree.py SoT (refuse-poison)")
    return True


def sync_pool_peer_worktree(
    paths: Sequence[Path],
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[str]:
    """Copy hub ``peer_worktree.py`` into slots missing ``_refuse_nested_pool_target``.

    Stale peer-N scripts (e.g. peer-31 at ~500 lines) can re-explode nested pools
    under themselves because they lack hub-anchor + refuse-nested guards.

    Prefer the executing module over ``hub/scripts/…`` — the primary checkout tip
    may lag a coding worktree that already has force-prune + refuse-nested.
    """
    # Heal clobbered hub SoT first so later hub-run ensure-pool stays complete.
    heal_hub_peer_worktree_sot(hub=hub, runner=runner, log_fn=log_fn)
    src = Path(__file__).resolve()
    if not src.is_file():
        anchor = primary_worktree_root(hub, runner=runner)
        src = anchor / "scripts" / "peer_worktree.py"
    if not src.is_file():
        return []
    try:
        hub_text = src.read_text()
    except OSError as exc:
        if log_fn:
            log_fn(f"worktree pool: peer_worktree sync skip ({exc})")
        return []
    marker = "_refuse_nested_pool_target"
    if marker not in hub_text:
        if log_fn:
            log_fn("worktree pool: peer_worktree.py missing refuse-nested — skip sync")
        return []
    # OVERSEER_SYNC_REFUSE_POISON_SOURCE_2026_09_04 — Mac/clobber hub tip without
    # SIBLING_FALLBACK must not overwrite pool slots (re-poison false eval path).
    # OVERSEER_SYNC_REFUSE_INCOMPLETE_SOURCE_2026_09_04 — SIBLING alone is not
    # enough: tips missing LANDED/POOL_TIP/HEAL still poison peer-{0,1,3,7}.
    # Prefer a complete donor over Path(__file__) when this module is incomplete
    # (hub-run ensure-pool after Mac clobber). Heal already restored hub SoT.
    if not _peer_worktree_source_complete(hub_text):
        donor = _complete_peer_worktree_donor(src)
        if donor is None:
            if log_fn:
                log_fn(
                    "worktree pool: peer_worktree.py incomplete source — "
                    "skip sync (refuse poison source)"
                )
            return []
        try:
            hub_text = donor.read_text()
            src = donor
        except OSError:
            if log_fn:
                log_fn(
                    "worktree pool: peer_worktree.py incomplete source — "
                    "skip sync (refuse poison source)"
                )
            return []
        if not _peer_worktree_source_complete(hub_text):
            if log_fn:
                log_fn(
                    "worktree pool: peer_worktree.py incomplete source — "
                    "skip sync (refuse poison source)"
                )
            return []
    synced: list[str] = []
    src_resolved = src.resolve()
    for path in paths:
        slot = Path(path).resolve()
        name = slot.name
        dest = slot / "scripts" / "peer_worktree.py"
        if not dest.is_file():
            continue
        try:
            if dest.resolve() == src_resolved:
                continue
        except OSError:
            pass
        try:
            cur = dest.read_text()
        except OSError:
            continue
        # Already has refuse-nested + force nested prune + hub-needle sync — skip.
        # Require sync_pool_hub_needle_scripts so lagging slots get false-eval fix.
        # OVERSEER_SYNC_REQUIRE_SIBLING_2026_09_04 — PATTERN_DEFS alone left peer-N
        # at 64k without SIBLING_FALLBACK → false eval() re-poison theater forever.
        # OVERSEER_SYNC_REQUIRE_REFUSE_POISON_2026_09_04 — slots lacking refuse-poison
        # must receive the donor that blocks Mac/clobber re-poison of the pool.
        # OVERSEER_SYNC_REQUIRE_FS_HEAD_2026_09_04 — vault_ok + pool skip require FS-HEAD.
        if (
            marker in cur
            and "force=True" in cur
            and "prune_nested_pool_pollution" in cur
            and "sync_pool_hub_needle_scripts" in cur
            and "_pool_hub_needle_source" in cur
            and "OVERSEER_STATIC_SKIP_PATTERN_DEFS_2026_09_04" in cur
            and "OVERSEER_SYNC_SIBLING_FALLBACK_2026_09_04" in cur
            and "OVERSEER_SYNC_REFUSE_POISON_SOURCE_2026_09_04" in cur
            and "OVERSEER_SYNC_POOL_TIP_FALLBACK_2026_09_04" in cur
            and "OVERSEER_SYNC_REQUIRE_FS_HEAD_2026_09_04" in cur
            and "OVERSEER_ALIGN_FS_HEAD_2026_09_04" in cur
            and "OVERSEER_HEAL_HUB_PEER_WORKTREE_SOT_2026_09_04" in cur
            and "OVERSEER_HEAL_HUB_NEEDLE_SOT_2026_09_04" in cur
            # OVERSEER_SYNC_REQUIRE_LANDED_FLAW_2026_09_04 — SIBLING+REFUSE+HEAL
            # without LANDED left peer-{0,1,3,7} never syncing theater skips.
            and "OVERSEER_SYNC_LANDED_FLAW_NEEDLES_2026_09_04" in cur
            # OVERSEER_SYNC_REQUIRE_REFUSE_INCOMPLETE_2026_09_04 — pre-complete
            # tips with SIBLING-only refuse still overwrite pool from Mac clobber.
            and "OVERSEER_SYNC_REFUSE_INCOMPLETE_SOURCE_2026_09_04" in cur
            # OVERSEER_SYNC_REQUIRE_PEER_LOOP_SOFT_2026_09_04 — without soft-exit
            # needles in the donor list, dirty peer-N kept hard agent-exit FAIL.
            and "OVERSEER_SYNC_PEER_LOOP_SOFT_EXIT_2026_09_04" in cur
            # OVERSEER_SYNC_REQUIRE_LAND_HOLD_MAC_PROTECT_2026_09_04 — without
            # land_hold needles, dirty tips never sync intentional_mac_clobber.
            and "OVERSEER_SYNC_LAND_HOLD_MAC_PROTECT_2026_09_04" in cur
        ):
            continue
        try:
            dest.write_text(hub_text)
        except OSError as exc:
            if log_fn:
                log_fn(f"worktree pool: {name} peer_worktree sync failed ({exc})")
            continue
        synced.append(name)
        if log_fn:
            log_fn(f"worktree pool: {name} synced peer_worktree.py (refuse-nested)")
    return synced


# OVERSEER_SYNC_HUB_NEEDLES_2026_09_04
# OVERSEER_SYNC_TRANSCRIPT_SCRUB_2026_09_04 — dirty slots skip hard-reset; copy hub
# scripts that still lack critical needles (false eval-call / hub-protect rewind).
# Needles MUST match live markers in peer_repo_research.py (PATTERN_DEFS +
# TITLE_ECHO). Invented FALSE_EVAL_ECHO/REPOISON_DOC names made
# _pool_hub_needle_source return None → stale peer-{0,1,3,7} never synced.
# Include FALSE_EVAL_ECHO + REPOISON_DOC so lagging hub tip cannot re-poison via
# incomplete TITLE_ECHO-only sync.
_POOL_HUB_NEEDLE_SCRIPTS: tuple[tuple[str, str], ...] = (
    ("peer_repo_research.py", "OVERSEER_STATIC_SKIP_EVAL_COMMENT_2026_09_04"),
    ("peer_repo_research.py", "OVERSEER_STATIC_SKIP_PATTERN_DEFS_2026_09_04"),
    ("peer_repo_research.py", "OVERSEER_STATIC_SKIP_TITLE_ECHO_2026_09_04"),
    ("peer_repo_research.py", "OVERSEER_STATIC_SKIP_FALSE_EVAL_ECHO_2026_09_04"),
    ("peer_repo_research.py", "OVERSEER_STATIC_SKIP_REPOISON_DOC_2026_09_04"),
    # OVERSEER_SYNC_POISON_SKIP_NEEDLES_2026_09_04 — lagging slots with only
    # STATIC_SKIP* looked "complete" and never got autoheal/poison enqueue skips.
    ("peer_repo_research.py", "OVERSEER_SKIP_AUTOHEAL_BOTTLENECK_2026_09_04"),
    ("peer_repo_research.py", "OVERSEER_SKIP_LAST_CYCLE_POISON_ENQUEUE_2026_09_04"),
    # OVERSEER_SYNC_LANDED_FLAW_NEEDLES_2026_09_04 — land-proof theater/reenqueue
    # skips; without these, STATIC_SKIP-only slots look complete and re-poison.
    ("peer_repo_research.py", "OVERSEER_SKIP_LANDED_FLAW_THEATER_2026_09_04"),
    ("peer_repo_research.py", "OVERSEER_SKIP_LANDED_FLAW_REENQUEUE_2026_09_04"),
    ("peer_remote.py", "OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04"),
    ("peer_remote.py", "notes/REPO_FLAW_RESEARCH.md"),
    # OVERSEER_SYNC_REMOTE_PROTECT_GAP_2026_09_04 — REPO_FLAW alone left peer-N
    # at older HUB_PROTECT list (no transcript/resource_priority) → Mac rsync
    # rewind + Path-local-import crash theater while needle-sync reported OK.
    ("peer_remote.py", "OVERSEER_PROTECT_TRANSCRIPT_SCRUB_2026_09_04"),
    ("peer_remote.py", "OVERSEER_PROTECT_RESOURCE_PRIORITY_2026_09_04"),
    ("peer_remote.py", "scripts/peer_transcript.py"),
    ("peer_remote.py", "scripts/dgx_resource_priority.py"),
    ("peer_pen_test.py", "OVERSEER_PEN_SKIP_CLOSED_2026_09_04"),
    ("peer_pen_test.py", "OVERSEER_PEN_SANITIZED_HTML_2026_09_04"),
    ("dgx_resource_priority.py", "OVERSEER_PATH_LOCAL_IMPORT_2026_09_04"),
    ("dgx_resource_priority.py", "OVERSEER_HUB_POLL_LATEST_2026_09_04"),
    # OVERSEER_SYNC_TRANSCRIPT_SCRUB_2026_09_04 — dirty pool skips hard-reset;
    # stale peer-N without scrub_last_cycle_poison re-seed fixture deferred poison.
    ("peer_transcript.py", "OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04"),
    ("peer_transcript.py", "scrub_last_cycle_poison"),
    ("peer_self_heal.py", "OVERSEER_HEAL_SCRUB_FALLBACK_2026_09_04"),
    ("peer_self_heal.py", "OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04"),
    # OVERSEER_SYNC_PEER_LOOP_SOFT_EXIT_2026_09_04 — dirty slots skipped hard-reset
    # and kept pre-soft peer_loop → cursor-agent non-zero stamped hard FAIL forever.
    ("peer_loop.py", "OVERSEER_AGENT_EXIT_SOFT_2026_09_04"),
    ("peer_loop.py", "OVERSEER_ATOMIC_DEFERRED_FT_2026_09_04"),
    # OVERSEER_SYNC_PEER_LINUX_INSTALL_2026_09_04 — EXIT_SOFT-only slots looked
    # complete so sync no-op'd; Linux cmd_install stayed launchctl-only on peer-N.
    ("peer_loop.py", "OVERSEER_PEER_LINUX_INSTALL_2026_09_04"),
    ("peer_loop.py", 'linux_install_daemon("peer")'),
    ("peer_agent_gates.py", "OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_2026_09_04"),
    ("peer_last_cycle_poison.py", "scrub_last_cycle_poison"),
    # OVERSEER_SYNC_SOFT_GREEN_NEEDLE_2026_09_04 — dirty slots skipped reset;
    # project_automation without NO_SHORT_SOFT_GREEN kept blanket len<24 false-green.
    ("project_automation.py", "OVERSEER_INCONCLUSIVE_NO_SHORT_SOFT_GREEN_2026_09_04"),
    # OVERSEER_SYNC_LAND_HOLD_MAC_PROTECT_2026_09_04 — dirty slots kept 2.5k
    # peer_land_hold without intentional_mac_clobber_protect → plan-gate HIGH
    # on WRAP stub during defend window; heal AttributeError → false-eval path
    # looks "blocked" while research needles are already live.
    ("peer_land_hold.py", "OVERSEER_MAC_CLOBBER_PROTECT_RESPECT_2026_09_04"),
    ("peer_land_hold.py", "def intentional_mac_clobber_protect"),
    ("peer_land_hold.py", "def restore_is_paused"),
)


def _pool_hub_needle_source(
    rel_name: str,
    needles: Sequence[str],
    *,
    hub: Path,
) -> tuple[Path, str] | None:
    """Prefer hub/scripts when complete; else sibling; else a complete pool tip.

    Primary checkout often lags a dirty peer worktree that already has false-eval
    skip needles. Never sync an incomplete source (would wipe ahead-of-hub slots).

    ``./scripts/peer ensure-pool`` always runs hub ``peer_worktree.py``, so
    ``Path(__file__).parent`` sibling is the hub scripts dir — useless when Mac
    clobbers hub tip. Scan ``hub/.worktrees/peer-*/scripts`` for a complete copy.
    """
    # OVERSEER_SYNC_HUB_PREFER_EXPLICIT_2026_09_04 — explicit complete hub wins.
    # OVERSEER_SYNC_SIBLING_FALLBACK_2026_09_04 — Mac/clobber incomplete primary
    # must fall through to complete sibling (coding tip). Ahead-of-hub slots stay
    # safe via all(needles in cur) skip in sync_pool_hub_needle_scripts.
    hub_src = Path(hub) / "scripts" / rel_name
    if hub_src.is_file():
        try:
            hub_text = hub_src.read_text()
        except OSError:
            hub_text = ""
        if hub_text and all(n in hub_text for n in needles):
            return hub_src, hub_text
        # Incomplete hub — try sibling / pool tips below (do not return None).
    sibling = Path(__file__).resolve().parent / rel_name
    if sibling.is_file():
        try:
            text = sibling.read_text()
        except OSError:
            text = ""
        if text and all(n in text for n in needles):
            return sibling, text
    # OVERSEER_SYNC_POOL_TIP_FALLBACK_2026_09_04 — hub-run ensure-pool sibling
    # is hub/scripts; find a complete peer-N tip under the pool directory.
    try:
        pool = _hub_pool_dir(Path(hub))
    except (TypeError, ValueError, OSError):
        pool = Path(hub) / ".worktrees"
    if pool.is_dir():
        for tip_scripts in sorted(pool.glob("peer-*/scripts")):
            cand = tip_scripts / rel_name
            if not cand.is_file():
                continue
            try:
                if hub_src.is_file() and cand.resolve() == hub_src.resolve():
                    continue
            except OSError:
                pass
            try:
                text = cand.read_text()
            except OSError:
                continue
            if text and all(n in text for n in needles):
                return cand, text
    return None


def sync_pool_hub_needle_scripts(
    paths: Sequence[Path],
    *,
    hub: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[str]:
    """Copy complete needle scripts into pool slots missing required OVERSEER needles.

    ``align_parallel_pool_to_hub`` skips dirty trees, so stale peer-N copies of
    ``peer_repo_research`` / ``peer_remote`` keep re-poisoning false eval-call flaws
    and rewinding hub-protect excludes. Sync by needle, not HEAD equality.

    Slots that already have every required needle are left alone (no hub-lag
    downgrade). Source prefers hub when complete, else ``scripts/`` next to this
    module when the primary tip is missing newer skip markers.
    """
    del runner  # API parity with sibling sync helpers
    # OVERSEER_SYNC_PATHS_COERCE_2026_09_04 — single Path must not iterate chars/parts.
    if isinstance(paths, (str, Path)):
        paths = [Path(paths)]
    elif paths is None:
        paths = []
    else:
        paths = [Path(p) for p in paths]
    anchor = primary_worktree_root(hub)
    synced: list[str] = []
    seen: set[tuple[str, str]] = set()
    rel_names = list(dict.fromkeys(rn for rn, _ in _POOL_HUB_NEEDLE_SCRIPTS))
    for rel_name in rel_names:
        needles_for = [n for rn, n in _POOL_HUB_NEEDLE_SCRIPTS if rn == rel_name]
        resolved = _pool_hub_needle_source(rel_name, needles_for, hub=anchor)
        if resolved is None:
            if log_fn:
                log_fn(
                    f"worktree pool: {rel_name} needle-sync skip "
                    f"(no complete source for {len(needles_for)} needle(s))"
                )
            continue
        src, hub_text = resolved
        # OVERSEER_HEAL_HUB_NEEDLE_SOT_2026_09_04 — Mac clobber leaves hub
        # peer_repo_research / peer_remote lagging (STATIC_SKIP without AUTOHEAL
        # / poison-enqueue skips). Fresh worktrees from hub tip re-poison false
        # eval until needle-sync; restore hub SoT from complete sibling/pool tip.
        hub_dest = Path(anchor) / "scripts" / rel_name
        if hub_dest.is_file():
            try:
                if hub_dest.resolve() != src.resolve():
                    cur_hub = hub_dest.read_text()
                    if not all(n in cur_hub for n in needles_for):
                        hub_dest.write_text(hub_text)
                        synced.append(f"hub/{rel_name}")
                        if log_fn:
                            log_fn(
                                f"worktree pool: healed hub {rel_name} SoT "
                                "(needle refuse-poison)"
                            )
            except OSError as exc:
                if log_fn:
                    log_fn(f"worktree pool: hub {rel_name} SoT heal failed ({exc})")
        for path in paths:
            slot = Path(path).resolve()
            name = slot.name
            key = (name, rel_name)
            if key in seen:
                continue
            dest = slot / "scripts" / rel_name
            if not dest.is_file():
                continue
            try:
                if dest.resolve() == src.resolve():
                    continue
            except OSError:
                pass
            try:
                cur = dest.read_text()
            except OSError:
                continue
            # Already protected — do not overwrite with lagging hub tip.
            if all(n in cur for n in needles_for):
                continue
            try:
                dest.write_text(hub_text)
            except OSError as exc:
                if log_fn:
                    log_fn(f"worktree pool: {name} {rel_name} needle-sync failed ({exc})")
                continue
            seen.add(key)
            synced.append(f"{name}/{rel_name}")
            if log_fn:
                log_fn(f"worktree pool: {name} synced {rel_name} (hub needle)")
    return synced


def ensure_parallel_pool(
    *,
    count: int | None = None,
    root: Path | None = None,
    runner: GitRunner | None = None,
    log_fn: Callable[[str], None] | None = None,
    align: bool = True,
    isolate_namespaces: bool = True,
    sync_adapt: bool = True,
    prune_nested: bool = True,
    prune_excess: bool = True,
    prune_dry_run: bool = False,
    force: bool = False,
) -> list[Path]:
    """Ensure ``peer-0`` … ``peer-N`` worktrees exist for 8 parallel Implement peers.

    Always anchors on the primary hub checkout so nested ``.worktrees/peer-N``
    agents do not create a second pool under themselves.

    Before ensure: prune nested ``peer-*/.worktrees/…`` pollution (unless
    ``prune_nested=False``) and retire excess hub ``peer-N`` with
    ``N >= max_parallel_peers`` (unless ``prune_excess=False``) so a prior
    inflated pool (e.g. 48 slots) cannot outlive the effective cap.

    After ensure: sync refuse-null adapt scripts, isolate namespaces (dirty
    slots that will skip align), soft-align clean slots to hub tip, then
    **re-isolate** — ``git reset --hard`` restores hub ``config_namespace``
    and would otherwise undo isolation (shared adapt-state / null fp poison).
    Extra registered trees (``peer-coding``, labeled slots, …) get the same
    align + re-isolate path so a clean divergent coding worktree cannot stay
    at ``HEAD≠hub`` after ``ensure-pool``.

    OVERSEER_POOL_ENSURE_FASTPATH_2026_09_06 — when ``force=False`` and the
    last full ensure is within ``POOL_ENSURE_FASTPATH_TTL_SEC`` and floor dirs
    exist **and** FS inventory is healthy (no nested/excess), skip prune/floor-align
    and only discover + align hub extras. Unhealthy inventory falls through to
    full ensure (OVERSEER_POOL_TTL_HEALTHY_INV_2026_09_06).
    """
    global _pool_ensure_fastpath_at
    floor = auto.parallel_peer_floor()
    cap = auto.max_parallel_peers()
    n = floor if count is None else count
    n = max(1, min(int(n), cap))
    rel_base, prefix = parallel_pool_config()
    # Hub-anchor even when caller ROOT is ``.worktrees/peer-3``.
    anchor = primary_worktree_root(root, runner=runner)

    # TTL fast-path: floor dirs ready + inventory healthy → skip prune / floor align.
    # OVERSEER_POOL_TTL_HEALTHY_INV_2026_09_06 — refuse dir-only skip when nested/excess.
    use_fastpath = (
        not force
        and _pool_ensure_ttl_warm()
        and _hub_parallel_floor_dirs_ready(anchor, n, rel_base=rel_base, prefix=prefix)
        and _pool_fs_inventory_healthy(
            anchor, cap=cap, rel_base=rel_base, prefix=prefix
        )
    )
    if use_fastpath:
        paths = [anchor / rel_base / f"{prefix}-{i}" for i in range(n)]
        age = time.monotonic() - _pool_ensure_fastpath_at
        if log_fn:
            log_fn(
                f"worktree pool: fast-path TTL "
                f"{POOL_ENSURE_FASTPATH_TTL_SEC:.0f}s age={age:.1f}s "
                f"(floor+healthy, skip prune/align)"
            )
        try:
            shared = list_worktrees(anchor, runner=runner)
        except (RuntimeError, OSError, FileNotFoundError):
            shared = []
        # Porcelain may still show pollution FS scan missed — abort to full ensure.
        if shared and not pool_inventory_healthy(shared, root=anchor, cap=cap):
            if log_fn:
                log_fn(
                    "worktree pool: fast-path aborted (porcelain unhealthy) — full ensure"
                )
        else:
            tip = _hub_tip_from_entries(anchor, shared) if shared else ""
            if not tip:
                tip = _git_head_sha_from_fs(anchor) or ""
            extras_aligned = 0
            if sync_adapt or isolate_namespaces or align:
                try:
                    extras = [Path(e.path) for e in parallel_entries(shared, root=anchor)]
                except (RuntimeError, OSError, FileNotFoundError):
                    extras = []
                pool_set = {Path(p).resolve() for p in paths}
                hub_wt = _hub_pool_dir(anchor).resolve()
                extra_only = [
                    p
                    for p in extras
                    if Path(p).resolve() not in pool_set
                    and Path(p).resolve().parent == hub_wt
                ]
                if extra_only:
                    if sync_adapt:
                        sync_pool_adapt_refuse_null(
                            extra_only, hub=anchor, runner=runner, log_fn=log_fn
                        )
                        sync_pool_peer_worktree(
                            extra_only, hub=anchor, runner=runner, log_fn=log_fn
                        )
                    if isolate_namespaces:
                        isolate_pool_adapt_namespaces(
                            extra_only, hub=anchor, runner=runner, log_fn=log_fn
                        )
                    extra_need_align = bool(align)
                    if (
                        extra_need_align
                        and tip
                        and shared
                        and _all_pool_heads_at_tip(extra_only, tip, shared)
                    ):
                        extra_need_align = False
                    if extra_need_align:
                        result = align_parallel_pool_to_hub(
                            extra_only, hub=anchor, runner=runner, log_fn=log_fn
                        )
                        aligned = (result or {}).get("aligned") or []
                        extras_aligned = len(aligned) if aligned else len(extra_only)
                        if isolate_namespaces:
                            isolate_pool_adapt_namespaces(
                                extra_only, hub=anchor, runner=runner, log_fn=log_fn
                            )
            if log_fn:
                log_fn(f"worktree pool: extras aligned={extras_aligned}")
            return paths

    # OVERSEER_HEAL_HUB_PEER_WORKTREE_SOT_2026_09_04 — restore clobbered hub tip
    # before pool sync so hub-run ensure-pool cannot re-poison false-eval slots.
    heal_hub_peer_worktree_sot(hub=anchor, runner=runner, log_fn=log_fn)
    # One porcelain list for prune + ensure slots + extras (stop 8× ensure_coding lists).
    try:
        shared = list_worktrees(anchor, runner=runner)
    except (RuntimeError, OSError, FileNotFoundError):
        shared = []
    pruned_removed = False
    if prune_nested:
        pruned = prune_nested_pool_pollution(
            root=anchor,
            dry_run=prune_dry_run,
            log_fn=log_fn,
            runner=runner,
            entries=shared,
        )
        if pruned.get("removed") and not prune_dry_run:
            pruned_removed = True
        if pruned.get("found") and log_fn:
            log_fn(
                f"worktree pool: nested pollution found={pruned['found']} "
                f"removed={len(pruned['removed'])} failed={len(pruned['failed'])}"
            )
    if prune_excess:
        excess = prune_excess_parallel_pool(
            root=anchor,
            cap=cap,
            dry_run=prune_dry_run,
            log_fn=log_fn,
            runner=runner,
            entries=shared,
        )
        if excess.get("removed") and not prune_dry_run:
            pruned_removed = True
        if (
            excess.get("found")
            or excess.get("orphans_found")
            or excess.get("empty_nests_found")
        ) and log_fn:
            log_fn(
                f"worktree pool: excess slots found={excess['found']} "
                f"removed={len(excess['removed'])} failed={len(excess['failed'])} "
                f"orphans={excess.get('orphans_found', 0)} "
                f"empty_nests={excess.get('empty_nests_found', 0)} "
                f"(cap {cap})"
            )
    # Refresh shared list only when prune actually removed git-registered trees.
    if pruned_removed:
        try:
            shared = list_worktrees(anchor, runner=runner)
        except (RuntimeError, OSError, FileNotFoundError):
            shared = []
    paths: list[Path] = []
    for i in range(n):
        rel = f"{rel_base}/{prefix}-{i}"
        branch = f"peer/{i}"
        try:
            paths.append(
                ensure_coding_worktree(
                    root=anchor,
                    rel_path=rel,
                    branch=branch,
                    runner=runner,
                    entries=shared,
                )
            )
        except RuntimeError as exc:
            if log_fn:
                log_fn(f"worktree pool: {prefix}-{i} skipped ({exc})")
    if paths and sync_adapt:
        sync_pool_adapt_refuse_null(
            paths, hub=anchor, runner=runner, log_fn=log_fn
        )
        sync_pool_peer_worktree(
            paths, hub=anchor, runner=runner, log_fn=log_fn
        )
        sync_pool_hub_needle_scripts(
            paths, hub=anchor, runner=runner, log_fn=log_fn
        )
    # Pre-align isolate: dirty slots skip reset but must not share hub ns.
    if paths and isolate_namespaces:
        isolate_pool_adapt_namespaces(
            paths, hub=anchor, runner=runner, log_fn=log_fn
        )
    # Skip align (+ post-align re-isolate) when shared porcelain already at tip.
    tip = _hub_tip_from_entries(anchor, shared) if shared else ""
    if not tip:
        tip = _git_head_sha_from_fs(anchor) or ""
    floor_need_align = bool(paths and align)
    if (
        floor_need_align
        and tip
        and shared
        and _all_pool_heads_at_tip(paths, tip, shared)
    ):
        floor_need_align = False
        if log_fn:
            log_fn("worktree pool: align skip (porcelain heads == hub tip)")
    if floor_need_align:
        align_parallel_pool_to_hub(
            paths, hub=anchor, runner=runner, log_fn=log_fn
        )
    # Re-isolate after align only: hard-reset restores hub automation.config.json.
    if paths and isolate_namespaces and floor_need_align:
        isolate_pool_adapt_namespaces(
            paths, hub=anchor, runner=runner, log_fn=log_fn
        )
    # Extra registered trees (peer-28, peer-coding, …) outside floor pool.
    # Must align like the floor — isolate/sync alone left clean peer-coding at HEAD≠hub.
    if sync_adapt or isolate_namespaces or align:
        try:
            extras = [
                Path(e.path)
                for e in parallel_entries(shared, root=anchor)
            ]
        except (RuntimeError, OSError, FileNotFoundError):
            extras = []
        pool_set = {Path(p).resolve() for p in paths}
        # Hub .worktrees only (peer-coding, peer-28, …). parallel_entries also
        # lists product trees (battery-peer, falcon-ai, …) — must not sync/align those.
        hub_wt = _hub_pool_dir(anchor).resolve()
        extra_only = [
            p
            for p in extras
            if Path(p).resolve() not in pool_set
            and Path(p).resolve().parent == hub_wt
        ]
        if extra_only:
            if sync_adapt:
                sync_pool_adapt_refuse_null(
                    extra_only, hub=anchor, runner=runner, log_fn=log_fn
                )
                sync_pool_peer_worktree(
                    extra_only, hub=anchor, runner=runner, log_fn=log_fn
                )
                sync_pool_hub_needle_scripts(
                    extra_only, hub=anchor, runner=runner, log_fn=log_fn
                )
            # Pre-align isolate: dirty extras skip reset but must not share hub ns.
            if isolate_namespaces:
                isolate_pool_adapt_namespaces(
                    extra_only, hub=anchor, runner=runner, log_fn=log_fn
                )
            extra_need_align = bool(align)
            if (
                extra_need_align
                and tip
                and shared
                and _all_pool_heads_at_tip(extra_only, tip, shared)
            ):
                extra_need_align = False
                if log_fn:
                    log_fn(
                        "worktree pool: extras align skip "
                        "(porcelain heads == hub tip)"
                    )
            if extra_need_align:
                align_parallel_pool_to_hub(
                    extra_only, hub=anchor, runner=runner, log_fn=log_fn
                )
            # Re-isolate after align: hard-reset restores hub automation.config.json.
            if isolate_namespaces and extra_need_align:
                isolate_pool_adapt_namespaces(
                    extra_only, hub=anchor, runner=runner, log_fn=log_fn
                )
    _pool_ensure_fastpath_at = time.monotonic()
    return paths


def inventory_snapshot(
    root: Path | None = None,
    *,
    ensure_pool: bool = False,
    log_fn: Callable[[str], None] | None = None,
    runner: GitRunner | None = None,
) -> dict[str, Any]:
    """Snapshot registered worktrees; optionally ensure (+prune) the parallel pool.

    ``peer_loop._emit_worktree_inventory`` calls this with ``ensure_pool=True`` so
    nested ``peer-*/.worktrees/…`` pollution is pruned inside ``ensure_parallel_pool``
    each continuous cycle — not only via CLI ``ensure-pool``.

    OVERSEER_POOL_ENSURE_FASTPATH_2026_09_06 — when ensure TTL is warm and floor
    dirs exist **and** FS inventory is healthy (nested=0, excess=0), defer porcelain
    entirely (no list_worktrees / ensure heavy path). Unhealthy inventory forces
    ensure so pollution cannot stick across TTL windows
    (OVERSEER_POOL_TTL_HEALTHY_INV_2026_09_06).
    """
    cwd = (root or ROOT).resolve()
    floor = auto.parallel_peer_floor()
    cap = auto.max_parallel_peers()
    rel_base, prefix = parallel_pool_config()
    try:
        anchor = primary_worktree_root(cwd, runner=runner)
    except Exception:  # noqa: BLE001
        anchor = cwd
    if (
        ensure_pool
        and _pool_ensure_ttl_warm()
        and _hub_parallel_floor_dirs_ready(
            anchor, floor, rel_base=rel_base, prefix=prefix
        )
        and _pool_fs_inventory_healthy(
            anchor, cap=cap, rel_base=rel_base, prefix=prefix
        )
    ):
        floor_paths = [
            anchor / rel_base / f"{prefix}-{i}" for i in range(floor)
        ]
        skew_rep = pool_tip_skew_report(floor_paths, hub=anchor, runner=runner)
        tip_ready = not (skew_rep.get("checked") and int(skew_rep.get("skew") or 0) > 0)
        if log_fn:
            log_fn(
                "worktree pool: porcelain deferred "
                f"(ensure fast-path TTL {POOL_ENSURE_FASTPATH_TTL_SEC:.0f}s; healthy)"
            )
            if not tip_ready:
                log_fn(
                    "worktree pool: tip_ready=false "
                    f"skew={skew_rep.get('skew')} matched={skew_rep.get('matched')} "
                    "(OVERSEER_POOL_READY_FAIL_CLOSED_TIP_2026_09_08)"
                )
        return {
            "ts": time.time(),
            "total": 0,
            "parallel_count": floor,
            "parallel_target": floor,
            "pool_ready": tip_ready,
            "pool_tip_skew": skew_rep,
            "porcelain_deferred": True,
            "inventory_healthy": True,
            "nested_pollution": 0,
            "parallel": [],
            "config": {
                "parallel_peer_floor": floor,
                "max_parallel_peers": cap,
            },
        }
    pool_paths: list[Path] = []
    if ensure_pool:
        try:
            pool_paths = ensure_parallel_pool(
                count=floor, root=cwd, runner=runner, log_fn=log_fn
            )
        except RuntimeError as exc:
            if log_fn:
                log_fn(f"worktree pool: ensure skipped ({exc})")
    try:
        entries = list_worktrees(cwd, runner=runner)
    except RuntimeError:
        entries = []
    extras = parallel_entries(entries, root=cwd)
    nested = nested_pool_pollution_count(entries, root=cwd)
    healthy = pool_inventory_healthy(entries, root=cwd, cap=auto.max_parallel_peers())
    parallel = [
        {"path": e.path, "branch": e.branch or "", "head": e.head or ""}
        for e in extras
    ]
    floor_ok = (len(pool_paths) >= floor) if ensure_pool else (len(extras) >= floor)
    skew_paths = (
        pool_paths
        if pool_paths
        else [anchor / rel_base / f"{prefix}-{i}" for i in range(floor)]
    )
    skew_rep = pool_tip_skew_report(skew_paths, hub=anchor, runner=runner)
    tip_ready = not (skew_rep.get("checked") and int(skew_rep.get("skew") or 0) > 0)
    if log_fn and not tip_ready:
        log_fn(
            "worktree pool: tip_ready=false "
            f"skew={skew_rep.get('skew')} matched={skew_rep.get('matched')} "
            "(OVERSEER_POOL_READY_FAIL_CLOSED_TIP_2026_09_08)"
        )
    return {
        "ts": time.time(),
        "total": len(entries),
        "parallel_count": len(extras),
        "parallel_target": floor,
        "pool_ready": bool(floor_ok and tip_ready),
        "pool_tip_skew": skew_rep,
        "porcelain_deferred": False,
        "inventory_healthy": healthy,
        "nested_pollution": nested,
        "parallel": parallel,
        "config": {
            "parallel_peer_floor": floor,
            "max_parallel_peers": auto.max_parallel_peers(),
        },
    }


def log_inventory(snapshot: dict[str, Any], log_fn: Callable[[str], None]) -> None:
    """Emit a short inventory line for peer_loop continuous logs."""
    total = snapshot.get("total", 0)
    parallel = snapshot.get("parallel_count", 0)
    target = snapshot.get("parallel_target", auto.parallel_peer_floor())
    nested = int(snapshot.get("nested_pollution") or 0)
    log_fn(
        f"worktree: {total} registered, {parallel} parallel "
        f"(target {target}+; nested={nested})"
    )
    for row in (snapshot.get("parallel") or [])[:6]:
        if isinstance(row, dict):
            path = row.get("path") or ""
            branch = row.get("branch") or "detached"
            log_fn(f"worktree: parallel {path} ({branch})")


def format_prompt_hint(
    entries: Sequence[WorktreeEntry] | None = None,
    *,
    root: Path | None = None,
) -> str:
    """Short harness hint so parallel Task peers prefer isolated worktrees."""
    cwd = (root or ROOT).resolve()
    try:
        rows = list(entries) if entries is not None else list_worktrees(cwd)
    except RuntimeError:
        return (
            "- Worktrees: inventory unavailable — "
            "use `python3 scripts/peer_worktree.py list` before parallel Implement peers."
        )
    extras = parallel_entries(rows, root=cwd)
    pool_n = len(extras)
    floor = auto.parallel_peer_floor()
    if pool_n >= floor:
        pool_note = f"{pool_n} parallel worktrees (≥{floor} peer target)"
    elif pool_n:
        pool_note = f"{pool_n} parallel — add more via peer_worktree pool (target {floor}+)"
    else:
        pool_note = f"only primary checkout — run peer_loop or `./scripts/peer spawn` / ensure-pool for {floor}+"
    if not extras:
        return (
            f"- Worktrees: {pool_note} — spawn one tree via "
            f"`./scripts/peer spawn --slot N` or "
            f"`python3 scripts/peer_worktree.py spawn --label task-name` "
            f"so parallel Implement peers do not collide."
        )
    shown = extras[:4]
    bits = ", ".join(
        f"{Path(e.path).name} ({e.branch or 'detached'})" for e in shown
    )
    more = f" (+{len(extras) - len(shown)} more)" if len(extras) > len(shown) else ""
    return (
        f"- Worktrees: {len(extras)} parallel available — {bits}{more}. "
        "Prefer one worktree per Implement Task peer when scopes are disjoint."
    )


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        entries = list_worktrees(Path(args.root) if args.root else None)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_list(entries))
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    try:
        argv = add_worktree(
            args.path,
            branch=args.branch,
            create_branch=args.create_branch,
            root=Path(args.root) if args.root else None,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prefix = "dry-run:" if args.dry_run else "ok:"
    print(f"{prefix} {shlex.join(argv)}")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    # Destructive: dry-run unless --execute.
    dry_run = not args.execute
    try:
        argv = remove_worktree(
            args.path,
            root=Path(args.root) if args.root else None,
            dry_run=dry_run,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prefix = "dry-run:" if dry_run else "ok:"
    print(f"{prefix} {shlex.join(argv)}")
    if dry_run:
        print("(pass --execute to run; never uses --force)", file=sys.stderr)
    return 0


def _cmd_spawn(args: argparse.Namespace) -> int:
    if args.slot is not None and args.label:
        print("error: use --slot or --label, not both", file=sys.stderr)
        return 1
    try:
        path = spawn_parallel_worktree(
            slot=args.slot,
            label=args.label,
            root=Path(args.root) if args.root else None,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prefix = "dry-run:" if args.dry_run else "ok:"
    print(f"{prefix} {path}")
    return 0


def _cmd_ensure_pool(args: argparse.Namespace) -> int:
    count = args.count
    root = Path(args.root) if args.root else None
    prune_dry = bool(getattr(args, "prune_dry_run", False))
    try:
        # Prune lives inside ensure_parallel_pool (peer_loop inventory path too).
        paths = ensure_parallel_pool(
            count=count,
            root=root,
            log_fn=lambda msg: print(msg, file=sys.stderr),
            prune_nested=True,
            prune_dry_run=prune_dry,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    skew_rep = pool_tip_skew_report(paths, hub=root, runner=None)
    tip_ready = not (skew_rep.get("checked") and int(skew_rep.get("skew") or 0) > 0)
    floor = auto.parallel_peer_floor()
    if tip_ready:
        print(f"ok: {len(paths)} worktree(s) ready (target {floor}+ peers)")
    else:
        print(
            f"warn: pool_skew head≠hub={skew_rep.get('skew')} "
            f"matched={skew_rep.get('matched')} "
            "(OVERSEER_POOL_READY_FAIL_CLOSED_TIP_2026_09_08)",
            file=sys.stderr,
        )
        print(
            f"ok: {len(paths)} worktree(s) floor (target {floor}+ peers) "
            "tip_ready=false"
        )
    for p in paths:
        print(p)
    left = nested_pool_pollution_count(root=root)
    return 0 if left == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="peer_worktree.py",
        description=(
            "Helpers for parallel-peer git worktrees. "
            "peer_loop inventories trees each continuous cycle; add/remove stay opt-in."
        ),
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Git repo root (default: Automation hub ROOT)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List worktrees (git worktree list --porcelain)")
    p_list.set_defaults(func=_cmd_list)

    p_spawn = sub.add_parser(
        "spawn",
        help="Spawn one parallel-peer worktree (optional --slot or --label)",
    )
    p_spawn.add_argument(
        "--slot",
        type=int,
        default=None,
        help="Pool slot index (peer-0, peer-1, …)",
    )
    p_spawn.add_argument(
        "--label",
        default=None,
        help="Ad-hoc task label (sanitized → peer-{label} path + branch)",
    )
    p_spawn.add_argument(
        "--dry-run",
        action="store_true",
        help="Print target path without creating the worktree",
    )
    p_spawn.set_defaults(func=_cmd_spawn)

    p_pool = sub.add_parser(
        "ensure-pool",
        help=f"Ensure .worktrees/peer-0..N for {auto.parallel_peer_floor()}+ parallel peers",
    )
    p_pool.add_argument(
        "--count",
        type=int,
        default=None,
        help=f"Pool size (default: parallel_peer_floor={auto.parallel_peer_floor()})",
    )
    p_pool.add_argument(
        "--prune-dry-run",
        action="store_true",
        help="List nested peer-*/.worktrees pollution without removing",
    )
    p_pool.set_defaults(func=_cmd_ensure_pool)

    p_add = sub.add_parser("add", help="Add a worktree (optional --dry-run)")
    p_add.add_argument("path", help="New worktree path")
    p_add.add_argument("--branch", default=None, help="Existing branch, or with -b a new branch name")
    p_add.add_argument(
        "-b",
        "--create-branch",
        action="store_true",
        help="Create a new branch (git worktree add -b)",
    )
    p_add.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the git command without running it",
    )
    p_add.set_defaults(func=_cmd_add)

    p_rm = sub.add_parser(
        "remove",
        help="Remove a worktree (dry-run by default; never --force)",
    )
    p_rm.add_argument("path", help="Worktree path to remove")
    p_rm.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print the git command without running (default)",
    )
    p_rm.add_argument(
        "--execute",
        action="store_true",
        help="Actually run git worktree remove (still never --force)",
    )
    p_rm.set_defaults(func=_cmd_remove)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
