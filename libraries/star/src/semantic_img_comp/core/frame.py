# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass

from semantic_img_comp.core.background import BgData
from semantic_img_comp.core.object import ObjData


@dataclass
class ImgEncData:
    """Data model for an image frame while it is being prepared by the encoder.

    Field notes:
    - `img_idx` is the sender-side frame/image identifier used by the encoder pipeline.
    - `org_jpeg_bytes` is the source JPEG size in bytes used for budgeting.
    - `org_img_size` is `(width, height)` in pixels.
    - `encoded_data` can hold a full encoded payload when used by callers.
    - `crops` and `bg` store encoded object/background state for muxing.
    """
    img_idx: int
    org_jpeg_bytes: int
    org_img_size: tuple[int, int] | None = None
    encoded_data: bytes | None = None
    crops: list[ObjData] | None = None
    bg: BgData | None = None


@dataclass
class ImgDecData:
    """Data model for a frame reconstructed by the decoder.

    Field notes:
    - `img_idx` is assigned by receiver order (1-based) when the frame is consumed.
    - `org_img_size` is `(width, height)` extracted from payload metadata.
    - `bg` contains decoded background state and `crops` holds decoded objects.
    """
    img_idx: int = None
    org_img_size: tuple[int, int] | None = None
    crops: list[ObjData] | None = None
    bg: BgData | None = None
