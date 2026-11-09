# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Tests for compression level feature in pipeline manager.
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pathlib import Path
from semantic_img_comp.encoder.pipeline_manager import (
    EncoderPipelineManager,
    PipelineContext,
)
from semantic_img_comp.utils.config import load_config


def _make_mock_cfg():
    """Create a mock config object for testing."""
    return SimpleNamespace(
        model=SimpleNamespace(
            tile_size=320,
            tile_overlap=5,
        ),
        enc=SimpleNamespace(
            compression_rate=100.0,
            max_iter_bg=5,
            max_iter_obj=10,
            compression_levels=SimpleNamespace(
                level_1=10.0,
                level_2=100.0,
            ),
        ),
        img_process=SimpleNamespace(
            encoders_tag_bg_level_1={"mono-2bit": 5},
            encoders_tag_objs_level_1={"mono-2bit": 5, "airplane-symbol-v1": 10},
            encoders_tag_bg_level_2={"mono-avif-mid": 2, "mono-2bit": 5},
            encoders_tag_objs_level_2={"mono-avif-mid": 2, "mono-mask-1bit": 6},
            active_encoders_tag_bg=None,
            active_encoders_tag_objs=None,
        ),
        pipeline_manager=SimpleNamespace(
            adaptive_compression_rate_warmup_frames=10,
            adaptive_compression_rate_max=300.0,
            adaptive_compression_rate_boost_factor=1.5,
            adaptive_compression_rate_method="moving_average",
            adaptive_compression_rate_target_margin_ratio=0.2,
            adaptive_compression_rate_ema_alpha=0.2,
            large_dim_tile_threshold_px=1280,
        ),
    )


def test_pipeline_context_with_compression_level():
    """Test PipelineContext with compression_level field."""
    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=2,
    )
    assert ctx.compression_level == 2


def test_decide_pipeline_accepts_compression_level():
    """Test that decide_pipeline accepts and returns compression_level."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        compression_level=2,
    )

    assert ctx.compression_level == 2


def test_get_compression_rate_for_level_1():
    """Test retrieving compression rate for level 1."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    rate = mgr._get_compression_rate_for_level(1)
    assert rate == 10.0


def test_get_compression_rate_for_level_2():
    """Test retrieving compression rate for level 2."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    rate = mgr._get_compression_rate_for_level(2)
    assert rate == 100.0


def test_apply_pipeline_config_sets_compression_rate_for_level():
    """Test that apply_pipeline_config sets compression rate based on level."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=1,
    )
    mgr.apply_pipeline_config(ctx)

    assert cfg.enc.compression_rate == 10.0


def test_apply_pipeline_config_sets_compression_rate_for_level_2():
    """Test that apply_pipeline_config sets compression rate for level 2."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=2,
    )
    mgr.apply_pipeline_config(ctx)

    assert cfg.enc.compression_rate == 100.0


def test_apply_pipeline_config_sets_encoder_tags_for_level_1():
    """Test that apply_pipeline_config sets encoder tags for level 1."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=1,
    )
    mgr.apply_pipeline_config(ctx)

    # Level 1 should set mono-2bit for both bg and objs
    assert cfg.img_process.active_encoders_tag_bg == {"mono-2bit": 5}
    assert cfg.img_process.active_encoders_tag_objs == {"mono-2bit": 5, "airplane-symbol-v1": 10}


def test_apply_pipeline_config_sets_encoder_tags_for_level_2():
    """Test that apply_pipeline_config sets encoder tags for level 2."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=2,
    )
    mgr.apply_pipeline_config(ctx)

    # Level 2 should set avif-mid and 2bit for bg, and avif-mid and mask for objs
    assert cfg.img_process.active_encoders_tag_bg == {"mono-avif-mid": 2, "mono-2bit": 5}
    assert cfg.img_process.active_encoders_tag_objs == {"mono-avif-mid": 2, "mono-mask-1bit": 6}


def test_apply_pipeline_config_target_rate_overrides_level():
    """Test that explicit target_compression_rate overrides level-based rate."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=1,
        target_compression_rate=50.0,
    )
    mgr.apply_pipeline_config(ctx)

    # Explicit target should override level-based rate
    assert cfg.enc.compression_rate == 50.0


@pytest.mark.parametrize(
    ("compression_level", "aggregated_comp_rate", "expected_rate"),
    [
        (1, 5.0, 12.0),
        (2, 79.0, 120.0),
    ],
)
def test_boost_factor_one_does_not_change_level_selected_rate(
    compression_level,
    aggregated_comp_rate,
    expected_rate,
):
    cfg = _make_mock_cfg()
    cfg.pipeline_manager.adaptive_compression_rate_boost_factor = 1.0
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=aggregated_comp_rate,
        processed_frames_count=10,
        compression_level=compression_level,
    )

    assert ctx.target_compression_rate == expected_rate

    mgr.apply_pipeline_config(ctx)
    assert cfg.enc.compression_rate == expected_rate


