# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: tests/test_pipeline_manager.py
Version: 0.1
Description: Unit tests for EncoderPipelineManager.
"""

from types import SimpleNamespace
import pytest
from semantic_img_comp.encoder.pipeline_manager import (
    EncoderPipelineManager,
    PipelineContext,
)


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


def test_pipeline_context_creation():
    """Test PipelineContext NamedTuple creation."""
    ctx = PipelineContext(skip_obj_detection=True, use_fast_path=False)
    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path is False
    assert ctx.target_compression_rate is None


def test_pipeline_manager_init():
    """Test EncoderPipelineManager initialization."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=3,
        queue_backlog_threshold_2=6,
        queue_backlog_threshold_3=9,
    )

    assert mgr.cfg is cfg
    assert mgr.queue_backlog_threshold_1 == 3
    assert mgr.queue_backlog_threshold_2 == 6
    assert mgr.queue_backlog_threshold_3 == 9
    assert mgr.adaptive_compression_rate_warmup_frames == 10
    assert mgr.adaptive_compression_rate_max == 300.0
    assert mgr.adaptive_compression_rate_boost_factor == 1.5
    assert mgr.adaptive_compression_rate_method == "moving_average"
    assert mgr.adaptive_compression_rate_target_margin_ratio == pytest.approx(0.2)
    assert mgr.adaptive_compression_rate_ema_alpha == pytest.approx(0.2)
    assert mgr._original_max_iter_bg == 5
    assert mgr._original_max_iter_obj == 10


def test_decide_pipeline_below_thresholds():
    """Test pipeline decision when both image size and queue are below thresholds."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=2)

    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path is False


def test_decide_pipeline_accepts_aggregated_comp_rate_input():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=4.25,
        processed_frames_count=1,
    )

    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path is False


def test_decide_pipeline_warmup_blocks_target_compression_rate_override():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=125.0,
        processed_frames_count=9,
    )

    assert ctx.target_compression_rate == 100.0


def test_decide_pipeline_corrects_target_when_aggregate_above_level_after_warmup():
    """After warmup, any aggregate deviation triggers correction (clamped to margin).
    Margin is applied only as a clamp range, NOT as a gate to skip correction."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # aggregate=125, level=100 (outside old margin of ±20)
    # backsolve: 100*10 - 125*9 = -125; boost -125*1.5 = -187.5; clamp to [80,120] → 80
    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=125.0,
        processed_frames_count=10,
    )

    assert ctx.target_compression_rate == pytest.approx(80.0)


def test_decide_pipeline_corrects_target_upward_when_aggregate_below_level():
    """When aggregate is below level rate, correction targets upward (within margin clamp)."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # aggregate=75, level=100 (clearly below)
    # backsolve: 100*11 - 75*10 = 1100 - 750 = 350; boost 350*1.5 = 525; clamp to [80,120] → 120
    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=75.0,
        processed_frames_count=10,
    )

    assert ctx.target_compression_rate == pytest.approx(120.0)


def test_decide_pipeline_corrects_target_well_above_level_with_high_margin():
    """When margin is wider (0.5 = ±50%), the corrective target can go well above
    the level rate when aggregate is sufficiently below it."""
    cfg = _make_mock_cfg()
    cfg.pipeline_manager.adaptive_compression_rate_target_margin_ratio = 0.5  # ±50%
    mgr = EncoderPipelineManager(cfg)

    # aggregate=50, level=100 (half the level rate)
    # backsolve: 100*11 - 50*10 = 1100 - 500 = 600; boost 600*1.5 = 900; clamp to [50,150] → 150
    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=50.0,
        processed_frames_count=10,
    )

    # Target can now go up to 150 (level * 1.5) due to wider margin
    assert ctx.target_compression_rate == pytest.approx(150.0)


def test_decide_pipeline_corrects_target_moderately_above_level_with_wider_margin():
    """With aggregate moderately below level and default margin (0.2), target is
    pushed to the upper clamp limit."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # aggregate=90, level=100 (10 points below)
    # backsolve: 100*11 - 90*10 = 1100 - 900 = 200; boost 200*1.5 = 300; clamp to [80,120] → 120
    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=90.0,
        processed_frames_count=10,
    )

    # With default margin (0.2), target reaches upper limit of 120
    assert ctx.target_compression_rate == pytest.approx(120.0)


def test_decide_pipeline_uses_aggregated_target_after_warmup_on_normal_path():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # aggregate=118, level=100 (formerly within old margin, but now corrects anyway)
    # backsolve: 100*11 - 118*10 = -80; boost -80*1.5 = -120; clamp to [80,120] → 80
    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=118.0,
        processed_frames_count=10,
    )

    assert ctx.use_fast_path is False
    assert ctx.target_compression_rate == pytest.approx(80.0)


