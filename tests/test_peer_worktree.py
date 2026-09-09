"""Minimal unit tests for peer_worktree scaffold."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Sequence
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_worktree as wt  # noqa: E402


PORCELAIN = """\
worktree /repo
HEAD abcdef0123456789
branch refs/heads/main

worktree /repo/.worktrees/peer-a
HEAD fedcba9876543210
branch refs/heads/peer/a

worktree /repo/.worktrees/detached
HEAD 1122334455667788
detached

"""


class ParsePorcelainTests(unittest.TestCase):
    def test_parse_multiple_entries(self) -> None:
        entries = wt.parse_worktree_porcelain(PORCELAIN)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].path, "/repo")
        self.assertEqual(entries[0].branch, "main")
        self.assertEqual(entries[1].branch, "peer/a")
        self.assertTrue(entries[2].detached)
        self.assertEqual(entries[2].branch, "")


class PrimaryWorktreeTests(unittest.TestCase):
    def test_primary_worktree_root_first_entry(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "nested"
            nested.mkdir()
            hub = wt.primary_worktree_root(nested, runner=runner)
        self.assertEqual(hub, Path("/repo").resolve())

    def test_coding_worktree_path_uses_hub_not_nested_root(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "nested"
            nested.mkdir()
            path = wt.coding_worktree_path(root=nested, runner=runner)
        self.assertEqual(path, Path("/repo/.worktrees/peer-coding").resolve())


class ListAddRemoveTests(unittest.TestCase):
    def test_list_worktrees_uses_runner(self) -> None:
        calls: list[tuple[tuple[str, ...], Path]] = []

        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            calls.append((tuple(argv), cwd))
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = wt.list_worktrees(root, runner=runner)
        self.assertEqual(len(entries), 3)
        self.assertEqual(calls[0][0], ("git", "worktree", "list", "--porcelain"))
        self.assertEqual(calls[0][1], root.resolve())

    def test_add_dry_run_no_runner_call(self) -> None:
        runner = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = wt.add_worktree(
                "peer-wt",
                branch="feature/x",
                root=root,
                dry_run=True,
                runner=runner,
            )
        runner.assert_not_called()
        self.assertEqual(argv[:3], ["git", "worktree", "add"])
        self.assertIn(str((root / "peer-wt").resolve()), argv)
        self.assertIn("feature/x", argv)

    def test_add_create_branch_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = wt.add_worktree(
                "peer-wt",
                branch="peer/new",
                create_branch=True,
                root=root,
                dry_run=True,
            )
        self.assertIn("-b", argv)
        self.assertEqual(argv[argv.index("-b") + 1], "peer/new")

    def test_remove_defaults_to_dry_run(self) -> None:
        runner = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "peer-wt"
            argv = wt.remove_worktree(target, root=root, runner=runner)
        runner.assert_not_called()
        self.assertEqual(argv, ["git", "worktree", "remove", str(target.resolve())])
        self.assertNotIn("--force", argv)
        self.assertNotIn("-f", argv)

    def test_remove_execute_calls_runner_without_force(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            self.assertNotIn("--force", argv)
            self.assertNotIn("-f", argv)
            return subprocess.CompletedProcess(list(argv), 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "peer-wt"
            argv = wt.remove_worktree(target, root=root, dry_run=False, runner=runner)
        self.assertEqual(argv[0:3], ["git", "worktree", "remove"])

    def test_remove_failure_raises(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                list(argv), 1, stdout="", stderr="locked"
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(RuntimeError) as ctx:
                wt.remove_worktree("x", root=root, dry_run=False, runner=runner)
        self.assertIn("locked", str(ctx.exception))


class SpawnParallelWorktreeTests(unittest.TestCase):
    def test_spawn_by_slot_dry_run(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "nested"
            nested.mkdir()
            path = wt.spawn_parallel_worktree(3, root=nested, runner=runner, dry_run=True)
        self.assertEqual(path, Path("/repo/.worktrees/peer-3").resolve())

    def test_spawn_by_label_sanitizes(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "nested"
            nested.mkdir()
            path = wt.spawn_parallel_worktree(
                label="fix auth flow",
                root=nested,
                runner=runner,
                dry_run=True,
            )
        self.assertEqual(path, Path("/repo/.worktrees/peer-fix-auth-flow").resolve())

    def test_spawn_returns_existing(self) -> None:
        porcelain = (
            "worktree /repo\nHEAD aaa\nbranch refs/heads/main\n\n"
            "worktree /repo/.worktrees/peer-2\nHEAD bbb\nbranch refs/heads/peer/2\n\n"
        )

        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=porcelain, stderr="")

        path = wt.spawn_parallel_worktree(2, root=Path("/repo"), runner=runner)
        self.assertEqual(path, Path("/repo/.worktrees/peer-2").resolve())

    def test_next_free_slot_skips_used(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        slot = wt._next_free_slot(root=Path("/repo"), runner=runner)
        self.assertEqual(slot, 0)

    def test_spawn_explicit_slot_refuses_at_or_above_cap(self) -> None:
        """slot=N must not bypass max_parallel_peers (recreates peer-cap after GC)."""

        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with mock.patch.object(wt.auto, "max_parallel_peers", return_value=8):
            with self.assertRaises(RuntimeError) as ctx:
                wt.spawn_parallel_worktree(
                    8, root=Path("/repo"), runner=runner, dry_run=True
                )
            self.assertIn("refuse slot 8", str(ctx.exception))
            self.assertIn("[0, 8)", str(ctx.exception))
            with self.assertRaises(RuntimeError) as ctx47:
                wt.spawn_parallel_worktree(
                    47, root=Path("/repo"), runner=runner, dry_run=True
                )
            self.assertIn("refuse slot 47", str(ctx47.exception))
            # In-range still allowed.
            path = wt.spawn_parallel_worktree(
                7, root=Path("/repo"), runner=runner, dry_run=True
            )
        self.assertEqual(path, Path("/repo/.worktrees/peer-7").resolve())

    def test_spawn_numeric_label_refuses_above_cap(self) -> None:
        """Pure-numeric label is a slot alias — same cap refuse as --slot."""

        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with mock.patch.object(wt.auto, "max_parallel_peers", return_value=8):
            with self.assertRaises(RuntimeError) as ctx:
                wt.spawn_parallel_worktree(
                    label="47",
                    root=Path("/repo"),
                    runner=runner,
                    dry_run=True,
                )
            self.assertIn("refuse slot 47", str(ctx.exception))
            ok = wt.spawn_parallel_worktree(
                label="3",
                root=Path("/repo"),
                runner=runner,
                dry_run=True,
            )
        self.assertEqual(ok, Path("/repo/.worktrees/peer-3").resolve())

    def test_spawn_cli_dry_run(self) -> None:
        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=PORCELAIN, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with unittest.mock.patch.object(wt, "_default_runner", runner):
                code = wt.main(["--root", str(root), "spawn", "--slot", "1", "--dry-run"])
        self.assertEqual(code, 0)


class CliHelpTests(unittest.TestCase):
    def test_build_parser_has_subcommands(self) -> None:
        parser = wt.build_parser()
        help_text = parser.format_help()
        self.assertIn("list", help_text)
        self.assertIn("spawn", help_text)
        self.assertIn("add", help_text)
        self.assertIn("remove", help_text)

    def test_main_help_exits_zero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            wt.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_remove_cli_dry_run_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = wt.main(["--root", str(root), "remove", "peer-wt"])
        self.assertEqual(code, 0)


class PromptHintTests(unittest.TestCase):
    def test_format_prompt_hint_primary_only(self) -> None:
        entries = [
            wt.WorktreeEntry(path="/repo", head="abc", branch="main"),
        ]
        hint = wt.format_prompt_hint(entries, root=Path("/repo"))
        self.assertIn("spawn", hint)

    def test_format_prompt_hint_lists_parallel(self) -> None:
        entries = [
            wt.WorktreeEntry(path="/repo", head="abc", branch="main"),
            wt.WorktreeEntry(path="/repo/.worktrees/peer-a", head="def", branch="peer/a"),
        ]
        hint = wt.format_prompt_hint(entries, root=Path("/repo"))
        self.assertIn("parallel available", hint)
        self.assertIn("peer-a", hint)


class EnsureCodingWorktreeTests(unittest.TestCase):
    def test_returns_existing_registered_path(self) -> None:
        porcelain = (
            "worktree /repo\nHEAD aaa\nbranch refs/heads/main\n\n"
            "worktree /repo/.worktrees/peer-coding\nHEAD bbb\nbranch refs/heads/peer/coding\n\n"
        )

        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=porcelain, stderr="")

        path = wt.ensure_coding_worktree(
            root=Path("/repo"),
            rel_path=".worktrees/peer-coding",
            branch="peer/coding",
            runner=runner,
        )
        self.assertEqual(path, Path("/repo/.worktrees/peer-coding").resolve())

    def test_creates_when_missing(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            calls.append(tuple(argv))
            if argv[:3] == ("git", "worktree", "list"):
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout="worktree /repo\nHEAD aaa\nbranch refs/heads/main\n\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = wt.ensure_coding_worktree(
                root=root,
                rel_path=".worktrees/peer-coding",
                branch="peer/coding",
                runner=runner,
            )
        self.assertTrue(str(path).endswith(".worktrees/peer-coding"))
        self.assertTrue(any(c[:3] == ("git", "worktree", "add") for c in calls))

    def test_continue_on_dirty_defaults(self) -> None:
        self.assertTrue(wt.continue_on_dirty_enabled())
        self.assertGreaterEqual(wt.dirty_wait_sec(), 0.0)

    def test_solved_dirty_dispatch_item_when_enabled(self) -> None:
        dirty = (
            "Unblock dirty tree for peer_loop dispatch — git: 20 changed path(s) "
            "— continue_on_dirty keeps coding"
        )
        with mock.patch.object(wt, "continue_on_dirty_enabled", return_value=True):
            self.assertTrue(wt.solved_dirty_dispatch_item(dirty))
            self.assertFalse(wt.solved_dirty_dispatch_item("Dirty-tree hygiene — optional stash"))
            self.assertFalse(wt.solved_dirty_dispatch_item("Harden grounded loop"))
        with mock.patch.object(wt, "continue_on_dirty_enabled", return_value=False):
            self.assertFalse(wt.solved_dirty_dispatch_item(dirty))


class NestedPoolPollutionTests(unittest.TestCase):
    def test_refuse_nested_pool_target(self) -> None:
        hub = Path("/repo")
        nested = Path("/repo/.worktrees/peer-31/.worktrees/peer-0")
        with self.assertRaises(RuntimeError) as ctx:
            wt._refuse_nested_pool_target(nested, hub=hub)
        self.assertIn("refuse nested", str(ctx.exception))

    def test_nested_pollution_count(self) -> None:
        entries = [
            wt.WorktreeEntry(path="/repo", head="a", branch="main"),
            wt.WorktreeEntry(path="/repo/.worktrees/peer-0", head="b", branch="peer/0"),
            wt.WorktreeEntry(
                path="/repo/.worktrees/peer-5/.worktrees/peer-1",
                head="c",
                branch="peer-1",
            ),
            wt.WorktreeEntry(
                path="/repo/.worktrees/peer-5/.worktrees/peer-coding",
                head="d",
                branch="peer/coding",
            ),
        ]
        self.assertEqual(wt.nested_pool_pollution_count(entries, root=Path("/repo")), 2)

    def test_prune_nested_pool_pollution_dry_run(self) -> None:
        nested = Path("/repo/.worktrees/peer-5/.worktrees/peer-1")
        with mock.patch.object(
            wt, "list_nested_pool_pollution", return_value=[nested]
        ), mock.patch.object(
            wt, "remove_worktree", return_value=["git", "worktree", "remove", str(nested)]
        ) as remove, mock.patch.object(
            wt, "primary_worktree_root", return_value=Path("/repo")
        ):
            logs: list[str] = []
            out = wt.prune_nested_pool_pollution(
                root=Path("/repo"), dry_run=True, log_fn=logs.append
            )
        self.assertEqual(out["found"], 1)
        self.assertEqual(out["removed"], [str(nested)])
        self.assertEqual(out["failed"], [])
        remove.assert_called_once()
        self.assertTrue(remove.call_args.kwargs.get("force") is True)
        self.assertTrue(any("would prune" in line for line in logs))

    def test_prune_excess_parallel_pool_defaults_force(self) -> None:
        """Dirty peer-N (N>=cap) must retire with --force — else 40 excess stick forever."""
        excess = Path("/hub/.worktrees/peer-40")
        with mock.patch.object(
            wt, "list_excess_parallel_slots", return_value=[excess]
        ), mock.patch.object(
            wt,
            "remove_worktree",
            return_value=["git", "worktree", "remove", "--force", str(excess)],
        ) as remove, mock.patch.object(
            wt, "primary_worktree_root", return_value=Path("/hub")
        ), mock.patch.object(wt.auto, "max_parallel_peers", return_value=8):
            logs: list[str] = []
            out = wt.prune_excess_parallel_pool(
                root=Path("/hub"), cap=8, dry_run=False, log_fn=logs.append
            )
        self.assertEqual(out["found"], 1)
        self.assertEqual(out["removed"], [str(excess)])
        self.assertEqual(out["failed"], [])
        self.assertTrue(out["force"])
        remove.assert_called_once()
        self.assertTrue(remove.call_args.kwargs.get("force") is True)
        self.assertTrue(any("--force" in line for line in logs))

    def test_ensure_parallel_pool_anchors_hub_from_nested_cwd(self) -> None:
        """ensure-pool from .worktrees/peer-N must create under hub, not nest."""
        seen_roots: list[Path] = []

        def fake_ensure(**kwargs):  # type: ignore[no-untyped-def]
            root = Path(kwargs["root"]).resolve()
            seen_roots.append(root)
            rel = kwargs["rel_path"]
            return (root / rel).resolve()

        with mock.patch.object(wt, "_git_common_dir", return_value=Path("/hub/.git")), mock.patch.object(
            wt, "ensure_coding_worktree", side_effect=fake_ensure
        ), mock.patch.object(
            wt,
            "prune_nested_pool_pollution",
            return_value={"found": 0, "removed": [], "failed": [], "dry_run": False},
        ) as prune, mock.patch.object(
            wt,
            "prune_excess_parallel_pool",
            return_value={
                "found": 0,
                "removed": [],
                "failed": [],
                "dry_run": False,
                "cap": 8,
                "force": True,
            },
        ):
            paths = wt.ensure_parallel_pool(
                count=2,
                root=Path("/hub/.worktrees/peer-31"),
                runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""),
            )
        prune.assert_called_once()
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(r == Path("/hub").resolve() for r in seen_roots))
        self.assertTrue(all(str(p).startswith("/hub/.worktrees/peer-") for p in paths))
        self.assertTrue(all(p.parts.count(".worktrees") == 1 for p in paths))

    def test_ensure_parallel_pool_prunes_nested_by_default(self) -> None:
        """peer_loop inventory → ensure_parallel_pool must prune (not CLI-only)."""
        prune_calls: list[dict[str, object]] = []

        def fake_prune(**kwargs):  # type: ignore[no-untyped-def]
            prune_calls.append(dict(kwargs))
            return {
                "found": 2,
                "removed": ["a", "b"],
                "failed": [],
                "dry_run": False,
            }

        def fake_ensure(**kwargs):  # type: ignore[no-untyped-def]
            root = Path(kwargs["root"]).resolve()
            return (root / kwargs["rel_path"]).resolve()

        logs: list[str] = []
        with mock.patch.object(wt, "_git_common_dir", return_value=Path("/hub/.git")), mock.patch.object(
            wt, "ensure_coding_worktree", side_effect=fake_ensure
        ), mock.patch.object(wt, "prune_nested_pool_pollution", side_effect=fake_prune), mock.patch.object(
            wt,
            "prune_excess_parallel_pool",
            return_value={
                "found": 0,
                "removed": [],
                "failed": [],
                "dry_run": False,
                "cap": 8,
                "force": True,
            },
        ):
            paths = wt.ensure_parallel_pool(
                count=1,
                root=Path("/hub/.worktrees/peer-3"),
                log_fn=logs.append,
                align=False,
                isolate_namespaces=False,
                sync_adapt=False,
            )
        self.assertEqual(len(paths), 1)
        self.assertEqual(len(prune_calls), 1)
        self.assertEqual(Path(str(prune_calls[0]["root"])).resolve(), Path("/hub").resolve())
        self.assertFalse(prune_calls[0]["dry_run"])
        self.assertTrue(any("nested pollution found=2" in line for line in logs))

    def test_list_excess_parallel_slots_beyond_cap(self) -> None:
        """Numbered peer-N with N>=cap are excess; labeled trees are not."""
        porcelain = """\
