#!/usr/bin/env bash
# Pull the default sub-1GB Mamba reranker for knowledge index.
set -euo pipefail

MODEL="${KNOWLEDGE_MAMBA_MODEL:-state-spaces/mamba-130m-hf}"
CACHE="${HF_HOME:-$HOME/.cache/huggingface}"

echo "== knowledge mamba setup =="
echo "model: $MODEL"
echo "budget: 2048MB RAM (cascade — one tier at a time)"
echo "cache: $CACHE"

python3 - <<'PY'
import os
import sys

model_id = os.environ.get("KNOWLEDGE_MAMBA_MODEL", "state-spaces/mamba-130m-hf")
try:
    import torch
    from transformers import AutoModel, AutoTokenizer
except ImportError as exc:
    print(f"install deps first: pip install torch transformers", file=sys.stderr)
    raise SystemExit(1) from exc

print(f"downloading {model_id} ...")
tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
mdl = AutoModel.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
    trust_remote_code=True,
)
mdl.eval()
print(f"ok — {model_id} ready (fp16, unload after idle)")
PY

echo ""
echo "Verify: python3 scripts/knowledge_mamba.py --status"
