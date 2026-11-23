# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""HTTP clients for VSS backend services."""

from .vss import (
    VssClient,
    VssError,
    is_image_reference,
)

__all__ = [
    "VssClient",
    "VssError",
    "is_image_reference",
]
