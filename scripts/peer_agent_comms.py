#!/usr/bin/env python3
"""GLink — structured agent-to-agent comms via shared files (Gibberlink-inspired).

GibberLink (GGWave/audio) targets voice A2A; this kit uses **compact JSON on disk**:
faster than English, human-auditable, no P2P sessions. Pattern:

- **Shared bus** — ``bus.jsonl`` append-only broadcast (+ optional ``to`` field)
- **Per-agent vault** — ``agents/{role_id}/state.json`` (tasks, summary)
- **Private notes** — ``agents/{role_id}/notes.jsonl``

Agents read the bus + their vault each cycle; post GLink lines after material work.

Usage:
  python3 scripts/peer_agent_comms.py --status
  python3 scripts/peer_agent_comms.py --init
  python3 scripts/peer_agent_comms.py --post --from factory_engineer --type STAT --payload '{"st":"WIP","op":"adapt"}'
  python3 scripts/peer_agent_comms.py --bus --limit 20
  ./scripts/peer comms
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
# COMPRESSION_ZLIB_GLINK_FP_2026_09_07 — path/cid digests use zlib (stdlib);
# top-level hashlib pulled libcrypto (~2.5MB) on every GLink import.

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_roles as roles  # noqa: E402
import project_automation as auto  # noqa: E402

COMMS_DIR = auto.CONFIG_DIR / "agent-comms"
BUS_PATH = COMMS_DIR / "bus.jsonl"
AGENTS_DIR = COMMS_DIR / "agents"
PROTOCOL_VERSION = 1
BUS_ROTATE_MAX_LINES = 500
BUS_ROTATE_KEEP_LINES = 250
# Hot-path caps — keep bus/vault prompt injection small.
SUMMARY_WRITE_CAP = 4000
SUMMARY_PROMPT_CAP = 200
NOTE_CAP = 120
STR_VALUE_CAP = 160
MAX_PROSE_WORDS = 8
PATH_HASH_LEN = 8
# Prompt-injection caps — bus tail dominates format_prompt_block bytes.
BUS_PROMPT_LIMIT = 12
BUS_PROMPT_LINE_CAP = 220
MCP_NEED_PREFIX = "mcp:"
# Hot-path cap for mcp REQ args JSON (compact) — reject English/bloat tool blobs.
MCP_ARGS_BYTE_BUDGET = 512
MCP_NS_MAX = 64
MCP_TOOL_MAX = 64
# Prompt-only vault tip caps (disk todo/summary stay full).
VAULT_NEXT_TIP_CAP = 48
VAULT_SUMMARY_PROMPT_CAP = 48
_ASN_BRACKET_RE = re.compile(r"^\[(asn-[^\]]+)\]", re.IGNORECASE)
_VAULT_ST_RE = re.compile(r"^(WIP|DONE|BLOCK|IDLE)\b(?:\s+(\S+))?", re.IGNORECASE)
_VAULT_ACTIVE_RE = re.compile(r"Active\s*=\s*(\d+)", re.IGNORECASE)
_VAULT_DRIFT_RE = re.compile(r"drift\s*=\s*(\d+)", re.IGNORECASE)
# Fixed REQ need codes (+ aliases) — MCP tools use mcp:<tool>.
REQ_NEED_ALIASES = {
    "verify": "vfy",
    "validation": "vfy",
    "self_heal": "heal",
    "self-heal": "heal",
    "heal_all": "heal",
    "adapt_heal": "adapt",
    "sync_queue": "sync",
    "assignment": "assign",
    # Rule-change proposals (propose-only → human close)
    "rule_suspend": "rsusp",
    "rule-suspend": "rsusp",
    "RULE_SUSPEND_REQ": "rsusp",
    "rule_change": "rchg",
    "rule-change": "rchg",
    "RULE_SUSPEND_ACK": "rchg",
}
REQ_NEED_CODES = frozenset(
    {
        "vfy",
        "adapt",
        "heal",
        "sync",
        "assign",
        "review",
        "audit",
        "comms",
        "rsusp",  # propose suspend (args.act defaults sus)
        "rchg",  # propose add|rm|mod|sus via args.act
    }
)
# STAT.op aliases — keep hot-path op codes short (≤8).
STAT_OP_ALIASES = {
    "verify": "vfy",
    "validation": "vfy",
    "self_heal": "heal",
    "self-heal": "heal",
    "hand_out": "hand",
    "orchestrate": "orch",
    "materialize": "mat",
    "schema_extend": "schema",
}
PRI_MAX = 9
TTL_MAX_SEC = 86400
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_PH_HEX_RE = re.compile(r"^[0-9a-f]{4,40}$")
_BREF_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/@-]{0,63}$")
_ROOT_STR = str(ROOT)
_BUS_PATH_STR = str(BUS_PATH)
_COMMS_DIR_STR = str(COMMS_DIR)

# Compact message types (not English — fixed vocabulary).
MSG_STAT = "STAT"  # status: st=WIP|DONE|BLOCK|IDLE, op=short code
MSG_DONE = "DONE"  # completed task ref
MSG_REQ = "REQ"  # request help: to=role_id, need=code
MSG_ACK = "ACK"  # acknowledge REQ
MSG_BLOCK = "BLOCK"  # blocked: reason code
MSG_DIFF = "DIFF"  # touched paths/refs
MSG_SUM = "SUM"  # summary snapshot
MSG_ASN = "ASN"  # assign work: task, eta_sec, when, due (peer_work_assign)

VALID_TYPES = frozenset(
    {MSG_STAT, MSG_DONE, MSG_REQ, MSG_ACK, MSG_BLOCK, MSG_DIFF, MSG_SUM, MSG_ASN}
)
BROADCAST = "*"


def comms_enabled() -> bool:
    return bool(auto.CFG.get("agent_comms_enabled", True))


def _short_digest(raw: bytes, n: int) -> str:
    """zlib adler+crc short fingerprint — no hashlib/libcrypto.

    Needle: COMPRESSION_ZLIB_GLINK_FP_2026_09_07
    """
    import zlib

    digest = f"{zlib.adler32(raw) & 0xffffffff:08x}{zlib.crc32(raw) & 0xffffffff:08x}"
    return digest[: max(1, int(n))]


def path_hash(path: str, *, n: int = PATH_HASH_LEN) -> str:
    """Short path fingerprint for DIFF/DONE without shipping full path strings."""
    return _short_digest(str(path).encode("utf-8"), max(4, int(n)))


def glink_schema() -> dict[str, Any]:
    """Machine-readable GLink contract (additive under PROTOCOL_VERSION=1)."""
    return {
        "v": PROTOCOL_VERSION,
        "types": sorted(VALID_TYPES),
        "envelope": {
            "v": "int",
            "t": "type",
            "f": "from",
            "to": "role|*",
            "ts": "iso",
            "p": "object",
        },
        "payload_fields": {
            MSG_STAT: ["st", "op", "vfy?", "noop?", "note?", "ft?", "cid?", "pri?", "ttl?", "git?", "re?"],
            MSG_DONE: ["ref", "paths?", "ph?", "bref?", "cid?", "kp?"],
            MSG_REQ: [
                "need",
                "cid",
                "args?",
                "mcp?",
                "ns?",  # Cursor MCP namespace (CallDynamicTool) — top-level, not args.ns
                "pri?",
                "ttl?",
                "re?",
                # rsusp/rchg: args.act=add|rm|mod|sus, args.rid, args.why?, args.id? (ack)
            ],
            MSG_ACK: ["cid|ref", "ok?", "re?", "id?"],
            MSG_BLOCK: ["reason", "wait?", "cid?"],
            MSG_DIFF: ["paths?", "ph?", "bref?", "wt?", "cid?", "kp?"],
            MSG_SUM: ["txt?", "code?", "tx?", "n?", "cid?", "sh?", "ah?"],
            MSG_ASN: ["id", "task", "eta_sec?", "when?", "due?", "paths?", "pri?", "ttl?"],
        },
        "compact": {
            "ph": f"path zlib-fp[:{PATH_HASH_LEN}]",
            "bref": "binary/artifact ref",
            "cid": "REQ/ACK correlation id",
            "need": "fixed code or mcp:<tool>",
            "ns": f"MCP namespace ≤{MCP_NS_MAX} (Cursor CallDynamicTool)",
            "pri": f"0-{PRI_MAX} urgency",
            "ttl": f"seconds ≤{TTL_MAX_SEC}",
            "re": "reply-to cid",
            "git": "short HEAD hex",
            "tx": "SUM alias → code",
            "kp": "1=keep paths on DIFF/DONE (default: paths→ph)",
            "sh": "SUM shared compact {m,f,q} (shared/team→sh; drop factory)",
            "ah": "SUM asn sha1[:8] when assignment prose compacted",
        },
        "need_codes": sorted(REQ_NEED_CODES),
        "stat_ops": sorted(set(STAT_OP_ALIASES.values()) | {"cycle", "schema", "hand", "orch", "mat"}),
        "mcp_prefix": MCP_NEED_PREFIX,
        "validators": {
            "payload": "validate_glink_payload",
            "english_reject": "_reject_english_heavy",
            "cid": "_ensure_cid",
            "path_hash": "path_hash",
            "prefer_ph": "_compact_paths_to_ph",
            "ph_bref": "_normalize_ph_bref",
            "build_diff": "build_diff_payload",
            "build_done": "build_done_payload",
            "req_need": "_normalize_req_need",
            "mcp_need": "mcp:<tool> | need=mcp + args.tool; optional ns; lean args (no dup tool)",
            "mcp_ns": "_finalize_mcp_req",
            "stat_op_aliases": "_normalize_stat_op",
            "sum_tx_alias": "_normalize_sum_aliases",
            "sum_nested": "_normalize_sum_nested",
            "pri": "_normalize_pri_ttl",
            "ttl": "_normalize_pri_ttl",
            "re": "reply-to cid str",
            "stat_asn": "ASN requires id+task",
            "stat_git": "STAT.git short hex",
            "req_self": "_reject_req_self",
            "last_ack": "materialize_open_reqs_mcp acked set",
            "open_threads": "materialize_open_reqs_mcp",
            "a2a_card": "validate_a2a_task_card",
            "a2a_from_glink": "a2a_task_card_from_glink",
            "tip_wip_dedupe": "_filter_duplicate_stat_op",
            "prompt_vault_summary": "_prompt_vault_summary",
        },
        "materialize": {
            "role_board": "materialize_role_board",
            "open_reqs_mcp": "materialize_open_reqs_mcp",
            "vault_next_tip": "_prompt_vault_next_tip",
            "vault_summary": "_prompt_vault_summary",
            "vault_prompt_lean": "format_vault_block",
            "bus_prompt_filter": "_filter_prompt_bus_msgs",
            "protocol_lean": "format_glink_protocol_doc",
            "a2a_open": "materialize_a2a_open_cards",
        },
        "a2a": {
            "card": ["id", "from", "to", "task", "cid", "eta?", "st?"],
            "from_types": [MSG_REQ, MSG_ACK, MSG_ASN],
            "builder": "build_a2a_task_card",
        },
        "encoding": {"prefer": "jsonl", "rate_threshold": 0.85},
        "caps": {
            "summary_write": SUMMARY_WRITE_CAP,
            "summary_prompt": SUMMARY_PROMPT_CAP,
            "note": NOTE_CAP,
            "str_value": STR_VALUE_CAP,
            "prose_words": MAX_PROSE_WORDS,
            "bus_prompt_limit": BUS_PROMPT_LIMIT,
            "bus_prompt_line": BUS_PROMPT_LINE_CAP,
            "vault_next_tip": VAULT_NEXT_TIP_CAP,
            "vault_summary_prompt": VAULT_SUMMARY_PROMPT_CAP,
            "pri_max": PRI_MAX,
            "ttl_max": TTL_MAX_SEC,
            "mcp_args_budget": MCP_ARGS_BYTE_BUDGET,
            # Prompt vaults: protocol doc already has COMMS root — omit per-role state.json paths.
            "vault_omit_state_path": True,
        },
    }


def _reject_english_heavy(val: str) -> None:
    """Raise if a payload string looks like English prose (hot-path ban)."""
    s = str(val)
    if len(s) > STR_VALUE_CAP:
        raise ValueError(f"GLink p value exceeds {STR_VALUE_CAP} chars — use codes/ph/bref")
    words = _ENGLISH_WORD_RE.findall(s)
    if len(words) > MAX_PROSE_WORDS:
        raise ValueError("GLink p value too English-heavy — use fixed codes, not prose")
    if s.count(" ") >= 6 and any(c in s for c in ".!?"):
        raise ValueError("GLink p value looks like a sentence — use codes/paths only")


def _ensure_cid(msg_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """REQ gets auto cid; ACK must correlate via cid or ref."""
    out = dict(payload)
    if "cd" in out and "cid" not in out:
        out["cid"] = out.pop("cd")
    elif "cd" in out and "cid" in out and str(out["cd"]) != str(out["cid"]):
        raise ValueError("GLink cid/cd mismatch")
    else:
        out.pop("cd", None)
    cid = str(out.get("cid") or "").strip()
    if msg_type == MSG_REQ and not cid:
        raw = f"{out.get('need') or ''}:{_now_iso()}:{time.time_ns()}"
        out["cid"] = _short_digest(raw.encode("utf-8"), 10)
    elif msg_type == MSG_ACK:
        ref = str(out.get("ref") or "").strip()
        if not cid and not ref:
            raise ValueError("ACK requires cid or ref for correlation")
    return out


def _enforce_mcp_args_budget(args: dict[str, Any]) -> dict[str, Any]:
    """Reject mcp REQ args blobs that would bloat the bus hot path."""
    raw = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
    nbytes = len(raw.encode("utf-8"))
    if nbytes > MCP_ARGS_BYTE_BUDGET:
        raise ValueError(
            f"GLink mcp args exceed {MCP_ARGS_BYTE_BUDGET}B (got {nbytes}) — shrink tool args"
        )
    return args


def _finalize_mcp_req(out: dict[str, Any], lean: dict[str, Any]) -> dict[str, Any]:
    """Apply ns + lean args after need folded to mcp:<tool> (PROTOCOL stays 1).

    Promote args.ns → top-level ns (Cursor CallDynamicTool namespace). Drop dup.
    """
    ns = out.get("ns")
    if ns is None and "ns" in lean:
        ns = lean.get("ns")
    if ns is not None and ns != "":
        if not isinstance(ns, str) or not (1 <= len(str(ns)) <= MCP_NS_MAX):
            raise ValueError(f"GLink mcp p.ns must be 1..{MCP_NS_MAX} chars")
        ns_s = str(ns)
        if any(c.isspace() for c in ns_s):
            raise ValueError("GLink mcp p.ns must not contain whitespace")
        out["ns"] = ns_s
    else:
        out.pop("ns", None)
    lean = {k: v for k, v in lean.items() if k != "ns"}
    if lean:
        out["args"] = _enforce_mcp_args_budget(lean)
    else:
        out.pop("args", None)
    out.pop("tool", None)
    return out


def _normalize_req_need(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize REQ.need to fixed codes or mcp:<tool>; reject free-text needs."""
    out = dict(payload)
    raw_need = str(out.get("need") or "").strip()
    if not raw_need:
        raise ValueError("REQ requires need=code or mcp:<tool>")
    need = REQ_NEED_ALIASES.get(raw_need, raw_need)
    args = out.get("args")
    if not isinstance(args, dict):
        args = {}
    mcp_flag = out.get("mcp")
    if need.startswith(MCP_NEED_PREFIX):
        tool = need[len(MCP_NEED_PREFIX) :].strip()
        if not tool or " " in tool or len(tool) > MCP_TOOL_MAX:
            raise ValueError("GLink mcp need must be mcp:<tool> (no spaces)")
        out["need"] = f"{MCP_NEED_PREFIX}{tool}"
        out["mcp"] = 1
        # tool lives in need= — drop redundant args.tool (hot-path bytes).
        lean = {k: v for k, v in args.items() if k != "tool"}
        return _finalize_mcp_req(out, lean)
    if need == "mcp" or mcp_flag in (1, True, "1"):
        tool = str(args.get("tool") or out.get("tool") or "").strip()
        if not tool or " " in tool or len(tool) > MCP_TOOL_MAX:
            raise ValueError("GLink mcp REQ requires args.tool")
        out["need"] = f"{MCP_NEED_PREFIX}{tool}"
        out["mcp"] = 1
        lean = {k: v for k, v in args.items() if k != "tool"}
        return _finalize_mcp_req(out, lean)
    if need not in REQ_NEED_CODES:
        raise ValueError(
            f"GLink REQ need {need!r} invalid; use {sorted(REQ_NEED_CODES)} or mcp:<tool>"
        )
    out["need"] = need
    out.pop("mcp", None)
    if need in ("rsusp", "rchg"):
        # Compact act: add|rm|mod|sus — default sus for rsusp.
        act = str(args.get("act") or out.get("act") or ("sus" if need == "rsusp" else "")).strip().lower()
        act_aliases = {
            "suspend": "sus",
            "pause": "sus",
            "remove": "rm",
            "delete": "rm",
            "modify": "mod",
            "edit": "mod",
            "create": "add",
            "new": "add",
        }
        act = act_aliases.get(act, act)
        if act and act not in ("add", "rm", "mod", "sus"):
            raise ValueError("GLink rsusp/rchg args.act must be add|rm|mod|sus")
        if need == "rsusp" and not act:
            act = "sus"
        if not act:
            raise ValueError("GLink rchg requires args.act=add|rm|mod|sus")
        rid = str(args.get("rid") or out.get("rid") or "").strip()
        if op_is_propose(args, out) and not rid:
            raise ValueError("GLink rsusp/rchg propose requires args.rid")
        args = {**args, "act": act}
        if rid:
            args["rid"] = rid[:80]
        out["args"] = args
    elif args:
        out["args"] = args
    return out


