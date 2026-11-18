# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Optional
from PIL import Image


@dataclass
class ObjData:
    """Data model for object-crop state across encode/decode pipeline stages.

    Field notes:
    - `bbox` and `expanded_bbox` are `(x1, y1, x2, y2)` pixel coordinates.
    - `obj_size` and `obj_size_scaled` are `(width, height)` in pixels.
    - `scaling_factor` is the selected downscale percentage (for example, 65).
    - `encoder_index` maps to the encoder tag index configured in
      `cfg.img_process.encoders_tag_objs`.
    - `encoded_obj` is the compressed crop bytes (encoder side), while
      `decoded_obj` is the decoded crop payload bytes (decoder side).
    """
    obj_pil: Optional[Image.Image] = None
    encoded_obj: Optional[bytes] = None
    obj_size: Optional[tuple[int, int]] = None
    bbox: Optional[tuple[int, int, int, int]] = None
    expanded_bbox: Optional[tuple[int, int, int, int]] = None
    margin_pixel: Optional[int] = None
    category_id: Optional[int] = None
    det_conf: Optional[float] = None
    scaling_factor: Optional[int] = None
    obj_size_scaled: Optional[tuple[int, int]] = None
    encoder_index: Optional[int] = None
    decoded_obj: Optional[bytes] = None
    recon_pil: Optional[Image.Image] = None
