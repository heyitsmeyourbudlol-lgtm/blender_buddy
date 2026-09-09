#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path("/home/arnavrastogi/Automation")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

buf: list[str] = []


class W:
    def write(self, s: str) -> None:
        buf.append(s)

    def flush(self) -> None:
        pass


suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_peer_error_adapt")
r = unittest.TextTestRunner(stream=W(), verbosity=2).run(suite)
buf.append(
    f"\nFAILS={len(r.failures)} ERR={len(r.errors)} tests={r.testsRun} ok={r.wasSuccessful()}\n"
)

a = (ROOT / "scripts/automation_adapt.py").read_text()
p = (ROOT / "scripts/peer_error_adapt.py").read_text()
buf.append(
    "adapt AUDIT=%s ok_passed=%s\n"
    % ("OVERSEER_AUDIT_RC_2026_09_03" in a, 'entry["ok"] = passed' in a)
)
buf.append(
    "pea still_hard=%s noop=%s AUTH=%s\n"
    % (
        "still = still_hard" in p,
        "noop-mislabel" in p,
        "OVERSEER_AUTH_HOLD_2026_09_03" in p,
    )
)

# Active open
wq = (ROOT / "notes/WORK_QUEUE.md").read_text()
ina = False
n = 0
opens: list[str] = []
for line in wq.splitlines():
    if line.startswith("## Active"):
        ina = True
        continue
    if line.startswith("## "):
        ina = False
        continue
    if ina and line.startswith("- [ ]"):
        n += 1
        opens.append(line[:140])
buf.append("Active open=%s\n" % n)
buf.extend(o + "\n" for o in opens)

out = ROOT / "notes/_overseer_test_snip.txt"
out.write_text("".join(buf))
print("wrote", out, "ok", r.wasSuccessful(), "tests", r.testsRun)
