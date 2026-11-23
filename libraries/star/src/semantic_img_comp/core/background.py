# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from PIL import Image
from typing import Optional


@dataclass
class BgData:
    """Data model for background image state across encode/decode pipeline stages.

    Typical lifecycle:
    - encoder input: `pil` holds the source background image.
    - post-encode: `encoded_data`, `scaled_size`, `encoder_index`, and
      `scaling_factor` are populated.
    - decoder output: `recon_pil` holds the reconstructed background image.

    Field notes:
    - `scaled_size` is `(width, height)` in pixels.
    - `scaling_factor` is the selected downscale percentage (for example, 65).
    - `encoder_index` maps to the encoder tag index configured in
      `cfg.img_process.encoders_tag_bg`.
    """
    pil: Image.Image = None
    encoded_data: Optional[bytes] = None
    scaled_size: Optional[tuple[int, int]] = None
    encoder_index: Optional[int] = None
    scaling_factor: Optional[int] = None
    recon_pil: Optional[Image.Image] = None