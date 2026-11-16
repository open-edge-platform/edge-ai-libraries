# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from io import BytesIO
import logging
import queue
import threading
import time
from typing import Any, TYPE_CHECKING

from PIL import Image

from semantic_img_comp.core.frame import ImgEncData
from semantic_img_comp.encoder.pipeline_manager import EncoderPipelineManager
from semantic_img_comp.utils.logging_helpers import compute_compression_rate


LOGGER = logging.getLogger(__name__)

# Key used for encode/decode sequence counters when no client_id/stream_id is supplied.
_DEFAULT_CLIENT_ID = "default"

if TYPE_CHECKING:
    from semantic_img_comp.decoder.decoder import Decoder
    from semantic_img_comp.encoder.encoder import Encoder


def _demux_frame(payload: bytes, mux_cfg, *, img_idx: int | None = None, max_crops: int | None = None):
    from semantic_img_comp.decoder.demux import demux_frame
    return demux_frame(payload, mux_cfg, img_idx=img_idx, max_crops=max_crops)


def _paste_with_margin(img_dec_data, *, margin_percent: float, feather_ratio: float, feather_min_px: int):
    from semantic_img_comp.utils.postprocessing import paste_with_margin
    return paste_with_margin(
        img_dec_data,
        margin_percent=margin_percent,
        feather_ratio=feather_ratio,
        feather_min_px=feather_min_px,
    )


@dataclass
class EncodeResult:
    payload: bytes
    size_log: dict[str, int]
    img_data: ImgEncData
    timing_ms: dict[str, float] | None = None
    bg_quota_bytes: int | None = None
    obj_quota_bytes: int | None = None
    fast_path_selected: bool = False
    obj_detection_skipped: bool = False
    comp_rate: float | None = None
    aggregated_comp_rate: float | None = None
    tar_comp_rate: float | None = None
    comp_level: int | None = None


@dataclass
class DecodeResult:
    image: Image.Image
    img_idx: int
    mask: Any | None = None
    org_img_size: tuple[int, int] | None = None
    crops: Any | None = None


