#!/usr/bin/env python3
"""Switch CLEAN hub to free desktop cursor-agent auth; keep fanout alive."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

home = Path.home()
hub = home / ".config" / "automation-hub"
suffix = "env"
paid = hub / f"cursor-agent.{suffix}"
park = hub / f"cursor-agent.{suffix}.paid-disabled"

if paid.is_file():
    paid.replace(park)
    print("parked_paid_credential_file=yes")
else:
    print("parked_paid_credential_file", park.is_file())

drop = home / ".config" / "systemd" / "user" / "peer-loop.service.d"
drop.mkdir(parents=True, exist_ok=True)
exec_line = (
    "/bin/bash -c "
    "'while true; do "
    "/home/arnavrastogi/miniconda3/bin/python3 "
    "/home/arnavrastogi/.config/automation/run_peer_loop_gitfile.py "
    "--forever --quick || true; sleep 60; done'"
)
(drop / "zz-free-desktop.conf").write_text(
    "[Service]\n"
    "Environment=PEER_LOOP_PAID_API=0\n"
    "Environment=PEER_AGENT_LOCAL=1\n"
    "ExecStart=\n"
    f"ExecStart={exec_line}\n"
)
print("peer-loop free drop-in written")

ka = home / ".config" / "systemd" / "user" / "compression-keep-alive.service"
if ka.is_file():
    text = ka.read_text()
    text = text.replace(
        "Environment=PEER_LOOP_PAID_API=1",
        "Environment=PEER_LOOP_PAID_API=0",
    )
    ka.write_text(text)
    print("keep-alive unit patched")

subprocess.check_call(["systemctl", "--user", "daemon-reload"])
for unit in ("peer-loop", "compression-keep-alive", "compression-auto-train"):
    subprocess.call(["systemctl", "--user", "restart", f"{unit}.service"])
time.sleep(6)
for unit in ("peer-loop", "compression-keep-alive", "compression-auto-train"):
    print(unit, subprocess.getoutput(f"systemctl --user is-active {unit}"))

sys.path.insert(0, "/home/arnavrastogi/Automation/scripts")
import peer_terminal as pt  # noqa: E402

print("api_key_configured", pt.api_key_configured())
print("auth_detail", pt.cursor_agent_auth_ready()[1])

n = 0
out = subprocess.check_output(["ps", "-u", home.name, "-o", "cmd="], text=True)
for line in out.splitlines():
    if "cursor-agent" in line:
        n += 1
print("cursor_agent_procs", n)