def test_decide_pipeline_uses_aggregated_target_after_warmup_on_bg_fast_only_tier():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    # aggregate=119, level=100
    # backsolve: 100*11 - 119*10 = -90; boost -90*1.5 = -135; clamp to [80,120] → 80
    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=7,
        aggregated_comp_rate=119.0,
        processed_frames_count=10,
    )

    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False
    assert ctx.target_compression_rate == pytest.approx(80.0)


def test_decide_pipeline_uses_1p5x_configured_rate_when_aggregate_misses_target():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=-1.0,
        processed_frames_count=10,
    )

    assert ctx.target_compression_rate == 120.0


def test_decide_pipeline_uses_configured_boost_factor_when_aggregate_misses_target():
    cfg = _make_mock_cfg()
    cfg.pipeline_manager.adaptive_compression_rate_boost_factor = 2.0
    cfg.pipeline_manager.adaptive_compression_rate_target_margin_ratio = 1.0
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=-1.0,
        processed_frames_count=10,
    )

    assert ctx.target_compression_rate == 200.0


def test_decide_pipeline_clamps_target_compression_rate_to_max():
    cfg = _make_mock_cfg()
    cfg.enc.compression_rate = 200.0
    cfg.pipeline_manager.adaptive_compression_rate_max = 180.0
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=2,
        aggregated_comp_rate=150.0,
        processed_frames_count=10,
    )

    assert ctx.target_compression_rate == 180.0


def test_decide_pipeline_image_size_exceeds_threshold():
    """Large image size alone should not skip object detection."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(image_size_bytes=1_500_000, queue_size=2)

    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path is False


def test_decide_pipeline_queue_exceeds_threshold():
    """Test pipeline decision when queue backlog exceeds threshold."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=10)

    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path is True


def test_decide_pipeline_both_exceed_thresholds():
    """Queue tier rules drive fast-path behavior independently of image size."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = mgr.decide_pipeline(image_size_bytes=1_500_000, queue_size=10)

    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path is True


def test_decide_pipeline_bg_only_fast_path_between_thresholds():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=7)

    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False


def test_decide_pipeline_skips_obj_detection_at_or_above_threshold_3():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=15)

    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False


def test_global_skip_obj_detection_keeps_normal_bg_path_at_low_queue():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
        global_skip_obj_detection=True,
    )

    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=0)

    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path is False
    assert ctx.use_fast_path_bg is False
    assert ctx.use_fast_path_obj is False


def test_global_skip_obj_detection_still_uses_bg_fast_tier_when_queue_grows():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
        global_skip_obj_detection=True,
    )

    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=7)

    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False


def test_hysteresis_skip_obj_state_persists_above_exit_threshold():
    """skip-obj state must persist while queue stays at or above the hysteresis exit threshold."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )
    # hysteresis_exit = (10+15)/2 = 12.5

    # Enter skip-obj state
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=15)
    assert ctx.skip_obj_detection is True
    assert mgr._skip_obj_active is True

    # Queue drops to exactly 13 (above 12.5) — should remain in skip-obj
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=13)
    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False
    assert mgr._skip_obj_active is True


def test_hysteresis_exits_skip_obj_below_exit_threshold():
    """skip-obj state must exit once queue drops below the hysteresis threshold."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )
    # hysteresis_exit = (10+15)/2 = 12.5

    # Enter skip-obj state
    mgr.decide_pipeline(image_size_bytes=0, queue_size=16)
    assert mgr._skip_obj_active is True

    # Queue drops to 12 (below 12.5) — exits hysteresis → fast-bg + fast-obj
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=12)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is True
    assert mgr._skip_obj_active is False
    assert mgr._fast_full_active is True


def test_hysteresis_normal_tiers_reachable_after_exit():
    """After exiting latches, the manager eventually evaluates tier rules normally again."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    # Enter and exit skip-obj state (which activates fast-full latch)
    mgr.decide_pipeline(image_size_bytes=0, queue_size=20)
    mgr.decide_pipeline(image_size_bytes=0, queue_size=11)  # 11 < 12.5 => exits skip-obj, enters fast-full latch
    assert mgr._skip_obj_active is False
    assert mgr._fast_full_active is True

    # Drop below fast-full hysteresis exit (7.5): transitions to bg-only first
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=2)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False
    assert mgr._fast_full_active is False

    # Next decision now follows base tiers; queue below t1 => normal path
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=2)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is False
    assert ctx.use_fast_path_obj is False


