# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: encoder/pipeline_manager.py
Version: 0.1
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-05-25
Description: Pipeline manager for adaptive encoding based on queue backlog.
"""

import logging
import math
from typing import Optional
from typing import NamedTuple

LOGGER = logging.getLogger(__name__)


class PipelineContext(NamedTuple):
    """Per-image pipeline context with adaptive settings."""
    skip_obj_detection: bool
    use_fast_path: bool
    use_fast_path_bg: bool = False
    use_fast_path_obj: bool = False
    target_compression_rate: float | None = None
    compression_level: int = 1


class EncoderPipelineManager:
    """Manages per-image encoding decisions based on queue pressure with hysteresis.

    Queue-based tier rules (evaluated per image):
        queue < t1                      → normal bg + normal obj
        t1 <= queue < t2                → fast bg  + normal obj
        t2 <= queue < t3                → fast bg  + fast obj
        queue >= t3                     → skip obj detection + fast bg  [skip-obj state entered]

    Hysteresis:
        Once the skip-obj state is entered it persists until the queue falls below
        (t2 + t3) / 2, at which point the pipeline returns to the fast-bg + fast-obj tier.
        Once the fast-bg + fast-obj state is active it persists until the queue falls
        below (t1 + t2) / 2, at which point the pipeline returns to fast-bg-only.

    Config changes are scoped to individual images and do not persist.
    """

    def __init__(
        self,
        cfg,
        *,
        queue_backlog_threshold_1: Optional[int] = None,
        queue_backlog_threshold_2: Optional[int] = None,
        queue_backlog_threshold_3: Optional[int] = None,
        fast_full_hysteresis_exit: Optional[float] = None,
        skip_obj_hysteresis_exit: Optional[float] = None,
        global_skip_obj_detection: bool = False,
    ):
        """Initialize pipeline manager.

        Args:
            cfg: Base configuration object.
            queue_backlog_threshold_1: Queue tier-1 threshold — fast bg starts above this.
            queue_backlog_threshold_2: Queue tier-2 threshold — fast bg + obj starts above this.
            queue_backlog_threshold_3: Queue tier-3 threshold — skip obj detection starts at/above this.
            fast_full_hysteresis_exit: Optional override for fast-full exit hysteresis.
            skip_obj_hysteresis_exit: Optional override for skip-obj exit hysteresis.
            global_skip_obj_detection: When True, every image unconditionally skips obj detection
                regardless of queue state. Intended to carry the CLI ``--skip-obj-detction`` flag
                or the encoder-level override so callers can use ``pipeline_ctx.skip_obj_detection``
                as the single per-frame authority.
        """
        self.cfg = cfg
        pipeline_cfg = getattr(cfg, "pipeline_manager", None)
        self.queue_backlog_threshold_1 = int(
            queue_backlog_threshold_1
            if queue_backlog_threshold_1 is not None
            else getattr(pipeline_cfg, "queue_backlog_threshold_1", 5)
        )
        self.queue_backlog_threshold_2 = int(
            queue_backlog_threshold_2
            if queue_backlog_threshold_2 is not None
            else getattr(pipeline_cfg, "queue_backlog_threshold_2", 10)
        )
        self.queue_backlog_threshold_3 = int(
            queue_backlog_threshold_3
            if queue_backlog_threshold_3 is not None
            else getattr(pipeline_cfg, "queue_backlog_threshold_3", 15)
        )
        if not (self.queue_backlog_threshold_1 < self.queue_backlog_threshold_2 < self.queue_backlog_threshold_3):
            raise ValueError(
                "queue thresholds must satisfy queue_backlog_threshold_1 < queue_backlog_threshold_2 < queue_backlog_threshold_3"
            )
        # Hysteresis exit: skip-obj state is held until queue drops below this value,
        # then transitions back to the fast-bg + fast-obj tier.
        self.skip_obj_hysteresis_exit = float(
            skip_obj_hysteresis_exit
            if skip_obj_hysteresis_exit is not None
            else getattr(
                pipeline_cfg,
                "skip_obj_hysteresis_exit",
                (self.queue_backlog_threshold_2 + self.queue_backlog_threshold_3) / 2.0,
            )
        )
        # Hysteresis exit: fast-bg + fast-obj state is held until queue drops below this
        # value, then transitions to fast-bg-only.
        self.fast_full_hysteresis_exit = float(
            fast_full_hysteresis_exit
            if fast_full_hysteresis_exit is not None
            else getattr(
                pipeline_cfg,
                "fast_full_hysteresis_exit",
                (self.queue_backlog_threshold_1 + self.queue_backlog_threshold_2) / 2.0,
            )
        )

        self.large_dim_tile_threshold_px = int(
            getattr(pipeline_cfg, "large_dim_tile_threshold_px", 1280)
        )
        self.adaptive_compression_rate_warmup_frames = int(
            getattr(pipeline_cfg, "adaptive_compression_rate_warmup_frames", 10)
        )
        self.adaptive_compression_rate_max = float(
            getattr(pipeline_cfg, "adaptive_compression_rate_max", 300.0)
        )
        self.adaptive_compression_rate_boost_factor = float(
            getattr(pipeline_cfg, "adaptive_compression_rate_boost_factor", 1.5)
        )
        self.adaptive_compression_rate_method = str(
            getattr(pipeline_cfg, "adaptive_compression_rate_method", "moving_average")
        ).strip().lower()
        self.adaptive_compression_rate_target_margin_ratio = float(
            getattr(pipeline_cfg, "adaptive_compression_rate_target_margin_ratio", 0.2)
        )
        self.adaptive_compression_rate_ema_alpha = float(
            getattr(pipeline_cfg, "adaptive_compression_rate_ema_alpha", 0.2)
        )

        # Persistent skip-obj state (hysteresis)
        self._skip_obj_active: bool = False
        # Persistent fast-bg + fast-obj state (hysteresis)
        self._fast_full_active: bool = False
        # Global unconditional skip flag (set once from CLI/encoder config)
        self.global_skip_obj_detection: bool = bool(global_skip_obj_detection)

        # Level-change tracking for aggregated_comp_rate reset.
        # _last_compression_level: level seen on the previous decide_pipeline call
        #     (None = not yet called).
        # _frames_since_level_change: frames processed at the *current* level.
        #     Initialised to adaptive_compression_rate_warmup_frames so the very
        #     first level does not impose an extra warmup on top of the global
        #     processed_frames_count warmup already in place.
        # level_changed: set True on the call where a level change is first detected
        #     so callers (e.g. runner.py) can reset their byte accumulators.
        self._last_compression_level: Optional[int] = None
        self._frames_since_level_change: int = self.adaptive_compression_rate_warmup_frames
        self.level_changed: bool = False
        self._adaptive_compression_rate_ema: float | None = None

        # Store original config values to restore them after per-image adjustments
        self._original_compression_rate = float(getattr(cfg.enc, "compression_rate", 1.0))
        self._original_max_iter_bg = int(getattr(cfg.enc, "max_iter_bg", 0))
        self._original_max_iter_obj = int(getattr(cfg.enc, "max_iter_obj", 0))
        model_cfg = getattr(cfg, "model", None)
        self._original_tile_size = getattr(model_cfg, "tile_size", None)
        self._original_tile_overlap = getattr(model_cfg, "tile_overlap", None)

    def _resolve_target_compression_rate(
        self,
        *,
        aggregated_comp_rate: float | None,
        processed_frames_count: int | None,
        skip_obj_detection: bool,
        use_fast_path_bg: bool,
        use_fast_path_obj: bool,
        compression_level: int,
    ) -> float:
        """Return the effective per-image compression target (default or adaptive)."""
        effective_compression_rate = self._get_compression_rate_for_level(compression_level)
        # Keep adaptive target shaping independent from object-detection skip and
        # fast-path routing decisions. Those switches control processing path only.
        _ = skip_obj_detection
        _ = use_fast_path_bg
        _ = use_fast_path_obj
        if processed_frames_count is None:
            return effective_compression_rate
        if processed_frames_count < self.adaptive_compression_rate_warmup_frames:
            return effective_compression_rate
        # Per-level warmup: block adaptive tuning until enough frames have been
        # processed at the *current* compression level.  _frames_since_level_change
        # resets to 0 on every level change so a fresh warmup window is enforced.
        if self._frames_since_level_change < self.adaptive_compression_rate_warmup_frames:
            return effective_compression_rate
        if aggregated_comp_rate is None or not math.isfinite(aggregated_comp_rate):
            return effective_compression_rate

        smoothed_comp_rate = self._get_smoothed_aggregate_comp_rate(aggregated_comp_rate)
        if not math.isfinite(smoothed_comp_rate):
            return effective_compression_rate

        # Always compute a corrective target to bring the aggregate back to the level rate.
        # The margin is applied only to clamp the result; it is NOT a gate to skip correction.
        base_target_rate = self._backsolve_target_compression_rate(
            smoothed_comp_rate=smoothed_comp_rate,
            effective_compression_rate=effective_compression_rate,
            processed_frames_count=processed_frames_count,
        )
        target_compression_rate = base_target_rate * self.adaptive_compression_rate_boost_factor

        # Clamp to ±margin around the level rate (not affected by whether the aggregate is
        # close to level rate or far).  This ensures the corrective target stays within a
        # reasonable range around the configured level rate.
        min_target = effective_compression_rate * (1.0 - self.adaptive_compression_rate_target_margin_ratio)
        max_target = effective_compression_rate * (1.0 + self.adaptive_compression_rate_target_margin_ratio)
        target_compression_rate = min(max(target_compression_rate, min_target), max_target)
        return min(target_compression_rate, self.adaptive_compression_rate_max)

    def _get_smoothed_aggregate_comp_rate(self, aggregated_comp_rate: float) -> float:
        """Return smoothed aggregate compression rate using configured method."""
        if self.adaptive_compression_rate_method == "ema":
            alpha = self.adaptive_compression_rate_ema_alpha
            if not (0.0 < alpha <= 1.0):
                return aggregated_comp_rate
            if self._adaptive_compression_rate_ema is None:
                self._adaptive_compression_rate_ema = aggregated_comp_rate
            else:
                self._adaptive_compression_rate_ema = (
                    (1.0 - alpha) * self._adaptive_compression_rate_ema
                    + alpha * aggregated_comp_rate
                )
            return self._adaptive_compression_rate_ema
        return aggregated_comp_rate

    def _backsolve_target_compression_rate(
        self,
        *,
        smoothed_comp_rate: float,
        effective_compression_rate: float,
        processed_frames_count: int | None,
    ) -> float:
        """Solve next target so one-step aggregate update reaches effective_compression_rate."""
        if self.adaptive_compression_rate_method == "ema":
            alpha = self.adaptive_compression_rate_ema_alpha
            if not (0.0 < alpha <= 1.0):
                return effective_compression_rate
            return (effective_compression_rate - (1.0 - alpha) * smoothed_comp_rate) / alpha

        frame_count = int(processed_frames_count or 0)
        if frame_count <= 0:
            return effective_compression_rate
        return (
            effective_compression_rate * (frame_count + 1)
            - smoothed_comp_rate * frame_count
        )

    def decide_pipeline(
        self,
        image_size_bytes: int,
        queue_size: int,
        aggregated_comp_rate: float | None = None,
        processed_frames_count: int | None = None,
        compression_level: int = 1,
    ) -> PipelineContext:
        """Decide adaptive pipeline settings for the current image.

        Args:
            image_size_bytes: Size of the image file in bytes (retained for API compatibility).
            queue_size: Current number of images in the processing queue.
            aggregated_comp_rate: Aggregate input/payload compression rate over
                previously processed images.
            processed_frames_count: Number of previously processed images included
                in the aggregate compression rate.
            compression_level: Compression level (1 or 2) to determine encoder tags and rate.

        Returns:
            PipelineContext with adaptive settings for this image.
        """
        # ---- Detect compression level change and reset per-level warmup counter ----
        self.level_changed = False
        if self._last_compression_level is None:
            # First-ever call: initialise tracking without triggering a reset.
            self._last_compression_level = compression_level
        elif compression_level != self._last_compression_level:
            LOGGER.info(
                "Compression level changed %d → %d: resetting aggregated_comp_rate warmup "
                "(will wait %d frames before resuming adaptive rate tuning)",
                self._last_compression_level,
                compression_level,
                self.adaptive_compression_rate_warmup_frames,
            )
            self._last_compression_level = compression_level
            self._frames_since_level_change = 0
            self._adaptive_compression_rate_ema = None
            self.level_changed = True

        try:
            return self._decide_pipeline_inner(
                image_size_bytes=image_size_bytes,
                queue_size=queue_size,
                aggregated_comp_rate=aggregated_comp_rate,
                processed_frames_count=processed_frames_count,
                compression_level=compression_level,
            )
        finally:
            # Advance the per-level warmup counter once per frame (clamped so it never
            # exceeds warmup_frames; avoids unbounded growth on very long runs).
            if self._frames_since_level_change < self.adaptive_compression_rate_warmup_frames:
                self._frames_since_level_change += 1

    def _decide_pipeline_inner(
        self,
        image_size_bytes: int,
        queue_size: int,
        aggregated_comp_rate: float | None,
        processed_frames_count: int | None,
        compression_level: int,
    ) -> "PipelineContext":
        """Inner implementation of decide_pipeline (called after level-change handling)."""
        skip_obj_detection = False
        use_fast_path_bg = False
        use_fast_path_obj = False

        LOGGER.debug(
            "Deciding pipeline image_size_bytes=%d queue_size=%d aggregated_comp_rate=%s processed_frames_count=%s skip_obj_active=%s fast_full_active=%s",
            image_size_bytes,
            queue_size,
            f"{aggregated_comp_rate:.4f}" if aggregated_comp_rate is not None else None,
            processed_frames_count,
            self._skip_obj_active,
            self._fast_full_active,
        )

        if self._skip_obj_active:
            if queue_size < self.skip_obj_hysteresis_exit:
                # Exit hysteresis: drop back to fast-bg + fast-obj tier.
                self._skip_obj_active = False
                self._fast_full_active = True
                use_fast_path_bg = True
                use_fast_path_obj = True
                LOGGER.debug(
                    "Queue backlog %d dropped below hysteresis exit %.1f: "
                    "returning to fast-bg + fast-obj tier",
                    queue_size,
                    self.skip_obj_hysteresis_exit,
                )
            else:
                # Remain in skip-obj state.
                skip_obj_detection = True
                use_fast_path_bg = True
                LOGGER.debug(
                    "Queue backlog %d still above hysteresis exit %.1f: "
                    "holding skip-obj state",
                    queue_size,
                    self.skip_obj_hysteresis_exit,
                )
        elif self._fast_full_active:
            if queue_size >= self.queue_backlog_threshold_3:
                # Upward transition always wins over hysteresis: escalate to skip-obj state.
                self._fast_full_active = False
                self._skip_obj_active = True
                skip_obj_detection = True
                use_fast_path_bg = True
                LOGGER.debug(
                    "Queue backlog %d reached threshold_3=%d while fast-full active: "
                    "escalating to skip-obj state",
                    queue_size,
                    self.queue_backlog_threshold_3,
                )
            elif queue_size < self.fast_full_hysteresis_exit:
                # Exit fast-full hysteresis: move to previous tier (fast-bg-only).
                self._fast_full_active = False
                use_fast_path_bg = True
                LOGGER.debug(
                    "Queue backlog %d dropped below fast-full hysteresis exit %.1f: "
                    "returning to fast-bg-only tier",
                    queue_size,
                    self.fast_full_hysteresis_exit,
                )
            else:
                # Hold fast-bg + fast-obj state.
                use_fast_path_bg = True
                use_fast_path_obj = True
                LOGGER.debug(
                    "Queue backlog %d still above fast-full hysteresis exit %.1f: "
                    "holding fast-bg + fast-obj state",
                    queue_size,
                    self.fast_full_hysteresis_exit,
                )
        else:
            if queue_size < self.queue_backlog_threshold_1:
                pass  # normal path
            elif queue_size < self.queue_backlog_threshold_2:
                use_fast_path_bg = True
            elif queue_size < self.queue_backlog_threshold_3:
                self._fast_full_active = True
                use_fast_path_bg = True
                use_fast_path_obj = True
            else:
                # Enter skip-obj state.
                self._skip_obj_active = True
                self._fast_full_active = False
                skip_obj_detection = True
                use_fast_path_bg = True
                LOGGER.debug(
                    "Queue backlog %d reached threshold_3=%d: entering skip-obj state",
                    queue_size,
                    self.queue_backlog_threshold_3,
                )

        # Forced skip sources (CLI/config-driven) keep queue-tier fast-path behavior.
        # Only queue pressure should decide fast bg/obj selection.
        if self.global_skip_obj_detection:
            skip_obj_detection = True
            use_fast_path_obj = False

        use_fast_path = use_fast_path_bg or use_fast_path_obj
        target_compression_rate = self._resolve_target_compression_rate(
            aggregated_comp_rate=aggregated_comp_rate,
            processed_frames_count=processed_frames_count,
            skip_obj_detection=skip_obj_detection,
            use_fast_path_bg=use_fast_path_bg,
            use_fast_path_obj=use_fast_path_obj,
            compression_level=compression_level,
        )

        if use_fast_path:
            LOGGER.debug(
                "Queue backlog %d: fast path active (fast_bg=%s fast_obj=%s skip_obj=%s)",
                queue_size,
                use_fast_path_bg,
                use_fast_path_obj,
                skip_obj_detection,
            )

        if target_compression_rate != self._original_compression_rate:
            LOGGER.debug(
                "Queue backlog %d: setting encoder compression_rate from %.4f to %.4f based on aggregated_comp_rate=%s after %d processed frames",
                queue_size,
                self._original_compression_rate,
                target_compression_rate,
                f"{aggregated_comp_rate:.4f}" if aggregated_comp_rate is not None else None,
                processed_frames_count if processed_frames_count is not None else 0,
            )

        return PipelineContext(
            skip_obj_detection=skip_obj_detection,
            use_fast_path=use_fast_path,
            use_fast_path_bg=use_fast_path_bg,
            use_fast_path_obj=use_fast_path_obj,
            target_compression_rate=target_compression_rate,
            compression_level=compression_level,
        )

    def apply_pipeline_config(
        self,
        context: PipelineContext,
        *,
        img_size: tuple[int, int] | None = None,
    ) -> None:
        """Apply per-image config adjustments based on pipeline context.

        Args:
            context: Pipeline context from decide_pipeline().

        Notes:
            Changes are temporary and should be reset after processing the image.
        """
        fast_bg = bool(getattr(context, "use_fast_path_bg", False))
        fast_obj = bool(getattr(context, "use_fast_path_obj", False))
        target_compression_rate = getattr(context, "target_compression_rate", None)
        compression_level = int(getattr(context, "compression_level", 1))

        compression_rate = self._get_compression_rate_for_level(compression_level)
        if target_compression_rate is not None:
            compression_rate = float(target_compression_rate)
        self.cfg.enc.compression_rate = compression_rate
        self.cfg.enc.max_iter_bg = 0 if fast_bg else self._original_max_iter_bg
        self.cfg.enc.max_iter_obj = 0 if fast_obj else self._original_max_iter_obj
        self._set_encoder_tags_for_level(compression_level)
        self._set_scaling_for_level(compression_level)

        model_cfg = getattr(self.cfg, "model", None)
        if (
            model_cfg is not None
            and not context.skip_obj_detection
            and img_size is not None
            and max(img_size) > self.large_dim_tile_threshold_px
        ):
            model_cfg.tile_size = 640
            model_cfg.tile_overlap = 10

    def restore_config(self) -> None:
        """Restore config to original values after per-image processing."""
        self.cfg.enc.compression_rate = self._original_compression_rate
        self.cfg.enc.max_iter_bg = self._original_max_iter_bg
        self.cfg.enc.max_iter_obj = self._original_max_iter_obj
        img_process = getattr(self.cfg, "img_process", None)
        if img_process is not None:
            img_process.active_encoders_tag_bg = None
            img_process.active_encoders_tag_objs = None
            img_process.active_bg_scaling_min1 = None
            img_process.active_bg_scaling_min2 = None
            img_process.active_bg_scaling_max = None
            img_process.active_obj_scaling_min = None
            img_process.active_obj_scaling_max = None
        model_cfg = getattr(self.cfg, "model", None)
        if model_cfg is not None:
            model_cfg.tile_size = self._original_tile_size
            model_cfg.tile_overlap = self._original_tile_overlap

    def get_skip_obj_detection_override(self, context: PipelineContext) -> bool:
        """Backward-compatible helper for callers expecting explicit skip override."""
        return bool(getattr(context, "skip_obj_detection", False))

    def _get_compression_rate_for_level(self, level: int) -> float:
        """Get compression rate based on level (1 or 2)."""
        compression_levels = getattr(self.cfg.enc, "compression_levels", None)
        if compression_levels is None:
            return self._original_compression_rate
        level_key = f"level_{level}"
        return float(getattr(compression_levels, level_key, self._original_compression_rate))

    def _set_encoder_tags_for_level(self, level: int) -> None:
        """Set active runtime encoder tags based on compression level."""
        img_process = getattr(self.cfg, "img_process", None)
        if img_process is None:
            return

        level_suffix = f"_level_{level}"
        default_bg_key = "encoders_tag_bg"
        default_obj_key = "encoders_tag_objs"
        level_bg_key = default_bg_key + level_suffix
        level_obj_key = default_obj_key + level_suffix

        bg_tags = getattr(img_process, level_bg_key, None)
        img_process.active_encoders_tag_bg = dict(bg_tags) if bg_tags is not None else None

        obj_tags = getattr(img_process, level_obj_key, None)
        img_process.active_encoders_tag_objs = dict(obj_tags) if obj_tags is not None else None

    def _set_scaling_for_level(self, level: int) -> None:
        """Set active runtime scaling values based on compression level."""
        img_process = getattr(self.cfg, "img_process", None)
        if img_process is None:
            return

        for base_name in (
            "bg_scaling_min1",
            "bg_scaling_min2",
            "bg_scaling_max",
            "obj_scaling_min",
            "obj_scaling_max",
        ):
            level_value = getattr(img_process, f"{base_name}_level_{level}", None)
            setattr(img_process, f"active_{base_name}", None if level_value is None else int(level_value))


    def get_effective_skip_obj_detection_for_bg_only(self, context: PipelineContext) -> bool:
        """Compatibility helper retained for legacy call sites/tests."""
        return bool(getattr(context, "skip_obj_detection", False))
