# Version lives in its own module-level tuple so it's available at
# import time even when Blender's 4.2+ extension loader rewrites the
# source to strip bl_info (the manifest supersedes bl_info under the
# Extensions platform). Use ADDON_VERSION, never `bl_info['version']`,
# anywhere outside this header block.
ADDON_VERSION = (9, 13, 1)

bl_info = {
    "name": "Blender Buddy",
    "author": "CGMatter",
    "version": ADDON_VERSION,
    "blender": (5, 1, 0),
    "location": "3D Viewport > Sidebar (N) > Buddy",
    "description": "Ask questions, run code, find online references, and more.",
    "category": "Development",
}

import bpy
import os
import re
import sys
import json
import time
import shutil
import zipfile
import tarfile
import platform
import textwrap
import threading
import subprocess
import base64
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import html as _htmllib
import bpy.utils.previews
from bpy.props import (
    StringProperty, PointerProperty, BoolProperty,
    IntProperty, EnumProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, AddonPreferences

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADDON_ID = __name__  # derived from filename; kept stable so prefs survive

# Two local models, one process. Text is the default; vision is lazy-
# downloaded on first use. The llama-server can only host one of them at a
# time because they have different architectures, so we stop + restart the
# server whenever the user switches modes (see start_server(mode=…)).

# Three text-model quant variants (low/medium/high intelligence). All
# three are Qwen3-30B-A3B-Instruct-2507 from the same unsloth repo — MoE
# with ~3.3B active params out of 30B. Same weights, different quantization
# → pick the one your RAM can hold. Medium is the default (best quality-
# for-size).
# Switched from Qwen3-Coder-30B-A3B-Instruct to Instruct-2507 because
# (a) Coder GGUFs at Q4/Q5 have a known tokenizer bug that conflates `_`
# and `*`, mangling bpy identifiers like __init__ / bl_idname; (b)
# Instruct-2507 emits the standard Hermes JSON tool-call format, which
# llama-server + --jinja handles more reliably than Coder's custom XML;
# (c) the api_index.jsonl RAG already neutralizes Coder's code-
# memorization edge. Same 30.5B-total / 3.3B-active MoE architecture,
# same GGUF sizes, same decode speed — the swap is effectively free.
# Source weights remain Apache-2.0 Qwen; attribution lives on the HF
# repo's model card.
# Primary source: Unsloth's public GGUF repos, pinned to specific
# commits so re-quantizations on `main` can't silently change file
# bytes / invalidate SHA-256s. Each `resolve/<sha>/...` URL is
# immutable (commit refs LFS blobs by hash), and Unsloth's repos are
# aggressively cached at HF's edge so downloads are much faster than
# a cold self-hosted mirror.
#
# Fallback: our own HF mirror (r568lp2/blenderbuddy). Download code
# tries the primary first and only falls back on network failure or
# SHA mismatch — meant as insurance if Unsloth's repo is ever deleted
# or the pinned commit is GC'd (rare). The mirror must contain files
# matching the SHAs below for the fallback to actually succeed — on
# a fresh Instruct-2507 swap, re-upload each GGUF to the mirror before
# shipping.
#
# To bump a pin: pick a new commit SHA from the repo's /commits/main
# page, grab each file's SHA-256 from its "Git LFS Details" section,
# update the constants below, ship a Buddy release.
_UNSLOTH_INSTRUCT_COMMIT = "eea7b2be5805a5f151f8847ede8e5f9a9284bf77"
_UNSLOTH_INSTRUCT_BASE = (
    "https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/"
    f"resolve/{_UNSLOTH_INSTRUCT_COMMIT}/"
)
# VL repo commits differ per file — the Q4_K_M and the mmproj were
# uploaded in different commits. Pin each to its own SHA.
_UNSLOTH_VL_Q4_COMMIT     = "c211810e6252bfaeeee977d5ac83e9c0e5c381c8"
_UNSLOTH_VL_MMPROJ_COMMIT = "e9986c66a0218c1182f36be627c4910d6290d3b1"
_UNSLOTH_VL_Q4_BASE = (
    "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/"
    f"resolve/{_UNSLOTH_VL_Q4_COMMIT}/"
)
_UNSLOTH_VL_MMPROJ_BASE = (
    "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/"
    f"resolve/{_UNSLOTH_VL_MMPROJ_COMMIT}/"
)
_MIRROR_BASE = "https://huggingface.co/r568lp2/blenderbuddy/resolve/main/"

# SHA-256 verification values per GGUF. Fetched from the "Git LFS
# Details" block on each file's HF page. Refresh with:
#     print(_head_sha256(TEXT_MODEL_VARIANTS['MEDIUM']['url']))
TEXT_MODEL_VARIANTS = {
    'LOW': {
        "key":          "LOW",
        "url":          _UNSLOTH_INSTRUCT_BASE + "Qwen3-30B-A3B-Instruct-2507-UD-IQ1_M.gguf",
        "fallback_url": _MIRROR_BASE           + "Qwen3-30B-A3B-Instruct-2507-UD-IQ1_M.gguf",
        "filename":     "Qwen3-30B-A3B-Instruct-2507-UD-IQ1_M.gguf",
        "label":        "Low",
        "quant":        "UD-IQ1_M",
        "size_tag":     "~9.7 GB · 16 GB RAM",
        "sha256":       "d527a854db2a1582a3ce746a17b1f42d860334ece18d385ede9e2e395058b39e",
    },
    'MEDIUM': {
        "key":          "MEDIUM",
        "url":          _UNSLOTH_INSTRUCT_BASE + "Qwen3-30B-A3B-Instruct-2507-Q3_K_M.gguf",
        "fallback_url": _MIRROR_BASE           + "Qwen3-30B-A3B-Instruct-2507-Q3_K_M.gguf",
        "filename":     "Qwen3-30B-A3B-Instruct-2507-Q3_K_M.gguf",
        "label":        "Medium",
        "quant":        "Q3_K_M",
        "size_tag":     "~14.7 GB · 24 GB RAM",
        "sha256":       "e145c9d2f5d11c9583eb099aa75100b7ab943e77d5240c9a2cd936f81c89ef43",
    },
    'HIGH': {
        "key":          "HIGH",
        "url":          _UNSLOTH_INSTRUCT_BASE + "Qwen3-30B-A3B-Instruct-2507-Q5_K_M.gguf",
        "fallback_url": _MIRROR_BASE           + "Qwen3-30B-A3B-Instruct-2507-Q5_K_M.gguf",
        "filename":     "Qwen3-30B-A3B-Instruct-2507-Q5_K_M.gguf",
        "label":        "High",
        "quant":        "Q5_K_M",
        "size_tag":     "~21.7 GB · 32 GB RAM",
        "sha256":       "74cf6e525344a184e59f8dbd1d18e59587f1a03eaff66f6b1fbd0ee3a53a3d68",
    },
}
TEXT_MODEL_ORDER = ('LOW', 'MEDIUM', 'HIGH')
TEXT_MODEL_DEFAULT_KEY = 'MEDIUM'

VISION_MODEL = {
    # Qwen3-VL-8B-Instruct — direct successor to Qwen2.5-VL. Explicitly
    # tuned for "visual agent / GUI understanding" with native point +
    # bounding-box grounding. Q4_K_M is 4.68 GB + mmproj 1.08 GB.
    "url":          _UNSLOTH_VL_Q4_BASE + "Qwen3-VL-8B-Instruct-Q4_K_M.gguf",
    "fallback_url": _MIRROR_BASE        + "Qwen3-VL-8B-Instruct-Q4_K_M.gguf",
    "filename":     "Qwen3-VL-8B-Instruct-Q4_K_M.gguf",
    # mmproj: maps image embeddings into the LM's token space. Stored
    # locally under a model-specific name so an upgrade from a prior VL
    # mmproj doesn't silently reuse the old file. Upstream Unsloth names
    # it plainly `mmproj-F16.gguf` (no model prefix), while our mirror
    # stores it under the verbose name — so the two URLs differ on the
    # last path segment even though the bytes are identical.
    "mmproj_url":          _UNSLOTH_VL_MMPROJ_BASE + "mmproj-F16.gguf",
    "mmproj_fallback_url": _MIRROR_BASE            + "mmproj-Qwen3-VL-8B-F16.gguf",
    "mmproj_filename":     "mmproj-Qwen3-VL-8B-F16.gguf",
    # User-visible label in preferences. The underlying model name is
    # kept out of the UI on purpose — "Vision model" is what matters
    # for a beginner choosing whether to download it.
    "label":    "Vision model (screenshots)",
    "sha256":        "108e7ff92b78eefd3db4741885104acba514255c11b617d3c7b197a5f46efe89",
    "mmproj_sha256": "d406d03ebabefdef86a2c86bf0c1b65f9e046f7a81c218f25de4931b46a07fc4",
}

# Pinned llama.cpp release. llama.cpp ships roughly daily, and breaking
# changes (flag renames, tool-call parsing shifts, vision regressions)
# land without fanfare — pinning a specific tested tag means every user
# on a given Buddy version gets the same binary. To refresh: pick a tag
# from https://github.com/ggml-org/llama.cpp/releases that's a few days
# old (long enough for immediate regressions to surface), verify Buddy
# still works against it, and bump the value below in a new Buddy
# release.
LLAMACPP_PINNED_TAG = "b8830"  # 2026-04-17
LLAMACPP_TAG_API    = "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/"

# Inference defaults — hardcoded in v9.2. The old Quality / Creativity
# preset knobs were scrapped: one good setting beats three mediocre ones,
# and the model is smart enough not to need per-question tuning.
DEFAULT_MAX_TOKENS   = 1024
# Temperature auto-switches on Action Mode so the user doesn't have to:
# - Action Mode ON  (code gen)   → CODE  = 0.2: sharp, deterministic;
#   top_k=20 does most of the truncation, T just picks among top few.
# - Action Mode OFF (UI / prose) → PROSE = 0.35: reads as natural
#   writing; operator names are still safe because search_api is a
#   hard requirement for anything the model isn't sure of.
# Bumped up from the old flat 0.1 — at T=0.1 with no top_k, Qwen3 MoE
# can get into greedy-repetition loops because near-greedy sampling
# reinforces the same expert path. Adding top_k=20 + a slightly higher
# T kills that failure mode without hurting code quality.
DEFAULT_TEMPERATURE_CODE  = 0.2
DEFAULT_TEMPERATURE_PROSE = 0.35
DEFAULT_TIMEOUT_SEC  = 180
# 16k is the baseline default: enough for long tool-calling sessions
# and a few page fetches while keeping KV-cache cost modest. Users can
# bump to 32k+ in preferences if they have the RAM — in the field 32k
# turned out to OOM some smaller systems (seen on a 16 GB MacBook).
DEFAULT_CONTEXT_SIZE = 16384

# v9.3: the Experimental (🧪) toggle is now "deep mode" — when on, the
# model gets a bigger response budget AND more tool rounds, so it can
# search further, cross-check pages, and write longer code. Scene
# inspection is now ALWAYS available (no longer gated).
#
# v9.6.5: deep mode bumped to 4096 tokens and 30 tool rounds. This is
# meant as "take your time, give me a really thorough answer" — the
# model can cross-check multiple search_api / search_web / fetch_url
# rounds without hitting the limit, and has room for long multi-part
# code responses. At 32k context this still leaves plenty of KV
# headroom even in the worst case.
DEEP_MAX_TOKENS      = 4096
DEEP_TOOL_ITERATIONS = 30

# System prompt lives in two files (not hardcoded):
#   1. scripts/addons/blender_buddy_assets/system_prompt_default.txt
#      — the canonical default, shipped with the addon, never modified
#      at runtime. Used as the source for "Reset to Default".
#   2. DATAFILES/blender_buddy/system_prompt.txt
#      — the user's active copy. Auto-created from #1 on first read.
#
# This layout means we can ship prompt-engineering improvements as
# simple text-file updates without bloating the .py file, and the user
# always has a writable copy to tinker with (plus a known-good backup).

# Only-ever-used-if-both-files-are-missing emergency string. Keeps the
# addon functional during a botched install.
_FALLBACK_SYSTEM_PROMPT = (
    "You are Blender Buddy, a local assistant inside Blender 5.1. "
    "Help the user with Blender and bpy questions. Call the tools "
    "when unsure — never fabricate operator names or UI steps."
)

# Appended to the active system prompt when the user has Action Mode on
# (the Python-code toggle in the prompt row). Overrides the UI-first
# default the prompt file lays out.
ACTION_MODE_ADDENDUM = (
    "\n\n# ACTION MODE (ACTIVE)\n"
    "The user has turned Action Mode ON — they want CODE that does "
    "the thing, not UI instructions. Override the UI-first default: "
    "respond with ONE ```python fence that performs the action. No "
    "prose before or after the fence. `bpy`, `context`, `D`, `C` are "
    "in scope — no import, no __main__ guard, no try/except. Keep it "
    "short and direct. Still call search_api first to verify any "
    "operator / property / enum you're not 100% sure of. See the "
    "'Action Mode code idioms' section above for the selection / "
    "keyframe / modifier / bmesh / geonode patterns."
)

# ---------------------------------------------------------------------------
# Shared state (threads write, main thread reads)
# ---------------------------------------------------------------------------

_server_proc = None
_server_log_path = None
_server_mode = None  # 'text' | 'vision' | None — which model the server has loaded
# Effective port the running server actually bound to. May differ from
# prefs.server_port if the requested port was in use and start_server
# fell back to an adjacent port. Client code reads this so requests
# always land at the real endpoint.
_server_port_actual = None
# Tracks whether our atexit handler has been wired up this interpreter
# session. Registering more than once would run stop_server multiple
# times on interpreter shutdown (harmless but noisy).
_atexit_registered = False

# Info-log capture — Blender doesn't expose the Info editor's log via a
# clean Python API, but operator ERROR / WARNING reports also flow through
# Python stderr. We tee stderr into a bounded deque at register() so the
# `list_info_log` tool can return recent entries on demand.
_INFO_LOG_MAX = 200
_info_log_buffer = []
_info_log_lock = threading.Lock()
_stderr_orig = None

_job_state = {
    "active": False,
    "label": "",
    "progress": 0.0,
    "message": "",
    "done": False,
    "error": None,
}
_job_lock = threading.Lock()


def _job_set(**kw):
    with _job_lock:
        _job_state.update(kw)


def _job_get():
    with _job_lock:
        return dict(_job_state)


# Multi-turn conversation history. We keep (role, content) pairs in-memory,
# re-sent on every call so llama-server's prompt-cache reuses the common
# prefix automatically (system + prior turns) — that's how "send the system
# prompt only once" happens in practice: it's always in the messages list
# but the server only re-encodes the delta.
_conversation = []           # list of {"role": "user"|"assistant", "content": str}
_conversation_lock = threading.Lock()


def _conv_get():
    with _conversation_lock:
        return list(_conversation)


def _conv_append(role, content):
    with _conversation_lock:
        _conversation.append({"role": role, "content": content})


def _conv_clear():
    with _conversation_lock:
        _conversation.clear()


def _prefs(context=None):
    ctx = context or bpy.context
    return ctx.preferences.addons[ADDON_ID].preferences


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _wrap_for_label(text, width=40):
    if not text:
        return [""]
    return textwrap.wrap(text, width=width) or [""]


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def data_root():
    return bpy.utils.user_resource('DATAFILES', path="blender_buddy", create=True)


def bin_dir():
    p = os.path.join(data_root(), "llama_bin")
    os.makedirs(p, exist_ok=True)
    return p


def models_dir():
    p = os.path.join(data_root(), "models")
    os.makedirs(p, exist_ok=True)
    return p


def server_exe_path():
    candidates = (
        ("llama-server.exe", "server.exe")
        if sys.platform == "win32"
        else ("llama-server", "server")
    )
    for root, _dirs, files in os.walk(bin_dir()):
        for name in candidates:
            if name in files:
                return os.path.join(root, name)
    return None


def text_variant(key=None):
    """Return the variant dict for `key`, or the currently selected variant
    from preferences when key is None. Falls back to MEDIUM if prefs aren't
    loaded yet or the stored key is unknown."""
    if key is None:
        try:
            key = _prefs().selected_text_model
        except Exception:
            key = TEXT_MODEL_DEFAULT_KEY
    return TEXT_MODEL_VARIANTS.get(key, TEXT_MODEL_VARIANTS[TEXT_MODEL_DEFAULT_KEY])


def text_model_path(key=None):
    return os.path.join(models_dir(), text_variant(key)["filename"])


def vision_model_path():
    return os.path.join(models_dir(), VISION_MODEL["filename"])


def vision_mmproj_path():
    return os.path.join(models_dir(), VISION_MODEL["mmproj_filename"])


def text_model_ready(key=None):
    return os.path.exists(text_model_path(key))


def text_downloaded_keys():
    """Which text-model variants are present on disk, in display order."""
    return [k for k in TEXT_MODEL_ORDER if text_model_ready(k)]


def vision_model_ready():
    # Vision requires BOTH the main weights and the mmproj projector file —
    # without mmproj, llama-server loads the model as text-only.
    return (os.path.exists(vision_model_path())
            and os.path.exists(vision_mmproj_path()))


def addon_dir():
    """Folder the addon lives in (scripts/addons/). Read-only at runtime."""
    return os.path.dirname(os.path.abspath(__file__))


def addon_assets_dir():
    """Shipped assets folder inside the addon — icons, animation frames,
    and the default system prompt. Read-only. Created on demand in case
    a user's install has blown it away (fallbacks handle missing
    individual files)."""
    p = os.path.join(addon_dir(), "blender_buddy_assets")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def default_system_prompt_path():
    """The shipped default — read-only at runtime. Lives in
    addon_assets_dir() so it travels with script reloads."""
    return os.path.join(addon_assets_dir(), "system_prompt_default.txt")


def system_prompt_path():
    """The user's active prompt — the file the model actually sees. Auto-
    seeded from the default on first read."""
    return os.path.join(data_root(), "system_prompt.txt")


def read_default_system_prompt():
    """Read the canonical default shipped in blender_buddy_assets/. Falls
    back to the minimal built-in string only if the file is missing."""
    path = default_system_prompt_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content
    except OSError:
        pass
    return _FALLBACK_SYSTEM_PROMPT


def read_system_prompt():
    """Return the user's active prompt from DATAFILES. If the active file
    doesn't exist yet, seed it from the default and return that. This
    guarantees that the on-disk active copy exists from the first ask
    onwards — so a user who wants to tweak it always has a file to edit."""
    path = system_prompt_path()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                return content
    except OSError:
        pass
    # No active file (or it was empty) — seed from the default.
    default_content = read_default_system_prompt()
    try:
        write_system_prompt(default_content)
    except OSError:
        pass
    return default_content


def write_system_prompt(text):
    with open(system_prompt_path(), "w", encoding="utf-8") as f:
        f.write(text)


def reset_system_prompt_to_default():
    """Overwrite the active prompt with the shipped default. Used by the
    'Reset to Default' button in preferences."""
    write_system_prompt(read_default_system_prompt())


def open_in_default_editor(path):
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


# ---------------------------------------------------------------------------
# Platform / backend detection
# ---------------------------------------------------------------------------

def detect_os():
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def detect_arch():
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x64"


def detect_default_backend():
    osn = detect_os()
    if osn == "macos":
        return "metal"
    if shutil.which("nvidia-smi"):
        return "cuda"
    # AMD on Linux — prefer ROCm/HIP when available. `rocm-smi` on PATH
    # or the /dev/kfd device node both indicate a working ROCm stack.
    # Falls through to Vulkan (which also runs on AMD) otherwise.
    if osn == "linux":
        if shutil.which("rocm-smi") or os.path.exists("/dev/kfd"):
            return "hip"
    return "vulkan"


def _effective_backend(prefs):
    b = prefs.backend.lower()
    return detect_default_backend() if b == 'auto' else b


# --- GPU-layer autodetect ---------------------------------------------------

_RUNTIME_OVERHEAD_MB = 700
_KV_MB_PER_1K_CTX = 70
_TYPICAL_LAYERS = 33
_FULL_OFFLOAD_TAG = 99


def _nvidia_free_vram_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5,
        )
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def _apple_unified_memory_mb():
    try:
        out = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], text=True, timeout=5,
        )
        total_mb = int(out.strip()) // (1024 * 1024)
        return int(total_mb * 0.6)
    except Exception:
        return None


def _free_gpu_memory_mb(backend):
    if backend == 'cpu':
        return 0
    if backend == 'metal':
        return _apple_unified_memory_mb()
    return _nvidia_free_vram_mb()


def _nvidia_total_vram_mb():
    """Total VRAM on the primary NVIDIA GPU, via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            text=True, timeout=5,
        )
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def _nvidia_gpu_name():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name",
             "--format=csv,noheader"],
            text=True, timeout=5,
        )
        return out.strip().splitlines()[0]
    except Exception:
        return None


def _system_ram_total_mb():
    """Total physical RAM in megabytes, cross-platform, stdlib-only."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _MemStatEx(ctypes.Structure):
                _fields_ = [
                    ('dwLength',               ctypes.c_ulong),
                    ('dwMemoryLoad',           ctypes.c_ulong),
                    ('ullTotalPhys',           ctypes.c_ulonglong),
                    ('ullAvailPhys',           ctypes.c_ulonglong),
                    ('ullTotalPageFile',       ctypes.c_ulonglong),
                    ('ullAvailPageFile',       ctypes.c_ulonglong),
                    ('ullTotalVirtual',        ctypes.c_ulonglong),
                    ('ullAvailVirtual',        ctypes.c_ulonglong),
                    ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]

            stat = _MemStatEx()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys // (1024 * 1024)
        if sys.platform == "darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], text=True, timeout=5,
            )
            return int(out.strip()) // (1024 * 1024)
        # Linux / *BSD — parse /proc/meminfo.
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


# Cached at first call — hardware doesn't change during a session, and
# `nvidia-smi` / ctypes calls cost ~50 ms which isn't free on a prefs
# redraw loop.
_HARDWARE_INFO_CACHE = {"done": False,
                         "ram_mb": None,
                         "gpu_label": None,
                         "gpu_mb": None}


def _hardware_info():
    """Return (ram_mb, gpu_label, gpu_mb) — any of them may be None if
    detection failed. Cached for the session."""
    if _HARDWARE_INFO_CACHE["done"]:
        return (_HARDWARE_INFO_CACHE["ram_mb"],
                _HARDWARE_INFO_CACHE["gpu_label"],
                _HARDWARE_INFO_CACHE["gpu_mb"])
    ram = _system_ram_total_mb()
    gpu_label = None
    gpu_mb = None
    if shutil.which("nvidia-smi"):
        name = _nvidia_gpu_name()
        total = _nvidia_total_vram_mb()
        if total:
            gpu_label = name or "NVIDIA GPU"
            gpu_mb = total
    elif sys.platform == "darwin":
        um = _apple_unified_memory_mb()
        if um:
            gpu_label = "Apple unified memory (~60% usable)"
            gpu_mb = um
    _HARDWARE_INFO_CACHE.update(
        done=True, ram_mb=ram, gpu_label=gpu_label, gpu_mb=gpu_mb)
    return ram, gpu_label, gpu_mb


def _hardware_summary_line():
    """One-line human-friendly summary for the prefs UI."""
    ram, gpu_label, gpu_mb = _hardware_info()
    bits = []
    if ram:
        bits.append(f"{ram / 1024:.0f} GB RAM")
    if gpu_label and gpu_mb:
        bits.append(f"{gpu_label}: {gpu_mb / 1024:.1f} GB")
    return "  ·  ".join(bits) if bits else "Couldn't detect hardware specs."


def _recommended_text_key():
    """Pick the recommended text-model tier based on detected hardware.

    The computer also has to run the OS and Blender (plus whatever the
    user is modelling) alongside Buddy, so we reserve a fixed baseline
    of system RAM before counting what's usable for the model. GPU
    VRAM is taken mostly as-is because the OS doesn't compete for it.

    Real-world baseline memory:
      · Windows / Linux + Blender with a real scene: 4–8 GB
      · macOS + Blender + a browser: 6–10 GB (unified memory is shared)
    We use 8 GB as a conservative floor, then size the tiers so a
    user with that much headroom can actually run the model without
    thrashing swap.
    """
    ram, _label, gpu_mb = _hardware_info()
    RAM_BASELINE_MB = 8 * 1024
    usable_mb = 0
    if ram:
        usable_mb = max(usable_mb, max(0, ram - RAM_BASELINE_MB))
    if gpu_mb:
        usable_mb = max(usable_mb, int(gpu_mb * 0.85))
    if usable_mb >= 24 * 1024:
        return 'HIGH'
    if usable_mb >= 16 * 1024:
        return 'MEDIUM'
    if usable_mb >= 8 * 1024:
        return 'LOW'
    return None


def autodetect_gpu_layers(model_file, context_size, backend):
    if backend == 'cpu':
        return 0
    free = _free_gpu_memory_mb(backend)
    if free is None:
        return _FULL_OFFLOAD_TAG
    try:
        model_mb = os.path.getsize(model_file) / (1024 * 1024)
    except OSError:
        return _FULL_OFFLOAD_TAG
    kv_mb = (context_size / 1024) * _KV_MB_PER_1K_CTX
    usable_mb = free - _RUNTIME_OVERHEAD_MB - kv_mb
    if usable_mb <= 0:
        return 0
    if usable_mb >= model_mb * 1.05:
        return _FULL_OFFLOAD_TAG
    per_layer = model_mb / _TYPICAL_LAYERS
    return max(0, min(_TYPICAL_LAYERS, int(usable_mb / per_layer)))


# ---------------------------------------------------------------------------
# llama.cpp release asset selection
# ---------------------------------------------------------------------------

def fetch_pinned_release():
    """Return the GitHub release JSON for the llama.cpp tag this Buddy
    version is pinned to. Every user on a given Buddy version installs
    the same binary so tool calling / vision / chat-completion shape
    stay reproducible."""
    url = LLAMACPP_TAG_API + LLAMACPP_PINNED_TAG
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "blender-buddy-addon"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def score_asset(name, osn, arch, backend):
    n = name.lower()
    if not (n.endswith(".zip") or n.endswith(".tar.gz") or n.endswith(".tgz")):
        return -1
    if n.startswith("cudart-") or n.startswith("hiprt-") or "runtime-only" in n:
        return -1
    if not n.startswith("llama-"):
        return -1
    score = 0
    if osn == "win":
        if "win" not in n:
            return -1
        score += 10
    elif osn == "macos":
        if "macos" not in n and "darwin" not in n:
            return -1
        score += 10
    elif osn == "linux":
        if not any(k in n for k in ("linux", "ubuntu")):
            return -1
        score += 10
    if arch == "arm64":
        if "arm64" in n or "aarch64" in n:
            score += 5
        elif "x64" in n or "amd64" in n or "x86_64" in n:
            return -1
    else:
        if "arm64" in n or "aarch64" in n:
            return -1
        if "x64" in n or "amd64" in n or "x86_64" in n:
            score += 5
    if backend == "cuda":
        if "cuda" in n:
            score += 20
        else:
            return -1
    elif backend == "vulkan":
        if "vulkan" in n:
            score += 20
        else:
            return -1
    elif backend == "hip":
        # AMD ROCm/HIP build — llama.cpp ships Linux x64 HIP assets
        # named "llama-*-linux-x64-hip.tar.gz".
        if "hip" in n:
            score += 20
        else:
            return -1
    elif backend == "cpu":
        if "cpu" in n:
            score += 20
        elif not any(k in n for k in ("cuda", "vulkan", "hip", "sycl", "kompute")):
            score += 10
        else:
            return -1
    elif backend == "metal":
        score += 5
    if "hip" in n and backend != "hip":
        score -= 5
    if "sycl" in n and backend != "sycl":
        score -= 5
    if "kompute" in n and backend != "kompute":
        score -= 5
    return score


def pick_asset(release_json, osn, arch, backend):
    best = None
    best_score = 0
    for a in release_json.get("assets", []):
        s = score_asset(a["name"], osn, arch, backend)
        if s > best_score:
            best_score = s
            best = a
    return best


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

def _head_content_length(url, timeout=30):
    """HEAD-request a URL to get its Content-Length. Returns int bytes or
    0 when the server doesn't advertise it (rare for HuggingFace / GitHub
    releases — they both set it). Used for the disk-space preflight."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "blender-buddy-addon"},
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.headers.get("Content-Length") or 0)
    except Exception as e:
        print(f"[Blender Buddy] HEAD failed for {url}: {e}")
        return 0


def _head_sha256(url, timeout=30):
    """HuggingFace serves GGUFs via LFS, and after the CloudFront
    redirect the CDN's `ETag` header IS the raw LFS SHA-256 (64 hex
    chars, no prefix). Older or non-CDN responses sometimes use
    `X-Linked-Etag: sha256:…` instead. We accept either form. Returns
    the lowercase hex hash or None when neither is present. Useful for
    auto-filling `sha256` fields when refreshing a release:
        print(_head_sha256(TEXT_MODEL_VARIANTS['MEDIUM']['url']))
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "blender-buddy-addon"},
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for key in ("X-Linked-Etag", "X-Linked-ETag", "ETag"):
                v = (r.headers.get(key) or "").strip().strip('"')
                if v.lower().startswith("sha256:"):
                    return v.split(":", 1)[1].lower()
                # CloudFront returns the LFS hash as a bare 64-char hex
                # string. Accept it when it's the right shape.
                low = v.lower()
                if len(low) == 64 and all(c in "0123456789abcdef" for c in low):
                    return low
    except Exception as e:
        print(f"[Blender Buddy] SHA-256 HEAD failed for {url}: {e}")
    return None


# Download-wide cancel flag. Workers check this between chunks so a user
# who realises they picked the wrong variant can abort mid-stream.
_download_cancel = threading.Event()


def _reset_download_cancel():
    _download_cancel.clear()


def request_download_cancel():
    _download_cancel.set()


def download_cancelled():
    return _download_cancel.is_set()


def _assert_free_space(dest, needed_bytes, already_have=0):
    """Raise RuntimeError with a friendly message if the filesystem
    holding `dest` doesn't have room for a `needed_bytes` download, minus
    what's already written to a `.part` resume file."""
    if needed_bytes <= 0:
        return
    dest_dir = os.path.dirname(dest) or "."
    try:
        free = shutil.disk_usage(dest_dir).free
    except Exception:
        return  # can't check — let the write fail naturally
    required = max(0, needed_bytes - already_have)
    # 128 MB headroom for FS metadata / temp-file slack so we don't wedge
    # the disk at exactly full.
    headroom = 128 * 1024 * 1024
    if free < required + headroom:
        raise RuntimeError(
            f"Not enough disk space to download "
            f"{needed_bytes / 1_073_741_824:.1f} GB. Free in "
            f"'{dest_dir}': {free / 1_073_741_824:.1f} GB — need at "
            f"least {(required + headroom) / 1_073_741_824:.1f} GB."
        )


def download_file(url, dest, label, expected_sha256=None):
    """Download `url` → `dest`, resuming from `dest + '.part'` if present.

    Adds three hardening steps over the v9.13 version:
      * pre-download disk-space check (HEAD the URL, compare to free space)
      * HTTP Range: resume when a `.part` file already exists
      * optional SHA-256 verification before the atomic rename

    The resume path falls back to a fresh download if the server doesn't
    honour Range: (status != 206); most CDNs do.
    """
    _job_set(label=label, progress=0.0, message=f"Connecting: {url}")
    tmp = dest + ".part"

    # Disk-space preflight. If a previous run left a .part file, only the
    # remaining bytes need to fit.
    already = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    total_expected = _head_content_length(url)
    _assert_free_space(dest, total_expected, already_have=already)

    headers = {"User-Agent": "blender-buddy-addon"}
    resume_offset = 0
    if already > 0 and (total_expected == 0 or already < total_expected):
        headers["Range"] = f"bytes={already}-"
        resume_offset = already
        _job_set(message=f"{label}: resuming at {already / 1_048_576:.1f} MB")
    elif already > 0 and total_expected and already >= total_expected:
        # .part is already complete — skip the fetch and go straight to
        # checksum + rename.
        resume_offset = already
        _job_set(progress=1.0,
                 message=f"{label}: .part already complete — finalizing")
        if expected_sha256:
            _verify_sha256(tmp, expected_sha256)
        os.replace(tmp, dest)
        return

    req = urllib.request.Request(url, headers=headers)
    start_time = time.time()
    last_ui   = 0.0
    with urllib.request.urlopen(req, timeout=60) as r:
        http_status = getattr(r, "status", 200)
        # If we asked for a partial but the server sent 200, it ignored
        # our Range and is re-sending the whole file — scrap the .part
        # and start fresh.
        if resume_offset > 0 and http_status != 206:
            resume_offset = 0
            already = 0
            _job_set(message=f"{label}: server ignored resume, starting over")
        total_from_resp = int(r.headers.get("Content-Length") or 0)
        # When resuming, Content-Length is just the remaining bytes; add
        # what we already had so the progress bar reflects the whole file.
        total = (total_from_resp + resume_offset) if resume_offset else total_from_resp
        done = resume_offset
        chunk = 1024 * 256
        open_mode = "ab" if resume_offset > 0 else "wb"
        with open(tmp, open_mode) as f:
            while True:
                if download_cancelled():
                    # Leave the .part file in place so a later retry can
                    # resume. Caller decides whether to surface the cancel
                    # as an error or a clean abort (workers below treat
                    # it as an expected early exit).
                    raise RuntimeError("Download cancelled by user.")
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                now = time.time()
                # Throttle UI updates to ~5/sec — _job_set behind a lock
                # is cheap but panel redraw isn't.
                if now - last_ui < 0.2 and total and done < total:
                    continue
                last_ui = now
                if total:
                    elapsed = max(0.001, now - start_time)
                    rate_bps = (done - resume_offset) / elapsed  # bytes / sec for this run
                    remaining = max(0, total - done)
                    eta_s = remaining / rate_bps if rate_bps > 1 else 0
                    eta = _fmt_eta(eta_s) if eta_s else ""
                    pct = done / total * 100
                    _job_set(
                        progress=done / total,
                        message=(f"{label}: {done/1_048_576:.1f} / "
                                 f"{total/1_048_576:.1f} MB ({pct:.0f}%)"
                                 + (f" — {eta} left" if eta else "")),
                    )
                else:
                    _job_set(message=f"{label}: {done/1_048_576:.1f} MB")

    if expected_sha256:
        _job_set(progress=1.0, message=f"{label}: checking file…")
        _verify_sha256(tmp, expected_sha256)
    _job_set(progress=1.0, message=f"{label}: saving…")
    os.replace(tmp, dest)
    _job_set(progress=1.0, message=f"{label}: done")


