"""OVERSEER_PARSE_PHASED_MD_FP_TTL_2026_09_04 — md-fp + 60s TTL on parse."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import project_automation as auto  # noqa: E402


class ParsePhasedTtlTests(unittest.TestCase):
    def setUp(self) -> None:
        auto.clear_parse_phased_cache()

    def tearDown(self) -> None:
        auto.clear_parse_phased_cache()

    def test_md_fp_ttl_cache_hit(self) -> None:
        md = (
            "## Active items\n"
            "- [ ] **alpha** — keep open\n"
            "## Done\n"
            "- [x] **beta** — closed\n"
        )
        with mock.patch.object(auto, "_parse_work_item", wraps=auto._parse_work_item) as parse:
            a = auto._parse_phased_work_items(md)
            first = parse.call_count
            self.assertGreaterEqual(first, 1)
            b = auto._parse_phased_work_items(md)
            self.assertEqual(parse.call_count, first)  # cached — no re-walk
            self.assertEqual(a, b)
            self.assertIsNot(a, b)  # caller-safe copy

    def test_md_fp_ttl_miss_on_md_change(self) -> None:
        md1 = "## Active items\n- [ ] **alpha** — keep\n"
        md2 = "## Active items\n- [ ] **beta** — keep\n"
        with mock.patch.object(auto, "_parse_work_item", wraps=auto._parse_work_item) as parse:
            auto._parse_phased_work_items(md1)
            c1 = parse.call_count
            auto._parse_phased_work_items(md2)
            self.assertGreater(parse.call_count, c1)

    def test_md_fp_ttl_expire(self) -> None:
        md = "## Active items\n- [ ] **ttl** — keep\n"
        with mock.patch.object(auto, "_parse_work_item", wraps=auto._parse_work_item) as parse:
            auto._parse_phased_work_items(md)
            c1 = parse.call_count
            auto._parse_phased_at = time.time() - (auto.PARSE_PHASED_CACHE_TTL_SEC + 1.0)
            auto._parse_phased_work_items(md)
            self.assertGreater(parse.call_count, c1)

    def test_empty_md_short_circuits(self) -> None:
        self.assertEqual(auto._parse_phased_work_items(""), [])
        self.assertIsNone(auto._parse_phased_result)

    def test_identity_short_circuit_skips_hash(self) -> None:
        # COMPRESSION_LAZY_HASHLIB — parse path uses zlib, not module hashlib.
        md = "## Active items\n- [ ] **id** — keep\n"
        auto._parse_phased_work_items(md)
        with mock.patch("zlib.adler32") as adler:
            with mock.patch("zlib.crc32") as crc:
                again = auto._parse_phased_work_items(md)
                adler.assert_not_called()
                crc.assert_not_called()
                self.assertEqual(again, ["**id** — keep"])

    def test_overseer_needle_in_source(self) -> None:
        src = (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_PARSE_PHASED_MD_FP_TTL_2026_09_04", src)
        self.assertIn("PARSE_PHASED_CACHE_TTL_SEC", src)
        self.assertIn("clear_parse_phased_cache", src)


if __name__ == "__main__":
    unittest.main()
