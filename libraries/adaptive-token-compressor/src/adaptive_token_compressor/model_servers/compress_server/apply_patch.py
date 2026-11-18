# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Apply the neighbor-protection patch to LLMLingua-2 (required by ``digit_neighbor_radius``).

Run once after installing extras:

    python -m adaptive_token_compressor.model_servers.compress_server.apply_patch

``--check`` exits 0 if already patched, 1 if not (no apply). Idempotent.
Same patch file is COPY'd by ``deployment/compress-server/Dockerfile``.
"""
from __future__ import annotations

import argparse
import subprocess  # nosec B404 - build-time helper; runs `patch` with a fixed list argv, no shell, no untrusted input
import sys
from pathlib import Path

# Marker only present in the patched copy.
_MARKER = "_digit_neighbor_radius"

_PATCH_FILE = Path(__file__).parent / "patches" / "0001-digit-neighbor-radius.patch"


def _llmlingua_dir() -> Path:
    try:
        import llmlingua
    except ImportError as e:
        raise SystemExit(
            "llmlingua is not installed. Install one of the compress-server extras first\n"
            "(from the adaptive-token-compressor repository root):\n"
            "  pip install --index-url https://download.pytorch.org/whl/cpu \\\n"
            "              --extra-index-url https://pypi.org/simple \\\n"
            "              \".[compress-server-pytorch-cpu]\"   # CPU (PyTorch)\n"
            "  pip install --index-url https://download.pytorch.org/whl/cpu \\\n"
            "              --extra-index-url https://pypi.org/simple \\\n"
            "              \".[compress-server-ov]\"            # OpenVINO\n"
            "  pip install --extra-index-url https://download.pytorch.org/whl/xpu \\\n"
            "              --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/ \\\n"
            "              \".[compress-server-pytorch-xpu]\"   # XPU (PyTorch)"
        ) from e
    return Path(llmlingua.__file__).parent


def is_patched() -> bool:
    src = _llmlingua_dir() / "prompt_compressor.py"
    return _MARKER in src.read_text(encoding="utf-8")


def apply() -> None:
    target_dir = _llmlingua_dir()
    if not _PATCH_FILE.exists():
        raise FileNotFoundError(
            f"Patch file missing from package: {_PATCH_FILE}. "
            "Reinstall adaptive-token-compressor."
        )
    result = subprocess.run(
        ["patch", "-p1", "-i", str(_PATCH_FILE)],
        cwd=target_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(
            f"patch failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
        )
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the neighbor-protection patch to LLMLingua-2 (required by digit_neighbor_radius)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if already patched, 1 if not. Does not apply.",
    )
    args = parser.parse_args()

    if args.check:
        return 0 if is_patched() else 1

    if is_patched():
        print("Neighbor-protection patch already applied, skipping.")
        return 0

    apply()
    print("Neighbor-protection patch applied successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
