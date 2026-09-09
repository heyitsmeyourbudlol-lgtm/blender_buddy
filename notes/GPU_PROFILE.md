# GPU profile meters (gpu_profiler)

_Profile-once per code change — do not re-profile without a diff in GPU/compute / CLEAN FP4 scope._

**Canonical tool:** `python3 scripts/gpu_profile_once.py`  
(`--json` · `--force` only after intentional re-measure)  
Meters: `~/.config/<ns>/gpu-profile-meters.jsonl` · state: `gpu-profile-once-state.json`  
Needle: `OVERSEER_GPU_PROFILE_ONCE_2026_09_05`

Scope fingerprint covers: `gpu_profile_once.py`, `bitnet_fp4_expert_rss_smoke.py`, `dgx_gpu_events.py`.

## 2026-09-06T03:07:35Z — profile-once (peer-77 / gpu_profiler_L2)

| Meter | Value | Notes |
|-------|------:|-------|
| Host GPU | NVIDIA GB10 | `dgx_gpu_events.gpu_snapshot` |
| `gpu_util_pct` | **0.0%** | Idle |
| power / temp | 15.32 W / 64 °C | Cool, low draw |
| `gpu_mem_mib` | 0 | SMI memory N/A-ish on this sample |
| Transformer Engine / TE FP4 | **NO** | `ModuleNotFoundError: transformer_engine` |
| CLEAN FP4 `prompt_tok_s` | ~2.88e6 | mmap/CPU accounting smoke (not GEMM) |
| CLEAN FP4 `accepted_writing_tok_s` | ~2.58e6 | Separated from prompt (C13) |
| `gds_forbidden_ok` | true | No nvidia-fs / cuFile |
| skip gate | OK | second run → `skipped_no_code_change` |

### Bottlenecks (this sample)

1. **Idle raw util** — `gpu_util_near_idle`; do not treat CLEAN FP4 tok/s as GB10 TE load.
2. **TE FP4 unavailable** — use CLEAN FP4 mmap smoke as accounting stand-in; NVFP4 train/serve still blocked on TE install (`notes/NVFP4_LOCK_APPLICABILITY.md`).
3. **No endless re-profile** — fingerprint skip holds until scope scripts change.

### Re-profile gate

```bash
python3 scripts/gpu_profile_once.py --json          # skip if unchanged
python3 scripts/gpu_profile_once.py --json --force  # after code change only
python3 -m unittest tests.test_gpu_profile_once -q
```