def test_compression_level_preserved_across_pipeline_tiers():
    """Test that compression_level is preserved through pipeline decisions."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    # Test at different queue levels with level 2
    ctx_normal = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        compression_level=2,
    )
    assert ctx_normal.compression_level == 2

    ctx_fast_bg = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=7,
        compression_level=2,
    )
    assert ctx_fast_bg.compression_level == 2

    ctx_fast_full = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=10,
        compression_level=2,
    )
    assert ctx_fast_full.compression_level == 2


def test_default_compression_level_is_1():
    """Test that default compression_level is 1."""
    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
    )
    assert ctx.compression_level == 1


def test_encoder_tags_not_set_without_level_config():
    """Test that encoder tags don't crash when level-specific tags are missing."""
    cfg = SimpleNamespace(
        model=SimpleNamespace(tile_size=320, tile_overlap=5),
        enc=SimpleNamespace(
            compression_rate=100.0,
            max_iter_bg=5,
            max_iter_obj=10,
            compression_levels=None,
        ),
        img_process=SimpleNamespace(
            encoders_tag_bg_level_1=None,
            encoders_tag_objs_level_1=None,
            encoders_tag_bg_level_2=None,
            encoders_tag_objs_level_2=None,
            active_encoders_tag_bg=None,
            active_encoders_tag_objs=None,
        ),
        pipeline_manager=SimpleNamespace(
            adaptive_compression_rate_warmup_frames=10,
            adaptive_compression_rate_max=300.0,
            adaptive_compression_rate_boost_factor=1.5,
            adaptive_compression_rate_method="moving_average",
            adaptive_compression_rate_target_margin_ratio=0.2,
            adaptive_compression_rate_ema_alpha=0.2,
            large_dim_tile_threshold_px=1280,
        ),
    )
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=1,
    )
    # Should not crash
    mgr.apply_pipeline_config(ctx)
    assert cfg.enc.compression_rate == 100.0
    assert cfg.img_process.active_encoders_tag_bg is None
    assert cfg.img_process.active_encoders_tag_objs is None


def test_yaml_loaded_level_1_object_tags_exclude_airplane_symbol():
    config_path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    cfg = load_config(str(config_path))
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        compression_level=1,
    )
    mgr.apply_pipeline_config(ctx)

    assert cfg.img_process.active_encoders_tag_objs == {
        "mono-avif-mid": 2,
    }
    assert 10 not in cfg.img_process.active_encoders_tag_objs.values()

@pytest.mark.skip(reason="no way of currently testing this")
def test_semantic_image_manager_passes_runtime_compression_level_to_bridge():
    class _Level2Manager(SemanticImageManager):
        def get_compression_level(self) -> int:
            return 2

    config_path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    cfg = load_config(str(config_path))
    manager = _Level2Manager(cfg=cfg, service_name="test")

    img = Image.new("RGB", (8, 6), color="red")
    buff = BytesIO()
    img.save(buff, format="JPEG")

    mock_bridge = MagicMock()
    mock_bridge.encode_from_jpeg.return_value = SimpleNamespace(
        payload=b"payload",
        size_log={"header": 1, "background": 2, "objects": 0, "metadata": 3},
        img_data=SimpleNamespace(img_idx=1, crops=[]),
        timing_ms={},
    )
    manager._bridge = mock_bridge

    manager.process_image(buff.getvalue())

    assert mock_bridge.encode_from_jpeg.call_args.kwargs["compression_level"] == 2

@pytest.mark.skip(reason="no way of currently testing this")
def test_semantic_image_manager_falls_back_to_level_2_for_invalid_runtime_level():
    class _InvalidLevelManager(SemanticImageManager):
        def get_compression_level(self) -> int:
            return "invalid"

    config_path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    cfg = load_config(str(config_path))
    manager = _InvalidLevelManager(cfg=cfg, service_name="test")

    img = Image.new("RGB", (8, 6), color="red")
    buff = BytesIO()
    img.save(buff, format="JPEG")

    mock_bridge = MagicMock()
    mock_bridge.encode_from_jpeg.return_value = SimpleNamespace(
        payload=b"payload",
        size_log={"header": 1, "background": 2, "objects": 0, "metadata": 3},
        img_data=SimpleNamespace(img_idx=1, crops=[]),
        timing_ms={},
    )
    manager._bridge = mock_bridge

    manager.process_image(buff.getvalue())

    assert mock_bridge.encode_from_jpeg.call_args.kwargs["compression_level"] == 2
