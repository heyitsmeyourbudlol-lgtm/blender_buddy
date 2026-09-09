#!/usr/bin/env python3
"""Tests for knowledge index."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import knowledge_index as ki  # noqa: E402
import knowledge_index_config as kcfg  # noqa: E402
import knowledge_mamba as kmamba  # noqa: E402
import knowledge_retrieve as kr  # noqa: E402


class KnowledgeIndexTests(unittest.TestCase):
    def test_chunk_text_overlap(self) -> None:
        text = "a" * 2500
        chunks = ki.chunk_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(len(chunks[0]), kcfg.chunk_chars())

    def test_index_and_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "index"
            notes = root / "notes"
            notes.mkdir()
            (notes / "needle.md").write_text("The zebra protocol uses peer orchestrate drift cache skip.")
            with mock.patch.object(kcfg, "data_root", return_value=data), mock.patch.object(
                kcfg, "hot_cache_root", return_value=data / "hot"
            ), mock.patch.object(kcfg, "enabled", return_value=True), mock.patch.object(
                kcfg, "sources", return_value=("notes",)
            ), mock.patch.object(
                ki.auto, "ROOT", notes.parent
            ):
                conn = ki._connect()
                ki.init_db(conn)
                added = ki._index_tree(conn, source="notes", root=notes)
                conn.commit()
                conn.close()
                self.assertGreaterEqual(added, 1)
                hits = ki.retrieve("zebra protocol drift cache")
                self.assertTrue(hits)
                self.assertIn("zebra", hits[0].text.lower())

    def test_sparse_retrieve_skips_mamba(self) -> None:
        """Cold-memory / peer_loop path must never pull torch via hybrid rerank."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "index"
            notes = root / "notes"
            notes.mkdir()
            (notes / "needle.md").write_text(
                "The zebra protocol uses peer orchestrate drift cache skip."
            )
            with mock.patch.object(kcfg, "data_root", return_value=data), mock.patch.object(
                kcfg, "hot_cache_root", return_value=data / "hot"
            ), mock.patch.object(kcfg, "enabled", return_value=True), mock.patch.object(
                kcfg, "sources", return_value=("notes",)
            ), mock.patch.object(ki.auto, "ROOT", notes.parent), mock.patch.object(
                ki,
                "_kmamba",
                side_effect=AssertionError("mamba must not load for hybrid=False"),
            ):
                conn = ki._connect()
                ki.init_db(conn)
                added = ki._index_tree(conn, source="notes", root=notes)
                conn.commit()
                conn.close()
                self.assertGreaterEqual(added, 1)
                hits = ki.retrieve("zebra protocol drift cache", hybrid=False)
                self.assertTrue(hits)
                self.assertIn("zebra", hits[0].text.lower())

    def test_build_query_includes_queue(self) -> None:
        with mock.patch.object(kr.auto, "load_work_queue_md", return_value="- [ ] Fix verify gate\n"):
            query = kr.build_query(conversation="user asked about mamba hybrid")
        self.assertIn("Fix verify gate", query)
        self.assertIn("mamba", query)

    def test_hybrid_rerank_orders_dense(self) -> None:
        hits = [
            {"text": "unrelated fluff", "sparse_score": 0.9, "path": "a", "source": "notes"},
            {"text": "mamba hybrid transformer retrieval", "sparse_score": 0.2, "path": "b", "source": "notes"},
        ]
        with mock.patch.object(kcfg, "mamba_cascade_enabled", return_value=False), mock.patch.object(
            kmamba, "_lazy_load", return_value=False
        ):
            out = kmamba.rerank("mamba hybrid retrieval", hits, top_k=2)
        self.assertEqual(out[0]["path"], "b")


if __name__ == "__main__":
    unittest.main()
