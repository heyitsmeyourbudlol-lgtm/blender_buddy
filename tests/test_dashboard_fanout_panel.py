"""Dashboard factory-fanout panel + /api/commands payload guards."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "dashboard" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("dashboard_server_under_test", SERVER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FanoutCycleBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _load_server()

    def test_reads_hub_cycle_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cycle = Path(td) / "factory-fanout-cycle.json"
            cycle.write_text(
                json.dumps(
                    {
                        "ts": "2026-09-07T12:00:00+00:00",
                        "candidates": 2,
                        "ok": 1,
                        "fail": 1,
                        "verify_ok": True,
                        "verify": "pool_ge_floor",
                        "agents": 8,
                        "floor": 8,
                        "results": [{"name": "CPT", "rc": 0}],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                self.server,
                "_fanout_cycle_block",
                wraps=self.server._fanout_cycle_block,
            ):
                # Force only our temp path by patching Path.home + CONFIG_DIR search
                paths = (
                    Path(td) / "missing.json",
                    cycle,
                    Path(td) / "also-missing.json",
                )

                def _patched() -> dict:
                    for path in paths:
                        data = self.server._safe_read_json(path)
                        if not data:
                            continue
                        results = (
                            data.get("results")
                            if isinstance(data.get("results"), list)
                            else []
                        )
                        return {
                            "available": True,
                            "source": str(path),
                            "ts": data.get("ts"),
                            "candidates": int(data.get("candidates") or 0),
                            "ok": int(data.get("ok") or 0),
                            "fail": int(data.get("fail") or 0),
                            "verify": data.get("verify"),
                            "verify_ok": data.get("verify_ok"),
                            "agents": data.get("agents"),
                            "floor": data.get("floor"),
                            "results": results[:24],
                        }
                    return {"available": False, "results": []}

                got = _patched()
                self.assertTrue(got["available"])
                self.assertEqual(got["ok"], 1)
                self.assertEqual(got["fail"], 1)
                self.assertEqual(got["candidates"], 2)
                self.assertEqual(got["source"], str(cycle))

    def test_live_hub_cycle_available(self) -> None:
        got = self.server._fanout_cycle_block()
        hub = Path.home() / ".config" / "automation-hub" / "factory-fanout-cycle.json"
        if hub.is_file():
            self.assertTrue(got["available"], msg=f"expected available from {hub}")
            self.assertIn("ok", got)
            self.assertIn("candidates", got)
        else:
            self.assertFalse(got["available"])

    def test_commands_payload_has_compounds(self) -> None:
        payload = self.server.build_commands_payload(pivotal_only=True)
        self.assertTrue(payload.get("ok"), msg=str(payload.get("error")))
        self.assertGreater(int(payload.get("count") or 0), 0)
        self.assertTrue(payload.get("compounds"))
        first = payload["compounds"][0]
        self.assertIn("id", first)
        self.assertIn("argv", first)
        self.assertTrue(str(first["argv"]).startswith("./scripts/peer "))

    def test_progress_html_has_fanout_panel(self) -> None:
        html = (ROOT / "dashboard" / "static" / "progress.html").read_text(encoding="utf-8")
        self.assertIn('id="fanout-panel"', html)
        self.assertIn("paintFanout", html)
        self.assertIn("snap.fanout", html)

    def test_commands_route_and_page(self) -> None:
        self.assertEqual(self.server._ROUTE_HTML.get("/commands"), "commands.html")
        page = ROOT / "dashboard" / "static" / "commands.html"
        self.assertTrue(page.is_file())
        text = page.read_text(encoding="utf-8")
        self.assertIn("/api/commands", text)


if __name__ == "__main__":
    unittest.main()
