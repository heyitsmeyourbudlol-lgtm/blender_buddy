"""Project-adaptive automation — detect stack, heal drift, install kit, export bundle.

Dynamically molds peer automation to any repo:
  - Probes package managers, CI, and scripts for working verify commands
  - Scans module tree → module_scope + match_rules in profiles/local.json
  - Re-adapts when git fingerprint changes (adapt-state.json)
  - Self-heals broken verify commands and queue drift

Usage:
  python3 scripts/automation_adapt.py --probe              # detect signals (JSON)
  python3 scripts/automation_adapt.py --apply --write      # apply detected config
  python3 scripts/automation_adapt.py --heal --write       # full heal cycle
  python3 scripts/automation_adapt.py --heal --write --quick  # skip slow probes
  python3 scripts/automation_adapt.py --install /path/repo # install kit + adapt
  python3 scripts/automation_adapt.py --export             # write dist/*.tar.gz
"""

from __future__ import annotations

# OVERSEER_LEAN_NONET_2026_09_04
# OVERSEER_LEAN_OCTET_STICKY_2026_09_04

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import automation_config as cfg_mod
import project_automation as auto

ROOT = cfg_mod.ROOT
SCRIPTS = cfg_mod.SCRIPTS
CFG = cfg_mod.CFG

KIT_MARKERS = (
    "scripts/peer_orchestrate.py",
    "scripts/project_automation.py",
    "scripts/automation_adapt.py",
    "automation.config.json",
)

KIT_COPY_PATHS = (
    "automation.config.json",
    "AGENTS.md",
    "LAUNCH.md",
    "IMPORT.md",
    "install.sh",
    "dgx_speed.local.json",  # root overlay — tests.test_automation landmine vs scripts/ copy
    "profiles",
    "scripts",
    "notes",
    "tests",
    "repos/registry.json",
    ".cursor/rules/plan-to-peer-tasks.mdc",
    ".cursor/hooks.json",
)

PROFILE_BY_STACK = {
    "ram": "ram",
    "caas": "caas",
    "node": "node",
    "python": "python",
    "rust": "rust",
    "go": "go",
    "automation": "automation",
    "unknown": "generic",
}

KNOWN_PROFILES = {"generic", "ram", "caas", "node", "python", "rust", "go", "automation"}

NODE_VERIFY_SCRIPTS = ("test", "lint", "build", "check", "typecheck", "check:controls", "verify")
MAX_MODULE_RULES = 18
PROBE_TIMEOUT = 45.0
QUICK_PROBE_TIMEOUT = 8.0
SELF_CHECK_AUDIT_TIMEOUT = 120.0
GENERATED_TEMPLATE_PREFIXES = ("scope_", "fw_")


@dataclass
class ProjectSignals:
    root: str
    stack: str
    profile: str
    package_manager: str | None
    frameworks: list[str]
    project_name: str
    project_slug: str
    config_namespace: str
    launch_agent_label: str
    test_command: list[str] | None
    test_probe: str | None
    verify_commands: list[str]
    module_scope: dict[str, str]
    rss_entrypoint: str | None
    post_cycle_hook: list[str] | None
    has_kit: bool
    kit_complete: bool
    missing_kit_paths: list[str] = field(default_factory=list)
    registry_match: dict[str, Any] | None = None
    ci_commands: list[str] = field(default_factory=list)
    adapt_fingerprint: str | None = None


@dataclass
class AuditFinding:
    level: str  # error | warn | info | pass
    category: str
    message: str


@dataclass
class AuditReport:
    root: str
    ok: bool
    findings: list[AuditFinding]
    checks_run: list[str]
    verify_results: list[dict[str, Any]]
    output_files: dict[str, Any]
    meta_ok: bool

    def errors(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.level == "error"]

    def warnings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.level == "warn"]


@dataclass
class HealReport:
    actions: list[str]
    issues_remaining: list[str]
    signals: ProjectSignals
    audit: AuditReport | None = None


REQUIRED_CONFIG_KEYS = ("project_name", "project_slug", "config_namespace", "launch_agent_label")
AUDIT_CATEGORIES = ("script", "config", "local_profile", "adapt_state", "verify", "queue", "tasks", "signals")
SCRIPT_REQUIRED_FUNCS = (
    "detect_signals", "run_heal", "run_heal_fresh", "run_audit", "generate_local_profile",
    "probe_verify_commands",
)


def kit_root() -> Path:
    env = os.environ.get("AUTOMATION_KIT_ROOT")
    if env:
        return Path(env).resolve()
    return ROOT


def _parse_shell_command(cmd: str) -> list[str]:
    """Best-effort split of a verify command string into argv."""
    cmd = cmd.strip()
    if not cmd:
        return []
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _detect_monorepo(root: Path) -> bool:
    return any(
        (root / marker).is_file()
        for marker in ("pnpm-workspace.yaml", "lerna.json", "turbo.json", "nx.json", "rush.json")
    )


def _makefile_targets(root: Path) -> list[str]:
    mf = root / "Makefile"
    if not mf.is_file():
        return []
    targets: list[str] = []
    for line in mf.read_text().splitlines():
        m = re.match(r"^([a-zA-Z0-9_.-]+):", line.strip())
        if m and not line.startswith("."):
            targets.append(m.group(1))
    return targets


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "my-project"


def _register_verify_protect(pid: int) -> None:
    """OVERSEER_ADAPT_VERIFY_PROTECT_2026_09_03 — shield adapt subprocess from storm trim."""
    try:
        import dgx_ram_budget as budget

        budget.register_verify_protect(int(pid))
    except Exception:  # noqa: BLE001
        pass


def _unregister_verify_protect(pid: int) -> None:
    try:
        import dgx_ram_budget as budget

        budget.unregister_verify_protect(int(pid))
    except Exception:  # noqa: BLE001
        pass


def _run(
    cmd: list[str] | str,
    *,
    cwd: Path,
    timeout: float = 20.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # Prefer argv lists; only enable shell mode for pipes/redirects/metacharacters.
    # OVERSEER_ADAPT_VERIFY_PROTECT_2026_09_03 — session + protect so ram trim
    # cannot SIGKILL adapt unittest / verify probes mid-run.
    if isinstance(cmd, str):
        raw = cmd.strip()
        needs_shell = any(ch in raw for ch in ("|", ";", "&&", "||", ">", "<", "`", "$", "\n"))
        argv: list[str] | str = raw if needs_shell else shlex.split(raw)
        use_shell = needs_shell
    else:
        argv = cmd
        use_shell = False
    proc = subprocess.Popen(
        argv,
        shell=use_shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )
    _register_verify_protect(proc.pid)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        _unregister_verify_protect(proc.pid)
    return subprocess.CompletedProcess(
        argv if isinstance(argv, list) else [str(argv)],
        proc.returncode or 0,
        stdout,
        stderr,
    )


def _porcelain_path_is_notes(path: str) -> bool:
    """True when porcelain path is notes/ (loop ticks write notes constantly)."""
    cleaned = path.strip().strip('"').replace("\\", "/")
    return cleaned == "notes" or cleaned.startswith("notes/")


def _strip_notes_porcelain(porcelain: str) -> str:
    """Drop notes/ lines so digest/queue notes do not churn adapt fingerprint."""
    kept: list[str] = []
    for raw in (porcelain or "").splitlines():
        if not raw.strip():
            continue
        # Porcelain is XY + path; .strip() on the whole status blob can eat the
        # leading space on the first line (XY starts with ' '), so parse robustly.
        line = raw if len(raw) >= 3 and raw[2] == " " else raw.strip()
        rest = line[3:] if len(line) >= 3 and line[2] == " " else line[2:].lstrip() if len(line) >= 2 else line
        parts = rest.split(" -> ")
        if parts and all(_porcelain_path_is_notes(p) for p in parts):
            continue
        kept.append(raw)
    return "\n".join(kept)


def _fingerprint_ignore_notes(fp: str | None) -> str | None:
    """HEAD + porcelain with notes/ lines removed (compare stored vs live)."""
    if not fp or ":" not in fp:
        return fp
    head, _, porcelain = fp.partition(":")
    return f"{head}:{_strip_notes_porcelain(porcelain)}"


def _git_fingerprint(root: Path) -> str | None:
    # Worktrees use a .git *file* (gitdir:); require exists, not is_dir.
    if not (root / ".git").exists():
        return None
    head = _run(["git", "-C", str(root), "rev-parse", "HEAD"], cwd=root)
    status = _run(["git", "-C", str(root), "status", "--porcelain"], cwd=root)
    if status.returncode != 0:
        return None
    head_ref = head.stdout.strip() if head.returncode == 0 else "INIT"
    # rstrip newline only — str.strip() eats leading space on first porcelain line
    # (unstaged ' M path') and breaks notes/ filtering.
    porcelain = (status.stdout or "").rstrip("\n")
    raw = f"{head_ref}:{porcelain}"
    return _fingerprint_ignore_notes(raw)



def _is_automation_hub_kit(root: Path, cfg: dict[str, Any] | None = None) -> bool:
    """True for this Automation Hub tree even when Mac rsync demotes namespace.

    OVERSEER_ADAPT_PATH_HUB_PIN_2026_09_04 — folder slug ``automation`` must
    not redirect adapt-state / heal away from ``~/.config/automation-hub/``.
    OVERSEER_HUB_KIT_BY_OVERSIGHT_DOC_2026_09_04 — SYSTEM_OVERSIGHT is hub-unique.
    """
    data = cfg if isinstance(cfg, dict) else {}
    if data.get("config_namespace") == "automation-hub":
        return True
    if data.get("project_slug") == "automation-hub":
        return True
    if data.get("project_name") == "Automation Hub":
        return True
    label = str(data.get("launch_agent_label") or "")
    if "automation-hub" in label:
        return True
    if (root / "notes" / "SYSTEM_OVERSIGHT.md").is_file() and (
        root / "scripts" / "peer_loop.py"
    ).is_file():
        return True
    return False


def adapt_state_path(root: Path) -> Path:
    ns = CFG.get("config_namespace", _slug(root.name))
    cfg_path = root / "automation.config.json"
    data: dict[str, Any] | None = None
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text())
            if isinstance(raw, dict):
                data = raw
                ns = raw.get("config_namespace", ns)
        except (json.JSONDecodeError, OSError):
            pass
    # OVERSEER_ADAPT_PATH_HUB_PIN_2026_09_04 — never follow demoted slug.
    if _is_automation_hub_kit(root, data) and str(ns) != "automation-hub":
        ns = "automation-hub"
    return Path.home() / ".config" / str(ns) / "adapt-state.json"