def test_hysteresis_fast_full_state_persists_above_exit_threshold():
    """fast-bg+fast-obj state must persist while queue stays at or above (t1+t2)/2."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )
    # fast_full_exit = (5+10)/2 = 7.5

    # Enter fast-full state from base tiers.
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=10)
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is True
    assert mgr._fast_full_active is True


def test_fast_full_tier_applies_adaptive_compression_rate_after_warmup():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    ctx = mgr.decide_pipeline(
        image_size_bytes=0,
        queue_size=10,
        aggregated_comp_rate=160.0,
        processed_frames_count=10,
    )

    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is True
    assert ctx.target_compression_rate == pytest.approx(80.0)

    # Stay above fast_full_exit => hold fast-full state.
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=8)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is True
    assert mgr._fast_full_active is True


def test_hysteresis_fast_full_exits_to_bg_only_below_exit_threshold():
    """fast-bg+fast-obj state exits to fast-bg-only when queue drops below (t1+t2)/2."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )
    # fast_full_exit = 7.5

    mgr.decide_pipeline(image_size_bytes=0, queue_size=10)
    assert mgr._fast_full_active is True

    # Drop below exit => transition to bg-only
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=7)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False
    assert mgr._fast_full_active is False


def test_hysteresis_fast_full_escalates_to_skip_obj_at_threshold_3():
    """When queue grows while fast-full is active, manager must escalate to skip-obj tier."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    # Enter fast-full state first.
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=10)
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is True
    assert mgr._fast_full_active is True

    # Grow to threshold_3 -> escalate to skip-obj.
    ctx = mgr.decide_pipeline(image_size_bytes=0, queue_size=15)
    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False
    assert mgr._skip_obj_active is True
    assert mgr._fast_full_active is False


def test_skip_obj_tier_applies_adaptive_compression_rate_after_warmup():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    ctx = mgr.decide_pipeline(
        image_size_bytes=500_000,
        queue_size=15,
        aggregated_comp_rate=180.0,
        processed_frames_count=10,
    )

    assert ctx.skip_obj_detection is True
    assert ctx.target_compression_rate == pytest.approx(80.0)


def test_apply_pipeline_config_fast_path():
    """Test that apply_pipeline_config sets max_iter values to 0 for fast path."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=True,
        use_fast_path_bg=True,
        use_fast_path_obj=True,
    )
    mgr.apply_pipeline_config(ctx)

    assert cfg.enc.compression_rate == 100.0
    assert cfg.enc.max_iter_bg == 0
    assert cfg.enc.max_iter_obj == 0


def test_apply_pipeline_config_no_fast_path():
    """Test that apply_pipeline_config leaves config unchanged when fast path is disabled."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(skip_obj_detection=False, use_fast_path=False)
    mgr.apply_pipeline_config(ctx)

    # Original values should be preserved
    assert cfg.enc.compression_rate == 100.0
    assert cfg.enc.max_iter_bg == 5
    assert cfg.enc.max_iter_obj == 10


def test_apply_pipeline_config_sets_target_compression_rate():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=False,
        target_compression_rate=150.0,
    )
    mgr.apply_pipeline_config(ctx)

    assert cfg.enc.compression_rate == 150.0
    assert cfg.enc.max_iter_bg == 5
    assert cfg.enc.max_iter_obj == 10


def test_restore_config():
    """Test that restore_config restores original values."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # Apply fast path (changes config)
    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=True,
        use_fast_path_bg=True,
        use_fast_path_obj=True,
        target_compression_rate=150.0,
    )
    mgr.apply_pipeline_config(ctx)
    assert cfg.enc.compression_rate == 150.0
    assert cfg.enc.max_iter_bg == 0
    assert cfg.enc.max_iter_obj == 0

    # Restore
    mgr.restore_config()
    assert cfg.enc.compression_rate == 100.0
    assert cfg.enc.max_iter_bg == 5
    assert cfg.enc.max_iter_obj == 10
    assert cfg.model.tile_size == 320
    assert cfg.model.tile_overlap == 5


def test_apply_pipeline_config_large_dim_sets_tile_params_when_obj_detection_active():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(skip_obj_detection=False, use_fast_path=False)
    mgr.apply_pipeline_config(ctx, img_size=(1920, 1080))

    assert cfg.model.tile_size == 640
    assert cfg.model.tile_overlap == 10


