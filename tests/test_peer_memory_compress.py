#!/usr/bin/env python3
"""Tests for lossless memory compress + fact librarian + domain SMEs."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_fact_librarian as fl  # noqa: E402
import peer_memory_compress as pmc  # noqa: E402
import peer_memory_span as ms  # noqa: E402
import peer_transcript as pt  # noqa: E402


class AlwaysReadHotTests(unittest.TestCase):
    def test_always_read_block_lists_sot_and_librarian(self) -> None:
        block = ms.format_always_read_block()
        self.assertIn(ms.ALWAYS_READ_HEADER, block)
        self.assertIn("notes/AGENT_WORKING_MEMORY.md", block)
        self.assertIn("fact-query", block)
        self.assertIn(ms.NO_PAY_HOT_LINE, block)

    def test_harness_memory_includes_remembrance_pointers(self) -> None:
        text = pt.format_harness_memory({"last_cycle": {}})
        self.assertIn("Always-read", text)
        self.assertIn("Fact librarian", text)


class DomainSmeTests(unittest.TestCase):
    def test_domain_map_loads(self) -> None:
        domains = fl.list_domains()
        self.assertGreaterEqual(len(domains), 8)
        ids = {d["id"] for d in domains}
        self.assertIn("queue_sync", ids)
        self.assertIn("peer_runtime", ids)
        self.assertIn("compression_bitnet", ids)

    def test_auto_pick_queue(self) -> None:
        d, scores = fl.auto_pick_domain("Active WORK_QUEUE sync-queue")
        self.assertIsNotNone(d)
        assert d is not None
        self.assertEqual(d["id"], "queue_sync")

    def test_path_in_domain(self) -> None:
        d = fl.get_domain("peer_runtime")
        assert d is not None
        self.assertTrue(fl.path_in_domain("scripts/peer_loop.py", d))
        self.assertFalse(fl.path_in_domain("dashboard/static/app.js", d))

    def test_relay_domain_scopes_paths(self) -> None:
        relay = fl.build_fact_relay(
            "peer_loop orchestrate",
            domain_id="peer_runtime",
            auto_domain=False,
        )
        self.assertEqual(relay["domain"]["id"], "peer_runtime")
        for hit in relay["pack_paths"]:
            self.assertTrue(
                fl.path_in_domain(hit["path"], fl.get_domain("peer_runtime") or {}),
                msg=hit["path"],
            )


class LosslessPackTests(unittest.TestCase):
    def test_round_trip_fixture_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / "notes").mkdir(parents=True)
            (root / "scripts").mkdir(parents=True)
            body = b"# fact\nline-one\nunique-needle-XYZ\n"
            (root / "notes" / "a.md").write_bytes(body)
            (root / "notes" / "b.md").write_bytes(body)
            (root / "notes" / "empty.md").write_bytes(b"")
            (root / "scripts" / "self_improve_context.md").write_text("- [ ] item\n")
            (root / "AGENTS.md").write_text("NO PAY free desktop\n")
            big = root / "notes" / "weights.bin"
            big.write_bytes(b"\x00\x01" * (pmc.BINARY_MAX_EMBED_BYTES + 10))

            payload = pmc.build_pack(root=root)
            pack_path = Path(tmp) / "pack.json.z"
            blob, header = pmc.pack_to_bytes(payload)
            pack_path.write_bytes(blob)
            self.assertGreater(header["json_bytes"], header["pack_bytes"])

            import base64

            header2, payload2 = pmc.read_pack(pack_path)
            self.assertEqual(header2["json_sha256"], header["json_sha256"])
            for ent in payload2["files"]:
                if not ent.get("embedded"):
                    continue
                data = base64.b64decode(payload2["blobs"][ent["sha256"]])
                live = root / ent["path"]
                self.assertEqual(live.read_bytes(), data, msg=ent["path"])

            staging = Path(tmp) / "staging"
            report = pmc.verify_pack(pack_path, root=root, staging=staging)
            self.assertTrue(report["ok"], msg=report)

    def test_expand_refuses_live_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "r"
            root.mkdir()
            (root / "f.md").write_text("x\n")
            payload = pmc.build_pack(root=root)
            pack = Path(tmp) / "p.z"
            pack.write_bytes(pmc.pack_to_bytes(payload)[0])
            with self.assertRaises(ValueError):
                pmc.expand_pack(pack, pmc.ROOT)

    def test_secrets_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "r"
            (root / "notes").mkdir(parents=True)
            (root / "notes" / "ok.md").write_text("safe\n")
            (root / ".env").write_text("SECRET=1\n")
            payload = pmc.build_pack(root=root)
            paths = {f["path"] for f in payload["files"]}
            self.assertIn("notes/ok.md", paths)
            self.assertNotIn(".env", paths)


if __name__ == "__main__":
    unittest.main()