def op_is_propose(args: dict[str, Any], out: dict[str, Any]) -> bool:
    op = str(args.get("op") or out.get("op") or "propose").strip().lower()
    return op not in ("ack", "ok")


def _normalize_stat_op(payload: dict[str, Any]) -> dict[str, Any]:
    """Collapse STAT.op aliases to short codes (≤8 chars)."""
    out = dict(payload)
    raw = str(out.get("op") or "").strip()
    if not raw:
        return out
    op = STAT_OP_ALIASES.get(raw, raw)
    if len(op) > 8 or " " in op:
        raise ValueError("GLink STAT op must be ≤8 chars code (no spaces)")
    out["op"] = op
    return out


def _normalize_sum_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    """SUM tx → code alias (compact transmit key)."""
    out = dict(payload)
    if "tx" in out and "code" not in out:
        out["code"] = out.pop("tx")
    elif "tx" in out and "code" in out:
        if str(out["tx"]) != str(out["code"]):
            raise ValueError("GLink SUM tx/code mismatch")
        out.pop("tx", None)
    return out


# SUM nested blob aliases — keep bus free of English factory/asn prose.
_SUM_MODE_ALIASES = {
    "self_sufficient": "ss",
    "external_proof": "ep",
    "oss": "ep",
    "monster": "ep",
    "external": "ep",
}
_SUM_FOCUS_ALIASES = {
    "command_builder": "cb",
    "factory": "fac",
    "peer": "fac",
    "general": "fac",
    "external_proof": "ep",
    "external": "ep",
    "oss": "ep",
}