def download_file_with_fallback(urls, dest, label, expected_sha256=None):
    """Try each URL in `urls` in order. On network error or SHA-256
    mismatch, scrap the partial file and move to the next URL. Raise
    the last exception if every source fails. User-initiated cancels
    propagate immediately — we never try to 'recover' from those by
    hitting another mirror.

    Used so downloads go to Unsloth's fast edge-cached repo first and
    only fall back to our own (slower, smaller) mirror if that source
    is actually unavailable."""
    if not urls:
        raise RuntimeError("download_file_with_fallback: no URLs provided")
    tmp = dest + ".part"
    last_err = None
    for i, url in enumerate(urls):
        attempt_label = label if i == 0 else f"{label} (fallback)"
        try:
            download_file(url, dest, attempt_label,
                          expected_sha256=expected_sha256)
            return
        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                raise
            last_err = e
        except Exception as e:
            last_err = e
        # Whatever we wrote to .part was either corrupt or came from a
        # source that didn't match the expected hash. Drop it so the
        # next URL starts clean instead of trying to resume bad bytes.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        if i + 1 < len(urls):
            print(f"[Blender Buddy] {url} failed ({last_err}); trying fallback.")
    raise last_err if last_err else RuntimeError("All download sources failed")


def _fmt_eta(seconds):
    """Render a human-friendly ETA string. Keeps it short: '12s', '3m',
    '1h 05m'. Returns '' for < 1 s."""
    if seconds < 1:
        return ""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m:02d}m"


def _verify_sha256(path, expected):
    """Compute the SHA-256 of `path` and raise RuntimeError if it doesn't
    match `expected` (hex, case-insensitive). Leaves the .part file in
    place on mismatch so a human can inspect it rather than re-downloading
    silently."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest().lower()
    want = expected.lower().strip()
    if got != want:
        raise RuntimeError(
            f"Checksum mismatch for {os.path.basename(path)}: "
            f"expected {want[:12]}…, got {got[:12]}…. File preserved at "
            f"{path} — delete it and retry if you want to re-download."
        )


# Extraction caps. Archives come from llama.cpp GitHub releases (trusted),
# but we still sanity-check to guard against a compromised CDN hop or a
# hand-forged archive: reject path-traversal names, cap total uncompressed
# size, cap entry count.
_EXTRACT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB total
_EXTRACT_MAX_ENTRIES     = 10_000


def _safe_extract_member_name(name, dest_dir):
    """Return the validated absolute path `dest_dir/name` is supposed to
    land at, or raise RuntimeError if the entry would escape dest_dir or
    contains an absolute path / traversal segment. Normalises the
    trailing separator for the dest-dir prefix check."""
    if not name or name.startswith("/") or name.startswith("\\"):
        raise RuntimeError(f"archive entry refused (absolute path): {name!r}")
    # Block both forward and backslash traversal; plus drive-letter
    # absolute paths on Windows (e.g. "C:\\foo").
    if ".." in name.replace("\\", "/").split("/"):
        raise RuntimeError(f"archive entry refused (path traversal): {name!r}")
    if os.path.isabs(name) or (len(name) > 1 and name[1] == ":"):
        raise RuntimeError(f"archive entry refused (absolute path): {name!r}")
    dest_real = os.path.realpath(dest_dir)
    target = os.path.realpath(os.path.join(dest_dir, name))
    prefix = dest_real + os.sep
    if not (target == dest_real or target.startswith(prefix)):
        raise RuntimeError(
            f"archive entry refused (escapes dest): {name!r} → {target}"
        )
    return target


def extract_archive(archive_path, dest_dir):
    _job_set(message=f"Extracting {os.path.basename(archive_path)}")
    os.makedirs(dest_dir, exist_ok=True)
    low = archive_path.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            infos = z.infolist()
            if len(infos) > _EXTRACT_MAX_ENTRIES:
                raise RuntimeError(
                    f"Archive has {len(infos)} entries (cap "
                    f"{_EXTRACT_MAX_ENTRIES}). Refusing to extract."
                )
            total = sum(info.file_size for info in infos)
            if total > _EXTRACT_MAX_TOTAL_BYTES:
                raise RuntimeError(
                    f"Archive uncompressed size {total / 1_073_741_824:.1f} "
                    f"GB exceeds cap ({_EXTRACT_MAX_TOTAL_BYTES / 1_073_741_824:.1f} GB)."
                )
            for info in infos:
                _safe_extract_member_name(info.filename, dest_dir)
            z.extractall(dest_dir)
    elif low.endswith(".tar.gz") or low.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as t:
            members = t.getmembers()
            if len(members) > _EXTRACT_MAX_ENTRIES:
                raise RuntimeError(
                    f"Archive has {len(members)} entries (cap "
                    f"{_EXTRACT_MAX_ENTRIES}). Refusing to extract."
                )
            total = sum(max(0, m.size) for m in members)
            if total > _EXTRACT_MAX_TOTAL_BYTES:
                raise RuntimeError(
                    f"Archive uncompressed size {total / 1_073_741_824:.1f} "
                    f"GB exceeds cap ({_EXTRACT_MAX_TOTAL_BYTES / 1_073_741_824:.1f} GB)."
                )
            for m in members:
                _safe_extract_member_name(m.name, dest_dir)
            # Python 3.12+ tarfile exposes a 'data' filter that also
            # blocks dangerous permissions / special file types. Use it
            # when available; silently fall through on older Pythons
            # (we already did the name-based checks above).
            try:
                t.extractall(dest_dir, filter='data')
            except TypeError:
                t.extractall(dest_dir)
    else:
        raise RuntimeError(f"Unknown archive type: {archive_path}")
    if sys.platform != "win32":
        for root, _dirs, files in os.walk(dest_dir):
            for f in files:
                if f.startswith("llama-") or f.endswith(".so") or f.endswith(".dylib"):
                    try:
                        os.chmod(os.path.join(root, f), 0o755)
                    except OSError as e:
                        print(f"[Blender Buddy] chmod failed for {f}: {e}")


# ---------------------------------------------------------------------------
# Install / download workers (run in threads)
# ---------------------------------------------------------------------------

def worker_install_server(backend):
    _reset_download_cancel()
    try:
        osn = detect_os()
        arch = detect_arch()
        _job_set(label="Fetching release info", progress=0.0,
                 message=f"{osn}/{arch}/{backend}")
        rel = fetch_pinned_release()
        tag = rel.get("tag_name", "?")
        asset = pick_asset(rel, osn, arch, backend)
        # Graceful fallback — if the requested backend has no matching
        # asset in the latest release (unusual hardware, ARM64 Windows,
        # etc.), retry with the CPU build so the user ends up with a
        # working install instead of a dead-end error. They can still
        # switch back to their preferred backend if a later release
        # ships matching assets.
        fell_back = False
        if asset is None and backend != "cpu":
            _job_set(message=f"No {backend.upper()} asset in {tag} — "
                              f"falling back to CPU build")
            asset = pick_asset(rel, osn, arch, "cpu")
            fell_back = True
        if asset is None:
            names = [a.get("name", "?") for a in rel.get("assets", [])][:12]
            raise RuntimeError(
                f"No asset matched {osn}/{arch}/{backend} (or CPU "
                f"fallback) in release {tag}. Available assets start "
                f"with: {names}"
            )
        url = asset["browser_download_url"]
        name = asset["name"]
        archive = os.path.join(bin_dir(), name)
        _job_set(message=f"Picked: {name}")
        if os.path.exists(archive):
            _job_set(message=f"Reusing cached {name}")
        else:
            download_file(url, archive, f"Server [{tag}] {name}")

        extract_dir = os.path.join(bin_dir(),
                                   os.path.splitext(name)[0].replace(".tar", ""))
        if os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        extract_archive(archive, extract_dir)

        # CUDA runtime side-car: only needed when we actually installed
        # a CUDA build. If we fell back to CPU, skip this — we don't
        # have CUDA and grabbing cudart would be a waste of bandwidth.
        if backend == "cuda" and osn == "win" and not fell_back:
            cudart = None
            for a in rel.get("assets", []):
                an = a["name"].lower()
                if an.startswith("cudart-") and "win" in an and an.endswith(".zip"):
                    cudart = a
                    break
            if cudart is not None:
                carc = os.path.join(bin_dir(), cudart["name"])
                if not os.path.exists(carc):
                    download_file(cudart["browser_download_url"], carc,
                                  f"CUDA runtime {cudart['name']}")
                extract_archive(carc, extract_dir)

        exe = server_exe_path()
        if not exe:
            listing = []
            for root, _dirs, files in os.walk(extract_dir):
                for f in files[:20]:
                    listing.append(f)
                if len(listing) >= 20:
                    break
            raise RuntimeError(
                f"Extracted {name} but no llama-server binary inside. "
                f"Files seen: {listing[:10]}"
            )
        note = (f"  (fell back to CPU — no {backend.upper()} asset "
                f"in {tag})" if fell_back else "")
        _job_set(done=True, progress=1.0,
                 message=f"Installed: {exe}{note}")
    except Exception as e:
        _job_set(done=True, error=str(e))


def worker_download_text_variant(variant_key):
    """Download one specific text-model variant (LOW/MEDIUM/HIGH). Skips
    if already on disk."""
    _reset_download_cancel()
    try:
        variant = TEXT_MODEL_VARIANTS[variant_key]
        path = os.path.join(models_dir(), variant["filename"])
        if os.path.exists(path):
            _job_set(done=True, progress=1.0,
                     message=f"{variant['label']} already present")
            return
        download_file_with_fallback(
            [variant["url"], variant["fallback_url"]],
            path, f"{variant['label']} model",
            expected_sha256=variant.get("sha256"),
        )
        _job_set(done=True, progress=1.0,
                 message=f"{variant['label']} model saved")
    except Exception as e:
        _job_set(done=True, error=str(e))


def worker_download_vision_model():
    """Download the VISION model + its mmproj projector. Both files are
    required; downloading either alone gives an unusable install."""
    _reset_download_cancel()
    try:
        # Main weights
        if not os.path.exists(vision_model_path()):
            download_file_with_fallback(
                [VISION_MODEL["url"], VISION_MODEL["fallback_url"]],
                vision_model_path(), "Vision model",
                expected_sha256=VISION_MODEL.get("sha256"),
            )
        # Multimodal projection file (maps image embeddings into LM token space)
        if not os.path.exists(vision_mmproj_path()):
            download_file_with_fallback(
                [VISION_MODEL["mmproj_url"], VISION_MODEL["mmproj_fallback_url"]],
                vision_mmproj_path(), "Vision helper",
                expected_sha256=VISION_MODEL.get("mmproj_sha256"),
            )
        _job_set(done=True, progress=1.0, message="Vision model ready")
    except Exception as e:
        _job_set(done=True, error=str(e))


def worker_download_selected_and_vision(variant_key):
    """One-click: ensure the chosen text variant + vision are on disk. Skips
    whichever is already there so re-runs only fetch what's missing."""
    _reset_download_cancel()
    try:
        variant = TEXT_MODEL_VARIANTS[variant_key]
        tpath = os.path.join(models_dir(), variant["filename"])
        if not os.path.exists(tpath):
            download_file_with_fallback(
                [variant["url"], variant["fallback_url"]],
                tpath, f"{variant['label']} model",
                expected_sha256=variant.get("sha256"),
            )
        if not os.path.exists(vision_model_path()):
            download_file_with_fallback(
                [VISION_MODEL["url"], VISION_MODEL["fallback_url"]],
                vision_model_path(), "Vision model",
                expected_sha256=VISION_MODEL.get("sha256"),
            )
        if not os.path.exists(vision_mmproj_path()):
            download_file_with_fallback(
                [VISION_MODEL["mmproj_url"], VISION_MODEL["mmproj_fallback_url"]],
                vision_mmproj_path(), "Vision helper",
                expected_sha256=VISION_MODEL.get("mmproj_sha256"),
            )
        _job_set(done=True, progress=1.0,
                 message=f"Ready: {variant['label']} + vision")
    except Exception as e:
        _job_set(done=True, error=str(e))


# ---------------------------------------------------------------------------
# Server process management
# ---------------------------------------------------------------------------

def _port_is_taken(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _launch_server_proc(cmd, log_path):
    log_f = open(log_path, "w", encoding="utf-8", errors="replace")
    # Windows: CREATE_NO_WINDOW keeps the console hidden. On Linux
    # start_new_session puts the server in its own process group so a
    # parent SIGTERM doesn't propagate when we're not asking for it,
    # and so our own group signals don't reach it. On macOS the same
    # flag is correct — don't tie the child to our TTY session.
    popen_kwargs = {
        "stdout": log_f,
        "stderr": subprocess.STDOUT,
        "cwd":    os.path.dirname(cmd[0]),
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **popen_kwargs)


def _terminate_proc(proc):
    if proc is None or proc.poll() is not None:
        return None
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception as e:
        # Termination shouldn't silently succeed on failure — if the OS
        # refuses to kill our child, the user needs to see that so they
        # can clean up manually (Task Manager / kill -9).
        print(f"[Blender Buddy] terminate failed for pid {proc.pid}: {e}")
    return proc.pid


def server_is_running():
    return _server_proc is not None and _server_proc.poll() is None


def current_server_mode():
    return _server_mode if server_is_running() else None


def start_server(prefs, mode='text'):
    """Launch llama-server in the requested mode. Stops + restarts if the
    server is already running in a different mode — only one model loaded
    at a time to avoid doubling VRAM/RAM usage."""
    global _server_proc, _server_log_path, _server_mode, _server_port_actual

    if server_is_running():
        if _server_mode == mode:
            return f"Server already running ({mode})."
        # Mode switch — stop the current server, then fall through and start.
        stop_server()
        # Small grace period so the OS releases the port before rebind.
        time.sleep(0.4)

    exe = server_exe_path()
    if not exe:
        raise RuntimeError(
            "llama-server not installed. Click 'Install Server' first."
        )

    if mode == 'text':
        if not text_model_ready():
            variant = text_variant()
            raise RuntimeError(
                f"{variant['label']} text model "
                f"({variant['filename']}) not downloaded. "
                "Open Preferences and click Download next to the variant you want."
            )
        model_file = text_model_path()
        extra_args = []
    elif mode == 'vision':
        if not vision_model_ready():
            raise RuntimeError(
                "Vision model not downloaded. Click 'Download' next to the "
                "vision model in Preferences."
            )
        model_file = vision_model_path()
        extra_args = ["--mmproj", vision_mmproj_path()]
    else:
        raise RuntimeError(f"Unknown server mode: {mode!r}")

    requested_port = int(prefs.server_port)
    port = requested_port
    # Previously this raised on a bound port, but the most common cause
    # is a stale llama-server from a prior Blender session still hogging
    # the port during TIME_WAIT. Scan up to 10 ports above the configured
    # one and use the first free one; log so the user knows we moved.
    if _port_is_taken(port):
        found = None
        for candidate in range(requested_port + 1, requested_port + 11):
            if 1024 <= candidate <= 65535 and not _port_is_taken(candidate):
                found = candidate
                break
        if found is None:
            raise RuntimeError(
                f"Port {requested_port} is already bound and ports "
                f"{requested_port + 1}-{requested_port + 10} are also "
                f"taken. Kill any stray llama-server (Task Manager) "
                f"then try again."
            )
        port = found
        print(f"[Blender Buddy] port {requested_port} busy; using {port} instead.")

    # v9.6.5: context size is user-tunable via `prefs.context_size`.
    # Falls back to the module default when prefs aren't loaded (first
    # register path) so the server never starts with an invalid -c.
    ctx_size = int(getattr(prefs, "context_size", DEFAULT_CONTEXT_SIZE)
                   or DEFAULT_CONTEXT_SIZE)
    ngl = autodetect_gpu_layers(
        model_file, ctx_size,
        backend=_effective_backend(prefs),
    )
    cmd = [
        exe,
        "-m", model_file,
        "-c", str(ctx_size),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-ngl", str(ngl),
    ]
    # --jinja renders the model's chat template so tool_calls are parsed
    # into structured OpenAI output — required for the agentic tool loop
    # in TEXT mode. DO NOT pass it in vision mode: the Qwen2.5-VL chat
    # template under --jinja can't handle OpenAI multipart content arrays
    # (the [{type:text},{type:image_url}] shape we send for screenshots),
    # and ends up stringifying the blob — the model then emits "??????…"
    # because it's looking at raw JSON instead of a decoded image.
    if mode == 'text':
        cmd.append("--jinja")
    cmd.extend(extra_args)
    _server_log_path = os.path.join(data_root(), "server.log")
    _server_proc = _launch_server_proc(cmd, _server_log_path)
    _server_mode  = mode
    _server_port_actual = port
    port_note = "" if port == requested_port else f" (fell back from {requested_port})"
    return (f"Started {mode} (pid {_server_proc.pid}) on port {port}{port_note}, "
            f"GPU layers={ngl}. Log: {_server_log_path}")


def stop_server():
    global _server_proc, _server_mode, _server_port_actual
    pid = _terminate_proc(_server_proc)
    _server_proc = None
    _server_mode = None
    _server_port_actual = None
    return f"Stopped (pid {pid})." if pid else "Server not running."


def effective_server_base_url(prefs):
    """Return the correct base URL to hit the running server. Prefers the
    port the server actually bound to (set by start_server after the
    fallback scan) over the user's prefs value — they diverge when the
    requested port was busy at launch time."""
    if _server_port_actual is not None and server_is_running():
        return f"http://127.0.0.1:{_server_port_actual}"
    return prefs.server_url.strip() or f"http://127.0.0.1:{prefs.server_port}"


# ---------------------------------------------------------------------------
# HTTP / chat
# ---------------------------------------------------------------------------

def _http_post(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _poll_server_ready(base, timeout=120):
    base = base.rstrip("/")
    urls = (base + "/health", base + "/v1/models")
    start = time.time()
    last_status = ""
    while time.time() - start < timeout:
        # If the server subprocess has already exited, stop waiting and
        # surface the log tail so the user sees what actually failed —
        # otherwise we'd sit for the full timeout before giving up.
        if _server_proc is not None and _server_proc.poll() is not None:
            exit_code = _server_proc.returncode
            tail = _read_server_log_tail(12)
            msg = (f"server exited with code {exit_code} before ready. "
                   f"Log tail:\n{tail}" if tail
                   else f"server exited with code {exit_code} before ready.")
            raise RuntimeError(msg)
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    body = r.read().decode("utf-8", errors="replace")
                    try:
                        j = json.loads(body)
                        status = (j.get("status") or "").lower()
                        if status == "ok" or "data" in j or "models" in j:
                            return True
                        if status and status != last_status:
                            last_status = status
                            _job_set(message=f"server: {status}")
                    except json.JSONDecodeError:
                        return True
            except Exception:
                pass
        time.sleep(1)
    return False


def _read_server_log_tail(n_lines=20):
    """Return the last n lines of the running server's log, or '' if no
    log exists. Used by _poll_server_ready when the subprocess exits
    early so the user sees *why* it failed."""
    if not _server_log_path or not os.path.exists(_server_log_path):
        return ""
    try:
        with open(_server_log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return "\n".join(lines[-n_lines:])
    except OSError:
        return ""


_CHAT_SAMPLING = {
    "repeat_penalty": 1.1,
    "top_p":          0.8,
    "top_k":          20,
    "min_p":          0.0,
}


def _call_chat_messages(base_url, messages, max_tokens, temperature,
                        timeout, stream_cb=None):
    """Send a full messages list. Streams via SSE when stream_cb is given.
    Returns the assistant's final text."""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": "qwen3",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": bool(stream_cb),
        **_CHAT_SAMPLING,
    }
    if not stream_cb:
        resp = _http_post(url, payload, timeout)
        return resp["choices"][0]["message"]["content"]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json",
                 "Accept": "text/event-stream"},
        method="POST",
    )
    parts = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                obj = json.loads(body)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    parts.append(delta)
                    stream_cb("".join(parts))
            except Exception:
                continue
    return "".join(parts)


# ---------------------------------------------------------------------------
# Web search (optional — DuckDuckGo HTML endpoint, no API key required)
# ---------------------------------------------------------------------------
#
# DDG serves a minimal HTML search results page at html.duckduckgo.com/html/
# that's stable enough for low-volume scraping (this addon hits it once per
# user-initiated question). No key, no signup, no rate-limiting in practice
# at conversational frequencies. If the parse fails (layout change, anomaly
# page, offline), we degrade silently — the question is still asked, just
# without web context.

# ---------------------------------------------------------------------------
# URL-safety guard for tool-driven fetches
# ---------------------------------------------------------------------------
# The model can hand us arbitrary URLs via search_web → fetch_url. A
# prompt-injected page can redirect a follow-up fetch to file:// (read
# local files), 169.254.169.254 (cloud metadata), 127.0.0.1:631 (local
# CUPS / internal services), or private-network IPs (intranet SSRF). We
# reject those schemes / destinations before calling urlopen, and cap
# redirects so a chain can't escape the policy.

_ALLOWED_URL_SCHEMES = ("http", "https")

_BLOCKED_HOST_PREFIXES = (
    "127.", "10.",
    "169.254.",                # link-local / cloud metadata
    "192.168.",
    "0.",
)
_BLOCKED_HOSTS_EXACT = {"localhost", "::1", "0.0.0.0"}


def _host_is_blocked(host):
    """True if `host` resolves to a literal private/loopback/metadata IP
    or is in our exact-match denylist. Keeps the check purely lexical —
    we don't want to make a DNS query for a URL we haven't decided to
    allow yet (that itself leaks info)."""
    if not host:
        return True
    h = host.lower().strip()
    if h in _BLOCKED_HOSTS_EXACT:
        return True
    if any(h.startswith(p) for p in _BLOCKED_HOST_PREFIXES):
        return True
    # 172.16.0.0/12 private block — 172.16..172.31
    if h.startswith("172."):
        try:
            second = int(h.split(".", 2)[1])
            if 16 <= second <= 31:
                return True
        except Exception:
            return True
    return False


def _safe_url(url):
    """Return (ok, reason). Reject disallowed schemes, empty hosts, and
    private/loopback/metadata destinations. Applied before every
    model-driven urlopen."""
    try:
        parsed = urllib.parse.urlparse(url or "")
    except Exception as e:
        return False, f"invalid url: {e}"
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        return False, f"scheme '{parsed.scheme}' not allowed (http/https only)"
    host = parsed.hostname or ""
    if not host:
        return False, "missing host"
    if _host_is_blocked(host):
        return False, f"host '{host}' is private/loopback/metadata; refused"
    return True, "ok"


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Cap redirects at 5 and re-validate the target URL on each hop.
    Anything that tries to redirect to file:// or an internal IP raises
    instead of silently following."""
    max_redirections = 5
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ok, reason = _safe_url(newurl)
        if not ok:
            raise urllib.error.URLError(f"unsafe redirect blocked ({reason})")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_SAFE_OPENER = urllib.request.build_opener(_SafeRedirectHandler())


_DDG_URL = "https://html.duckduckgo.com/html/"
# Honest identifying User-Agent. The DDG HTML endpoint accepts non-browser
# UAs at conversational volumes, and most target sites respect a clear
# bot identifier far better than a spoofed Chrome string. If DDG starts
# rejecting this UA, the right answer is to swap to their Instant Answer
# API (keyless) — not to resume impersonating a browser.
_DDG_UA  = f"Blender-Buddy/{ADDON_VERSION[0]}.{ADDON_VERSION[1]}.{ADDON_VERSION[2]} (+https://blender-buddy.local)"

# Result block layout: <a class="result__a" href="URL">Title</a> then a
# later <a|td class="result__snippet">Snippet</a>. We match on both via a
# non-greedy DOTALL regex. Tolerates small attribute-order changes.
_DDG_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)

_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _ddg_clean(html_text):
    """Strip inner tags (<b>, <em>) and decode entities in a result field."""
    return _htmllib.unescape(_HTML_TAG_RE.sub('', html_text)).strip()


def _ddg_decode_url(href):
    """DDG wraps outbound URLs as //duckduckgo.com/l/?uddg=<encoded>. Unwrap
    to the real URL so we can show it to the user and cite it to the model."""
    try:
        if href.startswith('//'):
            href = 'https:' + href
        parsed = urllib.parse.urlparse(href)
        if parsed.path.rstrip('/').endswith('/l'):
            qs = urllib.parse.parse_qs(parsed.query)
            if 'uddg' in qs and qs['uddg']:
                return urllib.parse.unquote(qs['uddg'][0])
    except Exception:
        pass
    return href


def _do_web_search(query, n_results=5, timeout=12):
    """Return [(title, url, snippet), ...] or [] on any failure.

    Runs on the worker thread (called from worker_ask). Never raises —
    search is best-effort context; if it fails the question is still sent
    to the model without web context."""
    try:
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            _DDG_URL, data=data,
            headers={
                "User-Agent": _DDG_UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html_body = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[Blender Buddy] web search request failed: {e}")
        return []

    results = []
    for m in _DDG_RESULT_RE.finditer(html_body):
        href, title_html, snippet_html = m.group(1), m.group(2), m.group(3)
        title   = _ddg_clean(title_html)
        snippet = _ddg_clean(snippet_html)
        url     = _ddg_decode_url(href)
        if title and url:
            results.append((title, url, snippet))
        if len(results) >= n_results:
            break
    if not results:
        # Anomaly page / layout change / empty query — log once, return
        # empty so the ask flow proceeds without search context.
        print(f"[Blender Buddy] web search returned no results "
              f"(HTML {len(html_body)} bytes)")
    return results


_PAGE_DROP_TAGS_RE = re.compile(
    r'<(script|style|noscript|nav|footer|aside|header|form|svg)[^>]*>.*?</\1>',
    re.DOTALL | re.IGNORECASE,
)


def _fetch_page_text(url, timeout=8, max_chars=3500):
    """Fetch a URL and extract a crude plain-text digest of its body.

    Naive on purpose — we can't ship BeautifulSoup and JS-heavy pages
    won't fully render. But for YouTube channel pages, docs sites, forum
    threads, GitHub issues, RSS feeds, etc., the visible server-rendered
    text is enough to answer questions like "what's the newest video" or
    "what's the release date". Capped per page so a single huge document
    can't blow out the context window."""
    ok, reason = _safe_url(url)
    if not ok:
        print(f"[Blender Buddy] page fetch refused {url}: {reason}")
        return ""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent":      _DDG_UA,
            "Accept":          "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with _SAFE_OPENER.open(req, timeout=timeout) as r:
            body = r.read(500_000).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[Blender Buddy] page fetch failed {url}: {e}")
        return ""

    # Drop chrome tags in full (their text content is never useful context).
    body = _PAGE_DROP_TAGS_RE.sub(' ', body)
    # Strip everything remaining to plain text.
    text = _HTML_TAG_RE.sub(' ', body)
    text = _htmllib.unescape(text)
    # Collapse runs of whitespace.
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


_PAGE_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\'#]+)["\'][^>]*>',
    re.IGNORECASE,
)


def _extract_page_links(body, base_url, max_links=3):
    """Pull a handful of outbound http(s) links from a raw HTML body.
    Filters to absolute URLs only (no fragments, no relative links) and
    dedupes by URL. Used for nested-rounds search to follow interesting
    links from a fetched page."""
    out = []
    seen = {base_url}
    for m in _PAGE_LINK_RE.finditer(body or ""):
        href = m.group(1).strip()
        # Absolute http(s) only — skip data:, mailto:, relative paths.
        if not (href.startswith("http://") or href.startswith("https://")):
            continue
        # Drop trailing punctuation that sometimes hitches a ride.
        while href and href[-1] in ').,;:\"\'':
            href = href[:-1]
        if href in seen:
            continue
        seen.add(href)
        out.append(href)
        if len(out) >= max_links:
            break
    return out


# --- Generic JS-heavy-site safety net ---------------------------------
# A lot of modern pages (YouTube, Reddit, news sites, blogs) server-
# render their "shell" in HTML but keep the actual payload (video list,
# post list, article body) elsewhere:
#   1. <link rel="alternate" type="application/rss+xml" href="…"> in the
#      <head> — points to a plain-XML feed with titles + dates
#   2. <script type="application/ld+json"> — schema.org structured data
#      with headlines, upload dates, article bodies, etc.
# We scan every fetched page for both. No site-specific code — if a
# domain exposes either of these, we get the good data for free.

_FEED_LINK_RE = re.compile(
    r'<link\b[^>]*\btype\s*=\s*["\']application/(?:rss|atom)\+xml["\'][^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'\bhref\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

_FEED_ITEM_RE = re.compile(
    r'<(item|entry)\b[^>]*>(.*?)</\1>',
    re.DOTALL | re.IGNORECASE,
)
_FEED_TITLE_RE = re.compile(
    r'<title\b[^>]*>(.*?)</title>', re.DOTALL | re.IGNORECASE,
)
_FEED_DATE_RE = re.compile(
    r'<(?:pubDate|published|updated|dc:date)\b[^>]*>(.*?)'
    r'</(?:pubDate|published|updated|dc:date)>',
    re.DOTALL | re.IGNORECASE,
)
_FEED_LINK_HREF_RE   = re.compile(
    r'<link\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE,
)
_FEED_LINK_TEXT_RE   = re.compile(
    r'<link\b[^>]*>\s*([^<\s][^<]*?)\s*</link>', re.IGNORECASE,
)
_CDATA_RE = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.DOTALL)

