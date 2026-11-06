"""ImageManager adapter for semantic image compression."""

from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any

from semantic_img_comp.utils.logging_helpers import build_encoder_log_record, compute_compression_rate

LOGGER = logging.getLogger(__name__)


class SemanticImageManager(ImageManager):
    """Semantic compression encoder/decoder using image transport."""

    _DEFAULT_COMPRESSION_LEVEL = 2
    _VALID_COMPRESSION_LEVELS = {0, 1, 2}
    _INITIALIZED_LOG_DIRS: set[str] = set()

    def __init__(
        self,
        *,
        cfg: Any,
        service_name: str,
        transform_name: str = "image-transform",
        output_dir: Path | str | None = None,
        synthetic_http_ok: bool = False,
    ) -> None:
        """Initialize semantic codec state and output paths."""

        super().__init__(
            service_name=service_name,
            transform_name=transform_name,
            synthetic_http_ok=synthetic_http_ok,
        )
        self.cfg = cfg
        model_cfg = getattr(cfg, "model", None)
        self.model_path = getattr(model_cfg, "enc_yolo_model_path", None)
        self.output_dir = Path(output_dir) if output_dir else None
        io_cfg = getattr(cfg, "io", None)
        self._write_json_logs = bool(getattr(io_cfg, "write_json_logs", True))
        self._frame_counter = 0
        self._decode_counter = 0
        self._bridge = None
        self._initialize_run_logs()

    def _initialize_run_logs(self) -> None:
        """Clear runtime JSON logs once per process/output directory."""

        if self.output_dir is None or not self._write_json_logs:
            return

        log_dir = (self.output_dir / "log").resolve()
        log_dir_key = str(log_dir)
        if log_dir_key in self._INITIALIZED_LOG_DIRS:
            return

        log_dir.mkdir(parents=True, exist_ok=True)
        for log_name in ("enc_log.json", "dec_log.json"):
            with open(log_dir / log_name, "w", encoding="utf-8"):
                pass

        self._INITIALIZED_LOG_DIRS.add(log_dir_key)

    @property
    def bridge(self):
        """Lazy-initialize the semantic codec bridge."""
        if self._bridge is None:
            from .semantic_codec_bridge import SemanticCodecBridge

            self._bridge = SemanticCodecBridge(self.cfg)
        return self._bridge

    def warmup(self) -> None:
        """Initialize codec dependencies during service startup."""
        LOGGER.info("Warming semantic codec bridge")
        bridge = self.bridge
        _ = bridge.encoder
        _ = bridge.decoder
        LOGGER.info("Semantic codec bridge warmed")

    def cleanup(self, **kwargs: Any) -> list[Any]:
        """Delegate accepted-frame cleanup, including synthetic HTTP OK, to ImageManager."""

        return super().cleanup(**kwargs)

    def _build_passthrough_encode_result(self, *, frame_id: int, jpeg_bytes: bytes) -> SimpleNamespace:
        """Build an encode-result compatible object for level-0 JPEG passthrough."""

        from PIL import Image as PILImage

        with PILImage.open(BytesIO(jpeg_bytes)) as image:
            org_img_size = image.size

        return SimpleNamespace(
            payload=jpeg_bytes,
            jpeg_bytes=jpeg_bytes,
            size_log={"jpeg_passthrough": len(jpeg_bytes)},
            img_data=SimpleNamespace(
                img_idx=frame_id,
                org_jpeg_bytes=len(jpeg_bytes),
                org_img_size=org_img_size,
                encoded_data=jpeg_bytes,
                crops=[],
                bg=None,
            ),
            timing_ms={},
            detections=[],
            bg_quota_bytes=None,
            obj_quota_bytes=None,
            fast_path_selected=False,
            obj_detection_skipped=True,
            comp_rate=1.0,
            aggregated_comp_rate=1.0,
            tar_comp_rate=None,
            comp_level=0,
        )

    def _resolve_compression_level(self, raw_level: Any) -> int:
        """Normalize compression level values and default invalid inputs to level 2."""

        try:
            level = int(raw_level)
        except (TypeError, ValueError):
            LOGGER.warning(
                "Invalid compression_level=%r from get_compression_level(); defaulting to %d",
                raw_level,
                self._DEFAULT_COMPRESSION_LEVEL,
            )
            return self._DEFAULT_COMPRESSION_LEVEL

        if level not in self._VALID_COMPRESSION_LEVELS:
            LOGGER.warning(
                "Unsupported compression_level=%r from get_compression_level(); defaulting to %d",
                raw_level,
                self._DEFAULT_COMPRESSION_LEVEL,
            )
            return self._DEFAULT_COMPRESSION_LEVEL

        return level

    def process_image(self, jpeg_bytes: bytes) -> bytes:
        """Encode one JPEG frame into a semantic compression payload."""
        if not isinstance(jpeg_bytes, (bytes, bytearray)):
            raise TypeError(f"jpeg_bytes must be bytes-like, got {type(jpeg_bytes).__name__}")
        if not jpeg_bytes:
            raise ValueError("jpeg_bytes must not be empty")

        self._frame_counter += 1
        frame_id = self._frame_counter
        queue_length = self.image_queue_length()
        compression_level = self._resolve_compression_level(self.get_compression_level())
        LOGGER.info("Frame %d: image_queue_length=%d compression_level=%d", frame_id, queue_length, compression_level)

        try:
            jpeg_bytes = bytes(jpeg_bytes)
            start = time.perf_counter()
            if compression_level == 0:
                LOGGER.debug("Frame %d using JPEG passthrough because compression_level=0", frame_id)
                result = self._build_passthrough_encode_result(frame_id=frame_id, jpeg_bytes=jpeg_bytes)
            else:
                result = self.bridge.encode_from_jpeg(
                    jpeg_bytes,
                    img_id=frame_id,
                    queue_length=queue_length,
                    compression_level=compression_level,
                ).result()
            encode_ms = (time.perf_counter() - start) * 1000.0
            timing_ms = dict(getattr(result, "timing_ms", None) or {})
            timing_ms["wall_encode"] = encode_ms
            self._record_image_encode(
                frame_id=frame_id,
                jpeg_bytes=jpeg_bytes,
                payload_bytes=len(result.payload),
                img_idx=getattr(result.img_data, "img_idx", frame_id),
                num_objs=len(getattr(result.img_data, "crops", []) or []),
                timing_ms=timing_ms,
                size_log=getattr(result, "size_log", None),
            )
            if self.output_dir:
                self._save_encoding_metadata(frame_id, result, encode_ms=encode_ms)

            LOGGER.info(
                "Frame %d encoded: jpeg=%d bytes, payload=%d bytes, num_objs=%d, comp_rate=%.2f, encode_ms=%.2f",
                frame_id,
                len(jpeg_bytes),
                len(result.payload),
                len(result.img_data.crops or []),
                len(jpeg_bytes) / len(result.payload) if result.payload else 0.0,
                encode_ms,
            )
            return result.payload
        except Exception:
            LOGGER.exception("Failed to encode frame %d", frame_id)
            raise

    def process_payload(self, payload_bytes: bytes, compression_level: int = 0) -> bytes:
        """Decode one semantic compression payload back into JPEG bytes."""
        if not isinstance(payload_bytes, (bytes, bytearray)):
            raise TypeError(f"payload_bytes must be bytes-like, got {type(payload_bytes).__name__}")
        if not payload_bytes:
            raise ValueError("payload_bytes must not be empty")

        try:
            start = time.perf_counter()
            if compression_level == 0:
                # Level 0 carries a raw JPEG payload, so skip semantic decode.
                from PIL import Image as PILImage

                with PILImage.open(BytesIO(payload_bytes)) as image:
                    passthrough_image = image.copy()
                result = SimpleNamespace(
                    image=passthrough_image,
                    img_idx=self._decode_counter + 1,
                    mask=None,
                    org_img_size=passthrough_image.size,
                )
            else:
                result = self.bridge.decode_payload(bytes(payload_bytes))
            jpeg_bytes = self.bridge._save_jpeg_from_image(result.image)
            decode_ms = (time.perf_counter() - start) * 1000.0
            self._decode_counter += 1
            self._record_image_decode(
                frame_number=self._decode_counter,
                img_idx=getattr(result, "img_idx", self._decode_counter),
                payload_size=len(payload_bytes),
                recon_jpeg_size=len(jpeg_bytes),
                img_size=getattr(result, "image").size,
                decode_ms=decode_ms,
            )

            if self.output_dir:
                self._save_decode_artifacts(
                    result,
                    payload_size=len(payload_bytes),
                    decode_ms=decode_ms,
                )

            LOGGER.info(
                "Frame %d decoded: payload=%d bytes, recon_jpeg=%d bytes, img_size=%s, decode_ms=%.2f",
                result.img_idx,
                len(payload_bytes),
                len(jpeg_bytes),
                result.image.size,
                decode_ms,
            )
            return jpeg_bytes
        except Exception:
            LOGGER.exception("Failed to decode payload")
            raise

    def performance_status(self) -> dict[str, Any]:
        """Return image processing timing metrics for dashboards/status APIs."""

        status = super().performance_status()
        return {
            **status,
            "model_path": str(self.model_path) if self.model_path is not None else None,
        }

    def _encode_result_detections(self, result: Any) -> list[dict[str, Any]]:
        """Return COCO-style detection records from bridge encode results."""

        detections = getattr(result, "detections", None)
        if detections is not None:
            return list(detections)

        img_data = getattr(result, "img_data", None)
        image_id = getattr(img_data, "img_idx", 0)
        records: list[dict[str, Any]] = []
        for crop in getattr(img_data, "crops", None) or []:
            bbox = getattr(crop, "bbox", None)
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
            records.append(
                {
                    "image_id": int(image_id),
                    "category_id": int(getattr(crop, "category_id", 0)),
                    "bbox": [
                        float(x1),
                        float(y1),
                        max(0.0, float(x2) - float(x1)),
                        max(0.0, float(y2) - float(y1)),
                    ],
                    "score": float(getattr(crop, "det_conf", 0.0)),
                }
            )
        return records

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        """Append one JSON record to a JSONL diagnostics file."""

        if not self._write_json_logs:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _save_encoding_metadata(self, frame_id: int, result: Any, *, encode_ms: float | None = None) -> None:
        """Save encoder metadata for runtime smoke tests and diagnostics."""
        try:
            if self.output_dir is None or not self._write_json_logs:
                return

            log_dir = self.output_dir / "log"
            log_dir.mkdir(parents=True, exist_ok=True)

            log_record = build_encoder_log_record(
                frame_id=frame_id,
                img_data=result.img_data,
                size_log=result.size_log,
                timing_ms=getattr(result, "timing_ms", None),
                bg_quota_bytes=getattr(result, "bg_quota_bytes", None),
                obj_quota_bytes=getattr(result, "obj_quota_bytes", None),
            )
            img_idx = result.img_data.img_idx
            detections = self._encode_result_detections(result)

            log_record["img_idx"] = img_idx
            log_record["detections"] = detections
            log_record.setdefault("file_name", None)
            payload_record = log_record.get("payload", {})
            objects_record = log_record.get("objects", {})
            runtime_record = log_record.get("runtime_ms", {})
            log_record.setdefault("org_img_size", list(getattr(result.img_data, "org_img_size", ()) or []))
            log_record.setdefault("org_jpeg_bytes", getattr(result.img_data, "org_jpeg_bytes", None))
            log_record.setdefault("orig_jpeg_bytes", result.img_data.org_jpeg_bytes)
            log_record.setdefault("objects_total_pixels", objects_record.get("total_pixels", 0))
            log_record.setdefault("timing_ms", runtime_record)
            log_record.setdefault("bg_quota_bytes", getattr(result, "bg_quota_bytes", None))
            log_record.setdefault("obj_quota_bytes", getattr(result, "obj_quota_bytes", None))
            fast_path_selected = bool(getattr(result, "fast_path_selected", False))
            log_record.setdefault("fast_path_selected", fast_path_selected)
            log_record.setdefault(
                "fast_path_bg_selected",
                bool(getattr(result, "fast_path_bg_selected", fast_path_selected)),
            )
            log_record.setdefault(
                "fast_path_obj_selected",
                bool(getattr(result, "fast_path_obj_selected", fast_path_selected)),
            )
            log_record.setdefault(
                "obj_detection_skipped",
                bool(getattr(result, "obj_detection_skipped", False)),
            )
            comp_rate = getattr(result, "comp_rate", None)
            if comp_rate is None:
                comp_rate = compute_compression_rate(
                    getattr(result.img_data, "org_jpeg_bytes", None),
                    payload_record.get("total_bytes"),
                )
            comp_level = getattr(result, "comp_level", None)
            if comp_level is None:
                comp_level = self._resolve_compression_level(self.get_compression_level())
            metrics_record = {
                "comp_rate": comp_rate,
                "aggregated_comp_rate": getattr(result, "aggregated_comp_rate", None),
                "tar_comp_rate": getattr(result, "tar_comp_rate", None),
                "comp_level": comp_level,
            }
            log_record["metrics"] = {
                key: value for key, value in metrics_record.items() if value is not None
            }
            if encode_ms is not None:
                log_record["wall_encode_ms"] = round(encode_ms, 2)
            self._append_jsonl(log_dir / "enc_log.json", log_record)
        except Exception as exc:
            LOGGER.warning("Failed to save encoding metadata: %s", exc)

    def _save_decode_artifacts(
        self,
        result: Any,
        *,
        payload_size: int,
        decode_ms: float | None = None,
    ) -> None:
        """Save reconstructed image/mask artifacts for smoke checks."""
        try:
            if self.output_dir is None or not self._write_json_logs:
                return

            log_dir = self.output_dir / "log"
            log_dir.mkdir(parents=True, exist_ok=True)

            self._append_jsonl(
                log_dir / "dec_log.json",
                {
                    "event": "frame_decoded",
                    "frame_number": self._decode_counter,
                    "img_idx": result.img_idx,
                    "payload_bytes": payload_size,
                    "decode_ms": round(decode_ms, 2) if decode_ms is not None else None,
                    "recon_image_path": None,
                    "mask_saved": False,
                },
            )
        except Exception as exc:
            LOGGER.warning("Failed to save decode artifacts: %s", exc)

