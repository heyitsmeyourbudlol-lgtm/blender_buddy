# CLEAN SSH intermittent (2026-09-08)

**Status:** Host up (ICMP + TCP/22) but `ssh CLEAN` often fails at **banner exchange** when load is high; mid-session checks succeeded.

**Daemons (when SSH worked):** peer-loop=active · improve-loop=active (no restart). Config: `max_parallel_agent_procs=8`, `resource_poll.enabled=false`, `trim_agents_over_cap=false`.

**Do not:** re-enable Mac peer/improve LaunchAgents (mac-offloaded).

**Recovery (one command):**
```bash
ssh -o ConnectTimeout=20 -o ServerAliveInterval=5 CLEAN 'systemctl --user is-active peer-loop improve-loop'
```
If still banner-timeout: console/IPMI on CLEAN and check `sshd` + load — not Mac offload.