def test_apply_pipeline_config_large_dim_does_not_set_tiles_when_obj_detection_skipped():
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(skip_obj_detection=True, use_fast_path=False)
    mgr.apply_pipeline_config(ctx, img_size=(1920, 1080))

    assert cfg.model.tile_size == 320
    assert cfg.model.tile_overlap == 5


def test_get_skip_obj_detection_override():
    """Test get_skip_obj_detection_override method."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(skip_obj_detection=True, use_fast_path=False)
    assert mgr.get_skip_obj_detection_override(ctx) is True

    ctx = PipelineContext(skip_obj_detection=False, use_fast_path=False)
    assert mgr.get_skip_obj_detection_override(ctx) is False


def test_get_effective_skip_obj_detection_for_bg_only():
    """Test get_effective_skip_obj_detection_for_bg_only method."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    ctx = PipelineContext(skip_obj_detection=True, use_fast_path=False)
    assert mgr.get_effective_skip_obj_detection_for_bg_only(ctx) is True

    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=True,
        use_fast_path_bg=True,
        use_fast_path_obj=True,
    )
    assert mgr.get_effective_skip_obj_detection_for_bg_only(ctx) is False


def test_pipeline_manager_config_edge_cases():
    """Test edge cases in config initialization."""
    cfg = SimpleNamespace(enc=SimpleNamespace())  # No max_iter_bg/obj
    mgr = EncoderPipelineManager(cfg)

    assert mgr._original_compression_rate == 1.0
    # Should default to 0
    assert mgr._original_max_iter_bg == 0
    assert mgr._original_max_iter_obj == 0


def test_multiple_restore_cycles():
    """Test multiple apply-restore cycles work correctly."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # First cycle
    ctx = PipelineContext(
        skip_obj_detection=False,
        use_fast_path=True,
        use_fast_path_bg=True,
        use_fast_path_obj=True,
    )
    mgr.apply_pipeline_config(ctx)
    assert cfg.enc.max_iter_bg == 0
    mgr.restore_config()
    assert cfg.enc.max_iter_bg == 5

    # Second cycle
    mgr.apply_pipeline_config(ctx)
    assert cfg.enc.max_iter_bg == 0
    mgr.restore_config()
    assert cfg.enc.max_iter_bg == 5


def test_queue_size_equals_threshold():
    """Test queue-size boundary behavior across all three thresholds."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )

    # At threshold_1: bg fast path starts
    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=5)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False

    # At threshold_2: bg + obj fast path starts
    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=10)
    assert ctx.skip_obj_detection is False
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is True

    # At threshold_3 while fast-full latch is active: escalate to skip-obj
    ctx = mgr.decide_pipeline(image_size_bytes=500_000, queue_size=15)
    assert ctx.use_fast_path is True
    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False

    # From a fresh manager, threshold_3 still enters skip-obj state.
    fresh_mgr = EncoderPipelineManager(
        cfg,
        queue_backlog_threshold_1=5,
        queue_backlog_threshold_2=10,
        queue_backlog_threshold_3=15,
    )
    ctx = fresh_mgr.decide_pipeline(image_size_bytes=500_000, queue_size=15)
    assert ctx.skip_obj_detection is True
    assert ctx.use_fast_path_bg is True
    assert ctx.use_fast_path_obj is False


def test_image_size_equals_threshold():
    """Image-size threshold no longer controls skip_obj_detection."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    # At threshold - should not skip.
    ctx = mgr.decide_pipeline(image_size_bytes=1_000_000, queue_size=1)
    assert ctx.skip_obj_detection is False

    # Above threshold - still should not skip (queue rules decide skip behavior).
    ctx = mgr.decide_pipeline(image_size_bytes=1_000_001, queue_size=1)
    assert ctx.skip_obj_detection is False


# ---------------------------------------------------------------------------
# Level-change reset tests
# ---------------------------------------------------------------------------

def test_level_changed_flag_false_on_first_call():
    """level_changed must be False on the very first decide_pipeline call."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)

    assert mgr.level_changed is False


def test_level_changed_flag_false_when_level_stays_same():
    """level_changed must be False when the same compression level is used repeatedly."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)
    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)

    assert mgr.level_changed is False


def test_level_changed_flag_true_on_level_change():
    """level_changed must be True on the call where the compression level first changes."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)
    assert mgr.level_changed is False

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=2)
    assert mgr.level_changed is True