_LDJSON_RE = re.compile(
    r'<script\b[^>]*\btype\s*=\s*["\']application/ld\+json["\'][^>]*>'
    r'(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# JSON-LD fields worth extracting. Order matters — headline first
# because news articles bury it.
_LDJSON_KEYS = (
    "headline", "name", "title",
    "datePublished", "dateModified", "uploadDate",
    "duration",
    "author", "creator",
    "description",
    "articleBody", "articleSection",
)

# Open Graph / meta tags. This is where YouTube video pages put the
# title + description (among many other sites). Parse every <meta> tag
# regardless of attribute order (property vs name vs itemprop, content
# first or second).
_META_TAG_RE = re.compile(r'<meta\b([^>]*?)/?>', re.IGNORECASE)
_META_ATTR_RE = re.compile(
    r'(\w[\w:-]*)\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)
# Meta keys we care about, in display order.
_META_KEYS_PRIORITY = (
    "og:site_name", "og:type",
    "og:title", "title", "twitter:title",
    "og:description", "description", "twitter:description",
    "og:video:title", "og:video:description", "og:video:duration",
    "article:author", "author",
    "article:published_time", "article:modified_time",
    "article:section", "article:tag",
)


def _absolutize(url, base_url):
    """Turn //x, /x, or bare x paths into absolute URLs relative to base."""
    if url.startswith("//"):
        scheme = base_url.split("://", 1)[0] if "://" in base_url else "https"
        return f"{scheme}:{url}"
    if url.startswith("/"):
        p = urllib.parse.urlparse(base_url)
        return f"{p.scheme}://{p.netloc}{url}"
    return url


def _discover_feed_urls(html, base_url, max_feeds=2):
    """Find RSS/Atom feed links declared in the page's <head>."""
    urls, seen = [], set()
    for m in _FEED_LINK_RE.finditer(html or ""):
        href_m = _HREF_RE.search(m.group(0))
        if not href_m:
            continue
        u = _htmllib.unescape(href_m.group(1)).strip()
        if not u or u.startswith(("data:", "mailto:", "javascript:")):
            continue
        u = _absolutize(u, base_url)
        if not u.startswith(("http://", "https://")):
            continue
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= max_feeds:
            break
    return urls


def _clean_feed_text(text):
    """Strip CDATA + inner HTML + entities from a feed field."""
    text = _CDATA_RE.sub(r'\1', text or "")
    text = _HTML_TAG_RE.sub('', text)
    return _htmllib.unescape(text).strip()


def _fetch_and_format_feed(feed_url, timeout=8, max_items=12):
    """Fetch an RSS or Atom feed and flatten it to a plain-text block.
    Handles both RSS (<item><pubDate>) and Atom (<entry><published>).
    Returns "" on any failure."""
    ok, reason = _safe_url(feed_url)
    if not ok:
        print(f"[Blender Buddy] feed fetch refused {feed_url}: {reason}")
        return ""
    try:
        req = urllib.request.Request(feed_url, headers={
            "User-Agent": _DDG_UA,
            "Accept":     "application/rss+xml, application/atom+xml, "
                          "application/xml, text/xml",
        })
        with _SAFE_OPENER.open(req, timeout=timeout) as r:
            xml = r.read(500_000).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[Blender Buddy] feed fetch failed {feed_url}: {e}")
        return ""
    lines = [f"FEED ({feed_url}) — newest first:"]
    for m in _FEED_ITEM_RE.finditer(xml):
        block = m.group(2)
        title = (_FEED_TITLE_RE.search(block) or [None, ""])
        title = _clean_feed_text(title.group(1)) if title and hasattr(title, 'group') else ""
        date_m  = _FEED_DATE_RE.search(block)
        date    = _clean_feed_text(date_m.group(1))[:10] if date_m else ""
        link    = ""
        lm = _FEED_LINK_HREF_RE.search(block)  # Atom-style: <link href="…"/>
        if lm:
            link = lm.group(1).strip()
        else:
            lm = _FEED_LINK_TEXT_RE.search(block)  # RSS-style: <link>…</link>
            if lm:
                link = lm.group(1).strip()
        if not title:
            continue
        row = f"- {date} — {title}" if date else f"- {title}"
        if link:
            row += f" — {link}"
        lines.append(row)
        if len(lines) - 1 >= max_items:
            break
    return "\n".join(lines) if len(lines) > 1 else ""


def _extract_meta_summary(html, max_chars=900):
    """Extract Open Graph + <meta> tag summary. YouTube video pages put
    the video title/description here (not JSON-LD), and it's where most
    modern social-shared content exposes its key metadata. No site-
    specific code: works for any page with standard meta tags."""
    if not html:
        return ""
    found = {}
    for m in _META_TAG_RE.finditer(html):
        attrs = dict(_META_ATTR_RE.findall(m.group(1)))
        key = (attrs.get('property')
               or attrs.get('name')
               or attrs.get('itemprop') or '').lower()
        val = _htmllib.unescape(attrs.get('content', '')).strip()
        if key and val and key not in found:
            found[key] = val
    if not found:
        return ""
    lines = []
    seen = set()
    for key in _META_KEYS_PRIORITY:
        if key in found and found[key]:
            lines.append(f"{key}: {found[key][:400]}")
            seen.add(key)
    if not lines:
        return ""
    out = "META / OPENGRAPH:\n" + "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars] + "…"
    return out


def _extract_ldjson_summary(html, max_items=6, max_total_chars=1500):
    """Pull headlines / dates / descriptions out of <script type=
    application/ld+json> blocks. Works across news articles, blog posts,
    product pages, videos — anything with schema.org structured data."""
    found = []
    for m in _LDJSON_RE.finditer(html or ""):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            # Some CMSes (WordPress in particular) HTML-entity-escape
            # their JSON-LD payloads (e.g. `&quot;` for `"`). Retry after
            # unescape so we don't drop structured data from those pages.
            try:
                data = json.loads(_htmllib.unescape(raw))
            except Exception:
                continue
        # JSON-LD can be an object, a list, or a {"@graph": [...]} wrapper.
        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            if isinstance(data.get("@graph"), list):
                candidates = data["@graph"]
            else:
                candidates = [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            tval = obj.get("@type", "")
            if isinstance(tval, list):
                tval = "/".join(str(x) for x in tval)
            summary = []
            for key in _LDJSON_KEYS:
                v = obj.get(key)
                if isinstance(v, dict):
                    # Common nested pattern: {"@type":"Person","name":"X"}
                    v = v.get("name") or v.get("@id") or ""
                if isinstance(v, list) and v:
                    v = v[0]
                    if isinstance(v, dict):
                        v = v.get("name") or ""
                if isinstance(v, str) and v.strip():
                    summary.append(f"{key}={v.strip()[:200]}")
            if summary:
                found.append(f"[{tval or 'Thing'}] " + "; ".join(summary))
            if len(found) >= max_items:
                break
        if len(found) >= max_items:
            break
    if not found:
        return ""
    out = "STRUCTURED DATA (JSON-LD):\n" + "\n".join(found)
    if len(out) > max_total_chars:
        out = out[:max_total_chars] + "…"
    return out


def _fetch_page_text_and_raw(url, timeout=8, max_chars=3500):
    """Fetch url, extract plain text + (where available) RSS feed
    content and JSON-LD structured data. Returns (text, raw_html) where
    `text` is a best-effort digest combining all three sources and
    `raw_html` is kept for round-2+ link extraction."""
    ok, reason = _safe_url(url)
    if not ok:
        print(f"[Blender Buddy] page fetch refused {url}: {reason}")
        return "", ""
    truncated_marker = ""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent":      _DDG_UA,
            "Accept":          "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with _SAFE_OPENER.open(req, timeout=timeout) as r:
            # Read one byte past the cap so we can detect truncation.
            # HuggingFace, news homepages, GH issues with long threads
            # all blow past 500 KB; the model otherwise sees no hint it
            # was served a partial page.
            raw_bytes = r.read(500_001)
            total_hint = int(r.headers.get("Content-Length") or 0)
            raw = raw_bytes[:500_000].decode("utf-8", errors="replace")
            if len(raw_bytes) > 500_000:
                if total_hint > 500_000:
                    truncated_marker = (
                        f"[truncated: showing first 500 KB of "
                        f"{total_hint / 1024:.0f} KB]\n"
                    )
                else:
                    truncated_marker = "[truncated: showing first 500 KB]\n"
    except Exception as e:
        print(f"[Blender Buddy] page fetch failed {url}: {e}")
        return "", ""

    # 1) Plain-text body extraction (same as before).
    body = _PAGE_DROP_TAGS_RE.sub(' ', raw)
    body_text = _HTML_TAG_RE.sub(' ', body)
    body_text = _htmllib.unescape(body_text)
    body_text = re.sub(r'\s+', ' ', body_text).strip()

    # 2) Open Graph / meta tags. This is where YouTube video pages put
    #    title + description (no JSON-LD on video pages reliably). Also
    #    covers news, blogs, product pages — any social-shared content.
    meta_text = _extract_meta_summary(raw)

    # 3) JSON-LD structured data (if any). Cheap — already in HTML.
    ldjson_text = _extract_ldjson_summary(raw)

    # 4) RSS/Atom feeds auto-discovered in <head>. Extra HTTP — capped
    #    to 2 feeds per page so we don't fan out.
    feed_texts = []
    for feed_url in _discover_feed_urls(raw, url):
        t = _fetch_and_format_feed(feed_url)
        if t:
            feed_texts.append(t)
        if sum(len(x) for x in feed_texts) > 1800:
            break

    # Assemble. Feeds first (juiciest "what's new" data), then OG/meta
    # (reliable title + description), then JSON-LD, then the plain-text
    # body. Global cap is max_chars + slack for the extras so the body
    # still gets meaningful room on pages where the extras are absent.
    parts = []
    if feed_texts:
        block = "\n\n".join(feed_texts)
        if len(block) > 1500:
            block = block[:1500] + "…"
        parts.append(block)
    if meta_text:
        parts.append(meta_text)
    if ldjson_text:
        parts.append(ldjson_text)

    if len(body_text) > max_chars:
        body_text = body_text[:max_chars] + "…"
    parts.append(body_text)

    text = "\n\n".join(p for p in parts if p)
    if truncated_marker:
        text = truncated_marker + text
    return text, raw


# ---------------------------------------------------------------------------
# Agentic tools (model-driven — v9)
# ---------------------------------------------------------------------------
#
# Three functions exposed to the model via OpenAI-compatible tool calling.
# The model decides when to invoke them; the addon executes each call and
# feeds the result back as a "tool" role message. The loop ends when the
# model emits a plain-content response (no tool_calls).
#
#   search_web(query) -> top DDG results (title / url / snippet)
#   fetch_url(url)    -> plain-text digest of a page (+ OpenGraph / JSON-LD
#                        / auto-discovered RSS feeds)
#   get_scene()       -> snapshot of the current .blend (captured once on
#                        the main thread before the worker starts)
#
# llama-server needs `--jinja` to parse tool_calls from the Qwen chat
# template into structured OpenAI output — see start_server().

# ---------------------------------------------------------------------------
# API index (RAG) — reads the JSONL produced by the Buddy Builder addon
# and serves lexical search hits to the model through the `search_api`
# tool. The file and its meta sidecar are written by buddy_builder.py at
# DATAFILES/blender_buddy/api_index.jsonl; if the user hasn't built one
# yet, the tool is simply withheld from the schema rather than returning
# empty hits that waste a tool round.
# ---------------------------------------------------------------------------

def user_api_index_path():
    """Writable user copy — what Buddy Builder generates/updates."""
    return os.path.join(data_root(), "api_index.jsonl")


def shipped_api_index_path():
    """Pre-built index bundled with the addon for first-run users who
    haven't run Buddy Builder themselves. Living under
    blender_buddy_assets/ means it ships with the addon and survives
    script reloads."""
    return os.path.join(addon_assets_dir(), "api_index.jsonl")


def api_index_path():
    """Preferred index path — user's runtime copy wins when it exists,
    otherwise fall back to the shipped snapshot. Callers treat it as a
    single logical file; the two-tier resolution is an impl detail."""
    user = user_api_index_path()
    if os.path.isfile(user):
        return user
    shipped = shipped_api_index_path()
    if os.path.isfile(shipped):
        return shipped
    return user  # doesn't exist; api_index_available() handles that


def api_index_available():
    for p in (user_api_index_path(), shipped_api_index_path()):
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return True
        except OSError:
            continue
    return False


# Token splitter that handles both camelCase (ShaderNodeBsdfPrincipled →
# shader / node / bsdf / principled) and snake_case / dotted paths
# (bpy.ops.mesh.primitive_cube_add → bpy / ops / mesh / primitive / cube /
# add). Lowercased. Also keeps standalone digits for version tokens.
_API_TOKEN_RE = re.compile(
    r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|[^A-Za-z]|$)|[0-9]+'
)


def _api_tokenize(text):
    if not text:
        return ()
    return tuple(t.lower() for t in _API_TOKEN_RE.findall(text))


# In-memory cache. Reloads when the file's mtime changes — avoids paying
# the ~200 ms parse cost on every ask while still picking up a rebuild
# without a Blender restart.
_api_cache = {
    "mtime":    0,
    "entries":  [],    # list of dict (parsed JSON lines)
    "postings": {},    # token -> list[entry_idx]
    "docs":     [],    # per-entry concatenated searchable text (lowered)
}
_api_cache_lock = threading.Lock()


def _entry_searchable_text(e):
    """Flatten one index entry into a single string for tokenizing. Covers
    the path + name + description, plus parameter/property/enum names (but
    not their values). Templates contribute their full source — that's
    what lets a query like 'modal raycast' match the view3d_raycast
    template file."""
    parts = [e.get("path") or "", e.get("name") or "",
             e.get("description") or "", e.get("doc") or ""]
    for key in ("parameters", "properties", "functions", "members"):
        items = e.get(key) or ()
        for item in items:
            if isinstance(item, dict):
                n = item.get("name")
                if n:
                    parts.append(n)
                for ei in item.get("enum_items") or ():
                    if isinstance(ei, dict):
                        eid = ei.get("id")
                        if eid:
                            parts.append(eid)
    for base in e.get("bases") or ():
        parts.append(base)
    if e.get("kind") == "template":
        # Templates are whole .py files — include the source so a query
        # like "depsgraph handler" can find driver_functions.py even
        # though the body has no schema-style identifiers at the top.
        parts.append(e.get("code") or "")
    return " ".join(parts)


def _load_api_index():
    """Load or refresh the cached index. Safe to call from worker threads;
    the lock serialises the parse, subsequent readers get the same snapshot.
    Returns True on success, False if the file is missing or malformed."""
    path = api_index_path()
    try:
        st = os.stat(path)
    except OSError:
        return False
    with _api_cache_lock:
        if _api_cache["mtime"] == st.st_mtime and _api_cache["entries"]:
            return True
        entries = []
        docs = []
        postings = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    entries.append(e)
                    text = _entry_searchable_text(e)
                    docs.append(text.lower())
                    for tok in set(_api_tokenize(text)):
                        postings.setdefault(tok, []).append(i)
        except OSError:
            return False
        _api_cache.update(
            mtime=st.st_mtime, entries=entries, docs=docs, postings=postings,
        )
    print(f"[Blender Buddy] api_index loaded: "
          f"{len(entries)} entries, {len(postings)} tokens")
    return True


def _format_hit(entry, max_chars=700):
    """One compact text block for a single hit. Keeps the model's context
    cheap: path + description + a sampling of parameters/enum values, or
    a short template excerpt. Never returns more than max_chars."""
    lines = []
    path = entry.get("path") or "?"
    kind = entry.get("kind") or "?"
    name = entry.get("name") or ""
    header = f"{path}  [{kind}]"
    if name and name != path.rsplit(".", 1)[-1]:
        header += f"  — {name}"
    lines.append(header)
    desc = entry.get("description") or entry.get("doc") or ""
    if desc:
        lines.append(desc.strip().splitlines()[0][:240])

    if kind in ("operator", "type"):
        params_key = "parameters" if kind == "operator" else "properties"
        items = entry.get(params_key) or []
        for p in items[:12]:
            bits = [p.get("name", "?"), f"({p.get('type', '?').lower()})"]
            if p.get("required"):
                bits.append("required")
            ei = p.get("enum_items") or []
            if ei:
                ids = ", ".join((it.get("id") or "")
                                for it in ei[:8] if it.get("id"))
                bits.append(f"enum: {ids}" + ("…" if len(ei) > 8 else ""))
            if "default" in p and not ei:
                bits.append(f"default={p['default']!r}")
            lines.append("  - " + " ".join(bits))
        if len(items) > 12:
            lines.append(f"  … +{len(items) - 12} more")
        for fn in (entry.get("functions") or [])[:6]:
            lines.append(f"  · fn {fn.get('name', '?')}()")
        bases = entry.get("bases") or []
        if bases:
            lines.append("  bases: " + " ← ".join(bases[:4]))

    elif kind == "function":
        sig = entry.get("signature") or ""
        if sig:
            lines.append(f"  signature: {sig}")

    elif kind == "class":
        for m in (entry.get("members") or [])[:10]:
            sig = m.get("signature") or ""
            lines.append(f"  · {m.get('name','?')}{sig}")
        if len(entry.get("members") or []) > 10:
            lines.append(f"  … +{len(entry['members']) - 10} more")

    elif kind == "template":
        code = entry.get("code") or ""
        # First ~30 non-blank lines is usually enough to show the
        # register() / class skeleton that makes a template useful.
        kept = []
        for ln in code.splitlines():
            kept.append(ln)
            if len(kept) >= 30:
                break
        lines.append("```python")
        lines.extend(kept)
        if len(code.splitlines()) > 30:
            lines.append(f"# … +{len(code.splitlines()) - 30} more lines")
        lines.append("```")

    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[:max_chars - 1].rstrip() + "…"
    return block


def _search_api_index(query, n_results=5):
    """Return a list of formatted hit blocks (strings). Ranking is a
    simple token-coverage score with boosts for matches inside the `path`
    field (canonical identifier hits should outrank incidental
    description hits)."""
    if not _load_api_index():
        return []
    tokens = list(set(_api_tokenize(query)))
    if not tokens:
        return []
    entries  = _api_cache["entries"]
    docs     = _api_cache["docs"]
    postings = _api_cache["postings"]
    # Also check for the full query as a substring — catches dotted paths
    # like "bpy.ops.mesh.primitive_cube_add" that the tokenizer fragments
    # into many tokens but are most valuable as an exact hit.
    needle = query.strip().lower()
    scores = {}
    for tok in tokens:
        for idx in postings.get(tok, ()):
            scores[idx] = scores.get(idx, 0.0) + 1.0
    # Phrase / substring boost
    if len(needle) >= 3:
        for idx, doc in enumerate(docs):
            if needle in doc:
                scores[idx] = scores.get(idx, 0.0) + 2.5
    # Path-level boost: if a query token appears inside the entry's path,
    # it's almost certainly the identifier the user is actually asking
    # about — weight those above description-only matches.
    for idx in list(scores.keys()):
        path = (entries[idx].get("path") or "").lower()
        for tok in tokens:
            if tok in path:
                scores[idx] += 1.5
    if not scores:
        return []
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    hits = []
    for idx, _s in ranked[:n_results]:
        hits.append(_format_hit(entries[idx]))
    return hits


TOOL_SEARCH_API = {
    "type": "function",
    "function": {
        "name": "search_api",
        "description": (
            "Search the local Blender Python API index (operators, RNA "
            "types, bpy.props / mathutils / bmesh / gpu modules, plus the "
            "shipped scripts/templates_py examples). ALWAYS call this "
            "before writing bpy code or naming an operator / property / "
            "method you aren't 100% sure of — it returns exact "
            "identifiers, parameter names, enum values, and template "
            "snippets. Prefer this over search_web for Blender API "
            "questions: it's local, instant, and verbatim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search terms. Can be a dotted path "
                        "('bpy.ops.mesh.primitive_cube_add'), a partial "
                        "identifier ('principled bsdf'), or a concept "
                        "('modal raycast template', 'depsgraph handler')."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


TOOL_SEARCH_WEB = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the web via DuckDuckGo. Use whenever you are not "
            "certain — operator names, property paths, version-specific "
            "Blender facts, current events. Returns top results as "
            "title + url + snippet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
            },
            "required": ["query"],
        },
    },
}

TOOL_FETCH_URL = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": (
            "Fetch an http(s) URL and return its plain-text body plus "
            "any auto-discovered RSS feed content, OpenGraph, and "
            "JSON-LD metadata. Use when a search snippet isn't enough "
            "— e.g., to read a docs page or forum thread."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full http(s) URL.",
                },
            },
            "required": ["url"],
        },
    },
}

TOOL_GET_SCENE = {
    "type": "function",
    "function": {
        "name": "get_scene",
        "description": (
            "High-level snapshot of the current .blend: Blender version, "
            "scene + render settings (engine, resolution, fps, frame "
            "range, units), active workspace + area, mode, active object "
            "(with transform, modifiers, materials, mesh stats), "
            "selected objects, bpy.data collection counts, enabled "
            "addons. Call before scene-specific answers. For one "
            "specific object's full details, use get_object_info."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_GET_OBJECT_INFO = {
    "type": "function",
    "function": {
        "name": "get_object_info",
        "description": (
            "Deep inspection of a single object by name. Returns type, "
            "full transform, dimensions, parent, collections, all "
            "modifier settings, all constraints, material slots, "
            "vertex groups, animation action (if any), custom "
            "properties, and data-block summary (mesh stats, curve "
            "splines, etc)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "Object name as it appears in bpy.data.objects."},
            },
            "required": ["name"],
        },
    },
}

TOOL_GET_SELECTION = {
    "type": "function",
    "function": {
        "name": "get_selection",
        "description": (
            "What the user has selected RIGHT NOW: mode, active object, "
            "all selected objects, and — if in edit mode — per-element "
            "selection counts (verts/edges/faces for meshes, splines "
            "for curves, bones for armatures)."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_GET_NODE_TREE = {
    "type": "function",
    "function": {
        "name": "get_node_tree",
        "description": (
            "Dump the node graph of a material, world, or node group. "
            "Returns node list (name, type, key settings) and links "
            "(from → to socket paths). Use to understand or modify an "
            "existing shader / compositor / geometry-node setup."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": (
                             "Material name, world name, or node-group "
                             "(bpy.data.node_groups) name."
                         )},
            },
            "required": ["name"],
        },
    },
}

TOOL_LIST_INFO_LOG = {
    "type": "function",
    "function": {
        "name": "list_info_log",
        "description": (
            "Recent lines captured from Blender's stderr — operator "
            "errors, warnings, and Python exceptions. Use when "
            "debugging 'why did my last op fail' or investigating a "
            "recent crash / traceback."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "n": {"type": "integer",
                      "description": "How many most-recent lines to return (default 40, max 200)."},
            },
        },
    },
}

TOOL_ASK_USER = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Ask the user a clarifying question when the request is "
            "ambiguous enough that answering would be guessing. Use "
            "SPARINGLY — only when a wrong guess would waste their "
            "time. The question becomes your final response; the loop "
            "stops and the user replies in the next turn. Examples of "
            "good use: 'Boolean modifier or Boolean node?', 'Which of "
            "the 3 cameras do you mean?'. Do NOT use for minor "
            "preferences ('what color?') — pick a sensible default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string",
                             "description": "A single clear question, one sentence."},
            },
            "required": ["question"],
        },
    },
}

TOOL_LIST_DATABLOCKS = {
    "type": "function",
    "function": {
        "name": "list_datablocks",
        "description": (
            "Enumerate a single bpy.data collection — returns its count "
            "and verbatim names. NEVER invent or pattern-guess datablock "
            "names ('Image.001', 'Material.001' etc.) — get_scene only "
            "shows counts, so if the user wants names you MUST call this "
            "first. For deep inspection of one object use "
            "get_object_info; for a node tree use get_node_tree. Known "
            "types: objects, materials, meshes, node_groups, actions, "
            "images, textures, collections, scenes, worlds, cameras, "
            "lights, armatures, curves, texts, brushes, particles, "
            "libraries, fonts, sounds, movieclips, masks, linestyles, "
            "grease_pencils."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string",
                         "description": "A bpy.data collection name (e.g. 'objects', 'materials')."},
            },
            "required": ["type"],
        },
    },
}

