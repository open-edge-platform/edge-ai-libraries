# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: integration/dlstreamer_client.py
Description: REST client bridging the star-image encoder to a running DL Streamer
Pipeline Server (https://github.com/open-edge-platform/edge-ai-libraries/tree/main/
microservices/dlstreamer-pipeline-server) instance. Used to run object detection
(via the server's `gvadetect` GStreamer element) instead of loading a YOLO model
locally in-process; see `utils/yolo_wrapper.run_yolo` for the backend it replaces.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from PIL import Image

Det = Tuple[float, float, float, float, float, int]

LOGGER = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({"COMPLETED", "ERROR", "ABORTED"})

# Fixed namespace the DL Streamer Pipeline Server uses for any pipeline supplied
# via configs/dlstreamer/config.json (as opposed to any built-in pipelines it may
# ship with) -- not something this project controls or needs to configure, so it's
# hardcoded rather than exposed as a config field. The REST endpoint is
# /pipelines/{_PIPELINE_SERVER_NAMESPACE}/{pipeline_name}, where `pipeline_name`
# is the actual pipeline id from config.json (e.g. "star_image_object_detection",
# see model.dlstreamer_pipeline_name in configs/default.yaml).
_PIPELINE_SERVER_NAMESPACE = "user_defined_pipelines"


class DLStreamerDetectionError(RuntimeError):
    """Raised when a DL Streamer Pipeline Server request fails, times out, or
    returns metadata that cannot be parsed into detections."""


class DLStreamerDetectionClient:
    """Runs object detection through a DL Streamer Pipeline Server pipeline instance.

    Each call to `detect()`:
      1. Writes the frame as a JPEG to `input_dir`, a directory bind-mounted at the
         same absolute path in both this process's container and the pipeline
         server container (see docker-compose.yml), so one path works for both
         local file I/O and the `file://` URI passed to the server.
      2. Starts a short-lived pipeline instance (`{auto_source} ! decodebin ! ... !
         gvadetect ! gvametaconvert ! gvametapublish`) via the REST API, pointing
         the source at that file and the metadata publisher at a per-request
         JSON-lines file in `output_dir` (mounted the same way).
      3. Polls the instance status until it reaches a terminal state.
      4. Parses the JSON-lines metadata file and returns detections in the same
         tuple format as `utils.yolo_wrapper.run_yolo`: (x1, y1, x2, y2, conf, cls).
      5. Stops the pipeline instance and removes the temporary input/output files.
    """

    def __init__(
        self,
        *,
        base_url: str,
        pipeline_name: str,
        pipeline_version: str,
        input_dir: Path,
        output_dir: Path,
        poll_interval_sec: float = 0.2,
        timeout_sec: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.pipeline_name = pipeline_name
        self.pipeline_version = pipeline_version
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.poll_interval_sec = poll_interval_sec
        self.timeout_sec = timeout_sec

        # trust_env=False: this client talks only to the pipeline server over the
        # internal service network and must never pick up a host/corporate proxy.
        self._client = http_client or httpx.Client(timeout=10.0, trust_env=False)
        self._owns_client = http_client is None

        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "DLStreamerDetectionClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def detect(
        self,
        pil_img: Image.Image,
        *,
        confidence_threshold: Optional[float] = None,
    ) -> List[Det]:
        """Run detection on one frame and return `(x1, y1, x2, y2, conf, cls)` tuples."""
        request_id = uuid.uuid4().hex
        input_path = self.input_dir / f"{request_id}.jpg"
        output_path = self.output_dir / f"{request_id}.jsonl"
        pipeline_input_uri = f"file://{input_path}"
        pipeline_output_path = str(output_path)

        pil_img.convert("RGB").save(input_path, format="JPEG", quality=95)

        instance_id = None
        try:
            instance_id = self._start_pipeline(
                uri=pipeline_input_uri,
                output_path=pipeline_output_path,
                confidence_threshold=confidence_threshold,
            )
            self._wait_for_completion(instance_id)
            return self._read_detections(output_path)
        finally:
            if instance_id is not None:
                self._stop_pipeline(instance_id)
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def _start_pipeline(
        self,
        *,
        uri: str,
        output_path: str,
        confidence_threshold: Optional[float],
    ) -> str:
        parameters = {"publish-properties": {"file-path": output_path}}
        if confidence_threshold is not None:
            parameters["detection-properties"] = {"threshold": float(confidence_threshold)}

        body = {"source": {"type": "uri", "uri": uri}, "parameters": parameters}
        url = f"{self.base_url}/pipelines/{self.pipeline_name}/{self.pipeline_version}"
        try:
            response = self._client.post(url, json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DLStreamerDetectionError(f"Failed to start DL Streamer pipeline at {url}: {exc}") from exc

        instance_id = response.text.strip().strip('"')
        if not instance_id:
            raise DLStreamerDetectionError(
                f"DL Streamer Pipeline Server returned an empty instance id from {url}"
            )
        return instance_id

    def _wait_for_completion(self, instance_id: str) -> None:
        # Note: only the unqualified /pipelines/{instance_id}/status endpoint is
        # implemented server-side; the /{name}/{version}/{instance_id}/status
        # variant always returns 400 (NOT_IMPLEMENTED) as of DL Streamer Pipeline
        # Server 2025.2.0.
        status_url = f"{self.base_url}/pipelines/{instance_id}/status"
        deadline = time.monotonic() + self.timeout_sec
        last_state = None
        while time.monotonic() < deadline:
            try:
                response = self._client.get(status_url)
                response.raise_for_status()
                status = response.json()
            except httpx.HTTPError as exc:
                raise DLStreamerDetectionError(
                    f"Failed to query DL Streamer pipeline status at {status_url}: {exc}"
                ) from exc

            last_state = status.get("state")
            if last_state == "COMPLETED":
                return
            if last_state in _TERMINAL_STATES:
                raise DLStreamerDetectionError(
                    f"DL Streamer pipeline instance {instance_id} finished with state={last_state}"
                )
            time.sleep(self.poll_interval_sec)

        raise DLStreamerDetectionError(
            f"Timed out after {self.timeout_sec}s waiting for DL Streamer pipeline instance "
            f"{instance_id} to complete (last state={last_state})"
        )

    def _stop_pipeline(self, instance_id: str) -> None:
        url = f"{self.base_url}/pipelines/{instance_id}"
        try:
            self._client.delete(url)
        except httpx.HTTPError as exc:
            LOGGER.debug("Failed to stop DL Streamer pipeline instance %s: %s", instance_id, exc)

    @staticmethod
    def _read_detections(output_path: Path) -> List[Det]:
        if not output_path.exists():
            raise DLStreamerDetectionError(
                f"DL Streamer pipeline completed but no metadata file was written: {output_path}"
            )

        dets: List[Det] = []
        with open(output_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DLStreamerDetectionError(
                        f"Failed to parse DL Streamer metadata line in {output_path}: {exc}"
                    ) from exc

                resolution = record.get("resolution") or {}
                width = float(resolution.get("width") or 0) or None
                height = float(resolution.get("height") or 0) or None

                for obj in record.get("objects", []):
                    detection = obj.get("detection") or {}
                    bbox = detection.get("bounding_box")

                    # Prefer the pixel-space ROI rect (x, y, w, h); it avoids
                    # re-denormalizing the fractional bounding_box and any rounding drift.
                    if all(k in obj for k in ("x", "y", "w", "h")):
                        x1 = float(obj["x"])
                        y1 = float(obj["y"])
                        x2 = x1 + float(obj["w"])
                        y2 = y1 + float(obj["h"])
                    elif bbox is not None and width and height:
                        x1 = float(bbox["x_min"]) * width
                        y1 = float(bbox["y_min"]) * height
                        x2 = float(bbox["x_max"]) * width
                        y2 = float(bbox["y_max"]) * height
                    else:
                        LOGGER.warning("Skipping detection with no usable bounding box: %s", obj)
                        continue

                    conf = float(detection.get("confidence", 0.0))
                    cls = int(detection.get("label_id", -1))
                    dets.append((x1, y1, x2, y2, conf, cls))
        return dets


def build_client_from_config(cfg) -> DLStreamerDetectionClient:
    """Construct a `DLStreamerDetectionClient` from a loaded `utils.config.Config`."""
    model_cfg = cfg.model
    return DLStreamerDetectionClient(
        base_url=model_cfg.dlstreamer_base_url,
        pipeline_name=_PIPELINE_SERVER_NAMESPACE,
        pipeline_version=model_cfg.dlstreamer_pipeline_name,
        input_dir=Path(model_cfg.dlstreamer_exchange_input_dir),
        output_dir=Path(model_cfg.dlstreamer_exchange_output_dir),
        poll_interval_sec=model_cfg.dlstreamer_poll_interval_sec,
        timeout_sec=model_cfg.dlstreamer_timeout_sec,
    )


def run_dlstreamer_detect(
    pil_img: Image.Image,
    cfg,
    *,
    client: Optional[DLStreamerDetectionClient] = None,
) -> List[Det]:
    """Drop-in replacement for `utils.yolo_wrapper.run_yolo`, backed by DL Streamer
    Pipeline Server instead of a locally loaded YOLO model.

    Args:
        pil_img: Input raw image.
        cfg: Loaded application config (uses `cfg.model.pre_comp_conf` /
            `cfg.model.valid_obj_categories`).
        client: Optional pre-built client (e.g. one owned by `Encoder`, so the
            HTTP connection is reused across frames). A short-lived client is
            created and closed automatically when not provided.

    Returns:
        List of `(x1, y1, x2, y2, conf, class_index)` tuples, filtered by
        `cfg.model.valid_obj_categories` the same way `run_yolo` filters them.
    """
    owns_client = client is None
    active_client = client or build_client_from_config(cfg)
    try:
        dets = active_client.detect(pil_img, confidence_threshold=cfg.model.pre_comp_conf)
    finally:
        if owns_client:
            active_client.close()

    allowed_classes = cfg.model.valid_obj_categories
    if allowed_classes is not None:
        dets = [d for d in dets if d[5] in allowed_classes]
    return dets
