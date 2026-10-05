# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""HTTP clients for VSS backend services."""

from .vss import (
    VssClient,
    VssError,
    encode_image_file,
    is_image_reference,
    resolve_image_input,
)

__all__ = [
    "VssClient",
    "VssError",
    "encode_image_file",
    "is_image_reference",
    "resolve_image_input",
]