class SemanticCodecBridge:
    """In-memory semantic encoder/decoder bridge for external pipelines."""

    def __init__(self, cfg, *, encoder: Encoder | None = None, decoder: Decoder | None = None):
        self.cfg = cfg
        self._encoder = encoder
        self._decoder = decoder
        self._pipeline_mgr: EncoderPipelineManager | None = None
        # Per-client/stream sequence counters: TCP and HTTP runners/services alike
        # pass a stable client_id/stream_id (both treated as "client_id" here) so each
        # logical producer/consumer gets its own monotonic sequence, even when several
        # are multiplexed through one shared bridge instance (e.g. the TCP decoder).
        self._encode_counters: dict[str, int] = {}
        self._decode_counters: dict[str, int] = {}
        self._counters_lock = threading.Lock()
        self._processed_frames_count = 0
        self._processed_input_bytes_total = 0
        self._processed_payload_bytes_total = 0.0
        # Serializes concurrent encode_from_jpeg callers (e.g. one thread per client) onto
        # one worker thread, since the encoder/pipeline manager aren't thread-safe.
        self._encode_queue: "queue.Queue" = queue.Queue(maxsize=200)
        self._encode_worker_thread: threading.Thread | None = None
        self._encode_worker_lock = threading.Lock()

    @property
    def encoder(self):
        if self._encoder is None:
            from semantic_img_comp.encoder.encoder import Encoder
            self._encoder = Encoder(self.cfg)
        return self._encoder

    @property
    def decoder(self):
        if self._decoder is None:
            from semantic_img_comp.decoder.decoder import Decoder
            self._decoder = Decoder(self.cfg)
        return self._decoder

    @property
    def pipeline_mgr(self) -> EncoderPipelineManager:
        if self._pipeline_mgr is None:
            global_skip_obj_detection = bool(getattr(self.encoder, "skip_obj_detection", False))
            try:
                self._pipeline_mgr = EncoderPipelineManager(
                    self.cfg,
                    global_skip_obj_detection=global_skip_obj_detection,
                )
            except TypeError as exc:
                if "global_skip_obj_detection" not in str(exc):
                    raise
                self._pipeline_mgr = EncoderPipelineManager(self.cfg)
                if hasattr(self._pipeline_mgr, "global_skip_obj_detection"):
                    self._pipeline_mgr.global_skip_obj_detection = global_skip_obj_detection
        return self._pipeline_mgr

    @staticmethod
    def _load_image_from_bytes(jpeg_bytes: bytes) -> Image.Image:
        """Load PIL image from JPEG bytes, preserving monochrome vs color."""
        with Image.open(BytesIO(jpeg_bytes)) as img:
            is_monochrome = img.mode in ("L", "LA", "I;16", "I;16B", "I;16L", "I")
            if is_monochrome:
                pil_img = img.convert("L")
            else:
                pil_img = img.convert("RGB")
            pil_img.load()
            return pil_img.copy()

    def _next_encode_sequence(self, client_id: str | None) -> int:
        """Return the next monotonic encode sequence number for client_id (or the default bucket)."""
        key = client_id or _DEFAULT_CLIENT_ID
        with self._counters_lock:
            self._encode_counters[key] = self._encode_counters.get(key, 0) + 1
            return self._encode_counters[key]

    def _next_decode_sequence(self, client_id: str | None) -> int:
        """Return the next monotonic decode sequence number for client_id (or the default bucket)."""
        key = client_id or _DEFAULT_CLIENT_ID
        with self._counters_lock:
            self._decode_counters[key] = self._decode_counters.get(key, 0) + 1
            return self._decode_counters[key]

    def _ensure_encode_worker(self) -> None:
        with self._encode_worker_lock:
            if self._encode_worker_thread is None:
                self._encode_worker_thread = threading.Thread(
                    target=self._encode_worker_loop,
                    daemon=True,
                    name="semantic-codec-bridge-encoder",
                )
                self._encode_worker_thread.start()

    def _encode_worker_loop(self) -> None:
        while True:
            future, kwargs = self._encode_queue.get()
            try:
                result = self._encode_from_jpeg_async(**kwargs)
            except BaseException as exc:  # noqa: BLE001 - propagated to the caller via the future
                future.set_exception(exc)
            else:
                future.set_result(result)
            finally:
                self._encode_queue.task_done()

    def encode_from_jpeg(
        self,
        jpeg_bytes: bytes,
        *,
        client_id: str | None = None,
        img_id: int | None = None,
        queue_length: int | None = None,
        compression_level: int = 2,
    ) -> "Future[EncodeResult]":
        """Submit one JPEG frame for encoding and return a Future for the result.

        Args:
            jpeg_bytes: JPEG-encoded image bytes.
            client_id: Stable producer identity (TCP client address or HTTP stream_id);
                scopes the auto-incremented img_id sequence so multiple clients sharing
                one bridge instance don't collide. Defaults to a single shared sequence.
            img_id: Optional image ID; if None, auto-incremented per client_id.
            queue_length: Optional queue length for pipeline decision.
            compression_level: Compression level (1 or 2) for encoder tag selection (2 keeps object detection enabled).

        Returns:
            Future resolving to an EncodeResult with payload, size_log, and detection metadata.
            Encode jobs from all callers are serialized onto one worker thread, so futures
            complete in the same order they were submitted.
        """
        if not isinstance(jpeg_bytes, (bytes, bytearray)):
            raise TypeError(f"jpeg_bytes must be bytes-like, got {type(jpeg_bytes).__name__}")

        if not jpeg_bytes:
            raise ValueError("jpeg_bytes must not be empty")

        self._ensure_encode_worker()
        future: "Future[EncodeResult]" = Future()
        self._encode_queue.put((future, dict(
            jpeg_bytes=jpeg_bytes,
            client_id=client_id,
            img_id=img_id,
            queue_length=queue_length,
            compression_level=compression_level,
        )))
        return future

    def _encode_from_jpeg_async(
        self,
        jpeg_bytes: bytes,
        *,
        client_id: str | None = None,
        img_id: int | None = None,
        queue_length: int | None = None,
        compression_level: int = 2,
    ) -> EncodeResult:
        t_start = time.perf_counter()
        pil_img = self._load_image_from_bytes(bytes(jpeg_bytes))
        org_jpeg_bytes = len(jpeg_bytes)

        queue_size = int(queue_length if queue_length is not None else len(self._encode_queue.queue))
        processed_frames_count = self._processed_frames_count
        forced_skip_obj_detection = (
            bool(getattr(self.encoder, "skip_obj_detection", False))
            or int(compression_level) != 2
        )
        if hasattr(self.pipeline_mgr, "global_skip_obj_detection"):
            self.pipeline_mgr.global_skip_obj_detection = forced_skip_obj_detection
        aggregated_comp_rate_input = compute_compression_rate(
            self._processed_input_bytes_total,
            self._processed_payload_bytes_total,
        )
        pipeline_ctx = self.pipeline_mgr.decide_pipeline(
            image_size_bytes=org_jpeg_bytes,
            queue_size=queue_size,
            aggregated_comp_rate=aggregated_comp_rate_input,
            processed_frames_count=processed_frames_count,
            compression_level=compression_level,
        )

        if bool(getattr(self.pipeline_mgr, "level_changed", False)):
            self._processed_input_bytes_total = 0
            self._processed_payload_bytes_total = 0.0
            self._processed_frames_count = 0

        if img_id is None:
            img_id = self._next_encode_sequence(client_id)
        elif img_id <= 0:
            raise ValueError(f"img_id must be > 0, got {img_id}")

        img_enc_data = ImgEncData(img_idx=img_id, org_jpeg_bytes=org_jpeg_bytes)
        img_enc_data.org_img_size = pil_img.size

        img_skip_obj_detection = bool(pipeline_ctx.skip_obj_detection)
        fast_path_bg = bool(getattr(pipeline_ctx, "use_fast_path_bg", getattr(pipeline_ctx, "use_fast_path", False)))
        fast_path_obj = bool(getattr(pipeline_ctx, "use_fast_path_obj", getattr(pipeline_ctx, "use_fast_path", False)))

        LOGGER.debug(
            "Bridge pipeline decision img_id=%s queue_size=%d processed_frames_count=%d aggregated_comp_rate_input=%s target_compression_rate=%s adaptive_skip_obj_detection=%s adaptive_fast_path=%s",
            img_id,
            queue_size,
            processed_frames_count,
            f"{aggregated_comp_rate_input:.4f}" if aggregated_comp_rate_input is not None else None,
            (
                f"{pipeline_ctx.target_compression_rate:.4f}"
                if getattr(pipeline_ctx, "target_compression_rate", None) is not None
                else None
            ),
            pipeline_ctx.skip_obj_detection,
            pipeline_ctx.use_fast_path,
        )

        timing_ms: dict[str, float] = {}
        pipeline_config_applied = False
        try:
            self.pipeline_mgr.apply_pipeline_config(
                pipeline_ctx,
                img_size=img_enc_data.org_img_size,
            )
            pipeline_config_applied = True

            if img_skip_obj_detection:
                crops = []
                timing_ms["yolo"] = 0.0
            else:
                t0 = time.perf_counter()
                crops = self.encoder.extract_objs(pil_img)
                timing_ms["yolo"] = (time.perf_counter() - t0) * 1000.0

            t1 = time.perf_counter()
            tar_objs_bytes, tar_enc_data_bytes = self.encoder.set_tar_objs_bytes(
                org_jpeg_bytes=img_enc_data.org_jpeg_bytes,
                num_objs=len(crops),
            )
            if img_skip_obj_detection:
                img_enc_data.crops = []
                timing_ms["obj_comp"] = 0.0
            else:
                img_enc_data.crops = self.encoder.compress_objs(
                    crops,
                    tar_objs_bytes,
                    use_fast_path=fast_path_obj,
                )
                timing_ms["obj_comp"] = (time.perf_counter() - t1) * 1000.0

            t2 = time.perf_counter()
            img_enc_data.bg, tar_bg_bytes = self.encoder.compress_background(
                pil_img,
                tar_enc_data_bytes,
                crops,
                use_fast_path=fast_path_bg,
            )
            timing_ms["bg_comp"] = (time.perf_counter() - t2) * 1000.0

            payload, size_log = self.encoder.encode_payload(img_enc_data)
            timing_ms["enc_total"] = (time.perf_counter() - t_start) * 1000.0

            frame_payload_bytes = float(sum(size_log.values()))
            self._processed_frames_count += 1
            self._processed_input_bytes_total += org_jpeg_bytes
            self._processed_payload_bytes_total += frame_payload_bytes
            per_image_comp_rate = compute_compression_rate(org_jpeg_bytes, frame_payload_bytes)
            aggregated_comp_rate = compute_compression_rate(
                self._processed_input_bytes_total,
                self._processed_payload_bytes_total,
            )

            LOGGER.info(
                "Bridge compression metrics img_id=%s per_image_comp_rate=%s aggregated_comp_rate=%s",
                img_id,
                f"{per_image_comp_rate:.4f}" if per_image_comp_rate is not None else None,
                f"{aggregated_comp_rate:.4f}" if aggregated_comp_rate is not None else None,
            )

            return EncodeResult(
                payload=payload,
                size_log=size_log,
                img_data=img_enc_data,
                timing_ms=timing_ms,
                bg_quota_bytes=tar_bg_bytes,
                obj_quota_bytes=tar_objs_bytes,
                fast_path_selected=bool(fast_path_bg or fast_path_obj),
                obj_detection_skipped=bool(img_skip_obj_detection),
                comp_rate=per_image_comp_rate,
                aggregated_comp_rate=aggregated_comp_rate,
                tar_comp_rate=getattr(pipeline_ctx, "target_compression_rate", None),
                comp_level=int(getattr(pipeline_ctx, "compression_level", compression_level)),
            )
        finally:
            if pipeline_config_applied:
                self.pipeline_mgr.restore_config()

    def decode_payload(self, payload: bytes, *, client_id: str | None = None) -> DecodeResult:
        """Decode one mux payload and return reconstructed PIL image.

        Args:
            payload: Raw mux payload bytes.
            client_id: Stable consumer identity (TCP client address or HTTP stream_id);
                scopes the assigned frame sequence (img_idx) so multiple clients sharing
                one bridge instance get independent, gap-free numbering.
        """
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError(f"payload must be bytes-like, got {type(payload).__name__}")

        frame_seq = self._next_decode_sequence(client_id)
        img_dec_data = _demux_frame(
            bytes(payload),
            self.cfg.mux_cfg,
            img_idx=frame_seq,
            max_crops=getattr(getattr(self.cfg, "model", None), "max_detections", None),
        )
        if img_dec_data is None or img_dec_data.bg is None:
            raise ValueError("Demuxed payload is missing background data")

        self.decoder.decompress_background(
            img_dec_data.bg,
            img_dec_data.org_img_size,
            img_dec_data.crops,
        )
        if img_dec_data.crops:
            self.decoder.decompress_objs(img_dec_data.crops)

        recon_on_full = _paste_with_margin(
            img_dec_data,
            margin_percent=self.cfg.img_process.additional_crop_margin,
            feather_ratio=self.cfg.img_process.paste_feather_ratio,
            feather_min_px=self.cfg.img_process.paste_feather_min_px,
        )

        if recon_on_full.size != img_dec_data.org_img_size:
            raise ValueError(
                f"Reconstructed image size {recon_on_full.size} does not match expected {img_dec_data.org_img_size}"
            )

        return DecodeResult(
            image=recon_on_full,
            img_idx=img_dec_data.img_idx,
            mask=getattr(img_dec_data.bg, "mask", None),
            org_img_size=img_dec_data.org_img_size,
            crops=img_dec_data.crops,
        )


    @staticmethod
    def _save_jpeg_from_image(image: Image.Image, quality: int = 95) -> bytes:
        """Encode PIL image to JPEG bytes."""
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality)
        return output.getvalue()