TOOL_GET_TIMELINE = {
    "type": "function",
    "function": {
        "name": "get_timeline",
        "description": (
            "Timeline + playback settings of the current scene: "
            "frame_start/end/current, frame_step, FPS and FPS base "
            "(real fps = fps/fps_base), use_preview_range with preview "
            "start/end if active, sync_mode. Call before any animation "
            "timing question, scripted bake range, or frame-indexed "
            "logic."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_GET_ANIMATION_DATA = {
    "type": "function",
    "function": {
        "name": "get_animation_data",
        "description": (
            "Animation data for a named object, action, or mesh's shape "
            "keys. Returns assigned action, F-curves (data_path, "
            "array_index, keyframe count, first/last frame, interp "
            "summary), NLA tracks + strips, and drivers. `kind` selects "
            "which bpy.data collection to consult; 'auto' tries objects "
            "→ actions → shape_keys (keyed by mesh name)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "Name to look up (object / action / mesh-with-shape-keys)."},
                "kind": {"type": "string",
                         "enum": ["auto", "object", "action", "shape_keys"],
                         "description": "Which namespace to consult. Default 'auto'."},
            },
            "required": ["name"],
        },
    },
}

TOOL_GET_RENDER_SETTINGS = {
    "type": "function",
    "function": {
        "name": "get_render_settings",
        "description": (
            "Structured render config: engine, resolution x/y/%, pixel "
            "aspect, frame range, output filepath + file_format + image "
            "settings, film_transparent, motion blur. Cycles block: "
            "samples, preview_samples, adaptive, denoiser, device, "
            "time_limit. EEVEE block: TAA samples (viewport + render), "
            "raytracing, GTAO. Color management: view transform, look, "
            "exposure, gamma, display_device. Use for any render-config "
            "question — the get_scene summary is just a one-liner."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_GET_VIEWPORT_STATE = {
    "type": "function",
    "function": {
        "name": "get_viewport_state",
        "description": (
            "Current UI state: active workspace, current area type, "
            "3D viewport shading mode (SOLID/MATERIAL/RENDERED/"
            "WIREFRAME) + overlay flags + gizmo visibility, camera / "
            "perspective / orthographic state, local view, camera in "
            "use, unit system (system, length_unit, scale, rotation), "
            "active WorkSpaceTool.idname. Use when tailoring UI "
            "instructions or when the question concerns viewport "
            "display rather than scene data."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def _build_tools_schema(allow_online):
    """Per-request tool list. `get_scene` / get_object_info / get_selection
    / get_node_tree / list_info_log / ask_user are always available
    (local, free). `search_api` is included when the Buddy Builder index
    exists on disk — withholding it when there's no index avoids wasted
    tool rounds. `allow_online` gates the two web tools (addon-level
    pref)."""
    tools = [
        TOOL_GET_SCENE,
        TOOL_GET_OBJECT_INFO,
        TOOL_GET_SELECTION,
        TOOL_GET_NODE_TREE,
        TOOL_LIST_INFO_LOG,
        TOOL_ASK_USER,
        TOOL_LIST_DATABLOCKS,
        TOOL_GET_TIMELINE,
        TOOL_GET_ANIMATION_DATA,
        TOOL_GET_RENDER_SETTINGS,
        TOOL_GET_VIEWPORT_STATE,
    ]
    if api_index_available():
        tools.append(TOOL_SEARCH_API)
    if allow_online:
        tools.append(TOOL_SEARCH_WEB)
        tools.append(TOOL_FETCH_URL)
    return tools


def _execute_tool(name, args, scene_snapshot):
    """Run a single tool call and return a stringified result. Never
    raises — errors come back as readable '(tool error: …)' messages so
    the model can react instead of the whole ask crashing."""
    try:
        if name == "search_web":
            query = (args.get("query") or "").strip()
            if not query:
                return "(empty query)"
            results = _do_web_search(query, n_results=6)
            if not results:
                return "(no results)"
            lines = []
            for i, (title, url, snippet) in enumerate(results, 1):
                lines.append(f"[{i}] {title}\n    {url}\n    {snippet}")
            return "\n".join(lines)

        if name == "fetch_url":
            url = (args.get("url") or "").strip()
            if not url:
                return "(missing url)"
            text, _raw = _fetch_page_text_and_raw(url, max_chars=5000)
            return text or "(empty or failed to fetch)"

        if name == "get_scene":
            if isinstance(scene_snapshot, dict):
                return scene_snapshot.get("summary") or "(scene info unavailable)"
            return scene_snapshot or "(scene info unavailable)"

        if name == "get_object_info":
            obj_name = (args.get("name") or "").strip()
            if not obj_name:
                return "(missing 'name')"
            if isinstance(scene_snapshot, dict):
                obj_infos = scene_snapshot.get("objects") or {}
                info = obj_infos.get(obj_name)
                if info is not None:
                    return info
                names = list(obj_infos.keys())
                return (f"(no object '{obj_name}' in scene. Available: "
                        + ", ".join(names[:30])
                        + (" …" if len(names) > 30 else "") + ")")
            return "(object lookup unavailable — no scene snapshot)"

        if name == "get_selection":
            if isinstance(scene_snapshot, dict):
                return scene_snapshot.get("selection") or "(nothing selected)"
            return "(selection unavailable — no scene snapshot)"

        if name == "get_node_tree":
            tree_name = (args.get("name") or "").strip()
            if not tree_name:
                return "(missing 'name')"
            if isinstance(scene_snapshot, dict):
                trees = scene_snapshot.get("node_trees") or {}
                t = trees.get(tree_name)
                if t is not None:
                    return t
                return (f"(no node tree '{tree_name}'. Known: "
                        + ", ".join(list(trees.keys())[:20]) + ")")
            return "(node-tree lookup unavailable — no scene snapshot)"

        if name == "list_datablocks":
            dtype = (args.get("type") or "").strip().lower()
            if not dtype:
                return "(missing 'type')"
            if isinstance(scene_snapshot, dict):
                db = scene_snapshot.get("datablocks") or {}
                entry = db.get(dtype)
                if entry is None:
                    return (f"(unknown type '{dtype}'. Known: "
                            + ", ".join(sorted(db.keys())) + ")")
                names = entry.get("names") or []
                count = entry.get("count", len(names))
                preview = names[:60]
                extra = f"\n  …+{len(names)-60} more" if len(names) > 60 else ""
                if not preview:
                    return f"bpy.data.{dtype}  count={count}  (empty)"
                return (f"bpy.data.{dtype}  count={count}\n"
                        + "\n".join(f"  '{n}'" for n in preview) + extra)
            return "(datablock lookup unavailable — no scene snapshot)"

        if name == "get_timeline":
            if isinstance(scene_snapshot, dict):
                return scene_snapshot.get("timeline") or "(timeline unavailable)"
            return "(timeline unavailable — no scene snapshot)"

        if name == "get_animation_data":
            target = (args.get("name") or "").strip()
            kind = (args.get("kind") or "auto").strip().lower()
            if not target:
                return "(missing 'name')"
            if isinstance(scene_snapshot, dict):
                anim = scene_snapshot.get("animation") or {}
                order = {
                    "auto":       ("objects", "actions", "shape_keys"),
                    "object":     ("objects",),
                    "action":     ("actions",),
                    "shape_keys": ("shape_keys",),
                }.get(kind, ("objects", "actions", "shape_keys"))
                for ns in order:
                    v = (anim.get(ns) or {}).get(target)
                    if v is not None:
                        return f"[{ns}] {v}"
                known = []
                for ns in ("objects", "actions", "shape_keys"):
                    for n in list((anim.get(ns) or {}).keys())[:15]:
                        known.append(f"{ns}/{n}")
                return (f"(no animation data for '{target}' in kind={kind}. "
                        f"Known: " + ", ".join(known) + ")")
            return "(animation lookup unavailable — no scene snapshot)"

        if name == "get_render_settings":
            if isinstance(scene_snapshot, dict):
                return scene_snapshot.get("render_settings") or "(render settings unavailable)"
            return "(render settings unavailable — no scene snapshot)"

        if name == "get_viewport_state":
            if isinstance(scene_snapshot, dict):
                return scene_snapshot.get("viewport_state") or "(viewport state unavailable)"
            return "(viewport state unavailable — no scene snapshot)"

        if name == "list_info_log":
            try:
                n = int(args.get("n") or 40)
            except (TypeError, ValueError):
                n = 40
            n = max(1, min(200, n))
            with _info_log_lock:
                tail = list(_info_log_buffer)[-n:]
            if not tail:
                return "(info log is empty)"
            return "\n".join(f"[{time.strftime('%H:%M:%S', time.localtime(ts))}] {line}"
                             for ts, line in tail)

        if name == "ask_user":
            # Handled by _tool_loop as a special terminal signal — we
            # shouldn't actually get here, but return the question as a
            # safety net if we do.
            q = (args.get("question") or "").strip()
            return q or "(no question)"

        if name == "search_api":
            query = (args.get("query") or "").strip()
            if not query:
                return "(empty query)"
            hits = _search_api_index(query, n_results=5)
            if not hits:
                return "(no matches in local API index)"
            return "\n\n".join(hits)
    except Exception as e:
        return f"(tool error: {type(e).__name__}: {e})"
    return f"(unknown tool: {name})"


def _tool_status(name, args):
    """Human-readable one-liner shown in the progress indicator."""
    if name == "search_web":
        q = (args.get("query") or "").strip()
        return f"searching: {q[:50]}"
    if name == "fetch_url":
        u = (args.get("url") or "").strip()
        return f"reading: {u[:60]}"
    if name == "get_scene":
        return "inspecting scene"
    if name == "get_object_info":
        return f"inspecting object: {(args.get('name') or '')[:40]}"
    if name == "get_selection":
        return "reading selection"
    if name == "get_node_tree":
        return f"reading node tree: {(args.get('name') or '')[:40]}"
    if name == "list_info_log":
        return "checking info log"
    if name == "ask_user":
        return "requesting clarification"
    if name == "search_api":
        q = (args.get("query") or "").strip()
        return f"api lookup: {q[:50]}"
    if name == "list_datablocks":
        return f"listing bpy.data.{(args.get('type') or '').strip()}"
    if name == "get_timeline":
        return "reading timeline"
    if name == "get_animation_data":
        return f"reading animation: {(args.get('name') or '')[:40]}"
    if name == "get_render_settings":
        return "reading render settings"
    if name == "get_viewport_state":
        return "reading viewport state"
    return f"tool: {name}"


# Some llama.cpp builds don't parse Qwen3-Coder's XML tool-call format
# through --jinja — the model's `<tool_call><function=X><parameter=Y>…
# </parameter></function></tool_call>` output ends up as raw content
# instead of structured `tool_calls`. Same for older servers that only
# know the Hermes JSON form (`<tool_call>{"name":…, "arguments":…}
# </tool_call>`). These regexes let us salvage both shapes ourselves so
# the tool loop continues instead of showing the user raw XML.
_INLINE_TOOLCALL_RE = re.compile(
    r'<tool_call>\s*(.*?)\s*</tool_call>', re.DOTALL | re.IGNORECASE,
)
_FUNCTION_TAG_RE  = re.compile(
    r'<function\s*=\s*([^>\s]+)\s*>(.*?)</function>',
    re.DOTALL | re.IGNORECASE,
)
_PARAMETER_TAG_RE = re.compile(
    r'<parameter\s*=\s*([^>\s]+)\s*>(.*?)</parameter>',
    re.DOTALL | re.IGNORECASE,
)


def _coerce_inline_param(raw):
    """Turn an XML-style `<parameter=foo>value</parameter>` text body into
    a Python scalar. Strings come through bare (no surrounding quotes in
    Qwen format); bools / nulls / numbers are coerced so tools receive
    the right types."""
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    low = s.lower()
    if low == 'true':  return True
    if low == 'false': return False
    if low == 'null' or low == 'none': return None
    try:
        if any(c in s for c in '.eE'):
            return float(s)
        return int(s)
    except ValueError:
        return s


def _parse_inline_tool_calls(content):
    """Return a list of {name, arguments} dicts parsed from inline
    `<tool_call>…</tool_call>` markup in the assistant content. Handles
    both the JSON body form and the XML `<function=…><parameter=…>` form
    (Qwen3-Coder)."""
    calls = []
    for m in _INLINE_TOOLCALL_RE.finditer(content or ""):
        body = (m.group(1) or "").strip()
        if not body:
            continue
        parsed = None
        # JSON body: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
        if body.startswith('{'):
            try:
                j = json.loads(body)
                if isinstance(j, dict) and j.get("name"):
                    args = j.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    parsed = {"name": j["name"], "arguments": args}
            except Exception:
                pass
        if parsed is None:
            fm = _FUNCTION_TAG_RE.search(body)
            if fm:
                fn_name = (fm.group(1) or "").strip()
                fn_body = fm.group(2) or ""
                args = {}
                for pm in _PARAMETER_TAG_RE.finditer(fn_body):
                    pname = (pm.group(1) or "").strip()
                    args[pname] = _coerce_inline_param(pm.group(2))
                if fn_name:
                    parsed = {"name": fn_name, "arguments": args}
        if parsed:
            calls.append(parsed)
    return calls


def _strip_inline_tool_calls(content):
    """Remove `<tool_call>…</tool_call>` blocks from an assistant content
    string. Used both to clean the message we persist (so history doesn't
    contain raw tool-call markup) and at render time as a belt-and-
    suspenders for any turns that were stored before this fallback
    landed."""
    if not content or '<tool_call>' not in content.lower():
        return content
    return _INLINE_TOOLCALL_RE.sub('', content).strip()


MAX_TOOL_ITERATIONS = 8


def _tool_call_signature(name, args):
    """Stable dedupe key for a tool call. For search tools we normalise
    by stripping common stopwords and lowering so near-identical queries
    collapse onto the same signature."""
    try:
        if name in ("search_api", "search_web"):
            q = (args.get("query") or "").lower()
            toks = sorted(re.findall(r'[a-z0-9]+', q))
            # Drop 1-char tokens — they're noise when matching intent.
            toks = [t for t in toks if len(t) > 1]
            return f"{name}::{' '.join(toks)}"
        if name == "fetch_url":
            return f"fetch_url::{(args.get('url') or '').strip().lower()}"
        if name == "get_object_info":
            return f"get_object_info::{(args.get('name') or '').lower()}"
        if name == "get_node_tree":
            return f"get_node_tree::{(args.get('name') or '').lower()}"
        return f"{name}::{json.dumps(args, sort_keys=True)}"
    except Exception:
        return name


def _force_final_answer(base_url, messages, temperature, max_tokens, timeout,
                        status_cb=None):
    """Strip tools, inject a STOP instruction, ask the model to write its
    best answer with what it already has. Called when the tool loop hits
    its cap OR when the model is clearly stuck in a research loop."""
    if status_cb:
        status_cb("finalizing")
    nudge = {
        "role": "user",
        "content": (
            "[SYSTEM NOTE: You have used your entire research budget. "
            "Do NOT call any more tools. Write the final answer NOW "
            "using everything you learned from the tool calls above "
            "plus your own knowledge. If some detail is still uncertain, "
            "say so inline and keep going — the user would rather have "
            "a 90%-correct answer with a caveat than no answer at all.]"
        ),
    }
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": "qwen3",
        "messages": messages + [nudge],
        # No tools — force text-only response.
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        **_CHAT_SAMPLING,
    }
    try:
        resp = _http_post(url, payload, timeout)
        final = resp["choices"][0]["message"].get("content") or ""
        return _strip_inline_tool_calls(final).strip()
    except Exception as e:
        print(f"[Blender Buddy] forced finalization failed: {e}")
        return ""


def _best_effort_fallback(messages, reason):
    """Last resort when even the forced finalization returns empty.
    Pulls the most recent non-trivial tool result out of the message
    trail so the user at least sees the research that happened."""
    last_result = ""
    for m in reversed(messages):
        if m.get("role") == "tool":
            body = (m.get("content") or "").strip()
            if body and not body.startswith("(") and len(body) > 40:
                last_result = body
                break
    if not last_result:
        return f"(No answer — {reason}. Try asking again or press Clear.)"
    return (
        f"_⚠ {reason} — here's the most recent thing I looked up:_\n\n"
        + last_result[:2000]
        + ("…" if len(last_result) > 2000 else "")
    )


def _tool_loop(base_url, messages, max_tokens, temperature, timeout,
               tools, scene_snapshot, status_cb=None,
               max_iterations=MAX_TOOL_ITERATIONS):
    """Drive a tool-calling conversation to completion. `tools` is the
    per-request tool list (see _build_tools_schema). `max_iterations`
    caps how many model→tool rounds we allow before forcing a final
    answer. Returns the final assistant content.

    v9.8.1 additions:
      - Duplicate-call detection: if the model asks for the same tool
        with the same (normalised) arguments twice, replace the 2nd
        result with a stop-nudge and mark a strike. Three strikes and
        we short-circuit to forced finalization.
      - Stronger forced finalization: explicit STOP-and-answer nudge
        injected before the tools-off retry.
      - Best-effort fallback: if even the forced retry is empty, return
        the most recent substantive tool result so the user sees SOME
        of the research instead of a generic error."""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    seen_sigs = {}   # sig -> call count
    wasted_strikes = 0

    for iteration in range(max_iterations):
        payload = {
            "model": "qwen3",
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **_CHAT_SAMPLING,
        }
        if status_cb:
            status_cb(f"thinking (round {iteration + 1})")
        resp = _http_post(url, payload, timeout)
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        # Fallback: if the server didn't parse tool_calls out of the
        # Qwen3-Coder / Hermes <tool_call>…</tool_call> markup, try
        # parsing it ourselves so the loop continues instead of returning
        # raw XML to the user. Common in older llama.cpp builds.
        if not tool_calls and content and '<tool_call>' in content.lower():
            inline = _parse_inline_tool_calls(content)
            if inline:
                tool_calls = [{
                    "id":       f"inline_{iteration}_{i}",
                    "type":     "function",
                    "function": {
                        "name":      c["name"],
                        "arguments": json.dumps(c["arguments"]),
                    },
                } for i, c in enumerate(inline)]
                # Scrub the markup from the visible content so the
                # assistant turn we persist doesn't leak raw XML.
                content = _strip_inline_tool_calls(content)

        if not tool_calls:
            final = _strip_inline_tool_calls(content).strip()
            if final:
                return final
            # Model produced nothing — do one forced retry with the STOP
            # nudge before giving up.
            forced = _force_final_answer(base_url, messages, temperature,
                                          max_tokens, timeout, status_cb)
            if forced:
                return forced
            return _best_effort_fallback(
                messages, "the model finished without producing text"
            )

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

        # Detect a terminal ask_user call first — if the model asked the
        # user a clarification, surface that question as the final
        # response and stop the loop. Any other tool calls in the same
        # batch are ignored (the clarification supersedes them).
        for tc in tool_calls:
            fn = tc.get("function") or {}
            if (fn.get("name") or "") == "ask_user":
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                q = (args.get("question") or "").strip()
                if q:
                    if status_cb:
                        status_cb("requesting clarification")
                    return f"❓ **Clarification needed:** {q}"

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}

            sig = _tool_call_signature(name, args)
            # Duplicate detection — common failure mode where the model
            # keeps re-searching near-identical queries instead of
            # committing. Let the FIRST call through, then replace
            # subsequent identical calls with a stop nudge so the model
            # realises it's looping. After 3 strikes, short-circuit.
            seen_sigs[sig] = seen_sigs.get(sig, 0) + 1
            if seen_sigs[sig] > 1:
                wasted_strikes += 1
                if status_cb:
                    status_cb(f"duplicate tool call ({seen_sigs[sig]}x) — nudging")
                result = (
                    f"(DUPLICATE CALL — you already called {name} with "
                    f"the same arguments earlier in this conversation. "
                    f"Review the previous result in the message above "
                    f"and STOP calling tools. Write the final answer now.)"
                )
            else:
                if status_cb:
                    status_cb(_tool_status(name, args))
                result = _execute_tool(name, args, scene_snapshot)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or "",
                "content": result,
            })

        # If the model has racked up 3+ duplicate strikes, it's stuck —
        # stop the loop early and force a final answer while there's
        # still context headroom.
        if wasted_strikes >= 3:
            if status_cb:
                status_cb("breaking out of duplicate loop")
            forced = _force_final_answer(base_url, messages, temperature,
                                          max_tokens, timeout, status_cb)
            if forced:
                return forced
            return _best_effort_fallback(
                messages, "the model got stuck re-calling the same tools"
            )

    # Ran out of iterations — force a final answer with the STOP nudge.
    forced = _force_final_answer(base_url, messages, temperature,
                                  max_tokens, timeout, status_cb)
    if forced:
        return forced
    return _best_effort_fallback(
        messages, "hit the tool-round limit"
    )


# ---------------------------------------------------------------------------
# Viewport screenshot (for vision mode)
# ---------------------------------------------------------------------------
#
# Called from the main thread (inside BB_OT_ask.execute, before the worker
# spawns) because bpy.ops.* are main-thread-only. Saves a PNG to a temp
# path, reads back as base64, returns for inclusion in the vision payload.

# Minimum file size for a "plausible" screenshot. Blender's Wayland path
# produces tiny all-zero PNGs (< 2 KB for a full viewport). A real area
# capture is usually 50-300 KB. We treat anything under this threshold as
# a failed/blank capture and warn the user, pointing them at the CUSTOM
# image path as the Wayland fallback.
_SCREENSHOT_MIN_BYTES = 2048

# Accepted extensions for the CUSTOM image path. Keeps the user from
# accidentally (or a malicious prompt from deliberately) loading a text
# / config / credential file as an "image".
_CUSTOM_IMAGE_EXT_ALLOW = (".png", ".jpg", ".jpeg", ".webp")


def _display_server_is_wayland():
    """Cheap Linux-only check: are we running under a Wayland session?
    Blender's screen.screenshot* produces black images on Wayland
    (upstream bug T98462). We use this to warn in preferences and to
    label suspicious tiny screenshots more helpfully."""
    if sys.platform != "linux":
        return False
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _capture_area_to_b64(area):
    """Screenshot one specific `bpy.types.Area` and return base64 PNG, or
    None on failure. Main-thread only (invokes bpy.ops)."""
    tmp = tempfile.NamedTemporaryFile(
        prefix="blender_buddy_ss_", suffix=".png", delete=False,
    )
    tmp.close()
    path = tmp.name
    try:
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.screenshot_area(filepath=path)
        if not os.path.exists(path):
            return None
        size = os.path.getsize(path)
        if size == 0:
            return None
        if size < _SCREENSHOT_MIN_BYTES:
            hint = " (Wayland: bpy screenshot returns a blank PNG — use CUSTOM image path instead)" if _display_server_is_wayland() else ""
            print(f"[Blender Buddy] area capture produced only {size} bytes; likely blank.{hint}")
            return None
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        print(f"[Blender Buddy] area capture failed: {e}")
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _capture_screenshot(scope='AREA', mouse_x=None, mouse_y=None,
                        custom_path=None):
    """Screenshot (or load a user-supplied image) per the chosen scope,
    base64-encode as PNG, return str. Returns None on failure.

        AREA    — the under-cursor editor area (legacy path; the panel
                  now normally uses the interactive SELECT modal below)
        WINDOW  — the entire Blender window via screen.screenshot()
        CUSTOM  — load the user-provided file at `custom_path`
    """
    if scope == 'CUSTOM':
        if not custom_path:
            print("[Blender Buddy] CUSTOM scope requires a file path.")
            return None
        full = bpy.path.abspath(custom_path)
        # Extension whitelist — the vision model only accepts raster
        # images, so blocking everything else also blocks the SSRF-ish
        # "read /etc/passwd by renaming .txt to .png" shape.
        if not full.lower().endswith(_CUSTOM_IMAGE_EXT_ALLOW):
            print(f"[Blender Buddy] CUSTOM image must be one of "
                  f"{_CUSTOM_IMAGE_EXT_ALLOW}: {full}")
            return None
        real = os.path.realpath(full)
        # Containment: allow paths under the blend-file dir, the user's
        # home, or our own DATAFILES cache. Anything else (system dirs,
        # somebody-else's-user) is refused.
        allowed_roots = []
        try:
            blend_dir = os.path.dirname(bpy.data.filepath or "") or None
            if blend_dir:
                allowed_roots.append(os.path.realpath(blend_dir))
        except Exception:
            pass
        try:
            allowed_roots.append(os.path.realpath(os.path.expanduser("~")))
        except Exception:
            pass
        try:
            allowed_roots.append(os.path.realpath(data_root()))
        except Exception:
            pass
        if allowed_roots and not any(
                real == root or real.startswith(root + os.sep)
                for root in allowed_roots):
            print(f"[Blender Buddy] CUSTOM image outside allowed roots: {real}")
            return None
        if not os.path.isfile(real):
            print(f"[Blender Buddy] image not found: {real}")
            return None
        try:
            with open(real, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[Blender Buddy] custom image load failed: {e}")
            return None

    tmp = tempfile.NamedTemporaryFile(
        prefix="blender_buddy_ss_", suffix=".png", delete=False,
    )
    tmp.close()
    path = tmp.name

    try:
        if scope == 'WINDOW':
            # screen.screenshot captures the entire Blender window.
            bpy.ops.screen.screenshot(filepath=path)
        else:
            # AREA — pick area under cursor if we have mouse coords, else
            # the currently-active area (works when Send comes from the
            # sidebar: context.area is the parent editor, e.g. VIEW_3D).
            target_area = None
            if mouse_x is not None and mouse_y is not None:
                for area in bpy.context.window.screen.areas:
                    if (area.x <= mouse_x <= area.x + area.width and
                            area.y <= mouse_y <= area.y + area.height):
                        target_area = area
                        break
            if target_area is None:
                target_area = bpy.context.area
            if target_area is None:
                print("[Blender Buddy] no area to screenshot; "
                      "falling back to full window.")
                bpy.ops.screen.screenshot(filepath=path)
            else:
                with bpy.context.temp_override(area=target_area):
                    bpy.ops.screen.screenshot_area(filepath=path)

        if not os.path.exists(path):
            return None
        size = os.path.getsize(path)
        if size == 0:
            return None
        if size < _SCREENSHOT_MIN_BYTES:
            hint = " (Wayland: bpy screenshot returns a blank PNG — use CUSTOM image path instead)" if _display_server_is_wayland() else ""
            print(f"[Blender Buddy] screenshot ({scope}) produced only {size} bytes; likely blank.{hint}")
            return None
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        print(f"[Blender Buddy] screenshot ({scope}) failed: {e}")
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Scene context (optional — useful for scene-specific questions)
# ---------------------------------------------------------------------------

def _fmt_vec(v, n=3):
    try:
        return "(" + ", ".join(f"{x:.{n}f}" for x in v) + ")"
    except Exception:
        return str(v)


def _editor_label_for_area(area):
    """Map an Area's raw type (and, for NODE_EDITOR, its tree_type) to the
    user-visible editor name Blender shows in its Editor Type menu. Used
    so the model doesn't default to '3D Viewport' when the user is in a
    different editor."""
    if area is None:
        return None
    t = area.type
    simple = {
        'VIEW_3D':         '3D Viewport',
        'IMAGE_EDITOR':    'Image/UV Editor',
        'SEQUENCE_EDITOR': 'Video Sequencer',
        'CLIP_EDITOR':     'Movie Clip Editor',
        'DOPESHEET_EDITOR': 'Dope Sheet / Timeline',
        'GRAPH_EDITOR':    'Graph Editor',
        'NLA_EDITOR':      'Nonlinear Animation',
        'TEXT_EDITOR':     'Text Editor',
        'OUTLINER':        'Outliner',
        'PROPERTIES':      'Properties',
        'FILE_BROWSER':    'File Browser',
        'SPREADSHEET':     'Spreadsheet',
        'PREFERENCES':     'Preferences',
        'INFO':            'Info',
        'CONSOLE':         'Python Console',
        'TOPBAR':          'Top Bar',
        'STATUSBAR':       'Status Bar',
    }
    if t in simple:
        return simple[t]
    if t == 'NODE_EDITOR':
        sp = area.spaces.active
        tt = getattr(sp, 'tree_type', None)
        return {
            'ShaderNodeTree':     'Shader Editor',
            'GeometryNodeTree':   'Geometry Nodes',
            'CompositorNodeTree': 'Compositor',
            'TextureNodeTree':    'Texture Node Editor',
        }.get(tt, f"Node Editor ({tt})")
    return t


def _scene_context_report():
    """Detailed snapshot of the current .blend for the model's `get_scene`
    tool. Main thread only — reads bpy.context/bpy.data which aren't
    thread-safe. Covers: Blender version, scene + render settings, active
    workspace + area type, current mode, active/selected objects, frame
    range, unit system, loaded addons. Kept to ~30 lines so it doesn't
    dominate the context window — deeper inspection is on-demand via
    get_object_info / get_node_tree."""
    parts = []

    def add(label, value):
        if value not in (None, "", [], ()):
            parts.append(f"{label}: {value}")

    try:
        add("blender", bpy.app.version_string)
    except Exception:
        pass

    try:
        scene = bpy.context.scene
        add("scene", f"'{scene.name}'")
        add("render", f"{scene.render.engine}  {scene.render.resolution_x}x"
                      f"{scene.render.resolution_y} @ {scene.render.fps} fps")
        add("frames", f"{scene.frame_start}-{scene.frame_end} "
                      f"(current {scene.frame_current})")
        us = scene.unit_settings
        add("units", f"{us.system} / {us.length_unit} / scale {us.scale_length}")
        if scene.world:
            add("world", f"'{scene.world.name}'")
        vl = getattr(bpy.context, 'view_layer', None)
        if vl:
            add("view_layer", f"'{vl.name}'")
    except Exception:
        pass

    try:
        ws = bpy.context.workspace
        add("workspace", f"'{ws.name}'" if ws else None)
        area = bpy.context.area
        if area is not None:
            label = _editor_label_for_area(area)
            add("area", f"{area.type}  ({label})")
        else:
            add("area", None)
    except Exception:
        pass

    try:
        add("mode", bpy.context.mode)
        active = bpy.context.active_object
        if active:
            loc = _fmt_vec(active.location)
            rot = _fmt_vec([r for r in active.rotation_euler])
            scl = _fmt_vec(active.scale)
            dim = _fmt_vec(active.dimensions)
            add("active",
                f"'{active.name}' ({active.type})  loc={loc}  "
                f"rot={rot}  scale={scl}  dims={dim}")
            if active.parent:
                add("  parent", f"'{active.parent.name}'")
            if active.modifiers:
                mods = [f"{m.name}:{m.type}" for m in active.modifiers]
                add("  modifiers", ", ".join(mods))
            if active.material_slots:
                mats = [(s.material.name if s.material else "None")
                        for s in active.material_slots]
                add("  materials", ", ".join(mats))
            data = getattr(active, 'data', None)
            if data is not None and hasattr(data, 'vertices'):
                add("  mesh", f"verts={len(data.vertices)}  "
                              f"edges={len(data.edges)}  "
                              f"polys={len(data.polygons)}")
        else:
            add("active", "None")
    except Exception:
        pass

    try:
        sel = [o.name for o in bpy.context.selected_objects]
        if sel:
            preview = sel[:6]
            extra = f" +{len(sel)-6} more" if len(sel) > 6 else ""
            add("selected", f"{len(sel)}: {preview}{extra}")
        else:
            add("selected", "0")
    except Exception:
        pass

    try:
        ac = getattr(bpy.context, 'collection', None)
        if ac:
            add("active_collection", f"'{ac.name}'")
    except Exception:
        pass

    try:
        objs = bpy.data.objects
        if len(objs) == 0:
            add("objects", "(empty)")
        else:
            by_type = {}
            for obj in objs:
                by_type.setdefault(obj.type, 0)
                by_type[obj.type] += 1
            groups = sorted(by_type.items())
            add("objects", f"total={len(objs)}  "
                + "  ".join(f"{t}={n}" for t, n in groups))
    except Exception:
        pass

    try:
        for k in ('meshes', 'materials', 'images', 'node_groups',
                  'collections', 'actions'):
            c = getattr(bpy.data, k, None)
            if c is not None and len(c) > 0:
                add(f"bpy.data.{k}", len(c))
    except Exception:
        pass

    try:
        import addon_utils
        enabled = [m.__name__ for m in addon_utils.modules()
                   if addon_utils.check(m.__name__)[1]]
        add("addons_enabled", f"{len(enabled)} " + ", ".join(enabled[:8])
            + (" …" if len(enabled) > 8 else ""))
    except Exception:
        pass

    return "\n".join(parts)


def _object_info_report(obj):
    """Full-fat inspection of one object — what the get_object_info tool
    returns. Main thread only."""
    lines = []
    try:
        lines.append(f"'{obj.name}'  type={obj.type}  data='{obj.data.name if obj.data else None}'")
        lines.append(f"  location={_fmt_vec(obj.location)}  "
                     f"rotation_euler={_fmt_vec([r for r in obj.rotation_euler])}  "
                     f"scale={_fmt_vec(obj.scale)}")
        lines.append(f"  dimensions={_fmt_vec(obj.dimensions)}")
        if obj.parent:
            lines.append(f"  parent='{obj.parent.name}'  parent_type={obj.parent_type}")
        colls = [c.name for c in obj.users_collection]
        if colls:
            lines.append(f"  collections={colls}")
        if obj.modifiers:
            for m in obj.modifiers:
                # Dump a few important settings per modifier type. RNA lets
                # us iterate properties but that'd be too verbose — pick
                # show_viewport/render + the distinctive settings the model
                # most often needs.
                settings = [f"show_viewport={m.show_viewport}",
                            f"show_render={m.show_render}"]
                for attr in ('object', 'offset', 'count', 'operation',
                             'solver', 'thickness', 'levels',
                             'render_levels', 'factor', 'strength',
                             'angle_limit', 'segments', 'width',
                             'use_clamp_overlap', 'seed'):
                    if hasattr(m, attr):
                        v = getattr(m, attr)
                        if hasattr(v, 'name'):
                            v = f"'{v.name}'"
                        settings.append(f"{attr}={v}")
                lines.append(f"  modifier '{m.name}' ({m.type}): "
                             + "  ".join(settings[:8]))
        if obj.constraints:
            for c in obj.constraints:
                lines.append(f"  constraint '{c.name}' ({c.type})  "
                             f"influence={c.influence}  "
                             f"mute={c.mute}")
        if obj.material_slots:
            mats = [(s.material.name if s.material else "None")
                    for s in obj.material_slots]
            lines.append(f"  material_slots={mats}")
        if hasattr(obj, 'vertex_groups') and obj.vertex_groups:
            vgs = [vg.name for vg in obj.vertex_groups][:20]
            lines.append(f"  vertex_groups({len(obj.vertex_groups)})={vgs}")
        if obj.animation_data and obj.animation_data.action:
            lines.append(f"  action='{obj.animation_data.action.name}'")
        custom = {k: v for k, v in obj.items()
                  if not k.startswith('_') and k != 'cycles_visibility'}
        if custom:
            lines.append(f"  custom_props={custom}")
        data = obj.data
        if data is not None:
            if hasattr(data, 'vertices'):
                lines.append(f"  mesh: verts={len(data.vertices)}  "
                             f"edges={len(data.edges)}  "
                             f"polys={len(data.polygons)}  "
                             f"uv_layers={len(data.uv_layers)}  "
                             f"mat_slots={len(data.materials)}")
            elif hasattr(data, 'splines'):
                lines.append(f"  curve: splines={len(data.splines)}")
            elif hasattr(data, 'lens'):
                lines.append(f"  camera: lens={data.lens}  type={data.type}")
            elif hasattr(data, 'energy'):
                lines.append(f"  light: type={data.type}  energy={data.energy}  "
                             f"color={_fmt_vec(list(data.color))}")
    except Exception as e:
        lines.append(f"(inspection error: {type(e).__name__}: {e})")
    return "\n".join(lines)


def _selection_report():
    """What is currently selected — main-thread read."""
    parts = []
    try:
        mode = bpy.context.mode
        parts.append(f"mode: {mode}")
        sel = bpy.context.selected_objects
        active = bpy.context.active_object
        parts.append(f"active: '{active.name}'" if active else "active: None")
        parts.append(f"selected_objects ({len(sel)}): "
                     + ", ".join(f"'{o.name}'" for o in sel[:20])
                     + (f"  +{len(sel)-20} more" if len(sel) > 20 else ""))
        if mode == 'EDIT_MESH' and active and active.type == 'MESH':
            # Edit-mode selection is on bmesh, not the object data — BUT
            # pulling bmesh from edit mesh needs its own context; skip the
            # deep count, just note the mode.
            parts.append("  (edit mesh — use bpy.ops.object.mode_set + bmesh "
                         "to inspect element selection)")
    except Exception as e:
        parts.append(f"(selection error: {type(e).__name__}: {e})")
    return "\n".join(parts)


def _node_tree_report(tree):
    """Dump nodes + links of a ShaderNodeTree / GeometryNodeTree / etc.
    Keeps key socket values so the model can reproduce the setup."""
    lines = []
    try:
        lines.append(f"tree '{tree.name}' ({type(tree).__name__})  "
                     f"nodes={len(tree.nodes)}  links={len(tree.links)}")
        for node in tree.nodes:
            bits = [f"'{node.name}' ({node.bl_idname})"]
            loc = getattr(node, 'location', None)
            if loc is not None:
                bits.append(f"loc={_fmt_vec(list(loc), 1)}")
            # A few commonly-set attributes that carry meaning
            for attr in ('operation', 'blend_type', 'data_type',
                         'distribution', 'projection', 'interpolation',
                         'extension', 'space'):
                if hasattr(node, attr):
                    v = getattr(node, attr)
                    if isinstance(v, str) and v:
                        bits.append(f"{attr}={v}")
            lines.append("  " + "  ".join(bits))
            # Default input values for disconnected sockets
            for sock in node.inputs:
                if sock.is_linked:
                    continue
                try:
                    dv = sock.default_value
                    if hasattr(dv, '__iter__') and not isinstance(dv, str):
                        dv = list(dv)
                    lines.append(f"    input '{sock.name}' ({sock.type}) = {dv}")
                except Exception:
                    pass
        for link in tree.links:
            lines.append(
                f"  link: '{link.from_node.name}'.{link.from_socket.name} "
                f"→ '{link.to_node.name}'.{link.to_socket.name}"
            )
    except Exception as e:
        lines.append(f"(node tree error: {type(e).__name__}: {e})")
    return "\n".join(lines)


_DATABLOCK_KINDS = (
    "objects", "materials", "meshes", "node_groups", "actions",
    "images", "textures", "collections", "scenes", "worlds",
    "cameras", "lights", "armatures", "curves", "texts",
    "brushes", "particles", "libraries", "fonts", "sounds",
    "movieclips", "masks", "linestyles", "grease_pencils",
)


def _collect_datablocks_report():
    """Enumerate every tracked bpy.data collection — names (capped) + counts.
    Main thread only. Returns {kind: {'count': n, 'names': [...]}}."""
    report = {}
    for key in _DATABLOCK_KINDS:
        coll = getattr(bpy.data, key, None)
        if coll is None:
            continue
        try:
            names = [d.name for d in coll][:500]
            report[key] = {"count": len(coll), "names": names}
        except Exception:
            report[key] = {"count": 0, "names": []}
    return report


def _timeline_report():
    """Timeline + playback settings — main-thread read."""
    parts = []

    def add(label, value):
        if value not in (None, "", [], ()):
            parts.append(f"{label}: {value}")

    try:
        scene = bpy.context.scene
        r = scene.render
        fps_real = (r.fps / r.fps_base) if r.fps_base else r.fps
        add("frame_start", scene.frame_start)
        add("frame_end", scene.frame_end)
        add("frame_current", scene.frame_current)
        add("frame_step", scene.frame_step)
        add("fps", f"{fps_real:g}  ({r.fps}/{r.fps_base})")
        add("use_preview_range", scene.use_preview_range)
        if scene.use_preview_range:
            add("preview_start", scene.frame_preview_start)
            add("preview_end", scene.frame_preview_end)
        add("sync_mode", getattr(scene, "sync_mode", None))
    except Exception as e:
        parts.append(f"(timeline error: {type(e).__name__}: {e})")
    return "\n".join(parts)


def _animation_report_for(id_data):
    """Animation dump for one ID: action + fcurves + NLA + drivers. Works
    on actions (direct fcurves) and on objects / shape-key blocks / other
    IDs that carry animation_data."""
    lines = []
    try:
        if isinstance(id_data, bpy.types.Action):
            fcurves = list(id_data.fcurves)
            fr = tuple(id_data.frame_range) if hasattr(id_data, 'frame_range') else None
            lines.append(f"action '{id_data.name}': fcurves={len(fcurves)}  frame_range={fr}")
            for fc in fcurves[:30]:
                kfs = fc.keyframe_points
                first = kfs[0].co[0] if len(kfs) else None
                last = kfs[-1].co[0] if len(kfs) else None
                modes = {}
                for kp in kfs:
                    modes[kp.interpolation] = modes.get(kp.interpolation, 0) + 1
                lines.append(
                    f"  fcurve {fc.data_path}[{fc.array_index}]  "
                    f"keyframes={len(kfs)}  frames=[{first}..{last}]  "
                    f"interp={modes}"
                )
            if len(fcurves) > 30:
                lines.append(f"  (…+{len(fcurves)-30} more fcurves)")
            return "\n".join(lines)

        ad = getattr(id_data, 'animation_data', None)
        name = getattr(id_data, 'name', '?')
        if ad is None:
            return f"'{name}': (no animation_data)"

        lines.append(f"'{name}':")
        if ad.action:
            lines.append(f"  action='{ad.action.name}'")
            fcurves = list(ad.action.fcurves)
            for fc in fcurves[:30]:
                kfs = fc.keyframe_points
                first = kfs[0].co[0] if len(kfs) else None
                last = kfs[-1].co[0] if len(kfs) else None
                modes = {}
                for kp in kfs:
                    modes[kp.interpolation] = modes.get(kp.interpolation, 0) + 1
                lines.append(
                    f"    fcurve {fc.data_path}[{fc.array_index}]  "
                    f"keyframes={len(kfs)}  frames=[{first}..{last}]  "
                    f"interp={modes}"
                )
            if len(fcurves) > 30:
                lines.append(f"    (…+{len(fcurves)-30} more fcurves)")
        else:
            lines.append("  action=None")

        if ad.nla_tracks:
            for tr in ad.nla_tracks:
                strips = [(s.name, s.frame_start, s.frame_end,
                           s.action.name if s.action else None)
                          for s in tr.strips]
                lines.append(f"  nla_track '{tr.name}'  muted={tr.mute}  strips={strips}")

        drivers = list(ad.drivers) if hasattr(ad, 'drivers') else []
        for dv in drivers[:20]:
            drv = dv.driver
            lines.append(
                f"  driver {dv.data_path}[{dv.array_index}]  "
                f"type={drv.type}  vars={len(drv.variables)}  "
                f"expr={drv.expression!r}"
            )
        if len(drivers) > 20:
            lines.append(f"  (…+{len(drivers)-20} more drivers)")
    except Exception as e:
        lines.append(f"(animation error: {type(e).__name__}: {e})")
    return "\n".join(lines)


def _render_settings_report():
    """Structured render engine + color-mgmt + output report — main thread."""
    lines = []
    try:
        scene = bpy.context.scene
        r = scene.render
        lines.append(f"engine: {r.engine}")
        lines.append(f"resolution: {r.resolution_x}x{r.resolution_y} @ {r.resolution_percentage}%")
        lines.append(f"pixel_aspect: {r.pixel_aspect_x}:{r.pixel_aspect_y}")
        lines.append(f"frame_range: {scene.frame_start}-{scene.frame_end}  step={scene.frame_step}")
        lines.append(f"output_filepath: '{r.filepath}'")
        img = r.image_settings
        lines.append(
            f"file_format: {img.file_format}  color_mode={img.color_mode}  "
            f"color_depth={img.color_depth}"
        )
        lines.append(f"film_transparent: {r.film_transparent}")
        lines.append(f"use_motion_blur: {getattr(r, 'use_motion_blur', None)}")

        cyc = getattr(scene, 'cycles', None)
        if cyc is not None:
            lines.append(
                f"cycles: max_render_samples={getattr(cyc, 'samples', None)}  "
                f"max_viewport_samples={getattr(cyc, 'preview_samples', None)}  "
                f"use_adaptive={getattr(cyc, 'use_adaptive_sampling', None)}  "
                f"adaptive_threshold={getattr(cyc, 'adaptive_threshold', None)}  "
                f"adaptive_min_samples={getattr(cyc, 'adaptive_min_samples', None)}  "
                f"time_limit_sec={getattr(cyc, 'time_limit', None)}"
            )
            lines.append(
                f"cycles_denoise: use={getattr(cyc, 'use_denoising', None)}  "
                f"denoiser={getattr(cyc, 'denoiser', None)}  "
                f"device={getattr(cyc, 'device', None)}"
            )

        ev = getattr(scene, 'eevee', None)
        if ev is not None:
            lines.append(
                f"eevee: taa_samples={getattr(ev, 'taa_samples', None)}  "
                f"taa_render_samples={getattr(ev, 'taa_render_samples', None)}  "
                f"use_raytracing={getattr(ev, 'use_raytracing', None)}  "
                f"use_gtao={getattr(ev, 'use_gtao', None)}"
            )

        vs = scene.view_settings
        lines.append(
            f"color_mgmt: view_transform={vs.view_transform}  look={vs.look}  "
            f"exposure={vs.exposure}  gamma={vs.gamma}"
        )
        ds = scene.display_settings
        lines.append(f"display_device: {ds.display_device}")
    except Exception as e:
        lines.append(f"(render settings error: {type(e).__name__}: {e})")
    return "\n".join(lines)


def _view3d_state_lines(v3d_area, prefix="view3d"):
    """Pull shading / overlay / gizmo / region state from a VIEW_3D area.
    Returns a list of lines; empty on failure."""
    out = []
    try:
        space = v3d_area.spaces.active
        shading = space.shading
        overlay = space.overlay
        out.append(
            f"{prefix}_shading: type={shading.type}  light={shading.light}  "
            f"color_type={shading.color_type}  "
            f"background_type={getattr(shading, 'background_type', None)}"
        )
        out.append(
            f"{prefix}_overlay: show_overlays={overlay.show_overlays}  "
            f"show_floor={getattr(overlay, 'show_floor', None)}  "
            f"show_axis_x={getattr(overlay, 'show_axis_x', None)}  "
            f"show_axis_y={getattr(overlay, 'show_axis_y', None)}  "
            f"show_axis_z={getattr(overlay, 'show_axis_z', None)}"
        )
        out.append(
            f"{prefix}_show_gizmo: {space.show_gizmo}  "
            f"local_view: {bool(space.local_view)}"
        )
        r3d = space.region_3d
        out.append(
            f"{prefix}_region: perspective={r3d.view_perspective}  "
            f"is_orthographic_side_view={r3d.is_orthographic_side_view}"
        )
        if space.camera:
            out.append(f"{prefix}_camera: '{space.camera.name}'")
    except Exception as e:
        out.append(f"({prefix} error: {type(e).__name__}: {e})")
    return out


def _current_area_detail_lines(area):
    """Editor-specific state for whatever area the user is currently in —
    so the model answers 'you're in the Shader Editor' instead of
    defaulting to '3D Viewport'."""
    out = []
    if area is None:
        return out
    try:
        space = area.spaces.active
        if area.type == 'VIEW_3D':
            out.extend(_view3d_state_lines(area, prefix="current_view3d"))
        elif area.type == 'NODE_EDITOR':
            tree = getattr(space, 'edit_tree', None) or getattr(space, 'node_tree', None)
            out.append(
                f"current_node_editor: tree_type={getattr(space, 'tree_type', None)}  "
                f"shader_type={getattr(space, 'shader_type', None)}  "
                f"pin={getattr(space, 'pin', None)}  "
                f"tree_name='{tree.name}'" if tree else
                f"current_node_editor: tree_type={getattr(space, 'tree_type', None)}  "
                f"shader_type={getattr(space, 'shader_type', None)}  (no tree)"
            )
        elif area.type == 'IMAGE_EDITOR':
            out.append(
                f"current_image_editor: mode={getattr(space, 'mode', None)}  "
                f"ui_mode={getattr(space, 'ui_mode', None)}  "
                f"image='{space.image.name}'" if getattr(space, 'image', None) else
                f"current_image_editor: mode={getattr(space, 'mode', None)}  "
                f"ui_mode={getattr(space, 'ui_mode', None)}  image=None"
            )
        elif area.type == 'PROPERTIES':
            out.append(f"current_properties: context={getattr(space, 'context', None)}")
        elif area.type == 'OUTLINER':
            out.append(f"current_outliner: display_mode={getattr(space, 'display_mode', None)}  "
                       f"filter_state={getattr(space, 'filter_state', None)}")
        elif area.type == 'DOPESHEET_EDITOR':
            out.append(f"current_dopesheet: mode={getattr(space, 'mode', None)}  "
                       f"ui_mode={getattr(space, 'ui_mode', None)}")
        elif area.type == 'GRAPH_EDITOR':
            out.append(f"current_graph: mode={getattr(space, 'mode', None)}")
        elif area.type == 'TEXT_EDITOR':
            txt = getattr(space, 'text', None)
            out.append(f"current_text_editor: text='{txt.name}'" if txt else
                       "current_text_editor: text=None")
    except Exception as e:
        out.append(f"(current area detail error: {type(e).__name__}: {e})")
    return out


def _viewport_state_report():
    """Current area (editor-specific state) + a VIEW_3D shading block if a
    3D Viewport exists anywhere on screen. Units + active tool at the end."""
    lines = []
    try:
        ws = bpy.context.workspace
        lines.append(f"workspace: '{ws.name}'" if ws else "workspace: None")

        area = bpy.context.area
        if area is not None:
            label = _editor_label_for_area(area)
            lines.append(f"current_area: {area.type}  ({label})")
        else:
            lines.append("current_area: None")

        lines.extend(_current_area_detail_lines(area))

        v3d_area = area if (area and area.type == 'VIEW_3D') else None
        if v3d_area is None:
            try:
                for win in bpy.context.window_manager.windows:
                    for a in win.screen.areas:
                        if a.type == 'VIEW_3D':
                            v3d_area = a
                            break
                    if v3d_area:
                        break
            except Exception:
                pass
            if v3d_area:
                lines.append("(VIEW_3D elsewhere on screen — its state follows:)")
                lines.extend(_view3d_state_lines(v3d_area, prefix="view3d"))

        us = bpy.context.scene.unit_settings
        lines.append(
            f"units: system={us.system}  length={us.length_unit}  "
            f"scale={us.scale_length}  rotation={us.system_rotation}"
        )

        try:
            mode = bpy.context.mode
            tool = ws.tools.from_space_view3d_mode(mode) if ws else None
            if tool:
                lines.append(f"active_tool (view3d/{mode}): {tool.idname}")
        except Exception:
            pass
    except Exception as e:
        lines.append(f"(viewport state error: {type(e).__name__}: {e})")
    return "\n".join(lines)


def _build_scene_snapshot():
    """Build the full snapshot dict that the worker's scene-inspection
    tools read from. All bpy access happens here on the main thread."""
    summary = ""
    try:
        summary = _scene_context_report()
    except Exception as e:
        summary = f"(scene context error: {e})"

    objects = {}
    animation_objects = {}
    try:
        for obj in bpy.data.objects:
            objects[obj.name] = _object_info_report(obj)
            if getattr(obj, 'animation_data', None):
                animation_objects[obj.name] = _animation_report_for(obj)
    except Exception:
        pass

    animation_actions = {}
    try:
        for act in bpy.data.actions:
            animation_actions[act.name] = _animation_report_for(act)
    except Exception:
        pass

    animation_shape_keys = {}
    try:
        for me in bpy.data.meshes:
            sk = getattr(me, 'shape_keys', None)
            if sk and getattr(sk, 'animation_data', None):
                animation_shape_keys[me.name] = _animation_report_for(sk)
    except Exception:
        pass

    selection = ""
    try:
        selection = _selection_report()
    except Exception:
        pass

    node_trees = {}
    try:
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                node_trees[mat.name] = _node_tree_report(mat.node_tree)
        for world in bpy.data.worlds:
            if world.use_nodes and world.node_tree:
                node_trees[world.name] = _node_tree_report(world.node_tree)
        for grp in bpy.data.node_groups:
            node_trees[grp.name] = _node_tree_report(grp)
    except Exception:
        pass

    datablocks = {}
    try:
        datablocks = _collect_datablocks_report()
    except Exception:
        pass

    timeline = ""
    try:
        timeline = _timeline_report()
    except Exception:
        pass

    render_settings = ""
    try:
        render_settings = _render_settings_report()
    except Exception:
        pass

    viewport_state = ""
    try:
        viewport_state = _viewport_state_report()
    except Exception:
        pass

    return {
        "summary":         summary,
        "objects":         objects,
        "selection":       selection,
        "node_trees":      node_trees,
        "datablocks":      datablocks,
        "timeline":        timeline,
        "animation":       {
            "objects":    animation_objects,
            "actions":    animation_actions,
            "shape_keys": animation_shape_keys,
        },
        "render_settings": render_settings,
        "viewport_state":  viewport_state,
    }


# ---------------------------------------------------------------------------
# Markdown renderer — best-effort pretty-print in a Blender UI panel.
#
# Blender UI primitives can't render bold or italic, don't have a monospace
# label, and have no table widget — but we can simulate most of it with
# row/column layouts, scale_y tricks for headings, boxes for code/quotes,
# and splitting pipe tables into aligned columns.
# ---------------------------------------------------------------------------

_INLINE_BOLD_RE  = re.compile(r"\*\*([^*]+?)\*\*")
_INLINE_BOLD2_RE = re.compile(r"__([^_]+?)__")
_INLINE_ITAL_RE  = re.compile(r"(?<!\*)\*([^*\s][^*]*?)\*(?!\*)")
_INLINE_ITAL2_RE = re.compile(r"(?<!_)_([^_\s][^_]*?)_(?!_)")
_INLINE_CODE_RE  = re.compile(r"`([^`]+?)`")
_INLINE_LINK_RE  = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HEADING_RE      = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_RE         = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.+)$")
_HR_RE           = re.compile(r"^\s*(\*{3,}|-{3,}|_{3,})\s*$")
_QUOTE_RE        = re.compile(r"^\s*>\s?(.*)$")
_TABLE_SEP_RE    = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _strip_inline(text):
    """Flatten inline markdown that labels can't style."""
    text = _INLINE_BOLD_RE.sub(r"\1", text)
    text = _INLINE_BOLD2_RE.sub(r"\1", text)
    text = _INLINE_ITAL_RE.sub(r"\1", text)
    text = _INLINE_ITAL2_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _INLINE_LINK_RE.sub(r"\1", text)
    return text


_PARA_SCALE_Y = 0.78  # tight vertical spacing for paragraph text
_CODE_SCALE_Y = 0.72  # tighter again for monospace-style code blocks


# --- LaTeX → plain text -----------------------------------------------------
# The model occasionally emits $$…$$ blocks or \frac{a}{b}-style markup even
# though the system prompt says not to. Blender's UI labels can't render math,
# so we preprocess to readable ASCII / Unicode equivalents — matches how a
# human would write the same equation in a chat message.

_LATEX_BLOCK_RE  = re.compile(r"\$\$\s*(.+?)\s*\$\$", re.DOTALL)
_LATEX_INLINE_RE = re.compile(r"(?<![\$\w])\$([^\$\n]+?)\$(?!\w)")
_LATEX_FRAC_RE   = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_LATEX_SQRT_RE   = re.compile(r"\\sqrt\s*\{([^{}]+)\}")
_LATEX_CMD_TAIL_RE = re.compile(r"\\([a-zA-Z]+)")

# Single-arg styling / wrapper commands. Strip them to just their content so
# nested cases like \frac{\mathbf{v}}{\|\mathbf{v}\|} can be parsed by the
# (deliberately non-recursive) frac/sqrt regexes after a few passes.
_LATEX_STRIP_CMD_RE = re.compile(
    r"\\(?:mathbf|mathrm|mathit|mathsf|mathtt|mathbb|mathfrak|mathcal|"
    r"text|textbf|textit|textrm|textsf|texttt|"
    r"boldsymbol|bm|vec|hat|tilde|bar|dot|ddot|underline|overline|"
    r"operatorname)\s*\{([^{}]*)\}"
)

_LATEX_SYMBOLS = {
    r"\cdot":   "·",
    r"\times":  "×",
    r"\div":    "÷",
    r"\pm":     "±",
    r"\mp":     "∓",
    r"\approx": "≈",
    r"\neq":    "≠",
    r"\leq":    "≤",
    r"\geq":    "≥",
    r"\to":     "→",
    r"\infty":  "∞",
    r"\sum":    "Σ",
    r"\prod":   "Π",
    r"\int":    "∫",
    r"\partial": "∂",
    r"\nabla":  "∇",
    r"\langle": "⟨", r"\rangle": "⟩",
    r"\lceil":  "⌈", r"\rceil":  "⌉",
    r"\lfloor": "⌊", r"\rfloor": "⌋",
    r"\|":      "‖",  # double-bar (norm)
    r"\alpha":  "α", r"\beta":  "β", r"\gamma":   "γ", r"\delta":  "δ",
    r"\epsilon":"ε", r"\zeta":  "ζ", r"\eta":     "η", r"\theta":  "θ",
    r"\iota":   "ι", r"\kappa": "κ", r"\lambda":  "λ", r"\mu":     "μ",
    r"\nu":     "ν", r"\xi":    "ξ", r"\pi":      "π", r"\rho":    "ρ",
    r"\sigma":  "σ", r"\tau":   "τ", r"\phi":     "φ", r"\chi":    "χ",
    r"\psi":    "ψ", r"\omega": "ω",
    r"\Gamma":  "Γ", r"\Delta": "Δ", r"\Theta":   "Θ", r"\Lambda": "Λ",
    r"\Xi":     "Ξ", r"\Pi":    "Π", r"\Sigma":   "Σ", r"\Phi":    "Φ",
    r"\Psi":    "Ψ", r"\Omega": "Ω",
    r"\left":   "",  r"\right": "",
    r"\,":      " ", r"\;":     " ", r"\!":       "",
    r"\\":      "\n",  # LaTeX line break inside an equation
}


def _convert_latex_expr(expr):
    """Convert a single LaTeX expression body to plain text."""
    # 1) Strip styling/wrapper commands first — this collapses
    #    \mathbf{v}, \text{normalized}, \vec{x} etc. to their inner content,
    #    so frac/sqrt's flat-brace regex can see through them. Iterate to
    #    handle nesting like \mathbf{\hat{n}}.
    for _ in range(6):
        new = _LATEX_STRIP_CMD_RE.sub(r"\1", expr)
        if new == expr:
            break
        expr = new
    # 2) frac/sqrt — also iterate because substitutions can expose new matches.
    for _ in range(6):
        new = _LATEX_FRAC_RE.sub(r"(\1)/(\2)", expr)
        new = _LATEX_SQRT_RE.sub(r"√(\1)", new)
        if new == expr:
            break
        expr = new
    # 3) Symbols.
    for k, v in _LATEX_SYMBOLS.items():
        expr = expr.replace(k, v)
    # 4) Strip remaining \command tokens — keep the name as a fallback so
    #    users can still see what was meant (e.g., \mathbb → mathbb).
    expr = _LATEX_CMD_TAIL_RE.sub(r"\1", expr)
    # 5) Collapse braces left over from stripped commands.
    expr = expr.replace("{", "").replace("}", "")
    return expr.strip()


_FENCE_PROTECT_RE       = re.compile(r"(```.*?```)", re.DOTALL)
_INLINE_CODE_PROTECT_RE = re.compile(r"(`[^`\n]+`)")

# x^2 → x², 10^{-3} → 10⁻³. Only digits + sign chars are converted, so
# `2^k`, `^L` (control chars in docs), and code paths like `path^foo`
# are left alone.
_SUPERSCRIPT_TR = str.maketrans('0123456789-+', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺')
_SUPERSCRIPT_RE = re.compile(r'\^(\{[\d\-+]+\}|[\d\-+]+)')


def _superscript_powers(text):
    """Convert ^N and ^{NN} to Unicode superscripts."""
    def repl(m):
        s = m.group(1)
        if s.startswith('{') and s.endswith('}'):
            s = s[1:-1]
        return s.translate(_SUPERSCRIPT_TR)
    return _SUPERSCRIPT_RE.sub(repl, text)


def _convert_latex(text):
    """Replace $$…$$ blocks and inline $…$ with readable plain text.
    Code fences and inline `code` are passed through untouched so $-syntax
    in shell snippets / variables doesn't get mangled."""
    def _block(m):
        return "\n" + _convert_latex_expr(m.group(1)) + "\n"

    def _convert_segment(seg):
        seg = _LATEX_BLOCK_RE.sub(_block, seg)
        seg = _LATEX_INLINE_RE.sub(
            lambda m: _convert_latex_expr(m.group(1)), seg,
        )
        # Catches both LaTeX-converted output (^2 left over from \frac/\sqrt
        # bodies) and plain-typed `mc^2`-style powers in normal prose.
        seg = _superscript_powers(seg)
        return seg

    out = []
    # Split on fenced code blocks (odd-index parts are fence content, kept verbatim)
    for i, part in enumerate(_FENCE_PROTECT_RE.split(text)):
        if i % 2 == 1:
            out.append(part)
            continue
        # Within non-fence text, also protect inline `code`
        sub_out = []
        for j, sub in enumerate(_INLINE_CODE_PROTECT_RE.split(part)):
            sub_out.append(sub if j % 2 == 1 else _convert_segment(sub))
        out.append("".join(sub_out))
    return "".join(out)


def _close_trailing_fence(text):
    """If the markdown text contains an odd number of triple-backtick
    fences, it ends with an open code block — typically because the
    model hit max_tokens mid-snippet. Append a closing fence plus a
    one-line truncation note so the renderer doesn't treat everything
    that follows as code."""
    if text.count("```") % 2 == 0:
        return text
    sep = "" if text.endswith("\n") else "\n"
    return text + sep + "```\n_(response was cut off)_\n"


def _render_markdown(layout, md, width=40, max_lines=200):
    """Walk a markdown string and render into the given layout.

    Paragraph text is emitted into a rolling compact column (align=True +
    reduced scale_y) so consecutive wrapped lines don't look double-spaced.
    Special blocks (code, table, heading, rule, quote) break that column
    and render in their own layouts so they aren't squished.
    """
    md = _convert_latex(md)
    # Auto-close an unterminated fenced block — common when the model
    # hits max_tokens mid-code and the last ``` got truncated. Without
    # this, the markdown renderer treats everything after the opening
    # fence as one giant code block and the conversation layout breaks.
    md = _close_trailing_fence(md)
    lines = md.splitlines()
    n = len(lines)
    rendered = [0]  # box so helpers can mutate

    # Rolling paragraph column — lazily created so each block break gets
    # its own column (which keeps tight spacing within but separates
    # visually from whatever comes next).
    para_col = [None]

    def _break_para():
        para_col[0] = None

    def _para_col():
        if para_col[0] is None:
            col = layout.column(align=True)
            col.scale_y = _PARA_SCALE_Y
            para_col[0] = col
        return para_col[0]

    def _emit_para(text, indent=""):
        if rendered[0] >= max_lines:
            return
        if not text.strip():
            return
        col = _para_col()
        for chunk in _wrap_for_label(indent + text, width=width):
            if rendered[0] >= max_lines:
                return
            col.label(text=chunk if chunk else " ")
            rendered[0] += 1

    i = 0
    while i < n and rendered[0] < max_lines:
        raw = lines[i]
        stripped = raw.strip()

        # ```fenced code block
        if stripped.startswith("```"):
            _break_para()
            lang = stripped[3:].strip() or "code"

            # Harvest the code body first so the copy button can receive it.
            i += 1
            code_body_lines = []
            while i < n and not lines[i].lstrip().startswith("```"):
                code_body_lines.append(lines[i])
                i += 1
            if i < n and lines[i].lstrip().startswith("```"):
                i += 1  # skip closing fence
            code_body = "\n".join(code_body_lines)

            box = layout.box()
            # Header row: language label on the left, [Copy][Run] on the
            # right. Run is Python-only — executing a shell/JSON/etc fence
            # doesn't make sense and would just error.
            hrow = box.row(align=False)
            left = hrow.row()
            left.label(text=lang, icon='SCRIPT')
            right = hrow.row(align=True)
            right.alignment = 'RIGHT'
            cop = right.operator(
                BB_OT_copy_code_block.bl_idname, text="", icon='COPYDOWN',
            )
            cop.code = code_body
            if lang.lower() in ('python', 'py', 'bpy'):
                rop = right.operator(
                    BB_OT_run_code_block.bl_idname, text="", icon='PLAY',
                )
                rop.code = code_body

            col = box.column(align=True)
            col.scale_y = _CODE_SCALE_Y
            for code_line in code_body_lines:
                if rendered[0] >= max_lines:
                    break
                for chunk in _wrap_for_label(code_line, width=max(10, width - 2)):
                    if rendered[0] >= max_lines:
                        break
                    col.label(text=chunk if chunk else " ")
                    rendered[0] += 1
            _break_para()
            continue

        # Pipe table (header + separator)
        if "|" in raw and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            _break_para()
            header_cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            table_start = i
            i += 2
            body_rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                body_rows.append(cells)
                i += 1

            try:
                tbox = layout.box()
                hrow = tbox.row(align=True)
                for cell in header_cells:
                    c = hrow.column(align=True)
                    c.label(text=_strip_inline(cell), icon='DOT')
                rendered[0] += 1
                for row in body_rows:
                    while len(row) < len(header_cells):
                        row.append("")
                    brow = tbox.row(align=True)
                    for cell in row[: len(header_cells)]:
                        c = brow.column(align=True)
                        c.scale_y = _PARA_SCALE_Y
                        wrapped = _wrap_for_label(
                            _strip_inline(cell),
                            width=max(8, width // max(1, len(header_cells))),
                        )
                        for t in wrapped[:3]:
                            c.label(text=t if t else " ")
                    rendered[0] += 1
            except Exception as e:
                # Table data was malformed enough to break the renderer
                # (ragged rows, empty header, mismatched separator row).
                # Fall back to rendering the raw table block as plain
                # text so the content isn't lost.
                print(f"[Blender Buddy] table render fallback: {e}")
                fallback = layout.column(align=True)
                fallback.scale_y = _PARA_SCALE_Y
                for ln in lines[table_start:i]:
                    for chunk in _wrap_for_label(ln, width=width):
                        if rendered[0] >= max_lines:
                            break
                        fallback.label(text=chunk if chunk else " ")
                        rendered[0] += 1
            _break_para()
            continue

        # Heading
        m = _HEADING_RE.match(stripped)
        if m:
            _break_para()
            level = len(m.group(1))
            text = _strip_inline(m.group(2))
            hrow = layout.row()
            hrow.scale_y = 1.4 if level == 1 else (1.2 if level == 2 else 1.05)
            icon = {1: 'BOOKMARKS', 2: 'DISCLOSURE_TRI_DOWN',
                    3: 'DOT'}.get(level, 'NONE')
            hrow.label(text=text.upper() if level == 1 else text, icon=icon)
            rendered[0] += 1
            i += 1
            _break_para()
            continue

        # Horizontal rule
        if _HR_RE.match(raw):
            _break_para()
            layout.separator()
            rendered[0] += 1
            i += 1
            continue

        # Blockquote
        mq = _QUOTE_RE.match(raw)
        if mq:
            _break_para()
            qbox = layout.box()
            qcol = qbox.column(align=True)
            qcol.scale_y = _PARA_SCALE_Y
            qtext = _strip_inline(mq.group(1) or "")
            for chunk in _wrap_for_label("▎ " + qtext, width=width):
                if rendered[0] >= max_lines:
                    break
                qcol.label(text=chunk)
                rendered[0] += 1
            i += 1
            _break_para()
            continue

        # List item — rendered into the rolling para column so successive
        # items share spacing.
        ml = _LIST_RE.match(raw)
        if ml:
            indent = len(ml.group(1))
            bullet = ml.group(2)
            text = _strip_inline(ml.group(3))
            prefix = "  " * (indent // 2)
            marker = "• " if bullet in ("-", "*", "+") else f"{bullet} "
            _emit_para(text, indent=prefix + marker)
            i += 1
            continue

        # Blank line — break paragraph, no separator (keeps spacing tight).
        if not stripped:
            _break_para()
            i += 1
            continue

        # Regular paragraph line
        _emit_para(_strip_inline(stripped))
        i += 1

    if rendered[0] >= max_lines:
        layout.label(
            text=f"… (truncated to {max_lines} lines — open in Text Editor)",
            icon='INFO',
        )


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def _save_prefs(_self, _context):
    """Persist preferences on every change so values (context size,
    model choice, hardware backend, etc.) survive Blender restarts
    even when the user has 'Auto-Save Preferences' turned off."""
    try:
        bpy.ops.wm.save_userpref()
    except Exception as e:
        print(f"[Blender Buddy] Could not save preferences: {e}")


def _on_server_setting_change(self, context):
    _save_prefs(self, context)
    if _job_get()["active"]:
        return
    if not server_is_running():
        return
    mode = current_server_mode() or 'text'
    try:
        stop_server()
        start_server(self, mode=mode)
    except Exception as e:
        print(f"[Blender Buddy] Auto-restart failed: {e}")


class BB_AP_prefs(AddonPreferences):
    bl_idname = ADDON_ID

    server_url: StringProperty(
        name="Server URL",
        description="Where to send chat requests. Leave default for the managed local server.",
        default="http://127.0.0.1:8080",
        update=_save_prefs,
    )
    server_port: IntProperty(
        name="Port",
        description="Port for the managed llama-server. Server auto-restarts on change.",
        default=8080, min=1024, max=65535,
        update=_on_server_setting_change,
    )
    backend: EnumProperty(
        name="Hardware",
        description="Which GPU / CPU to use for running the model.",
        items=[
            ('AUTO',   "Auto",   "Best guess based on your system."),
            ('CUDA',   "CUDA",   "NVIDIA GeForce / RTX / Quadro."),
            ('CPU',    "CPU",    "Slowest but works on any computer."),
            ('METAL',  "Metal",  "Apple Silicon (M-series Macs)."),
            ('VULKAN', "Vulkan", "Universal GPU (AMD / Intel / NVIDIA)."),
            ('HIP',    "ROCm",   "AMD GPU via ROCm/HIP (Linux only)."),
        ],
        default='AUTO',
        update=_save_prefs,
    )

    selected_text_model: EnumProperty(
        name="Text model",
        description=(
            "Which text model size to use. Low = fastest, lowest RAM, "
            "simpler answers. Medium = balanced. High = best quality, "
            "heaviest RAM."
        ),
        items=[
            (TEXT_MODEL_VARIANTS[k]["key"],
             TEXT_MODEL_VARIANTS[k]["label"],
             TEXT_MODEL_VARIANTS[k]["size_tag"])
            for k in TEXT_MODEL_ORDER
        ],
        default=TEXT_MODEL_DEFAULT_KEY,
        update=_save_prefs,
    )
    # v9.2: context_size / max_tokens / temperature / timeout are all
    # hardcoded as module-level DEFAULT_* constants. Quality and
    # Creativity presets removed — one well-chosen setting beats three
    # noisy knobs for a local assistant.

    allow_online_access: BoolProperty(
        name="Allow online access",
        description=(
            "When on, Buddy can look things up on the web and read "
            "pages for citations. When off, it answers from what it "
            "already knows plus any attached screenshot only."
        ),
        default=True,
        update=_save_prefs,
    )

    context_size: EnumProperty(
        name="Context size",
        description=(
            "How much conversation history + research the model can "
            "hold in mind at once. Larger = more room for long "
            "conversations and multi-page web reads, but uses more "
            "RAM / VRAM up front. Change requires Unload + Load."
        ),
        items=[
            ('8192',   "8 k",   "Smallest. Minimal RAM. Safest on tight systems."),
            ('16384',  "16 k",  "Default — balanced for most sessions."),
            ('32768',  "32 k",  "Roomy. Uses noticeably more RAM."),
            ('65536',  "64 k",  "Long research / deep mode."),
            ('131072', "128 k", "Only if you have the RAM to spare."),
        ],
        default='16384',
        update=_save_prefs,
    )

    # --- Global hotkey to open the Buddy sidebar in the area under the cursor ---
    hotkey_key: EnumProperty(
        name="Key",
        description="Key that opens the Buddy sidebar in the area under the cursor",
        items=[(c, c, "") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
        default='Q',
        update=lambda self, ctx: _on_hotkey_change(self, ctx),
    )
    hotkey_ctrl: BoolProperty(
        name="Ctrl", default=True,
        update=lambda self, ctx: _on_hotkey_change(self, ctx),
    )
    hotkey_shift: BoolProperty(
        name="Shift", default=True,
        update=lambda self, ctx: _on_hotkey_change(self, ctx),
    )
    hotkey_alt: BoolProperty(
        name="Alt", default=False,
        update=lambda self, ctx: _on_hotkey_change(self, ctx),
    )

    def draw(self, _context):
        layout = self.layout
        exe = server_exe_path()
        any_text_ready = any(text_model_ready(k) for k in TEXT_MODEL_ORDER)
        vision_ready = vision_model_ready()
        running = server_is_running()
        mode    = current_server_mode()
        state = _job_get()
        ready_count = sum([bool(exe), any_text_ready])

        # ---- Big online-access toggle (first thing the user sees) ----
        # Elevated to the top on purpose: the default is ON, but if a
        # user unticks it they should immediately see where to turn
        # it back on. scale_y=1.5 + a short explanation underneath.
        online_box = layout.box()
        online_icon = ('INTERNET' if self.allow_online_access
                       else 'INTERNET_OFFLINE')
        online_row = online_box.row(align=True)
        online_row.scale_y = 1.5
        online_row.prop(self, "allow_online_access",
                        toggle=True, icon=online_icon)
        online_box.label(
            text=("Buddy can look things up on the web."
                  if self.allow_online_access
                  else "Offline: no web lookups or page fetching."),
            icon='INFO',
        )

        # ---- Setup status header ----
        header = layout.box()
        header.label(
            text=(f"Setup: {ready_count}/2 complete"
                  + (f"  •  running ({mode})" if running else "")),
            icon='CHECKMARK' if (ready_count == 2 and running) else 'SETTINGS',
        )
        if state["active"]:
            prog_row = header.row(align=True)
            prog_row.label(
                text=_progress_display_text(state),
                icon='SORTTIME',
            )
            # Cancel is only meaningful during Install / Download jobs;
            # the operator's poll just checks _job_get().active so we
            # render it here for any active job.
            if "Download" in str(state.get("label", "")) or "Install" in str(state.get("label", "")):
                cancel_btn = prog_row.row()
                cancel_btn.operator("blender_buddy.cancel_download",
                                    text="Cancel", icon='CANCEL')

        # ---- Step 1: hardware + runner ----
        box = layout.box()
        box.label(text="1.  Hardware + runner", icon='DESKTOP')
        hw_row = box.row(align=True)
        hw_row.scale_y = 1.2
        hw_row.prop(self, "backend", expand=True)
        if self.backend == 'CUDA':
            box.label(
                text="CUDA needs the NVIDIA CUDA runtime installed.",
                icon='ERROR',
            )
        elif self.backend == 'AUTO':
            box.label(text=f"Auto will pick: {detect_default_backend().upper()}",
                      icon='INFO')
        bin_row = box.row(align=True)
        bin_row.label(
            text=("Runner"
                  + ("  ✓ installed" if exe else "  (not installed)")),
            icon='CHECKMARK' if exe else 'RADIOBUT_OFF',
        )
        bin_btn = bin_row.row()
        bin_btn.scale_y = 1.2
        bin_btn.operator("blender_buddy.install_server",
                         text="Reinstall" if exe else "Install",
                         icon='IMPORT')

        # ---- Step 2: models (text variants + vision) ----
        box = layout.box()
        downloaded = text_downloaded_keys()
        total_ready = len(downloaded) + (1 if vision_ready else 0)
        box.label(
            text=(f"2.  Models  ({total_ready}/4 downloaded — "
                  f"{len(downloaded)}/3 text"
                  + (", vision ✓" if vision_ready else ", vision —")
                  + ")"),
            icon='CHECKMARK' if downloaded else 'RADIOBUT_OFF',
        )
        # Your system — helps the user pick a tier that'll actually fit.
        box.label(text=f"Your system: {_hardware_summary_line()}",
                  icon='MEMORY')
        recommended = _recommended_text_key()
        for key in TEXT_MODEL_ORDER:
            v = TEXT_MODEL_VARIANTS[key]
            on_disk = text_model_ready(key)
            is_active = (self.selected_text_model == key)
            is_recommended = (recommended == key)
            row = box.row(align=True)
            row.scale_y = 1.1
            sel = row.row(align=True)
            sel.enabled = on_disk
            btn_text = v["label"]
            if is_active and on_disk:
                btn_text = f"{v['label']} (active)"
            sel_op = sel.operator(
                "blender_buddy.select_text_variant",
                text=btn_text,
                icon='RADIOBUT_ON' if is_active else 'RADIOBUT_OFF',
                depress=is_active,
            )
            sel_op.variant = key
            tag = row.row()
            tag_text = v["size_tag"]
            if is_recommended and not (is_active and on_disk):
                tag_text += "   (recommended)"
            tag.label(text=tag_text)
            dl = row.row(align=True)
            dl_op = dl.operator(
                "blender_buddy.download_text_variant",
                text="✓" if on_disk else "Download",
                icon='CHECKMARK' if on_disk else 'IMPORT',
            )
            dl_op.variant = key
            dl_op.select_on_finish = not on_disk
        # Vision sub-row — same visual rhythm as the text variants so
        # it reads as another "tier" rather than a separate step.
        vrow = box.row(align=True)
        vrow.scale_y = 1.1
        vrow.label(
            text=(f"Vision"
                  + ("  ✓ ready" if vision_ready else "  (optional)")),
            icon='CAMERA_STEREO',
        )
        vtag = vrow.row()
        vtag.label(text=f"{VISION_MODEL['label']}  ~5.8 GB")
        vdl = vrow.row(align=True)
        vdl.operator("blender_buddy.download_vision_model",
                     text="✓" if vision_ready else "Download",
                     icon='CHECKMARK' if vision_ready else 'IMPORT')
        # Wayland caveat lives with the vision row so users see it in
        # context.
        if _display_server_is_wayland():
            wl = box.row()
            wl.alert = True
            wl.label(
                text="Wayland detected: viewport screenshots come out blank. "
                     "Use the CUSTOM image path from the panel instead.",
                icon='ERROR',
            )

        # ---- Step 3: context + system prompt + logs ----
        box = layout.box()
        box.label(text="3.  Behaviour + diagnostics", icon='SETTINGS')

        # Context size (compact preset row).
        ctx_row = box.row(align=True)
        ctx_row.label(text="Context size", icon='MEMORY')
        ctx_row.prop(self, "context_size", expand=True)
        if running:
            box.label(
                text="Unload and reload to apply a new context size.",
                icon='INFO',
            )

        # System prompt — compact one-row with label + two buttons.
        sp_row = box.row(align=True)
        sp_row.label(text="System prompt", icon='TEXT')
        sp_row.operator("blender_buddy.edit_system_prompt",
                        text="Edit", icon='GREASEPENCIL')
        sp_row.operator("blender_buddy.reset_system_prompt",
                        text="Reset", icon='LOOP_BACK')

        # Logs — folder + clipboard copy in the same compact row.
        log_row = box.row(align=True)
        log_row.label(text="Logs", icon='CONSOLE')
        log_row.operator("blender_buddy.open_log_folder",
                         text="Open folder", icon='FILE_FOLDER')
        log_row.operator("blender_buddy.copy_server_log",
                         text="Copy server log", icon='COPYDOWN')

        # ---- Hotkey (single-row, compact) ----
        hk_box = layout.box()
        hk_head = hk_box.row(align=True)
        hk_head.label(text="Hotkey", icon='RESTRICT_SELECT_OFF')
        hk_head.prop(self, "hotkey_ctrl", toggle=True)
        hk_head.prop(self, "hotkey_shift", toggle=True)
        hk_head.prop(self, "hotkey_alt", toggle=True)
        hk_head.prop(self, "hotkey_key", text="")
        hk_box.label(
            text=f"Press {_hotkey_label(self)} to open Buddy anywhere.",
            icon='INFO',
        )
        # Collision warning — populated by _register_keymap() when it
        # finds another binding on the same combo. Silent when clear.
        if _keymap_conflicts:
            first = _keymap_conflicts[0]
            more  = f" (+{len(_keymap_conflicts) - 1} more)" if len(_keymap_conflicts) > 1 else ""
            warn = hk_box.row()
            warn.alert = True
            warn.label(
                text=(f"Conflict: also bound to {first['operator']} "
                      f"in '{first['keymap']}'{more}. Change the combo above."),
                icon='ERROR',
            )


# ---------------------------------------------------------------------------
# Scene props
# ---------------------------------------------------------------------------

# Auto-submit on Enter WITH cancel-on-toggle-click. Blender can't distinguish
# the textbox committing via Enter vs focus-loss — but we CAN detect when a
# toggle changes value (its own update callback fires) and we can skip the
# submit when the commit context isn't our sidebar region. So the scheme is:
#   1. question update fires  → schedule submit in ~150ms
#   2. toggle  update fires   → cancel any pending submit
#   3. commit from non-UI region (clicked into a different editor) → skip
# Net effect: Enter inside the prompt fires the ask; clicking a toggle or
# clicking into another editor doesn't.
_pending_submit_token = [None]


def _cancel_pending_submit(self, context):
    _pending_submit_token[0] = None


def _on_question_commit(self, context):
    q = (self.question or "").strip()
    if not q or _job_get()["active"]:
        return
    # If the commit fires from outside a sidebar UI region (user clicked
    # into a 3D viewport or node editor), don't auto-submit.
    region = getattr(context, 'region', None)
    if region is not None and region.type != 'UI':
        return

    my_token = object()
    _pending_submit_token[0] = my_token

    def _submit_if_still_pending():
        if _pending_submit_token[0] is my_token:
            _pending_submit_token[0] = None
            try:
                bpy.ops.blender_buddy.ask('INVOKE_DEFAULT')
            except Exception as e:
                print(f"[Blender Buddy] auto-ask failed: {e}")
        return None

    bpy.app.timers.register(_submit_if_still_pending, first_interval=0.15)


class BB_PG_props(PropertyGroup):
    question: StringProperty(
        name="",
        description=(
            "Ask about Blender or bpy. Press Enter inside the prompt to "
            "submit. Clicking a toggle or clicking into another editor "
            "won't fire the prompt."
        ),
        default="",
        update=_on_question_commit,
    )
    attach_image: BoolProperty(
        name="Attach Screenshot",
        description=(
            "Send a screenshot with the question. Auto-switches the local "
            "server to the vision model (requires one-time download in "
            "Preferences). The Scope dropdown picks what gets captured."
        ),
        default=False,
        update=_cancel_pending_submit,
    )
    add_context: BoolProperty(
        name="Deep",
        description=(
            "Experimental deep mode. When on, the model gets a bigger "
            "response budget (2x tokens) and more tool rounds (2x), so "
            "it can search further, cross-check multiple pages, and "
            "write longer code. Off: snappy default."
        ),
        default=False,
        update=_cancel_pending_submit,
    )
    action_mode: BoolProperty(
        name="Action",
        description=(
            "Action mode. When ON, Buddy returns ONE Python code block "
            "that performs the action (instead of the default UI "
            "instructions). Flip this on when you want code to run "
            "rather than a how-to."
        ),
        default=False,
        update=_cancel_pending_submit,
    )
    screenshot_scope: EnumProperty(
        name="Scope",
        description="What Attach Screenshot captures",
        items=[
            ('AREA', "Select Area",
             "On Send, the cursor becomes a crosshair; click the editor "
             "area you want to capture. Esc / right-click cancels."),
            ('WINDOW', "Full Window",
             "The entire Blender window, including every editor + sidebars."),
            ('CUSTOM', "Custom Image",
             "Attach an image from disk. Drop or paste the file path into "
             "the field below, or click the folder button to browse."),
        ],
        default='AREA',
        update=_cancel_pending_submit,
    )
    custom_image_path: StringProperty(
        name="Image path",
        description=(
            "Path to an image file (PNG / JPG / WebP) to attach to the "
            "question. Blender file-path fields accept drag-and-drop "
            "from the OS file explorer."
        ),
        subtype='FILE_PATH',
        default="",
        update=_cancel_pending_submit,
    )


# ---------------------------------------------------------------------------
# Modal helper for long jobs
# ---------------------------------------------------------------------------

class _ModalJob:
    _timer = None
    _thread = None

    def _start_job(self, context, worker, args=(), label="", tick=0.2,
                   register_handler=True):
        """Spawn `worker` in a thread, start a redraw timer, and put this
        operator into its modal loop. When `register_handler=False` we
        skip `modal_handler_add` — caller is already in modal (used by
        BB_OT_ask's PICK → WORK phase transition)."""
        if _job_get()["active"]:
            self.report({'WARNING'}, "A job is already running.")
            return {'CANCELLED'}
        _job_set(active=True, label=label, progress=0.0, message="starting",
                 done=False, error=None, answer="", partial="")
        # Re-roll the buddy animation so each job gets a fresh random
        # sequence. Must happen here because the icon getter only runs
        # while busy — it can never observe the idle-to-active flip
        # itself.
        _rotate_animation()
        self._thread = threading.Thread(target=worker, args=args, daemon=True)
        self._thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(tick, window=context.window)
        if register_handler:
            wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            # Tag every area AND every region in every window. The per-region
            # pass is what gets popovers / popup dialogs to refresh during
            # streaming — they live as TEMPORARY regions in area.regions and
            # don't auto-redraw with just area.tag_redraw().
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
                    for region in area.regions:
                        region.tag_redraw()
            state = _job_get()
            if state["done"]:
                return self._finish_wrapper(context, state)
        return {'PASS_THROUGH'}

    def _finish_wrapper(self, context, state):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        _job_set(active=False)
        return self._finish(context, state)

    def _finish(self, context, state):
        if state.get("error"):
            self.report({'ERROR'},
                        f"{state.get('label','Job')} failed: {state['error']}")
            return {'CANCELLED'}
        self.report({'INFO'}, state.get("message", "done"))
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Setup-flow operators
# ---------------------------------------------------------------------------

class BB_OT_install_server(_ModalJob, Operator):
    bl_idname = "blender_buddy.install_server"
    bl_label = "Install Server"
    bl_description = "Download and install the local model runner for your hardware."

    def execute(self, context):
        backend = _effective_backend(_prefs(context))
        return self._start_job(context, worker_install_server,
                               args=(backend,), label="Install server")


class BB_OT_download_text_variant(_ModalJob, Operator):
    bl_idname = "blender_buddy.download_text_variant"
    bl_label = "Download Text Variant"
    bl_description = (
        "Download one text-model quant (Low / Medium / High). Skips if "
        "already on disk. Selects the variant once the download finishes."
    )

    variant: StringProperty(default=TEXT_MODEL_DEFAULT_KEY)
    select_on_finish: BoolProperty(default=True)

    def execute(self, context):
        if self.variant not in TEXT_MODEL_VARIANTS:
            self.report({'ERROR'}, f"Unknown variant: {self.variant!r}")
            return {'CANCELLED'}
        v = TEXT_MODEL_VARIANTS[self.variant]
        if self.select_on_finish:
            try:
                _prefs(context).selected_text_model = self.variant
            except Exception:
                pass
        return self._start_job(
            context, worker_download_text_variant,
            args=(self.variant,),
            label=f"Download {v['label']} ({v['quant']})",
        )


class BB_OT_select_text_variant(Operator):
    bl_idname = "blender_buddy.select_text_variant"
    bl_label = "Select Text Variant"
    bl_description = (
        "Make this downloaded variant the active text model. Restarts the "
        "server if it's currently running so the new weights load."
    )

    variant: StringProperty(default=TEXT_MODEL_DEFAULT_KEY)

    def execute(self, context):
        if self.variant not in TEXT_MODEL_VARIANTS:
            self.report({'ERROR'}, f"Unknown variant: {self.variant!r}")
            return {'CANCELLED'}
        if not text_model_ready(self.variant):
            self.report({'ERROR'},
                        f"{TEXT_MODEL_VARIANTS[self.variant]['label']} "
                        "variant not downloaded yet.")
            return {'CANCELLED'}
        prefs = _prefs(context)
        prefs.selected_text_model = self.variant
        # Switching variants means the currently-loaded weights are no
        # longer the selected ones — unload so the next Launch picks up
        # the right GGUF. We don't auto-relaunch: that would force a
        # 20-30 s reload when the user may have just been exploring.
        if server_is_running() and current_server_mode() == 'text':
            stop_server()
        self.report({'INFO'},
                    f"Active text model: {TEXT_MODEL_VARIANTS[self.variant]['label']}")
        return {'FINISHED'}


class BB_OT_download_vision_model(_ModalJob, Operator):
    bl_idname = "blender_buddy.download_vision_model"
    bl_label = "Download Vision Model"
    bl_description = (
        "Download the vision model (~5.8 GB). Enables the Attach "
        "Screenshot toggle so Buddy can look at what's on your screen."
    )

    def execute(self, context):
        return self._start_job(context, worker_download_vision_model,
                               args=(), label="Download vision model")


class BB_OT_open_setup_prefs(Operator):
    bl_idname = "blender_buddy.open_setup_prefs"
    bl_label = "Open Buddy Preferences"
    bl_description = (
        "Open Blender Preferences on the Buddy panel so you can pick "
        "a text-model variant and finish setup."
    )

    def execute(self, context):
        try:
            context.preferences.active_section = 'ADDONS'
        except Exception:
            pass
        try:
            context.window_manager.addon_search = "Blender Buddy"
        except Exception:
            pass
        try:
            bpy.ops.preferences.addon_expand(module=__package__)
        except Exception:
            pass
        bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
        return {'FINISHED'}


class BB_OT_open_log_folder(Operator):
    bl_idname = "blender_buddy.open_log_folder"
    bl_label = "Open Log Folder"
    bl_description = (
        "Reveal Buddy's DATAFILES directory in your OS file browser. "
        "Handy when filing a bug — server.log lives here."
    )

    def execute(self, context):
        path = data_root()
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.report({'ERROR'}, f"Couldn't open {path}: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Opened: {path}")
        return {'FINISHED'}


class BB_OT_copy_server_log(Operator):
    bl_idname = "blender_buddy.copy_server_log"
    bl_label = "Copy Server Log"
    bl_description = (
        "Copy the last ~400 lines of the running server's log to your "
        "clipboard so you can paste it into a bug report."
    )

    def execute(self, context):
        if not _server_log_path or not os.path.exists(_server_log_path):
            self.report({'WARNING'}, "No server log found yet — launch Buddy first.")
            return {'CANCELLED'}
        try:
            with open(_server_log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            tail = "\n".join(lines[-400:])
        except OSError as e:
            self.report({'ERROR'}, f"Couldn't read log: {e}")
            return {'CANCELLED'}
        context.window_manager.clipboard = tail
        self.report({'INFO'}, f"Copied {len(tail)} chars from server log.")
        return {'FINISHED'}


class BB_OT_toggle_turn_collapse(Operator):
    bl_idname = "blender_buddy.toggle_turn_collapse"
    bl_label = "Toggle Turn Collapse"
    bl_description = (
        "Collapse or expand a long response. Responses are shown fully "
        "by default; the Collapse button appears on any response 15+ "
        "lines tall so you can hide it when scrolling past."
    )
    bl_options = {'INTERNAL'}

    turn_key: StringProperty(default="")
    collapse: BoolProperty(default=True)

    def execute(self, context):
        if not self.turn_key:
            return {'CANCELLED'}
        if self.collapse:
            _turn_collapsed.add(self.turn_key)
        else:
            _turn_collapsed.discard(self.turn_key)
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


class BB_OT_cancel_download(Operator):
    bl_idname = "blender_buddy.cancel_download"
    bl_label = "Cancel Download"
    bl_description = (
        "Stop the current download. The partial file is kept so a later "
        "retry can resume from where you stopped."
    )
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, _context):
        return _job_get().get("active", False)

    def execute(self, context):
        request_download_cancel()
        self.report({'INFO'}, "Cancel requested — waiting for chunk boundary…")
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


class BB_OT_unload_model(Operator):
    bl_idname = "blender_buddy.unload_model"
    bl_label = "Unload Buddy"
    bl_description = (
        "Stop the local llama-server, free the model weights from RAM, "
        "and clear the current conversation. The next ask will relaunch "
        "the server and start a fresh conversation."
    )

    def execute(self, _context):
        was_running = server_is_running()
        had_history = bool(_conv_get())
        if was_running:
            stop_server()
        # Unload implies "reset the session" — clearing history matches
        # that mental model and keeps the next launch clean.
        _conv_clear()
        if was_running and had_history:
            self.report({'INFO'}, "Server stopped, conversation cleared.")
        elif was_running:
            self.report({'INFO'}, "Server stopped.")
        elif had_history:
            self.report({'INFO'}, "Conversation cleared.")
        else:
            self.report({'INFO'}, "Nothing to close.")
            return {'CANCELLED'}
        return {'FINISHED'}


class BB_OT_start_server(Operator):
    bl_idname = "blender_buddy.start_server"
    bl_label = "Start Server"
    bl_description = "Launch the managed llama-server"

    def execute(self, context):
        try:
            msg = start_server(_prefs(context))
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class BB_OT_stop_server(Operator):
    bl_idname = "blender_buddy.stop_server"
    bl_label = "Stop Server"
    bl_description = "Terminate the managed llama-server"

    def execute(self, _context):
        msg = stop_server()
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Launch — pre-warm the server so the first question doesn't stall for
# 20-30 s while the ~14 GB model is loaded into RAM. The panel shows a big
# "Launch Buddy" button when the server isn't running; clicking it spawns
# the server AND polls /health, surfacing a "loading model…" status the
# whole time. Once ready, the panel flips to the normal prompt row.
# ---------------------------------------------------------------------------

def worker_wait_ready(base_url):
    """Thread: poll llama-server /health until it reports ok. The server
    process itself is spawned on the main thread before this runs, so all
    we're waiting for is the model weights to load into RAM."""
    try:
        _job_set(label="Loading model", progress=0.3,
                 message="loading weights into RAM…")
        ok = _poll_server_ready(base_url, timeout=300)
        if ok:
            _job_set(done=True, progress=1.0, message="Buddy is ready.")
        else:
            _job_set(done=True,
                     error="Server didn't report ready within 5 minutes.")
    except Exception as e:
        _job_set(done=True, error=str(e))


class BB_OT_launch(_ModalJob, Operator):
    bl_idname = "blender_buddy.launch"
    bl_label = "Load Buddy"
    bl_description = (
        "Start the local model server and wait for it to finish loading "
        "(~20-30 s the first time). Doing this before your first question "
        "means the answer starts immediately instead of after a long pause."
    )

    def execute(self, context):
        prefs = _prefs(context)
        try:
            msg = start_server(prefs, mode='text')
            self.report({'INFO'}, msg)
        except Exception as e:
            self.report({'ERROR'}, f"Can't start server: {e}")
            return {'CANCELLED'}
        base = effective_server_base_url(prefs)
        return self._start_job(
            context, worker_wait_ready, args=(base,),
            label="Loading model", tick=0.3,
        )


# ---------------------------------------------------------------------------
# Ask / conversation operators
# ---------------------------------------------------------------------------

# Legacy text-block name from pre-8.11 versions; removed on load so the
# .blend isn't permanently polluted after a version bump.
_LEGACY_TEXT_BLOCK_NAME = "blender_buddy_chat.md"

# Model files from earlier versions that are no longer used. Auto-deleted
# at register() ONLY when the current TEXT_MODEL is already on disk —
# that way a mid-upgrade user (still on the old model, hasn't downloaded
# the new one yet) keeps a working setup until they hit Download.
_LEGACY_MODEL_FILENAMES = (
    "Bonsai-8B-Q1_0.gguf",                          # pre-8.8
    "Qwen3-8B-Q4_K_M.gguf",                         # v8.22-v8.27 — rolled back
    "Qwen3-8B-Instruct-2507-Q4_K_M.gguf",           # v8.22 wrong URL leftover
    "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",           # v8.28 — replaced by 30B-A3B MoE in v9.0
    "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",           # v9.3 — replaced by Qwen3-VL-8B in v9.4
    "mmproj-F16.gguf",                              # old generic mmproj — collides with new VL
)


def _cleanup_legacy_text_block():
    try:
        tb = bpy.data.texts.get(_LEGACY_TEXT_BLOCK_NAME)
        if tb is not None:
            bpy.data.texts.remove(tb)
    except Exception as e:
        print(f"[Blender Buddy] legacy text-block cleanup skipped: {e}")


def _cleanup_legacy_models():
    # Don't delete anything unless at least one current text variant is on
    # disk — we never want to leave the user with no working text model.
    if not any(text_model_ready(k) for k in TEXT_MODEL_ORDER):
        return
    # Safety: preserve every filename we currently use so nothing in the
    # active set can be removed even if someone adds it to the legacy
    # list by mistake.
    current = {v["filename"] for v in TEXT_MODEL_VARIANTS.values()}
    current.add(VISION_MODEL["filename"])
    current.add(VISION_MODEL["mmproj_filename"])
    models_d = models_dir()
    for fname in _LEGACY_MODEL_FILENAMES:
        if fname in current:
            continue
        path = os.path.join(models_d, fname)
        if os.path.exists(path):
            try:
                size_mb = os.path.getsize(path) / 1_048_576
                os.remove(path)
                print(f"[Blender Buddy] removed legacy model "
                      f"{fname} ({size_mb:,.0f} MB freed)")
            except OSError as e:
                print(f"[Blender Buddy] couldn't remove {fname}: {e}")


def _snapshot_prefs(context):
    p = _prefs(context)
    return {
        "base": effective_server_base_url(p),
        "max_tokens":   DEFAULT_MAX_TOKENS,
        # Temperature is finalized in _start_work based on action_mode;
        # CODE is the safer default in case that override is skipped.
        "temperature":  DEFAULT_TEMPERATURE_CODE,
        "timeout":      DEFAULT_TIMEOUT_SEC,
        "system_prompt": read_system_prompt(),
        "allow_online": bool(p.allow_online_access),
        "add_context":  False,   # panel-level BB_PG_props.add_context
        "scene_context": "",     # main-thread snapshot, filled in execute()
        "image_b64":    None,    # vision mode only
    }


def _build_user_message(question, image_b64):
    """Wrap the question (plus optional image) as an OpenAI-style user
    message. Vision uses a multipart `content` array; text is a plain
    string."""
    if image_b64:
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url",
                 "image_url": {
                     "url": f"data:image/png;base64,{image_b64}",
                 }},
            ],
        }
    return {"role": "user", "content": question}


_VISION_LOG_MARKERS = (
    "processing image", "encoding image", "image slice",
    "mtmd_encode", "clip_image", "image decoded",
)


def _check_vision_image_seen(log_path, since_bytes):
    """After a vision ask, scan the new section of server.log for any
    evidence that the image hit the mtmd / clip pipeline. Returns True
    if we saw proof (or if we can't tell — we never want to falsely
    accuse a working setup). Returns False only when the tail is
    present AND contains no image-processing markers, which is a strong
    signal that llama-server silently fell back to text-only.

    Background: llama.cpp had regressions in late-2025 builds where
    Qwen2.5-VL's M-RoPE was broken (issue #17930) and some builds
    predate the Qwen2.5-VL mtmd support (PR #12119, b5517+). Either way
    the image is dropped without an API-level error, so we have to peek
    at the log to catch it."""
    try:
        if not log_path or not os.path.exists(log_path):
            return True
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(since_bytes)
            tail = f.read()
        if not tail.strip():
            return True
        low = tail.lower()
        return any(m in low for m in _VISION_LOG_MARKERS)
    except Exception:
        return True


def worker_ask(snap, question, prior_history):
    """Thread: run the ask flow.

    Text mode  → agentic tool-call loop (search_web / fetch_url /
                 get_scene). Non-streaming; status updates show which
                 tool is running.
    Vision mode → direct streaming call without tools. The 3B vision
                 model is not reliable at tool calling, and screenshot
                 questions rarely need external context.
    """
    raw = ""
    try:
        # Mode-aware initial status so mode switches read clearly in the
        # UI instead of a generic "thinking…". `just_started` tells us
        # whether BB_OT_ask.execute just spawned or restarted the server
        # — if it did, the first /health poll can take 20-30 s while
        # the GGUF loads into RAM, so we label it as loading rather than
        # plain waiting.
        if snap.get("just_started"):
            if snap.get("image_b64"):
                _job_set(message="loading vision model (~3.5 GB)")
            else:
                _job_set(message="loading text model (~14 GB)")
        else:
            _job_set(message="waiting for server")
        if not _poll_server_ready(snap["base"], timeout=120):
            _job_set(done=True, error="Server didn't become ready in time.")
            return

        system_content = (snap["system_prompt"]
                          or _FALLBACK_SYSTEM_PROMPT).rstrip()
        # Append the Action-Mode addendum when the user has the code
        # toggle on. Keeps the base prompt UI-first and flips the rule
        # just for this request.
        if snap.get("action_mode"):
            system_content += ACTION_MODE_ADDENDUM
        messages = [{"role": "system", "content": system_content}]
        messages.extend(prior_history)

        if snap.get("image_b64"):
            # Vision: single streaming chat completion, no tools. Still
            # respects Action Mode (prefix the user turn with the hard
            # directive) and Deep Mode (bump max_tokens so long answers
            # have room — DEEP_TOOL_ITERATIONS is moot since there's no
            # tool loop here).
            vision_user_text = question
            if snap.get("action_mode"):
                vision_user_text = (
                    "[ACTION MODE — RESPOND WITH CODE, NOT UI STEPS.] "
                    "Write exactly ONE ```python fence that performs "
                    "this request, based on what you see in the "
                    "screenshot. No prose before or after. `bpy`, "
                    "`context`, `D`, `C` are in scope.\n\nRequest: "
                    + question
                )
            messages.append(_build_user_message(vision_user_text,
                                                snap["image_b64"]))

            def stream_cb(text_so_far):
                _job_set(
                    partial=text_so_far,
                    message=f"generating ({len(text_so_far)} chars)",
                )

            # Remember where the server log is before the request so we
            # can tail just the portion that belongs to THIS ask.
            log_before = 0
            try:
                if _server_log_path and os.path.exists(_server_log_path):
                    log_before = os.path.getsize(_server_log_path)
            except Exception:
                pass

            _job_set(message="generating")
            vision_max_tokens = (DEEP_MAX_TOKENS
                                  if snap.get("add_context")
                                  else snap["max_tokens"])
            print(f"[Blender Buddy] vision  action_mode="
                  f"{bool(snap.get('action_mode'))}  "
                  f"deep={bool(snap.get('add_context'))}  "
                  f"max_tokens={vision_max_tokens}")
            raw = _call_chat_messages(
                snap["base"], messages,
                vision_max_tokens, snap["temperature"], snap["timeout"],
                stream_cb=stream_cb,
            )

            # Diagnose silent image drop — happens when the llama.cpp
            # build is too old for Qwen2.5-VL mtmd, or is in the M-RoPE
            # regression window. Append a visible note to the answer so
            # the user sees it and can reinstall.
            if not _check_vision_image_seen(_server_log_path, log_before):
                raw = (raw or "").rstrip() + (
                    "\n\n---\n_Heads-up: the server log shows no image "
                    "processing for this question — your llama.cpp build "
                    "may be too old for Qwen2.5-VL, or has a known "
                    "M-RoPE bug. Try Preferences → Install to fetch a "
                    "newer build, then ask again._"
                )
        else:
            # Text: always-on scene tool + web tools gated by pref. Deep
            # mode (add_context) doubles the token budget and tool-round
            # cap so the model can search further and write longer code.
            # Action mode: prepend a hard directive to the user's turn
            # so the model can't miss it — the system-prompt addendum
            # alone kept getting overridden by the "Default is UI"
            # section that dominates the middle of the prompt.
            user_text = question
            if snap.get("action_mode"):
                user_text = (
                    "[ACTION MODE — RESPOND WITH CODE, NOT UI STEPS.] "
                    "Write exactly ONE ```python fence that performs "
                    "this request. No prose before or after. `bpy`, "
                    "`context`, `D`, `C` are in scope — no import, no "
                    "__main__ guard, no try/except. Call search_api "
                    "first only to verify operator / property / enum "
                    "names you're not 100% sure of; then write the "
                    "code.\n\nRequest: " + question
                )
            messages.append({"role": "user", "content": user_text})
            print(f"[Blender Buddy] action_mode="
                  f"{bool(snap.get('action_mode'))}  "
                  f"deep={bool(snap.get('add_context'))}")
            tools = _build_tools_schema(
                allow_online=snap.get("allow_online", True),
            )
            deep = bool(snap.get("add_context"))
            max_tokens = DEEP_MAX_TOKENS if deep else DEFAULT_MAX_TOKENS
            max_iters  = DEEP_TOOL_ITERATIONS if deep else MAX_TOOL_ITERATIONS

            def status_cb(m):
                _job_set(message=m)
            raw = _tool_loop(
                snap["base"], messages,
                max_tokens, snap["temperature"], snap["timeout"],
                tools=tools,
                scene_snapshot=snap.get("scene_context", ""),
                status_cb=status_cb,
                max_iterations=max_iters,
            )
            # Post-generation AST linter: scan code blocks for
            # hallucinated bpy identifiers and append a warning footer.
            try:
                raw = _append_lint_warnings(raw)
            except Exception as e:
                print(f"[Blender Buddy] linter failed: {e}")
            # Show the final answer in the panel's "partial" slot so the
            # streaming-style placeholder gets replaced before done fires.
            _job_set(partial=raw)

        print(f"[Blender Buddy] raw ({len(raw)} chars):\n{raw}\n[/Blender Buddy]")
        _job_set(done=True, answer=raw, raw_question=question)

    except urllib.error.HTTPError as e:
        if e.code == 400:
            _job_set(done=True, error=(
                "Server rejected request (HTTP 400). The context window "
                "may be full. Try Clear Conversation."
            ), answer=raw)
            return
        if e.code == 500:
            try:
                ctx = int(getattr(_prefs(), "context_size",
                                  DEFAULT_CONTEXT_SIZE)
                          or DEFAULT_CONTEXT_SIZE)
            except Exception:
                ctx = DEFAULT_CONTEXT_SIZE
            if ctx > 8192:
                tip = (
                    f" Your context size is set to {ctx // 1024} k — "
                    f"this is often too high for the amount of RAM / "
                    f"VRAM available. In preferences, drop Context "
                    f"size to 8 k or 16 k, then Unload + Load Buddy."
                )
            else:
                tip = (
                    " Try Unload + Load Buddy. If it keeps happening, "
                    "a smaller text-model tier may fit your system "
                    "better."
                )
            _job_set(done=True, error=(
                "Server error (HTTP 500). The model likely ran out of "
                "memory while generating." + tip
            ), answer=raw)
            return
        _job_set(done=True, error=str(e), answer=raw)
    except (ConnectionResetError, ConnectionAbortedError,
            urllib.error.URLError) as e:
        # Connection reset usually means llama-server crashed or exited
        # mid-request — OOM, KV-cache exhaustion, or a model edge case.
        # Check whether the process is still alive and give the user an
        # actionable message either way.
        alive = server_is_running()
        if not alive:
            msg = ("llama-server crashed or exited mid-request. Click "
                   "Load Buddy to relaunch it. Common causes: out of "
                   "RAM, KV cache exhausted, bad model edge case. "
                   "Check server.log in the datafiles folder for "
                   "details. Original error: " + str(e))
        else:
            msg = ("Connection dropped mid-request. The server may be "
                   "overloaded or hung. Try Unload Buddy then Load "
                   "Buddy. Original error: " + str(e))
        _job_set(done=True, error=msg, answer=raw)
    except Exception as e:
        _job_set(done=True, error=str(e), answer=raw)


def _strip_scene_ctx_prefix(user_content):
    """Strip prefixed data blocks (BLENDER STATE / WEB SEARCH RESULTS)
    and the 'CURRENT QUESTION:' marker so the panel displays just the
    user's actual question. Runs on turns stored in history too, though
    we commit the raw question to history — this is belt-and-suspenders
    for older turns that may still have the old prefix format."""
    marker = "CURRENT QUESTION:\n"
    idx = user_content.find(marker)
    if idx != -1:
        return user_content[idx + len(marker):].strip()
    # Back-compat: older format used "Question: " in a single block
    legacy = "\n\nQuestion: "
    idx = user_content.find(legacy)
    if idx != -1:
        return user_content[idx + len(legacy):].strip()
    return user_content


class BB_OT_ask(_ModalJob, Operator):
    bl_idname = "blender_buddy.ask"
    bl_label = "Ask"
    bl_description = (
        "Send the question to Blender Buddy. Prior turns in the conversation "
        "are included automatically; click 'Clear Conversation' to reset."
    )
    bl_options = {'REGISTER'}

    # Two modal phases share this operator:
    #   PICK — cursor is a crosshair; wait for LEFTMOUSE to choose which
    #          editor area to screenshot. Entered only when the user has
    #          selected Attach Screenshot + Select Area.
    #   WORK — classic _ModalJob redraw-and-poll loop while the worker
    #          thread talks to llama-server.
    _phase = 'WORK'
    _cursor_active = False
    _status_active = False

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        props = context.scene.blender_buddy_props
        question = props.question.strip()
        if not question:
            self.report({'WARNING'}, "Type a question first.")
            return {'CANCELLED'}

        want_mode = 'vision' if props.attach_image else 'text'
        if want_mode == 'vision' and not vision_model_ready():
            self.report(
                {'ERROR'},
                "Vision model not downloaded. Open Preferences and click "
                "'Download Models' (~3.4 GB, one-time)."
            )
            return {'CANCELLED'}

        # AREA mode now means "let the user click the area to capture".
        # Enter the PICK modal first; the click handler will call back
        # into _start_work with the captured image.
        if (want_mode == 'vision'
                and props.screenshot_scope == 'AREA'):
            self._phase = 'PICK'
            try:
                context.window.cursor_modal_set('EYEDROPPER')
                self._cursor_active = True
            except Exception:
                pass
            try:
                context.workspace.status_text_set(
                    "Click an editor area to capture for Buddy  •  "
                    "Esc / Right-click to cancel"
                )
                self._status_active = True
            except Exception:
                pass
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        # WINDOW / CUSTOM / text mode — synchronous capture (or none).
        image_b64 = None
        if want_mode == 'vision':
            image_b64 = _capture_screenshot(
                scope=props.screenshot_scope,
                custom_path=props.custom_image_path,
            )
            if not image_b64:
                msg = ("Couldn't load custom image. Check the file path."
                       if props.screenshot_scope == 'CUSTOM'
                       else "Couldn't capture screenshot.")
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

        return self._start_work(context, image_b64,
                                register_handler=True)

    # -- PICK phase -------------------------------------------------------

    def _end_pick_ui(self, context):
        """Restore cursor + status bar after PICK ends (click, cancel, or
        error). Idempotent so we can call it from any exit path."""
        if self._cursor_active:
            try:
                context.window.cursor_modal_restore()
            except Exception:
                pass
            self._cursor_active = False
        if self._status_active:
            try:
                context.workspace.status_text_set(None)
            except Exception:
                pass
            self._status_active = False

    def _modal_pick(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._end_pick_ui(context)
            self.report({'INFO'}, "Area select cancelled.")
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            mx, my = event.mouse_x, event.mouse_y
            target = None
            for area in context.window.screen.areas:
                if (area.x <= mx <= area.x + area.width and
                        area.y <= my <= area.y + area.height):
                    target = area
                    break
            self._end_pick_ui(context)
            if target is None:
                self.report({'WARNING'}, "Click missed every area — cancelled.")
                return {'CANCELLED'}
            image_b64 = _capture_area_to_b64(target)
            if not image_b64:
                self.report({'ERROR'},
                            f"Couldn't capture the {target.type} area.")
                return {'CANCELLED'}
            # Transition from PICK to WORK. We're already the active
            # modal handler, so don't re-register.
            self._phase = 'WORK'
            return self._start_work(context, image_b64,
                                    register_handler=False)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if self._phase == 'PICK':
            return self._modal_pick(context, event)
        return _ModalJob.modal(self, context, event)

    # -- WORK phase -------------------------------------------------------

    def _start_work(self, context, image_b64, register_handler):
        """Server-start + snapshot + worker-spawn. Shared by the plain
        execute() path and the PICK → WORK transition."""
        props = context.scene.blender_buddy_props
        question = props.question.strip()
        want_mode = 'vision' if props.attach_image else 'text'

        just_started = False
        if (not server_is_running()) or current_server_mode() != want_mode:
            try:
                msg = start_server(_prefs(context), mode=want_mode)
                just_started = True
                self.report({'INFO'}, msg)
            except Exception as e:
                self.report({'ERROR'}, f"Can't start server: {e}")
                return {'CANCELLED'}

        snap = _snapshot_prefs(context)
        snap["image_b64"]    = image_b64
        snap["mode"]         = want_mode
        snap["add_context"]  = bool(props.add_context)
        snap["action_mode"]  = bool(props.action_mode)
        # Tie sampling temperature to the user's code-vs-prose intent:
        # Action Mode ON → tighter sampling for deterministic bpy code;
        # Action Mode OFF → slightly looser for natural UI/tutorial prose.
        snap["temperature"]  = (DEFAULT_TEMPERATURE_CODE if props.action_mode
                                else DEFAULT_TEMPERATURE_PROSE)
        snap["just_started"] = just_started
        prior = _conv_get()
        try:
            snap["scene_context"] = _build_scene_snapshot()
        except Exception as e:
            print(f"[Blender Buddy] scene snapshot failed: {e}")
            snap["scene_context"] = {
                "summary": "", "objects": {},
                "selection": "", "node_trees": {},
                "datablocks": {}, "timeline": "",
                "animation": {"objects": {}, "actions": {}, "shape_keys": {}},
                "render_settings": "", "viewport_state": "",
            }

        return self._start_job(
            context, worker_ask,
            args=(snap, question, prior),
            label="Answering", tick=0.15,
            register_handler=register_handler,
        )

    def _finish(self, context, state):
        if state.get("error"):
            self.report({'ERROR'}, f"Ask failed: {state['error']}")
            return {'CANCELLED'}

        answer = (state.get("answer") or "").strip()
        raw_question = state.get("raw_question") or ""
        props = context.scene.blender_buddy_props

        # Commit CLEAN history (no context decoration) so future turns get
        # fresh context blocks and the transcript stays readable.
        if raw_question:
            _conv_append("user", raw_question)
        if answer:
            # Strip <think> blocks before storing so (a) follow-up turns
            # don't see old reasoning as context and (b) the Copy button
            _conv_append("assistant", answer)

        # Clear the input so the next question is easy to type.
        props.question = ""

        self.report({'INFO'},
                    f"Answer: {len(answer.splitlines())} lines  |  "
                    f"turns: {len(_conv_get()) // 2}")
        return {'FINISHED'}


class BB_OT_clear_conversation(Operator):
    bl_idname = "blender_buddy.clear_conversation"
    bl_label = "Clear Conversation"
    bl_description = (
        "Forget all prior turns. The next question starts a fresh conversation "
        "(system prompt + scene context re-sent). Hotkey: Esc when the Buddy "
        "sidebar tab is active."
    )

    def execute(self, context):
        _conv_clear()
        # Force every area to redraw so the cleared state is visible
        # immediately — without this the sidebar still shows the old turns
        # until the cursor moves.
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        self.report({'INFO'}, "Conversation cleared.")
        return {'FINISHED'}


class BB_OT_revert_last_message(Operator):
    bl_idname = "blender_buddy.revert_last_message"
    bl_label = "Revert"
    bl_description = (
        "Remove the most recent question + answer pair from the "
        "conversation. Handy when an answer didn't help and you want "
        "to re-ask with a tweak, or drop the pair entirely from the "
        "context window. Token counter updates automatically."
    )
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, _context):
        # Disabled while a request is in flight — popping history mid-ask
        # would race with the worker appending the response.
        if _job_get().get("active"):
            return False
        return len(_conv_get()) > 0

    def execute(self, context):
        # Pop up to 2 entries so a single click drops the full
        # (user, assistant) pair. When not busy, _conversation is
        # always even-length, so 2 is the normal case; the odd-length
        # guard is defensive for edge scenarios where a pair might
        # have been appended half-complete.
        removed_roles = []
        with _conversation_lock:
            for _ in range(2):
                if not _conversation:
                    break
                removed_roles.append(_conversation.pop().get("role", "message"))
        if not removed_roles:
            return {'CANCELLED'}
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        if len(removed_roles) == 2:
            self.report({'INFO'}, "Reverted last question + answer.")
        else:
            self.report({'INFO'}, f"Reverted last {removed_roles[0]} message.")
        return {'FINISHED'}


class BB_OT_esc_clear(Operator):
    """Esc-keymap shim: only fires when the cursor is over a sidebar UI
    region with the Buddy tab active. Forwards to clear_conversation, which
    has no poll restriction so the panel button is always enabled. Splitting
    these two avoids the chicken-and-egg of the button being grayed out
    during draw because Blender's poll context didn't see the UI region."""
    bl_idname = "blender_buddy.esc_clear"
    bl_label = "Clear Conversation (Esc)"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        region = getattr(context, 'region', None)
        if region is None or region.type != 'UI':
            return False
        try:
            return region.active_panel_category == "Buddy"
        except (AttributeError, TypeError):
            return False

    def execute(self, _context):
        bpy.ops.blender_buddy.clear_conversation()
        return {'FINISHED'}


class BB_OT_copy_code_block(Operator):
    bl_idname = "blender_buddy.copy_code_block"
    bl_label = "Copy Code"
    bl_description = "Copy this code block to the system clipboard"
    bl_options = {'INTERNAL'}

    # The code body is passed through as an operator property, which is how
    # we get per-block scoping — one operator class, N button instances,
    # each with its own `code` value.
    code: StringProperty(name="code", default="")

    def execute(self, context):
        if not self.code:
            self.report({'WARNING'}, "Nothing to copy.")
            return {'CANCELLED'}
        context.window_manager.clipboard = self.code
        self.report({'INFO'}, f"Copied {len(self.code)} chars to clipboard.")
        return {'FINISHED'}


# Session-scoped trust flag for the Run button. Flipped to True by the
# confirmation dialog when the user ticks "don't ask again this session".
# Module-global is the right scope here — resets on Blender restart, on
# addon disable/enable, and on any script reload. No persistence across
# restarts means a fresh Blender session always asks at least once.
_run_code_trusted_this_session = False


# Dangerous-call surface. Any AST attribute chain whose "module path"
# starts with one of these strings flags the snippet as risky. Kept
# intentionally broad — the dialog lists the exact call that tripped it
# so the user can approve / skip, and the list is static (not model-
# controlled). None of these are forbidden — the scanner only warns.
_DANGEROUS_CALLS = (
    # Filesystem destructive
    "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.truncate",
    "shutil.rmtree", "shutil.move", "shutil.copytree", "shutil.chown",
    "pathlib.Path.unlink", "pathlib.Path.rmdir",
    # Shell / process escape
    "os.system", "os.popen", "os.execv", "os.execve", "os.execl",
    "os.execlp", "os.execvp", "os.spawnl", "os.spawnv", "os.fork",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput",
    # Dynamic import / code eval
    "__import__", "importlib.import_module", "importlib.reload",
    "compile", "eval", "exec",
    # Raw network
    "socket.socket", "socket.create_connection",
    "urllib.request.urlopen", "urllib.request.urlretrieve",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "ftplib.FTP", "smtplib.SMTP",
    # Native-code escape hatches
    "ctypes.CDLL", "ctypes.WinDLL", "ctypes.cdll", "ctypes.windll",
)


def _resolve_attr_chain(node):
    """Return the dotted-path string for an ast.Attribute / ast.Name node,
    e.g. `os.system` or `subprocess.Popen`. Returns '' for chains rooted
    at anything other than a plain Name (e.g. obj.attr where `obj` is
    itself a call). Helper for _scan_code_for_danger."""
    parts = []
    cur = node
    while isinstance(cur, _ast_mod.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, _ast_mod.Name):
        return ""
    parts.append(cur.id)
    return ".".join(reversed(parts))


def _scan_code_for_danger(code):
    """Static pre-exec scan. Returns a list of (line_no, call_path)
    tuples — one per suspicious call site — so the confirm dialog can
    show the user exactly what tripped the warning. Pure static check;
    we do NOT resolve aliases (`import os as O; O.system(...)` slips
    through). The goal is a fast reasonable-effort warning, not a
    rigorous sandbox.

    Also flags two non-call patterns:
      * `open(path, 'w'|'a'|'x'|...)` — destructive file writes
      * syntax errors — returned as a single [(0, 'syntax error: ...')]
    """
    findings = []
    try:
        tree = _ast_mod.parse(code)
    except SyntaxError as e:
        return [(e.lineno or 0, f"syntax error: {e.msg}")]
    for node in _ast_mod.walk(tree):
        if not isinstance(node, _ast_mod.Call):
            continue
        line = getattr(node, "lineno", 0) or 0
        func = node.func
        # attribute-chain calls like os.system(...)
        if isinstance(func, _ast_mod.Attribute):
            path = _resolve_attr_chain(func)
            if not path:
                continue
            for danger in _DANGEROUS_CALLS:
                if path == danger or path.endswith("." + danger):
                    findings.append((line, path))
                    break
        # bare-name calls like eval(...) / __import__(...) / open(...)
        elif isinstance(func, _ast_mod.Name):
            name = func.id
            if name in ("eval", "exec", "compile", "__import__"):
                findings.append((line, name))
            elif name == "open" and len(node.args) >= 2:
                mode_arg = node.args[1]
                if isinstance(mode_arg, _ast_mod.Constant) and isinstance(mode_arg.value, str):
                    m = mode_arg.value
                    if any(c in m for c in ("w", "a", "x", "+")):
                        findings.append((line, f"open(..., {m!r})"))
    return findings


def _resolve_live_bpy_expr(node):
    """Given an AST expression, statically resolve it against live bpy
    state WITHOUT executing any user code. Only follows Name `bpy`,
    Attribute accesses, and Subscript lookups with constant-string
    keys — so we never invoke functions or touch user variables.
    Returns the live object or None.

    The scanner uses this to check that `bpy.data.materials["X"]` etc
    references point at something that actually exists before the user
    runs the snippet."""
    if isinstance(node, _ast_mod.Name):
        return bpy if node.id == "bpy" else None
    if isinstance(node, _ast_mod.Attribute):
        base = _resolve_live_bpy_expr(node.value)
        if base is None:
            return None
        return getattr(base, node.attr, None)
    if isinstance(node, _ast_mod.Subscript):
        base = _resolve_live_bpy_expr(node.value)
        if base is None:
            return None
        idx = node.slice
        if isinstance(idx, _ast_mod.Constant) and isinstance(idx.value, str):
            try:
                return base[idx.value]
            except (KeyError, TypeError, AttributeError):
                return None
        return None
    return None


def _expr_source(node, code_lines):
    """Best-effort reconstruction of the source snippet for an AST
    node. Falls back to ast.unparse when source segments aren't
    available (older cpython, edge case)."""
    try:
        if code_lines and hasattr(node, "lineno"):
            line = code_lines[node.lineno - 1]
            if hasattr(node, "col_offset") and hasattr(node, "end_col_offset"):
                return line[node.col_offset:node.end_col_offset]
    except Exception:
        pass
    try:
        return _ast_mod.unparse(node)
    except Exception:
        return "<expr>"


# Blender 4.0 renamed / split a bunch of Principled BSDF sockets. The
# LLM's training data skews toward pre-4.0 docs, so it routinely writes
# `node.inputs["Subsurface"]` / `.inputs["Specular"]` / etc on code
# meant for Blender 4.x+. We can't tell from the AST what node type a
# local variable refers to, but if a legacy socket name shows up in an
# `.inputs[...]` / `.outputs[...]` subscript at all, it's almost
# certainly this problem — so flag it. Empty-string values mean the
# socket was removed outright with no direct replacement.
_LEGACY_SOCKET_RENAMES = {
    "Subsurface":             "Subsurface Weight",
    "Subsurface Color":       "",  # removed; bake into base color or use Subsurface Radius
    "Specular":               "Specular IOR Level",
    "Sheen":                  "Sheen Weight",
    "Clearcoat":              "Coat Weight",
    "Clearcoat Roughness":    "Coat Roughness",
    "Clearcoat Normal":       "Coat Normal",
    "Clearcoat Tint":         "Coat Tint",
    "Transmission":           "Transmission Weight",
    "Transmission Roughness": "",  # removed in 4.x
    # "Emission" still exists but as "Emission Color" + "Emission Strength"
    # is the new idiom. Only flag when paired with a scalar .default_value
    # assignment would be misleading — too noisy to flag the name alone.
}


def _scan_code_for_unknown_keys(code):
    """Catch `bpy_prop_collection["Name"]: key not found` errors before
    exec. Two flavours of check, both read-only — never calls user
    code, never mutates data:

    1. **Live lookup:** for subscripts whose base resolves through
       `bpy.*` against the current scene, verify the key exists in the
       collection. Offers a `difflib` near-match suggestion.

    2. **Legacy socket names:** when the base is a local variable (so
       we can't live-resolve) but the subscript is `.inputs[...]` or
       `.outputs[...]` and the key matches a known Blender 4.0+ rename
       table, flag it with the correct new name.

    Returns a list of dicts:
        {"line": int, "expr": str, "key": str, "suggest": str | None}
    """
    findings = []
    try:
        tree = _ast_mod.parse(code)
    except SyntaxError:
        return findings
    code_lines = code.splitlines()
    for node in _ast_mod.walk(tree):
        if not isinstance(node, _ast_mod.Subscript):
            continue
        idx = node.slice
        if not (isinstance(idx, _ast_mod.Constant) and isinstance(idx.value, str)):
            continue
        key = idx.value
        base = _resolve_live_bpy_expr(node.value)

        # --- Check 2: legacy socket rename — only when we couldn't
        # resolve the base (usually because it's a local variable from
        # nodes.new(...) or similar). If we did resolve it and the key
        # is actually present, great. If we did resolve it and the key
        # is missing, check 1 catches that more precisely below.
        if base is None:
            if (isinstance(node.value, _ast_mod.Attribute)
                    and node.value.attr in ("inputs", "outputs")
                    and key in _LEGACY_SOCKET_RENAMES):
                new_name = _LEGACY_SOCKET_RENAMES[key]
                findings.append({
                    "line":    getattr(node, "lineno", 0) or 0,
                    "expr":    _expr_source(node, code_lines),
                    "key":     key,
                    "suggest": new_name if new_name else "(socket removed in Blender 4.0)",
                })
            continue

        # --- Check 1: live lookup. Must be a collection with .keys().
        keys_fn = getattr(base, "keys", None)
        if not callable(keys_fn):
            continue
        try:
            existing = list(keys_fn())
        except Exception:
            continue
        if not existing:
            continue  # empty collection — probably a freshly-built scene
        if key in existing:
            continue  # valid reference
        import difflib
        match = difflib.get_close_matches(key, existing, n=1, cutoff=0.6)
        findings.append({
            "line":    getattr(node, "lineno", 0) or 0,
            "expr":    _expr_source(node, code_lines),
            "key":     key,
            "suggest": match[0] if match else None,
        })
    return findings


class BB_OT_run_code_block(Operator):
    bl_idname = "blender_buddy.run_code_block"
    bl_label = "Run Code"
    bl_description = (
        "Execute this code in Blender's Python. Runs with `bpy`, `context`, "
        "`D`, `C` in scope and a 3D Viewport override if available so "
        "operators like bpy.ops.mesh.* work. Ctrl+Z to undo what it did."
    )
    # UNDO lets Blender wrap any data-block changes the snippet makes into
    # a single undo step, so Ctrl+Z reverts the whole thing cleanly.
    bl_options = {'INTERNAL', 'REGISTER', 'UNDO'}

    code: StringProperty(name="code", default="")
    # Checked by the confirm dialog. When True on execute(), we record
    # session-wide trust so the rest of the session runs without prompts.
    trust_session: BoolProperty(
        name="Don't ask again this session",
        description=(
            "Skip this confirmation for every Run click until Blender "
            "restarts or the addon is reloaded."
        ),
        default=False,
    )
    # Set internally by invoke() so execute() knows whether to prompt
    # again. Skipping the prompt entirely on subsequent runs relies on
    # _run_code_trusted_this_session being True.
    skip_prompt: BoolProperty(default=False, options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.code.strip():
            self.report({'WARNING'}, "Nothing to run.")
            return {'CANCELLED'}
        # Session trust short-circuits the dialog UNLESS the key
        # scanner flagged something — broken references catch obvious
        # bugs the user hasn't seen yet, and silently exec-ing into a
        # KeyError is exactly what the scanner exists to prevent.
        if _run_code_trusted_this_session and not _scan_code_for_unknown_keys(self.code):
            self.skip_prompt = True
            return self.execute(context)
        # Show the confirm dialog. invoke_props_dialog renders each
        # property plus an OK/Cancel pair; OK flows into execute().
        self.skip_prompt = False
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        """Confirmation dialog body. Top-to-bottom:
            1. title
            2. dangerous-call findings (if any)
            3. unknown-key findings (if any) — catches the common
               `bpy.data.X["Missing"]` KeyError before exec
            4. code preview
            5. "Don't ask again this session" checkbox
        """
        layout = self.layout
        danger_findings = _scan_code_for_danger(self.code)
        key_findings = _scan_code_for_unknown_keys(self.code)

        head = layout.row()
        head.label(text="Run AI-generated Python?", icon='SCRIPTPLUGINS')

        if danger_findings:
            warn = layout.box()
            wrow = warn.row()
            wrow.alert = True
            wrow.label(
                text=f"Flagged {len(danger_findings)} potentially dangerous call"
                     f"{'s' if len(danger_findings) != 1 else ''}:",
                icon='ERROR',
            )
            # Cap to 8 entries in the dialog; the rest are in the model's
            # output anyway. Each row: "line 3: os.system".
            for line, path in danger_findings[:8]:
                row = warn.row()
                row.alert = True
                row.label(text=f"  line {line}: {path}", icon='DOT')
            if len(danger_findings) > 8:
                warn.label(text=f"  …and {len(danger_findings) - 8} more.")
        elif not key_findings:
            ok = layout.box()
            ok.label(text="No dangerous calls detected by the scanner.",
                     icon='CHECKMARK')
            ok.label(text="Scanner is advisory — review the code yourself before running.",
                     icon='INFO')

        # Unknown-key references — distinct visual from the danger box
        # (uses TRACKER_DATA icon rather than ERROR) so the user can
        # tell security issues from "this'll throw KeyError at runtime"
        # issues at a glance. Always shows a suggestion line when
        # difflib finds a close match.
        if key_findings:
            kwarn = layout.box()
            kwarn.label(
                text=f"Likely missing reference"
                     f"{'s' if len(key_findings) != 1 else ''} "
                     f"({len(key_findings)}) — would throw KeyError:",
                icon='TRACKER_DATA',
            )
            for f in key_findings[:8]:
                row = kwarn.row(align=True)
                row.alert = True
                row.label(text=f"  line {f['line']}: {f['expr']}", icon='DOT')
                if f.get("suggest"):
                    hint = kwarn.row()
                    hint.label(text=f"     did you mean {f['suggest']!r}?",
                               icon='INFO')
            if len(key_findings) > 8:
                kwarn.label(text=f"  …and {len(key_findings) - 8} more.")

        # Code preview, line-capped to keep the dialog compact.
        code_box = layout.box()
        code_box.label(text="Code:", icon='TEXT')
        lines = self.code.split("\n")
        max_lines = 18
        col = code_box.column(align=True)
        for ln in lines[:max_lines]:
            col.label(text=ln[:160])
        if len(lines) > max_lines:
            col.label(text=f"  … ({len(lines) - max_lines} more lines)")

        # "Don't ask again" checkbox — rendered larger than the rest
        # of the dialog so it's hard to miss when the user actually
        # wants to opt out of the confirmation loop.
        trust_row = layout.row()
        trust_row.scale_y = 1.6
        trust_row.prop(self, "trust_session")

    def execute(self, context):
        global _run_code_trusted_this_session
        if not self.code.strip():
            self.report({'WARNING'}, "Nothing to run.")
            return {'CANCELLED'}

        # If execute was reached through the dialog (not the trust
        # short-circuit), the user clicked OK. Honour the trust toggle.
        if not self.skip_prompt and self.trust_session:
            _run_code_trusted_this_session = True

        # Give the snippet Blender's usual script-editor globals so common
        # patterns (bpy.ops.*, bpy.data.*, C.object, D.meshes) just work.
        g = {
            '__name__': '__main__',
            'bpy':      bpy,
            'context':  context,
            'C':        context,
            'D':        bpy.data,
        }

        # Many ops (e.g. mesh.primitive_cube_add) need a 3D Viewport context
        # to resolve. Find one in the active window so snippets run reliably
        # even when clicked from a non-viewport editor.
        view_area   = None
        view_region = None
        for area in context.window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        view_area, view_region = area, region
                        break
                if view_area is not None:
                    break

        import traceback
        # Push a named undo step BEFORE exec so Ctrl+Z reverts the
        # whole snippet as one action, regardless of how many data
        # edits it made. Best-effort: an undo_push failure (e.g. no
        # active scene) shouldn't block the run.
        try:
            bpy.ops.ed.undo_push(message="Blender Buddy: Run")
        except Exception:
            pass
        try:
            if view_area is not None:
                with context.temp_override(area=view_area, region=view_region):
                    exec(self.code, g, g)
            else:
                exec(self.code, g, g)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'},
                        f"Run failed: {type(e).__name__}: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, "Code executed.")
        return {'FINISHED'}


class BB_OT_copy_message(Operator):
    """Per-message clipboard copy. Drawn as an icon-only button under each
    assistant turn so the user can copy *that specific* message (not just
    'the latest one' like the old action-row Copy did)."""
    bl_idname = "blender_buddy.copy_message"
    bl_label = "Copy message"
    bl_description = "Copy this response to the clipboard"
    bl_options = {'INTERNAL'}

    content: StringProperty(name="content", default="")

    def execute(self, context):
        if not self.content:
            self.report({'WARNING'}, "Nothing to copy.")
            return {'CANCELLED'}
        context.window_manager.clipboard = self.content
        self.report({'INFO'}, f"Copied {len(self.content)} chars.")
        return {'FINISHED'}


class BB_OT_copy_answer(Operator):
    bl_idname = "blender_buddy.copy_answer"
    bl_label = "Copy"
    bl_description = "Copy the latest answer to the system clipboard"

    def execute(self, context):
        history = _conv_get()
        latest = ""
        for msg in reversed(history):
            if msg["role"] == "assistant":
                latest = msg["content"]
                break
        if not latest:
            self.report({'WARNING'}, "No answer to copy yet.")
            return {'CANCELLED'}
        context.window_manager.clipboard = latest
        self.report({'INFO'}, f"Copied {len(latest)} chars to clipboard.")
        return {'FINISHED'}


class BB_OT_edit_system_prompt(Operator):
    bl_idname = "blender_buddy.edit_system_prompt"
    bl_label = "Edit System Prompt"
    bl_description = (
        "Open the active system_prompt.txt in your OS default editor. "
        "Gets auto-seeded from blender_buddy_assets/system_prompt_default.txt "
        "the first time."
    )

    def execute(self, _context):
        path = system_prompt_path()
        if not os.path.isfile(path):
            # Seeds the active file from the bundled default so there's
            # always something to edit.
            reset_system_prompt_to_default()
        try:
            open_in_default_editor(path)
        except Exception as e:
            self.report({'ERROR'}, f"Couldn't open {path}: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Opened {path}")
        return {'FINISHED'}


class BB_OT_reset_system_prompt(Operator):
    bl_idname = "blender_buddy.reset_system_prompt"
    bl_label = "Reset System Prompt"
    bl_description = (
        "Overwrite the active system_prompt.txt with the shipped default "
        "(blender_buddy_assets/system_prompt_default.txt). The default "
        "file itself is never modified — it's a read-only backup."
    )

    def execute(self, _context):
        try:
            reset_system_prompt_to_default()
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, "System prompt reset to default.")
        return {'FINISHED'}


def _activate_buddy_tab(area):
    """Open `area`'s sidebar and switch its UI region to the Buddy category.
    Returns True if the category was successfully set."""
    space = area.spaces.active
    if space is not None and hasattr(space, 'show_region_ui'):
        space.show_region_ui = True
    for region in area.regions:
        if region.type != 'UI':
            continue
        try:
            region.active_panel_category = "Buddy"
        except (AttributeError, TypeError):
            return False
        region.tag_redraw()
        return region.active_panel_category == "Buddy"
    return False


class BB_OT_summon(Operator):
    bl_idname = "blender_buddy.summon"
    bl_label = "Toggle Blender Buddy Sidebar"
    bl_description = (
        "Toggle the Blender Buddy sidebar in the editor under the cursor. "
        "If Buddy is already the open tab, the sidebar closes; otherwise "
        "the sidebar opens and switches to Buddy."
    )
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        # Prefer the area under the cursor — that matches user intent (they
        # pressed the key while looking at that editor). Fall back to any
        # sidebar-supporting area if the cursor area doesn't have one (e.g.
        # cursor over Outliner / Properties).
        target = None
        mx, my = event.mouse_x, event.mouse_y
        for area in context.screen.areas:
            if (area.x <= mx <= area.x + area.width and
                    area.y <= my <= area.y + area.height):
                if area.type in _SIDEBAR_SPACES:
                    target = area
                break
        if target is None:
            for area in context.screen.areas:
                if area.type in _SIDEBAR_SPACES:
                    target = area
                    break
        if target is None:
            self.report({'WARNING'},
                        "No editor with a sidebar in this workspace.")
            return {'CANCELLED'}

        # TOGGLE behavior: if the sidebar is already open AND Buddy is the
        # active tab, the hotkey should close the sidebar (dismiss Buddy).
        # Otherwise it opens the sidebar and activates Buddy.
        space = target.spaces.active
        if (space is not None
                and getattr(space, 'show_region_ui', False)):
            for region in target.regions:
                if region.type == 'UI':
                    try:
                        if region.active_panel_category == "Buddy":
                            space.show_region_ui = False
                            region.tag_redraw()
                            return {'FINISHED'}
                    except (AttributeError, TypeError):
                        pass
                    break

        # First attempt synchronously. In some editors (Spreadsheet, certain
        # Node Editor states) the UI region's category list isn't populated
        # until the sidebar has drawn at least once, so the first set silently
        # no-ops. We retry on a short timer to catch that case — by then the
        # sidebar has had a frame to initialize.
        _activate_buddy_tab(target)

        target_x, target_y, target_type = target.x, target.y, target.type

        def _retry():
            for area in bpy.context.screen.areas:
                if (area.type == target_type
                        and area.x == target_x and area.y == target_y):
                    _activate_buddy_tab(area)
                    return None
            return None

        bpy.app.timers.register(_retry, first_interval=0.05)
        return {'FINISHED'}


class BB_OT_dev_reload(Operator):
    bl_idname = "blender_buddy.dev_reload"
    bl_label = "Reload addon from disk"
    bl_description = (
        "Stop the managed server, then run Blender's Reload Scripts."
    )

    def execute(self, _context):
        try:
            stop_server()
        except Exception:
            pass

        def _do_reload():
            try:
                bpy.ops.script.reload()
                print("[Blender Buddy] bpy.ops.script.reload() fired")
            except Exception as e:
                print(f"[Blender Buddy] script.reload failed: {e}")
            return None

        bpy.app.timers.register(_do_reload, first_interval=0.1)
        self.report({'INFO'}, f"Reloading {os.path.abspath(__file__)}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Hotkey
# ---------------------------------------------------------------------------

_addon_keymaps = []

# Filled by _register_keymap when it finds an existing binding on the same
# (key, modifiers) combo belonging to another operator. Displayed in
# preferences so the user can rebind instead of discovering a silent
# conflict later.
_keymap_conflicts = []


def _scan_keymap_conflicts(prefs):
    """Return a list of dicts describing other user keymap bindings that
    collide with our hotkey choice. Walks the user keyconfig (not the
    addon one) because that's where stock Blender + other addons
    register; the addon keyconfig is where we'll add ours a moment later."""
    conflicts = []
    try:
        kc_user = bpy.context.window_manager.keyconfigs.user
    except Exception:
        return conflicts
    if kc_user is None:
        return conflicts
    want_key   = prefs.hotkey_key
    want_ctrl  = bool(prefs.hotkey_ctrl)
    want_shift = bool(prefs.hotkey_shift)
    want_alt   = bool(prefs.hotkey_alt)
    for km in kc_user.keymaps:
        for kmi in km.keymap_items:
            try:
                if (kmi.type == want_key
                        and bool(kmi.ctrl)  == want_ctrl
                        and bool(kmi.shift) == want_shift
                        and bool(kmi.alt)   == want_alt
                        and kmi.value == 'PRESS'
                        and kmi.idname and not kmi.idname.startswith("blender_buddy.")):
                    conflicts.append({
                        "keymap":   km.name,
                        "operator": kmi.idname,
                    })
            except Exception:
                continue
    return conflicts


def _hotkey_label(prefs):
    parts = []
    if prefs.hotkey_ctrl:
        parts.append("Ctrl")
    if prefs.hotkey_shift:
        parts.append("Shift")
    if prefs.hotkey_alt:
        parts.append("Alt")
    parts.append(prefs.hotkey_key)
    return "+".join(parts)


def _register_keymap():
    """Bind the configured hotkey in the global Window keymap so it fires in
    any area / workspace. Must be called after prefs are loaded."""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc is None:
        return
    try:
        prefs = _prefs()
    except Exception as e:
        print(f"[Blender Buddy] keymap: prefs not ready: {e}")
        return

    # Detect collisions against the user keyconfig BEFORE we add our own
    # binding. Other addons / stock Blender may already claim this combo;
    # surface that in preferences instead of silently overriding.
    global _keymap_conflicts
    _keymap_conflicts = _scan_keymap_conflicts(prefs)
    if _keymap_conflicts:
        combo = _hotkey_label(prefs)
        first = _keymap_conflicts[0]
        print(f"[Blender Buddy] hotkey {combo} conflicts with "
              f"{first['operator']} in '{first['keymap']}' keymap "
              f"({len(_keymap_conflicts)} total). Rebind in Preferences.")

    km = kc.keymaps.new(name="Window", space_type='EMPTY')
    kmi = km.keymap_items.new(
        "blender_buddy.summon",
        type=prefs.hotkey_key,
        value='PRESS',
        ctrl=prefs.hotkey_ctrl,
        shift=prefs.hotkey_shift,
        alt=prefs.hotkey_alt,
    )
    _addon_keymaps.append((km, kmi))

    # Esc → clear conversation. Bound globally on the Window keymap; the
    # operator's poll restricts it to UI regions where the Buddy tab is
    # active. Custom-named per-space UI-region keymaps proved unreliable in
    # Blender's dispatcher, so we filter at poll time instead. Esc inside a
    # text edit is absorbed by Blender's edit modal before reaching us, and
    # poll-failure means Esc passes through to its normal handlers anywhere
    # else (cancel transform, close popup, etc.).
    kmi = km.keymap_items.new(
        "blender_buddy.esc_clear",
        type='ESC', value='PRESS',
    )
    _addon_keymaps.append((km, kmi))


def _unregister_keymap():
    for km, kmi in _addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _addon_keymaps.clear()


def _on_hotkey_change(self, context):
    """Fired when any hotkey pref changes — rebind so the new combo takes
    effect immediately, no reload needed."""
    _unregister_keymap()
    _register_keymap()
    _save_prefs(self, context)


# ---------------------------------------------------------------------------
# Icons — one static buddy.png for the panel header, plus a collection of
# animation sequences (folders of numbered PNGs). Each time a busy/loading
# cycle starts we pick a random animation folder and ping-pong through its
# frames for the duration of the cycle. Animation folders are
# auto-discovered at register time from blender_buddy_assets/animations/;
# the user can drop in folder 4, 5, 6, etc., and they'll be picked up on
# addon reload with no code change.
# ---------------------------------------------------------------------------

import random as _random

_BUDDY_STATIC_KEY = "buddy_static"
_BUDDY_FPS        = 3   # frames per second for the ping-pong playback

_icon_previews = None

# {folder_name: [ordered_icon_keys]} — populated by _register_icons().
_anim_sequences = {}

# Folder name currently being played. Cleared to None by _start_job so
# the next panel draw picks a fresh random sequence.
_current_anim_key = None


def _rotate_animation():
    """Invalidate the cached sequence so the next _animated_buddy_icon_id
    call re-rolls. Called from _start_job at the moment a busy/loading
    cycle begins. Trying to detect the transition from inside the icon
    getter doesn't work because the panel only calls the getter WHILE
    busy — so an idle→active flip is never observed there."""
    global _current_anim_key
    _current_anim_key = None


def _pingpong_indices(n):
    """Indices for a forward-then-reverse cycle over n frames, with
    endpoints held once. n=6 → (0,1,2,3,4,5,4,3,2,1); n=7 →
    (0,1,2,3,4,5,6,5,4,3,2,1). Period 2·(n-1)."""
    if n <= 1:
        return tuple(range(n))
    return tuple(list(range(n)) + list(range(n - 2, 0, -1)))


def _register_icons():
    """Load the static icon + every animation folder under
    blender_buddy_assets/animations/. Each PNG is registered as a
    Blender preview so we get an integer icon_id back for template_icon
    / layout.label(icon_value=…) rendering. Frame files are sorted
    numerically by filename stem so `10.png` comes after `9.png`."""
    global _icon_previews, _anim_sequences
    # Reload-safety: if a prior register() left a preview collection
    # alive (hot-reload without clean unregister), close it before
    # allocating a fresh one so we don't leak GPU texture memory.
    if _icon_previews is not None:
        try:
            bpy.utils.previews.remove(_icon_previews)
        except Exception as e:
            print(f"[Blender Buddy] icons: stale cleanup on re-register: {e}")
        _icon_previews = None
    _icon_previews = bpy.utils.previews.new()
    _anim_sequences = {}

    asset_dir = addon_assets_dir()

    static_path = os.path.join(asset_dir, "buddy.png")
    if os.path.isfile(static_path):
        try:
            p = _icon_previews.load(_BUDDY_STATIC_KEY, static_path, 'IMAGE')
            # Force eager GPU upload so the first draw isn't a grey box.
            _ = p.icon_id
        except Exception as e:
            print(f"[Blender Buddy] static icon load failed: {e}")

    anim_root = os.path.join(asset_dir, "animations")
    if os.path.isdir(anim_root):
        for folder_name in sorted(os.listdir(anim_root)):
            folder = os.path.join(anim_root, folder_name)
            if not os.path.isdir(folder):
                continue
            frames = []
            for fname in os.listdir(folder):
                if not fname.lower().endswith(".png"):
                    continue
                stem = os.path.splitext(fname)[0]
                try:
                    num = int(stem)
                except ValueError:
                    # Filenames that aren't pure numbers are ignored so
                    # stray thumbnails/sidecars don't end up in the
                    # sequence.
                    continue
                frames.append((num, fname))
            if not frames:
                continue
            frames.sort(key=lambda x: x[0])
            keys = []
            for num, fname in frames:
                icon_key = f"anim_{folder_name}_{num}"
                path = os.path.join(folder, fname)
                try:
                    p = _icon_previews.load(icon_key, path, 'IMAGE')
                    _ = p.icon_id
                    keys.append(icon_key)
                except Exception as e:
                    print(f"[Blender Buddy] frame load failed {path}: {e}")
            if keys:
                _anim_sequences[folder_name] = keys

    print(f"[Blender Buddy] icons registered — static: "
          f"{'yes' if os.path.isfile(static_path) else 'MISSING'}  "
          f"animations: {list(_anim_sequences.keys()) or '(none)'}")


def _unregister_icons():
    global _icon_previews, _anim_sequences
    if _icon_previews is not None:
        try:
            bpy.utils.previews.remove(_icon_previews)
        except Exception as e:
            print(f"[Blender Buddy] icons: remove failed: {e}")
        _icon_previews = None
    _anim_sequences = {}


def _buddy_static_icon_id():
    """The fixed buddy.png used in the panel header and as a fallback for
    the animated accessor when no sequences are registered."""
    if _icon_previews is None:
        return 0
    entry = _icon_previews.get(_BUDDY_STATIC_KEY)
    return entry.icon_id if entry is not None else 0


def _icon_id_for_key(key):
    if _icon_previews is None:
        return 0
    entry = _icon_previews.get(key)
    return entry.icon_id if entry is not None else 0


def _animated_buddy_icon_id():
    """Current frame of the active animation sequence. The sequence is
    chosen randomly at job start (_start_job → _rotate_animation) and
    stays fixed for the whole cycle. Falls back to the static icon when
    no animation is registered."""
    global _current_anim_key
    if _current_anim_key is None and _anim_sequences:
        _current_anim_key = _random.choice(list(_anim_sequences.keys()))

    if not _current_anim_key or _current_anim_key not in _anim_sequences:
        return _buddy_static_icon_id()
    keys = _anim_sequences[_current_anim_key]
    n = len(keys)
    if n == 0:
        return _buddy_static_icon_id()
    pp = _pingpong_indices(n)
    idx = int(time.time() * _BUDDY_FPS) % len(pp)
    icon_id = _icon_id_for_key(keys[pp[idx]])
    if icon_id:
        return icon_id
    # Mid-reload fallback: any loaded frame is better than the grey box.
    for k in keys:
        alt = _icon_id_for_key(k)
        if alt:
            return alt
    return _buddy_static_icon_id()


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

def _progress_display_text(state):
    """Format a running job's message for display in a panel.

    Stages that block without visible byte-counter progress (SHA-256
    hash verification of a multi-GB file, atomic rename) would otherwise
    appear frozen at '100%' for tens of seconds. We detect those stages
    by keyword and append animated dots + a 'this takes a moment' hint,
    so the user can see the addon is alive and just chewing through a
    post-download step."""
    msg = state.get("message") or state.get("label") or ""
    lm = msg.lower()
    if "checking" in lm or "verifying" in lm:
        dots = "." * (((int(time.time() * 3)) % 4) + 1)
        core = msg.rstrip("…. ")
        return f"{core}{dots}  (this takes a moment)"
    if "saving" in lm and "saved" not in lm:
        dots = "." * (((int(time.time() * 3)) % 4) + 1)
        core = msg.rstrip("…. ")
        return f"{core}{dots}"
    return msg


def _panel_char_width(context, fallback=38):
    """Estimate how many chars of plain text fit in a panel row. Uses the
    live region width so wrapping tracks the user's actual sidebar size.

    Blender's default font is variable-width, so we use a conservative
    px-per-char (8.8) and subtract a generous margin (40 px) for the panel
    padding + box inset. Better to wrap a little early than let labels
    overflow and get truncated with '…' on the right."""
    try:
        region = context.region
        if region and region.width > 0:
            ui_scale = getattr(context.preferences.view, "ui_scale", 1.0) or 1.0
            chars = (region.width - 40) / (8.8 * ui_scale)
            return max(18, min(100, int(chars)))
    except Exception:
        pass
    return fallback


# URLs are detected verbatim AND extracted from markdown links [text](url).
# Stops at whitespace and common closing chars so trailing prose punctuation
# doesn't get glued onto the URL.
_URL_RE       = re.compile(r'https?://[^\s\)\]\>"\']+')
_MD_LINK_URL_RE = re.compile(r'\[[^\]]+\]\(([^)\s]+)\)')


def _extract_urls(text):
    """Return unique URLs in order of first appearance, stripped of
    trailing prose punctuation."""
    seen = set()
    out  = []
    for url in list(_MD_LINK_URL_RE.findall(text)) + list(_URL_RE.findall(text)):
        while url and url[-1] in '.,;:':
            url = url[:-1]
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _truncate(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def _truncate_url(url, n=56):
    """Render a long URL as `host/…/last-segment` so the visible label
    keeps both the domain and what the page is about. Falls back to
    plain truncation when the URL isn't structured enough to short-form
    (e.g. missing path)."""
    if len(url) <= n:
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc
        path = parsed.path.rstrip("/")
        if not host:
            return _truncate(url, n)
        scheme = parsed.scheme or "https"
        last = path.rsplit("/", 1)[-1] if path else ""
        if last and len(last) > n - len(host) - 10:
            last = last[: max(1, n - len(host) - 10)] + "…"
        if path.count("/") > 1 and last:
            short = f"{host}/…/{last}"
        elif last:
            short = f"{host}/{last}"
        else:
            short = host
        if len(short) <= n:
            return short
        return _truncate(short, n)
    except Exception:
        return _truncate(url, n)


# Turn-collapse state. Keys are short content hashes so the same turn
# stays collapsed/expanded across redraws without bloating the
# conversation dicts. Cleared on addon reload (module state).
# Semantics: responses 15+ lines get a "Collapse" button, but they
# render fully until the user explicitly collapses them. The set
# tracks what the user has hidden.
_COLLAPSE_MIN_LINES = 15
_turn_collapsed = set()  # hashes of turns the user has explicitly collapsed


def _turn_hash(content):
    # 10 hex chars is enough to keep turns distinct within a session.
    import hashlib
    return hashlib.md5((content or "").encode("utf-8", "replace")).hexdigest()[:10]


def _draw_turn(layout, msg, width=40, markdown_cap=120):
    """Render one conversation turn (user OR assistant) into the layout.

    No headers — user messages get `alert=True` which tints the text
    red/orange (Blender's only built-in label tint), so they stand apart
    from the normal-coloured assistant text without any header label.
    """
    content = msg.get("content", "")
    if msg.get("role") == "user":
        content = _strip_scene_ctx_prefix(content)
        ubox = layout.box()
        ubox.alert = True
        col = ubox.column(align=True)
        col.scale_y = _PARA_SCALE_Y
        any_line = False
        for ln in content.splitlines():
            if not ln.strip():
                continue
            for chunk in _wrap_for_label(ln, width=width):
                col.label(text=chunk)
                any_line = True
        if not any_line:
            col.label(text=" ")
    else:
        # Scrub any leftover `<tool_call>…</tool_call>` markup — keeps
        # turns stored before the tool-loop fallback landed looking
        # clean, and guards against anything that still slips through.
        content = _strip_inline_tool_calls(content)
        if not content.strip():
            # Pre-v9.6.2 turns could land here as blank if the model's
            # final response was pure tool-call markup that got stripped
            # to nothing. Show a placeholder so the box doesn't render
            # as an empty rectangle with just the copy button.
            content = "_(empty response)_"
        bbox = layout.box()

        # Long-turn collapse: show the full response by default. When
        # it's 15+ lines tall, a control button at the TOP of the box
        # toggles between full-render and a 3-line peek.
        turn_key = _turn_hash(content)
        line_count = content.count("\n") + 1
        is_long = line_count >= _COLLAPSE_MIN_LINES
        is_collapsed = turn_key in _turn_collapsed
        if is_long:
            ctrl_row = bbox.row(align=True)
            if is_collapsed:
                op = ctrl_row.operator(
                    BB_OT_toggle_turn_collapse.bl_idname,
                    text=f"Show full response ({line_count} lines)",
                    icon='TRIA_DOWN',
                )
                op.turn_key = turn_key
                op.collapse = False
            else:
                op = ctrl_row.operator(
                    BB_OT_toggle_turn_collapse.bl_idname,
                    text="Collapse",
                    icon='TRIA_UP',
                )
                op.turn_key = turn_key
                op.collapse = True

        if is_long and is_collapsed:
            # Collapsed peek — just the first line + ellipsis.
            preview_lines = content.splitlines()[:1]
            preview = "\n".join(preview_lines).rstrip()
            if len(preview_lines) < line_count:
                preview += "\n…"
            _render_markdown(bbox, preview, width=width, max_lines=markdown_cap)
        else:
            _render_markdown(bbox, content, width=width, max_lines=markdown_cap)
        # Clickable link buttons — wm.url_open opens the URL in the OS
        # default browser. Capped to keep long answers from spawning
        # dozens of buttons.
        urls = _extract_urls(content)
        for url in urls[:6]:
            op = bbox.operator("wm.url_open",
                               text=_truncate_url(url, 56), icon='URL')
            op.url = url
        # Per-message Copy — icon only, left-aligned at the bottom of the
        # box so it's associated with this specific response. No label
        # text because the clipboard icon is universally recognizable.
        copy_row = bbox.row()
        copy_row.alignment = 'LEFT'
        op = copy_row.operator(
            "blender_buddy.copy_message", text="", icon='COPYDOWN',
        )
        op.content = content


def _custom_image_info(path):
    """Return a short user-facing line describing the image referenced
    by `path` — filename + WxH if we can read the header, just the
    filename otherwise. Empty string when the path doesn't resolve to
    an accessible whitelisted image."""
    if not path:
        return ""
    try:
        full = os.path.realpath(bpy.path.abspath(path))
    except Exception:
        return ""
    if not os.path.isfile(full):
        return ""
    if not full.lower().endswith(_CUSTOM_IMAGE_EXT_ALLOW):
        return ""
    name = os.path.basename(full)
    try:
        size_kb = os.path.getsize(full) / 1024
    except OSError:
        size_kb = 0
    dims = _read_image_dimensions(full)
    if dims:
        return f"{name} — {dims[0]}×{dims[1]} ({size_kb:.0f} KB)"
    return f"{name} ({size_kb:.0f} KB)"


def _read_image_dimensions(path):
    """Best-effort WxH read. PNG, JPEG, and WebP all expose dimensions
    near the start of the file — we skip a full library (no Pillow
    dependency) and just parse the header bytes. Returns (w, h) or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return None
    # PNG: IHDR starts at byte 16, W/H are the next two u32 big-endian.
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        import struct
        w, h = struct.unpack(">II", head[16:24])
        return (w, h)
    # JPEG: walk markers for SOF0/SOF2 (harder; use a tiny read loop).
    if head[:2] == b"\xff\xd8":
        try:
            with open(path, "rb") as f:
                f.read(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        break
                    seg_len_bytes = f.read(2)
                    if len(seg_len_bytes) < 2:
                        break
                    seg_len = int.from_bytes(seg_len_bytes, "big")
                    if marker[1] in (0xC0, 0xC1, 0xC2):
                        f.read(1)  # precision
                        h = int.from_bytes(f.read(2), "big")
                        w = int.from_bytes(f.read(2), "big")
                        return (w, h)
                    f.read(seg_len - 2)
        except Exception:
            return None
    # WebP: VP8/VP8L/VP8X variants — skip for now, just return None.
    return None


def _format_token_usage(history, context):
    """Return a subtle "~X / Yk" string estimating how much of the
    configured context window the current conversation has consumed. We
    use a crude chars/4 heuristic since tokenization is backend-specific
    and running the real tokenizer per-redraw would be wasteful. Close
    enough to warn the user before answers start getting truncated."""
    try:
        total_chars = sum(len(m.get("content") or "") for m in history)
    except Exception:
        total_chars = 0
    tokens = total_chars // 4
    try:
        prefs = _prefs(context)
        ctx_max = int(getattr(prefs, "context_size", DEFAULT_CONTEXT_SIZE) or DEFAULT_CONTEXT_SIZE)
    except Exception:
        ctx_max = DEFAULT_CONTEXT_SIZE
    def _fmt(n):
        if n >= 1000:
            return f"{n / 1000:.1f}k".replace(".0k", "k")
        return str(n)
    return f"~{_fmt(tokens)} / {_fmt(ctx_max)}"


def _draw_buddy_panel(layout, context):
    """Sidebar panel body. Input is fixed at the top of the panel and the
    conversation is rendered NEWEST-PAIR-FIRST below it, so the user never
    has to scroll to type or to read the most recent answer. Older history
    grows downward and can be scrolled to."""
    props = context.scene.blender_buddy_props
    state = _job_get()
    busy = state["active"] and state.get("label") == "Answering"
    loading = state["active"] and state.get("label") == "Loading model"
    running = server_is_running() and not loading
    ready_to_launch = text_model_ready() and (server_exe_path() is not None)
    history = _conv_get()
    width = _panel_char_width(context)

    # 1) Top row — three mutually-exclusive modes:
    #    a) server not yet running + model installed → big "Launch" button
    #       so the first ask doesn't stall for 20-30 s while the 14 GB
    #       model loads into RAM
    #    b) currently loading the model → animated spinner + status
    #    c) server running (or loading button pressed) → normal prompt
    #       row with image toggle + textbox
    if loading:
        lbox = layout.box()
        lrow = lbox.row(align=True)
        icon_id = _animated_buddy_icon_id()
        if icon_id:
            lrow.template_icon(icon_value=icon_id, scale=1.5)
        dots = "." * (((int(time.time() * 3)) % 4) + 1)
        msg = state.get("message") or "loading…"
        lrow.label(text=f"{msg}{dots}")
        lbox.label(text="First launch takes ~20-30 s.", icon='INFO')
    elif not running and ready_to_launch:
        lrow = layout.row()
        lrow.scale_y = 2.0
        lrow.operator(BB_OT_launch.bl_idname,
                      text="Load Buddy", icon='PLAY')
        layout.label(
            text="Loads the model into RAM (~20-30 s).",
            icon='INFO',
        )
    elif not running and not ready_to_launch:
        # First-run flow: one button that opens Preferences where the
        # user picks their own text-model variant. The N-panel doesn't
        # pre-select a quant — RAM-based "recommended" can overshoot
        # for users who want a smaller download, so don't push it here.
        fr = layout.box()
        fr.label(text="Welcome — let's get Buddy set up.")

        has_exe = server_exe_path() is not None
        any_text = any(text_model_ready(k) for k in TEXT_MODEL_ORDER)

        missing = []
        if not has_exe:
            missing.append("runner (~300 MB)")
        if not any_text:
            missing.append("text model")
        if missing:
            fr.label(text="Needs: " + " + ".join(missing), icon='INFO')

        brow = fr.row()
        brow.scale_y = 1.5
        brow.operator("blender_buddy.open_setup_prefs",
                      text="Open Preferences to Finish Setup",
                      icon='PREFERENCES')

        # Active-job progress line — a download kicked off from
        # Preferences keeps running if that window is closed, so keep
        # the progress + cancel visible on the N-panel.
        if state.get("active"):
            jrow = fr.row(align=True)
            jrow.label(text=_progress_display_text(state), icon='SORTTIME')
            jrow.operator("blender_buddy.cancel_download",
                          text="Cancel", icon='CANCEL')
    else:
        # Layout:
        #   [ LOGO ][ 🌐 Web    ][ > Action ]
        #   [      ][ ✨ Deep   ][ 📷 Vision ]
        #   [ prompt textbox …………………………………… ]
        # Wrapped in one align=True column so the top row and the
        # prompt row sit flush (no inter-row padding above the textbox).
        outer = layout.column(align=True)

        # Logo column takes 30 % of the row; toggle grid fills the rest.
        top = outer.split(factor=0.30, align=True)

        # Logo on the left.
        logo_id = _buddy_static_icon_id()
        logo_col = top.row()
        logo_col.alignment = 'CENTER'
        if logo_id:
            logo_col.template_icon(icon_value=logo_id, scale=3.5)

        # 2×2 toggle grid on the right. Busy-gate scoped to the toggles
        # (not the logo — the logo is display-only). Leading + trailing
        # separators vertically position the grid against the logo.
        grid = top.column(align=True)
        grid.enabled = not busy
        grid.separator(factor=1.22)
        # Row 1: Web (top-left) + Action (top-right)
        r1 = grid.row(align=True)
        r1.scale_y = 1.4
        cell = r1.row(align=True)
        try:
            prefs = _prefs(context)
            cell.prop(prefs, "allow_online_access", text="Web",
                      icon='INTERNET' if prefs.allow_online_access
                           else 'INTERNET_OFFLINE',
                      toggle=True)
        except Exception as e:
            print(f"[Blender Buddy] online toggle skipped: {e}")
        cell = r1.row(align=True)
        cell.prop(props, "action_mode", text="Action",
                  icon='CONSOLE', toggle=True)
        # Row 2: Deep (bottom-left) + Vision (bottom-right)
        r2 = grid.row(align=True)
        r2.scale_y = 1.4
        cell = r2.row(align=True)
        cell.prop(props, "add_context", text="Deep",
                  icon='EXPERIMENTAL', toggle=True)
        cell = r2.row(align=True)
        cell.enabled = vision_model_ready()
        cell.prop(props, "attach_image", text="Vision",
                  icon='CAMERA_STEREO', toggle=True)
        grid.separator(factor=0.40)

        # ---- Prompt textbox on the same align=True column, flush with
        # the top row so there's no margin above it. ----
        q_row = outer.row(align=True)
        q_row.enabled = not busy
        q_row.scale_y = 1.4
        q_row.prop(props, "question", text="")

        # 1b) Scope toggles shown only when Image is armed, so the panel
        #     stays clean the rest of the time. Three side-by-side buttons
        #     via prop_enum (clicking one sets the enum to that value; the
        #     current value is rendered "pressed"). CUSTOM mode reveals a
        #     file-path field underneath.
        if props.attach_image and vision_model_ready():
            scope_row = layout.row(align=True)
            scope_row.prop_enum(props, "screenshot_scope", 'AREA')
            scope_row.prop_enum(props, "screenshot_scope", 'WINDOW')
            scope_row.prop_enum(props, "screenshot_scope", 'CUSTOM')
            if props.screenshot_scope == 'CUSTOM':
                path_row = layout.row(align=True)
                path_row.prop(props, "custom_image_path", text="")
                # Confirmation line: does the path resolve to a real
                # image, and what are its dimensions? Helps catch typos
                # before firing the ask.
                info = _custom_image_info(props.custom_image_path)
                if info:
                    info_row = layout.row()
                    info_row.enabled = False
                    info_row.label(text=info, icon='IMAGE_DATA')

    # 2) Action row — Clear button on the left, a subtle token-usage
    #    estimate on the right so the user sees when they're approaching
    #    the context limit before answers get truncated.
    if history or busy:
        tail = layout.row(align=True)
        tail.operator(BB_OT_revert_last_message.bl_idname,
                      text="Revert", icon='LOOP_BACK')
        tail.operator(BB_OT_clear_conversation.bl_idname,
                      text="Clear (Esc)", icon='TRASH')
        tok_sub = tail.row()
        tok_sub.alignment = 'RIGHT'
        tok_sub.enabled = False   # visually greyed — informational only
        tok_sub.label(text=_format_token_usage(history, context))
        layout.separator()

    # 3) Conversation, newest pair first. Pairs are (user, assistant);
    #    the in-flight pair (if busy) is appended last so it ends up at
    #    the top after reversing.
    pairs = [
        (history[i], history[i + 1] if i + 1 < len(history) else None)
        for i in range(0, len(history), 2)
    ]
    if busy:
        pending_q = props.question.strip()
        partial   = state.get("partial") or ""
        pairs.append((
            {"role": "user", "content": pending_q} if pending_q else None,
            {"role": "assistant", "content": partial} if partial else None,
        ))

    for user_msg, asst_msg in reversed(pairs):
        # Within a pair, assistant (the answer) is drawn ABOVE the user's
        # question. Reading order is answer first — you see the content you
        # care about without scrolling past the question.
        if asst_msg:
            _draw_turn(layout, asst_msg, width=width)
        elif user_msg is not None and busy:
            # No partial yet — show the animated Buddy icon inline with
            # whatever status the worker most recently set (e.g.
            # "loading vision model…", "searching: blender 5.1 cycles",
            # "reading: docs.blender.org/…", "generating"). Falls back
            # to "thinking" before the worker emits anything.
            pbox = layout.box()
            hbox = pbox.row(align=True)
            icon_id = _animated_buddy_icon_id()
            if icon_id:
                hbox.template_icon(icon_value=icon_id, scale=1.2)
            status = (state.get("message") or "").strip() or "thinking"
            # Avoid dots when the status already ends in a punctuation
            # mark (ellipsis / colon already imply progress).
            dots = ("." * (((int(time.time() * 3)) % 4) + 1)
                    if status[-1:] not in ".…:)" else "")
            hbox.label(text=f"{status}{dots}")
        if user_msg:
            _draw_turn(layout, user_msg, width=width)


# Sidebar panels — same draw, one class per supported space type so the
# "Buddy" tab appears in every editor's N-panel.
_SIDEBAR_SPACES = (
    'VIEW_3D', 'IMAGE_EDITOR', 'NODE_EDITOR',
    'SEQUENCE_EDITOR', 'CLIP_EDITOR', 'TEXT_EDITOR',
    'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'NLA_EDITOR',
    'SPREADSHEET',
)


def _draw_buddy_header(layout, _context):
    """Left-side header — static Buddy icon rendered next to the panel's
    `bl_label` ("Blender Buddy"). Kept STATIC on purpose: an animating
    header would force a 3×/sec redraw that re-runs the full panel
    draw (markdown re-parse of the whole conversation, URL extraction,
    etc.), which measurably hurts viewport framerate. The animated
    icon still shows in the panel body during busy/loading where
    motion actually conveys something."""
    icon_id = _buddy_static_icon_id()
    if icon_id:
        layout.label(text="", icon_value=icon_id)


def _draw_buddy_header_preset(layout, _context):
    """Right-aligned Unload button — only visible when the server is
    running. Rendered with normal button emboss so it reads as
    clickable at a glance rather than looking like part of the header
    text."""
    if not server_is_running():
        return
    row = layout.row(align=True)
    row.alignment = 'RIGHT'
    row.operator("blender_buddy.unload_model", text="Unload", icon='X')


def _make_sidebar_panel_cls(space_type):
    idname = f"BB_PT_panel_{space_type.lower()}"
    return type(
        idname,
        (Panel,),
        {
            'bl_idname': idname,
            'bl_space_type': space_type,
            'bl_region_type': 'UI',
            'bl_category': "Buddy",
            'bl_label': "Blender Buddy",
            'draw_header':        lambda self, ctx: _draw_buddy_header(self.layout, ctx),
            'draw_header_preset': lambda self, ctx: _draw_buddy_header_preset(self.layout, ctx),
            'draw':               lambda self, ctx: _draw_buddy_panel(self.layout, ctx),
        },
    )


_SIDEBAR_PANEL_CLASSES = tuple(
    _make_sidebar_panel_cls(s) for s in _SIDEBAR_SPACES
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    BB_AP_prefs,
    BB_PG_props,
    BB_OT_install_server,
    BB_OT_download_text_variant,
    BB_OT_select_text_variant,
    BB_OT_download_vision_model,
    BB_OT_open_setup_prefs,
    BB_OT_cancel_download,
    BB_OT_open_log_folder,
    BB_OT_copy_server_log,
    BB_OT_toggle_turn_collapse,
    BB_OT_unload_model,
    BB_OT_start_server,
    BB_OT_stop_server,
    BB_OT_launch,
    BB_OT_ask,
    BB_OT_clear_conversation,
    BB_OT_revert_last_message,
    BB_OT_esc_clear,
    BB_OT_copy_answer,
    BB_OT_copy_message,
    BB_OT_copy_code_block,
    BB_OT_run_code_block,
    BB_OT_edit_system_prompt,
    BB_OT_reset_system_prompt,
    BB_OT_summon,
    BB_OT_dev_reload,
) + _SIDEBAR_PANEL_CLASSES


# v9.2: nothing to reset per session anymore — inference knobs are
# hardcoded module constants, and the only runtime settings
# (allow_online_access, hotkey) are meant to persist across reloads.


def _migrate_hotkey_default():
    """One-shot: if the hotkey is still the v8.1.0–v8.3.0 default of plain B,
    bump it to the new Ctrl+Shift+Q. Anything else the user customized stays."""
    try:
        p = _prefs()
    except Exception:
        return
    if (p.hotkey_key == 'B' and not p.hotkey_ctrl
            and not p.hotkey_shift and not p.hotkey_alt):
        p.hotkey_ctrl = True
        p.hotkey_shift = True
        p.hotkey_key = 'Q'


def _post_register():
    """Deferred init: prefs aren't fully loaded during register() itself, so
    one-shot migrations + legacy cleanup + keymap binding run from a timer."""
    _migrate_hotkey_default()
    _cleanup_legacy_text_block()
    _cleanup_legacy_models()
    _register_keymap()
    return None


class _StderrTee:
    """Forward writes to the real stderr AND store a rolling tail in our
    in-memory deque for the list_info_log tool. Idempotent — re-install
    during a script reload just swaps the orig pointer."""
    _marker = "__blender_buddy_stderr_tee__"
    def __init__(self, orig):
        self.orig = orig
        self._carry = ""
    def write(self, data):
        # C extensions occasionally write bytes to stderr; decode defensively
        # so a single bytes-write doesn't wedge the whole tee.
        if isinstance(data, (bytes, bytearray)):
            try:
                data = data.decode("utf-8", errors="replace")
            except Exception:
                data = ""
        try:
            self.orig.write(data)
        except Exception:
            pass
        if not data or not isinstance(data, str):
            return
        try:
            self._carry += data
            lines = self._carry.split("\n")
            self._carry = lines[-1]
            now = time.time()
            with _info_log_lock:
                for ln in lines[:-1]:
                    if ln.strip():
                        _info_log_buffer.append((now, ln.rstrip()))
                if len(_info_log_buffer) > _INFO_LOG_MAX:
                    del _info_log_buffer[:-_INFO_LOG_MAX]
        except Exception:
            # Never let a tee exception escape — that corrupts stderr for
            # the whole Blender process. Swallow and carry on.
            pass
    def flush(self):
        try:
            self.orig.flush()
        except Exception:
            pass


def _install_stderr_tee():
    """Wrap sys.stderr exactly once, regardless of hot-reload count. If a
    prior _StderrTee is already in place (from an earlier register() that
    didn't cleanly unregister), reuse it so we don't chain wrappers."""
    global _stderr_orig
    # If sys.stderr is already one of our tees, do nothing — chaining
    # wrappers leaks the original reference and risks nested-lock hangs.
    if isinstance(sys.stderr, _StderrTee) or getattr(sys.stderr, "_marker", None) == _StderrTee._marker:
        if _stderr_orig is None:
            _stderr_orig = getattr(sys.stderr, "orig", None)
        return
    if _stderr_orig is not None:
        return
    _stderr_orig = sys.stderr
    sys.stderr = _StderrTee(_stderr_orig)


def _uninstall_stderr_tee():
    """Restore sys.stderr to the original stream defensively. Handles the
    case where something else has wrapped our tee in the meantime by
    walking back to the first non-tee stream."""
    global _stderr_orig
    try:
        cur = sys.stderr
        # Walk any nested-tee chain back to the first real stream.
        seen = 0
        while isinstance(cur, _StderrTee) and seen < 10:
            cur = cur.orig
            seen += 1
        if _stderr_orig is not None:
            sys.stderr = _stderr_orig
        elif seen > 0:
            sys.stderr = cur
    except Exception:
        pass
    _stderr_orig = None


# ---------------------------------------------------------------------------
# AST identifier linter — after the tool loop returns, scan any code
# blocks in the assistant's response for bpy.ops / bpy.types / bpy.data
# paths that AREN'T in the RAG index. Append a short warning footer so
# the user sees which identifiers weren't verified. Cheap safety net —
# catches the "the model forgot to call search_api" case post-hoc.
# ---------------------------------------------------------------------------

import ast as _ast_mod

_CODE_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)\n```",
                            re.DOTALL | re.IGNORECASE)


def _extract_bpy_chains(code):
    """Return the set of canonical bpy identifiers actually used in the
    code. Only collects the patterns the RAG index has entries for:
      - `bpy.ops.<category>.<operator>` (exactly 4 parts)
      - `bpy.types.<TypeName>`          (exactly 3 parts)
    Any longer access (e.g. `bpy.ops.mesh.primitive_cube_add(radius=1)`,
    `bpy.types.Mesh.vertices.add()`) collapses down to these canonical
    forms because the suffix is a call / property chain that can't be
    verified against the index anyway. Shorter ones (`bpy.ops`, `bpy.
    ops.mesh`) are dropped — they're namespace containers with no
    index entry. This stops the old 'flagged a false positive on
    bpy.ops.mesh' behaviour."""
    out = set()
    try:
        tree = _ast_mod.parse(code)
    except (SyntaxError, ValueError):
        return out
    for node in _ast_mod.walk(tree):
        if not isinstance(node, _ast_mod.Attribute):
            continue
        chain = []
        cur = node
        while isinstance(cur, _ast_mod.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if not (isinstance(cur, _ast_mod.Name) and cur.id == 'bpy'):
            continue
        chain.reverse()
        # bpy.ops.<cat>.<op> — need at least the category and the op
        if len(chain) >= 3 and chain[0] == 'ops':
            out.add(f"bpy.ops.{chain[1]}.{chain[2]}")
        # bpy.types.<TypeName>
        elif len(chain) >= 2 and chain[0] == 'types':
            out.add(f"bpy.types.{chain[1]}")
    return out


def _lint_code_identifiers(content):
    """Parse every ```python fence in `content`, check each bpy.ops.* /
    bpy.types.* identifier against the loaded API index. Returns a list
    of unknown identifiers (ordered, deduped). Quiet when the index
    isn't available so we don't false-alarm on a fresh install."""
    if '```' not in content:
        return []
    if not _load_api_index():
        return []
    entries = _api_cache.get("entries", [])
    known = {e.get("path") for e in entries if e.get("path")}
    unknown = []
    seen = set()
    for fence in _CODE_FENCE_RE.finditer(content):
        for ref in _extract_bpy_chains(fence.group(1)):
            if ref in known or ref in seen:
                continue
            seen.add(ref)
            unknown.append(ref)
    return unknown


def _append_lint_warnings(content):
    """If the linter finds unknown bpy identifiers in code blocks, tack on
    a short warning footer. Leaves content untouched when everything's
    fine or when the index isn't built yet."""
    unknown = _lint_code_identifiers(content)
    if not unknown:
        return content
    footer = ("\n\n---\n⚠ _Identifiers not found in the API index — "
              "verify before running:_\n"
              + "\n".join(f"- `{u}`" for u in unknown[:12]))
    if len(unknown) > 12:
        footer += f"\n- _…and {len(unknown) - 12} more_"
    return content.rstrip() + footer


def _atexit_stop_server():
    """Interpreter-shutdown safety net. If Blender exits without calling
    unregister() (crash, Alt+F4 while Python is mid-work, etc.), make
    sure our subprocess doesn't outlive us. Best-effort: any exception
    at interpreter teardown is swallowed — printing to stderr from here
    isn't reliable and there's no UI left to notify."""
    try:
        if server_is_running():
            stop_server()
    except Exception:
        pass


def register():
    global _atexit_registered
    _register_icons()
    _install_stderr_tee()
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.blender_buddy_props = PointerProperty(type=BB_PG_props)

    bpy.app.timers.register(_post_register, first_interval=0.1)

    # atexit safety net so the server doesn't outlive a hard Blender
    # crash / Alt+F4. Registered once per interpreter session — hot
    # reloads won't pile up handlers.
    if not _atexit_registered:
        import atexit as _atexit
        _atexit.register(_atexit_stop_server)
        _atexit_registered = True

    try:
        mtime = os.path.getmtime(os.path.abspath(__file__))
    except OSError:
        mtime = 0
    print(f"[Blender Buddy] register() — version {ADDON_VERSION} — mtime {mtime:.0f}")


def unregister():
    _unregister_keymap()
    # Surface stop_server failures via print (stderr tee feeds them to
    # the Info log) instead of silently swallowing them. A crashed
    # subprocess here means the next register() gets to retry cleanly.
    try:
        msg = stop_server()
        if msg:
            print(f"[Blender Buddy] unregister: {msg}")
    except Exception as e:
        print(f"[Blender Buddy] unregister: stop_server failed: {e}")

    # Clean per-scene property instance data before removing the type
    # attribute. Without this, a user who disables the addon, saves
    # the .blend, then reopens it sees the CustomProperty lingering on
    # the Scene datablock with no registered owner.
    try:
        for scene in bpy.data.scenes:
            if "blender_buddy_props" in scene:
                try:
                    del scene["blender_buddy_props"]
                except Exception:
                    pass
    except Exception:
        pass
    if hasattr(bpy.types.Scene, "blender_buddy_props"):
        del bpy.types.Scene.blender_buddy_props
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception as e:
            print(f"[Blender Buddy] unregister: class {c.__name__}: {e}")
    _unregister_icons()
    _uninstall_stderr_tee()


if __name__ == "__main__":
    register()
