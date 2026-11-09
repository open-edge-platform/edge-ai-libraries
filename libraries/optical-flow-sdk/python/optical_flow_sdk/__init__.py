# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Intel Optical Flow SDK."""

try:
    from ._native import (  # noqa: F401
        Backend,
        OpticalFlow,
        Preset,
        available_backends,
        backend_name,
        preset_name,
        resolve_backend,
    )
except ImportError as exc:  # pragma: no cover - packaging help text
    raise ImportError(
        "optical_flow_sdk native module is missing. Build with "
        "-DOPTICALFLOW_BUILD_PYTHON=ON and place _native next to this package."
    ) from exc

__all__ = [
    "Backend",
    "OpticalFlow",
    "Preset",
    "available_backends",
    "backend_name",
    "preset_name",
    "resolve_backend",
]
