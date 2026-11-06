# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: encoder/encoder.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: encoder class.
"""
import logging
import math
import socket
import struct
from pathlib import Path
from typing import Dict, List
from PIL import Image

from semantic_img_comp.core.background import BgData
from semantic_img_comp.core.frame import ImgEncData
from semantic_img_comp.core.object import ObjData
from semantic_img_comp.encoder import codecs as encoder_codecs
from semantic_img_comp.encoder.mux import PayloadMultiplexer
from semantic_img_comp.utils.coco import load_coco_annotations
from semantic_img_comp.utils.load import load_yolo_model
from semantic_img_comp.utils.preprocessing import bboxes_to_mask, clear_bboxes_in_mask, crop_boxes_with_margin, del_obj_from_bg, select_canny_edge_det
from semantic_img_comp.utils.yolo_wrapper import run_yolo
from semantic_img_comp.integration.dlstreamer_client import (
    build_client_from_config as build_dlstreamer_client,
    run_dlstreamer_detect,
)


LOGGER = logging.getLogger(__name__)
MASK_REQUIRED_ENCODERS = frozenset({"mono-28bit", "mono-18bit", "mono-mask-1bit", "color-28bit"})
BG_BBOX_SKIP_SUPPORTED_ENCODERS = frozenset({"mono-2bit", "mono-2bit-mixed-n1bit", "mono-2bit-template-drop1bit", "mono-8bit-template-drop1bit", "mono-mask-1bit"})
SPARSE_OVERLAY_OBJECT_ENCODERS = frozenset({"mono-skel-v1", "mono-shape-v1", "airplane-symbol-v1"})
NON_MASK_CODEC_DISPATCH = {
    "color-4bit": encoder_codecs.encode_color_4bit,
    "mono-4bit": encoder_codecs.encode_mono_4bit,
    "color-2bit": encoder_codecs.encode_color_2bit,
    "mono-2bit": encoder_codecs.encode_mono_2bit,
    "mono-2bit-mixed-n1bit": encoder_codecs.encode_mono_2bit_mixed_n1bit,
    "mono-2bit-template-drop1bit": encoder_codecs.encode_mono_2bit_template_drop1bit,
    "mono-8bit-template-drop1bit": encoder_codecs.encode_mono_8bit_template_drop1bit,
    "mono-skel-v1": encoder_codecs.encode_mono_skel_v1,
    "mono-shape-v1": encoder_codecs.encode_mono_shape_v1,
    "airplane-symbol-v1": encoder_codecs.encode_airplane_symbol_v1,
}
MASKED_CODEC_DISPATCH = {
    "mono-28bit": encoder_codecs.encode_mono_28bit,
    "mono-18bit": encoder_codecs.encode_mono_18bit,
    "mono-mask-1bit": encoder_codecs.encode_mono_mask_1bit,
    "color-28bit": encoder_codecs.encode_color_28bit,
}



class Encoder:
    """Encoder for object extraction, image compression, payload muxing, and transport."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.skip_obj_detection = bool(getattr(cfg.model, "skip_obj_detection", False))
        self.detector_backend = str(getattr(cfg.model, "detector_backend", "yolo")).strip().lower()
        self.yolo = None
        self.dlstreamer_client = None
        if self.skip_obj_detection:
            LOGGER.info("Skipping detector model initialization (skip_obj_detection=true)")
        elif self.detector_backend == "dlstreamer":
            LOGGER.info(
                "Using DL Streamer Pipeline Server for object detection (base_url=%s, pipeline=%s)",
                cfg.model.dlstreamer_base_url,
                cfg.model.dlstreamer_pipeline_name,
            )
            self.dlstreamer_client = build_dlstreamer_client(cfg)
        else:
            LOGGER.info("Loading detector model from %s", cfg.model.enc_yolo_model_path)
            self.yolo, _ = load_yolo_model(cfg.model.enc_yolo_model_path, device=cfg.app.device)
        # RT-DETR is intentionally not initialized here because the production
        # encoder path uses YOLO and eager HF model loading adds significant
        # startup cost and an avoidable runtime dependency.
        self.rtdetr_processor = None
        self.rtdetr_model = None

    @staticmethod
    def carve_out_objs(pil_img: Image.Image, crops: List[ObjData]) -> Image.Image:
        """Remove detected object regions from image for background-only processing."""

        for crop in crops:
            pil_img = del_obj_from_bg(pil_img, crop.bbox)

        return pil_img

    @staticmethod
    def _resize_image(
        img: Image.Image,
        scale_percent: int,
        *,
        resample: Image.Resampling = Image.Resampling.BICUBIC,
    ) -> Image.Image:
        """Resize while guaranteeing at least 1 pixel in each dimension."""
        if scale_percent <= 0:
            raise ValueError(f"scale_percent must be > 0, got {scale_percent}")

        width = max(1, int(img.width * scale_percent / 100))
        height = max(1, int(img.height * scale_percent / 100))
        if width == img.width and height == img.height:
            return img
        return img.resize((width, height), resample=resample)

    @classmethod
    def _resize_mask(cls, mask: Image.Image | None, scale_percent: int) -> Image.Image | None:
        """Resize optional mask with nearest-neighbor interpolation."""
        if mask is None:
            return None
        return cls._resize_image(mask, scale_percent, resample=Image.Resampling.NEAREST)

    @staticmethod
    def _estimate_symbol_theta(img: Image.Image, *, category_id: int) -> float:
        """Estimate per-category symbol heading from crop content."""
        if int(category_id) == 2:
            theta = encoder_codecs.estimate_airplane_nose_theta_deg(img)
        elif int(category_id) == 3:
            theta = encoder_codecs.estimate_vessel_nose_theta_deg(img)
        else:
            theta = None

        if theta is not None:
            return float(theta)
        # Fallback keeps behavior stable when silhouette is too ambiguous.
        return float(encoder_codecs._estimate_major_axis_theta_deg(img))

    def _adjust_symbol_theta(self, theta_deg: float, *, category_id: int) -> float:
        """Apply per-category post-estimation heading offsets.

        Vessel silhouettes can be consistently shifted by 90 degrees depending on
        dataset annotation conventions. Keep this configurable at runtime.
        """
        theta = float(theta_deg) % 360.0
        if int(category_id) == 3:
            vessel_offset = float(getattr(self.cfg.img_process, "vessel_theta_offset_deg", 90.0))
            theta = (theta + vessel_offset) % 360.0
        return theta

    @staticmethod
    def _resolve_skip_bg_fallback(enc_tag: dict[str, int]) -> tuple[str, int]:
        """Pick fallback codec when skip_bg is reached with no detected objects."""
        items = list(enc_tag.items())
        skip_idx = next((idx for idx, (name, _) in enumerate(items) if name == "skip_bg"), None)
        if skip_idx is None:
            raise ValueError("skip_bg must exist in encoder tag map to resolve fallback")

        # Prefer the codec immediately before skip_bg in priority order.
        if skip_idx > 0:
            return items[skip_idx - 1]

        # If skip_bg is first, pick the first configured non-skip codec.
        next_codec = next(((name, idx) for name, idx in items if name != "skip_bg"), None)
        if next_codec is not None:
            return next_codec

        raise ValueError(
            "encoders_tag_bg cannot contain only skip_bg when frames may have no objects; "
            "add at least one real background codec before/after skip_bg"
        )

    def _resolve_fast_bg_encoder(self, enc_tag: dict[str, int], has_objects: bool) -> tuple[str, int]:
        """Resolve fast-path background codec from enc_tag.

        Fast path always picks the last codec in priority order.
        """
        _ = has_objects
        return next(reversed(enc_tag.items()))

    def _build_edge_mask(self, img: Image.Image) -> Image.Image:
        """Build mask using selected canny mode and related tuning fields."""
        return select_canny_edge_det(
            img,
            mode=getattr(self.cfg.img_process, "canny_mode", "old"),
            canny_sigma=float(getattr(self.cfg.img_process, "canny_sigma", 1.0)),
            canny_low=int(getattr(self.cfg.img_process, "canny_low", 12)),
            canny_high=int(getattr(self.cfg.img_process, "canny_high", 45)),
            canny_deriche_bilateral_d=int(getattr(self.cfg.img_process, "canny_deriche_bilateral_d", 9)),
            canny_deriche_bilateral_sigma_color=float(getattr(self.cfg.img_process, "canny_deriche_bilateral_sigma_color", 60.0)),
            canny_deriche_bilateral_sigma_space=float(getattr(self.cfg.img_process, "canny_deriche_bilateral_sigma_space", 60.0)),
            canny_deriche_gaussian_sigma=float(getattr(self.cfg.img_process, "canny_deriche_gaussian_sigma", 2.0)),
            canny_deriche_morph_close_kernel=int(getattr(self.cfg.img_process, "canny_deriche_morph_close_kernel", 7)),
            canny_deriche_morph_close_iterations=int(getattr(self.cfg.img_process, "canny_deriche_morph_close_iterations", 2)),
        )

    def _resolve_object_encoder_name(self, encoder_index: int | None) -> str | None:
        """Resolve an object encoder index to its configured codec name.

        Background bbox-skip decisions must mirror decoder behavior. Some object
        indices (for example mono-mask-1bit fallback when symbol mode is active)
        may not exist in the active per-level object tag map, so fall back to the
        unified ``img_process.encoders_tag`` registry when needed.
        """
        if encoder_index is None:
            return None

        tags = self._get_active_obj_encoder_tags()
        enc_name = next((name for name, idx in tags.items() if idx == encoder_index), None)
        if enc_name is not None:
            return enc_name

        full_tags = getattr(getattr(self.cfg, "img_process", None), "encoders_tag", None) or {}
        return next((name for name, idx in full_tags.items() if idx == encoder_index), None)

    def _get_selected_compression_level(self) -> int:
        """Return the configured compression level when no active runtime map is set."""
        return int(getattr(getattr(self.cfg, "pipeline_manager", None), "compression_level", 1))

    def _get_active_bg_encoder_tags(self) -> dict[str, int]:
        """Return runtime-selected background encoder tags for the current image."""
        img_process = getattr(self.cfg, "img_process", None)
        if img_process is None:
            raise ValueError("cfg.img_process is required")

        active = getattr(img_process, "active_encoders_tag_bg", None)
        if active:
            return dict(active)

        level = self._get_selected_compression_level()
        level_tags = getattr(img_process, f"encoders_tag_bg_level_{level}", None)
        if level_tags:
            return dict(level_tags)

        raise ValueError("No active background encoder tags configured for the selected compression level")

    def _get_active_obj_encoder_tags(self) -> dict[str, int]:
        """Return runtime-selected object encoder tags for the current image."""
        img_process = getattr(self.cfg, "img_process", None)
        if img_process is None:
            raise ValueError("cfg.img_process is required")

        active = getattr(img_process, "active_encoders_tag_objs", None)
        if active:
            return dict(active)

        level = self._get_selected_compression_level()
        level_tags = getattr(img_process, f"encoders_tag_objs_level_{level}", None)
        if level_tags:
            return dict(level_tags)

        raise ValueError("No active object encoder tags configured for the selected compression level")

    def _get_active_scaling_value(self, base_name: str) -> int:
        """Return a runtime-selected scaling value for the current compression level."""
        img_process = getattr(self.cfg, "img_process", None)
        if img_process is None:
            raise ValueError("cfg.img_process is required")

        active_value = getattr(img_process, f"active_{base_name}", None)
        if active_value is not None:
            return int(active_value)

        level = self._get_selected_compression_level()
        level_value = getattr(img_process, f"{base_name}_level_{level}", None)
        if level_value is not None:
            return int(level_value)

        raise ValueError(f"No active scaling value configured for '{base_name}' at compression level {level}")

    def _get_bg_skippable_bboxes(self, crops: List[ObjData]) -> list[tuple[int, int, int, int]]:
        """Return expanded object bboxes that are safe to omit from background encoding."""
        if not bool(getattr(self.cfg.img_process, "skip_object_bboxes_in_background", False)):
            return []

        skippable: list[tuple[int, int, int, int]] = []
        for crop in crops:
            bbox = getattr(crop, "expanded_bbox", None)
            if bbox is None:
                continue

            enc_name = self._resolve_object_encoder_name(getattr(crop, "encoder_index", None))
            if enc_name is None or enc_name in SPARSE_OVERLAY_OBJECT_ENCODERS:
                continue

            x1, y1, x2, y2 = bbox
            skippable.append((int(x1), int(y1), int(x2), int(y2)))

        return skippable

    def _prepare_background_inputs(
        self,
        pil_img: Image.Image,
        *,
        enc_name: str,
        crops: List[ObjData],
        mask: Image.Image | None = None,
        skip_mask: Image.Image | None = None,
    ) -> tuple[Image.Image, Image.Image | None, Image.Image | None]:
        """Prepare background image/mask inputs for a specific codec attempt."""
        skippable_bboxes = self._get_bg_skippable_bboxes(crops)
        if not skippable_bboxes or enc_name not in BG_BBOX_SKIP_SUPPORTED_ENCODERS:
            return pil_img, mask, None

        if skip_mask is None:
            skip_mask = bboxes_to_mask(pil_img.size, skippable_bboxes, fill=255)

        if enc_name in {"mono-2bit", "mono-2bit-mixed-n1bit", "mono-2bit-template-drop1bit", "mono-8bit-template-drop1bit"}:
            return pil_img, None, skip_mask

        if enc_name == "mono-mask-1bit":
            if mask is None:
                mask = self._build_edge_mask(pil_img)
            mask = clear_bboxes_in_mask(mask, skippable_bboxes, fill=0)
            return pil_img, mask, skip_mask

        return pil_img, mask, None


    def compress_background(
        self,
        pil_img: Image.Image,
        tar_enc_data_bytes: int,
        crops: List[ObjData],
        *,
        use_fast_path: bool | None = None,
    ) -> tuple[BgData, int]:
        """
        Compress background image with adaptive scale and codec selection.

        Args:
            pil_img: Raw frame image.
            tar_enc_data_bytes: Target encoded bytes budget for frame payload.
            crops: Encoded object crops already allocated budget.

        Returns:
            Tuple of encoded background object and target background budget bytes.
        """
        bg = BgData(pil=pil_img)

        total_objs_bytes = sum(len(c.encoded_obj or b"") for c in crops)

        tar_bg_bytes = max(tar_enc_data_bytes - total_objs_bytes, self.cfg.enc.min_bg_bytes)

        enc_tag = self._get_active_bg_encoder_tags()
        if not enc_tag:
            raise ValueError("Active background encoder tag map must not be empty")

        last_encoder_name = next(reversed(enc_tag))

        mask = None
        skip_mask = None
        min_scale = (
            self._get_active_scaling_value("bg_scaling_min2")
            if crops
            else self._get_active_scaling_value("bg_scaling_min1")
        )
        max_scale = self._get_active_scaling_value("bg_scaling_max")

        has_objects = bool(crops)

        # ------------------------------------------------------------------
        # Fast path: max_iter_bg == 0 → skip binary search, encode at fixed
        # scale (level-selected bg_scaling_min1 when no objects, bg_scaling_min2 otherwise).
        # ------------------------------------------------------------------
        max_iter_bg = int(self.cfg.enc.max_iter_bg)
        if use_fast_path is None:
            use_fast_path = max_iter_bg == 0

        if use_fast_path:
            fast_enc_name, fast_enc_idx = self._resolve_fast_bg_encoder(enc_tag, has_objects)
            if fast_enc_name == "skip_bg":
                if has_objects:
                    bg.pil = pil_img
                    bg.scaled_size = pil_img.size
                    bg.scaling_factor = 100
                    bg.encoded_data = b""
                    bg.encoder_index = fast_enc_idx
                    return bg, tar_bg_bytes
                else:
                    fast_enc_name, fast_enc_idx = self._resolve_skip_bg_fallback(enc_tag)

            # Encoding-agnostic estimate: assume bytes scale ~ pixels ~ (scale^2)
            target_rate = max(float(self.cfg.enc.compression_rate), 1.0)
            scale_from_rate = int(round(100.0 / math.sqrt(target_rate)))
            fixed_scale = max(min_scale, min(max_scale, scale_from_rate))

            fast_mask = None
            if fast_enc_name in MASK_REQUIRED_ENCODERS:
                fast_mask = self._build_edge_mask(pil_img)
            bg_encode_img, fast_mask, fast_skip_mask = self._prepare_background_inputs(
                pil_img,
                enc_name=fast_enc_name,
                crops=crops,
                mask=fast_mask,
                skip_mask=skip_mask,
            )
            img_resized = self._resize_image(bg_encode_img, scale_percent=fixed_scale)
            fast_mask = self._resize_mask(fast_mask, scale_percent=fixed_scale)
            fast_skip_mask = self._resize_mask(fast_skip_mask, scale_percent=fixed_scale)
            encode_kwargs = {
                "encoder": fast_enc_name,
                "mask": fast_mask,
            }
            if fast_skip_mask is not None:
                encode_kwargs["skip_mask"] = fast_skip_mask
            enc_bytes = self.encode_img(img_resized, **encode_kwargs)
            bg.pil = img_resized
            bg.scaled_size = img_resized.size
            bg.scaling_factor = fixed_scale
            bg.encoded_data = enc_bytes
            bg.encoder_index = fast_enc_idx
            return bg, tar_bg_bytes

        # ------------------------------------------------------------------
        # Normal path: iterative binary search across codecs.
        # ------------------------------------------------------------------
        for enc_name, enc_idx in enc_tag.items():
            force_accept = False
            if enc_name == "skip_bg" and not has_objects:
                # Do not emit an empty frame when there are no objects.
                enc_name, enc_idx = self._resolve_skip_bg_fallback(enc_tag)
                force_accept = True
            elif enc_name == "skip_bg":
                # Background-only no-op codec: intentionally send no bg bytes.
                bg.pil = pil_img
                bg.scaled_size = pil_img.size
                bg.scaling_factor = 100
                bg.encoded_data = b""
                bg.encoder_index = enc_idx
                break

            if enc_name in MASK_REQUIRED_ENCODERS and mask is None:
                mask = self._build_edge_mask(pil_img)

            bg_encode_img, bg_mask, bg_skip_mask = self._prepare_background_inputs(
                pil_img,
                enc_name=enc_name,
                crops=crops,
                mask=mask,
                skip_mask=skip_mask,
            )

            search_result = self._find_scale_for_budget(
                bg_encode_img,
                budget_bytes=tar_bg_bytes,
                min_scale_percent=min_scale,
                max_scale_percent=max_scale,
                iters=max(1, max_iter_bg),
                encoder=enc_name,
                min_pixels=min(pil_img.width * pil_img.height, self.cfg.enc.min_bg_pixels),
                mask=bg_mask,
                skip_mask=bg_skip_mask,
            )
            scale, size_bytes, enc_bytes = search_result

            if size_bytes <= tar_bg_bytes or enc_name == last_encoder_name or force_accept:
                bg.pil = self._resize_image(bg_encode_img, scale_percent=scale)
                bg.scaled_size = bg.pil.size
                bg.scaling_factor = scale
                bg.encoded_data = enc_bytes
                bg.encoder_index = enc_idx

                break


        return bg, tar_bg_bytes

    def extract_objs_from_annot(self, pil_img: Image.Image, annot_path: Path) -> List[ObjData]:
        """Build object crops directly from a YOLO-style annotation file, bypassing YOLO inference.

        The annotation file must contain one detection per line in the format::

            class_id  cx  cy  w  h

        where all coordinates are normalized to [0, 1] relative to the image dimensions.
        Lines that are empty or start with ``#`` are ignored.

        Args:
            pil_img:    Input raw image.
            annot_path: Path to the corresponding YOLO-style ``.txt`` annotation file.

        Returns:
            List of crop records with bbox metadata (``det_conf`` is set to 1.0).
        """
        W, H = pil_img.size
        dets = []

        with open(annot_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 5:
                    LOGGER.warning("Skipping malformed annotation line in %s: %r", annot_path, line)
                    continue
                cls_id = int(parts[0])
                cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                x1 = (cx - bw / 2) * W
                y1 = (cy - bh / 2) * H
                x2 = (cx + bw / 2) * W
                y2 = (cy + bh / 2) * H
                dets.append((x1, y1, x2, y2, 1.0, cls_id))

        objs_pils, boxes, expanded_boxes = crop_boxes_with_margin(
            pil_img, dets, self.cfg.img_process.additional_crop_margin
        )

        crops: List[ObjData] = []
        for idx, obj_pil in enumerate(objs_pils):
            crop_data = ObjData(
                obj_pil=obj_pil,
                obj_size=obj_pil.size,
                bbox=boxes[idx],
                expanded_bbox=expanded_boxes[idx],
                category_id=dets[idx][5],
                det_conf=dets[idx][4],
            )
            crops.append(crop_data)

        return crops

    def extract_objs(self, pil_img: Image.Image, img_name: str | None = None) -> List[ObjData]:
        """Detect and crop objects from an image.

        Args:
            pil_img: Input raw image.
            img_name: Optional source file name, used only for diagnostics/log messages.

        Returns:
            List of crop records with detection metadata.
        """
        if self.skip_obj_detection:
            return []

        # -------------------------
        # PERFORM OBJECT DETECTIONS
        # -------------------------
        if self.detector_backend == "dlstreamer":
            # Detection runs remotely via DL Streamer Pipeline Server (gvadetect);
            # tile_size/imgsz are YOLO-tiling knobs and don't apply to this backend.
            orig_dets = run_dlstreamer_detect(pil_img, self.cfg, client=self.dlstreamer_client)
        else:
            orig_dets = run_yolo(
                pil_img,
                self.yolo,
                self.cfg,
                tile_size=self.cfg.model.tile_size,
                imgsz=self.cfg.performance.image_size,
            )

        # orig_dets = run_rtdetr(
        #     pil_img,
        #     self.rtdetr_processor,
        #     self.rtdetr_model,
        #     score_thresh=self.cfg.model.score_thresh,
        #     allowed_classes=self.cfg.model.valid_obj_categories
        # )

        # -------------------------
        # ENFORCE MAX DETECTIONS CAP
        # -------------------------
        # The YOLO backend already caps output at the source via `max_det`, but
        # the DL Streamer backend (gvadetect) returns every detection above the
        # confidence threshold with no count limit. The wire protocol's
        # `fmt_crops_count` field and the decoder's demux validation both cap
        # `num_crops` at `cfg.model.max_detections`, so an uncapped detection
        # list here would produce a payload the decoder rejects as malformed.
        # Keep the highest-confidence detections when truncation is needed, to
        # match YOLO's own confidence-based selection when it hits max_det.
        max_detections = getattr(self.cfg.model, "max_detections", None)
        if max_detections is not None and len(orig_dets) > max_detections:
            LOGGER.warning(
                "\nextract_objs: image '%s' has %d detections exceeding max_detections=%d; "
                "keeping the %d highest-confidence detections",
                img_name or "<unknown>", len(orig_dets), max_detections, max_detections,
            )
            orig_dets = sorted(orig_dets, key=lambda d: d[4], reverse=True)[:max_detections]

        # -------------------------
        # CROP DETECTIONS
        # -------------------------
        objs_pils, boxes, expanded_boxes = crop_boxes_with_margin(
            pil_img, orig_dets, self.cfg.img_process.additional_crop_margin
        )

        crops: List[ObjData] = []
        for idx, obj_pil in enumerate(objs_pils):
            crop_data = ObjData(
                obj_pil=obj_pil,
                obj_size=obj_pil.size,
                bbox=boxes[idx],
                expanded_bbox=expanded_boxes[idx],
                category_id=orig_dets[idx][5],
                det_conf=orig_dets[idx][4],
            )
            crops.append(crop_data)

        return crops


    def set_tar_objs_bytes(self, org_jpeg_bytes: int, num_objs: int = 0) -> tuple[int, int]:
        """Compute target bytes for object payload and total encoded payload.

        Args:
            org_jpeg_bytes: Source image size in JPEG bytes.
            num_objs: Number of detected object crops.

        Returns:
            Tuple ``(tar_objs_bytes, tar_enc_data_bytes)``.

        Notes:
            Uses ``cfg.enc.compression_rate`` to derive payload budget from source
            JPEG size before accounting for mux overhead.
        """
        overhead_bg, overhead_per_crop = self.cfg.mux_cfg.header_fields_total_bytes()
        overhead = overhead_bg + num_objs * overhead_per_crop
        total_tar_payload_bytes = org_jpeg_bytes / self.cfg.enc.compression_rate
        tar_enc_data_bytes = int(total_tar_payload_bytes - overhead)

        if tar_enc_data_bytes <= 0:
            tar_enc_data_bytes = self.cfg.enc.min_bytes_for_encoded_data

        tar_objs_bytes = int(tar_enc_data_bytes * self.cfg.enc.obj_budget_ratio)

        LOGGER.debug(
            "set_tar_objs_bytes: org_jpeg_bytes=%d, comp_rate=%.1f, overhead_bg=%d, "
            "overhead_per_crop=%d, num_objs=%d, total_overhead=%d, "
            "total_tar_payload=%.2f, tar_enc_data_bytes=%d, obj_budget_ratio=%.2f, tar_objs_bytes=%d",
            org_jpeg_bytes, self.cfg.enc.compression_rate, overhead_bg, overhead_per_crop, num_objs,
            overhead, total_tar_payload_bytes, tar_enc_data_bytes, self.cfg.enc.obj_budget_ratio, tar_objs_bytes
        )

        return tar_objs_bytes, tar_enc_data_bytes

    def compress_objs(
        self,
        crops: List[ObjData],
        tar_objs_bytes: int,
        *,
        use_fast_path: bool | None = None,
    ) -> List[ObjData]:
        """
        Compress detected object crops and populate encoded fields.

        Args:
            crops: Detected object crops.
            tar_objs_bytes: Target byte budget for all object crops.

        Returns:
            Updated crops with encoder metadata and encoded bytes.
        """

        if len(crops) == 0:
            return crops

        budgets = self._allocate_budgets_by_pixels(
            [c.obj_pil for c in crops],
            total_bytes=tar_objs_bytes,
            min_bytes=self.cfg.enc.min_bytes_for_budget_allocation,
            soft_budget=self.cfg.enc.object_budget_soft,
        )

        enc_tag = self._get_active_obj_encoder_tags()
        if not enc_tag:
            raise ValueError("Active object encoder tag map must not be empty")

        symbol_idx = enc_tag.get("airplane-symbol-v1")
        fallback_mask_idx = enc_tag.get("mono-mask-1bit")

        # If mono-mask-1bit not in active encoder tags, look it up from unified encoders_tag registry
        # (decoder has access to full list and can fall back to mono-mask-1bit)
        if fallback_mask_idx is None:
            full_tags = getattr(self.cfg.img_process, "encoders_tag", None)
            if full_tags:
                fallback_mask_idx = full_tags.get("mono-mask-1bit")

        symbol_category_ids = set(getattr(getattr(self.cfg, "model", None), "symbol_category_ids", {4, 8}))

        # When symbol mode is enabled, categories 2/3 use symbol payload; others fall back to mono-mask-1bit.
        # No error needed - decoder has access to full encoder tag list for fallback.
        if symbol_idx is not None and fallback_mask_idx is None:
            raise ValueError("mono-mask-1bit must be configured in encoders_tag for airplane-symbol-v1 non-symbol fallback")

        last_encoder_name = next(reversed(enc_tag))

        max_iter_obj = int(self.cfg.enc.max_iter_obj)
        if use_fast_path is None:
            use_fast_path = max_iter_obj == 0

        # ------------------------------------------------------------------
        # Fast path: max_iter_obj == 0 -> skip scale search and encode with
        # fixed scale for the selected per-object codec.
        # ------------------------------------------------------------------
        if use_fast_path:
            fixed_scale_default = self._get_active_scaling_value("obj_scaling_min")
            fast_default_enc_name, fast_default_enc_idx = next(reversed(enc_tag.items()))
            for crop in crops:
                category_id = int(getattr(crop, "category_id", -1))

                # Fast path follows configured priority: pick the last object codec.
                fast_enc_name = fast_default_enc_name
                fast_enc_idx = fast_default_enc_idx

                # If the selected fast codec is symbol, non-symbol categories fall back to mask.
                if fast_enc_name == "airplane-symbol-v1" and category_id not in symbol_category_ids:
                    fast_enc_name = "mono-mask-1bit"
                    fast_enc_idx = fallback_mask_idx

                if fast_enc_name == "airplane-symbol-v1":
                    theta_deg = self._estimate_symbol_theta(crop.obj_pil, category_id=category_id)
                    theta_deg = self._adjust_symbol_theta(theta_deg, category_id=category_id)
                    enc_bytes = self.encode_img(
                        crop.obj_pil,
                        encoder="airplane-symbol-v1",
                        category_id=category_id,
                        theta_deg=theta_deg,
                    )
                    # Symbol payload is orientation-driven (no resize search), so log scaling as None.
                    crop.scaling_factor = None
                    crop.obj_size_scaled = crop.obj_pil.size
                    crop.encoded_obj = enc_bytes
                    crop.encoder_index = fast_enc_idx
                    continue


                fixed_scale = 100 if fast_enc_name == "airplane-symbol-v1" else fixed_scale_default
                img_resized = self._resize_image(crop.obj_pil, scale_percent=fixed_scale)
                fast_mask = None
                if fast_enc_name in MASK_REQUIRED_ENCODERS:
                    fast_mask = self._build_edge_mask(crop.obj_pil)
                    fast_mask = self._resize_mask(fast_mask, scale_percent=fixed_scale)
                enc_bytes = self.encode_img(img_resized, encoder=fast_enc_name, mask=fast_mask)
                crop.scaling_factor = fixed_scale
                crop.obj_pil = img_resized
                crop.obj_size_scaled = img_resized.size
                crop.encoded_obj = enc_bytes
                crop.encoder_index = fast_enc_idx

            return crops

        for crop, budget in zip(crops, budgets):
            category_id = int(getattr(crop, "category_id", -1))

            mask = None
            for enc_name, enc_idx in list(enc_tag.items()):
                if enc_name in MASK_REQUIRED_ENCODERS and mask is None:
                    mask = self._build_edge_mask(crop.obj_pil)

                if enc_name == "airplane-symbol-v1":
                    if category_id in symbol_category_ids:
                        # Symbol path: always accept (orientation-driven, fixed-size payload).
                        theta_deg = self._estimate_symbol_theta(crop.obj_pil, category_id=category_id)
                        theta_deg = self._adjust_symbol_theta(theta_deg, category_id=category_id)
                        enc_bytes = self.encode_img(
                            crop.obj_pil,
                            encoder="airplane-symbol-v1",
                            category_id=category_id,
                            theta_deg=theta_deg,
                        )
                        crop.scaling_factor = None
                        crop.obj_size_scaled = crop.obj_pil.size
                        crop.encoded_obj = enc_bytes
                        crop.encoder_index = enc_idx
                        break
                    else:
                        # Non-symbol category at symbol slot: fall back to mono-mask-1bit.
                        if mask is None:
                            mask = self._build_edge_mask(crop.obj_pil)
                        scale, _, enc_bytes = self._find_scale_for_budget(
                            crop.obj_pil,
                            budget_bytes=budget,
                            min_scale_percent=self._get_active_scaling_value("obj_scaling_min"),
                            max_scale_percent=self._get_active_scaling_value("obj_scaling_max"),
                            iters=max(1, max_iter_obj),
                            encoder="mono-mask-1bit",
                            min_pixels=self.cfg.enc.min_obj_pixels,
                            mask=mask,
                        )
                        crop.scaling_factor = scale
                        crop.obj_pil = self._resize_image(crop.obj_pil, scale_percent=scale)
                        crop.obj_size_scaled = crop.obj_pil.size
                        crop.encoded_obj = enc_bytes
                        crop.encoder_index = fallback_mask_idx
                        break
                else:
                    search_result = self._find_scale_for_budget(
                        crop.obj_pil,
                        budget_bytes=budget,
                        min_scale_percent=self._get_active_scaling_value("obj_scaling_min"),
                        max_scale_percent=self._get_active_scaling_value("obj_scaling_max"),
                        iters=max(1, max_iter_obj),
                        encoder=enc_name,
                        min_pixels=self.cfg.enc.min_obj_pixels,
                        mask=mask,
                    )
                    scale, size_bytes, enc_bytes = search_result

                    if size_bytes <= budget or enc_name == last_encoder_name:
                        crop.scaling_factor = scale
                        crop.obj_pil = self._resize_image(crop.obj_pil, scale_percent=scale)
                        crop.obj_size_scaled = crop.obj_pil.size
                        crop.encoded_obj = enc_bytes
                        crop.encoder_index = enc_idx
                        break


        return crops

    @staticmethod
    def _allocate_budgets_by_pixels(
        images: List[Image.Image],
        total_bytes: int,
        *,
        min_bytes: int,
        soft_budget: bool = True,
    ) -> List[int]:
        """Allocate per-image object budgets proportionally by pixel count.

        Note:
            By default allocation is intentionally *soft*. The ``min_bytes`` floor is
            applied per image first, so the sum of returned budgets can exceed
            ``total_bytes`` when many small crops are present.
        """
        pixels = [img.width * img.height for img in images]
        s = sum(pixels) or 1

        budgets = [max(min_bytes, int(total_bytes * p / s)) for p in pixels]
        allocated = sum(budgets)
        if allocated > total_bytes:
            LOGGER.debug(
                "Object budget oversubscribed due to min_bytes floor: total=%d allocated=%d min_bytes=%d num_images=%d",
                total_bytes,
                allocated,
                min_bytes,
                len(images),
            )

        if not soft_budget and allocated > total_bytes:
            order = sorted(range(len(images)), key=lambda i: pixels[i], reverse=True)
            idx = 0
            while allocated > total_bytes and idx < len(order) * max(1, total_bytes):
                i = order[idx % len(order)]
                if budgets[i] > min_bytes:
                    budgets[i] -= 1
                    allocated -= 1
                idx += 1

        return budgets

    def _find_scale_for_budget(
        self,
        img: Image.Image,
        *,
        budget_bytes: int,
        min_scale_percent: int,
        max_scale_percent: int,
        iters: int,
        encoder: str,
        min_pixels: int,
        mask=None,
        skip_mask=None,
    ) -> tuple[int, int, bytes]:
        """
        Find scale percent for budget-constrained encoding with pixel floor.

        Resize scale is a percent of original linear dimensions:
        - ``scale_percent=50`` means width/height ~50% and pixels ~25%.

        Goals (priority order):
        1) ``total_pixels_post_resize >= min_pixels`` (hard)
        2) ``encoded_size_bytes <= budget_bytes`` (best effort)

        """
        if budget_bytes <= 0:
            raise ValueError(f"budget_bytes must be > 0, got {budget_bytes}")
        if min_scale_percent <= 0 or max_scale_percent <= 0:
            raise ValueError("scale bounds must be > 0")
        if min_scale_percent > max_scale_percent:
            raise ValueError("min_scale_percent must be <= max_scale_percent")

        needs_mask = encoder in MASK_REQUIRED_ENCODERS
        if needs_mask and mask is None:
            raise ValueError(f"Encoder '{encoder}' requires a non-null mask")

        orig_pixels = img.width * img.height

        # If min_pixels is impossible to meet (larger than original), choose max_scale_percent.
        if min_pixels >= orig_pixels:
            img_resized = self._resize_image(img, max_scale_percent)
            mask_resized = self._resize_mask(mask, scale_percent=max_scale_percent) if needs_mask else None
            skip_mask_resized = self._resize_mask(skip_mask, scale_percent=max_scale_percent) if skip_mask is not None else None
            encode_kwargs = {"encoder": encoder, "mask": mask_resized}
            if skip_mask_resized is not None:
                encode_kwargs["skip_mask"] = skip_mask_resized
            enc_bytes = self.encode_img(img_resized, **encode_kwargs)
            return max_scale_percent, len(enc_bytes), enc_bytes

        # Minimum linear scale needed so that resized_pixels ~= orig_pixels*(s/100)^2 >= min_pixels.
        required_scale = int(math.ceil(100.0 * math.sqrt(min_pixels / orig_pixels)))

        # Enforce both caller-provided bounds and pixel feasibility.
        effective_min = max(min_scale_percent, required_scale)
        effective_max = max_scale_percent

        # If pixel constraint can't be met within [min_scale_percent, max_scale_percent],
        # pixel priority => return the largest scale we are allowed to use.
        if effective_min > effective_max:
            img_resized = self._resize_image(img, effective_max)
            mask_resized = self._resize_mask(mask, scale_percent=effective_max) if needs_mask else None
            enc_bytes = self.encode_img(img_resized, encoder=encoder, mask=mask_resized)
            return effective_max, len(enc_bytes), enc_bytes

        if effective_min == effective_max:
            img_resized = self._resize_image(img, effective_min)
            mask_resized = self._resize_mask(mask, scale_percent=effective_min) if needs_mask else None
            skip_mask_resized = self._resize_mask(skip_mask, scale_percent=effective_min) if skip_mask is not None else None
            encode_kwargs = {"encoder": encoder, "mask": mask_resized}
            if skip_mask_resized is not None:
                encode_kwargs["skip_mask"] = skip_mask_resized
            enc_bytes = self.encode_img(img_resized, **encode_kwargs)
            return effective_min, len(enc_bytes), enc_bytes

        # Binary search for largest scale in [effective_min, effective_max] with encoded size <= budget.
        lo, hi = effective_min, effective_max
        best_scale = None
        best_size_bytes = None
        best_encoded_bytes = None
        last_scale = None
        last_size_bytes = None
        last_encoded_bytes = None
        step_size = self.cfg.enc.scale_search_step_size

        for _ in range(max(1, iters)):
            mid = (lo + hi) // 2

            img_resized = self._resize_image(img, mid)
            total_pixels_post_resize = img_resized.width * img_resized.height

            # Safety: due to integer rounding in resize, ensure we still meet pixel constraint.
            if total_pixels_post_resize < min_pixels:
                lo = max(lo, mid + step_size)
                continue

            mask_resized = self._resize_mask(mask, mid) if needs_mask else None
            skip_mask_resized = self._resize_mask(skip_mask, mid) if skip_mask is not None else None
            encode_kwargs = {"encoder": encoder, "mask": mask_resized}
            if skip_mask_resized is not None:
                encode_kwargs["skip_mask"] = skip_mask_resized
            enc_bytes = self.encode_img(img_resized, **encode_kwargs)
            size_bytes = len(enc_bytes)
            last_scale = mid
            last_size_bytes = size_bytes
            last_encoded_bytes = enc_bytes

            if size_bytes <= budget_bytes:
                best_scale = mid
                best_size_bytes = size_bytes
                best_encoded_bytes = enc_bytes
                lo = mid + step_size  # try larger (more pixels) while staying under budget
            else:
                hi = mid - step_size  # need smaller to reduce bytes

            if lo > hi:
                break

        if best_scale is not None:
            return best_scale, best_size_bytes, best_encoded_bytes

        if last_scale == effective_min and last_size_bytes is not None and last_encoded_bytes is not None:
            return effective_min, last_size_bytes, last_encoded_bytes

        # Nothing met the byte budget while satisfying min_pixels.
        # Pixel constraint has priority => return smallest pixel-feasible scale (effective_min).
        img_resized = self._resize_image(img, effective_min)
        mask_resized = self._resize_mask(mask, effective_min) if needs_mask else None
        skip_mask_resized = self._resize_mask(skip_mask, effective_min) if skip_mask is not None else None
        encode_kwargs = {"encoder": encoder, "mask": mask_resized}
        if skip_mask_resized is not None:
            encode_kwargs["skip_mask"] = skip_mask_resized
        enc_bytes = self.encode_img(img_resized, **encode_kwargs)
        return effective_min, len(enc_bytes), enc_bytes


    def encode_img(
        self,
        img: Image.Image,
        encoder: str = 'color-avif',
        mask=None,
        skip_mask=None,
        *,
        category_id: int | None = None,
        theta_deg: float | None = None,
    ) -> bytes:
        """Encode a PIL image with one of the configured semantic codecs.

        Args:
            img: PIL image to encode.
            encoder: Encoder key from the currently active per-image encoder tag map.
            mask: Optional edge/structure mask required by mask-aware codecs.
            category_id: Optional object category id used by ``airplane-symbol-v1``.
            theta_deg: Optional orientation override used by ``airplane-symbol-v1``.

        Returns:
            Encoded image bytes.

        Raises:
            ValueError: Unsupported encoder or required mask missing.
            RuntimeError: Selected encoder returns no bytes.
        """
        if encoder in MASK_REQUIRED_ENCODERS and mask is None:
            raise ValueError(f"Encoder '{encoder}' requires a non-null mask")
        if encoder == "color-avif":
            enc_bytes = encoder_codecs.encode_avif(
                img,
                quality=self.cfg.enc.avif_quality,
                speed=self.cfg.enc.avif_speed,
                is_monochrome=(img.mode == "L"),  # auto-select YUV400 for L-mode images
                timeout_sec=self.cfg.enc.avif_timeout_sec,
                jobs=getattr(self.cfg.enc, "avif_jobs", None),
                codec=getattr(self.cfg.enc, "avif_codec", None),
            )
        elif encoder in ("mono-avif", "mono-avif-high", "mono-avif-mid", "mono-avif-low"):
            # Convert to 1-channel mono before encoding
            # Determine quality based on encoder variant
            if encoder in self.cfg.enc.avif_mono_quality_map:
                quality = self.cfg.enc.avif_mono_quality_map[encoder]
            else:
                # Fallback for legacy "mono-avif" name or if quality map is incomplete
                quality = self.cfg.enc.avif_quality
            
            enc_bytes = encoder_codecs.encode_avif(
                img.convert("L"),
                quality=quality,
                speed=self.cfg.enc.avif_speed,
                is_monochrome=True,
                timeout_sec=self.cfg.enc.avif_timeout_sec,
                jobs=getattr(self.cfg.enc, "avif_jobs", None),
                codec=getattr(self.cfg.enc, "avif_codec", None),
            )
        elif encoder in NON_MASK_CODEC_DISPATCH:
             zlib_level = int(getattr(self.cfg.enc, "zlib_level", 9))
             if encoder == "airplane-symbol-v1":
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](
                     img,
                     zlib_level=zlib_level,
                     category_id=category_id,
                     theta_deg=theta_deg,
                 )
             elif encoder == "mono-skel-v1":
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](
                     img,
                     zlib_level=zlib_level,
                     max_segments=int(getattr(self.cfg.img_process, "mono_skel_max_segments", 8)),
                     min_segment_length=int(getattr(self.cfg.img_process, "mono_skel_min_segment_length", 5)),
                     hough_threshold=int(getattr(self.cfg.img_process, "mono_skel_hough_threshold", 20)),
                     max_segment_gap=int(getattr(self.cfg.img_process, "mono_skel_max_segment_gap", 2)),
                     work_max_dim=int(getattr(self.cfg.img_process, "mono_skel_work_max_dim", 128)),
                     stitch_angle_tol_deg=float(getattr(self.cfg.img_process, "mono_skel_stitch_angle_tol_deg", 20.0)),
                 )
             elif encoder == "mono-shape-v1":
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](
                     img,
                     zlib_level=zlib_level,
                     max_points=int(getattr(self.cfg.img_process, "mono_shape_max_points", 120)),
                     epsilon_ratio=float(getattr(self.cfg.img_process, "mono_shape_epsilon_ratio", 0.01)),
                 )
             elif encoder == "mono-2bit" and skip_mask is not None:
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](img, zlib_level=zlib_level, skip_mask=skip_mask)
             elif encoder == "mono-2bit-mixed-n1bit":
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](
                     img,
                     zlib_level=zlib_level,
                     two_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_two_bit_run", 4)),
                     one_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_one_bit_run", 1)),
                     skip_mask=skip_mask,
                 )
             elif encoder == "mono-2bit-template-drop1bit":
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](
                     img,
                     zlib_level=zlib_level,
                     two_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_two_bit_run", 4)),
                     one_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_one_bit_run", 1)),
                     skip_mask=skip_mask,
                 )
             elif encoder == "mono-8bit-template-drop1bit":
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](
                     img,
                     zlib_level=zlib_level,
                     two_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_two_bit_run", 4)),
                     one_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_one_bit_run", 1)),
                     skip_mask=skip_mask,
                 )
             else:
                 enc_bytes = NON_MASK_CODEC_DISPATCH[encoder](img, zlib_level=zlib_level)
        elif encoder in MASKED_CODEC_DISPATCH:
            zlib_level = int(getattr(self.cfg.enc, "zlib_level", 9))
            if encoder == "mono-mask-1bit" and skip_mask is not None:
                enc_bytes = MASKED_CODEC_DISPATCH[encoder](img, mask=mask, zlib_level=zlib_level, skip_mask=skip_mask)
            else:
                enc_bytes = MASKED_CODEC_DISPATCH[encoder](img, mask=mask, zlib_level=zlib_level)
        else:
            raise ValueError(f"Unsupported encoder: {encoder}")


        if enc_bytes is None:
            raise RuntimeError(f"Encoder '{encoder}' returned no data")

        return enc_bytes

    def map_img_name_to_id(self) -> dict[str, int]:
        """Build filename-to-image_id mapping from COCO annotations when configured."""
        if self.cfg.io.annot_file:
            coco_gt = load_coco_annotations(self.cfg.io.annot_file)

            img_name_to_id: Dict[str, int] = {
                img["file_name"]: img["id"]
                for img in coco_gt.loadImgs(coco_gt.getImgIds())
            }
        else:
            img_name_to_id: Dict[str, int] = {}

        return img_name_to_id

    def encode_payload(self, img_data: ImgEncData) -> tuple[bytes, dict[str, int]]:
        """Serialize frame metadata, background, and object crops into wire bytes."""
        if img_data is None:
            raise ValueError("img_data must not be None")
        mux = PayloadMultiplexer.from_img_data(img_data, cfg=self.cfg.mux_cfg)
        mux.mux_crops(img_data.crops)
        return mux.finalize()

    def send_frame(self, sock: socket.socket, payload: bytes) -> None:
        """Send one framed payload over TCP using a fixed-size length prefix."""
        if sock is None:
            raise ValueError("sock must not be None")
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError(f"payload must be bytes-like, got {type(payload).__name__}")
        payload = bytes(payload)

        header = struct.pack(self.cfg.mux_cfg.fmt_payload_len, len(payload))
        sock.sendall(header)
        sock.sendall(payload)
