# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: encoder/mux.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: multiplexes encoded data into a payload and send as a tcp data frame.
"""
from __future__ import annotations

from semantic_img_comp.utils.config import MuxStructConfig
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Tuple


@dataclass
class PayloadMultiplexer:
    """Build a binary encoder payload and keep per-bucket byte accounting.

    Validation is intentionally strict so protocol regressions fail close to the
    source instead of surfacing as opaque decode-time errors.
    """
    cfg: MuxStructConfig

    buf: bytearray = field(default_factory=bytearray)
    size_log: Dict[str, int] = field(
        default_factory=lambda: {"header": 0, "background": 0, "objects": 0, "metadata": 0}
    )

    # ---------- low-level helpers ----------
    def _add(self, chunk: bytes, *, bucket: str) -> None:
        self.buf.extend(chunk)
        self.size_log[bucket] += len(chunk)

    def _pack_add(self, fmt_code: str, *values: Any, bucket: str) -> None:
        # fmt_code is without endian (preferred) or already endian-prefixed
        fmt = self.cfg.fmt(fmt_code)
        self._add(struct.pack(fmt, *values), bucket=bucket)

    # ---------- validation helpers ----------
    @staticmethod
    def _require_bytes(value: Any, field_name: str) -> bytes:
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(f"{field_name} must be bytes-like, got {type(value).__name__}")
        return bytes(value)

    @staticmethod
    def _require_hw(size: Any, field_name: str) -> tuple[int, int]:
        if not isinstance(size, tuple) or len(size) != 2:
            raise ValueError(f"{field_name} must be a (width, height) tuple")

        w, h = size
        if not isinstance(w, int) or not isinstance(h, int):
            raise TypeError(f"{field_name} dimensions must be integers")
        if w <= 0 or h <= 0:
            raise ValueError(f"{field_name} dimensions must be > 0, got {(w, h)}")
        if w > 0xFFFF or h > 0xFFFF:
            raise ValueError(f"{field_name} dimensions exceed uint16 wire limit: {(w, h)}")
        return w, h

    @staticmethod
    def _require_bbox(bbox: Any, field_name: str) -> tuple[int, int, int, int]:
        if not isinstance(bbox, tuple) or len(bbox) != 4:
            raise ValueError(f"{field_name} must be a (x1, y1, x2, y2) tuple")
        x1, y1, x2, y2 = bbox
        vals = (x1, y1, x2, y2)
        if any(not isinstance(v, int) for v in vals):
            raise TypeError(f"{field_name} coordinates must be integers")
        if any(v < 0 or v > 0xFFFF for v in vals):
            raise ValueError(f"{field_name} coordinates must be within uint16 range")
        return x1, y1, x2, y2

    # ---------- fixed overhead / initialization ----------
    @classmethod
    def from_img_data(cls, img_data: Any, cfg: MuxStructConfig) -> "PayloadMultiplexer":
        """
        Initializes with per-payload fixed fields:
          - original image size
          - background length + bytes + background scaled size + bg encoder index
          - crops_count
        """
        self = cls(cfg=cfg)

        if img_data.bg is None:
            raise ValueError("img_data.bg must be populated before muxing")
        if img_data.crops is None:
            raise ValueError("img_data.crops must be a list (use [] when empty)")

        org_w, org_h = self._require_hw(img_data.org_img_size, "img_data.org_img_size")
        bg_bytes = self._require_bytes(img_data.bg.encoded_data, "img_data.bg.encoded_data")
        bg_w, bg_h = self._require_hw(img_data.bg.scaled_size, "img_data.bg.scaled_size")

        # 1) Original image size is stored as (width, height) to match PIL.
        # Use cfg.fmt_hw so you can change to "2I" etc later.
        self._pack_add(cfg.fmt_hw, org_w, org_h, bucket="metadata")

        # 2) Background
        self._pack_add(cfg.fmt_len_bg, len(bg_bytes), bucket="background")
        self._add(bg_bytes, bucket="background")

        self._pack_add(cfg.fmt_hw, bg_w, bg_h, bucket="background")

        self._pack_add(cfg.fmt_encoder_index, img_data.bg.encoder_index, bucket="background")

        # 3) Crops count
        self._pack_add(cfg.fmt_crops_count, len(img_data.crops), bucket="metadata")

        return self

    # ---------- incremental muxing ----------
    def mux_crop(self, crop: Any) -> None:
        cfg = self.cfg
        encoded_obj = self._require_bytes(crop.encoded_obj, "crop.encoded_obj")
        expanded_bbox = self._require_bbox(crop.expanded_bbox, "crop.expanded_bbox")
        ow, oh = self._require_hw(crop.obj_size_scaled, "crop.obj_size_scaled")

        encoder_index = crop.encoder_index
        if not isinstance(encoder_index, int) or not (0 <= encoder_index <= 0xFF):
            raise ValueError(f"crop.encoder_index must be uint8-compatible, got {encoder_index}")

        # 3.a) Encoded object length
        self._pack_add(cfg.fmt_len_obj, len(encoded_obj), bucket="metadata")

        # 3.b) Encoded object bytes
        self._add(encoded_obj, bucket="objects")

        # 3.c) Expanded BBox
        self._pack_add(cfg.fmt_bbox, *expanded_bbox, bucket="metadata")

        # 3.d) Object size after down-scaling
        self._pack_add(cfg.fmt_hw, ow, oh, bucket="metadata")

        # 3.e) Encoder index
        self._pack_add(cfg.fmt_encoder_index, encoder_index, bucket="metadata")

    def mux_crops(self, crops: Iterable[Any]) -> None:
        for crop in crops:
            self.mux_crop(crop)

    def finalize(self) -> Tuple[bytes, Dict[str, int]]:
        return bytes(self.buf), dict(self.size_log)
