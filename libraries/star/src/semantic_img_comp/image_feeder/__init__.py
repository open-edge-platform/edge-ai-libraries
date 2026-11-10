# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: image_feeder/__init__.py
Description: package exposing the rate-limited image feeder used by the TCP batch encoder.
"""
from semantic_img_comp.image_feeder.feeder import (
    FEEDER_DONE,
    ImageFeederHandle,
    feed_images,
    start_image_feeder,
)

__all__ = [
    "FEEDER_DONE",
    "ImageFeederHandle",
    "feed_images",
    "start_image_feeder",
]
