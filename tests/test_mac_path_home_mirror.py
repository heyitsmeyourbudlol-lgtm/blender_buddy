"""OVERSEER_MAC_PATH_HOME_MIRROR_2026_09_08 — rewrite missing Mac file-scoped paths."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_automation import rewrite_unreachable_mac_file_scoped_paths


class MacPathHomeMirrorTests(unittest.TestCase):
    def test_rewrites_missing_users_path_to_home_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mirror = home / "CaaS"
            mirror.mkdir()
            md = (
                "## Active\n"
                "- [ ] **[top10] Newdrop** — after #163; "
                "file-scoped `/Users/togi/CaaS`; verify npm test\n"
            )
            with mock.patch(
                "project_automation.clean_push_auth_blocked", return_value=True
            ):
                new_md, n = rewrite_unreachable_mac_file_scoped_paths(md, home=home)
            self.assertEqual(n, 1)
            self.assertIn(str(mirror), new_md)
            self.assertIn("OVERSEER_MAC_PATH_HOME_MIRROR_2026_09_08", new_md)
            self.assertIn("push deferred", new_md)
            self.assertNotIn("file-scoped `/Users/togi/CaaS`", new_md)

    def test_noop_when_mac_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mac = home / "Users" / "togi" / "CaaS"
            mac.mkdir(parents=True)
            md = f"- [ ] item — file-scoped `{mac}`; ok\n"
            new_md, n = rewrite_unreachable_mac_file_scoped_paths(md, home=home)
            self.assertEqual(n, 0)
            self.assertEqual(new_md, md)

    def test_noop_when_home_mirror_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            md = (
                "- [ ] item — file-scoped `/Users/togi/MissingRepo`; ok\n"
            )
            new_md, n = rewrite_unreachable_mac_file_scoped_paths(md, home=home)
            self.assertEqual(n, 0)
            self.assertEqual(new_md, md)


if __name__ == "__main__":
    unittest.main()
