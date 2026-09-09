#!/usr/bin/env python3
from pathlib import Path
import subprocess, time, json, sys

home = Path.home()
unit_dir = home / ".config/systemd/user"
unit_dir.mkdir(parents=True, exist_ok=True)
unit = unit_dir / "compression-gpu-worker.service"
unit.write_text("""[Unit]
Description=Automation Hub — compression GPU worker (local CUDA, free)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/arnavrastogi/Automation
Environment=HOME=/home/arnavrastogi
Environment=PYTHONPATH=/home/arnavrastogi/Automation/scripts
Environment=PATH=/home/arnavrastogi/miniconda3/bin:/home/arnavrastogi/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=CUDA_DEVICE_ORDER=PCI_BUS_ID
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/home/arnavrastogi/miniconda3/bin/python3 /home/arnavrastogi/Automation/scripts/compression_gpu_worker.py --forever --interval-sec 15
Restart=always
RestartSec=10
StandardOutput=append:/home/arnavrastogi/.config/automation/compression-gpu-worker.log
StandardError=append:/home/arnavrastogi/.config/automation/compression-gpu-worker.log

[Install]
WantedBy=default.target
""")
print("unit written")
subprocess.check_call(["systemctl", "--user", "daemon-reload"])
subprocess.check_call(["systemctl", "--user", "enable", "--now", "compression-gpu-worker.service"])
subprocess.call(["systemctl", "--user", "restart", "compression-gpu-worker.service"])
time.sleep(8)
print("active", subprocess.getoutput("systemctl --user is-active compression-gpu-worker"))
# smoke once also
rc = subprocess.call([
    "/home/arnavrastogi/miniconda3/bin/python3",
    "/home/arnavrastogi/Automation/scripts/compression_gpu_worker.py",
    "--once",
])
print("once_rc", rc)
status = Path("/home/arnavrastogi/Automation/notes/compression_artifacts/gpu_accel_status.json")
if status.is_file():
    data = json.loads(status.read_text())
    print("device", data.get("device"))
    print("t4_S", (data.get("t4_ratio_check") or {}).get("S"))
    print("svd_sec", (data.get("svd_scale_sweep") or {}).get("seconds"))
    print("kd_mse", (data.get("kd_gpu_step") or {}).get("heldout_proxy_mse"))
# util
print(subprocess.getoutput(
    "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader"
))
