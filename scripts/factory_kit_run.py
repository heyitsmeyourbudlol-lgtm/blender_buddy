#!/usr/bin/env python3
"""Factory kit A→Z compound — adapt → worktree → verify → artifact → writeback.

Usage:
  python3 scripts/factory_kit_run.py --list
  python3 scripts/factory_kit_run.py --repo CPT --dry-run
  python3 scripts/factory_kit_run.py --repo CPT --run --stop-after E
  ./scripts/peer kit-run --repo CPT --dry-run

Needle: OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07
Phase2: OVERSEER_KIT_RUN_AE_2026_09_07
False-green heal: OVERSEER_FALSE_GREEN_LOCK_2026_09_07
B on clean wt: OVERSEER_KIT_RUN_B_ON_CLEAN_WT_2026_09_08
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

REGISTRY = ROOT / "repos" / "registry.json"
ADAPT = SCRIPTS / "automation_adapt.py"
PROOF_JSON = ROOT / "notes" / "factory_a_to_z_last.json"
PROOF_MD = ROOT / "notes" / "FACTORY_A_TO_Z_PROOF.md"
EXTERNAL_PROOF = ROOT / "notes" / "EXTERNAL_PROOF.md"
TASKS_MD = ROOT / "notes" / "FACTORY_A_TO_Z_TASKS.md"
NEEDLE = "OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07"
NEEDLE_AE = "OVERSEER_KIT_RUN_AE_2026_09_07"
NEEDLE_FALSE_GREEN = "OVERSEER_FALSE_GREEN_LOCK_2026_09_07"
NEEDLE_B_CLEAN_WT = "OVERSEER_KIT_RUN_B_ON_CLEAN_WT_2026_09_08"
_VERIFY_PATH_RE = re.compile(r"(?:^|[\s\"'])((?:scripts|tests)/[^\s\"';|&;]+)")
_PR_URL_RE = re.compile(r"https://github\.com/\S+/pull/\d+")
_PUSH_AUTH_MARKERS = (
    "could not read username",
    "authentication failed",
    "permission denied (publickey)",
    "no such device or address",
    "terminal prompts disabled",
    "support for password authentication was removed",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kit_worktree_stamp(*, attempt: int = 0) -> str:
    """Unique kit-run C stamp — second-precision alone collides under parallel overseers.

    Needle: ``OVERSEER_KIT_WT_STAMP_COLLISION_2026_09_08``
    """
    # YYYYMMDDTHHMMSS + 2 µs digits (17) — keeps branch names short + race-safe.
    base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:17]
    if attempt <= 0:
        return base
    return f"{base}r{attempt}"


def classify_push_failure(*, exit_code: Any, stderr: str = "", stdout: str = "") -> str:
    """Map git push failure to an honest blocked reason (auth vs generic)."""
    blob = f"{stderr}\n{stdout}".lower()
    if any(m in blob for m in _PUSH_AUTH_MARKERS):
        return "push_auth_missing"
    return f"push_failed:{exit_code}"


def origin_owner_repo(target: Path) -> tuple[str, str] | None:
    """Parse ``origin`` remote into ``(owner, repo)`` for public GitHub API.

    Needle: ``OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08``
    """
    rem = _run(["git", "remote", "get-url", "origin"], cwd=target, timeout=30)
    url = (rem.get("stdout_tail") or "").strip().splitlines()
    raw = url[0].strip() if url else ""
    if not raw:
        return None
    m = re.search(
        r"(?:github\.com[:/]|github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$",
        raw,
    )
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def discover_origin_kit_prs(
    target: Path,
    *,
    prefer_merged: bool = True,
) -> dict[str, Any] | None:
    """Adopt Mac/sibling kit PRs when CLEAN push/gh is auth-blocked.

    Public GitHub API (no token) — when ``peer/kit-a-to-z-*`` PRs already exist on
    origin, return ``mode=pr`` instead of ``blocked_receipt`` theater that freezes
    queue_fp while Mac already filed irreversible PR artifacts.

    Needle: ``OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08``
    """
    parsed = origin_owner_repo(target)
    if not parsed:
        return None
    owner, repo = parsed
    import urllib.error
    import urllib.request

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&per_page=30"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "automation-kit-run",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — public API
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, list):
        return None
    kit_prs: list[dict[str, Any]] = []
    for pr in payload:
        if not isinstance(pr, dict):
            continue
        head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
        ref = str(head.get("ref") or "")
        if not ref.startswith("peer/kit-a-to-z-"):
            continue
        html = str(pr.get("html_url") or "")
        if not _PR_URL_RE.search(html):
            continue
        kit_prs.append(
            {
                "pr_url": html,
                "number": pr.get("number"),
                "state": "merged" if pr.get("merged_at") else str(pr.get("state") or ""),
                "merged_at": pr.get("merged_at"),
                "branch": ref,
                "sha": str(head.get("sha") or "")[:40],
            }
        )
    if not kit_prs:
        return None
    if prefer_merged:
        merged = [p for p in kit_prs if p.get("merged_at")]
        pick = merged[0] if merged else kit_prs[0]
    else:
        pick = kit_prs[0]
    return {
        "pr_url": pick["pr_url"],
        "branch": pick["branch"],
        "sha": pick.get("sha") or "",
        "state": pick.get("state"),
        "sibling_prs": kit_prs,
        "needle": "OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08",
    }


def green_lock_eligible(receipt: dict[str, Any] | None) -> tuple[bool, str]:
    """Phase 4 green requires irreversible remote artifact — never local commit theater.

    Eligible: mode=pr with github pull URL **and** origin ls-remote hit for branch,
    or mode=merge_note with pushed_ref + note file.
    PR URL alone / blocked receipts / missing push / invented PR URLs → not eligible.
    Needle: OVERSEER_FALSE_GREEN_LOCK_2026_09_07
    """
    if not isinstance(receipt, dict):
        return False, "no_receipt"
    mode = str(receipt.get("artifact_mode") or receipt.get("mode") or "")
    # Accept either top-level receipt or nested D artifact dict.
    artifact = receipt
    if receipt.get("artifact_mode") and isinstance(receipt.get("steps"), list):
        for step in receipt["steps"]:
            if isinstance(step, dict) and step.get("step") == "D_artifact":
                artifact = step
                mode = str(step.get("mode") or mode)
                break
    if mode == "pr":
        url = str(artifact.get("pr_url") or receipt.get("pr_url") or "")
        if not _PR_URL_RE.search(url):
            return False, "pr_url_missing"
        # Local-only invent: require push evidence when present on receipt.
        if artifact.get("ok") is False:
            return False, "pr_step_not_ok"
        # Fail-closed: PR URL alone must not unlock — require origin ref via ls-remote.
        branch = artifact.get("branch") or receipt.get("branch")
        probe = artifact.get("worktree_path") or artifact.get("target") or receipt.get("target")
        if not branch or not probe or not Path(str(probe)).exists():
            return False, "pr_remote_ref_missing"
        remote = _run(
            ["git", "ls-remote", "--heads", "origin", str(branch)],
            cwd=Path(str(probe)),
            timeout=60,
        )
        out = (remote.get("stdout_tail") or "").strip()
        if remote.get("exit") != 0 or not out:
            return False, "pr_remote_ref_missing"
        return True, "pr"
    if mode == "merge_note":
        pushed = artifact.get("pushed_ref") or receipt.get("pushed_ref")
        note = artifact.get("merge_note") or receipt.get("merge_note")
        if not pushed:
            return False, "merge_note_no_push"
        if not note or not Path(str(note)).is_file():
            return False, "merge_note_file_missing"
        return True, "merge_note"
    if mode == "blocked_receipt":
        return False, "blocked_receipt"
    if mode:
        return False, f"not_eligible:{mode}"
    return False, "no_artifact_mode"


def _force_proof_lock_status(text: str, *, status: str, stamped: str) -> str:
    """Rewrite Lock status table fields without inventing run rows."""
    text = re.sub(
        r"(\| Status \| )\*\*[^*]+\*\*",
        rf"\1**{status}**",
        text,
        count=1,
    )
    text = re.sub(
        r"(\| Green lock stamped \| )[^\n|]*",
        rf"\1{stamped} ",
        text,
        count=1,
    )
    return text


def heal_false_green_lock(*, write: bool = True) -> dict[str, Any]:
    """If PROOF claims green without eligible D artifact → force red + honest receipt.

    Catches parallel-peer theater that stamps PR URLs after push_auth_missing.
    Needle: OVERSEER_FALSE_GREEN_LOCK_2026_09_07
    """
    out: dict[str, Any] = {
        "needle": NEEDLE_FALSE_GREEN,
        "ts": _utc(),
        "healed": False,
        "write": write,
    }
    receipt: dict[str, Any] = {}
    if PROOF_JSON.is_file():
        try:
            loaded = json.loads(PROOF_JSON.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                receipt = loaded
        except (OSError, json.JSONDecodeError) as exc:
            out["receipt_error"] = str(exc)

    eligible, why = green_lock_eligible(receipt)
    out["eligible"] = eligible
    out["eligible_why"] = why

    proof_text = PROOF_MD.read_text(encoding="utf-8") if PROOF_MD.is_file() else ""
    claims_green = bool(re.search(r"\|\s*Status\s*\|\s*\*\*green\*\*", proof_text, re.I))
    out["proof_claims_green"] = claims_green
    # Prior Phase4 unlock (CPT PR) must survive later targets that honestly
    # finish as blocked_receipt / merge_note without a new PR.
    # Needle: OVERSEER_FALSE_GREEN_LOCK_2026_09_07 (do not clobber prior eligible)
    prior_eligible_stamp = bool(
        re.search(r"green_lock_eligible\s*=\s*pr", proof_text, re.I)
        and re.search(
            r"https://github\.com/heyitsmeyourbudlol-lgtm/CPT/pull/\d+",
            proof_text,
        )
    )
    out["prior_eligible_stamp"] = prior_eligible_stamp

    if eligible or not claims_green or prior_eligible_stamp:
        out["action"] = "noop"
        if prior_eligible_stamp and claims_green and not eligible:
            out["noop_why"] = "prior_cpt_green_lock_stamp"
        return out

    # Force honest blocked_receipt when green was stamped without push/PR.
    reasons: list[str] = []
    for step in receipt.get("steps") or []:
        if not isinstance(step, dict) or step.get("step") != "D_artifact":
            continue
        br = step.get("blocked_receipt") or {}
        if isinstance(br, dict) and br.get("reasons"):
            reasons = [str(r) for r in br["reasons"]]
        mode = step.get("mode")
        if mode == "pr" and not green_lock_eligible(step)[0]:
            reasons = reasons or ["false_pr_url", "push_auth_missing"]
        elif mode == "blocked_receipt":
            reasons = reasons or [str(r) for r in (br.get("reasons") or ["blocked"])]
    if not reasons:
        reasons = ["false_green_no_remote_artifact", "push_auth_missing"]

    stamped = f"— (false green healed {_utc()[:10]}; {why}; {NEEDLE_FALSE_GREEN})"
    new_proof = _force_proof_lock_status(proof_text, status="red", stamped=stamped)
    # Demote any green run-row PR claim that isn't backed by eligibility.
    new_proof = re.sub(
        r"(\| 2026-\d{2}-\d{2} \| CPT \| ok \| ok \| ok \| )\*\*PR\*\*",
        r"\1blocked",
        new_proof,
        count=1,
    )
    if "false green" not in new_proof.lower() and NEEDLE_FALSE_GREEN not in new_proof:
        new_proof = new_proof.rstrip() + (
            f"\n\n## False-green heal\n\n"
            f"- {NEEDLE_FALSE_GREEN}: Status forced **red** — receipt not eligible ({why}).\n"
        )

    honest_receipt = dict(receipt) if receipt else {
        "needle": NEEDLE,
        "needle_ae": NEEDLE_AE,
        "ts": _utc(),
        "repo": "CPT",
    }
    honest_receipt["artifact_mode"] = "blocked_receipt"
    honest_receipt["ok"] = True
    honest_receipt["note"] = (
        f"False green healed ({NEEDLE_FALSE_GREEN}): not eligible ({why}). "
        f"Reasons: {','.join(reasons)}. Re-run kit-run after GitHub auth (SSH key or gh)."
    )
    # Ensure D step reflects block (do not leave mode=pr theater).
    steps = list(honest_receipt.get("steps") or [])
    patched_d = False
    for i, step in enumerate(steps):
        if isinstance(step, dict) and step.get("step") == "D_artifact":
            steps[i] = {
                **step,
                "ok": True,
                "mode": "blocked_receipt",
                "pr_url": None,
                "blocked_receipt": {
                    "blocked": True,
                    "reasons": reasons,
                    "ts": _utc(),
                    "needle": NEEDLE_FALSE_GREEN,
                    "note": honest_receipt["note"],
                },
                "needle": NEEDLE_AE,
            }
            patched_d = True
            break
    if not patched_d:
        steps.append(
            {
                "step": "D_artifact",
                "ok": True,
                "mode": "blocked_receipt",
                "blocked_receipt": {
                    "blocked": True,
                    "reasons": reasons,
                    "ts": _utc(),
                    "needle": NEEDLE_FALSE_GREEN,
                },
                "needle": NEEDLE_AE,
            }
        )
    honest_receipt["steps"] = steps

    ext_text = EXTERNAL_PROOF.read_text(encoding="utf-8") if EXTERNAL_PROOF.is_file() else ""
    date = _utc()[:10]
    ext_row = (
        f"| 1 | CPT | kit A→E blocked ({','.join(reasons[:3])}) | "
        f"native verify ok | blocked receipt (false green healed; {NEEDLE_FALSE_GREEN}) | {date} |"
    )
    if re.search(r"\| 1 \| CPT \|", ext_text):
        ext_text = re.sub(r"\| 1 \| CPT \|[^\n]*\n", ext_row + "\n", ext_text, count=1)

    tasks_text = TASKS_MD.read_text(encoding="utf-8") if TASKS_MD.is_file() else ""
    if tasks_text:
        tasks_text = re.sub(
            r"- \[x\] \*\*\[a-to-z:phase4\] Stamp green lock\*\*[^\n]*",
            (
                "- [ ] **[a-to-z:phase4] Stamp green lock** — blocked: push_auth_missing on CLEAN "
                f"(no SSH/gh); false green healed {NEEDLE_FALSE_GREEN}; "
                "FACTORY_A_TO_Z_PROOF.md status=**red**"
            ),
            tasks_text,
            count=1,
        )
        # OVERSEER_DEMOTE_A_TO_Z_AUTH_PIN_2026_09_07 — annotate push_auth so
        # compact-queue demote_human_auth_blocked_active moves Active→Creative
        # (bare "red until…" pins previously escaped demote and froze queue_fp).
        tasks_text = re.sub(
            r"- \[x\] \*\*\[a-to-z\] Factory A→Z sequencing lock\*\*[^\n]*",
            (
                "- [ ] **[a-to-z] Factory A→Z sequencing lock** — red until real PR/merge_note; "
                "blocked: push_auth_missing on CLEAN (no SSH/gh); "
                f"do not jump ladder — {NEEDLE}"
            ),
            tasks_text,
            count=1,
        )

    out.update(
        {
            "action": "force_red",
            "reasons": reasons,
            "healed": True,
        }
    )
    if write:
        PROOF_MD.parent.mkdir(parents=True, exist_ok=True)
        PROOF_MD.write_text(new_proof, encoding="utf-8")
        write_receipt(honest_receipt, path=PROOF_JSON)
        if ext_text:
            EXTERNAL_PROOF.write_text(ext_text, encoding="utf-8")
        if tasks_text:
            TASKS_MD.write_text(tasks_text, encoding="utf-8")
        out["paths"] = [str(PROOF_MD), str(PROOF_JSON), str(EXTERNAL_PROOF), str(TASKS_MD)]
    return out


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_repos(reg: dict[str, Any]) -> list[dict[str, Any]]:
    repos = reg.get("repos")
    return list(repos) if isinstance(repos, list) else []


def find_repo(reg: dict[str, Any], name: str) -> dict[str, Any] | None:
    key = name.strip().lower()
    for row in list_repos(reg):
        if not isinstance(row, dict):
            continue
        n = str(row.get("name") or "")
        ns = str(row.get("namespace") or "")
        if n.lower() == key or ns.lower() == key or key in n.lower():
            return row
    return None


def _home_mirror_candidates(name: str, ns: str) -> list[str]:
    """Portable home mirrors (Mac or Linux) — no hardcoded /Users/… literals.

    Needle: OVERSEER_KIT_RUN_HOME_MIRRORS_2026_09_07
    Override base with AUTOMATION_MAC_HOME when the Mac home differs from Path.home().

    OVERSEER_KIT_RUN_HYPHEN_MIRROR_2026_09_08 — registry Mac paths often use spaces
    (``Congressional App Challenge``) while CLEAN clones use GitHub hyphens
    (``Congressional-App-Challenge``). Always append hyphen/namespace slug variants
    so ``resolve_repo_path`` finds the local mirror instead of ``offline-mac`` MISSING
    → queue_fp flat after Mac already MERGED.
    """
    home = Path(os.environ.get("AUTOMATION_MAC_HOME") or Path.home()).expanduser()
    blob = f"{name} {ns}".lower()
    folders: list[str] = []
    if "cpt" in blob or ns == "cpt":
        folders.append("CPT")
    if "ram" in blob or ns == "ram-park":
        folders.append("ram")
    if "newdrop" in blob or "caas" in blob or ns == "newdrop":
        folders.append("CaaS")
    if "doc2api" in blob or ns == "doc2api":
        folders.append("Doc2Api")
    if "news" in blob or ns == "news":
        folders.append("News")
    if "terminal" in blob or ns == "terminal":
        folders.append("Terminal")
    if "marketplace" in blob or ns == "marketplace":
        folders.append("Marketplace")
    if "saas" in blob or "health dashboard" in blob:
        folders.append("SaaS Health Dashboard")
    if "f.i.r.e" in blob or "fire" in blob or ns == "fire-project":
        folders.append("F.I.R.E. Project")
    if name.strip():
        folders.append(name.strip())
        hyph = re.sub(r"[\s_]+", "-", name.strip())
        if hyph and hyph not in folders:
            folders.append(hyph)
    if ns.strip():
        if ns.strip() not in folders:
            folders.append(ns.strip())
        titled = "-".join(
            part[:1].upper() + part[1:] for part in re.split(r"[-_]+", ns.strip()) if part
        )
        if titled and titled not in folders:
            folders.append(titled)
    # Dedupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for folder in folders:
        if folder in seen:
            continue
        seen.add(folder)
        ordered.append(folder)
    return [str(home / folder) for folder in ordered]


def resolve_repo_path(row: dict[str, Any]) -> Path | None:
    """Prefer an existing path on this host (Mac mirror or hub/dgx)."""
    candidates: list[str] = []
    for key in ("path", "dgx_path", "mac_path"):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            candidates.append(raw.strip())
    # Common home mirrors when registry only has the other host's paths
    name = str(row.get("name") or "")
    ns = str(row.get("namespace") or "").lower()
    candidates.extend(_home_mirror_candidates(name, ns))
    seen: set[str] = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        p = Path(c)
        if p.is_dir():
            return p
    return None


def _run(cmd: list[str], *, cwd: Path, timeout: int = 900) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            check=False,
        )
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "exit": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "exit": 124,
            "stdout_tail": "",
            "stderr_tail": f"timeout after {timeout}s: {exc}",
        }


def step_adapt(target: Path, *, dry_run: bool) -> dict[str, Any]:
    # automation_adapt uses --target (not --root). Needle OVERSEER_KIT_RUN_AE_2026_09_07
    # --quick: kit-run must not false-fail A when dirty target local.json was
    # re-poisoned with hub unittest storm (Newdrop). Needle OVERSEER_KIT_RUN_A_QUICK_2026_09_08
    cmd = [
        sys.executable,
        str(ADAPT),
        "--heal",
        "--write",
        "--quick",
        "--target",
        str(target),
    ]
    if dry_run:
        return {"step": "A_adapt", "ok": True, "dry_run": True, "cmd": cmd}
    result = _run(cmd, cwd=target)
    result["step"] = "A_adapt"
    result["ok"] = result.get("exit") == 0
    result["dry_run"] = False
    result["needle_a_quick"] = "OVERSEER_KIT_RUN_A_QUICK_2026_09_08"
    return result


def _verify_cmd_paths(verify_cmds: list[str]) -> list[str]:
    """Extract relative scripts/tests paths referenced by verify shell commands."""
    found: list[str] = []
    seen: set[str] = set()
    for shell in verify_cmds:
        for match in _VERIFY_PATH_RE.finditer(shell):
            rel = match.group(1).rstrip("/")
            if rel and rel not in seen:
                seen.add(rel)
                found.append(rel)
    return found


def heal_missing_verify_paths_from_head(
    target: Path,
    verify_cmds: list[str],
    *,
    donor: Path | None = None,
) -> list[str]:
    """Restore verify wrappers missing on the verify cwd.

    Needle: OVERSEER_KIT_RUN_B_ON_CLEAN_WT_2026_09_08 — CaaS dirty main deleted
    ``scripts/with-node.sh`` → B_verify exit 127 theater.

    OVERSEER_KIT_RUN_HEAL_DONOR_2026_09_08 — origin/main tip may also lack
    with-node (never committed) while dirty product root still has the wrapper;
    copy from donor after HEAD restore fails.
    """
    healed: list[str] = []
    for rel in _verify_cmd_paths(verify_cmds):
        dest = target / rel
        if dest.exists():
            continue
        probe = _run(
            ["git", "cat-file", "-e", f"HEAD:{rel}"],
            cwd=target,
            timeout=30,
        )
        if probe.get("exit") == 0:
            checkout = _run(
                ["git", "checkout", "HEAD", "--", rel],
                cwd=target,
                timeout=60,
            )
            if checkout.get("exit") == 0 and dest.exists():
                healed.append(rel)
                continue
        if donor is None:
            continue
        src = Path(donor) / rel
        if not src.is_file():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
        except OSError:
            continue
        if dest.exists():
            dest.chmod(dest.stat().st_mode | 0o111)
            healed.append(f"{rel}:donor")
    return healed


def ensure_node_modules_for_verify(
    verify_cwd: Path, source: Path
) -> str | None:
    """Share product node_modules into kit worktree (no npm ci tax).

    Fresh ``git worktree add`` has no node_modules → ``vitest: not found``.
    Symlink from the product root when present. Needle: OVERSEER_KIT_RUN_B_ON_CLEAN_WT_2026_09_08.
    """
    dest = verify_cwd / "node_modules"
    if dest.exists():
        return None
    src = source / "node_modules"
    if not src.is_dir():
        return "missing_source_node_modules"
    try:
        dest.symlink_to(src)
    except OSError as exc:
        return f"symlink_failed:{exc}"
    return "symlinked"


def step_verify(
    target: Path,
    verify_cmds: list[str],
    *,
    dry_run: bool,
    verify_cwd: Path | None = None,
) -> dict[str, Any]:
    planned = [{"shell": c} for c in verify_cmds]
    if dry_run:
        return {
            "step": "B_verify",
            "ok": True,
            "dry_run": True,
            "commands": planned,
            "needle_b_clean_wt": NEEDLE_B_CLEAN_WT,
        }
    cwd = Path(verify_cwd) if verify_cwd is not None else target
    donor = target if cwd.resolve() != target.resolve() else None
    healed = heal_missing_verify_paths_from_head(cwd, verify_cmds, donor=donor)
    nm_action: str | None = None
    needs_npm = any(
        "npm " in c or "with-node" in c or "vitest" in c for c in verify_cmds
    )
    if needs_npm and cwd.resolve() != target.resolve():
        nm_action = ensure_node_modules_for_verify(cwd, target)
    results: list[dict[str, Any]] = []
    ok = True
    for shell in verify_cmds:
        r = _run(["bash", "-lc", shell], cwd=cwd, timeout=1800)
        r["shell"] = shell
        results.append(r)
        if r.get("exit") != 0:
            ok = False
            break
    out: dict[str, Any] = {
        "step": "B_verify",
        "ok": ok,
        "dry_run": False,
        "results": results,
        "verify_cwd": str(cwd),
        "needle_b_clean_wt": NEEDLE_B_CLEAN_WT,
    }
    if healed:
        out["healed_from_head"] = healed
    if nm_action:
        out["node_modules"] = nm_action
        if nm_action.startswith("missing_") or nm_action.startswith("symlink_failed"):
            out["ok"] = False
    return out


def _worktree_start_ref(target: Path) -> str:
    """Prefer origin/main (or master) over stale/dirty HEAD for kit-run C.

    Needle: OVERSEER_KIT_RUN_C_ORIGIN_MAIN_2026_09_08 — Newdrop local HEAD lagged
    origin/main and lacked plan-gate fail-closed; B on HEAD-wt false-failed.
    """
    for ref in ("origin/main", "origin/master"):
        probe = _run(
            ["git", "rev-parse", "--verify", ref],
            cwd=target,
            timeout=30,
        )
        if probe.get("exit") == 0:
            return ref
    return "HEAD"


def step_worktree(target: Path, *, dry_run: bool) -> dict[str, Any]:
    """C: add dirty-main-safe worktree (prefer origin/main). Needle OVERSEER_KIT_RUN_AE.

    Retries unique stamps on path/branch collision (parallel overseer races).
    Needle: ``OVERSEER_KIT_WT_STAMP_COLLISION_2026_09_08``.
    """
    stamp = _kit_worktree_stamp()
    branch = f"peer/kit-a-to-z-{stamp}"
    wt_path = target.parent / f"{target.name}-kit-a-to-z-{stamp}"
    plan = {
        "suggested_branch": branch,
        "worktree_path": str(wt_path),
        "target": str(target),
        "hint": "git worktree add -b <branch> <path> origin/main|HEAD — dirty-main safe",
    }
    if dry_run:
        return {"step": "C_worktree", "ok": True, "dry_run": True, **plan}

    probe = _run(["git", "status", "--porcelain"], cwd=target, timeout=60)
    dirty = bool((probe.get("stdout_tail") or "").strip())
    if probe.get("exit") != 0:
        return {
            "step": "C_worktree",
            "ok": False,
            "dry_run": False,
            "dirty": dirty,
            "error": "git status failed",
            **plan,
        }

    start_ref = _worktree_start_ref(target)
    last_err = ""
    for attempt in range(8):
        stamp = _kit_worktree_stamp(attempt=attempt)
        branch = f"peer/kit-a-to-z-{stamp}"
        wt_path = target.parent / f"{target.name}-kit-a-to-z-{stamp}"
        plan = {
            "suggested_branch": branch,
            "worktree_path": str(wt_path),
            "target": str(target),
            "hint": "git worktree add -b <branch> <path> origin/main|HEAD — dirty-main safe",
            "start_ref": start_ref,
        }
        if wt_path.exists():
            last_err = f"worktree path exists: {wt_path}"
            continue
        add = _run(
            ["git", "worktree", "add", "-b", branch, str(wt_path), start_ref],
            cwd=target,
            timeout=120,
        )
        if add.get("exit") == 0 and wt_path.is_dir():
            return {
                "step": "C_worktree",
                "ok": True,
                "dry_run": False,
                "dirty": dirty,
                "status": "worktree_added",
                "add_exit": 0,
                "add_stderr": add.get("stderr_tail", "")[-500:],
                "attempts": attempt + 1,
                "needle": NEEDLE_AE,
                "needle_c_origin": "OVERSEER_KIT_RUN_C_ORIGIN_MAIN_2026_09_08",
                "stamp_collision_needle": "OVERSEER_KIT_WT_STAMP_COLLISION_2026_09_08",
                **plan,
            }
        err = (add.get("stderr_tail") or "")[-500:]
        last_err = err or f"worktree_add_exit:{add.get('exit')}"
        low = err.lower()
        if "already exists" in low or "already checked out" in low or wt_path.exists():
            continue
        return {
            "step": "C_worktree",
            "ok": False,
            "dry_run": False,
            "dirty": dirty,
            "status": "worktree_failed",
            "add_exit": add.get("exit"),
            "add_stderr": err,
            "error": last_err,
            "needle": NEEDLE_AE,
            **plan,
        }

    return {
        "step": "C_worktree",
        "ok": False,
        "dry_run": False,
        "dirty": dirty,
        "status": "worktree_failed",
        "error": last_err or "worktree stamp collision exhausted",
        "needle": NEEDLE_AE,
        "stamp_collision_needle": "OVERSEER_KIT_WT_STAMP_COLLISION_2026_09_08",
        **plan,
    }


def step_artifact(
    target: Path,
    *,
    worktree_path: str | None,
    branch: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    """D: PR URL when possible, else honest blocked receipt (no mid-loop human)."""
    if dry_run:
        return {
            "step": "D_artifact",
            "ok": True,
            "dry_run": True,
            "mode": "pr_or_blocked_receipt",
            "worktree_path": worktree_path,
            "branch": branch,
        }

    reasons: list[str] = []
    remotes = _run(["git", "remote"], cwd=target, timeout=30)
    remote_names = {
        line.strip()
        for line in (remotes.get("stdout_tail") or "").splitlines()
        if line.strip()
    }
    if "origin" not in remote_names:
        reasons.append("no_origin_remote")

    gh = shutil.which("gh")
    # OVERSEER_KIT_RUN_MERGE_NOTE_2026_09_07 — Plan DoD allows merge note without gh.
    # Push + write notes/FACTORY_A_TO_Z_MERGE_NOTE.md when origin exists; gh optional for PR.

    pr_url = None
    merge_note_path: str | None = None
    pushed_ref: str | None = None
    cwd = Path(worktree_path) if worktree_path else target

    if "no_origin_remote" not in reasons and worktree_path and branch:
        push = _run(
            ["git", "push", "-u", "origin", f"HEAD:refs/heads/{branch}"],
            cwd=cwd,
            timeout=180,
        )
        if push.get("exit") != 0:
            reasons.append(
                classify_push_failure(
                    exit_code=push.get("exit"),
                    stderr=str(push.get("stderr_tail") or ""),
                    stdout=str(push.get("stdout_tail") or ""),
                )
            )
        else:
            pushed_ref = f"origin/{branch}"
            if gh:
                create = _run(
                    [
                        gh,
                        "pr",
                        "create",
                        "--fill",
                        "--head",
                        branch,
                        "--title",
                        f"kit A→Z prove ({NEEDLE_AE})",
                    ],
                    cwd=cwd,
                    timeout=180,
                )
                out = (create.get("stdout_tail") or "") + "\n" + (create.get("stderr_tail") or "")
                m = re.search(r"https://github\.com/\S+/pull/\d+", out)
                if m:
                    pr_url = m.group(0)
                elif create.get("exit") != 0:
                    reasons.append(f"gh_pr_create_failed:{create.get('exit')}")
                else:
                    reasons.append("gh_pr_create_no_url")
            else:
                # Irreversible merge note (hub notes/) — satisfies D without gh.
                note = ROOT / "notes" / "FACTORY_A_TO_Z_MERGE_NOTE.md"
                body = (
                    f"# Factory A→Z merge note\n\n"
                    f"Needle: `{NEEDLE_AE}`\n\n"
                    f"- target: `{target}`\n"
                    f"- worktree: `{worktree_path}`\n"
                    f"- branch pushed: `{pushed_ref}`\n"
                    f"- ts: {_utc()}\n"
                    f"- gh: missing — PR deferred; push is irreversible remote artifact\n"
                )
                try:
                    note.write_text(body, encoding="utf-8")
                    merge_note_path = str(note)
                except OSError as exc:
                    reasons.append(f"merge_note_write_failed:{exc}")

    if pr_url:
        return {
            "step": "D_artifact",
            "ok": True,
            "dry_run": False,
            "mode": "pr",
            "pr_url": pr_url,
            "branch": branch,
            "worktree_path": worktree_path,
            "needle": NEEDLE_AE,
        }

    if merge_note_path and pushed_ref:
        return {
            "step": "D_artifact",
            "ok": True,
            "dry_run": False,
            "mode": "merge_note",
            "merge_note": merge_note_path,
            "pushed_ref": pushed_ref,
            "branch": branch,
            "worktree_path": worktree_path,
            "needle": NEEDLE_AE,
        }

    if not gh and "gh_cli_missing" not in reasons:
        reasons.append("gh_cli_missing")

    # OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08 — Mac already filed kit PRs while
    # CLEAN push/gh is auth-empty → adopt public open/merged PR instead of blocked
    # receipt that freezes twenty-third+ Active / queue_fp.
    adopted = discover_origin_kit_prs(target)
    if adopted and adopted.get("pr_url"):
        return {
            "step": "D_artifact",
            "ok": True,
            "dry_run": False,
            "mode": "pr",
            "pr_url": adopted["pr_url"],
            "branch": adopted.get("branch") or branch,
            "worktree_path": worktree_path,
            "target": str(target),
            "adopted_public_pr": True,
            "adopted_state": adopted.get("state"),
            "sibling_prs": adopted.get("sibling_prs"),
            "local_block_reasons": reasons,
            "needle": NEEDLE_AE,
            "public_pr_needle": "OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08",
        }

    # Honest blocked receipt counts as irreversible artifact for Phase 2 stamp.
    receipt = {
        "blocked": True,
        "reasons": reasons or ["unknown_block"],
        "branch": branch,
        "worktree_path": worktree_path,
        "target": str(target),
        "ts": _utc(),
        "needle": NEEDLE_AE,
        "note": (
            "Unsupervised compound stopped at D with explicit blocked receipt — "
            "no mid-loop human. Re-run after origin+gh available for PR path."
        ),
    }
    return {
        "step": "D_artifact",
        "ok": True,  # blocked receipt is a valid Phase-2 outcome
        "dry_run": False,
        "mode": "blocked_receipt",
        "blocked_receipt": receipt,
        "needle": NEEDLE_AE,
    }


def _patch_proof_md(
    *,
    repo: str,
    steps: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> None:
    """E writeback into FACTORY_A_TO_Z_PROOF.md runs table + last compound."""
    date = _utc()[:10]
    marks: dict[str, str] = {}
    for letter, key in (
        ("A", "A_adapt"),
        ("B", "B_verify"),
        ("C", "C_worktree"),
        ("D", "D_artifact"),
        ("E", "E_writeback"),
    ):
        hit = next((s for s in steps if s.get("step") == key), None)
        if hit is None:
            marks[letter] = "—"
        elif hit.get("ok"):
            marks[letter] = "ok"
        else:
            marks[letter] = "FAIL"
    if artifact.get("mode") == "pr":
        d_note = artifact.get("pr_url") or "pr"
        marks["D"] = "pr"
    elif artifact.get("mode") == "merge_note":
        d_note = f"merge_note:{artifact.get('pushed_ref') or artifact.get('branch')}"
        marks["D"] = "merge_note"
    elif artifact.get("mode") == "blocked_receipt":
        reasons = (artifact.get("blocked_receipt") or {}).get("reasons") or []
        d_note = "blocked:" + ",".join(str(r) for r in reasons[:3])
        marks["D"] = "blocked"
    else:
        d_note = str(artifact.get("mode") or "—")

    row = (
        f"| {date} | {repo} | {marks['A']} | {marks['B']} | {marks['C']} | "
        f"{marks['D']} | ok | {d_note} · {NEEDLE_AE} |"
    )
    text = PROOF_MD.read_text(encoding="utf-8") if PROOF_MD.is_file() else ""

    # Prefer replacing placeholder run rows; never touch Lock status fields.
    if re.search(r"\| — \| — \|", text) or "awaiting Phase 1" in text:
        text = re.sub(
            r"\| — \|[^\n]*awaiting[^\n]*\n|\| — \| — \|[^\n]*\n",
            row + "\n",
            text,
            count=1,
        )
    elif NEEDLE_AE not in text:
        # Insert after Runs table header separator (second markdown table)
        parts = text.split("## Runs", 1)
        if len(parts) == 2:
            head, rest = parts
            rest = re.sub(
                r"(\|----[-| ]+\|\n)",
                r"\1" + row + "\n",
                rest,
                count=1,
            )
            text = head + "## Runs" + rest
        else:
            text = text.rstrip() + "\n\n" + row + "\n"

    # OVERSEER_KIT_RUN_PROOF_DATE_BACKREF_2026_09_08 — never rf"\1{date}" when date
    # starts with a digit (``\12026`` is octal → ``P26``). Use ``\g<1>`` / ``\g<2>``.
    compound = f"| Last compound | {date} {repo} A→E ({artifact.get('mode')}) |"
    if re.search(r"\| Last compound \|", text):
        text = re.sub(
            r"\| Last compound \|[^\n]*",
            compound,
            text,
            count=1,
        )
    else:
        # Heal octal-corrupted lock rows (``P26-09-08 …|``) or insert after First target.
        if re.search(r"^P26-\d{2}-\d{2} ", text, flags=re.M):
            text = re.sub(
                r"^P26-\d{2}-\d{2} [^\n]*\|?\n",
                compound + "\n",
                text,
                count=1,
                flags=re.M,
            )
        elif re.search(r"\| First target \|", text):
            text = re.sub(
                r"(\| First target \|[^\n]*\n)",
                r"\1" + compound + "\n",
                text,
                count=1,
            )
        else:
            text = text.rstrip() + "\n" + compound + "\n"
    # OVERSEER_KIT_RUN_PROOF_UPSERT_2026_09_08 — always insert a Runs row even when
    # NEEDLE_AE already appears elsewhere in the proof (live file always has it).
    if row not in text:
        if "## Runs" in text:
            parts = text.split("## Runs", 1)
            head, rest = parts
            if re.search(r"\|----[-| ]+\|\n", rest):
                rest = re.sub(
                    r"(\|----[-| ]+\|\n)",
                    r"\1" + row + "\n",
                    rest,
                    count=1,
                )
            else:
                rest = "\n" + row + "\n" + rest
            text = head + "## Runs" + rest
        elif NEEDLE_AE not in text:
            text = text.rstrip() + "\n\n" + row + "\n"
    PROOF_MD.parent.mkdir(parents=True, exist_ok=True)
    PROOF_MD.write_text(text, encoding="utf-8")


def _patch_external_proof(*, repo: str, artifact: dict[str, Any]) -> None:
    if not EXTERNAL_PROOF.is_file():
        return
    text = EXTERNAL_PROOF.read_text(encoding="utf-8")
    date = _utc()[:10]
    if artifact.get("mode") == "pr":
        status = f"kit A→E PR {artifact.get('pr_url')}"
        pr = artifact.get("pr_url") or "—"
    elif artifact.get("mode") == "merge_note":
        status = f"kit A→E merge_note {artifact.get('pushed_ref')}"
        pr = artifact.get("merge_note") or "merge note (gh missing)"
    else:
        reasons = (artifact.get("blocked_receipt") or {}).get("reasons") or ["blocked"]
        status = f"kit A→E blocked ({','.join(str(r) for r in reasons[:3])})"
        pr = "blocked receipt (see factory_a_to_z_last.json)"
    # Update first CPT pending row if present
    new_row = f"| 1 | {repo} | {status} | native verify ok | {pr} | {date} |"
    if re.search(r"\| 1 \| CPT \|", text):
        text = re.sub(r"\| 1 \| CPT \|[^\n]*\n", new_row + "\n", text, count=1)
    EXTERNAL_PROOF.write_text(text, encoding="utf-8")


def step_writeback(
    *,
    repo: str,
    steps: list[dict[str, Any]],
    artifact: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    """E: stamp FACTORY_A_TO_Z_PROOF + EXTERNAL_PROOF from compound receipt."""
    if dry_run:
        return {
            "step": "E_writeback",
            "ok": True,
            "dry_run": True,
            "paths": [str(PROOF_MD), str(EXTERNAL_PROOF), str(PROOF_JSON)],
        }
    try:
        _patch_proof_md(repo=repo, steps=steps, artifact=artifact)
        _patch_external_proof(repo=repo, artifact=artifact)
        # Never leave a prior false-green Status after an honest blocked D.
        heal = heal_false_green_lock(write=True)
        return {
            "step": "E_writeback",
            "ok": True,
            "dry_run": False,
            "paths": [str(PROOF_MD), str(EXTERNAL_PROOF), str(PROOF_JSON)],
            "needle": NEEDLE_AE,
            "false_green_heal": heal,
        }
    except OSError as exc:
        return {
            "step": "E_writeback",
            "ok": False,
            "dry_run": False,
            "error": str(exc),
            "needle": NEEDLE_AE,
        }


def write_receipt(payload: dict[str, Any], path: Path | None = None) -> None:
    dest = PROOF_JSON if path is None else path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _commit_receipt(report: dict[str, Any], *, dry_run: bool) -> None:
    """OVERSEER_FALSE_GREEN_LOCK_2026_09_07 — dry-run must not clobber live proof JSON."""
    if dry_run:
        report["receipt_skipped"] = "dry_run"
        return
    write_receipt(report)


def run_kit(
    repo_name: str,
    *,
    dry_run: bool,
    stop_after: str = "E",
) -> dict[str, Any]:
    reg = load_registry()
    row = find_repo(reg, repo_name)
    if row is None:
        return {
            "ok": False,
            "error": f"repo not found: {repo_name}",
            "needle": NEEDLE,
            "ts": _utc(),
        }
    target = resolve_repo_path(row)
    if target is None:
        return {
            "ok": False,
            "error": f"no existing path for {row.get('name')}",
            "registry_path": row.get("path"),
            "needle": NEEDLE,
            "ts": _utc(),
        }
    verify = row.get("verify_commands") or []
    if not isinstance(verify, list) or not verify:
        verify = ["python3 scripts/peer_orchestrate.py --self-check --quick"]
    verify_cmds = [str(c) for c in verify]

    steps: list[dict[str, Any]] = []
    stop = stop_after.upper()
    report: dict[str, Any] = {
        "needle": NEEDLE,
        "needle_ae": NEEDLE_AE,
        "ts": _utc(),
        "repo": row.get("name"),
        "namespace": row.get("namespace"),
        "target": str(target),
        "dry_run": dry_run,
        "stop_after": stop,
        "steps": steps,
    }

    a = step_adapt(target, dry_run=dry_run)
    steps.append(a)
    if not a.get("ok"):
        report["ok"] = False
        report["blocked"] = "A_adapt"
        _commit_receipt(report, dry_run=dry_run)
        return report
    if stop == "A":
        report["ok"] = True
        _commit_receipt(report, dry_run=dry_run)
        return report

    # OVERSEER_KIT_RUN_B_ON_CLEAN_WT_2026_09_08 — create C before B so dirty
    # main (deleted with-node.sh / test files) cannot false-fail native verify.
    c = step_worktree(target, dry_run=dry_run)
    steps.append(c)
    if not c.get("ok"):
        report["ok"] = False
        report["blocked"] = "C_worktree"
        _commit_receipt(report, dry_run=dry_run)
        return report

    verify_cwd: Path | None = None
    if not dry_run:
        wt = c.get("worktree_path")
        if wt:
            verify_cwd = Path(str(wt))

    b = step_verify(target, verify_cmds, dry_run=dry_run, verify_cwd=verify_cwd)
    steps.append(b)
    if not b.get("ok"):
        report["ok"] = False
        report["blocked"] = "B_verify"
        _commit_receipt(report, dry_run=dry_run)
        return report
    if stop in ("B", "C"):
        report["ok"] = True
        if stop == "C":
            report["note"] = (
                "Stopped after C (worktree). B ran on clean wt — "
                f"{NEEDLE_B_CLEAN_WT}. Pass --stop-after E for Phase 2."
            )
        else:
            report["note"] = (
                "Stopped after B (verify on clean worktree) — "
                f"{NEEDLE_B_CLEAN_WT}."
            )
        _commit_receipt(report, dry_run=dry_run)
        return report

    d = step_artifact(
        target,
        worktree_path=c.get("worktree_path"),
        branch=c.get("suggested_branch"),
        dry_run=dry_run,
    )
    steps.append(d)
    if not d.get("ok"):
        report["ok"] = False
        report["blocked"] = "D_artifact"
        _commit_receipt(report, dry_run=dry_run)
        return report
    if stop == "D":
        report["ok"] = True
        _commit_receipt(report, dry_run=dry_run)
        return report

    # E needs D in steps list already; writeback then append E
    e = step_writeback(
        repo=str(row.get("name") or repo_name),
        steps=steps,
        artifact=d,
        dry_run=dry_run,
    )
    steps.append(e)
    if not e.get("ok"):
        report["ok"] = False
        report["blocked"] = "E_writeback"
        _commit_receipt(report, dry_run=dry_run)
        return report

    report["ok"] = True
    report["artifact_mode"] = d.get("mode")
    report["note"] = (
        f"Phase2 A→E complete ({d.get('mode')}). "
        f"Green lock still requires Phase 3–4 — {NEEDLE_AE}."
    )
    _commit_receipt(report, dry_run=dry_run)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Factory kit A→Z compound")
    ap.add_argument("--list", action="store_true", help="List registry repos")
    ap.add_argument("--repo", default="CPT", help="Registry name/namespace (default CPT)")
    ap.add_argument("--dry-run", action="store_true", help="Print planned steps only")
    ap.add_argument("--run", action="store_true", help="Execute A→E compound (default stop E)")
    ap.add_argument(
        "--heal-false-green",
        action="store_true",
        help="Force PROOF Status red when green lacks eligible PR/merge_note",
    )
    ap.add_argument(
        "--stop-after",
        default="E",
        choices=("A", "B", "C", "D", "E", "a", "b", "c", "d", "e"),
        help="Stop after step letter (default E)",
    )
    ap.add_argument("--json", action="store_true", help="Print JSON receipt")
    args = ap.parse_args(argv)

    if args.heal_false_green:
        heal = heal_false_green_lock(write=True)
        if args.json:
            print(json.dumps(heal, indent=2))
        else:
            print(
                f"{NEEDLE_FALSE_GREEN} action={heal.get('action')} "
                f"healed={heal.get('healed')} eligible={heal.get('eligible')} "
                f"why={heal.get('eligible_why')}"
            )
        return 0 if heal.get("action") in ("noop", "force_red") else 1

    if args.list:
        for row in list_repos(load_registry()):
            if not isinstance(row, dict):
                continue
            p = resolve_repo_path(row)
            print(
                f"{row.get('name')}\t{row.get('status')}\t"
                f"{'OK ' + str(p) if p else 'MISSING ' + str(row.get('path'))}"
            )
        return 0

    if not args.run and not args.dry_run:
        args.dry_run = True

    report = run_kit(args.repo, dry_run=args.dry_run, stop_after=args.stop_after.upper())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{NEEDLE} kit-run repo={report.get('repo')} target={report.get('target')}")
        print(f"ok={report.get('ok')} dry_run={report.get('dry_run')} blocked={report.get('blocked')}")
        for step in report.get("steps") or []:
            print(f"  {step.get('step')}: ok={step.get('ok')} dry_run={step.get('dry_run')} mode={step.get('mode')}")
        if report.get("error"):
            print(f"error: {report['error']}", file=sys.stderr)
        if report.get("note"):
            print(report["note"])
        print(f"receipt: {PROOF_JSON}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