def test_level_changed_flag_resets_to_false_on_subsequent_same_level_call():
    """After a level change, level_changed must revert to False on the next same-level call."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)
    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=2)
    assert mgr.level_changed is True  # change detected here

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=2)
    assert mgr.level_changed is False  # back to False on same level


def test_level_change_blocks_adaptive_rate_despite_high_processed_frames_count():
    """After a level change, adaptive rate tuning is suppressed even when
    processed_frames_count already exceeds warmup_frames."""
    cfg = _make_mock_cfg()
    # warmup_frames = 10 (from _make_mock_cfg)
    mgr = EncoderPipelineManager(cfg)

    # Establish level 1 context with processed_frames_count well past warmup.
    mgr.decide_pipeline(
        image_size_bytes=0,
        queue_size=0,
        aggregated_comp_rate=80.0,
        processed_frames_count=20,
        compression_level=1,
    )

    # Switch to level 2: warmup window resets regardless of processed_frames_count.
    ctx = mgr.decide_pipeline(
        image_size_bytes=0,
        queue_size=0,
        aggregated_comp_rate=80.0,
        processed_frames_count=20,  # well past global warmup
        compression_level=2,
    )

    assert mgr.level_changed is True
    # Adaptive target shaping must NOT be applied during per-level warmup.
    assert ctx.target_compression_rate == 100.0


def test_level_change_adaptive_resumes_after_warmup_frames():
    """Adaptive rate tuning must resume exactly after adaptive_compression_rate_warmup_frames
    frames have been processed at the new level."""
    cfg = _make_mock_cfg()
    warmup = cfg.pipeline_manager.adaptive_compression_rate_warmup_frames  # 10
    mgr = EncoderPipelineManager(cfg)

    # Establish level 1 (seeds _last_compression_level).
    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)

    # Frame where level change is detected — counts as warmup frame #1 internally.
    mgr.decide_pipeline(
        image_size_bytes=0,
        queue_size=0,
        aggregated_comp_rate=79.0,
        processed_frames_count=20,
        compression_level=2,
    )

    # Process warmup-1 more frames (frames 2 … warmup); all must still be in warmup.
    for _ in range(warmup - 1):
        ctx = mgr.decide_pipeline(
            image_size_bytes=0,
            queue_size=0,
            aggregated_comp_rate=79.0,
            processed_frames_count=20,
            compression_level=2,
        )
        assert ctx.target_compression_rate == 100.0, (
            "Adaptive boost must not fire during per-level warmup"
        )

    # The next call is the first frame *after* the warmup window → adaptive kicks in.
    ctx = mgr.decide_pipeline(
        image_size_bytes=0,
        queue_size=0,
        aggregated_comp_rate=79.0,   # below configured rate and outside margin → adaptive expected
        processed_frames_count=20,
        compression_level=2,
    )
    expected_boosted_rate = 120.0
    assert ctx.target_compression_rate == expected_boosted_rate


def test_frames_since_level_change_resets_to_zero_on_level_change():
    """_frames_since_level_change must be 0 at the start of the frame where a change
    is detected (before the counter is incremented at frame end)."""
    cfg = _make_mock_cfg()
    mgr = EncoderPipelineManager(cfg)

    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=1)
    # Counter was clamped at warmup_frames; after one call it stays there (already at max).
    assert mgr._frames_since_level_change == cfg.pipeline_manager.adaptive_compression_rate_warmup_frames

    # Level change: counter must reset.  After the call the finally block increments it to 1.
    mgr.decide_pipeline(image_size_bytes=0, queue_size=0, compression_level=2)
    assert mgr._frames_since_level_change == 1


def test_level_change_back_and_forth_resets_warmup_each_time():
    """Each transition between levels must independently reset the warmup counter."""
    cfg = _make_mock_cfg()
    warmup = cfg.pipeline_manager.adaptive_compression_rate_warmup_frames  # 10
    mgr = EncoderPipelineManager(cfg)

    common_kwargs = dict(
        image_size_bytes=0,
        queue_size=0,
        aggregated_comp_rate=79.0,
        processed_frames_count=20,
    )

    # Warm up on level 1.
    mgr.decide_pipeline(**common_kwargs, compression_level=1)

    # Switch to level 2: warmup resets.
    for i in range(warmup):
        ctx = mgr.decide_pipeline(**common_kwargs, compression_level=2)
        if i < warmup - 1:
            assert ctx.target_compression_rate == 100.0  # still in warmup

    # Adaptive is now active at level 2.
    ctx = mgr.decide_pipeline(**common_kwargs, compression_level=2)
    assert ctx.target_compression_rate == pytest.approx(120.0)

    # Switch back to level 1: warmup resets again.
    ctx = mgr.decide_pipeline(**common_kwargs, compression_level=1)
    assert mgr.level_changed is True
    assert ctx.target_compression_rate == 100.0  # in warmup again

