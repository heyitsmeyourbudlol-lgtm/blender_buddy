"""Guards: GPU worker releases CUDA between forever cycles."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_gpu_worker as cgw  # noqa: E402


class GpuWorkerReleaseTests(unittest.TestCase):
    def test_release_cuda_no_raise_without_torch(self) -> None:
        with mock.patch.dict(sys.modules, {"torch": None}):
            # import torch raises ModuleNotFoundError-like TypeError path → soft pass
            cgw.release_cuda()

    def test_release_cuda_empty_cache_when_cuda_ok(self) -> None:
        torch = mock.MagicMock()
        torch.cuda.is_available.return_value = True
        with mock.patch.dict(sys.modules, {"torch": torch}):
            cgw.release_cuda()
        torch.cuda.synchronize.assert_called()
        torch.cuda.empty_cache.assert_called()


if __name__ == "__main__":
    unittest.main()
