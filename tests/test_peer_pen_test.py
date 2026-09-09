"""Unit tests for defensive pen-test lane."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_pen_test as pt  # noqa: E402


def _finding_path(loc: str) -> str:
    """Path stem before :line — avoids 'safe.tsx' matching inside 'unsafe.tsx'."""
    return loc.split(":", 1)[0].replace("\\", "/")


class PenTestProbeTests(unittest.TestCase):
    def test_probe_flags_eval_and_shell_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text(
                "def f(x):\n    return eval(x)\n\nsubprocess.run(cmd, shell=True)\n",
                encoding="utf-8",
            )
            (root / ".git").mkdir()
            findings = pt.probe_target(root)
            titles = {f.title for f in findings}
            self.assertTrue(any("eval" in t.lower() for t in titles))
            self.assertTrue(any("shell=True" in t for t in titles))

    def test_skips_dotenv_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "STRIPE=sk_live_FAKE_NOT_REAL_VALUE_12345\n",
                encoding="utf-8",
            )
            (root / ".git").mkdir()
            findings = pt.probe_target(root)
            self.assertFalse(
                any("Stripe" in f.title or "secret" in f.title.lower() for f in findings)
            )

    def test_make_id_stable(self) -> None:
        a = pt.PenFinding.make_id("t", "a.py:1", "CaaS")
        b = pt.PenFinding.make_id("t", "a.py:1", "CaaS")
        c = pt.PenFinding.make_id("t", "a.py:2", "CaaS")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_scan_patterns_compiled(self) -> None:
        self.assertGreaterEqual(len(pt.SCAN_PATTERNS), 5)
        for pid, pat, sev, title in pt.SCAN_PATTERNS:
            self.assertTrue(pid)
            self.assertTrue(pat)
            self.assertIn(sev, ("critical", "high", "medium", "low"))
            self.assertTrue(title)

    def test_skips_tests_dir_via_skip_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_fixture.py").write_text(
                "def f(x):\n    return eval(x)\n",
                encoding="utf-8",
            )
            (root / "live_bad.py").write_text(
                "def f(x):\n    return eval(x)\n",
                encoding="utf-8",
            )
            (root / ".git").mkdir()
            findings = pt.probe_target(root)
            locs = {_finding_path(f.location) for f in findings}
            self.assertIn("live_bad.py", locs)
            self.assertFalse(any(p.startswith("tests/") for p in locs))

    def test_skips_danger_html_when_sanitizer_present(self) -> None:
        # OVERSEER_PEN_SAFE_SUBSTR_2026_09_04 — bare `in loc` matches safe inside unsafe.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scrubbed.tsx").write_text(
                'import sanitizeHtml from "sanitize-html";\n'
                "const x = { dangerouslySetInnerHTML: { __html: sanitizeHtml(s) } };\n",
                encoding="utf-8",
            )
            (root / "raw_html.tsx").write_text(
                "const x = { dangerouslySetInnerHTML: { __html: raw } };\n",
                encoding="utf-8",
            )
            (root / ".git").mkdir()
            findings = pt.probe_target(root)
            locs = {
                _finding_path(f.location)
                for f in findings
                if "HTML" in f.title or "XSS" in f.title
            }
            self.assertIn("raw_html.tsx", locs)
            self.assertNotIn("scrubbed.tsx", locs)

    def test_skips_mark_script_token_query_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "_mark_flaw_research_landed.py").write_text(
                'assert ("accept?" + "token=") not in text\n'
                'url = "/x?token=abc"\n',
                encoding="utf-8",
            )
            (root / ".git").mkdir()
            findings = pt.probe_target(root)
            self.assertFalse(any("query string" in f.title.lower() for f in findings))

    def test_skips_detector_needle_eval_strings(self) -> None:
        # OVERSEER_PEN_SKIP_DETECTOR_NEEDLE_EVAL_2026_09_05
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Match live hub shape: escaped needles inside a generator string
            # (scripts/_ov_stag_fix_land.py:136).
            (root / "detector.py").write_text(
                '        "    if evidence and (\\".eval(\\" in line or \\"eval(\\" '
                'in line):\\n"\n',
                encoding="utf-8",
            )
            (root / "live_bad.py").write_text(
                "def f(x):\n    return eval(x)\n",
                encoding="utf-8",
            )
            (root / ".git").mkdir()
            findings = pt.probe_target(root)
            locs = {
                _finding_path(f.location)
                for f in findings
                if "eval" in f.title.lower()
            }
            self.assertIn("live_bad.py", locs)
            self.assertNotIn("detector.py", locs)


    def test_enqueue_skips_closed_pen_test_twins(self) -> None:
        # OVERSEER_PEN_SKIP_CLOSED_2026_09_04
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "WORK_QUEUE.md"
            wq.write_text(
                "## Active\n"
                "- [x] **[pen-test] Unsanitized HTML sink (XSS risk) — CaaS** — deferred\n",
                encoding="utf-8",
            )
            ctx = root / "self_improve_context.md"
            ctx.write_text("## Remaining work (priority order)\n", encoding="utf-8")
            import project_automation as auto

            old_wq, old_ctx = auto.WORK_QUEUE_PATH, auto.CONTEXT_PATH
            auto.WORK_QUEUE_PATH = wq
            auto.CONTEXT_PATH = ctx
            try:
                finding = pt.PenFinding(
                    id="t1",
                    severity="high",
                    title="Unsanitized HTML sink (XSS risk)",
                    evidence="x",
                    location="src/app/support/SupportChat.tsx:308",
                    target="CaaS",
                )
                got = pt.enqueue_findings([finding], cap=3)
                self.assertEqual(got, [])
                self.assertNotIn("- [ ] **[pen-test] Unsanitized HTML sink", wq.read_text())
            finally:
                auto.WORK_QUEUE_PATH = old_wq
                auto.CONTEXT_PATH = old_ctx


if __name__ == "__main__":
    unittest.main()