def _compact_sum_shared(blob: dict[str, Any]) -> dict[str, Any]:
    """Collapse shared/team dict to sh{m,f,q} — drop factory prose."""
    out: dict[str, Any] = {}
    mode = str(blob.get("mode") or blob.get("m") or "").strip().lower()
    focus = str(blob.get("focus") or blob.get("f") or "").strip().lower()
    if mode:
        out["m"] = _SUM_MODE_ALIASES.get(mode, mode.replace(" ", "")[:8])
    if focus:
        out["f"] = _SUM_FOCUS_ALIASES.get(focus, focus.replace(" ", "")[:8])
    q_raw = blob.get("queue_open", blob.get("q"))
    if q_raw is not None:
        try:
            out["q"] = int(q_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("GLink SUM sh.q must be int") from exc
    return out


def _normalize_sum_nested(payload: dict[str, Any]) -> dict[str, Any]:
    """SUM: shared/team→sh{m,f,q}; english asn→ah+code — nested English hole closed."""
    out = dict(payload)
    for key in ("shared", "team"):
        raw = out.pop(key, None)
        if not isinstance(raw, dict):
            continue
        sh = _compact_sum_shared(raw)
        if not sh:
            continue
        existing = out.get("sh")
        if isinstance(existing, dict):
            merged = dict(existing)
            merged.update(sh)
            out["sh"] = merged
        else:
            out["sh"] = sh
    if "sh" in out:
        if not isinstance(out["sh"], dict):
            raise ValueError("GLink SUM sh must be object")
        out["sh"] = _compact_sum_shared(out["sh"])
        if not out["sh"]:
            out.pop("sh", None)
    if "asn" in out:
        asn = str(out.pop("asn") or "").strip()
        if asn:
            clipped = asn[:STR_VALUE_CAP]
            try:
                _reject_english_heavy(clipped)
                if "code" not in out:
                    out["code"] = clipped[:32]
            except ValueError:
                out["ah"] = path_hash(asn)
                if "code" not in out:
                    out["code"] = "asn"
    # Drop known bulky prose keys that are not in SUM schema.
    out.pop("factory", None)
    return out


def _normalize_pri_ttl(payload: dict[str, Any]) -> dict[str, Any]:
    """Optional pri (0-9) and ttl (seconds) — drop empty; reject out-of-range."""
    out = dict(payload)
    if "pri" in out:
        try:
            pri = int(out["pri"])
        except (TypeError, ValueError) as exc:
            raise ValueError("GLink pri must be int 0-9") from exc
        if pri < 0 or pri > PRI_MAX:
            raise ValueError(f"GLink pri must be 0-{PRI_MAX}")
        out["pri"] = pri
    if "ttl" in out:
        try:
            ttl = int(out["ttl"])
        except (TypeError, ValueError) as exc:
            raise ValueError("GLink ttl must be positive int seconds") from exc
        if ttl < 1 or ttl > TTL_MAX_SEC:
            raise ValueError(f"GLink ttl must be 1-{TTL_MAX_SEC}")
        out["ttl"] = ttl
    if "re" in out:
        re_val = str(out.get("re") or "").strip()
        if not re_val or " " in re_val or len(re_val) > 40:
            raise ValueError("GLink re must be short cid (no spaces)")
        out["re"] = re_val
    if "git" in out:
        git = str(out.get("git") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{7,40}", git):
            raise ValueError("GLink STAT git must be 7-40 hex")
        out["git"] = git
    return out


def _reject_req_self(from_role: str, to_role: str) -> None:
    """REQ must not target the posting role (use vault notes instead)."""
    fr = str(from_role or "").strip()
    to = str(to_role or "").strip()
    if fr and to and to != BROADCAST and to == fr:
        raise ValueError("GLink REQ cannot target self")


def _compact_paths_to_ph(payload: dict[str, Any]) -> dict[str, Any]:
    """DIFF/DONE: prefer short path hashes on the bus; drop full paths unless kp=1."""
    out = dict(payload)
    keep = out.pop("kp", None) in (1, True, "1")
    paths = out.get("paths")
    ph_raw = out.get("ph")
    if isinstance(paths, list) and paths and not keep:
        hashed = [path_hash(str(p)) for p in paths if str(p).strip()]
        if hashed:
            if ph_raw is None:
                out["ph"] = hashed
            elif isinstance(ph_raw, list):
                # Prefer explicit ph; still drop bulky paths.
                pass
            elif isinstance(ph_raw, str) and ph_raw.strip():
                out["ph"] = ph_raw.strip()
            else:
                out["ph"] = hashed
            out.pop("paths", None)
    elif isinstance(paths, list) and paths and keep:
        out["kp"] = 1
    if "ph" in out and not isinstance(out["ph"], (list, str)):
        raise ValueError("GLink ph must be str or list of short hashes")
    if "bref" in out and not isinstance(out["bref"], (str, list)):
        raise ValueError("GLink bref must be str or list")
    return out


def _normalize_one_ph(val: str) -> str:
    """Path-hash token: lowercase hex only (no path strings / prose)."""
    s = str(val or "").strip().lower()
    if not _PH_HEX_RE.fullmatch(s):
        raise ValueError("GLink ph must be short hex hash (use path_hash())")
    return s


def _normalize_one_bref(val: str) -> str:
    """Binary/artifact ref: short token (kind:id); reject English prose."""
    s = str(val or "").strip()
    if not s:
        raise ValueError("GLink bref entry empty")
    _reject_english_heavy(s)
    if " " in s or not _BREF_TOKEN_RE.fullmatch(s):
        raise ValueError("GLink bref must be short token (e.g. wt:peer-7), not prose")
    return s


def _normalize_ph_bref(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate ph hex + bref tokens after path compaction."""
    out = dict(payload)
    if "ph" in out:
        ph_raw = out["ph"]
        if isinstance(ph_raw, str):
            out["ph"] = _normalize_one_ph(ph_raw)
        elif isinstance(ph_raw, list):
            out["ph"] = [_normalize_one_ph(str(x)) for x in ph_raw if str(x).strip()]
            if not out["ph"]:
                out.pop("ph", None)
        else:
            raise ValueError("GLink ph must be str or list of short hashes")
    if "bref" in out:
        bref_raw = out["bref"]
        if isinstance(bref_raw, str):
            out["bref"] = _normalize_one_bref(bref_raw)
        elif isinstance(bref_raw, list):
            out["bref"] = [_normalize_one_bref(str(x)) for x in bref_raw if str(x).strip()]
            if not out["bref"]:
                out.pop("bref", None)
        else:
            raise ValueError("GLink bref must be str or list")
    return out


def build_diff_payload(
    paths: list[str] | None = None,
    *,
    ph: list[str] | str | None = None,
    bref: str | list[str] | None = None,
    cid: str | None = None,
    wt: str | None = None,
    kp: int | None = None,
) -> dict[str, Any]:
    """Compact DIFF payload — paths→ph by default (hot-path byte shrink)."""
    raw: dict[str, Any] = {}
    if paths:
        raw["paths"] = [str(p) for p in paths if str(p).strip()]
    if ph is not None:
        raw["ph"] = ph
    if bref is not None:
        raw["bref"] = bref
    if cid:
        raw["cid"] = str(cid).strip()
    if wt:
        raw["wt"] = str(wt).strip()
    if kp is not None:
        raw["kp"] = kp
    return validate_glink_payload(MSG_DIFF, raw)


def build_done_payload(
    ref: str,
    *,
    paths: list[str] | None = None,
    ph: list[str] | str | None = None,
    bref: str | list[str] | None = None,
    cid: str | None = None,
    kp: int | None = None,
) -> dict[str, Any]:
    """Compact DONE payload — prefer ph/bref/cid over long path strings."""
    raw: dict[str, Any] = {"ref": str(ref or "").strip()}
    if not raw["ref"]:
        raise ValueError("DONE requires ref")
    if paths:
        raw["paths"] = [str(p) for p in paths if str(p).strip()]
    if ph is not None:
        raw["ph"] = ph
    if bref is not None:
        raw["bref"] = bref
    if cid:
        raw["cid"] = str(cid).strip()
    if kp is not None:
        raw["kp"] = kp
    return validate_glink_payload(MSG_DONE, raw)


def validate_glink_payload(msg_type: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize + validate compact GLink payload; reject English-heavy blobs."""
    t = str(msg_type or "").upper()
    if t not in VALID_TYPES:
        raise ValueError(f"invalid GLink type {t!r}; use one of {sorted(VALID_TYPES)}")
    raw = dict(payload or {})
    if t == MSG_REQ:
        raw = _normalize_req_need(raw)
    if t == MSG_STAT:
        raw = _normalize_stat_op(raw)
    if t == MSG_SUM:
        raw = _normalize_sum_aliases(raw)
        raw = _normalize_sum_nested(raw)
    if t in (MSG_STAT, MSG_REQ, MSG_ASN, MSG_ACK):
        raw = _normalize_pri_ttl(raw)
    out = _ensure_cid(t, raw)
    if t == MSG_ASN:
        if not str(out.get("id") or "").strip():
            raise ValueError("ASN requires id")
        if not str(out.get("task") or "").strip():
            raise ValueError("ASN requires task")
    if t in (MSG_DIFF, MSG_DONE):
        out = _compact_paths_to_ph(out)
    out = _normalize_ph_bref(out)
    for key, val in list(out.items()):
        if isinstance(val, str):
            if key == "note":
                clipped = val[:NOTE_CAP]
                try:
                    _reject_english_heavy(clipped)
                    out[key] = clipped
                except ValueError:
                    # Cycle hooks may pass prose; collapse to code so bus stays compact.
                    out[key] = "prose"
            elif key == "task":
                # ASN.task is the one structured English slot — length-cap only.
                out[key] = val[:STR_VALUE_CAP]
            elif key in ("txt", "summary"):
                out[key] = val[:STR_VALUE_CAP]
                _reject_english_heavy(out[key])
            elif key not in (
                "ts",
                "due",
                "id",
                "ref",
                "cid",
                "need",
                "op",
                "st",
                "code",
                "reason",
                "wait",
                "wt",
                "ft",
                "re",
                "git",
                "ah",
                "ph",
                "bref",
            ):
                _reject_english_heavy(val)
            elif len(val) > STR_VALUE_CAP:
                out[key] = val[:STR_VALUE_CAP]
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str) and key in ("paths", "ph", "bref"):
                    if len(item) > STR_VALUE_CAP:
                        raise ValueError(f"GLink {key} entry too long")
                elif isinstance(item, str):
                    _reject_english_heavy(item)
    return out


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _now_ts() -> float:
    return time.time()


def agent_dir(role_id: str) -> Path:
    return AGENTS_DIR / role_id


def agent_state_path(role_id: str) -> Path:
    return agent_dir(role_id) / "state.json"


def agent_notes_path(role_id: str) -> Path:
    return agent_dir(role_id) / "notes.jsonl"


def comms_read_paths(role_id: str) -> list[str]:
    """Paths agents should read (relative to repo root where possible)."""
    rel_bus = _try_rel(BUS_PATH)
    rel_state = _try_rel(agent_state_path(role_id))
    return [p for p in (rel_bus, rel_state) if p]


def _try_rel(path: Path) -> str:
    s = str(path)
    if not s.startswith(_ROOT_STR):
        return s
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return s


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def default_state(role_id: str) -> dict[str, Any]:
    role = _role_by_id(role_id)
    return {
        "v": PROTOCOL_VERSION,
        "role_id": role_id,
        "job_title": role.job_title if role else role_id,
        "updated_at": _now_iso(),
        "tasks": {"todo": [], "done": []},
        "summary": "",
        "last_glink_ts": None,
    }


def _role_by_id(role_id: str) -> roles.AgentRole | None:
    for role in roles.load_roles():
        if role.id == role_id:
            return role
    return None


def ensure_agent(role_id: str) -> dict[str, Any]:
    path = agent_state_path(role_id)
    state = _read_json(path)
    if not state:
        state = default_state(role_id)
        _write_json(path, state)
    return state


def ensure_all_agents(pool: list[roles.AgentRole] | None = None) -> None:
    if not comms_enabled():
        return
    COMMS_DIR.mkdir(parents=True, exist_ok=True)
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    if not BUS_PATH.is_file():
        BUS_PATH.write_text("", encoding="utf-8")
    pool = pool or roles.load_roles()
    for role in pool[: roles.worker_pool_size()]:
        ensure_agent(role.id)


def _validate_message(msg: dict[str, Any]) -> dict[str, Any]:
    t = str(msg.get("t") or msg.get("type") or "").upper()
    if t not in VALID_TYPES:
        raise ValueError(f"invalid GLink type {t!r}; use one of {sorted(VALID_TYPES)}")
    f = str(msg.get("f") or msg.get("from") or "").strip()
    if not f:
        raise ValueError("GLink message requires f (from role_id)")
    to = str(msg.get("to") or BROADCAST).strip() or BROADCAST
    payload = msg.get("p") if "p" in msg else msg.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("GLink payload p must be a JSON object")
    payload = validate_glink_payload(t, payload)
    return {
        "v": PROTOCOL_VERSION,
        "t": t,
        "f": f,
        "to": to,
        "ts": str(msg.get("ts") or _now_iso()),
        "p": payload,
    }


def rotate_bus_if_needed(
    *,
    max_lines: int = BUS_ROTATE_MAX_LINES,
    keep: int = BUS_ROTATE_KEEP_LINES,
) -> int:
    """Archive older bus lines when count exceeds max_lines. Returns archived count.

    Keep floor of 50 applies only when max_lines >= 50 so test/small caps
    (e.g. max_lines=10, keep=5) are honored and archive_n never goes negative.
    """
    global _bus_count_cache
    if max_lines < 1:
        return 0
    count = _bus_message_count()
    if count <= max_lines:
        return 0
    # Floor 50 only when the cap allows it; never keep > max_lines.
    keep_floor = 50 if max_lines >= 50 else 1
    keep = max(keep_floor, min(int(keep), max_lines))
    try:
        lines = [ln for ln in BUS_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return 0
    if len(lines) <= max_lines:
        return 0
    archive_n = len(lines) - keep
    if archive_n <= 0:
        return 0
    archive_dir = COMMS_DIR / "bus-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = archive_dir / f"bus-{stamp}.jsonl"
    archive_path.write_text("\n".join(lines[:archive_n]) + "\n", encoding="utf-8")
    BUS_PATH.write_text("\n".join(lines[archive_n:]) + "\n", encoding="utf-8")
    _bus_count_cache = None
    return archive_n


def post_glink(
    *,
    msg_type: str,
    from_role: str,
    payload: dict[str, Any] | None = None,
    to_role: str = BROADCAST,
) -> dict[str, Any]:
    """Append one GLink line to the shared bus."""
    if not comms_enabled():
        return {}
    t = str(msg_type or "").upper()
    if t == MSG_REQ:
        _reject_req_self(from_role, to_role)
    ensure_agent(from_role)
    line = _validate_message(
        {
            "t": msg_type,
            "f": from_role,
            "to": to_role,
            "p": payload or {},
        }
    )
    COMMS_DIR.mkdir(parents=True, exist_ok=True)
    with BUS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, separators=(",", ":")) + "\n")
    rotate_bus_if_needed()
    state = ensure_agent(from_role)
    state["last_glink_ts"] = line["ts"]
    state["updated_at"] = _now_iso()
    _write_json(agent_state_path(from_role), state)
    _maybe_apply_rule_change_glink(from_role=from_role, msg_type=t, payload=line.get("p") or {})
    return line


def _maybe_apply_rule_change_glink(
    *, from_role: str, msg_type: str, payload: dict[str, Any]
) -> None:
    """Side-effect: rsusp/rchg REQ (and ACK with id) → rule-change registry (propose-only)."""
    try:
        import peer_rule_shutdown as rshut
    except Exception:  # noqa: BLE001
        return
    p = payload if isinstance(payload, dict) else {}
    if msg_type == MSG_REQ:
        need = str(p.get("need") or "")
        if need not in ("rsusp", "rchg"):
            return
        try:
            rshut.handle_glink_payload(from_role=from_role, payload=p)
            rshut.write_mirror()
        except Exception:  # noqa: BLE001 — bus must not fail on registry
            return
        return
    if msg_type == MSG_ACK:
        args = p.get("args") if isinstance(p.get("args"), dict) else {}
        item_id = str(p.get("id") or args.get("id") or "").strip()
        if not item_id.startswith("rs-"):
            return
        try:
            rshut.ack(item_id=item_id, from_role=from_role)
            rshut.write_mirror()
        except Exception:  # noqa: BLE001
            return


def materialize_role_board(*, bus_limit: int = 80, limit_roles: int = 16) -> dict[str, dict[str, Any]]:
    """Last STAT per role from bus tail — compact board for vault/dashboard."""
    board: dict[str, dict[str, Any]] = {}
    for msg in read_bus(limit=bus_limit):
        if msg.get("t") != MSG_STAT:
            continue
        role = str(msg.get("f") or "").strip()
        if not role:
            continue
        p = msg.get("p") if isinstance(msg.get("p"), dict) else {}
        entry: dict[str, Any] = {"st": p.get("st"), "op": p.get("op"), "ts": msg.get("ts")}
        if "vfy" in p:
            entry["vfy"] = p.get("vfy")
        if "pri" in p:
            entry["pri"] = p.get("pri")
        board[role] = entry
    if limit_roles > 0 and len(board) > limit_roles:
        # Keep most recently seen roles (last overwrite wins; trim by ts desc).
        ranked = sorted(
            board.items(),
            key=lambda kv: str(kv[1].get("ts") or ""),
            reverse=True,
        )
        board = dict(ranked[:limit_roles])
    return board


def materialize_open_reqs_mcp(*, bus_limit: int = 80) -> list[dict[str, Any]]:
    """Open REQ rows (incl. mcp:*) without a matching ACK cid/ref."""
    reqs: list[dict[str, Any]] = []
    acked: set[str] = set()
    for msg in read_bus(limit=bus_limit):
        t = msg.get("t")
        p = msg.get("p") if isinstance(msg.get("p"), dict) else {}
        if t == MSG_ACK:
            cid = str(p.get("cid") or p.get("ref") or "").strip()
            if cid:
                acked.add(cid)
        elif t == MSG_REQ:
            reqs.append(msg)
    open_rows: list[dict[str, Any]] = []
    for msg in reqs:
        p = msg.get("p") if isinstance(msg.get("p"), dict) else {}
        cid = str(p.get("cid") or "").strip()
        if not cid or cid in acked:
            continue
        row: dict[str, Any] = {
            "f": msg.get("f"),
            "to": msg.get("to"),
            "need": p.get("need"),
            "cid": cid,
        }
        if p.get("mcp"):
            row["mcp"] = p.get("mcp")
        if p.get("ns"):
            row["ns"] = p.get("ns")
        if "pri" in p:
            row["pri"] = p.get("pri")
        open_rows.append(row)
    return open_rows


# A2A-style task cards — map GLink REQ/ACK/ASN to structured delegation (no PROTOCOL bump).
A2A_CARD_REQUIRED = ("id", "from", "to", "task", "cid")
A2A_CARD_ST = frozenset({"req", "ack", "asn"})


def build_a2a_task_card(
    *,
    id: str,
    from_role: str,
    to_role: str,
    task: str,
    cid: str,
    eta: int | None = None,
    st: str | None = None,
) -> dict[str, Any]:
    """Pure builder for an A2A-style task card (id/from/to/task/cid + optional eta/st)."""
    card: dict[str, Any] = {
        "id": str(id or "").strip(),
        "from": str(from_role or "").strip(),
        "to": str(to_role or "").strip() or BROADCAST,
        "task": str(task or "").strip(),
        "cid": str(cid or "").strip(),
    }
    if eta is not None:
        card["eta"] = eta
    if st is not None:
        card["st"] = str(st).strip().lower()
    return validate_a2a_task_card(card)


def validate_a2a_task_card(card: dict[str, Any] | None) -> dict[str, Any]:
    """Validate A2A task card; require id, from, to, task, cid; optional eta (seconds)."""
    if not isinstance(card, dict):
        raise ValueError("A2A card must be object")
    out: dict[str, Any] = {}
    for key in A2A_CARD_REQUIRED:
        val = str(card.get(key) or "").strip()
        if not val:
            raise ValueError(f"A2A card requires {key}")
        if key == "task":
            out[key] = val[:STR_VALUE_CAP]
        elif key in ("id", "cid") and (" " in val or len(val) > 64):
            raise ValueError(f"A2A card {key} must be short id (no spaces)")
        else:
            out[key] = val
    if "eta" in card and card.get("eta") is not None:
        try:
            eta = int(card["eta"])
        except (TypeError, ValueError) as exc:
            raise ValueError("A2A card eta must be int seconds") from exc
        if eta < 1 or eta > TTL_MAX_SEC:
            raise ValueError(f"A2A card eta must be 1-{TTL_MAX_SEC}")
        out["eta"] = eta
    st = str(card.get("st") or "").strip().lower()
    if st:
        if st not in A2A_CARD_ST:
            raise ValueError(f"A2A card st must be one of {sorted(A2A_CARD_ST)}")
        out["st"] = st
    if "ok" in card and card.get("ok") is not None:
        try:
            out["ok"] = 1 if int(card["ok"]) else 0
        except (TypeError, ValueError) as exc:
            raise ValueError("A2A card ok must be 0|1") from exc
    if "need" in card and card.get("need") is not None:
        need = str(card.get("need") or "").strip()
        if need:
            out["need"] = need[:64]
    return out


def a2a_task_card_from_glink(msg: dict[str, Any] | None) -> dict[str, Any]:
    """Map one GLink bus envelope (REQ/ACK/ASN) → A2A task card for cross-repo agents."""
    if not isinstance(msg, dict):
        raise ValueError("GLink message must be object")
    t = str(msg.get("t") or "").upper()
    p = msg.get("p") if isinstance(msg.get("p"), dict) else {}
    f = str(msg.get("f") or "").strip()
    to = str(msg.get("to") or BROADCAST).strip() or BROADCAST
    if t == MSG_REQ:
        # Ensure cid/need via existing validators when raw payload is incomplete.
        p = validate_glink_payload(MSG_REQ, dict(p))
        cid = str(p.get("cid") or "").strip()
        need = str(p.get("need") or "").strip()
        card: dict[str, Any] = {
            "id": cid,
            "from": f,
            "to": to,
            "task": need,
            "cid": cid,
            "st": "req",
            "need": need,
        }
        if "ttl" in p:
            card["eta"] = p["ttl"]
        return validate_a2a_task_card(card)
    if t == MSG_ACK:
        p = validate_glink_payload(MSG_ACK, dict(p))
        cid = str(p.get("cid") or p.get("ref") or "").strip()
        card = {
            "id": cid,
            "from": f,
            "to": to,
            "task": "ack",
            "cid": cid,
            "st": "ack",
        }
        if "ok" in p:
            card["ok"] = p["ok"]
        return validate_a2a_task_card(card)
    if t == MSG_ASN:
        p = validate_glink_payload(MSG_ASN, dict(p))
        asn_id = str(p.get("id") or "").strip()
        card = {
            "id": asn_id,
            "from": f,
            "to": to,
            "task": str(p.get("task") or "").strip(),
            "cid": asn_id,
            "st": "asn",
        }
        if p.get("eta_sec") is not None:
            card["eta"] = p["eta_sec"]
        return validate_a2a_task_card(card)
    raise ValueError(f"A2A card maps REQ/ACK/ASN only, not {t!r}")


def materialize_a2a_open_cards(*, bus_limit: int = 80) -> list[dict[str, Any]]:
    """Open (unacked) REQ rows as A2A task cards — structured cross-repo delegation view."""
    cards: list[dict[str, Any]] = []
    for row in materialize_open_reqs_mcp(bus_limit=bus_limit):
        cid = str(row.get("cid") or "").strip()
        need = str(row.get("need") or "").strip()
        if not cid or not need:
            continue
        cards.append(
            validate_a2a_task_card(
                {
                    "id": cid,
                    "from": str(row.get("f") or "").strip(),
                    "to": str(row.get("to") or BROADCAST).strip() or BROADCAST,
                    "task": need,
                    "cid": cid,
                    "st": "req",
                    "need": need,
                }
            )
        )
    return cards


def _read_bus_tail_raw(*, limit: int) -> list[str]:
    """Last N non-empty bus lines without parsing the full jsonl into memory."""
    if not BUS_PATH.is_file():
        return []
    lines = auto.tail_text_lines(BUS_PATH, max(limit * 2, limit + 4))
    return [ln.strip() for ln in lines if ln.strip()][-limit:]


_bus_count_cache: tuple[int, int, int] | None = None  # mtime_ns, size, count


def _bus_message_count() -> int:
    global _bus_count_cache
    if not BUS_PATH.is_file():
        return 0
    try:
        st = BUS_PATH.stat()
        witness = (st.st_mtime_ns, st.st_size)
    except OSError:
        return 0
    if _bus_count_cache and _bus_count_cache[0] == witness[0] and _bus_count_cache[1] == witness[1]:
        return _bus_count_cache[2]
    try:
        count = 0
        with BUS_PATH.open(encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    count += 1
    except OSError:
        count = 0
    _bus_count_cache = (witness[0], witness[1], count)
    return count


def read_bus(
    *,
    limit: int = 40,
    since_ts: float | None = None,
    for_role: str | None = None,
) -> list[dict[str, Any]]:
    if not BUS_PATH.is_file():
        return []
    if since_ts is None and for_role is None:
        raw_lines = _read_bus_tail_raw(limit=limit)
        out: list[dict[str, Any]] = []
        for raw in raw_lines:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                out.append(msg)
        return out
    out: list[dict[str, Any]] = []
    try:
        lines = BUS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        if since_ts is not None:
            try:
                ts_str = str(msg.get("ts") or "")
                # ISO compare via parsed time if possible
                msg_ts = datetime.fromisoformat(ts_str).timestamp() if ts_str else 0.0
            except (TypeError, ValueError):
                msg_ts = 0.0
            if msg_ts < since_ts:
                continue
        to = str(msg.get("to") or BROADCAST)
        if for_role and to not in (BROADCAST, for_role):
            continue
        out.append(msg)
    return out[-limit:]


def update_tasks(
    role_id: str,
    *,
    todo: list[str] | None = None,
    done: list[str] | None = None,
    append_todo: str | None = None,
    append_done: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    state = ensure_agent(role_id)
    tasks = state.setdefault("tasks", {"todo": [], "done": []})
    if todo is not None:
        tasks["todo"] = list(todo)
    if done is not None:
        tasks["done"] = list(done)
    if append_todo:
        tasks.setdefault("todo", [])
        if append_todo not in tasks["todo"]:
            tasks["todo"].append(append_todo)
    if append_done:
        tasks.setdefault("done", [])
        if append_done not in tasks["done"]:
            tasks["done"].append(append_done)
        tasks.setdefault("todo", [])
        tasks["todo"] = [t for t in tasks["todo"] if t != append_done]
    if summary is not None:
        state["summary"] = summary[:SUMMARY_WRITE_CAP]
    state["updated_at"] = _now_iso()
    _write_json(agent_state_path(role_id), state)
    return state


def append_note(role_id: str, body: str, *, kind: str = "note") -> None:
    ensure_agent(role_id)
    line = json.dumps(
        {"ts": _now_iso(), "kind": kind, "body": body[:SUMMARY_WRITE_CAP]},
        separators=(",", ":"),
    )
    path = agent_notes_path(role_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def record_cycle_glink(
    *,
    role_id: str | None,
    verify_ok: bool,
    noop: bool,
    note: str = "",
    failure_type: str | None = None,
) -> None:
    """Hook from peer_transcript after each cycle.

    ``failure_type=deferred`` is a soft-skip — emit IDLE + ft (not BLOCK) so Hot
    memory hydrate keeps Soft-skip instead of a verify FAIL storm.
    """
    if not comms_enabled() or not role_id:
        return
    ft = str(failure_type or "").strip() or None
    deferred = ft == "deferred"
    if verify_ok and not noop:
        st = "DONE"
    elif deferred:
        st = "IDLE"
    elif not verify_ok:
        st = "BLOCK"
    else:
        st = "IDLE"
    payload: dict[str, Any] = {
        "st": st,
        "op": "cycle",
        "vfy": 1 if verify_ok else 0,
        "noop": 1 if noop else 0,
        "note": (note or "")[:NOTE_CAP],
    }
    if ft:
        payload["ft"] = ft
    post_glink(
        msg_type=MSG_STAT,
        from_role=role_id,
        payload=payload,
    )


def _prompt_lean_payload(msg: dict[str, Any]) -> dict[str, Any]:
    """Prompt-only payload lean — disk bus unchanged."""
    p = msg.get("p") if isinstance(msg.get("p"), dict) else {}
    out = dict(p)
    t = str(msg.get("t") or "")
    if out.get("ph") and "paths" in out:
        out.pop("paths", None)
    if t == MSG_SUM and (out.get("code") or out.get("sh") or out.get("ah") or out.get("learn")):
        # Prefer codes; always drop bulky English learn/paths on tip.
        if out.get("learn") and not (out.get("code") or out.get("sh") or out.get("ah")):
            out["code"] = "learn"
        out.pop("learn", None)
        out.pop("paths", None)
        out.pop("cycle", None)
        out.pop("cycle_id", None)
    if t == MSG_DONE:
        if out.get("ph") and "paths" in out:
            out.pop("paths", None)
        out.pop("expected_vs_actual", None)
        out.pop("cycle_id", None)
        # Prefer ref over redundant st/op on DONE tip.
        if out.get("ref"):
            out.pop("st", None)
    if t == MSG_STAT and out.get("st") in ("DONE", "IDLE") and "note" in out:
        out.pop("note", None)
    if t == MSG_STAT and out.get("st") == "WIP" and out.get("op"):
        out.pop("st", None)
    return out


def _filter_duplicate_stat_op(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prompt tip: keep newest STAT WIP per (from, op); drop WIP after same-op DONE/BLOCK/FAIL (IDLE does not supersede).

    Parallel dispatch posts many identical ``hand_out`` WIP frames. IDLE does not supersede WIP. Disk JSONL unchanged.
    """
    if not msgs:
        return msgs
    seen_wip: set[tuple[Any, Any]] = set()
    terminal_op: set[tuple[Any, Any]] = set()  # (f, op) after IDLE/DONE/BLOCK/FAIL
    out: list[dict[str, Any]] = []
    for msg in reversed(msgs):
        payload = msg.get("p") if isinstance(msg.get("p"), dict) else {}
        t = msg.get("t")
        f = msg.get("f")
        st = payload.get("st")
        op = payload.get("op")
        if t == MSG_STAT and st in ("DONE", "BLOCK", "FAIL") and op:
            terminal_op.add((f, op))
            out.append(msg)
            continue
        if t == MSG_STAT and st == "WIP" and op:
            key = (f, op)
            if key in terminal_op or key in seen_wip:
                continue
            seen_wip.add(key)
            out.append(msg)
            continue
        out.append(msg)
    out.reverse()
    return out



def _filter_prompt_bus_msgs(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop superseded tip noise (prompt-only): dup DONE + WIP after DONE/BLOCK/FAIL.

    IDLE does not supersede WIP (tip_wip_dedupe keeps newest WIP alongside IDLE).
    """
    msgs = _filter_duplicate_stat_op(msgs)
    if not msgs:
        return msgs
    seen_done: set[tuple[str, str]] = set()
    terminal_ops: set[tuple[str, str]] = set()
    keep_rev: list[dict[str, Any]] = []
    for msg in reversed(msgs):
        t = str(msg.get("t") or "")
        f = str(msg.get("f") or "")
        p = msg.get("p") if isinstance(msg.get("p"), dict) else {}
        if t == MSG_DONE:
            ref = str(p.get("ref") or "").strip()
            key = (f, ref)
            if ref and key in seen_done:
                continue
            if ref:
                seen_done.add(key)
            op = str(p.get("op") or "").strip()
            if op:
                terminal_ops.add((f, op))
            terminal_ops.add((f, ""))  # DONE from f supersedes all WIP from f
            keep_rev.append(msg)
            continue
        if t == MSG_STAT:
            st = str(p.get("st") or "").strip()
            op = str(p.get("op") or "").strip()
            # IDLE deliberately omitted — tip keeps newest WIP alongside IDLE.
            if st in ("DONE", "BLOCK", "FAIL"):
                if op:
                    terminal_ops.add((f, op))
                terminal_ops.add((f, ""))
                keep_rev.append(msg)
                continue
            if st == "WIP" and ((f, op) in terminal_ops or (f, "") in terminal_ops):
                continue
            keep_rev.append(msg)
            continue
        if t == MSG_BLOCK:
            terminal_ops.add((f, ""))
            keep_rev.append(msg)
            continue
        keep_rev.append(msg)
    keep_rev.reverse()
    return keep_rev



def _format_msg_line(msg: dict[str, Any], *, line_cap: int | None = None) -> str:
    p = json.dumps(_prompt_lean_payload(msg), separators=(",", ":"))
    to = msg.get("to") or BROADCAST
    line = f"{msg.get('ts')} {msg.get('t')} {msg.get('f')}→{to} {p}"
    if line_cap is not None and line_cap > 0 and len(line) > line_cap:
        return line[: max(0, line_cap - 1)] + "…"
    return line


def format_glink_protocol_doc() -> str:
    """Compact protocol card for prompt injection (paths are short labels, not abs)."""
    return (
        "## GLink (codes/ph — no English on bus)\n\n"
        "Append one JSONL to `agent-comms/bus.jsonl`; vault `agents/{role_id}/state.json`.\n"
        'Shape: `{"v":1,"t":"STAT","f":"role","to":"*","ts":"ISO","p":{…}}`\n\n'
        "| t | p |\n|---|---|\n"
        f"| {MSG_STAT} | st=WIP\\|DONE\\|BLOCK\\|IDLE, op |\n"
        f"| {MSG_DONE} | ref, ph[] |\n"
        f"| {MSG_REQ} | need=code\\|mcp:<tool>, cid |\n"
        f"| {MSG_ACK} | cid\\|ref |\n"
        f"| {MSG_BLOCK} | reason, wait? |\n"
        f"| {MSG_DIFF} | ph[] (kp=1 keep paths) |\n"
        f"| {MSG_SUM} | code\\|sh{{m,f,q}}\\|ah |\n"
        f"| {MSG_ASN} | id, task, eta, when, due |\n"
    )


def format_bus_block(
    *,
    for_role: str | None = None,
    limit: int = BUS_PROMPT_LIMIT,
    line_cap: int = BUS_PROMPT_LINE_CAP,
) -> str:
    """Prompt bus tip — compact lines + superseded/dup-WIP filter (disk JSONL unchanged)."""
    if not comms_enabled():
        return ""
    msgs = _filter_prompt_bus_msgs(read_bus(limit=limit, for_role=for_role))
    if not msgs:
        return "## GLink bus (empty)\n\nPost STAT/DIFF after you change state.\n"
    lines = ["## GLink bus", ""]
    for msg in msgs:
        lines.append(f"- `{_format_msg_line(msg, line_cap=line_cap)}`")
    lines.append("")
    return "\n".join(lines)


def _prompt_vault_next_tip(item: str) -> str:
    """Prompt-only vault tip: ASN id + w=/e= codes; drop English task prose."""
    raw = str(item or "").strip()
    if not raw:
        return ""
    m = _ASN_BRACKET_RE.match(raw)
    if m:
        body = m.group(1)
        body = re.sub(r"\s*when=", " w=", body, count=1, flags=re.IGNORECASE)
        body = re.sub(r"\s*eta=", " e=", body, count=1, flags=re.IGNORECASE)
        tip = f"[{body}]"
        return tip[:VAULT_NEXT_TIP_CAP]
    return "·"


def _prompt_vault_summary(
    summary: str,
    board_entry: dict[str, Any] | None,
    *,
    todo_n: int = 0,
) -> str:
    """Prompt-only: role_board STAT codes beat English vault summary (disk full)."""
    cap = VAULT_SUMMARY_PROMPT_CAP
    if isinstance(board_entry, dict):
        st = str(board_entry.get("st") or "").strip().upper()
        op = str(board_entry.get("op") or "").strip()
        if st == "WIP" and op:
            return f"WIP {op}"[:cap]
        if st == "BLOCK":
            base = f"BLOCK {op}".strip() if op else "BLOCK"
            return f"{base} n={todo_n}"[:cap]
        if st:
            return (f"{st} {op}".strip() if op else st)[:cap]
    s = str(summary or "").strip()
    if not s:
        return ""
    m = _VAULT_ST_RE.match(s)
    if m:
        tip = m.group(1).upper()
        if m.group(2):
            tip = f"{tip} {m.group(2)[:16]}"
        return tip[:cap]
    parts: list[str] = []
    am = _VAULT_ACTIVE_RE.search(s)
    dm = _VAULT_DRIFT_RE.search(s)
    if am:
        parts.append(f"a={am.group(1)}")
    if dm:
        parts.append(f"d={dm.group(1)}")
    if parts:
        return " ".join(parts)[:cap]
    return ""


def format_vault_block(
    role_id: str,
    *,
    board: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Prompt vault card — no abs state paths; board codes over English summary."""
    if not comms_enabled():
        return ""
    state = _read_json(agent_state_path(role_id))
    if not state:
        return ""
    todo = (state.get("tasks") or {}).get("todo") or []
    done = (state.get("tasks") or {}).get("done") or []
    summary = str(state.get("summary") or "").strip()
    entry = None
    if isinstance(board, dict):
        raw = board.get(role_id)
        entry = raw if isinstance(raw, dict) else None
    tip_sum = _prompt_vault_summary(summary, entry, todo_n=len(todo))
    if not todo and not done:
        return ""
    lines = [
        f"### `{role_id}`",
        f"- n: {len(todo)}/{len(done)}",
    ]
    if tip_sum:
        lines.append(f"- s: {tip_sum}")
    tips = [_prompt_vault_next_tip(t) for t in todo[:3]]
    tips = [t for t in tips if t]
    if tips:
        lines.append("- next: " + "; ".join(tips))
    return "\n".join(lines)


def format_team_vaults(limit_roles: int = 8) -> str:
    if not comms_enabled():
        return ""
    pool = roles.load_roles()[:limit_roles]
    board = materialize_role_board(limit_roles=max(limit_roles, 16))
    blocks = [format_vault_block(r.id, board=board) for r in pool]
    blocks = [b for b in blocks if b]
    if not blocks:
        return ""
    return "## Agent vaults\n\n" + "\n\n".join(blocks) + "\n"


def format_prompt_block(*, for_role: str | None = None) -> str:
    if not comms_enabled():
        return ""
    parts = [
        format_glink_protocol_doc(),
        "",
        format_bus_block(for_role=for_role),
        format_team_vaults(),
    ]
    return "\n".join(p for p in parts if p).strip() + "\n"



def status_dict() -> dict[str, Any]:
    pool = roles.load_roles()[: roles.worker_pool_size()]
    bus_count = _bus_message_count()
    vaults: list[dict[str, Any]] = []
    for role in pool:
        st = _read_json(agent_state_path(role.id))
        tasks = st.get("tasks") if isinstance(st.get("tasks"), dict) else {}
        vaults.append(
            {
                "role_id": role.id,
                "job_title": role.job_title,
                "todo": len(tasks.get("todo") or []),
                "done": len(tasks.get("done") or []),
                "summary_len": len(str(st.get("summary") or "")),
                "last_glink_ts": st.get("last_glink_ts"),
            }
        )
    recent = read_bus(limit=8)
    return {
        "enabled": comms_enabled(),
        "comms_dir": _COMMS_DIR_STR,
        "bus_path": _BUS_PATH_STR,
        "bus_messages": bus_count,
        "schema": glink_schema(),
        "agents": vaults,
        "recent_bus": recent,
    }


def cmd_status() -> int:
    st = status_dict()
    print(f"GLink enabled: {st['enabled']}")
    print(f"comms dir: {st['comms_dir']}")
    print(f"bus messages: {st['bus_messages']}")
    print()
    print("| Role | todo | done | last GLink |")
    print("|------|------|------|------------|")
    for v in st["agents"]:
        print(
            f"| {v['job_title']} | {v['todo']} | {v['done']} | {v.get('last_glink_ts') or '—'} |"
        )
    if st["recent_bus"]:
        print("\nRecent bus:")
        for msg in st["recent_bus"]:
            print(f"  {_format_msg_line(msg)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GLink agent comms (shared bus + per-agent vaults)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--init", action="store_true", help="Create bus + agent vaults")
    parser.add_argument("--bus", action="store_true", help="Print recent bus lines")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--post", action="store_true", help="Append GLink message to bus")
    parser.add_argument("--from", dest="from_role", metavar="ROLE")
    parser.add_argument("--type", dest="msg_type", metavar="TYPE")
    parser.add_argument("--to", dest="to_role", default=BROADCAST)
    parser.add_argument("--payload", default="{}", help="JSON object for p")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.init:
        ensure_all_agents()
        print(f"initialized GLink under {COMMS_DIR}")
        return 0
    if args.post:
        if not args.from_role or not args.msg_type:
            print("--post requires --from ROLE --type TYPE", file=sys.stderr)
            return 1
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(f"invalid --payload JSON: {exc}", file=sys.stderr)
            return 1
        line = post_glink(
            msg_type=args.msg_type,
            from_role=args.from_role,
            to_role=args.to_role,
            payload=payload if isinstance(payload, dict) else {},
        )
        print(json.dumps(line, indent=2))
        return 0
    if args.bus:
        for msg in read_bus(limit=args.limit):
            print(_format_msg_line(msg))
        return 0
    if args.json:
        print(json.dumps(status_dict(), indent=2))
        return 0
    if args.status:
        return cmd_status()
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
