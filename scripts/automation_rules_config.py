"""Automation rules config — declarative event → action rules."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import project_automation as auto

ROOT = auto.ROOT
DEFAULT_RULES = ROOT / "automation.rules.json"
LOCAL_RULES = auto.CONFIG_DIR / "automation.rules.local.json"


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("automation_engine")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def rules_paths() -> list[Path]:
    paths: list[Path] = []
    custom = _cfg().get("rules_path")
    if custom:
        paths.append(Path(str(custom)).expanduser())
    if LOCAL_RULES.is_file():
        paths.append(LOCAL_RULES)
    if DEFAULT_RULES.is_file():
        paths.append(DEFAULT_RULES)
    return paths


def webhook_token() -> str:
    env = os.environ.get("AUTOMATION_WEBHOOK_TOKEN", "").strip()
    if env:
        return env
    raw = str(_cfg().get("webhook_token") or "").strip()
    if raw.startswith("env:"):
        return os.environ.get(raw[4:].strip(), "").strip()
    return raw


def state_path() -> Path:
    return auto.CONFIG_DIR / "automation-engine-state.json"


def log_path() -> Path:
    return auto.CONFIG_DIR / "automation-engine.log"


def audit_enabled() -> bool:
    return bool(_cfg().get("audit_log", True))
