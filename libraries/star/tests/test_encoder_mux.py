# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from semantic_img_comp.encoder.mux import PayloadMultiplexer
from semantic_img_comp.utils.config import MuxStructConfig


def _make_img_data():
    bg = SimpleNamespace(
        encoded_data=b"bg",
        scaled_size=(8, 6),
        encoder_index=1,
    )
    crop = SimpleNamespace(
        encoded_obj=b"obj",
        bbox=(0, 0, 4, 4),
        expanded_bbox=(0, 0, 5, 5),
        category_id=3,
        det_conf=0.9,
        obj_size_scaled=(5, 5),
        encoder_index=2,
    )
    return SimpleNamespace(
        img_idx=7,
        org_img_size=(10, 10),
        bg=bg,
        crops=[crop],
    )


def test_payload_multiplexer_roundtrip_builds_payload_and_size_log():
    cfg = MuxStructConfig()
    img_data = _make_img_data()

    mux = PayloadMultiplexer.from_img_data(img_data, cfg)
    mux.mux_crops(img_data.crops)
    payload, size_log = mux.finalize()

    assert isinstance(payload, bytes)
    assert len(payload) > 0
    assert set(size_log.keys()) == {"header", "background", "objects", "metadata"}
    assert cfg.header_fields_total_bytes() == (14, 17)
    assert size_log == {"header": 0, "background": 11, "objects": 3, "metadata": 22}
    assert sum(size_log.values()) == len(payload)


def test_payload_multiplexer_requires_org_size_tuple():
    cfg = MuxStructConfig()
    img_data = _make_img_data()
    img_data.org_img_size = None

    with pytest.raises(ValueError, match="org_img_size"):
        PayloadMultiplexer.from_img_data(img_data, cfg)


def test_payload_multiplexer_requires_crop_encoded_bytes():
    cfg = MuxStructConfig()
    img_data = _make_img_data()
    img_data.crops[0].encoded_obj = None

    mux = PayloadMultiplexer.from_img_data(img_data, cfg)
    with pytest.raises(TypeError, match="crop.encoded_obj"):
        mux.mux_crop(img_data.crops[0])


def test_payload_multiplexer_rejects_out_of_range_dimensions():
    cfg = MuxStructConfig()
    img_data = _make_img_data()
    img_data.bg.scaled_size = (70000, 1)

    with pytest.raises(ValueError, match="uint16"):
        PayloadMultiplexer.from_img_data(img_data, cfg)

