#!/usr/bin/env python3
"""Install compression-result-watch systemd user unit on CLEAN."""
from __future__ import annotations

import subprocess
from pathlib import Path

home = Path.home()
unit_dir = home / ".config" / "systemd" / "user"
unit_dir.mkdir(parents=True, exist_ok=True)
unit = unit_dir / "compression-result-watch.service"
unit.write_text(
    """[Unit]
Description=Automation Hub — compression result watch (time+results, free desktop)
After=network-online.target compression-keep-alive.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/arnavrastogi/Automation
Environment=HOME=/home/arnavrastogi
Environment=PYTHONPATH=/home/arnavrastogi/Automation/scripts
Environment=PATH=/home/arnavrastogi/miniconda3/bin:/home/arnavrastogi/.local/bin:/usr/bin:/bin
Environment=AUTOMATION_FORCE_FREE_DESKTOP=1
Environment=PEER_LOOP_PAID_API=0
Environment=WATCH_STALL_SEC=600
Environment=WATCH_POLL_SEC=60
ExecStart=/home/arnavrastogi/miniconda3/bin/python3 /home/arnavrastogi/Automation/scripts/compression_result_watch.py --forever
Restart=always
RestartSec=12
StandardOutput=append:/home/arnavrastogi/.config/automation/compression-result-watch.log
StandardError=append:/home/arnavrastogi/.config/automation/compression-result-watch.log

[Install]
WantedBy=default.target
"""
)
print("wrote", unit)
subprocess.check_call(["systemctl", "--user", "daemon-reload"])
subprocess.check_call(["systemctl", "--user", "enable", "--now", "compression-result-watch.service"])
subprocess.call(["systemctl", "--user", "restart", "compression-result-watch.service"])
print("active", subprocess.getoutput("systemctl --user is-active compression-result-watch"))
