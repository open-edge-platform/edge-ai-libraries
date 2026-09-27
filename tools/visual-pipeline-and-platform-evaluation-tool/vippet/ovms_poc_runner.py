# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run a file-to-file KServe gRPC streaming inference job through OVMS."""

from __future__ import annotations

import argparse
import json
import logging
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
import tritonclient.grpc as grpcclient


logger = logging.getLogger("ovms_poc_runner")
_stop_requested = threading.Event()
_PROMETHEUS_LABEL_PATTERN = re.compile(r'([a-z_]+)="([^"]*)"')


@dataclass(frozen=True)
class OvmsInferenceMetrics:
    """Prometheus histogram totals for one OVMS backend model."""

    count: float
    total_time_us: float


def _post_metric(
    url: str,
    payload: dict[str, Any],
    description: str,
) -> threading.Thread:
    """Send one telemetry payload without blocking OVMS inference."""
    data = json.dumps(payload).encode("utf-8")

    def worker() -> None:
        try:
            response = httpx.post(
                url,
                content=data,
                headers={"Content-Type": "application/json"},
                timeout=1.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning(
                "Failed to post %s metric to %s: %s",
                description,
                url,
                error,
            )

    thread = threading.Thread(
        target=worker,
        name=f"ovms-metrics-{description}",
        daemon=True,
    )
    thread.start()
    return thread


def _read_ovms_inference_metrics(
    metrics_url: str,
    model_name: str,
) -> OvmsInferenceMetrics | None:
    """Return OVMS backend inference histogram totals for one model."""
    try:
        response = httpx.get(metrics_url, timeout=1.0)
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("Failed to read OVMS metrics from %s: %s", metrics_url, error)
        return None

    inference_count = 0.0
    total_time_us = 0.0
    found_count = False
    for line in response.text.splitlines():
        if not line.startswith(
            (
                "ovms_inference_time_us_count{",
                "ovms_inference_time_us_sum{",
            )
        ):
            continue
        sample, value = line.rsplit(maxsplit=1)
        labels = dict(_PROMETHEUS_LABEL_PATTERN.findall(sample))
        if labels.get("name") != model_name:
            continue
        try:
            if sample.startswith("ovms_inference_time_us_count{"):
                inference_count += float(value)
                found_count = True
            else:
                total_time_us += float(value)
        except ValueError:
            logger.warning("Invalid OVMS inference metric value: %s", value)
            return None

    if found_count:
        return OvmsInferenceMetrics(
            count=inference_count,
            total_time_us=total_time_us,
        )

    # OVMS creates the per-model histogram after its first inference request.
    # A healthy endpoint with no matching sample therefore represents zero
    # completed requests at the start of a job.
    return OvmsInferenceMetrics(count=0.0, total_time_us=0.0)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def _request_stop(_signum: int, _frame: Any) -> None:
    _stop_requested.set()


def _prepare_frame(
    frame: np.ndarray,
    max_width: int,
    max_height: int,
) -> np.ndarray:
    frame_height, frame_width = frame.shape[:2]
    scale = min(max_width / frame_width, max_height / frame_height, 1.0)
    inference_width = round(frame_width * scale)
    inference_height = round(frame_height * scale)
    inference_frame = cv2.resize(
        frame,
        (inference_width, inference_height),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(inference_frame)


def _prediction_record(
    frame_id: int,
    timestamp_ms: float,
    inference_ms: float,
    response_timestamp: int,
    output_shape: tuple[int, ...],
) -> dict[str, Any]:
    return {
        "frame_id": frame_id,
        "timestamp_ms": round(timestamp_ms, 3),
        "ovms_inference_ms": round(inference_ms, 3),
        "response_timestamp": response_timestamp,
        "output_shape": list(output_shape),
    }


def _publish_browser_video(intermediate_video: Path, output_video: Path) -> None:
    """Publish the OpenCV output as a browser-compatible MP4 artifact."""
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(intermediate_video),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    subprocess.run(
        command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    intermediate_video.unlink(missing_ok=True)


def run(config_path: Path) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    job_id = str(config["job_id"])
    input_video = Path(config["input_video"])
    output_video = Path(config["output_video"])
    metadata_path = Path(config["metadata_path"])
    status_path = Path(config["status_path"])
    summary_path = Path(config["summary_path"])
    grpc_address = str(config["grpc_address"])
    graph_name = str(config["graph_name"])
    max_parallel_requests = int(config["max_parallel_requests"])
    max_width = int(config["max_inference_width"])
    max_height = int(config["max_inference_height"])
    timeout_s = float(config["request_timeout_s"])
    metrics_manager_url = str(config["metrics_manager_url"])
    ovms_metrics_url = str(config["ovms_metrics_url"])
    ovms_model_name = str(config["ovms_model_name"])
    fps_metrics_url = f"{metrics_manager_url}/api/v1/metrics/simple"
    latency_metrics_url = f"{metrics_manager_url}/api/v1/metrics"

    metric_tags = {
        "job_id": job_id,
        "stream_id": "ovms",
        "runtime": "ovms",
        "graph_name": graph_name,
    }

    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open input video: {input_video}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    intermediate_video = output_video.with_name(f"{output_video.stem}.intermediate.mp4")
    writer = cv2.VideoWriter(
        str(intermediate_video),
        cv2.VideoWriter.fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Cannot create output video: {output_video}")

    started = time.perf_counter()
    frame_id = 0
    next_frame_id = 0
    failed_frames = 0
    inference_times_ms: list[float] = []
    metrics_window_started = started
    metrics_window_completed_frames = 0
    metrics_window_inference_times_ms: list[float] = []
    in_flight_metric_threads: list[threading.Thread] = []
    ovms_metrics_at_start: OvmsInferenceMetrics | None = None
    ovms_inference_count_previous: float | None = None
    responses: queue.Queue[
        tuple[grpcclient.InferResult | None, BaseException | None]
    ] = queue.Queue()
    pending_frames: dict[int, tuple[float, float]] = {}
    completed_frames: dict[
        int, tuple[np.ndarray, float, float, int, tuple[int, ...]]
    ] = {}

    def callback(
        result: grpcclient.InferResult | None, error: BaseException | None
    ) -> None:
        responses.put((result, error))

    def write_completed(metadata_file) -> None:
        nonlocal frame_id
        while frame_id in completed_frames:
            (
                annotated_frame,
                timestamp_ms,
                inference_ms,
                response_timestamp,
                output_shape,
            ) = completed_frames.pop(frame_id)
            writer.write(annotated_frame)
            metadata_file.write(
                json.dumps(
                    _prediction_record(
                        frame_id,
                        timestamp_ms,
                        inference_ms,
                        response_timestamp,
                        output_shape,
                    )
                )
                + "\n"
            )
            frame_id += 1

    def publish_metrics_window(
        window_seconds: float,
        completed_frames: int,
        inference_times_ms: list[float],
    ) -> list[threading.Thread]:
        if window_seconds <= 0:
            return []

        window_fps = completed_frames / window_seconds
        metric_threads = [
            _post_metric(
                fps_metrics_url,
                {
                    "name": "fps",
                    "value": round(window_fps, 3),
                    "tags": metric_tags,
                },
                "fps",
            )
        ]

        if not inference_times_ms:
            return metric_threads

        metric_threads.append(
            _post_metric(
                latency_metrics_url,
                {
                    "metrics": [
                        {
                            "name": "pipeline_latency",
                            "fields": {
                                "avg_ms": round(
                                    sum(inference_times_ms) / len(inference_times_ms),
                                    3,
                                ),
                                "min_ms": round(min(inference_times_ms), 3),
                                "max_ms": round(max(inference_times_ms), 3),
                                "latency_ms": round(inference_times_ms[-1], 3),
                            },
                            "tags": metric_tags,
                        }
                    ]
                },
                "latency",
            )
        )
        return metric_threads

    _write_json(
        status_path, {"state": "RUNNING", "job_id": job_id, "frames_processed": 0}
    )
    try:
        client = grpcclient.InferenceServerClient(url=grpc_address, verbose=False)
        client.start_stream(callback=callback)
        ovms_metrics_at_start = _read_ovms_inference_metrics(
            ovms_metrics_url,
            ovms_model_name,
        )
        ovms_inference_count_previous = (
            ovms_metrics_at_start.count if ovms_metrics_at_start is not None else None
        )
        try:
            with metadata_path.open("w", encoding="utf-8") as metadata_file:
                input_exhausted = False
                while not input_exhausted or pending_frames:
                    while (
                        not input_exhausted
                        and not _stop_requested.is_set()
                        and len(pending_frames) < max_parallel_requests
                    ):
                        ok, frame = capture.read()
                        if not ok:
                            input_exhausted = True
                            break
                        timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
                        inference_frame = _prepare_frame(frame, max_width, max_height)
                        infer_input = grpcclient.InferInput(
                            "input", inference_frame.shape, "UINT8"
                        )
                        infer_input.set_data_from_numpy(inference_frame)
                        pending_frames[next_frame_id] = (
                            timestamp_ms,
                            time.perf_counter(),
                        )
                        client.async_stream_infer(
                            model_name=graph_name,
                            inputs=[infer_input],
                            outputs=[
                                grpcclient.InferRequestedOutput("annotated_image")
                            ],
                            parameters={"OVMS_MP_TIMESTAMP": next_frame_id},
                        )
                        next_frame_id += 1

                    if _stop_requested.is_set():
                        input_exhausted = True
                    try:
                        result, error = responses.get(timeout=timeout_s)
                    except queue.Empty as error:
                        raise TimeoutError(
                            "Timed out waiting for OVMS streaming response"
                        ) from error
                    if error is not None:
                        raise RuntimeError(f"OVMS streaming inference failed: {error}")
                    if result is None:
                        raise RuntimeError("OVMS streaming callback returned no result")
                    response_timestamp = (
                        result.get_response()
                        .parameters["OVMS_MP_TIMESTAMP"]
                        .int64_param
                    )
                    timestamp_ms, request_started = pending_frames.pop(
                        response_timestamp
                    )
                    annotated_output = result.as_numpy("annotated_image")
                    if annotated_output is None:
                        raise RuntimeError(
                            "OVMS streaming response did not contain annotated_image"
                        )
                    annotated_frame = np.asarray(annotated_output, dtype=np.uint8)
                    output_shape = annotated_frame.shape
                    annotated_frame = cv2.resize(
                        annotated_frame, (width, height), interpolation=cv2.INTER_LINEAR
                    )
                    inference_ms = (time.perf_counter() - request_started) * 1000
                    inference_times_ms.append(inference_ms)
                    metrics_window_completed_frames += 1
                    metrics_window_inference_times_ms.append(inference_ms)
                    completed_frames[response_timestamp] = (
                        annotated_frame,
                        timestamp_ms,
                        inference_ms,
                        response_timestamp,
                        output_shape,
                    )
                    write_completed(metadata_file)
                    now = time.perf_counter()
                    window_seconds = now - metrics_window_started
                    if window_seconds >= 1.0:
                        ovms_metrics_current = _read_ovms_inference_metrics(
                            ovms_metrics_url,
                            ovms_model_name,
                        )
                        ovms_inference_count_current = (
                            ovms_metrics_current.count
                            if ovms_metrics_current is not None
                            else None
                        )
                        ovms_fps = None
                        if (
                            ovms_inference_count_current is not None
                            and ovms_inference_count_previous is not None
                            and ovms_inference_count_current
                            >= ovms_inference_count_previous
                        ):
                            ovms_fps = (
                                ovms_inference_count_current
                                - ovms_inference_count_previous
                            ) / window_seconds
                        if ovms_inference_count_current is not None:
                            ovms_inference_count_previous = ovms_inference_count_current
                        in_flight_metric_threads.extend(
                            publish_metrics_window(
                                window_seconds,
                                metrics_window_completed_frames,
                                metrics_window_inference_times_ms,
                            )
                        )
                        in_flight_metric_threads[:] = [
                            thread
                            for thread in in_flight_metric_threads
                            if thread.is_alive()
                        ]
                        metrics_window_started = now
                        metrics_window_completed_frames = 0
                        metrics_window_inference_times_ms.clear()
                        elapsed_s = time.perf_counter() - started
                        _write_json(
                            status_path,
                            {
                                "state": "RUNNING",
                                "job_id": job_id,
                                "frames_processed": frame_id,
                                "fps": round(frame_id / elapsed_s, 3)
                                if elapsed_s
                                else 0,
                                "ovms_fps": round(ovms_fps, 3)
                                if ovms_fps is not None
                                else None,
                                "mean_ovms_inference_ms": round(
                                    sum(inference_times_ms) / len(inference_times_ms),
                                    3,
                                )
                                if inference_times_ms
                                else None,
                            },
                        )
        finally:
            client.stop_stream()
    finally:
        capture.release()
        writer.release()

        for thread in in_flight_metric_threads:
            thread.join()

        final_window_seconds = time.perf_counter() - metrics_window_started
        if metrics_window_completed_frames > 0 or metrics_window_inference_times_ms:
            for thread in publish_metrics_window(
                final_window_seconds,
                metrics_window_completed_frames,
                metrics_window_inference_times_ms,
            ):
                thread.join()

        final_fps_thread = _post_metric(
            fps_metrics_url,
            {
                "name": "fps",
                "value": 0.0,
                "tags": metric_tags,
            },
            "fps",
        )
        final_fps_thread.join()

    inference_finished = time.perf_counter()
    _publish_browser_video(intermediate_video, output_video)

    duration_s = time.perf_counter() - started
    inference_duration_s = inference_finished - started
    ovms_metrics_at_end = _read_ovms_inference_metrics(
        ovms_metrics_url,
        ovms_model_name,
    )
    ovms_fps = (
        (ovms_metrics_at_end.count - ovms_metrics_at_start.count) / inference_duration_s
        if (
            ovms_metrics_at_end is not None
            and ovms_metrics_at_start is not None
            and ovms_metrics_at_end.count >= ovms_metrics_at_start.count
            and inference_duration_s
        )
        else None
    )
    ovms_inference_count = (
        ovms_metrics_at_end.count - ovms_metrics_at_start.count
        if (
            ovms_metrics_at_end is not None
            and ovms_metrics_at_start is not None
            and ovms_metrics_at_end.count >= ovms_metrics_at_start.count
        )
        else None
    )
    ovms_inference_time_us = (
        ovms_metrics_at_end.total_time_us - ovms_metrics_at_start.total_time_us
        if (
            ovms_metrics_at_end is not None
            and ovms_metrics_at_start is not None
            and ovms_metrics_at_end.total_time_us >= ovms_metrics_at_start.total_time_us
        )
        else None
    )
    state = "CANCELLED" if _stop_requested.is_set() else "COMPLETED"
    sorted_times = sorted(inference_times_ms)
    p95_index = max(0, round(len(sorted_times) * 0.95) - 1)
    summary = {
        "job_id": job_id,
        "state": state,
        "frames_processed": frame_id,
        "failed_frames": failed_frames,
        "duration_s": round(duration_s, 3),
        "end_to_end_fps": round(frame_id / duration_s, 3) if duration_s else 0,
        "ovms_fps": round(ovms_fps, 3) if ovms_fps is not None else None,
        "ovms_model_name": ovms_model_name,
        "ovms_inference_count": int(ovms_inference_count)
        if ovms_inference_count is not None
        else None,
        "ovms_inference_time_us": round(ovms_inference_time_us, 3)
        if ovms_inference_time_us is not None
        else None,
        "ovms_mean_inference_ms": round(
            ovms_inference_time_us / ovms_inference_count / 1000,
            3,
        )
        if ovms_inference_time_us is not None and ovms_inference_count
        else None,
        "mean_ovms_inference_ms": round(
            sum(inference_times_ms) / len(inference_times_ms), 3
        )
        if inference_times_ms
        else 0,
        "p95_ovms_inference_ms": round(sorted_times[p95_index], 3)
        if sorted_times
        else 0,
        "output_video": str(output_video),
        "metadata_path": str(metadata_path),
    }
    _write_json(summary_path, summary)
    _write_json(status_path, summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        return run(arguments.config)
    except Exception as error:
        logger.exception("OVMS POC runner failed: %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
