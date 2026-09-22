# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle management for the isolated OpenCV-to-OVMS streaming proof of concept."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import httpx

from managers.metadata_manager import METADATA_DIR
from videos import OUTPUT_VIDEO_DIR


logger = logging.getLogger("ovms_poc_manager")
INPUT_VIDEO_DIR = Path(os.getenv("INPUT_VIDEO_DIR", "/videos/input"))
OVMS_GRPC_ENDPOINT = os.getenv("OVMS_GRPC_ENDPOINT", "ovms:9000")
OVMS_REST_ENDPOINT = os.getenv("OVMS_REST_ENDPOINT", "http://ovms:8080").rstrip("/")
OVMS_METRICS_ENDPOINT = f"{OVMS_REST_ENDPOINT}/metrics"
RUNNER_PATH = Path(__file__).resolve().parents[1] / "ovms_poc_runner.py"
METRICS_MANAGER_URL = os.getenv(
    "METRICS_MANAGER_URL",
    "http://metrics-manager:9090",
).rstrip("/")
OVMS_MODEL_NAME = os.getenv(
    "OVMS_MODEL_NAME",
    "public_ssdlite_object_detection",
)


class OvmsPocManager:
    """Owns POC runner processes and their on-disk status artifacts."""

    _instance: "OvmsPocManager | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "OvmsPocManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._jobs: dict[str, subprocess.Popen[bytes]] = {}
        self._job_directories: dict[str, Path] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _resolve_input_video(input_video: str) -> Path:
        requested_path = Path(input_video)
        if requested_path.is_absolute() or ".." in requested_path.parts:
            raise ValueError(
                "input_video must be a relative path below INPUT_VIDEO_DIR"
            )
        input_root = INPUT_VIDEO_DIR.resolve()
        candidate = (input_root / requested_path).resolve()
        if not candidate.is_relative_to(input_root):
            raise ValueError("input_video must be located below INPUT_VIDEO_DIR")
        if not candidate.is_file():
            raise FileNotFoundError(f"Input video does not exist: {input_video}")
        return candidate

    def ensure_ovms_ready(self) -> None:
        try:
            with httpx.Client(timeout=2, trust_env=False) as client:
                response = client.get(f"{OVMS_REST_ENDPOINT}/v2/health/ready")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(
                f"OVMS is unavailable at {OVMS_REST_ENDPOINT}: {error}"
            ) from error

    def start_job(
        self,
        input_video: str,
        graph_name: str,
        max_parallel_requests: int,
        max_inference_width: int,
        max_inference_height: int,
        request_timeout_s: float,
    ) -> str:
        self.ensure_ovms_ready()
        source_path = self._resolve_input_video(input_video)
        job_id = f"ovms-poc-{uuid.uuid4().hex}"
        metadata_directory = Path(METADATA_DIR) / job_id
        output_directory = Path(OUTPUT_VIDEO_DIR) / job_id
        metadata_directory.mkdir(parents=True, exist_ok=False)
        output_directory.mkdir(parents=True, exist_ok=False)

        status_path = metadata_directory / "status.json"
        config_path = metadata_directory / "request.json"
        runner_log_path = metadata_directory / "runner.log"
        config = {
            "job_id": job_id,
            "input_video": str(source_path),
            "output_video": str(output_directory / "output.mp4"),
            "metadata_path": str(metadata_directory / "predictions.jsonl"),
            "status_path": str(status_path),
            "summary_path": str(metadata_directory / "summary.json"),
            "grpc_address": OVMS_GRPC_ENDPOINT,
            "graph_name": graph_name,
            "max_parallel_requests": max_parallel_requests,
            "max_inference_width": max_inference_width,
            "max_inference_height": max_inference_height,
            "request_timeout_s": request_timeout_s,
            "metrics_manager_url": METRICS_MANAGER_URL,
            "ovms_metrics_url": OVMS_METRICS_ENDPOINT,
            "ovms_model_name": OVMS_MODEL_NAME,
        }
        self._write_json(config_path, config)
        self._write_json(status_path, {"state": "STARTING", "job_id": job_id})

        with runner_log_path.open("wb") as runner_log:
            process = subprocess.Popen(
                [sys.executable, str(RUNNER_PATH), "--config", str(config_path)],
                cwd=str(RUNNER_PATH.parent),
                stdout=runner_log,
                stderr=subprocess.STDOUT,
            )
        with self._lock:
            self._jobs[job_id] = process
            self._job_directories[job_id] = metadata_directory
        return job_id

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            process = self._jobs.get(job_id)
            directory = self._job_directories.get(job_id)
        if directory is None:
            return None
        status_path = directory / "status.json"
        status = self._read_json(status_path) or {"state": "UNKNOWN", "job_id": job_id}
        if (
            process is not None
            and process.poll() is not None
            and status.get("state") in {"STARTING", "RUNNING"}
        ):
            status = {
                "state": "FAILED",
                "job_id": job_id,
                "message": f"OVMS POC runner exited with code {process.returncode}",
            }
            self._write_json(status_path, status)
        return status

    def get_metadata(
        self, job_id: str, limit: int = 200
    ) -> list[dict[str, Any]] | None:
        """Return the latest JSONL prediction records for a known POC job."""
        with self._lock:
            directory = self._job_directories.get(job_id)
        if directory is None:
            return None
        metadata_path = directory / "predictions.jsonl"
        if not metadata_path.is_file():
            return []
        records: deque[dict[str, Any]] = deque(maxlen=limit)
        with metadata_path.open(encoding="utf-8") as metadata_file:
            for line in metadata_file:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
            return list(records)

    def stop_job(self, job_id: str) -> tuple[bool, str]:
        with self._lock:
            process = self._jobs.get(job_id)
        if process is None:
            return False, f"OVMS POC job {job_id} not found"
        if process.poll() is not None:
            return False, f"OVMS POC job {job_id} is not running"
        process.terminate()
        return True, f"Stop requested for OVMS POC job {job_id}"
