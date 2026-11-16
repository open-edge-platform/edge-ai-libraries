# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""OpenVINO ViCLIP-B/L video and text encoders loaded from prepared packages."""

import html
import json
from pathlib import Path
import threading

import numpy as np

import config
from core.content import ROLE_L1_SEGMENT, ROLE_SHORT_VIDEO
from inference.meta import RUNTIME_OV_CORE, InferenceMeta


class ViClipOpenVINOEmbedding(InferenceMeta):
    BACKEND = config.LOCAL_OPENVINO
    RUNTIME = RUNTIME_OV_CORE
    SUPPORT_MULTIMODAL = True
    supported_roles = frozenset({ROLE_SHORT_VIDEO, ROLE_L1_SEGMENT})
    PACKAGE_TYPES = {
        "viclip-b": ("viclip", 512, 32, "clip_bpe"),
        "viclip-l": ("viclip", 768, 32, "clip_bpe"),
    }
    MODEL_IDS = {
        "viclip-b": "OpenGVLab/ViCLIP-B-16-hf",
        "viclip-l": "OpenGVLab/ViCLIP-L-14-hf",
    }

    @classmethod
    def package_metadata(cls, model_path, expected_name=None, expected_precision=None):
        """Validate file/identity contracts without loading OV or model tensors."""
        root = Path(model_path)
        metadata = json.loads((root / "video_embedding.json").read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("video_embedding.json must contain an object")
        name = metadata.get("name")
        if name not in cls.PACKAGE_TYPES or (expected_name and name != expected_name):
            raise ValueError(f"Unsupported or mismatched video package: {name!r}")
        actual = tuple(metadata.get(k) for k in (
            "preprocessing", "dimension", "context_length", "tokenizer_type"))
        if (metadata.get("format") != 1 or actual != cls.PACKAGE_TYPES[name]
                or (metadata.get("frames"), metadata.get("image_size")) != (8, 224)
                or metadata.get("precision") not in ("fp16", "fp32")):
            raise ValueError("Unexpected video package format/geometry/tokenizer/precision")
        suffix = root.name.rsplit("-", 1)[-1]
        if suffix in ("fp16", "fp32") and suffix != metadata["precision"]:
            raise ValueError("Video package directory precision conflicts with its manifest")
        if expected_precision and metadata["precision"] != expected_precision:
            raise ValueError("Selected model ID precision conflicts with its manifest")
        if root.name in {f"{family}-{precision}" for family in cls.PACKAGE_TYPES
                         for precision in ("fp16", "fp32")} and root.name != f"{name}-{metadata['precision']}":
            raise ValueError("Video package directory identity conflicts with its manifest")
        if name in cls.MODEL_IDS and metadata.get("model_id") != cls.MODEL_IDS[name]:
            raise ValueError("Video package canonical model ID does not match its identity")
        count = metadata.get("parameter_count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("Missing positive model parameter_count")
        artifacts = metadata.get("artifacts")
        if (not isinstance(artifacts, dict)
                or set(artifacts) != {"video_encoder", "text_encoder", "tokenizer"}):
            raise ValueError("Package must declare both encoders and tokenizer artifacts")
        for tower in ("video_encoder", "text_encoder"):
            if artifacts[tower] != [f"{tower}.xml", f"{tower}.bin"]:
                raise ValueError(f"Unexpected {tower} artifacts")
        required = {"video_encoder.xml", "video_encoder.bin", "text_encoder.xml",
                    "text_encoder.bin", "tokenizer_config.json", "special_tokens_map.json"}
        required.update(("vocab.json", "merges.txt") if name.startswith("viclip-") else ("vocab.txt",))
        for files in artifacts.values():
            if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
                raise ValueError("Invalid package artifact list")
            required.update(files)
        for file in required:
            artifact = root / file
            if (Path(file).name != file or artifact.is_symlink()
                    or not artifact.is_file() or artifact.stat().st_size == 0):
                raise ValueError(f"Missing, empty or unsafe package artifact: {file}")
        return metadata

    def __init__(self, model_path, device="CPU", family=None):
        import openvino as ov
        from transformers import AutoTokenizer

        self.model_path = str(Path(model_path).expanduser().resolve())
        root = Path(self.model_path)
        self.metadata = self.package_metadata(root)
        self.name = self.metadata["name"]
        self.preprocessing, self.dimension, self.context_length, _ = self.PACKAGE_TYPES[self.name]
        if family and family != self.preprocessing:
            raise ValueError(f"Requested {family}, package contains {self.preprocessing}")
        self.frames_per_clip = 8
        self.image_size = 224
        self.precision = self.metadata["precision"]
        self.parameter_count = self.metadata["parameter_count"]
        self.parameter_count_source = "exported-full-reference-model"
        self.device = device or "CPU"
        self.tokenizer_source = self.model_path
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True, use_fast=False, trust_remote_code=False)
        self._lock = threading.RLock()
        # Precision comes from the package manifest.
        hint = "f16" if self.precision == "fp16" else "f32"
        self.execution_precision = hint
        core = ov.Core()
        options = {"INFERENCE_PRECISION_HINT": hint}
        self._video = core.compile_model(root / "video_encoder.xml", self.device, options)
        self._text = core.compile_model(root / "text_encoder.xml", self.device, options)
        if list(self._video.input(0).shape) != [1, 8, 3, 224, 224]:
            raise ValueError("Unexpected compiled video input")
        text_names = {p.get_any_name() for p in self._text.inputs}
        expected = {"input_ids"} if self.preprocessing == "viclip" else {"input_ids", "attention_mask"}
        if text_names != expected:
            raise ValueError("Unexpected compiled text inputs")
        for tower in (self._video, self._text):
            if len(tower.outputs) != 1 or tower.output(0).get_partial_shape()[-1].get_length() != self.dimension:
                raise ValueError("Unexpected compiled embedding dimension")

    @staticmethod
    def _normalized(vectors):
        values = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(values, axis=-1, keepdims=True)
        if not np.isfinite(values).all() or np.any(norms <= 1e-12):
            raise ValueError("Invalid OpenVINO embedding: nonfinite or zero vector")
        return values / norms

    def get_query_embedding(self, text):
        return self.get_text_embeddings([text])[0]

    def get_text_embedding_batch(self, texts):
        return self.get_text_embeddings(texts)

    def get_text_embeddings(self, texts):
        texts = list(texts)
        if not texts:
            return []
        if self.preprocessing == "viclip":
            import ftfy

            texts = [html.unescape(html.unescape(ftfy.fix_text(text))).strip() for text in texts]
        with self._lock:
            tokens = self.tokenizer(texts, padding="max_length", max_length=self.context_length,
                                    truncation=True, return_tensors="np")
            inputs = {"input_ids": np.asarray(tokens["input_ids"], dtype=np.int64)}
            if self.preprocessing != "viclip":
                inputs["attention_mask"] = np.asarray(tokens["attention_mask"], dtype=np.int64)
            output = self._text(inputs)[self._text.output(0)]
            return self._normalized(output).tolist()

    def _pixels(self, frames):
        import cv2

        pixels = np.stack([cv2.resize(np.asarray(frame.convert("RGB")), (224, 224)) for frame in frames])
        pixels = pixels.astype(np.float32).transpose(0, 3, 1, 2) / 255.0
        pixels -= np.array([.485, .456, .406], dtype=np.float32)[None, :, None, None]
        pixels /= np.array([.229, .224, .225], dtype=np.float32)[None, :, None, None]
        return np.ascontiguousarray(pixels[None], dtype=np.float32)

    def get_image_embeddings(self, images):
        raise NotImplementedError(f"{self.name} embeds video clips, not still images; use an image source")

    def get_video_embedding(self, frames):
        from core.multimodal.frames import pad_to

        frames = pad_to(list(frames), self.frames_per_clip)
        if len(frames) != self.frames_per_clip:
            raise ValueError("Expected eight sampled frames")
        pixels = self._pixels(frames)
        with self._lock:
            output = self._video({"pixel_values": pixels})[self._video.output(0)]
            return self._normalized(output)[0].tolist()