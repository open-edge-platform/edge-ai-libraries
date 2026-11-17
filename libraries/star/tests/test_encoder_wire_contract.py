# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from semantic_img_comp.decoder.demux import demux_frame
from semantic_img_comp.encoder.mux import PayloadMultiplexer
from semantic_img_comp.utils.config import MuxStructConfig


def _sample_img_data():
    bg = SimpleNamespace(
        encoded_data=b"background-bytes",
        scaled_size=(13, 7),
        encoder_index=9,
    )
    crops = [
        SimpleNamespace(
            encoded_obj=b"obj-a",
            bbox=(1, 2, 8, 6),
            expanded_bbox=(0, 1, 9, 7),
            category_id=5,
            det_conf=0.625,
            obj_size_scaled=(9, 7),
            encoder_index=2,
        ),
        SimpleNamespace(
            encoded_obj=b"obj-b-larger",
            bbox=(10, 4, 20, 15),
            expanded_bbox=(9, 3, 22, 17),
            category_id=42,
            det_conf=0.125,
            obj_size_scaled=(13, 14),
            encoder_index=3,
        ),
    ]
    return SimpleNamespace(
        img_idx=123,
        org_img_size=(21, 11),
        bg=bg,
        crops=crops,
    )


def test_mux_demux_roundtrip_preserves_frame_metadata_ordering():
    cfg = MuxStructConfig()
    img_data = _sample_img_data()

    mux = PayloadMultiplexer.from_img_data(img_data, cfg)
    mux.mux_crops(img_data.crops)
    payload, size_log = mux.finalize()

    decoded = demux_frame(payload, cfg, img_idx=1)

    assert decoded.img_idx == 1
    assert decoded.org_img_size == img_data.org_img_size
    assert decoded.bg.scaled_size == img_data.bg.scaled_size
    assert decoded.bg.encoder_index == img_data.bg.encoder_index
    assert decoded.bg.encoded_data == img_data.bg.encoded_data
    assert cfg.header_fields_total_bytes() == (14, 17)

    assert len(decoded.crops) == len(img_data.crops)
    for got, exp in zip(decoded.crops, img_data.crops):
        assert got.bbox is None          # bbox no longer sent on wire
        assert got.expanded_bbox == exp.expanded_bbox
        assert got.category_id is None
        assert got.det_conf is None
        assert got.obj_size_scaled == exp.obj_size_scaled
        assert got.encoder_index == exp.encoder_index
        assert got.decoded_obj == exp.encoded_obj

    # Margin is now config-driven at decode/reconstruction time, not transmitted per crop.
    assert decoded.crops[0].margin_pixel is None
    assert decoded.crops[1].margin_pixel is None

    assert size_log == {"header": 0, "background": 25, "objects": 17, "metadata": 39}
    assert sum(size_log.values()) == len(payload)


def test_mux_demux_roundtrip_with_zero_crops():
    cfg = MuxStructConfig()
    img_data = _sample_img_data()
    img_data.crops = []

    mux = PayloadMultiplexer.from_img_data(img_data, cfg)
    payload, _ = mux.finalize()

    decoded = demux_frame(payload, cfg)

    assert decoded.org_img_size == img_data.org_img_size
    assert decoded.img_idx is None
    assert decoded.crops == []

