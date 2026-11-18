# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: decoder/demux.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: demultiplexing received data stream.
"""

import struct
import socket

from semantic_img_comp.core.background import BgData
from semantic_img_comp.core.object import ObjData
from semantic_img_comp.core.frame import ImgDecData
from semantic_img_comp.utils.config import MuxStructConfig


def demux_frame(
    payload: bytes,
    cfg: MuxStructConfig,
    *,
    img_idx: int | None = None,
    max_crops: int | None = None,
):
    """Decode one payload into ``ImgDecData`` using the mux wire layout.

    Image sizes are interpreted as ``(width, height)``.

    :param max_crops: reject payloads declaring more than this many crops
        (defaults to ``cfg.default_max_crops``); callers should pass the
        configured ``model.max_detections`` when available.
    """
    crop_cap = cfg.default_max_crops if max_crops is None else max_crops
    bg = BgData()
    img_dec_data = ImgDecData()

    fmt_hw = cfg.fmt(cfg.fmt_hw)
    fmt_len_bg = cfg.fmt(cfg.fmt_len_bg)
    fmt_encoder_index = cfg.fmt(cfg.fmt_encoder_index)
    fmt_crops_count = cfg.fmt(cfg.fmt_crops_count)
    fmt_len_obj = cfg.fmt(cfg.fmt_len_obj)
    fmt_bbox = cfg.fmt(cfg.fmt_bbox)

    sz_hw = struct.calcsize(fmt_hw)
    sz_len_bg = struct.calcsize(fmt_len_bg)
    sz_encoder_index = struct.calcsize(fmt_encoder_index)
    sz_crops_count = struct.calcsize(fmt_crops_count)
    sz_len_obj = struct.calcsize(fmt_len_obj)
    sz_bbox = struct.calcsize(fmt_bbox)

    offset = 0
    img_dec_data.img_idx = img_idx
    try:

        org_w, org_h = struct.unpack_from(fmt_hw, payload, offset)
        img_dec_data.org_img_size = (org_w, org_h)
        offset += sz_hw

        full_len = struct.unpack_from(fmt_len_bg, payload, offset)[0]
        offset += sz_len_bg
        bg.encoded_data = payload[offset:offset + full_len]
        offset += full_len

        bg_w, bg_h = struct.unpack_from(fmt_hw, payload, offset)
        offset += sz_hw
        bg.scaled_size = (bg_w, bg_h)

        bg.encoder_index = struct.unpack_from(fmt_encoder_index, payload, offset)[0]
        offset += sz_encoder_index

        num_crops = struct.unpack_from(fmt_crops_count, payload, offset)[0]
        offset += sz_crops_count

        if num_crops > crop_cap:
            raise ValueError(f"num_crops {num_crops} exceeds max_detections {crop_cap}")

        crops = []

        for _ in range(num_crops):
            crop = ObjData()
            crop_len = struct.unpack_from(fmt_len_obj, payload, offset)[0]
            offset += sz_len_obj
            crop.decoded_obj = payload[offset:offset + crop_len]
            offset += crop_len

            crop.expanded_bbox = struct.unpack_from(fmt_bbox, payload, offset)
            offset += sz_bbox


            w, h = struct.unpack_from(fmt_hw, payload, offset)
            crop.obj_size_scaled = (w, h)
            offset += sz_hw

            crop.encoder_index = struct.unpack_from(fmt_encoder_index, payload, offset)[0]
            offset += sz_encoder_index

            crops.append(crop)
    except struct.error as exc:
        raise ValueError(f"Malformed payload while demuxing at byte offset {offset}") from exc

    if offset != len(payload):
        raise ValueError(f"Malformed payload: trailing bytes detected at byte offset {offset}")

    img_dec_data.bg = bg
    img_dec_data.crops = crops

    return img_dec_data


def recv_frame(sock: socket.socket, cfg: MuxStructConfig):
    # ---- read header ----
    fmt_payload_len = cfg.fmt(cfg.fmt_payload_len)
    header_size = struct.calcsize(fmt_payload_len)
    header = recv_exact(sock, header_size)

    # connection closed cleanly (normal termination)
    if header is None:
        return None

    frame_len = struct.unpack(fmt_payload_len, header)[0]

    # optional safety check (VERY useful)
    if frame_len == 0:
        # explicit end-of-stream marker (if you decide to use it later)
        return None

    if frame_len > cfg.max_frame_len:
        raise ValueError(f"frame_len {frame_len} exceeds max_frame_len {cfg.max_frame_len}")

    # ---- read payload ----
    payload = recv_exact(sock, frame_len)

    # connection died mid-frame
    if payload is None:
        return None

    return payload


def recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """
    Receive exactly n bytes from the socket.

    Returns:
        bytes: the received data
        None: peer closed the connection (EOF)
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    if n == 0:
        return b""

    # Fast path for real sockets: fill a preallocated buffer to avoid O(n^2) concatenation.
    if hasattr(sock, "recv_into"):
        buf = bytearray(n)
        view = memoryview(buf)
        received = 0
        while received < n:
            num_read = sock.recv_into(view[received:], n - received)
            if num_read == 0:
                return None
            received += num_read
        return bytes(buf)

    # Fallback for socket-like test doubles that only implement recv().
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if chunk == b"":
            return None
        buf.extend(chunk)

    return bytes(buf)