worktree /hub
HEAD abcdef0123456789
branch refs/heads/main

worktree /hub/.worktrees/peer-0
HEAD aaaaaaaaaaaaaaaa
branch refs/heads/peer/0

worktree /hub/.worktrees/peer-7
HEAD bbbbbbbbbbbbbbbb
branch refs/heads/peer/7

worktree /hub/.worktrees/peer-8
HEAD cccccccccccccccc
branch refs/heads/peer/8

worktree /hub/.worktrees/peer-47
HEAD dddddddddddddddd
branch refs/heads/peer/47

worktree /hub/.worktrees/peer-coding
HEAD eeeeeeeeeeeeeeee
branch refs/heads/peer/coding
"""
        entries = wt.parse_worktree_porcelain(porcelain)
        with mock.patch.object(wt.auto, "max_parallel_peers", return_value=8), mock.patch.object(
            wt, "primary_worktree_root", return_value=Path("/hub")
        ), mock.patch.object(
            wt,
            "is_hub_pool_path",
            side_effect=lambda p, hub=None: str(p).startswith("/hub/.worktrees/peer-")
            and str(p).count(".worktrees") == 1,
        ):
            excess = wt.list_excess_parallel_slots(entries, root=Path("/hub"), cap=8)
        names = [p.name for p in excess]
        self.assertEqual(names, ["peer-8", "peer-47"])
        self.assertNotIn("peer-coding", names)
        self.assertNotIn("peer-7", names)

    def test_prune_excess_reaps_orphan_dirs_and_empty_nests(self) -> None:
        """Unregistered peer-N (no .git) + empty nested .worktrees must not stick.

        list_excess is porcelain-only — leftover dirs after git prune stay on disk.
        """
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            pool = hub / ".worktrees"
            (pool / "peer-0").mkdir(parents=True)
            (pool / "peer-1").mkdir()
            empty_nest = pool / "peer-1" / ".worktrees"
            empty_nest.mkdir()
            (pool / "peer-3").mkdir()
            (pool / "peer-3" / ".worktrees").mkdir()
            orphan = pool / "peer-20"
            orphan.mkdir()
            (orphan / "notes").mkdir()
            (orphan / "notes" / "leftover.md").write_text("orphan\n")
            floor_nogit = pool / "peer-5"
            floor_nogit.mkdir()
            labeled = pool / "peer-coding"
            labeled.mkdir()
            logs: list[str] = []
            out = wt.prune_excess_parallel_pool(
                root=hub, cap=8, dry_run=False, log_fn=logs.append
            )
            self.assertEqual(out["found"], 0)
            self.assertEqual(out["orphans_found"], 1)
            self.assertEqual(out["empty_nests_found"], 2)
            self.assertEqual(len(out["orphans_removed"]), 1)
            self.assertEqual(len(out["empty_nests_removed"]), 2)
            self.assertEqual(out["failed"], [])
            self.assertFalse(orphan.exists())
            self.assertFalse(empty_nest.exists())
            self.assertFalse((pool / "peer-3" / ".worktrees").exists())
            self.assertTrue((pool / "peer-0").is_dir())
            self.assertTrue((pool / "peer-1").is_dir())
            self.assertTrue((pool / "peer-3").is_dir())
            self.assertTrue(floor_nogit.is_dir())
            self.assertTrue(labeled.is_dir())
            self.assertTrue(any("reaped orphan excess peer-20" in line for line in logs))
            self.assertTrue(any("rmdir empty nested" in line for line in logs))

    def test_prune_excess_orphan_dry_run_does_not_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            orphan = hub / ".worktrees" / "peer-20"
            nest = hub / ".worktrees" / "peer-1" / ".worktrees"
            orphan.mkdir(parents=True)
            nest.mkdir(parents=True)
            out = wt.prune_excess_parallel_pool(root=hub, cap=8, dry_run=True)
            self.assertTrue(orphan.is_dir())
            self.assertTrue(nest.is_dir())
            self.assertEqual(out["orphans_found"], 1)
            self.assertEqual(out["empty_nests_found"], 1)
            self.assertTrue(out["dry_run"])

    def test_ensure_parallel_pool_prunes_excess_beyond_cap(self) -> None:
        """Cap shrink must retire peer-N (N>=max) inside ensure-pool — not leave 48 live."""
        removed: list[str] = []

        def fake_ensure(**kwargs):  # type: ignore[no-untyped-def]
            root = Path(kwargs["root"]).resolve()
            return (root / kwargs["rel_path"]).resolve()

        def fake_prune_excess(**kwargs):  # type: ignore[no-untyped-def]
            removed.append(str(kwargs.get("cap")))
            return {
                "found": 40,
                "removed": [f"/hub/.worktrees/peer-{i}" for i in range(8, 48)],
                "failed": [],
                "dry_run": False,
                "cap": kwargs.get("cap"),
                "force": True,
            }

        logs: list[str] = []
        with mock.patch.object(wt, "_git_common_dir", return_value=Path("/hub/.git")), mock.patch.object(
            wt.auto, "max_parallel_peers", return_value=8
        ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=8), mock.patch.object(
            wt, "ensure_coding_worktree", side_effect=fake_ensure
        ), mock.patch.object(
            wt,
            "prune_nested_pool_pollution",
            return_value={"found": 0, "removed": [], "failed": [], "dry_run": False},
        ), mock.patch.object(
            wt, "prune_excess_parallel_pool", side_effect=fake_prune_excess
        ) as excess:
            paths = wt.ensure_parallel_pool(
                count=8,
                root=Path("/hub"),
                log_fn=logs.append,
                align=False,
                isolate_namespaces=False,
                sync_adapt=False,
            )
        self.assertEqual(len(paths), 8)
        excess.assert_called_once()
        self.assertEqual(excess.call_args.kwargs.get("cap"), 8)
        self.assertEqual(removed, ["8"])
        self.assertTrue(
            any("excess slots found=40" in line and "removed=40" in line for line in logs)
        )

    def test_refuse_slot_out_of_cap_clamps_spawn(self) -> None:
        """spawn(slot=N) must refuse N outside [0, max_parallel_peers)."""
        with mock.patch.object(wt.auto, "max_parallel_peers", return_value=8):
            with self.assertRaises(RuntimeError) as ctx:
                wt._refuse_slot_out_of_cap(8)
            self.assertIn("max_parallel_peers=8", str(ctx.exception))
            with self.assertRaises(RuntimeError):
                wt._refuse_slot_out_of_cap(47)
            wt._refuse_slot_out_of_cap(0)
            wt._refuse_slot_out_of_cap(7)

    def test_isolate_pool_adapt_namespaces_rewrites_shared_hub_ns(self) -> None:
        """Isolate via gitignored local.json — tracked config stays clean."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            hub.mkdir()
            (hub / "automation.config.json").write_text(
                json.dumps({"config_namespace": "automation-hub"}) + "\n"
            )
            slot = hub / ".worktrees" / "peer-0"
            slot.mkdir(parents=True)
            cfg = slot / "automation.config.json"
            before = json.dumps({"config_namespace": "automation-hub", "x": 1}) + "\n"
            cfg.write_text(before)
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub):
                changed = wt.isolate_pool_adapt_namespaces([slot], hub=hub)
            self.assertEqual(changed, ["peer-0"])
            # Tracked config untouched (align must not see permanent dirty).
            self.assertEqual(cfg.read_text(), before)
            local = json.loads((slot / "automation.config.local.json").read_text())
            self.assertEqual(local["config_namespace"], "peer-0")
            self.assertEqual(wt._slot_effective_namespace(slot), "peer-0")

    def test_align_parallel_pool_skips_dirty(self) -> None:
        """Dirty slots must not hard-reset; clean divergent slots align to hub tip."""
        calls: list[tuple[tuple[str, ...], str]] = []

        def fake_run(argv, cwd):  # type: ignore[no-untyped-def]
            calls.append((tuple(argv), str(cwd)))
            if argv[:2] == ["git", "rev-parse"] and argv[2] == "HEAD":
                if "hub" in str(cwd) and "peer" not in Path(cwd).name:
                    return subprocess.CompletedProcess(argv, 0, "hubtipdeadbeef\n", "")
                return subprocess.CompletedProcess(argv, 0, "staletipaaaaaaa\n", "")
            if argv[:2] == ["git", "status"]:
                # peer-0 dirty, peer-1 clean
                out = " M notes/x.md\n" if Path(cwd).name == "peer-0" else ""
                return subprocess.CompletedProcess(argv, 0, out, "")
            if argv[:2] == ["git", "reset"]:
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 1, "", "unexpected")

        hub = Path("/tmp/hub-align")
        p0 = hub / ".worktrees" / "peer-0"
        p1 = hub / ".worktrees" / "peer-1"
        with mock.patch.object(wt, "primary_worktree_root", return_value=hub):
            out = wt.align_parallel_pool_to_hub([p0, p1], hub=hub, runner=fake_run)
        self.assertEqual(out["aligned"], ["peer-1"])
        self.assertEqual(out["skipped_dirty"], ["peer-0"])
        self.assertTrue(any(c[0][:3] == ("git", "reset", "--hard") for c in calls))

    def test_ensure_parallel_pool_aligns_extra_coding(self) -> None:
        """Clean peer-coding outside floor must get align_parallel_pool_to_hub.

        Product worktrees outside hub/.worktrees must NOT be in extras sync/align
        (extra_only hub-pool-scoped).
        """
        align_batches: list[list[str]] = []
        sync_batches: list[list[str]] = []

        def fake_ensure(**kwargs):  # type: ignore[no-untyped-def]
            root = Path(kwargs["root"]).resolve()
            return (root / kwargs["rel_path"]).resolve()

        def fake_align(paths, **kwargs):  # type: ignore[no-untyped-def]
            names = [Path(p).name for p in paths]
            align_batches.append(names)
            return {"aligned": names, "skipped_dirty": [], "skipped_other": []}

        def fake_sync(paths, **kwargs):  # type: ignore[no-untyped-def]
            names = [Path(p).name for p in paths]
            sync_batches.append(names)
            return names

        coding = Path("/hub/.worktrees/peer-coding")
        floor0 = Path("/hub/.worktrees/peer-0")
        product = Path("/other/battery-peer-l3-25")
        entries = [
            wt.WorktreeEntry(path="/hub", head="hubtip", branch="main"),
            wt.WorktreeEntry(path=str(floor0), head="a", branch="peer/0"),
            wt.WorktreeEntry(path=str(coding), head="stale", branch="peer/coding"),
            wt.WorktreeEntry(path=str(product), head="x", branch="peer/l3"),
        ]

        with mock.patch.object(wt, "_git_common_dir", return_value=Path("/hub/.git")), mock.patch.object(
            wt, "ensure_coding_worktree", side_effect=fake_ensure
        ), mock.patch.object(
            wt,
            "prune_nested_pool_pollution",
            return_value={"found": 0, "removed": [], "failed": [], "dry_run": False},
        ), mock.patch.object(
            wt,
            "prune_excess_parallel_pool",
            return_value={
                "found": 0,
                "removed": [],
                "failed": [],
                "dry_run": False,
                "cap": 8,
                "force": True,
            },
        ), mock.patch.object(wt, "list_worktrees", return_value=entries), mock.patch.object(
            wt, "align_parallel_pool_to_hub", side_effect=fake_align
        ), mock.patch.object(
            wt, "isolate_pool_adapt_namespaces", return_value=[]
        ), mock.patch.object(
            wt, "sync_pool_adapt_refuse_null", side_effect=fake_sync
        ), mock.patch.object(wt, "sync_pool_peer_worktree", side_effect=fake_sync):
            paths = wt.ensure_parallel_pool(
                count=1,
                root=Path("/hub"),
                runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""),
            )
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].name, "peer-0")
        # Floor batch + extras batch (peer-coding must be aligned, not only isolated).
        self.assertGreaterEqual(len(align_batches), 2)
        self.assertIn(["peer-0"], align_batches)
        self.assertTrue(any("peer-coding" in batch for batch in align_batches))
        extras_batch = next(b for b in align_batches if "peer-coding" in b)
        self.assertNotIn("peer-0", extras_batch)
        # Product trees outside hub/.worktrees must never sync/align.
        flat_align = [n for b in align_batches for n in b]
        flat_sync = [n for b in sync_batches for n in b]
        self.assertNotIn("battery-peer-l3-25", flat_align)
        self.assertNotIn("battery-peer-l3-25", flat_sync)

    def test_sync_pool_adapt_refuse_null_copies_hub_script(self) -> None:
        """Pool slots lacking refuse-null must receive hub automation_adapt.py."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            slot = hub / ".worktrees" / "peer-0"
            (hub / "scripts").mkdir(parents=True)
            (slot / "scripts").mkdir(parents=True)
            hub_adapt = hub / "scripts" / "automation_adapt.py"
            hub_adapt.write_text(
                "def save_adapt_state(root, state):\n"
                "    '''Never write git_fingerprint: null'''\n"
                "    pass\n"
            )
            dest = slot / "scripts" / "automation_adapt.py"
            dest.write_text("def save_adapt_state(root, state):\n    pass\n")
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub):
                synced = wt.sync_pool_adapt_refuse_null([slot], hub=hub)
            self.assertEqual(synced, ["peer-0"])
            self.assertIn("Never write git_fingerprint: null", dest.read_text())


if __name__ == "__main__":
    unittest.main()
