# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: decoder/decoder.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: decoder class.
"""

from typing import Dict
from PIL import Image

from semantic_img_comp.decoder import codecs as decoder_codecs
from semantic_img_comp.utils.preprocessing import bboxes_to_mask
from semantic_img_comp.utils.coco import load_coco_annotations


# Codec dispatch tables for clean routing to decoder implementations
AVIF_DECODERS = frozenset({"color-avif", "mono-avif", "mono-avif-high", "mono-avif-mid", "mono-avif-low"})
AVIF_CODEC_DISPATCH = {
    "color-avif": lambda data, **kw: decoder_codecs.decode_avif(data, color=True, **kw),
    "mono-avif": lambda data, **kw: decoder_codecs.decode_avif(data, color=False, **kw),
    "mono-avif-high": lambda data, **kw: decoder_codecs.decode_avif(data, color=False, **kw),
    "mono-avif-mid": lambda data, **kw: decoder_codecs.decode_avif(data, color=False, **kw),
    "mono-avif-low": lambda data, **kw: decoder_codecs.decode_avif(data, color=False, **kw),
}
NON_MASK_CODEC_DISPATCH = {
    "color-4bit": decoder_codecs.decode_color_4bit,
    "mono-4bit": decoder_codecs.decode_mono_4bit,
    "color-2bit": decoder_codecs.decode_color_2bit,
    "mono-2bit": decoder_codecs.decode_mono_2bit,
    "mono-2bit-mixed-n1bit": decoder_codecs.decode_mono_2bit_mixed_n1bit,
    "mono-2bit-template-drop1bit": decoder_codecs.decode_mono_2bit_template_drop1bit,
    "mono-skel-v1": decoder_codecs.decode_mono_skel_v1,
    "mono-shape-v1": decoder_codecs.decode_mono_shape_v1,
}
MASKED_CODEC_DISPATCH = {
    "mono-28bit": decoder_codecs.decode_mono_28bit,
    "mono-18bit": decoder_codecs.decode_mono_18bit,
    "mono-mask-1bit": decoder_codecs.decode_mono_mask_1bit,
    "color-28bit": decoder_codecs.decode_color_28bit,
}
BACKGROUND_MUTED_CODECS = frozenset({"mono-2bit", "mono-2bit-mixed-n1bit", "mono-2bit-template-drop1bit", "mono-mask-1bit"})
SPARSE_LINE_CODECS = frozenset({"mono-skel-v1", "mono-shape-v1", "airplane-symbol-v1"})


class Decoder:
    def __init__(self, cfg):
        self.cfg = cfg
        # Resolve decoder tag map once; decoding then uses this cached lookup.
        self._decoder_tags = self._get_decoder_tags()
        self.img_names = self.set_filename_from_annot()

    def _get_avif_timeout_sec(self) -> int:
        return int(self.cfg.dec.avif_timeout_sec)

    def _get_smooth_sigma(self) -> float:
        return float(self.cfg.dec.smooth_sigma)

    def _get_bg_max_level(self) -> int:
        return int(self.cfg.dec.bg_max_level)

    @staticmethod
    def _find_key(dic: dict, val, default=None):
        return next((k for k, v in dic.items() if v == val), default)

    def _get_decoder_tags(self) -> dict:
        """Return decoder encoder-tag registry.

        Decoder index resolution is anchored to ``img_process.encoders_tag``.
        If the unified registry is not configured, derive a merged registry
        from split level maps as a one-time fallback.
        """

        tags = getattr(self.cfg.img_process, "encoders_tag", None)
        if isinstance(tags, dict) and tags:
            return tags

        merged = {
            **(getattr(self.cfg.img_process, "encoders_tag_bg_level_1", None) or {}),
            **(getattr(self.cfg.img_process, "encoders_tag_objs_level_1", None) or {}),
            **(getattr(self.cfg.img_process, "encoders_tag_bg_level_2", None) or {}),
            **(getattr(self.cfg.img_process, "encoders_tag_objs_level_2", None) or {}),
        }
        if merged:
            return merged

        raise ValueError("img_process.encoders_tag must be a non-empty dictionary")

    def _resolve_encoder_name(self, encoder_index: int, *, tags: dict, scope: str) -> str:
        enc_name = self._find_key(dic=tags, val=encoder_index, default=None)
        if enc_name is None:
            raise ValueError(
                f"Unknown encoder_index={encoder_index} for {scope}; available tags: {tags}"
            )
        return enc_name

    @staticmethod
    def _validate_size(size: tuple, field_name: str = "size") -> tuple[int, int]:
        if not isinstance(size, tuple) or len(size) != 2:
            raise ValueError(f"{field_name} must be a (width, height) tuple")
        w, h = size
        if not isinstance(w, int) or not isinstance(h, int):
            raise TypeError(f"{field_name} dimensions must be integers")
        if w <= 0 or h <= 0:
            raise ValueError(f"{field_name} dimensions must be > 0, got {(w, h)}")
        return w, h

    @staticmethod
    def _require_length(actual: int, expected: int, field_name: str) -> None:
        if actual != expected:
            raise ValueError(
                f"Invalid decoded payload length for {field_name}: expected {expected}, got {actual}"
            )

    def _resolve_object_encoder_name(self, encoder_index: int | None) -> str | None:
        if encoder_index is None:
            return None
        return next((name for name, idx in self._decoder_tags.items() if idx == encoder_index), None)

    def _build_bg_skip_mask(self, crops, org_img_size: tuple[int, int], scaled_size: tuple[int, int]):
        if not bool(getattr(self.cfg.img_process, "skip_object_bboxes_in_background", False)):
            return None
        if not crops:
            return None

        bboxes = []
        for crop in crops:
            enc_name = self._resolve_object_encoder_name(getattr(crop, "encoder_index", None))
            if enc_name is None or enc_name in SPARSE_LINE_CODECS:
                continue
            ex_bbox = getattr(crop, "expanded_bbox", None)
            if ex_bbox is None:
                continue
            bboxes.append(ex_bbox)

        if not bboxes:
            return None

        full_mask = bboxes_to_mask(org_img_size, bboxes, fill=255)
        return full_mask.resize(scaled_size, Image.Resampling.NEAREST)

    def decompress_background(self, bg, org_img_size, crops=None):
        self._validate_size(org_img_size, field_name="org_img_size")
        enc_name = self._resolve_encoder_name(
            bg.encoder_index,
            tags=self._decoder_tags,
            scope="background",
        )

        if enc_name == "skip_bg":
            bg.recon_pil = Image.new("RGB", org_img_size, color=0)
            bg.mask = None
            return

        skip_mask = self._build_bg_skip_mask(crops, org_img_size, bg.scaled_size)

        bg_recon_pil, mask = Decoder.decode_img(
            encoded_data=bg.encoded_data,
            scaled_size=bg.scaled_size,
            enc_name=enc_name,
            avif_timeout_sec=self._get_avif_timeout_sec(),
            smooth_sigma=self._get_smooth_sigma(),
            max_level=self._get_bg_max_level() if enc_name in BACKGROUND_MUTED_CODECS else 255,
            skip_mask=skip_mask,
            two_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_two_bit_run", 4)),
            one_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_one_bit_run", 1)),
            neighbor_k=int(getattr(self.cfg.enc, "mono_2bit_drop1bit_neighbor_k", 2)),
            fill_gray_level=int(getattr(self.cfg.enc, "mono_2bit_drop1bit_fill_gray_level", 128)),
        )
        bg_recon_pil = bg_recon_pil.resize(org_img_size, Image.Resampling.BICUBIC)

        # if enc_name not in ['color-avif', 'mono-avif']:
        #     # bg_recon_pil = bg_recon_pil.filter(ImageFilter.GaussianBlur(radius=0.3))
        #     bg_recon_pil = self.realesrgan.process_pil(bg_recon_pil)
        #     bg_recon_pil = bg_recon_pil.resize(org_img_size, Image.Resampling.BICUBIC)

        bg.recon_pil = bg_recon_pil
        bg.mask = mask

    def decompress_objs(self, crops):
        if not crops:
            return

        for crop in crops:
            x1m, y1m, x2m, y2m = crop.expanded_bbox
            w_exp = x2m - x1m
            h_exp = y2m - y1m
            if w_exp <= 0 or h_exp <= 0:
                raise ValueError(f"expanded_bbox produced invalid crop size: {crop.expanded_bbox}")

            skip_resize = False
            enc_name = self._resolve_encoder_name(
                crop.encoder_index,
                tags=self._decoder_tags,
                scope="objects",
            )

            if enc_name == "airplane-symbol-v1":
                category_id, theta_deg = decoder_codecs.decode_airplane_symbol_v1(bytes(crop.decoded_obj or b""))
                if int(category_id) == 2:
                    recon_pil = decoder_codecs.render_airplane_symbol(crop.obj_size_scaled, theta_deg=theta_deg)
                elif int(category_id) == 3:
                    recon_pil = decoder_codecs.render_tanker_symbol((w_exp, h_exp), theta_deg=theta_deg)
                    skip_resize = True
                else:
                    # Defensive fallback: unexpected category in symbol payload.
                    recon_pil = decoder_codecs.render_airplane_symbol(crop.obj_size_scaled, theta_deg=theta_deg)
            else:
                recon_pil, _ = Decoder.decode_img(
                    encoded_data=crop.decoded_obj,
                    scaled_size=crop.obj_size_scaled,
                    enc_name=enc_name,
                    avif_timeout_sec=self._get_avif_timeout_sec(),
                    smooth_sigma=self._get_smooth_sigma(),
                    two_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_two_bit_run", 4)),
                    one_bit_run=int(getattr(self.cfg.enc, "mono_2bit_mixed_one_bit_run", 1)),
                    neighbor_k=int(getattr(self.cfg.enc, "mono_2bit_drop1bit_neighbor_k", 2)),
                    fill_gray_level=int(getattr(self.cfg.enc, "mono_2bit_drop1bit_fill_gray_level", 128)),
                )

            # Preserve binary mask-like object edges; bicubic introduces intermediate gray levels.
            obj_resample = (
                Image.Resampling.NEAREST
                if enc_name in {"mono-mask-1bit", "mono-skel-v1", "mono-shape-v1", "airplane-symbol-v1"}
                else Image.Resampling.BICUBIC
            )
            if not skip_resize:
                recon_pil = recon_pil.resize((w_exp, h_exp), obj_resample)
            crop.sparse_overlay = enc_name in SPARSE_LINE_CODECS

                # if enc_name not in ['color-avif', 'mono-avif']:
                #     # recon_pil = recon_pil.filter(ImageFilter.GaussianBlur(radius=0.3))
                #     recon_pil = self.realesrgan.process_pil(recon_pil)
                #     recon_pil = recon_pil.resize((w_exp, h_exp), Image.Resampling.BICUBIC)

            crop.recon_pil = recon_pil


    @classmethod
    def decode_img(
        cls,
        encoded_data: bytes,
        scaled_size: tuple = None,
        enc_name: str = 'color-avif',
        avif_timeout_sec: int = 120,
        smooth_sigma: float = 0.0,
        max_level: int = 255,
        skip_mask=None,
        two_bit_run: int = 4,
        one_bit_run: int = 1,
        neighbor_k: int = 2,
        fill_gray_level: int = 128,
    ) -> tuple[Image.Image, tuple]:
        """Decode image bytes with one of the configured semantic codecs.

        Args:
            encoded_data: Encoded image bytes.
            scaled_size: Expected (width, height) for non-AVIF decoders.
            enc_name: Encoder/decoder name key.
            avif_timeout_sec: Timeout for AVIF decoding.
            smooth_sigma: Gaussian smoothing sigma for masked codecs (0.0 = disabled).
            max_level: Maximum grayscale level for decoders that support remapped low-bit output.

        Returns:
            Tuple of (PIL Image, mask). Mask is None for non-masked decoders.

        Raises:
            TypeError: encoded_data is not bytes-like.
            ValueError: Invalid encoder name or missing required parameters.
        """
        if not isinstance(encoded_data, (bytes, bytearray, memoryview)):
            raise TypeError(f"encoded_data must be bytes-like, got {type(encoded_data).__name__}")

        encoded_data = bytes(encoded_data)
        if not encoded_data:
            raise ValueError("encoded_data must not be empty")

        if enc_name not in AVIF_DECODERS:
            cls._validate_size(scaled_size, field_name="scaled_size")

        mask = None

        if enc_name in AVIF_CODEC_DISPATCH:
            recon_pil = AVIF_CODEC_DISPATCH[enc_name](encoded_data, timeout_sec=avif_timeout_sec)
        elif enc_name == "mono-2bit":
            recon_pil = decoder_codecs.decode_mono_2bit(
                encoded_data,
                scaled_size,
                max_level=max_level,
                skip_mask=skip_mask,
            )
        elif enc_name == "mono-2bit-mixed-n1bit":
            recon_pil = decoder_codecs.decode_mono_2bit_mixed_n1bit(
                encoded_data,
                scaled_size,
                two_bit_run=two_bit_run,
                one_bit_run=one_bit_run,
                max_level=max_level,
                skip_mask=skip_mask,
            )
        elif enc_name == "mono-2bit-template-drop1bit":
            recon_pil = decoder_codecs.decode_mono_2bit_template_drop1bit(
                encoded_data,
                scaled_size,
                two_bit_run=two_bit_run,
                one_bit_run=one_bit_run,
                neighbor_k=neighbor_k,
                fill_gray_level=fill_gray_level,
                max_level=max_level,
                skip_mask=skip_mask,
            )
        elif enc_name in NON_MASK_CODEC_DISPATCH:
            recon_pil = NON_MASK_CODEC_DISPATCH[enc_name](encoded_data, scaled_size)
        elif enc_name == "mono-mask-1bit":
            recon_pil, mask = decoder_codecs.decode_mono_mask_1bit(
                encoded_data,
                scaled_size,
                smooth_sigma=smooth_sigma,
                max_level=max_level,
                skip_mask=skip_mask,
            )
        elif enc_name in MASKED_CODEC_DISPATCH:
            recon_pil, mask = MASKED_CODEC_DISPATCH[enc_name](encoded_data, scaled_size, smooth_sigma=smooth_sigma)
        else:
            raise ValueError(f"Invalid encoder name - decoding failed: {enc_name}")

        return recon_pil, mask



    def set_filename_from_annot(self):
        """Return mapping from image id to file name when COCO annotations are configured."""

        if self.cfg.io.annot_file:
            coco_gt = load_coco_annotations(self.cfg.io.annot_file)

            img_names: Dict[int, str] = {
                img["id"]: img["file_name"]
                for img in coco_gt.loadImgs(coco_gt.getImgIds())
            }
        else:
            img_names: Dict[int, str] = {}

        return img_names

