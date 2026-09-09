#!/usr/bin/env python3
from pathlib import Path
import subprocess, time, sys

home = Path.home()
hub = home / ".config" / "automation-hub"
suffix = "env"
paid = hub / f"cursor-agent.{suffix}"
park = hub / f"cursor-agent.{suffix}.paid-disabled"
if paid.is_file():
    paid.replace(park)
    print("parked_cred=yes")
else:
    print("parked_cred_already", park.is_file())

drop = home / ".config" / "systemd" / "user" / "peer-loop.service.d"
drop.mkdir(parents=True, exist_ok=True)
# Disable any drop-in that still passes paid flag
for p in drop.glob("*.conf"):
    text = p.read_text()
    if "paid-api" in text or "PEER_LOOP_PAID_API=1" in text:
        disabled = p.with_suffix(p.suffix + ".disabled")
        p.replace(disabled)
        print("disabled_dropin", p.name, "->", disabled.name)

# trap '' USR1 — agents use `systemctl kill -s USR1` as fake reload; must not
# kill bash wrapper (OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07 / T10-04 flaps).
exec_line = (
    "/bin/bash -c "
    "'trap \"\" USR1; while true; do "
    "/home/arnavrastogi/miniconda3/bin/python3 "
    "/home/arnavrastogi/.config/automation/run_peer_loop_gitfile.py "
    "--forever --quick || true; sleep 60; done'"
)
# Highest lexical name wins last ExecStart clear+set among drop-ins we control
(drop / "zzz-force-free-desktop.conf").write_text(
    "[Service]\n"
    "Environment=PEER_LOOP_PAID_API=0\n"
    "Environment=AUTOMATION_FORCE_FREE_DESKTOP=1\n"
    "Environment=PEER_AGENT_LOCAL=1\n"
    "ExecStart=\n"
    f"ExecStart={exec_line}\n"
)
print("wrote zzz-force-free-desktop.conf")

ka = home / ".config" / "systemd" / "user" / "compression-keep-alive.service"
if ka.is_file():
    t = ka.read_text().replace("PEER_LOOP_PAID_API=1", "PEER_LOOP_PAID_API=0")
    ka.write_text(t)

subprocess.check_call(["systemctl", "--user", "daemon-reload"])
subprocess.call(["systemctl", "--user", "restart", "peer-loop.service"])
subprocess.call(["systemctl", "--user", "restart", "compression-keep-alive.service"])
time.sleep(4)

# show effective ExecStart
out = subprocess.getoutput("systemctl --user cat peer-loop.service")
paid_mentions = [ln.strip() for ln in out.splitlines() if "paid" in ln.lower()]
print("paid_mentions_in_cat:")
for ln in paid_mentions:
    print(" ", ln[:180])
# effective main PID cmdline
pid = subprocess.getoutput("systemctl --user show -p MainPID --value peer-loop")
print("main_pid", pid)
if pid.strip().isdigit() and int(pid) > 0:
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
    except Exception:
        cmd = subprocess.getoutput(f"ps -p {pid} -o args=")
    print("main_cmd", cmd[:300])
    print("main_has_paid_flag", "--paid-api" in cmd)

sys.path.insert(0, "/home/arnavrastogi/Automation/scripts")
import peer_terminal as pt
print("api_key_configured", pt.api_key_configured())
print("auth", pt.cursor_agent_auth_ready()[1])
