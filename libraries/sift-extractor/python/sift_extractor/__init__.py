# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Intel SIFT extractor (OpenCL / SYCL) Python bindings.

This pip package installs only the Python extension. It does **not** install
the GPU driver or compute runtime.

System requirements (install separately for your OS / Intel GPU host):
  - Intel GPU driver with compute support
  - OpenCL ICD loader (`libOpenCL.so.1`) for the OpenCL backend
  - Intel oneAPI / Level Zero + SYCL runtime for the SYCL backend
    (e.g. source ``/opt/intel/oneapi/setvars.sh``, or equivalent packages)

Install pattern::

    # 1) GPU stack for your machine (driver + OpenCL / oneAPI) — not via pip
    # 2) pip install sift-extractor-*.whl

If ``import sift_extractor`` fails with a missing shared library, the stack is
incomplete — that is not a pip packaging defect.
"""

from __future__ import annotations

_STACK_HELP = (
    "Failed to load the sift_extractor native extension. "
    "This wheel does not ship the GPU stack. Ensure you have: "
    "(1) an Intel GPU driver, "
    "(2) OpenCL ICD (libOpenCL.so.1) for OpenCL, "
    "(3) Intel oneAPI/SYCL + Level Zero runtimes on the loader path for SYCL "
    "(often: source /opt/intel/oneapi/setvars.sh). "
    "See the package README 'System requirements' section."
)

try:
    from sift_extractor._native import (  # noqa: F401
        Backend,
        Extractor,
        __version__,
        available_backends,
        has_opencl_matcher,
        match,
        resolve_backend,
    )
except ImportError as exc:  # pragma: no cover - depends on host stack
    raise ImportError(_STACK_HELP) from exc

try:
    from sift_extractor._native import OpenCLMatcher  # noqa: F401
except ImportError:  # OpenCL matcher not built into this wheel
    OpenCLMatcher = None  # type: ignore[misc, assignment]

__all__ = [
    "Backend",
    "Extractor",
    "OpenCLMatcher",
    "__version__",
    "available_backends",
    "has_opencl_matcher",
    "match",
    "resolve_backend",
    "system_requirements",
]


def system_requirements() -> str:
    """Return the human-readable GPU stack requirements (not installed by pip)."""
    return (
        "Intel GPU driver; OpenCL ICD (libOpenCL.so.1); "
        "optional for SYCL: Intel oneAPI Level Zero + SYCL runtime "
        "(e.g. source /opt/intel/oneapi/setvars.sh)."
    )