def load_adapt_state(root: Path) -> dict[str, Any]:
    path = adapt_state_path(root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_adapt_state(root: Path, state: dict[str, Any]) -> None:
    """Persist adapt-state. Never write git_fingerprint: null (churns should_re_adapt)."""
    path = adapt_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    fp = payload.get("git_fingerprint")
    if fp is None:
        live = _git_fingerprint(root)
        if live is not None:
            payload["git_fingerprint"] = live
        else:
            prev_fp = load_adapt_state(root).get("git_fingerprint")
            if prev_fp:
                payload["git_fingerprint"] = prev_fp
            else:
                payload.pop("git_fingerprint", None)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def should_re_adapt(root: Path) -> bool:
    fp = _git_fingerprint(root)
    if fp is None:
        return True
    prev = load_adapt_state(root).get("git_fingerprint")
    return prev != fp


def sync_git_fingerprint(root: Path) -> bool:
    """Refresh stored git fingerprint without re-probe (after mechanical note writes)."""
    fp = _git_fingerprint(root)
    if fp is None:
        return False
    state = load_adapt_state(root)
    if state.get("git_fingerprint") == fp:
        return False
    state = dict(state)
    state["git_fingerprint"] = fp
    if not state.get("_generated_at"):
        state["_generated_at"] = datetime.now(timezone.utc).isoformat()
    save_adapt_state(root, state)
    return True


def sync_notes_only_fingerprint(root: Path) -> bool:
    """Verify-start sync — ``_git_fingerprint`` already ignores notes/ porcelain.

    Keeps adapt-state aligned so notes-only ticks cannot re-open adapt_stale.
    Returns True when the stored fingerprint was rewritten.
    """
    return sync_git_fingerprint(root)


def sync_verify_commands_state(root: Path) -> bool:
    """Verify-start heal — align adapt-state verify_commands to lean local.json.

    OVERSEER_SYNC_VERIFY_CMDS_2026_09_04 — Mac/rsync + wrong-ns adapt-state
    (``~/.config/automation/``) leave verify_commands drift vs lean local →
    ADAPT_STALE blocks heal-all while fingerprint is fresh. Rewrite hub
    adapt-state (and demoted ``automation`` twin) to lean canon before audit.

    OVERSEER_SYNC_VERIFY_LOCAL_CONFIG_2026_09_07 — also pin
    ``automation.config.local.json`` / root ``automation.config.json`` to lean.
    ``load_config`` merges local last; verify-start previously only healed
    ``profiles/local.json`` + adapt-state while CFG stayed at 9 cmds → gate
    theater (OVERSEER regression suite never ran).
    """
    local_path = root / "profiles" / "local.json"
    lean: list[str] = []
    if local_path.is_file():
        try:
            raw = json.loads(local_path.read_text()).get("verify_commands") or []
            lean = _lean_automation_verify_commands(raw, stack="automation")
        except (json.JSONDecodeError, OSError, TypeError):
            lean = []
    if not lean:
        lean = _lean_automation_verify_commands(None, stack="automation")
    if not lean:
        return False

    rewritten = False
    # Also rewrite lean local.json when Mac/rsync stripped needles (peer_remote etc.).
    if local_path.is_file():
        try:
            loc = json.loads(local_path.read_text())
            if isinstance(loc, dict) and list(loc.get("verify_commands") or []) != lean:
                loc = dict(loc)
                loc["verify_commands"] = list(lean)
                loc["_generated_at"] = datetime.now(timezone.utc).isoformat()
                local_path.write_text(json.dumps(loc, indent=2) + "\n")
                rewritten = True
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    # Pin hub configs every verify-start (not only heal_verify_commands --write).
    hub_actions = _sync_lean_verify_to_hub_configs(root, lean, write=True)
    if hub_actions:
        rewritten = True
    # OVERSEER_RESTORE_LEAN_VERIFY_2026_09_07 — hub-protect vault SoT must match
    # lean or beat-mac peers-cap restore reintroduces stripped 9-cmd theater.
    vault_local = (
        Path.home()
        / ".config"
        / "automation-hub"
        / "hub-protect"
        / "automation.config.local.json"
    )
    if vault_local.is_file() and lean:
        try:
            vdata = json.loads(vault_local.read_text())
            if isinstance(vdata, dict) and list(vdata.get("verify_commands") or []) != lean:
                vdata = dict(vdata)
                vdata["verify_commands"] = list(lean)
                vdata["_overseer_verify_pin"] = "OVERSEER_RESTORE_LEAN_VERIFY_2026_09_07"
                vault_local.write_text(json.dumps(vdata, indent=2) + "\n")
                rewritten = True
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    paths = [adapt_state_path(root)]
    demoted = Path.home() / ".config" / "automation" / "adapt-state.json"
    if demoted not in paths:
        paths.append(demoted)
    for path in paths:
        if not path.is_file() and path != adapt_state_path(root):
            continue
        try:
            data = json.loads(path.read_text()) if path.is_file() else {}
        except (json.JSONDecodeError, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        if list(data.get("verify_commands") or []) == lean:
            continue
        data = dict(data)
        data["verify_commands"] = list(lean)
        if not data.get("_generated_at"):
            data["_generated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n")
            rewritten = True
        except OSError:
            continue
    # Refresh fingerprint so verify-start clears ADAPT_STALE in one shot.
    if sync_git_fingerprint(root):
        rewritten = True
    return rewritten



_registry_cache: dict[str, tuple[tuple[tuple[str, int, int], ...], dict[str, Any] | None]] = {}
_REGISTRY_CACHE_MAX = 8


def _registry_witness(root: Path) -> tuple[tuple[str, int, int], ...]:
    witness: list[tuple[str, int, int]] = []
    for reg_path in (root / "repos" / "registry.json", kit_root() / "repos" / "registry.json"):
        try:
            st = reg_path.stat()
            witness.append((str(reg_path), st.st_mtime_ns, st.st_size))
        except OSError:
            witness.append((str(reg_path), 0, 0))
    return tuple(witness)


def _registry_entry_might_match(entry_path: str, root_resolved: Path) -> bool:
    """Skip Path.resolve on cross-OS registry paths (Mac paths on Linux DGX)."""
    if sys.platform != "darwin" and entry_path.startswith("/Users/"):
        return False
    if sys.platform == "darwin" and entry_path.startswith("/home/"):
        return False
    try:
        return Path(entry_path).resolve() == root_resolved
    except OSError:
        return str(entry_path) == str(root_resolved)


def _load_registry(root: Path) -> dict[str, Any] | None:
    root_key = str(root)
    witness = _registry_witness(root)
    hit = _registry_cache.get(root_key)
    if hit and hit[0] == witness:
        return hit[1]
    root_resolved = root.resolve()
    matched: dict[str, Any] | None = None
    for reg_path in (root / "repos" / "registry.json", kit_root() / "repos" / "registry.json"):
        if not reg_path.is_file():
            continue
        try:
            data = json.loads(reg_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for entry in data.get("repos") or []:
            entry_path = entry.get("path")
            if not entry_path:
                continue
            if _registry_entry_might_match(str(entry_path), root_resolved):
                matched = entry
                break
        if matched is not None:
            break
    _registry_cache[root_key] = (witness, matched)
    if len(_registry_cache) > _REGISTRY_CACHE_MAX:
        oldest = min(_registry_cache, key=lambda k: _registry_cache[k][0][0][1] if _registry_cache[k][0] else 0)
        del _registry_cache[oldest]
    return matched


def _detect_package_manager(root: Path) -> str | None:
    if not (root / "package.json").is_file():
        return None
    if (root / "pnpm-lock.yaml").is_file() or (root / "pnpm-workspace.yaml").is_file():
        return "pnpm"
    if (root / "bun.lockb").is_file():
        return "bun"
    if (root / "yarn.lock").is_file():
        return "yarn"
    return "npm"


def _pm_run(pm: str, script: str) -> list[str]:
    if pm == "npm":
        return ["npm", "run", script]
    if pm in ("pnpm", "yarn", "bun"):
        return [pm, "run", script]
    return ["npm", "run", script]


def _pm_test(pm: str) -> list[str]:
    if pm == "npm":
        return ["npm", "test"]
    return [pm, "test"]


def _detect_automation_kit(root: Path) -> bool:
    return sum(1 for marker in KIT_MARKERS if (root / marker).is_file()) >= 2


def _detect_stack(root: Path) -> str:
    if list(root.glob("ram_*.py")) or (root / "ram.py").is_file():
        return "ram"
    if _detect_caas_fingerprint(root):
        return "caas"
    if (root / "package.json").is_file():
        return "node"
    if any((root / name).is_file() for name in ("pyproject.toml", "setup.py", "setup.cfg")):
        return "python"
    if (root / "requirements.txt").is_file():
        return "python"
    if (root / "Cargo.toml").is_file():
        return "rust"
    if (root / "go.mod").is_file():
        return "go"
    if _detect_automation_kit(root):
        return "automation"
    return "unknown"


def _detect_caas_fingerprint(root: Path) -> bool:
    markers = (
        "AGENT_MEMORY.md",
        "docs/agent/AGENT_WORKFLOW.md",
        "public/ide-agent.md",
        "docs/product/EXPERIENCE_ROADMAP.md",
    )
    if sum(1 for m in markers if (root / m).is_file()) >= 2:
        return True
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            raw = pkg.read_text().lower()
            if "newdrop" in raw or "caas" in raw:
                return True
        except OSError:
            pass
    return False


def _detect_frameworks(root: Path, stack: str) -> list[str]:
    fw: list[str] = []
    if stack == "node":
        pkg = root / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for name in ("next", "react", "vue", "svelte", "express", "vite"):
                    if name in deps:
                        fw.append(name)
            except (json.JSONDecodeError, OSError):
                pass
        if (root / "next.config.js").is_file() or (root / "next.config.mjs").is_file():
            fw.append("next")
    if stack == "python":
        for marker, label in (("django", "django"), ("fastapi", "fastapi"), ("flask", "flask")):
            req = root / "requirements.txt"
            if req.is_file() and marker in req.read_text().lower():
                fw.append(label)
        if (root / "pyproject.toml").is_file():
            text = (root / "pyproject.toml").read_text().lower()
            for label in ("django", "fastapi", "flask"):
                if label in text:
                    fw.append(label)
    if (root / "Package.swift").is_file() or list(root.glob("*.xcodeproj")):
        fw.append("swift")
    return sorted(set(fw))


def _read_package_name(root: Path) -> str | None:
    pkg = root / "package.json"
    if not pkg.is_file():
        return None
    try:
        data = json.loads(pkg.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    name = data.get("name")
    return str(name) if name else None


def _read_pyproject_name(root: Path) -> str | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        m = re.match(r'^name\s*=\s*"([^"]+)"', line.strip())
        if m:
            return m.group(1)
    return None


def _extract_ci_run_commands(root: Path) -> list[str]:
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    found: list[str] = []
    for yml in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        try:
            text = yml.read_text()
        except OSError:
            continue
        for match in re.finditer(r"run:\s*(.+?)\s*$", text, re.MULTILINE):
            cmd = match.group(1).strip()
            if cmd and not cmd.startswith("$") and cmd not in found:
                if any(x in cmd for x in ("npm", "pnpm", "yarn", "python", "pytest", "cargo", "go test", "unittest")):
                    found.append(cmd)
    return found[:12]


def _npm_script_candidates(root: Path, pm: str) -> list[str]:
    pkg = root / "package.json"
    if not pkg.is_file():
        return []
    try:
        scripts = json.loads(pkg.read_text()).get("scripts") or {}
    except (json.JSONDecodeError, OSError):
        return []
    cmds: list[str] = []
    for key in NODE_VERIFY_SCRIPTS:
        if key not in scripts:
            continue
        if key == "test":
            cmds.append(" ".join(_pm_test(pm)))
        else:
            cmds.append(" ".join(_pm_run(pm, key)))
    return cmds


def _caas_with_node_cmd(script: str) -> str:
    """Shell for Newdrop native verify via scripts/with-node.sh when present."""
    if script == "test":
        return "bash scripts/with-node.sh npm test"
    return f"bash scripts/with-node.sh npm run {script}"


def _is_hub_automation_unittest_cmd(cmd: str) -> bool:
    """True for hub lean unittest modules — poison on CaaS/product profiles."""
    low = (cmd or "").lower()
    if "unittest" not in low:
        return False
    # Hub OVERSEER regression suite (tests.test_peer_* / test_automation / …).
    return bool(
        re.search(
            r"unittest\s+tests\.test_(automation|run_peer_tasks|peer_|compact_|"
            r"pool_|adapt_|emit_|prepare_|auth_|parse_|cache_|self_check_)",
            low,
        )
    )


def _lean_caas_verify_commands(
    commands: list[str] | None, *, root: Path
) -> list[str]:
    """Pin CaaS verify to native product cmds — drop hub unittest theater.

    Needle: OVERSEER_CAAS_NATIVE_VERIFY_2026_09_07 — kit ``scripts/`` install +
    ``heal_verify_commands`` re-inserts hub lean suite into CaaS
    ``profiles/local.json`` (19 unittests) while registry B_verify expects
    ``with-node.sh npm test``. Adapt then looks "green" on wrong gate.
    """
    required: list[str] = []
    if (root / "scripts" / "peer_orchestrate.py").is_file():
        required.append("python3 scripts/peer_orchestrate.py --self-check")
    has_wrapper = (root / "scripts" / "with-node.sh").is_file()
    pkg_scripts: dict[str, Any] = {}
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            pkg_scripts = json.loads(pkg.read_text()).get("scripts") or {}
        except (json.JSONDecodeError, OSError, TypeError):
            pkg_scripts = {}
    if not isinstance(pkg_scripts, dict):
        pkg_scripts = {}
    if "test" in pkg_scripts:
        required.append(
            _caas_with_node_cmd("test") if has_wrapper else "npm test"
        )
    if "check:controls" in pkg_scripts:
        required.append(
            _caas_with_node_cmd("check:controls")
            if has_wrapper
            else "npm run check:controls"
        )
    seen: set[str] = set(required)
    out = list(required)
    for c in commands or []:
        if not isinstance(c, str) or not c.strip():
            continue
        if c in seen:
            continue
        if _is_hub_automation_unittest_cmd(c):
            continue
        if "unittest discover" in c.lower():
            continue
        seen.add(c)
        out.append(c)
    return out


def _stack_verify_candidates(root: Path, stack: str, pm: str | None) -> list[str]:
    cmds: list[str] = []
    if (root / "scripts" / "peer_orchestrate.py").is_file():
        cmds.append("python3 scripts/peer_orchestrate.py --self-check")

    cmds.extend(_extract_ci_run_commands(root))

    for target in _makefile_targets(root):
        if target in ("test", "lint", "check", "verify", "build", "ci"):
            cmds.append(f"make {target}")

    if _detect_monorepo(root) and pm:
        cmds.append(" ".join(_pm_run(pm, "test")))

    if stack == "node" and pm:
        cmds.extend(_npm_script_candidates(root, pm))
    elif stack == "caas":
        # OVERSEER_CAAS_NATIVE_VERIFY_2026_09_07 — do not fall through to
        # unittest discover; prefer with-node wrappers when present.
        has_wrapper = (root / "scripts" / "with-node.sh").is_file()
        pkg = root / "package.json"
        pkg_scripts: dict[str, Any] = {}
        if pkg.is_file():
            try:
                pkg_scripts = json.loads(pkg.read_text()).get("scripts") or {}
            except (json.JSONDecodeError, OSError, TypeError):
                pkg_scripts = {}
        if not isinstance(pkg_scripts, dict):
            pkg_scripts = {}
        if "test" in pkg_scripts:
            cmds.append(
                _caas_with_node_cmd("test") if has_wrapper else "npm test"
            )
        if "check:controls" in pkg_scripts:
            cmds.append(
                _caas_with_node_cmd("check:controls")
                if has_wrapper
                else "npm run check:controls"
            )
        if pm and not pkg_scripts:
            cmds.extend(_npm_script_candidates(root, pm))
    elif stack == "python":
        cmds.extend([
            "python3 -m pytest -q",
            "python3 -m unittest discover -s tests -q",
            "python3 -m ruff check .",
            "python3 -m mypy .",
        ])
    elif stack == "rust":
        cmds.extend(["cargo test --quiet", "cargo clippy -- -D warnings"])
    elif stack == "go":
        cmds.extend(["go test ./...", "go vet ./..."])
    elif stack == "ram":
        cmds.extend([
            "python3 -m unittest discover -s tests -q",
            "python3 ram.py --self-check",
        ])
    elif stack == "automation":
        cmds.extend([
            # Prefer lean hub verify (matches automation.config.local.json).
            # Full discover belongs on `./scripts/peer test`, not every heal/adapt.
            "python3 -m unittest tests.test_automation -q",
            # Deferred soft-skip / quiet-wait live only here — omit and verify/quick
            # stays green on false-PASS regressions (still lean: no discover).
            "python3 -m unittest tests.test_run_peer_tasks -q",
            # Never include `automation_adapt.py --audit` here — probing/auditing it
            # re-enters verify and fork-bombs unittest.
        ])
    else:
        cmds.append("python3 -m unittest discover -s tests -q")

    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in cmds:
        if c not in seen and not _is_recursive_adapt_command(c):
            seen.add(c)
            out.append(c)
    return out


def _is_recursive_adapt_command(cmd: str) -> bool:
    """True for adapt --audit/--heal probes that must not nest inside verify."""
    low = cmd.lower()
    if "automation_adapt" not in low:
        return False
    return any(flag in low for flag in ("--audit", "--heal", "--write"))


def _command_usable(proc: subprocess.CompletedProcess[str], cmd: str, *, root: Path | None = None) -> bool:
    if proc.returncode == 0:
        return True
    combined = ((proc.stdout or "") + (proc.stderr or "")).lower()
    # OVERSEER_AUDIT_OK_NE_USABLE_2026_09_04 — never bare "not found"
    # (matches AssertionError: 'cached' not found in…).
    skip_phrases = (
        "command not found",
        "no such file",
        "missing script",
        "lifecycle script",
        "no test specified",
        "cannot find module",
        "not recognized",
        "enoent",
        "npm error",
        "npm err!",
    )
    if any(p in combined for p in skip_phrases):
        return False
    low = cmd.lower()
    probe_root = root or ROOT
    if any(x in low for x in ("npm ", "pnpm ", "yarn ")) and not (probe_root / "package.json").is_file():
        return False
    # Non-zero but ran (e.g. failing tests) — still a valid verify command
    return bool(combined.strip())


def _lean_automation_verify_commands(commands: list[str] | None, *, stack: str | None = None) -> list[str]:
    """Drop full unittest discover from automation hub verify gates.

    Full discover belongs on `./scripts/peer test`, not adapt/heal/local.json.
    Previously only stripped when lean smoke was already present — so a
    discover-only probe could rewrite local.json and recontaminate adapt-state.
    Also drop echo stubs and CaaS npm check:controls pollution.

    OVERSEER_LEAN_CANON_ORDER_2026_09_04 — always emit required cmds in fixed
    order. Scrambled cache (run_peer_tasks before test_automation) made
    detect_signals' first-unittest fallback thrash test_command and re-open
    adapt audit warns every heal.
    """
    cmds = [c for c in (commands or []) if isinstance(c, str) and c.strip()]
    if stack not in (None, "automation"):
        return cmds
    discover = "python3 -m unittest discover -s tests -q"
    required = (
        "python3 scripts/peer_orchestrate.py --self-check",
        "python3 -m unittest tests.test_automation -q",
        "python3 -m unittest tests.test_run_peer_tasks -q",
        "python3 -m unittest tests.test_peer_worktree -q",
        "python3 -m unittest tests.test_peer_pen_test -q",
        # OVERSEER_LEAN_PEER_REMOTE_2026_09_04 — hub-protect exclude regressions
        "python3 -m unittest tests.test_peer_remote -q",
        # OVERSEER_LEAN_COMPACT_LAND_PROOF_2026_09_07 — deferred_poison land-proof theater
        "python3 -m unittest tests.test_compact_land_proof -q",
        # OVERSEER_LEAN_FACTORY_KIT_RUN_2026_09_08 — A→C→B + heal helpers (no verify theater)
        "python3 -m unittest tests.test_factory_kit_run -q",
        # OVERSEER_LEAN_LAST_CYCLE_POISON_2026_09_04
        # OVERSEER_LEAN_PEER_SELF_HEAL_2026_09_04 — sanitize deferred under verify_ok
        "python3 -m unittest tests.test_peer_last_cycle_poison -q",
        # OVERSEER_LEAN_PEER_SELF_HEAL_2026_09_04
        "python3 -m unittest tests.test_peer_self_heal -q",
        # OVERSEER_LEAN_PEER_REPO_RESEARCH_2026_09_04 — static-skip / false eval theater
        "python3 -m unittest tests.test_peer_repo_research -q",
        # OVERSEER_LEAN_POOL_ENSURE_FASTPATH_2026_09_06 — TTL fastpath + force=
        "python3 -m unittest tests.test_pool_ensure_fastpath -q",
        # OVERSEER_LEAN_DUAL_RESEARCH_LINUX_2026_09_06 — no launchctl on Linux
        "python3 -m unittest tests.test_peer_dual_research_linux_install -q",
        # OVERSEER_LEAN_STORM_BRAKE_2026_09_06 — no adapt pkill in dgx_utilization
        "python3 -m unittest tests.test_adapt_verify_protect -q",
        # OVERSEER_LEAN_EMIT_INVENTORY_TTL_2026_09_06 — porcelain list deferred on TTL
        "python3 -m unittest tests.test_emit_inventory_ttl_list_skip -q",
        # OVERSEER_LEAN_PREPARE_PROMPTS_TTL_2026_09_06 — gather deferred when age-fresh
        "python3 -m unittest tests.test_prepare_prompts_ttl -q",
        # OVERSEER_LEAN_AUTH_LIVE_SOFT_2026_09_06 — auth live hits never critical-stampede
        "python3 -m unittest tests.test_auth_live_soft -q",
        # OVERSEER_LEAN_PARSE_PHASED_TTL_2026_09_06 — md-fp + 60s TTL on WQ parse
        "python3 -m unittest tests.test_parse_phased_ttl -q",
        # OVERSEER_LEAN_CACHE_PATH_FALLBACK_2026_09_06 — unwritable shm → CONFIG_DIR
        "python3 -m unittest tests.test_cache_path_fallback -q",
        # OVERSEER_LEAN_SELF_CHECK_DEDUP_2026_09_07 — no orphan measure before build_plan
        "python3 -m unittest tests.test_self_check_dedup_measure -q",
    )
    # OVERSEER_LEAN_NO_EXTRAS_2026_09_04 — never append extras (drift → ADAPT_STALE).
    for c in cmds:
        if c == discover or "unittest discover" in c:
            continue
        if c.strip().startswith("echo "):
            continue
        if "check:controls" in c or "npm run check" in c:
            continue
        # OVERSEER_LEAN_DROP_COMBINED_UNITTEST_2026_09_04 — multi-module one-liners
        if "unittest" in c and c.count("tests.") > 1:
            continue
    # Ensure lean nonet — peer_remote + last_cycle_poison + repo_research stay visible.
    # OVERSEER_LEAN_PEN_TEST_2026_09_04
    # OVERSEER_LEAN_PEER_REMOTE_2026_09_04
    # OVERSEER_LEAN_PEER_REPO_RESEARCH_2026_09_04
    # OVERSEER_LEAN_POOL_ENSURE_FASTPATH_2026_09_06
    # OVERSEER_LEAN_DUAL_RESEARCH_LINUX_2026_09_06
    # OVERSEER_LEAN_EMIT_INVENTORY_TTL_2026_09_06
    # OVERSEER_LEAN_PREPARE_PROMPTS_TTL_2026_09_06
    # OVERSEER_LEAN_NONET_2026_09_04 — 14 required; beat must restore this needle.
    return list(required)



def probe_verify_commands(
    root: Path,
    candidates: list[str],
    *,
    quick: bool = False,
    cached: list[str] | None = None,
) -> list[str]:
    if quick:
        return _lean_automation_verify_commands(
            [c for c in (cached or []) if not _is_recursive_adapt_command(c)]
        )

    timeout = QUICK_PROBE_TIMEOUT if quick else PROBE_TIMEOUT
    working: list[str] = []
    candidates = [c for c in candidates if not _is_recursive_adapt_command(c)]

    def _probe_one(cmd: str) -> tuple[str, bool]:
        try:
            proc = _run(cmd, cwd=root, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            return cmd, quick and cmd.startswith("python3 scripts/peer_orchestrate")
        return cmd, _command_usable(proc, cmd, root=root)

    with ThreadPoolExecutor(max_workers=min(4, max(len(candidates), 1))) as pool:
        futures = {pool.submit(_probe_one, cmd): cmd for cmd in candidates}
        for fut in as_completed(futures):
            cmd, ok = fut.result()
            if ok:
                working.append(cmd)

    # preserve candidate order
    order = {c: i for i, c in enumerate(candidates)}
    working.sort(key=lambda c: order.get(c, 999))
    return working


def _test_candidates(stack: str, root: Path, pm: str | None) -> list[list[str]]:
    if stack == "node" and pm:
        out: list[list[str]] = [_pm_test(pm)]
        pkg = root / "package.json"
        if pkg.is_file():
            try:
                scripts = json.loads(pkg.read_text()).get("scripts") or {}
                if "test" in scripts and pm != "npm":
                    out.insert(0, _pm_test(pm))
            except (json.JSONDecodeError, OSError):
                pass
        return out
    if stack == "python":
        return [
            ["python3", "-m", "pytest", "-q"],
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-q"],
            ["python3", "-m", "unittest", "discover", "-q"],
        ]
    if stack == "rust":
        return [["cargo", "test", "--quiet"]]
    if stack == "go":
        return [["go", "test", "./..."]]
    return [["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]]


def probe_test_command(root: Path, stack: str, pm: str | None) -> tuple[list[str] | None, str | None]:
    for cmd in _test_candidates(stack, root, pm):
        try:
            proc = _run(cmd, cwd=root, timeout=PROBE_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if proc.returncode == 0:
            return cmd, "ok"
        combined = (proc.stdout or "") + (proc.stderr or "")
        if "no test specified" in combined.lower() or "missing script" in combined.lower():
            continue
    return None, None


def _scan_kit_scripts_scope(root: Path, scope: dict[str, str]) -> None:
    scripts_dir = root / "scripts"
    if not scripts_dir.is_dir():
        return
    for path in sorted(scripts_dir.glob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("test_"):
            continue
        scope[path.stem] = f"scripts/{path.name}"
        if len(scope) >= MAX_MODULE_RULES:
            return


def scan_module_scope(root: Path, stack: str) -> dict[str, str]:
    scope: dict[str, str] = {}
    if stack == "automation" or _detect_automation_kit(root):
        _scan_kit_scripts_scope(root, scope)
    if stack in ("ram", "python"):
        for path in sorted(root.glob("ram_*.py"))[:MAX_MODULE_RULES]:
            scope[path.stem] = path.name
        for path in sorted((root / "contrib").glob("*.py"))[:8]:
            key = f"contrib/{path.stem}"
            scope[key] = f"contrib/{path.name}"
    if stack == "node":
        for pattern in ("src/**/*.ts", "src/**/*.tsx", "app/**/*.ts", "packages/*/src/**/*.ts"):
            for path in sorted(root.glob(pattern))[:MAX_MODULE_RULES]:
                rel = str(path.relative_to(root))
                if ".test." in path.name or ".spec." in path.name:
                    continue
                key = rel.replace("/", "_").replace(".", "_")[:40]
                scope.setdefault(key, rel)
                if len(scope) >= MAX_MODULE_RULES:
                    break
    if stack == "caas":
        for rel in ("src/lib/billing/", "src/lib/security/", "src/components/", "src/app/api/"):
            p = root / rel
            if p.is_dir():
                scope[rel.rstrip("/").replace("/", "_")] = rel
    existing = CFG.get("module_scope") or {}
    if isinstance(existing, dict):
        for k, v in existing.items():
            scope.setdefault(str(k), str(v))
    return dict(list(scope.items())[:MAX_MODULE_RULES])


def _existing_reads(root: Path, candidates: list[str]) -> list[str]:
    return [c for c in candidates if (root / c).is_file()]


def _strip_generated_overlay(profile: dict[str, Any]) -> dict[str, Any]:
    """Remove prior adapt-generated templates/rules before re-merge."""
    out = dict(profile)
    templates = dict(out.get("task_templates") or {})
    for key in list(templates):
        if any(key.startswith(p) for p in GENERATED_TEMPLATE_PREFIXES):
            del templates[key]
    out["task_templates"] = templates

    rules = [
        r for r in (out.get("match_rules") or [])
        if not any(str(r.get("template", "")).startswith(p) for p in GENERATED_TEMPLATE_PREFIXES)
    ]
    out["match_rules"] = rules
    return out


def generate_local_profile(root: Path, signals: ProjectSignals) -> dict[str, Any]:
    """Build profiles/local.json overlay from live project signals."""
    reads_impl = _existing_reads(root, [
        "AGENTS.md", "AGENT_MEMORY.md", "README.md",
        "docs/agent/AGENT_WORKFLOW.md", "docs/product/EXPERIENCE_ROADMAP.md",
        "notes/SAFETY_GATES.md", "notes/VALUE_STACK.md",
    ])
    reads_verify = _existing_reads(root, ["AGENTS.md", "docs/agent/AGENT_WORKFLOW.md", "notes/AUTOMATION.md"])

    fp = signals.adapt_fingerprint or _git_fingerprint(Path(signals.root))
    if signals.stack == "caas":
        verify_cmds = _lean_caas_verify_commands(
            signals.verify_commands, root=Path(signals.root)
        )
    else:
        verify_cmds = _lean_automation_verify_commands(
            signals.verify_commands, stack=signals.stack
        )
    profile: dict[str, Any] = {
        "_generated_by": "automation_adapt.py",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "verify_commands": verify_cmds,
    }
    if fp is not None:
        profile["_git_fingerprint"] = fp

    if signals.module_scope:
        profile["module_scope"] = signals.module_scope

    peers_patch: dict[str, Any] = {}
    if reads_impl:
        peers_patch["implement"] = {"reads": reads_impl[:6]}
    if reads_verify:
        peers_patch["verify"] = {"reads": reads_verify[:4]}
    if peers_patch:
        profile["peers"] = peers_patch

    match_rules: list[dict[str, Any]] = list(profile.get("match_rules") or [])
    templates: dict[str, Any] = dict(profile.get("task_templates") or {})

    for mod, path in list(signals.module_scope.items())[:MAX_MODULE_RULES]:
        tmpl = f"scope_{re.sub(r'[^a-z0-9_]', '_', mod.lower())}"
        match_rules.append({
            "template": tmpl,
            "any": [mod.replace("_", " "), mod, path.split("/")[-1]],
            "priority": 45,
        })
        templates[tmpl] = {
            "peer": "implement",
            "safety_tier": "green",
            "scope": [path] if not path.endswith("/") else [path],
            "prompt": f"Implement queue item for `{mod}`. Minimal diff; match repo conventions; run verify before done.",
        }

    for fw in signals.frameworks:
        tmpl = f"fw_{fw}"
        match_rules.append({"template": tmpl, "any": [fw], "priority": 30})
        templates[tmpl] = {
            "peer": "implement",
            "safety_tier": "green",
            "scope": [],
            "prompt": f"Implement {fw}-related queue item. Follow framework conventions; minimal diff.",
        }

    if match_rules:
        profile["match_rules"] = match_rules
    if templates:
        profile["task_templates"] = templates

    constraints: list[str] = []
    agents = root / "AGENTS.md"
    if agents.is_file():
        for line in agents.read_text().splitlines()[:40]:
            if line.strip().startswith("- "):
                constraints.append(line.strip()[2:].strip()[:120])
    if constraints:
        profile["product_constraints"] = constraints[:6]

    return profile


def apply_local_profile(root: Path, profile: dict[str, Any], *, write: bool = False) -> dict[str, Any]:
    path = root / "profiles" / "local.json"
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = _strip_generated_overlay(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            existing = {}

    merged = auto._deep_merge(existing, profile)
    # verify_commands must replace, not append — deep_merge concatenates lists and
    # would permanently retain dropped probes (e.g. unittest discover) → adapt_state drift.
    if "verify_commands" in profile:
        merged["verify_commands"] = list(profile["verify_commands"] or [])
    # module_scope must replace — deep_merge keeps deleted keys (stale
    # _overseer_land_stagnation → missing-path audit warn forever).
    if "module_scope" in profile:
        merged["module_scope"] = dict(profile["module_scope"] or {})
    # Lean by target stack — kit-copied profiles/automation.json on CaaS must
    # NOT re-run hub lean (OVERSEER_CAAS_NATIVE_VERIFY_2026_09_07). Hub empty
    # temps / CFG task_profile=automation still lean for replace-verify tests.
    target_stack = _detect_stack(root)
    if target_stack == "caas":
        merged["verify_commands"] = _lean_caas_verify_commands(
            merged.get("verify_commands"), root=root
        )
    elif target_stack in ("node", "ram", "python", "rust", "go"):
        pass
    elif (
        target_stack == "automation"
        or (root / "profiles" / "automation.json").is_file()
        or auto.CFG.get("task_profile") == "automation"
    ):
        merged["verify_commands"] = _lean_automation_verify_commands(
            merged.get("verify_commands"), stack="automation"
        )
    for meta_key in ("_generated_by", "_generated_at", "_git_fingerprint"):
        merged[meta_key] = profile.get(meta_key)

    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2) + "\n")
    return {"path": str(path), "written": write, "verify_count": len(merged.get("verify_commands") or [])}


def _guess_rss_entrypoint(root: Path, stack: str) -> str | None:
    if stack not in ("python", "ram"):
        return None
    for candidate in ("ram.py", "main.py", "app.py", "src/main.py"):
        if (root / candidate).is_file():
            return candidate
    return None


def _guess_post_cycle_hook(root: Path, stack: str, pm: str | None) -> list[str] | None:
    if stack == "ram" and (root / "ram.py").is_file():
        return ["python3", "ram.py", "install"]
    if stack == "node" and pm:
        pkg = root / "package.json"
        if pkg.is_file():
            try:
                scripts = json.loads(pkg.read_text()).get("scripts") or {}
                for key in ("build", "prepare"):
                    if key in scripts:
                        return _pm_run(pm, key)
            except (json.JSONDecodeError, OSError):
                pass
    return None


def _kit_status(root: Path) -> tuple[bool, bool, list[str]]:
    missing = [rel for rel in KIT_MARKERS if not (root / rel).is_file()]
    has_kit = (root / "scripts" / "peer_orchestrate.py").is_file()
    return has_kit, len(missing) == 0, missing


def _infer_profile(root: Path, stack: str, registry: dict[str, Any] | None) -> str:
    if registry and registry.get("profile") in KNOWN_PROFILES:
        return str(registry["profile"])
    return PROFILE_BY_STACK.get(stack, "generic")


def detect_signals(root: Path | None = None, *, quick: bool = False) -> ProjectSignals:
    root = (root or ROOT).resolve()
    registry = _load_registry(root)
    stack = _detect_stack(root)
    pm = _detect_package_manager(root)
    profile = _infer_profile(root, stack, registry)
    frameworks = _detect_frameworks(root, stack)

    name = (registry or {}).get("name") or _read_package_name(root) or _read_pyproject_name(root) or root.name
    slug = (registry or {}).get("namespace") or _slug(str(name))

    prev_state = load_adapt_state(root)
    ci_cmds = _extract_ci_run_commands(root)
    candidates = _stack_verify_candidates(root, stack, pm)
    # Prefer live local.json over adapt-state cache on quick path — stale
    # cache with discover was rewriting lean local profiles every heal.
    cached_verify = prev_state.get("verify_commands")
    local_path = root / "profiles" / "local.json"
    if quick and local_path.is_file():
        try:
            local_verify = json.loads(local_path.read_text()).get("verify_commands") or []
            if local_verify:
                cached_verify = local_verify
        except (json.JSONDecodeError, OSError):
            pass
    verify_cmds = probe_verify_commands(
        root,
        candidates,
        quick=quick,
        cached=cached_verify,
    )
    verify_cmds = _lean_automation_verify_commands(verify_cmds, stack=stack)
    if not verify_cmds:
        verify_cmds = _lean_automation_verify_commands(candidates[:4], stack=stack)

    test_cmd, probe = probe_test_command(root, stack, pm) if not quick else (None, None)
    if not test_cmd and verify_cmds:
        for vc in verify_cmds:
            if any(x in vc for x in ("test", "pytest", "unittest", "cargo test", "go test")):
                test_cmd = _parse_shell_command(vc)
                break
    # Pin hub smoke test_command — discover probe often fails under swarm;
    # fallback used to pick whichever unittest landed first in scrambled verify.
    # OVERSEER_LEAN_CANON_ORDER_2026_09_04
    if profile == "automation" or stack == "automation":
        test_cmd = ["python3", "-m", "unittest", "tests.test_automation", "-q"]
        probe = probe or "ok"

    has_kit, kit_complete, missing = _kit_status(root)
    fp = _git_fingerprint(root)

    return ProjectSignals(
        root=str(root),
        stack=stack,
        profile=profile,
        package_manager=pm,
        frameworks=frameworks,
        project_name=str(name),
        project_slug=_slug(str(name)),
        config_namespace=slug,
        launch_agent_label=f"com.togi.{slug}-peer-loop",
        test_command=test_cmd,
        test_probe=probe,
        verify_commands=verify_cmds,
        module_scope=scan_module_scope(root, stack if profile != "caas" else "caas"),
        rss_entrypoint=_guess_rss_entrypoint(root, stack),
        post_cycle_hook=_guess_post_cycle_hook(root, stack, pm),
        has_kit=has_kit,
        kit_complete=kit_complete,
        missing_kit_paths=missing,
        registry_match=registry,
        ci_commands=ci_cmds,
        adapt_fingerprint=fp,
    )


def config_patches(signals: ProjectSignals, existing: dict | None = None) -> dict[str, Any]:
    existing = existing or {}
    patches: dict[str, Any] = {}
    # OVERSEER_PRESERVE_HUB_NS_2026_09_04 — folder slug "automation" must not
    # demote live hub identity (wrong adapt-state path + Mac rsync thrash).
    # OVERSEER_FORCE_HUB_NS_RESTORE_2026_09_04 — prior preserve only *skipped*
    # when already hub; demoted ns=automation stayed stuck. Force-restore.
    _HUB_IDENTITY = {
        "config_namespace": "automation-hub",
        "launch_agent_label": "com.togi.automation-hub-peer-loop",
        "project_slug": "automation-hub",
        "project_name": "Automation Hub",
    }
    root = Path(getattr(signals, "root", "") or ".")
    if _is_automation_hub_kit(root, existing):
        for key, hub_val in _HUB_IDENTITY.items():
            if existing.get(key) != hub_val:
                patches[key] = hub_val
    else:
        for key in ("project_name", "project_slug", "config_namespace", "launch_agent_label"):
            val = getattr(signals, key)
            if existing.get(key) != val:
                patches[key] = val
    if signals.profile and existing.get("task_profile") != signals.profile:
        patches["task_profile"] = signals.profile
    if signals.test_command and existing.get("test_command") != signals.test_command:
        patches["test_command"] = signals.test_command
    if signals.rss_entrypoint and not existing.get("rss_entrypoint"):
        patches["rss_entrypoint"] = signals.rss_entrypoint
    if signals.post_cycle_hook and not existing.get("post_cycle_hook"):
        patches["post_cycle_hook"] = signals.post_cycle_hook
    if signals.module_scope and existing.get("module_scope") != signals.module_scope:
        merged_scope = dict(existing.get("module_scope") or {})
        merged_scope.update(signals.module_scope)
        patches["module_scope"] = merged_scope
    return patches



def apply_config(signals: ProjectSignals, *, write: bool = False) -> dict[str, Any]:
    path = Path(signals.root) / "automation.config.json"
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
    patches = config_patches(signals, existing)
    if not patches:
        return {"path": str(path), "patches": {}, "written": False}
    merged = dict(existing)
    merged.update(patches)
    if write:
        path.write_text(json.dumps(merged, indent=2) + "\n")
    return {"path": str(path), "patches": patches, "written": write}



def _sync_lean_verify_to_hub_configs(
    root: Path, lean: list[str], *, write: bool = False
) -> list[str]:
    """Pin hub config verify_commands to lean split — OVERSEER_LEAN_HUB_CONFIG_2026_09_04.

    Mac/rsync + overlay thrash rewrites combined multi-module one-liners into
    automation.config.json / .local.json; profiles/local.json stays lean → adapt
    audit / verify storms. Heal must rewrite both hub configs when they drift.
    """
    actions: list[str] = []
    if not lean:
        return actions
    for name in ("automation.config.json", "automation.config.local.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        cur = data.get("verify_commands") or []
        if cur == lean:
            continue
        if write:
            data["verify_commands"] = list(lean)
            path.write_text(json.dumps(data, indent=2) + "\n")
            actions.append(f"lean hub verify synced: {name}")
        else:
            actions.append(f"would lean-sync hub verify: {name}")
    return actions


def heal_verify_commands(root: Path, signals: ProjectSignals, *, quick: bool = False, write: bool = False) -> list[str]:
    """Re-probe verify commands; rewrite local.json when broken commands drop off."""
    actions: list[str] = []
    local_path = root / "profiles" / "local.json"
    existing_verify: list[str] = []
    if local_path.is_file():
        try:
            existing_verify = json.loads(local_path.read_text()).get("verify_commands") or []
        except (json.JSONDecodeError, OSError):
            pass

    candidates = _stack_verify_candidates(root, signals.stack, signals.package_manager)
    for cmd in existing_verify:
        # OVERSEER_CAAS_NATIVE_VERIFY_2026_09_07 — never re-poison caas candidates
        # with hub lean unittest suite from a prior kit-sync local.json.
        if signals.stack == "caas" and _is_hub_automation_unittest_cmd(cmd):
            continue
        if cmd not in candidates:
            candidates.insert(0, cmd)

    # Quick path: trust lean local.json instead of re-probing discover.
    # CaaS: never trust poisoned hub-unittest local.json as cache.
    if (
        quick
        and existing_verify
        and not (
            signals.stack == "caas"
            and any(_is_hub_automation_unittest_cmd(c) for c in existing_verify)
        )
    ):
        cached = existing_verify
    else:
        cached = None
    fresh = probe_verify_commands(root, candidates, quick=quick, cached=cached)
    if signals.stack == "automation":
        lean_self = "python3 scripts/peer_orchestrate.py --self-check"
        lean_test = "python3 -m unittest tests.test_automation -q"
        lean_rpt = "python3 -m unittest tests.test_run_peer_tasks -q"
        for cmd in (lean_self, lean_test, lean_rpt):
            if cmd not in fresh:
                fresh.insert(0, cmd)
        # Drop full discover when lean smoke test is present — avoids
        # verify_commands drift vs config.local and unittest storms on heal.
        fresh = _lean_automation_verify_commands(fresh, stack="automation")
    elif signals.stack == "caas":
        fresh = _lean_caas_verify_commands(fresh, root=root)
    if not fresh:
        return actions

    dropped = [c for c in existing_verify if c not in fresh]
    added = [c for c in fresh if c not in existing_verify]

    if dropped or added or not local_path.is_file():
        signals.verify_commands = fresh
        overlay = generate_local_profile(root, signals)
        result = apply_local_profile(root, overlay, write=write)
        if write:
            actions.append(f"verify commands updated ({len(fresh)} working)")
            for d in dropped:
                actions.append(f"dropped broken verify: {d[:60]}")
            for a in added:
                actions.append(f"added verify: {a[:60]}")
        else:
            actions.append(f"would update verify commands ({len(fresh)} working)")
    elif signals.stack == "automation":
        signals.verify_commands = fresh
    if signals.stack == "automation":
        actions.extend(_sync_lean_verify_to_hub_configs(root, fresh, write=write))
    return actions


def _bootstrap_scaffold(root: Path, *, write: bool = False) -> list[str]:
    """Ensure minimal queue/context files exist for a fresh install."""
    actions: list[str] = []
    ctx_path, wq_path = _queue_paths(root)
    if not wq_path.is_file() and write:
        wq_path.parent.mkdir(parents=True, exist_ok=True)
        wq_path.write_text(
            "# Work queue\n\n## Active items\n\n"
            "1. [ ] **Bootstrap automation** — run `python3 scripts/automation_adapt.py --heal --write`\n"
        )
        actions.append(f"created {wq_path.relative_to(root)}")
    if not ctx_path.is_file() and write:
        ctx_path.parent.mkdir(parents=True, exist_ok=True)
        ctx_path.write_text(
            "# Self-improve context\n\n## Loop\n\nactive\n\n"
            "## Remaining work (priority order)\n\n"
            "1. [ ] **Bootstrap automation** — run adapt --heal --write\n\n"
            "## Product rules (never regress)\n\n"
            "- Keep notes/WORK_QUEUE.md ↔ this file in sync\n"
        )
        actions.append(f"created {ctx_path.relative_to(root)}")
    return actions


def adapt_registry_repos(
    *,
    write: bool = False,
    quick: bool = False,
    force: bool = False,
    only_profile: str | None = None,
) -> list[HealReport]:
    """Adapt every registry repo that exists on disk."""
    reg_path = kit_root() / "repos" / "registry.json"
    if not reg_path.is_file():
        return []
    try:
        data = json.loads(reg_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    reports: list[HealReport] = []
    for entry in data.get("repos") or []:
        path_str = entry.get("path")
        profile = entry.get("profile")
        if not path_str:
            continue
        if only_profile and profile != only_profile:
            continue
        root = Path(path_str).expanduser()
        if not root.is_dir():
            continue
        if profile and write:
            cfg = root / "automation.config.json"
            existing: dict[str, Any] = {}
            if cfg.is_file():
                try:
                    existing = json.loads(cfg.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
            if existing.get("task_profile") != profile:
                existing["task_profile"] = profile
                cfg.write_text(json.dumps(existing, indent=2) + "\n")
        reports.append(run_heal(write=write, target=root, quick=quick, force=force))
    return reports


def install_kit(target: Path, *, force_scripts: bool = False, profile: str | None = None) -> list[str]:
    hub = kit_root()
    actions: list[str] = []
    target = target.resolve()
    seen_actions: set[str] = set()
    for rel in KIT_COPY_PATHS:
        src = hub / rel
        dst = target / rel
        if not src.exists():
            continue
        if src.is_file():
            # Machine-local secrets / overlays — never --install into foreign trees.
            # Needle: OVERSEER_KIT_INSTALL_NO_LOCAL_SECRETS_2026_09_08
            if _kit_basename_is_local_secret(src.name):
                msg = f"skip (secret): {rel}"
                if msg not in seen_actions:
                    actions.append(msg)
                    seen_actions.add(msg)
                continue
            if _kit_basename_is_weight(src.name):
                msg = f"skip (weight): {rel}"
                if msg not in seen_actions:
                    actions.append(msg)
                    seen_actions.add(msg)
                continue
            if dst.is_file() and not force_scripts:
                msg = f"skip (exists): {rel}"
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
                if rel.startswith("scripts/"):
                    try:
                        dst.chmod(dst.stat().st_mode | 0o111)
                    except OSError:
                        pass
                msg = f"installed: {rel}"
            if msg not in seen_actions:
                actions.append(msg)
                seen_actions.add(msg)
        elif src.is_dir():
            for item in src.rglob("*"):
                if item.is_dir():
                    continue
                # Machine-local secrets / overlays — install must match export filter.
                # Needle: OVERSEER_KIT_INSTALL_NO_LOCAL_SECRETS_2026_09_08
                if _kit_basename_is_local_secret(item.name):
                    msg = f"skip (secret): {item.relative_to(hub)}"
                    if msg not in seen_actions:
                        actions.append(msg)
                        seen_actions.add(msg)
                    continue
                # Local-only weights — never copy into target repos (install ≠ publish).
                # Needle: OVERSEER_KIT_INSTALL_NO_WEIGHTS_2026_09_07
                if _kit_basename_is_weight(item.name):
                    msg = f"skip (weight): {item.relative_to(hub)}"
                    if msg not in seen_actions:
                        actions.append(msg)
                        seen_actions.add(msg)
                    continue
                item_rel = item.relative_to(hub)
                out = target / item_rel
                if out.is_file() and not force_scripts:
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(item.read_bytes())
                if "scripts" in item_rel.parts:
                    try:
                        out.chmod(out.stat().st_mode | 0o111)
                    except OSError:
                        pass
                msg = f"installed: {item_rel}"
                if msg not in seen_actions:
                    actions.append(msg)
                    seen_actions.add(msg)
    if profile:
        sig = detect_signals(target, quick=True)
        sig.profile = profile
        apply_config(sig, write=True)
        actions.append(f"set task_profile={profile}")
    return actions


def _insert_queue_item(section_lines: list[str], item_text: str) -> list[str]:
    norm = auto._normalize_queue_key(item_text)
    for line in section_lines:
        parsed = auto._parse_work_item(line.strip())
        if parsed and auto._normalize_queue_key(parsed) == norm:
            return section_lines
    nums = [int(m.group(1)) for line in section_lines if (m := re.match(r"^(\d+)\.", line.strip()))]
    n = max(nums, default=0) + 1
    return section_lines + [f"{n}. [ ] **{item_text}** — synced by automation_adapt"]


def _insert_work_queue_item(work_md: str, item_text: str) -> str:
    norm = auto._normalize_queue_key(item_text)
    stop = ("## Creative backlog", "## Done", "## Metrics", "## Backlog")
    in_active = False
    for line in work_md.splitlines():
        s = line.strip()
        if s.startswith("## Active") or s.startswith("## Phase"):
            in_active = True
            continue
        if in_active and any(s.startswith(p) for p in stop):
            in_active = False
        if in_active:
            parsed = auto._parse_work_item(s)
            if parsed and auto._normalize_queue_key(parsed) == norm:
                return work_md
    lines = work_md.splitlines()
    out: list[str] = []
    i = 0
    inserted = False
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if not inserted and line.strip().startswith("## Active"):
            out.append(_open_queue_bullet_line(item_text))
            inserted = True
        i += 1
    if not inserted:
        out.extend(["", "## Active", "", _open_queue_bullet_line(item_text)])
    return "\n".join(out).rstrip() + "\n"


def _ensure_context_active_open(context_md: str, item_text: str) -> tuple[str, bool]:
    """Ensure SIC ## Active has an open bullet matching WQ Active (file twin).

    Needle: OVERSEER_SIC_ACTIVE_MIRROR_HEAL_2026_09_08 — Remaining-only sync clears
    dual-brain via Remaining∪Active union while SIC ## Active stays empty → agents
    edit only one brain; Mac rsync reopens drift. Mirror Active opens explicitly.
    """
    if not context_md or not item_text:
        return context_md, False
    norm = auto._normalize_queue_key(item_text)
    lines = context_md.splitlines()
    in_active = False
    stop = ("## Creative backlog", "## Done", "## Metrics", "## Backlog", "## Remaining")
    for line in lines:
        s = line.strip()
        if s.startswith("## Active") or s.startswith("## Phase"):
            in_active = True
            continue
        if in_active and any(s.startswith(p) for p in stop):
            in_active = False
        if in_active and s.startswith("- [ ]"):
            parsed = auto._parse_work_item(s)
            if parsed and auto._normalize_queue_key(parsed) == norm:
                return context_md, False
    bullet = _open_queue_bullet_line(item_text)
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().startswith("## Active"):
            out.append(bullet)
            inserted = True
    if not inserted:
        out = ["## Active", "", bullet, ""] + lines
        inserted = True
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, inserted


def _insert_context_item(context_md: str, item_text: str) -> str:
    """Insert open item under Remaining. Active twins must NOT short-circuit.

    OVERSEER_INSERT_CTX_REMAINING_ONLY_2026_09_07 — when SIC mirrors WQ ## Active
    and Remaining lacks the open bullet, whole-file duplicate scan returned early
    → Remaining stayed empty → dual-brain HIGH forever (WQ Active vs Remaining).
    Only treat as present when the key is already under Remaining.

    OVERSEER_SIC_ACTIVE_MIRROR_HEAL_2026_09_08 — also ensure ## Active carries the
    same open (file-level twin), not Remaining-only.
    """
    heading = "## Remaining work (priority order)"
    norm = auto._normalize_queue_key(item_text)
    remaining_keys = {
        auto._normalize_queue_key(i) for i in auto.remaining_work_items(context_md)
    }
    if norm not in remaining_keys:
        bullet = _open_queue_bullet_line(item_text)
        if heading not in context_md:
            context_md = context_md.rstrip() + f"\n\n{heading}\n\n{bullet}\n"
        else:
            lines = context_md.splitlines()
            out: list[str] = []
            i = 0
            while i < len(lines):
                line = lines[i]
                if line.strip() == heading:
                    out.append(line)
                    out.append(bullet)
                    i += 1
                    while i < len(lines) and not lines[i].startswith("## "):
                        out.append(lines[i])
                        i += 1
                    continue
                out.append(line)
                i += 1
            context_md = "\n".join(out).rstrip() + "\n"
    context_md, _ = _ensure_context_active_open(context_md, item_text)
    return context_md


def _work_queue_open_items(work_md: str) -> list[str]:
    items = auto._parse_phased_work_items(work_md)
    if items:
        return items
    for line in auto.extract_section_lines(work_md, "Active items"):
        parsed = auto._parse_work_item(line.strip())
        if parsed:
            items.append(parsed)
    return items


def _is_top10_queue_item(item: str) -> bool:
    """True for Top10 production / TOP10_NEXT Active work (Mac↔CLEAN must not drop)."""
    low = re.sub(r"\*\*", "", item).strip().lower()
    return "[top10]" in low or low.startswith("top10")


def _open_queue_bullet_line(item_text: str) -> str:
    """Format an open Active bullet without double-wrapping ** markers."""
    body = item_text.strip()
    if body.startswith("- [ ]"):
        return body
    if not body.startswith("**"):
        body = f"**{body}**"
    return f"- [ ] {body}"


def _sync_drift_lists(context_md: str, work_md: str) -> list[str]:
    """Drift = context opens (Remaining∪Active) vs WQ Active/phased opens."""
    warnings: list[str] = []
    if auto.context_twin_structure_broken(context_md, work_md):
        warnings.append(
            "self_improve_context missing Active/Remaining structure vs WORK_QUEUE "
            "(headerless twin — restore from WQ)"
        )
    # OVERSEER_HEAL_CTX_OPEN_UNION_2026_09_07 — same union as sync_queue_drift.
    ctx_items = auto.context_queue_open_items(context_md)
    wq_items = auto._parse_phased_work_items(work_md)  # noqa: SLF001
    ctx_keys = {auto._normalize_queue_key(i): i for i in ctx_items}
    wq_keys = {auto._normalize_queue_key(i): i for i in wq_items}
    ctx_top10_only = [
        raw for key, raw in ctx_keys.items() if key not in wq_keys and _is_top10_queue_item(raw)
    ]
    # OVERSEER_MAC_CLEAN_QUEUE_TWIN_2026_09_07 — empty CLEAN Active must not
    # silently drop Mac/context Top10 opens (hub-protect + heal used to delete).
    if not wq_items and ctx_top10_only:
        warnings.append(
            "CLEAN empty-Active while context has Top10 opens — restore WORK_QUEUE "
            f"({len(ctx_top10_only)} item(s); Mac↔CLEAN twin)"
        )
    for key, raw in ctx_keys.items():
        if key not in wq_keys:
            warnings.append(f"only in self_improve_context: {raw[:80]}")
    for key, raw in wq_keys.items():
        if key not in ctx_keys:
            warnings.append(f"only in notes/WORK_QUEUE.md: {raw[:80]}")
    return warnings


def _queue_paths(root: Path) -> tuple[Path, Path]:
    cfg_path = root / "automation.config.json"
    paths = CFG.get("paths", {})
    if cfg_path.is_file():
        try:
            paths = json.loads(cfg_path.read_text()).get("paths", paths)
        except (json.JSONDecodeError, OSError):
            pass
    rel_ctx = paths.get("context", "scripts/self_improve_context.md")
    rel_wq = paths.get("work_queue", "notes/WORK_QUEUE.md")
    return root / rel_ctx, root / rel_wq


def _remove_context_open_item(context_md: str, item_text: str) -> tuple[str, bool]:
    """Remove one open queue line from context (WORK_QUEUE is source of truth)."""
    norm = auto._normalize_queue_key(item_text)
    out: list[str] = []
    removed = False
    for line in context_md.splitlines():
        parsed = auto._parse_work_item(line.strip())
        if parsed and auto._normalize_queue_key(parsed) == norm:
            removed = True
            continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def _reconcile_context_from_work_queue(context_md: str, work_md: str) -> tuple[str, list[str]]:
    """Replace truncated/corrupt context lines with canonical WORK_QUEUE lines."""
    wq_line_by_key: dict[str, str] = {}
    for line in work_md.splitlines():
        stripped = line.strip()
        parsed = auto._parse_work_item(stripped)
        if parsed:
            wq_line_by_key[auto._normalize_queue_key(parsed)] = stripped
    actions: list[str] = []
    out: list[str] = []
    in_remaining = False
    for line in context_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Remaining work"):
            in_remaining = True
            out.append(line)
            continue
        if in_remaining and stripped.startswith("## "):
            in_remaining = False
        if in_remaining:
            parsed = auto._parse_work_item(stripped)
            if parsed:
                key = auto._normalize_queue_key(parsed)
                canonical_line = wq_line_by_key.get(key)
                if canonical_line and stripped != canonical_line:
                    out.append(canonical_line)
                    actions.append(f"reconciled context: {parsed[:60]}")
                    continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, actions


def heal_queue_drift(*, root: Path, write: bool = False) -> tuple[list[str], list[str]]:
    ctx_path, wq_path = _queue_paths(root)
    context_md = ctx_path.read_text() if ctx_path.is_file() else ""
    work_md = wq_path.read_text() if wq_path.is_file() else ""
    actions: list[str] = []

    # OVERSEER_MAC_CLEAN_QUEUE_TWIN_2026_09_07 — poison twin + tmp clobber artifacts
    poison_ctx = root / "notes" / "self_improve_context.md"
    if poison_ctx.is_file():
        if write:
            try:
                poison_ctx.unlink()
                actions.append(
                    "removed poison notes/self_improve_context.md (canonical scripts/)"
                )
            except OSError:
                pass
        else:
            actions.append(
                "would remove poison notes/self_improve_context.md (canonical scripts/)"
            )
    wq_tmp = root / "notes" / "WORK_QUEUE.md.tmp"
    if wq_tmp.exists():
        if write:
            import shutil

            try:
                if wq_tmp.is_dir():
                    shutil.rmtree(wq_tmp)
                else:
                    wq_tmp.unlink()
                actions.append("removed notes/WORK_QUEUE.md.tmp clobber artifact")
            except OSError:
                pass
        else:
            actions.append("would remove notes/WORK_QUEUE.md.tmp clobber artifact")

    # OVERSEER_HEADERLESS_SIC_DRIFT_2026_09_07 — restore twin before item sync
    # (headerless fuel orphans are invisible to remaining_work_items).
    if auto.context_twin_structure_broken(context_md, work_md):
        context_md = work_md if work_md.endswith("\n") else work_md + "\n"
        actions.append("restored headerless context twin from WORK_QUEUE")

    # OVERSEER_HEAL_CLOSE_LANDED_BEFORE_SYNC_2026_09_04 — Mac rsync reopens
    # proof-green Active (e.g. HUB_PROTECT); syncing those into Remaining
    # widens dual-brain. Close landed first so drift heal shrinks queue_fp.
    work_md, landed_w = auto.close_landed_done_orphans(work_md)
    context_md, landed_c = auto.close_landed_done_orphans(context_md)
    if landed_w + landed_c:
        actions.append(f"closed {landed_w + landed_c} landed Active/Done orphan(s)")

    new_context, new_work = context_md, work_md
    # OVERSEER_HEAL_DEMOTE_CTX_BACKLOG_2026_09_06 — demote Active→Backlog when
    # context already deferred the key (do not promote into Remaining).
    new_work, demoted = auto.demote_active_present_in_context_backlog(new_work, new_context)
    if demoted:
        actions.append(f"demoted {demoted} Active→Backlog (context backlog SoT)")
    new_work, active_clones = auto.strip_backlog_active_clones(new_work)
    if active_clones:
        actions.append(f"stripped {active_clones} backlog active-clone(s)")

    new_work, open_done_w = auto.strip_open_done_dupes(new_work)
    new_context, open_done_c = auto.strip_open_done_dupes(new_context)
    open_done_total = open_done_w + open_done_c
    if open_done_total:
        actions.append(f"stripped {open_done_total} open-done dup(s)")

    new_work, flaw_w = auto.strip_flaw_research_drift_meta(new_work)
    new_context, flaw_c = auto.strip_flaw_research_drift_meta(new_context)
    flaw_total = flaw_w + flaw_c
    if flaw_total:
        actions.append(f"stripped {flaw_total} flaw-drift meta line(s)")

    wake_ok = False
    try:
        import peer_loop as pl

        wake_ok = float(pl.effective_continuous_wake_sec(open_queue_count=4)) > 5.0
    except Exception:
        wake_ok = False
    if wake_ok:
        new_work, wake_w = auto.resolve_satisfied_wake_interval(new_work, wake_ok=True)
        new_context, wake_c = auto.resolve_satisfied_wake_interval(new_context, wake_ok=True)
        wake_total = wake_w + wake_c
        if wake_total:
            actions.append(f"resolved {wake_total} satisfied wake-interval line(s)")

    pre_warnings = _sync_drift_lists(new_context, new_work)

    # OVERSEER_HEAL_CTX_OPEN_UNION_2026_09_07 — match sync_queue_drift /
    # context_queue_open_items (Remaining∪Active). Remaining-only missed
    # Active-only Top10 fuel (Newdrop after #N) → dual-brain warns with empty
    # heal actions when Remaining already had other opens.
    ctx_items = auto.context_queue_open_items(new_context)
    wq_items = auto._parse_phased_work_items(new_work)  # noqa: SLF001 — Remaining≡Active
    ctx_keys = {auto._normalize_queue_key(i): i for i in ctx_items}
    wq_keys = {auto._normalize_queue_key(i): i for i in wq_items}
    remaining_drift = set(ctx_keys) != set(wq_keys)

    if pre_warnings or remaining_drift:
        # OVERSEER_MAC_CLEAN_QUEUE_TWIN_2026_09_07 — Top10 context-only → WQ Active
        # (never delete Mac Top10 when CLEAN Active empty / missing the key).
        for key, raw in list(ctx_keys.items()):
            if key in wq_keys:
                continue
            if _is_top10_queue_item(raw):
                new_work = _insert_work_queue_item(new_work, raw)
                actions.append(
                    f"restored Top10 to WORK_QUEUE from context (Mac↔CLEAN): {raw[:60]}"
                )
                wq_keys[key] = raw
                continue
            new_context, did = _remove_context_open_item(new_context, raw)
            if did:
                actions.append(f"removed from context: {raw[:60]}")
        for key, raw in wq_keys.items():
            if key not in ctx_keys:
                new_context = _insert_context_item(new_context, raw)
                actions.append(f"synced to context: {raw[:60]}")
                ctx_keys[key] = raw

    # OVERSEER_INSERT_CTX_REMAINING_ONLY_2026_09_07 — union Active∪Remaining can
    # skip insert when Active already mirrors WQ; still populate Remaining.
    rem_keys = {
        auto._normalize_queue_key(i) for i in auto.remaining_work_items(new_context)
    }
    for key, raw in list(wq_keys.items()):
        if key in rem_keys:
            continue
        before = new_context
        new_context = _insert_context_item(new_context, raw)
        if new_context != before:
            actions.append(f"synced to context: {raw[:60]}")
            rem_keys.add(key)

    # OVERSEER_SIC_ACTIVE_MIRROR_HEAL_2026_09_08 — Remaining already matched but
    # SIC ## Active lacked the open → mirror Active file twin explicitly.
    for key, raw in list(wq_keys.items()):
        before = new_context
        new_context, did = _ensure_context_active_open(new_context, raw)
        if did and new_context != before:
            actions.append(f"mirrored Active open to context: {raw[:60]}")

    reconciled_context, reconciled = _reconcile_context_from_work_queue(new_context, new_work)
    if reconciled:
        new_context = reconciled_context
        actions.extend(reconciled)

    # Prefer Remaining-vs-WQ for heal return (matches self-check ISSUES).
    warnings = auto.sync_queue_drift(new_context, new_work)

    # OVERSEER_CLOSE_STALE_SYNC_META_2026_09_08 — after Top10 restore / twin
    # reconcile, empty-Active warning clears but Sync meta stays open on both
    # twins → forever noop queue_fp. Close Sync when that warning is gone.
    if not any("CLEAN empty-Active while context has Top10" in w for w in warnings):
        new_work, sync_w = auto.close_stale_sync_queue_meta(new_work)
        new_context, sync_c = auto.close_stale_sync_queue_meta(new_context)
        sync_total = sync_w + sync_c
        if sync_total:
            actions.append(f"closed {sync_total} stale Sync↔context meta line(s)")
            warnings = auto.sync_queue_drift(new_context, new_work)

    if write and (actions or new_work != work_md or new_context != context_md):
        wq_path.parent.mkdir(parents=True, exist_ok=True)
        ctx_path.parent.mkdir(parents=True, exist_ok=True)
        wq_path.write_text(new_work)
        ctx_path.write_text(new_context)
    return actions, warnings



def run_heal_fresh(
    *,
    write: bool = False,
    target: Path | None = None,
    quick: bool = False,
    force: bool = False,
    timeout: float = 600.0,
) -> HealReport:
    """Heal via a fresh interpreter so long-lived daemons cannot re-poison null fp.

    peer/improve import ``automation_adapt`` once; in-process ``run_heal`` keeps a
    pre-refuse-null ``save_adapt_state`` until restart. Subprocess always loads disk.
    """
    root = (target or ROOT).resolve()
    script = Path(__file__).resolve()
    cmd = [sys.executable, str(script), "--heal", "--target", str(root)]
    if write:
        cmd.append("--write")
    if quick:
        cmd.append("--quick")
    if force:
        cmd.append("--force")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        signals = detect_signals(root, quick=True)
        return HealReport(
            actions=[],
            issues_remaining=[f"subprocess heal failed: {exc}"],
            signals=signals,
            audit=None,
        )
    actions = [
        ln.strip()[1:].strip()
        for ln in (proc.stdout or "").splitlines()
        if ln.strip().startswith("✓")
    ]
    if not actions:
        actions = [f"subprocess heal rc={proc.returncode}"]
    issues = [
        ln.strip()[1:].strip()
        for ln in (proc.stdout or "").splitlines()
        if ln.strip().startswith("✗")
    ]
    if proc.returncode != 0 and not issues:
        tail = ((proc.stderr or proc.stdout or "")[-400:]).strip()
        issues.append(f"subprocess heal rc={proc.returncode}" + (f": {tail}" if tail else ""))
    signals = detect_signals(root, quick=True)
    return HealReport(actions=actions, issues_remaining=issues, signals=signals, audit=None)

def run_heal(*, write: bool = False, target: Path | None = None, quick: bool = False, force: bool = False) -> HealReport:
    root = (target or ROOT).resolve()
    actions: list[str] = []

    if not force and not quick and not should_re_adapt(root):
        prev = load_adapt_state(root)
        actions.append(f"skip re-probe — git unchanged since {prev.get('_generated_at', 'last adapt')[:19]}")
        quick = True

    signals = detect_signals(root, quick=quick)

    if not signals.has_kit:
        actions.extend(install_kit(root, force_scripts=False, profile=signals.profile))
        actions.extend(_bootstrap_scaffold(root, write=write))
        signals = detect_signals(root, quick=quick)

    missing_core = [p for p in signals.missing_kit_paths if p.startswith("scripts/")]
    if missing_core:
        actions.extend(install_kit(root, force_scripts=True))
        signals = detect_signals(root, quick=quick)

    cfg_result = apply_config(signals, write=write)
    if cfg_result["patches"]:
        actions.append(f"config patches: {json.dumps(cfg_result['patches'])}")

    overlay = generate_local_profile(root, signals)
    local_result = apply_local_profile(root, overlay, write=write)
    if local_result["verify_count"]:
        actions.append(
            f"local profile: {local_result['verify_count']} verify command(s)"
            + (" written" if write else " (dry-run)")
        )

    actions.extend(heal_verify_commands(root, signals, quick=quick, write=write))

    drift_actions, drift_warnings = heal_queue_drift(root=root, write=write)
    actions.extend(drift_actions)

    if write:
        final_verify = list(signals.verify_commands)
        local_path = root / "profiles" / "local.json"
        if local_path.is_file():
            try:
                final_verify = json.loads(local_path.read_text()).get("verify_commands") or final_verify
            except (json.JSONDecodeError, OSError):
                pass
        fp = signals.adapt_fingerprint if signals.adapt_fingerprint is not None else _git_fingerprint(root)
        if fp is None:
            fp = load_adapt_state(root).get("git_fingerprint")
        state_payload: dict[str, Any] = {
            "_generated_at": datetime.now(timezone.utc).isoformat(),
            "verify_commands": final_verify,
            "profile": signals.profile,
            "stack": signals.stack,
        }
        if fp is not None:
            state_payload["git_fingerprint"] = fp
        save_adapt_state(root, state_payload)

    issues: list[str] = []
    if drift_warnings and not drift_actions:
        issues.extend(drift_warnings)

    audit = run_audit(root, signals=signals, quick=quick)
    for err in audit.errors():
        issues.append(f"[{err.category}] {err.message}")
    if not audit.meta_ok:
        issues.append("audit meta-check failed (incomplete self-audit)")

    audit_path = adapt_state_path(root).parent / "adapt-audit.json"
    if write:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit_report_to_dict(audit), indent=2) + "\n")

    return HealReport(actions=actions, issues_remaining=issues, signals=signals, audit=audit)


def _finding(level: str, category: str, message: str) -> AuditFinding:
    return AuditFinding(level=level, category=category, message=message)


def _load_json_path(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing: {path.name}"
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "root must be object"
    return data, None


def _merged_tasks_at(root: Path) -> dict[str, Any]:
    """Merge peer_tasks + profile + local the same way load_tasks_config does.

    verify_commands replace (not append) so lean local.json wins over discover.
    """
    cfg: dict[str, Any] = {"peers": {}, "task_templates": {}, "verify_commands": [], "match_rules": []}
    tasks = root / "scripts" / "peer_tasks.json"
    if tasks.is_file():
        cfg = auto._deep_merge(cfg, json.loads(tasks.read_text()))
    config_path = root / "automation.config.json"
    profile = None
    if config_path.is_file():
        try:
            profile = json.loads(config_path.read_text()).get("task_profile")
        except (json.JSONDecodeError, OSError):
            pass
    # Prefer local config overlay for task_profile when present.
    local_cfg = root / "automation.config.local.json"
    if local_cfg.is_file():
        try:
            profile = json.loads(local_cfg.read_text()).get("task_profile", profile)
        except (json.JSONDecodeError, OSError):
            pass
    if profile and profile != "generic":
        for name in (f"{profile}.json", f"{profile}.tasks.json"):
            p = root / "profiles" / name
            if p.is_file():
                overlay = json.loads(p.read_text())
                cfg = auto._deep_merge(cfg, overlay)
                if isinstance(overlay, dict) and "verify_commands" in overlay:
                    cfg["verify_commands"] = list(overlay.get("verify_commands") or [])
    local = root / "profiles" / "local.json"
    if local.is_file():
        overlay = json.loads(local.read_text())
        cfg = auto._deep_merge(cfg, overlay)
        if isinstance(overlay, dict) and "verify_commands" in overlay:
            cfg["verify_commands"] = list(overlay.get("verify_commands") or [])
    if profile == "automation":
        cfg["verify_commands"] = _lean_automation_verify_commands(
            cfg.get("verify_commands"), stack="automation"
        )
    return cfg


def _audit_script_self(hub: Path, findings: list[AuditFinding], checks: list[str]) -> None:
    checks.append("script")
    adapt_path = hub / "scripts" / "automation_adapt.py"
    if not adapt_path.is_file():
        findings.append(_finding("error", "script", "automation_adapt.py missing"))
        return
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(adapt_path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        findings.append(_finding("error", "script", f"py_compile failed: {(proc.stderr or proc.stdout or '').strip()}"))
    else:
        findings.append(_finding("pass", "script", "automation_adapt.py compiles"))

    for func in SCRIPT_REQUIRED_FUNCS:
        if func not in globals():
            findings.append(_finding("error", "script", f"missing function: {func}"))
    for rel in KIT_MARKERS:
        if not (hub / rel).is_file():
            findings.append(_finding("warn", "script", f"kit marker missing: {rel}"))


def _audit_config(root: Path, signals: ProjectSignals, findings: list[AuditFinding], outputs: dict[str, Any]) -> None:
    path = root / "automation.config.json"
    data, err = _load_json_path(path)
    outputs["automation.config.json"] = {"path": str(path), "exists": data is not None, "error": err}
    if data is None:
        findings.append(_finding("error" if signals.has_kit else "warn", "config", err or "no config"))
        return
    for key in REQUIRED_CONFIG_KEYS:
        if not data.get(key):
            findings.append(_finding("error", "config", f"missing key: {key}"))
    if data.get("task_profile") != signals.profile:
        findings.append(_finding("warn", "config", f"task_profile={data.get('task_profile')!r} expected {signals.profile!r}"))
    if signals.test_command and data.get("test_command") != signals.test_command:
        findings.append(_finding("warn", "config", "test_command differs from probed signals"))
    if not any(f.category == "config" and f.level == "error" for f in findings):
        findings.append(_finding("pass", "config", "automation.config.json valid"))


def _audit_local_profile(root: Path, findings: list[AuditFinding], outputs: dict[str, Any]) -> list[str]:
    path = root / "profiles" / "local.json"
    data, err = _load_json_path(path)
    outputs["profiles/local.json"] = {"path": str(path), "exists": data is not None, "error": err}
    verify_cmds: list[str] = []
    if data is None:
        findings.append(_finding("warn", "local_profile", "no local.json overlay yet"))
        return verify_cmds

    verify_cmds = [c for c in (data.get("verify_commands") or []) if isinstance(c, str) and c.strip()]
    if not verify_cmds:
        findings.append(_finding("error", "local_profile", "verify_commands empty"))
    else:
        findings.append(_finding("pass", "local_profile", f"{len(verify_cmds)} verify command(s)"))

    templates = data.get("task_templates") or {}
    seen_templates: set[str] = set()
    for rule in data.get("match_rules") or []:
        if not isinstance(rule, dict):
            findings.append(_finding("error", "local_profile", "match_rules entry not object"))
            continue
        tmpl = str(rule.get("template", ""))
        if tmpl in seen_templates:
            findings.append(_finding("warn", "local_profile", f"duplicate match_rule template: {tmpl}"))
        seen_templates.add(tmpl)
        if tmpl and tmpl not in templates:
            findings.append(_finding("warn", "local_profile", f"match_rule {tmpl} has no local template (may be in base)"))

    for mod, rel_path in (data.get("module_scope") or {}).items():
        if not (root / str(rel_path)).exists():
            findings.append(_finding("warn", "local_profile", f"module_scope path missing: {mod} → {rel_path}"))

    if not data.get("_generated_at"):
        findings.append(_finding("warn", "local_profile", "missing _generated_at metadata"))
    return verify_cmds


def _audit_adapt_state(root: Path, signals: ProjectSignals, local_verify: list[str], findings: list[AuditFinding], outputs: dict[str, Any]) -> None:
    path = adapt_state_path(root)
    data, err = _load_json_path(path)
    outputs["adapt-state.json"] = {"path": str(path), "exists": data is not None, "error": err}
    if data is None:
        findings.append(_finding("info", "adapt_state", "no adapt-state yet (first run)"))
        return
    # Live fp even when detect_signals(quick=True) left adapt_fingerprint=None —
    # otherwise null stored fp reports "consistent" and verify gate never blocks.
    fp = signals.adapt_fingerprint or _git_fingerprint(root)
    stored = data.get("git_fingerprint")
    if not stored or (fp and stored != fp):
        findings.append(_finding("warn", "adapt_state", "git fingerprint stale — re-run adapt --heal"))
    # OVERSEER_SYNC_VERIFY_CMDS_2026_09_04 — compare lean-normalized lists so
    # scrambled/extra local.json cannot false-ADAPT_STALE after sync heal.
    lean_local = _lean_automation_verify_commands(local_verify, stack=signals.stack)
    state_verify = _lean_automation_verify_commands(
        data.get("verify_commands") or [], stack=signals.stack
    )
    if lean_local and state_verify != lean_local:
        findings.append(_finding("warn", "adapt_state", "verify_commands drift vs local.json"))
    elif not any(f.category == "adapt_state" and f.level == "warn" for f in findings):
        findings.append(_finding("pass", "adapt_state", "adapt-state consistent"))


def _audit_verify_commands(
    root: Path,
    commands: list[str],
    *,
    quick: bool,
    findings: list[AuditFinding],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    commands = [c for c in commands if not _is_recursive_adapt_command(c)]
    if not commands:
        findings.append(_finding("error", "verify", "no verify commands to audit"))
        return results

    if quick:
        for cmd in commands:
            entry: dict[str, Any] = {
                "command": cmd,
                "ok": True,
                "exit_code": None,
                "detail": "trusted from local profile (quick audit)",
            }
            findings.append(_finding("info", "verify", f"SKIP quick: {cmd[:70]}"))
            results.append(entry)
        findings.append(_finding("pass", "verify", f"{len(commands)} command(s) listed (quick — run full audit to execute)"))
        return results

    # Nested full audits must not re-enter (verify lists once included adapt --audit).
    if os.environ.get("AUTOMATION_ADAPT_AUDIT_ACTIVE") == "1":
        findings.append(_finding("warn", "verify", "skip nested adapt audit verify execution"))
        return results

    timeout = QUICK_PROBE_TIMEOUT if quick else PROBE_TIMEOUT
    env = os.environ.copy()
    env["AUTOMATION_ADAPT_AUDIT_ACTIVE"] = "1"
    for cmd in commands:
        entry: dict[str, Any] = {"command": cmd, "ok": False, "exit_code": None, "detail": ""}
        cmd_timeout = SELF_CHECK_AUDIT_TIMEOUT if "self-check" in cmd else timeout
        try:
            proc = _run(cmd, cwd=root, timeout=cmd_timeout, env=env)
            entry["exit_code"] = proc.returncode
            # OVERSEER_AUDIT_RC_2026_09_03 — hub-protect needle: usable≠PASS; ok=rc==0
            # OVERSEER_AUDIT_OK_NE_USABLE_2026_09_04 — never assign ok from usable
            usable = _command_usable(proc, cmd, root=root)
            passed = proc.returncode == 0
            entry["usable"] = usable
            ok = proc.returncode == 0
            entry["ok"] = ok  # Needle: OVERSEER_AUDIT_OK_NE_USABLE_2026_09_04
            tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
            entry["detail"] = tail[-1][:120] if tail else ""
            if passed:
                findings.append(_finding("pass", "verify", f"OK: {cmd[:70]}"))
            elif int(proc.returncode or 0) < 0:
                # OVERSEER_AUDIT_SIGKILL_SKIP_2026_09_04 — storm trim theater
                entry["ok"] = True
                entry["detail"] = entry["detail"] or f"signal kill rc={proc.returncode}"
                findings.append(
                    _finding(
                        "warn",
                        "verify",
                        f"SKIP signal: {cmd[:70]} — rc={proc.returncode} (storm trim)",
                    )
                )
            elif usable:
                findings.append(
                    _finding("warn", "verify", f"RAN fail: {cmd[:70]} — {entry['detail']}")
                )
            else:
                findings.append(_finding("error", "verify", f"FAIL: {cmd[:70]} — {entry['detail']}"))
        except (subprocess.TimeoutExpired, OSError) as exc:
            entry["detail"] = str(exc)
            findings.append(_finding("error", "verify", f"TIMEOUT: {cmd[:70]}"))
        results.append(entry)

    passed = sum(1 for r in results if r["ok"])
    if passed == 0:
        findings.append(_finding("error", "verify", "zero verify commands passed"))
    elif passed < len(results):
        findings.append(_finding("warn", "verify", f"{passed}/{len(results)} verify commands passed"))
    return results


def _audit_queue(root: Path, findings: list[AuditFinding]) -> None:
    ctx_path, wq_path = _queue_paths(root)
    context_md = ctx_path.read_text() if ctx_path.is_file() else ""
    work_md = wq_path.read_text() if wq_path.is_file() else ""
    drift = _sync_drift_lists(context_md, work_md)
    if drift:
        for d in drift:
            findings.append(_finding("error", "queue", d))
    else:
        findings.append(_finding("pass", "queue", "WORK_QUEUE ↔ context in sync"))


def _audit_tasks(root: Path, findings: list[AuditFinding]) -> None:
    try:
        cfg = _merged_tasks_at(root)
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(_finding("error", "tasks", f"cannot merge tasks config: {exc}"))
        return
    issues = auto.validate_tasks_config(cfg)
    for issue in issues:
        findings.append(_finding("error", "tasks", issue))
    if not issues:
        findings.append(_finding("pass", "tasks", f"{len(cfg.get('task_templates') or {})} templates, {len(cfg.get('verify_commands') or [])} verify cmds"))


def _audit_signals_consistency(signals: ProjectSignals, findings: list[AuditFinding]) -> None:
    if signals.has_kit and not signals.kit_complete:
        findings.append(_finding("error", "signals", f"incomplete kit: {signals.missing_kit_paths}"))
    if not signals.verify_commands:
        findings.append(_finding("error", "signals", "no working verify commands detected"))
    if signals.profile not in KNOWN_PROFILES:
        findings.append(_finding("warn", "signals", f"unknown profile: {signals.profile}"))
    if not any(f.category == "signals" and f.level == "error" for f in findings):
        findings.append(_finding("pass", "signals", f"stack={signals.stack} profile={signals.profile}"))


def _audit_meta(checks_run: list[str], findings: list[AuditFinding], report: AuditReport) -> bool:
    required = [c for c in AUDIT_CATEGORIES if c != "script" or "script" in checks_run]
    missing_cats = [c for c in required if c not in checks_run]
    for cat in missing_cats:
        findings.append(_finding("error", "meta", f"audit did not run category: {cat}"))
    if report.verify_results and not any(r.get("ok") for r in report.verify_results):
        findings.append(_finding("error", "meta", "audit output: all verify results failed"))
    if not report.output_files:
        findings.append(_finding("error", "meta", "audit output: no output_files recorded"))
    return not missing_cats and not any(f.level == "error" and f.category == "meta" for f in findings)


def format_audit_report(report: AuditReport) -> str:
    lines = [
        "=== automation adapt audit ===",
        f"root: {report.root}",
        f"ok: {report.ok}",
        f"meta_ok: {report.meta_ok}",
        "",
    ]
    for level in ("error", "warn", "info", "pass"):
        items = [f for f in report.findings if f.level == level]
        if not items:
            continue
        lines.append(f"{level.upper()}S:")
        for f in items:
            lines.append(f"  [{f.category}] {f.message}")
        lines.append("")
    if report.verify_results:
        lines.append("VERIFY OUTPUT:")
        for r in report.verify_results:
            mark = "✓" if r.get("ok") else "✗"
            lines.append(f"  {mark} ({r.get('exit_code')}) {r.get('command', '')[:80]}")
            if r.get("detail"):
                lines.append(f"      {r['detail']}")
        lines.append("")
    lines.append("OUTPUT FILES:")
    lines.append(json.dumps(report.output_files, indent=2))
    return "\n".join(lines)


def audit_report_to_dict(report: AuditReport) -> dict[str, Any]:
    return {
        "root": report.root,
        "ok": report.ok,
        "meta_ok": report.meta_ok,
        "checks_run": report.checks_run,
        "findings": [asdict(f) for f in report.findings],
        "verify_results": report.verify_results,
        "output_files": report.output_files,
        "error_count": len(report.errors()),
        "warn_count": len(report.warnings()),
    }


def run_audit(
    root: Path | None = None,
    *,
    signals: ProjectSignals | None = None,
    quick: bool = False,
    audit_self: bool = True,
) -> AuditReport:
    root = (root or ROOT).resolve()
    hub = kit_root()
    signals = signals or detect_signals(root, quick=quick)
    findings: list[AuditFinding] = []
    checks_run: list[str] = []
    outputs: dict[str, Any] = {}

    if audit_self:
        _audit_script_self(hub, findings, checks_run)

    checks_run.append("config")
    _audit_config(root, signals, findings, outputs)

    checks_run.append("local_profile")
    local_verify = _audit_local_profile(root, findings, outputs)

    checks_run.append("adapt_state")
    _audit_adapt_state(root, signals, local_verify, findings, outputs)

    verify_cmds = local_verify or signals.verify_commands or _stack_verify_candidates(root, signals.stack, signals.package_manager)
    checks_run.append("verify")
    verify_results = _audit_verify_commands(root, verify_cmds, quick=quick, findings=findings)

    checks_run.append("queue")
    _audit_queue(root, findings)

    checks_run.append("tasks")
    _audit_tasks(root, findings)

    checks_run.append("signals")
    _audit_signals_consistency(signals, findings)

    ok = not any(f.level == "error" for f in findings)
    report = AuditReport(
        root=str(root),
        ok=ok,
        findings=findings,
        checks_run=checks_run,
        verify_results=verify_results,
        output_files=outputs,
        meta_ok=False,
    )
    report.meta_ok = _audit_meta(checks_run, findings, report)
    if not report.meta_ok:
        report.ok = False
    return report


# Model weight suffixes — local train/niche artifacts under notes/ must not ship
# via portable kit tarball or --install into foreign trees
# (OVERSEER_MODEL_LOCAL_ONLY_2026_09_06 · OVERSEER_KIT_EXPORT_NO_WEIGHTS_2026_09_07 ·
#  OVERSEER_KIT_INSTALL_NO_WEIGHTS_2026_09_07).
_KIT_EXPORT_WEIGHT_SUFFIXES = (
    ".pt",
    ".pth",
    ".safetensors",
    ".gguf",
    ".ckpt",
    ".onnx",
)

# Machine-local secret / overlay basenames — shared by --export filter and --install.
# Needle: OVERSEER_KIT_EXPORT_NO_LOCAL_SECRETS_2026_09_05 ·
#         OVERSEER_KIT_INSTALL_NO_LOCAL_SECRETS_2026_09_08
_KIT_LOCAL_SECRET_EXACT = frozenset({"cursor-agent.env", "credentials.json", ".env"})


def _kit_basename_is_weight(name: str) -> bool:
    """True when basename is a local-only model weight / checkpoint file."""
    lower = Path(name).name.lower()
    return any(lower.endswith(suf) for suf in _KIT_EXPORT_WEIGHT_SUFFIXES)


def _kit_basename_is_local_secret(name: str) -> bool:
    """True when basename is a machine-local secret or host overlay (not portable)."""
    base = Path(name).name
    if base.startswith(".env") or base.endswith(".local.json"):
        return True
    return base in _KIT_LOCAL_SECRET_EXACT


def _kit_export_tarinfo_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Drop secrets / machine-local overlays from portable kit tarballs.

    ``KIT_COPY_PATHS`` includes whole ``scripts/`` / ``notes/`` trees; without a
    filter, ``*.local.json`` and dotenv files under those dirs would ship.
    Also drops local model weight files (``*.pt`` / safetensors / GGUF / …) so
    compression + niche checkpoints never leave the host via ``--export``.
    Needle: OVERSEER_KIT_EXPORT_NO_LOCAL_SECRETS_2026_09_05 ·
    OVERSEER_MODEL_LOCAL_ONLY_2026_09_06 · OVERSEER_KIT_EXPORT_NO_WEIGHTS_2026_09_07 ·
    OVERSEER_KIT_INSTALL_NO_LOCAL_SECRETS_2026_09_08
    """
    name = Path(tarinfo.name).name
    if _kit_basename_is_local_secret(name):
        return None
    if _kit_basename_is_weight(name):
        return None
    return tarinfo


def export_tarball(out_dir: Path | None = None) -> Path:
    hub = kit_root()
    out_dir = out_dir or (hub / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / f"automation-kit-{stamp}.tar.gz"
    with tarfile.open(out_path, "w:gz") as tar:
        for rel in KIT_COPY_PATHS:
            src = hub / rel
            if src.exists():
                tar.add(
                    src,
                    arcname=f"automation-kit/{rel}",
                    filter=_kit_export_tarinfo_filter,
                )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt peer automation to any project")
    parser.add_argument("--probe", action="store_true", help="Print detected project signals as JSON")
    parser.add_argument("--apply", action="store_true", help="Apply config patches from detection")
    parser.add_argument("--heal", action="store_true", help="Full adapt/heal cycle")
    parser.add_argument("--install", metavar="PATH", help="Install kit into target repo then adapt")
    parser.add_argument("--export", action="store_true", help="Write dist/automation-kit-YYYY-MM-DD.tar.gz")
    parser.add_argument("--write", action="store_true", help="Persist changes")
    parser.add_argument("--quick", action="store_true", help="Skip slow test probes; reuse adapt-state")
    parser.add_argument("--force", action="store_true", help="Re-probe even when git fingerprint unchanged")
    parser.add_argument("--force-scripts", action="store_true", help="Overwrite existing scripts on install")
    parser.add_argument("--profile", help="Override task_profile")
    parser.add_argument("--all", action="store_true", help="Adapt all repos in registry.json")
    parser.add_argument("--all-profile", help="With --all, only repos with this profile")
    parser.add_argument("--audit", action="store_true", help="Self-audit script + outputs (no heal)")
    parser.add_argument("--audit-json", action="store_true", help="Emit audit report as JSON")
    parser.add_argument("--target", help="Repo root (default: automation root)")
    args = parser.parse_args()

    if args.all:
        reports = adapt_registry_repos(
            write=args.write or args.heal,
            quick=args.quick,
            force=args.force,
            only_profile=args.all_profile,
        )
        if not reports:
            print("No registry repos found on disk.", file=sys.stderr)
            return 1
        exit_code = 0
        for report in reports:
            print(f"\n=== {report.signals.root} ({report.signals.profile}) ===")
            for a in report.actions:
                print(f"  ✓ {a}")
            for i in report.issues_remaining:
                print(f"  ✗ {i}")
                exit_code = 1
        return exit_code

    target = Path(args.target).resolve() if args.target else ROOT

    if args.export:
        print(export_tarball())
        return 0

    if args.install:
        dest = Path(args.install).resolve()
        if not dest.is_dir():
            print(f"not a directory: {dest}", file=sys.stderr)
            return 1
        seen: set[str] = set()
        for a in install_kit(dest, force_scripts=args.force_scripts, profile=args.profile):
            if a not in seen:
                print(a)
                seen.add(a)
        report = run_heal(write=True, target=dest, quick=False, force=True)
        for a in report.actions:
            if a not in seen:
                print(a)
        if report.issues_remaining:
            for i in report.issues_remaining:
                print(f"  ✗ {i}", file=sys.stderr)
            return 1
        print("\nAdapt complete.")
        return 0

    if args.probe:
        sig = detect_signals(target, quick=args.quick)
        if args.profile:
            sig.profile = args.profile
        print(json.dumps(asdict(sig), indent=2))
        return 0

    if args.apply:
        sig = detect_signals(target, quick=args.quick)
        if args.profile:
            sig.profile = args.profile
        print(json.dumps(apply_config(sig, write=args.write), indent=2))
        if args.write:
            apply_local_profile(target, generate_local_profile(target, sig), write=True)
        return 0

    if args.heal:
        report = run_heal(write=args.write, target=target, quick=args.quick, force=args.force)
        print("=== automation adapt/heal ===")
        for a in report.actions:
            print(f"  ✓ {a}")
        for i in report.issues_remaining:
            print(f"  ✗ {i}")
        if report.audit:
            print()
            print(format_audit_report(report.audit))
        if not args.write and report.actions:
            print("\n(dry-run — pass --write to persist)", file=sys.stderr)
        return 1 if report.issues_remaining else 0

    if args.audit or args.audit_json:
        audit = run_audit(target, quick=args.quick)
        if args.audit_json:
            print(json.dumps(audit_report_to_dict(audit), indent=2))
        else:
            print(format_audit_report(audit))
        return 0 if audit.ok and audit.meta_ok else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
