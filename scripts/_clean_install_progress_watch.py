#!/usr/bin/env python3
"""Install peer-progress-watch systemd user unit on CLEAN."""
from __future__ import annotations

import subprocess
from pathlib import Path

home = Path.home()
unit_dir = home / ".config" / "systemd" / "user"
unit_dir.mkdir(parents=True, exist_ok=True)
unit = unit_dir / "peer-progress-watch.service"
unit.write_text(
    """[Unit]
Description=Automation Hub — peer progress watch (time+result self-heal)
After=network-online.target peer-loop.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/arnavrastogi/Automation
Environment=HOME=/home/arnavrastogi
Environment=PYTHONPATH=/home/arnavrastogi/Automation/scripts
Environment=PATH=/home/arnavrastogi/miniconda3/bin:/home/arnavrastogi/.local/bin:/usr/bin:/bin
Environment=AUTOMATION_FORCE_FREE_DESKTOP=1
Environment=PEER_LOOP_PAID_API=0
Environment=PROGRESS_STALL_SEC=180
Environment=PROGRESS_POLL_SEC=45
ExecStart=/home/arnavrastogi/miniconda3/bin/python3 /home/arnavrastogi/Automation/scripts/peer_progress_watch.py --forever
Restart=always
RestartSec=12
StandardOutput=append:/home/arnavrastogi/.config/automation/peer-progress-watch.log
StandardError=append:/home/arnavrastogi/.config/automation/peer-progress-watch.log

[Install]
WantedBy=default.target
"""
)
print("wrote", unit)
subprocess.check_call(["systemctl", "--user", "daemon-reload"])
subprocess.check_call(["systemctl", "--user", "enable", "--now", "peer-progress-watch.service"])
subprocess.call(["systemctl", "--user", "restart", "peer-progress-watch.service"])
print("active", subprocess.getoutput("systemctl --user is-active peer-progress-watch"))
