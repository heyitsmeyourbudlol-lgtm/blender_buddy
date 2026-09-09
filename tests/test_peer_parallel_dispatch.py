#!/usr/bin/env python3
"""Tests for parallel niche cursor-agent dispatch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_parallel_dispatch as ppd  # noqa: E402
import peer_roles as roles  # noqa: E402


def _role(rid: str, title: str | None = None) -> roles.AgentRole:
    return roles.AgentRole(
        id=rid,
        job_title=title or rid.replace("_", " ").title(),
        subagent_type="generalPurpose",
        model="inherit",
        strengths=("peer_loop",),
        responsibilities="Kit Python.",
        reads=("notes/AUTOMATION.md",),
    )


def _asn(rid: str, item: str) -> roles.RoleAssignment:
    return roles.RoleAssignment(role=_role(rid), score=1.0, item=item)


class TestPeerParallelDispatch(unittest.TestCase):
    def test_build_niche_prompt_scoped_to_role(self) -> None:
        asn = _asn("factory_engineer", "**Fix tests** — run unittest")
        text = ppd.build_niche_prompt(asn, cwd=Path("/tmp/wt"))
        self.assertIn("Factory Engineer", text)
        self.assertIn("factory_engineer", text)
        self.assertIn("Fix tests", text)
        self.assertIn("Do not orchestrate", text)

    def test_max_parallel_agent_procs_respects_cap(self) -> None:
        import project_automation as auto

        n = ppd.max_parallel_agent_procs()
        cap = auto.max_parallel_peers()
        self.assertGreaterEqual(n, 1)
        self.assertLessEqual(n, cap)

    def test_parallel_enabled_by_default(self) -> None:
        self.assertTrue(ppd.parallel_agent_dispatch_enabled())

    def test_refuse_root_cwd_when_pool_short(self) -> None:
        """Short pool must skip launch — never cwd=ROOT."""
        asn_a = _asn("factory_engineer", "a")
        asn_b = _asn("verify_runner", "b")
        logs: list[str] = []
        launched: list[Path] = []

        def _fake_run(asn, cwd, *, log_fn, paid_api):  # noqa: ANN001
            launched.append(Path(cwd))
            return asn.role.id, 0, False

        with mock.patch.object(ppd, "hub_dispatch_cap", return_value=8):
            with mock.patch.object(ppd, "effective_hub_running", return_value=0):
                with mock.patch.object(ppd, "find_agent_procs", return_value=[]):
                    with mock.patch.object(ppd, "trim_agents_over_cap", return_value=0):
                        with mock.patch.object(
                            ppd.wt, "ensure_parallel_pool", return_value=[Path("/tmp/wt0")]
                        ):
                            with mock.patch.object(ppd, "_run_one_niche", side_effect=_fake_run):
                                with mock.patch.object(ppd, "_dispatch_flock") as flock:
                                    flock.return_value.__enter__ = lambda s: None
                                    flock.return_value.__exit__ = lambda *a: None
                                    rc, auth = ppd.run_parallel_niche_cycle(
                                        [asn_a, asn_b],
                                        [],
                                        log_fn=logs.append,
                                    )
        self.assertEqual(rc, 0)
        self.assertFalse(auth)
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0], Path("/tmp/wt0").resolve())
        self.assertTrue(any("refuse ROOT" in m for m in logs))
        self.assertNotIn(ppd.ROOT.resolve(), launched)

    def test_scopes_conflict_exact_and_prefix(self) -> None:
        self.assertTrue(
            ppd.scopes_conflict({"scripts/a.py"}, {"scripts/a.py"})
        )
        self.assertTrue(
            ppd.scopes_conflict({"scripts"}, {"scripts/a.py"})
        )
        self.assertFalse(
            ppd.scopes_conflict({"scripts/a.py"}, {"scripts/b.py"})
        )
        self.assertFalse(ppd.scopes_conflict(set(), {"scripts/a.py"}))

    def test_filter_disjoint_rejects_overlap(self) -> None:
        a = _asn("factory_engineer", "Fix `scripts/peer_loop.py`")
        b = _asn("verify_runner", "Also touch `scripts/peer_loop.py`")
        c = _asn("queue_steward", "Edit `scripts/peer_orchestrate.py`")
        logs: list[str] = []
        accepted, deferred = ppd.filter_disjoint_assignments(
            [a, b, c], log_fn=logs.append
        )
        self.assertEqual(
            [x.role.id for x in accepted], ["factory_engineer", "queue_steward"]
        )
        self.assertEqual([x.role.id for x in deferred], ["verify_runner"])
        self.assertTrue(any("scope overlap reject" in m for m in logs))
        self.assertEqual(ppd.batch_has_scope_collision(accepted), [])

    def test_run_parallel_skips_overlapping_second_niche(self) -> None:
        a = _asn("factory_engineer", "Land `scripts/alpha.py`")
        b = _asn("verify_runner", "Also land `scripts/alpha.py`")
        c = _asn("queue_steward", "Land `scripts/beta.py`")
        logs: list[str] = []
        launched: list[str] = []

        def _fake_run(asn, cwd, *, log_fn, paid_api):  # noqa: ANN001
            launched.append(asn.role.id)
            return asn.role.id, 0, False

        pool = [Path("/tmp/wt0"), Path("/tmp/wt1"), Path("/tmp/wt2")]
        with mock.patch.object(ppd, "hub_dispatch_cap", return_value=8):
            with mock.patch.object(ppd, "effective_hub_running", return_value=0):
                with mock.patch.object(ppd, "find_agent_procs", return_value=[]):
                    with mock.patch.object(ppd, "trim_agents_over_cap", return_value=0):
                        with mock.patch.object(ppd, "_run_one_niche", side_effect=_fake_run):
                            with mock.patch.object(ppd, "_dispatch_flock") as flock:
                                flock.return_value.__enter__ = lambda s: None
                                flock.return_value.__exit__ = lambda *a: None
                                rc, auth = ppd.run_parallel_niche_cycle(
                                    [a, b, c],
                                    pool,
                                    log_fn=logs.append,
                                    max_workers=8,
                                )
        self.assertEqual(rc, 0)
        self.assertFalse(auth)
        self.assertEqual(launched, ["factory_engineer", "queue_steward"])
        self.assertTrue(
            any("deferred" in m and "scope overlap" in m for m in logs)
        )

    def test_prove_10_cycles_zero_collisions(self) -> None:
        """Factory A+ Phase 2 — 10 simulated waves, zero merge collisions."""
        waves: list[list[roles.RoleAssignment]] = []
        for cycle in range(10):
            waves.append(
                [
                    _asn(
                        f"role_a_{cycle}",
                        f"Edit `scripts/mod_a_{cycle}.py` and `scripts/shared.py`",
                    ),
                    _asn(
                        f"role_b_{cycle}",
                        f"Edit `scripts/shared.py` and `scripts/mod_b_{cycle}.py`",
                    ),
                    _asn(
                        f"role_c_{cycle}",
                        f"Edit `scripts/mod_c_{cycle}.py`",
                    ),
                    _asn(
                        f"role_d_{cycle}",
                        f"Edit `notes/doc_{cycle}.md`",
                    ),
                ]
            )
        report = ppd.prove_disjoint_dispatch_cycles(waves, worktree_count=8)
        self.assertEqual(report["cycles"], 10)
        self.assertEqual(report["collisions"], 0)
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(int(report["deferred"]), 10)  # shared.py each wave
        self.assertGreaterEqual(int(report["launched"]), 20)
        self.assertLessEqual(int(report["max_batch"]), 8)


if __name__ == "__main__":
    unittest.main()


class OverseerCensusTests(unittest.TestCase):
    """OVERSEER_EXCLUDE_FROM_FACTORY_CENSUS_2026_09_07 / FREE_DESKTOP_RESERVE."""

    def test_overseer_cmdline_detected(self) -> None:
        import peer_parallel_dispatch as ppd

        self.assertTrue(
            ppd._is_overseer_cmdline(
                "cursor-agent -p # System Overseer — event-triggered stagnation dispatch"
            )
        )
        self.assertFalse(ppd._is_overseer_cmdline("cursor-agent -p Read the full peer prompt"))

    def test_agent_proc_excludes_overseer(self) -> None:
        import peer_parallel_dispatch as ppd

        self.assertIsNone(
            ppd._agent_proc_from_cmdline(
                "cursor-agent -p System Overseer for Automation",
                12345,
            )
        )
