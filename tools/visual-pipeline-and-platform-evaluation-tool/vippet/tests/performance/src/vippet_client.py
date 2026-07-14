# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
VIPPET REST API Client

Provides interface to interact with VIPPET REST API endpoints.
"""

import os
import time
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class VIPPETClient:
    """Client for interacting with VIPPET REST API."""

    def __init__(self, base_url: str, timeout: int = 600):
        """
        Initialize VIPPET client.

        Args:
            base_url: VIPPET API base URL (e.g., http://localhost/api/v1)
            timeout: Default timeout for API requests in seconds
        """
        self.base_url = os.environ.get("VIPPET_BASE_URL", base_url).rstrip("/")
        self.timeout = timeout
        self.session = httpx.Client(
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )

        logger.info(f"Initialized VIPPET client: {self.base_url}")

    def health_check(self) -> bool:
        """
        Check if VIPPET API is healthy and reachable.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10.0)
            response.raise_for_status()
            logger.info("✓ VIPPET API health check passed")
            return True
        except Exception as e:
            logger.error(f"✗ VIPPET API health check failed: {e}")
            return False

    def wait_for_ready(self, max_wait: int = 300, check_interval: int = 5) -> bool:
        """
        Wait for VIPPET API to become ready.

        Args:
            max_wait: Maximum time to wait in seconds
            check_interval: Interval between checks in seconds

        Returns:
            True if ready, False if timeout
        """
        logger.info(f"Waiting for VIPPET API to be ready (max {max_wait}s)...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if self.health_check():
                return True
            time.sleep(check_interval)

        logger.error(f"VIPPET API not ready after {max_wait}s")
        return False

    def get_devices(self) -> list[dict[str, Any]]:
        """
        Fetch available hardware devices.

        Returns:
            List of device dictionaries with keys: device_id, device_family, device_name, device_type

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        logger.info("Fetching available devices...")
        response = self.session.get(f"{self.base_url}/devices", timeout=30.0)
        response.raise_for_status()
        devices = response.json()

        logger.info(f"Found {len(devices)} device(s)")
        for device in devices:
            logger.debug(
                f"  - {device.get('device_family')}: {device.get('device_name')}"
            )

        return devices

    def get_pipelines(self) -> list[dict[str, Any]]:
        """
        Fetch all available pipelines with their variants.

        Returns:
            List of pipeline dictionaries with keys: id, name, description, variants

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        logger.info("Fetching available pipelines...")
        response = self.session.get(f"{self.base_url}/pipelines", timeout=30.0)
        response.raise_for_status()
        pipelines = response.json()

        logger.info(f"Found {len(pipelines)} pipeline(s)")
        for pipeline in pipelines:
            variant_count = len(pipeline.get("variants", []))
            logger.debug(f"  - {pipeline.get('name')}: {variant_count} variant(s)")

        return pipelines

    def get_models(self) -> list[dict[str, Any]]:
        """
        Fetch all available models and their installation status.

        Returns:
            List of model dictionaries with keys: display_name, install_status, used_by_pipelines

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        logger.info("Fetching model information...")
        response = self.session.get(f"{self.base_url}/models", timeout=30.0)
        response.raise_for_status()
        models = response.json()

        installed_count = sum(
            1 for m in models if m.get("install_status", "").lower() == "installed"
        )
        logger.info(f"Found {len(models)} model(s), {installed_count} installed")

        return models

    def submit_performance_test(
        self,
        pipeline_id: str,
        variant_id: str,
        streams: int,
        output_mode: str = "disabled",
        max_runtime: int | None = None,
    ) -> str:
        """
        Submit a performance test job.

        Args:
            pipeline_id: Pipeline ID
            variant_id: Variant ID (e.g., 'cpu', 'gpu', 'npu')
            streams: Number of parallel streams
            output_mode: Output mode ('disabled', 'file', 'live_stream')
            max_runtime: Maximum runtime in seconds (optional)

        Returns:
            Job ID string

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        payload = {
            "pipeline_performance_specs": [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": pipeline_id,
                        "variant_id": variant_id,
                    },
                    "streams": streams,
                }
            ],
            "execution_config": {"output_mode": output_mode},
        }

        if max_runtime:
            payload["execution_config"]["max_runtime"] = max_runtime

        logger.debug(
            f"Submitting performance test: {pipeline_id}/{variant_id} ({streams} streams)"
        )

        response = self.session.post(
            f"{self.base_url}/tests/performance", json=payload, timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        job_id = result.get("job_id")

        logger.info(f"Job submitted: {job_id}")
        return job_id

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """
        Get performance test job status.

        Args:
            job_id: Job ID returned from submit_performance_test

        Returns:
            Job status dictionary with keys: job_id, state, total_fps, per_stream_fps, etc.

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        response = self.session.get(
            f"{self.base_url}/jobs/tests/performance/{job_id}/status", timeout=30.0
        )
        response.raise_for_status()
        return response.json()

    def poll_job_completion(
        self, job_id: str, timeout: int = 600, poll_interval: int = 2
    ) -> dict[str, Any]:
        """
        Poll job status until completion or timeout.

        Args:
            job_id: Job ID to poll
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            Final job status dictionary

        Raises:
            TimeoutError: If job doesn't complete within timeout
            RuntimeError: If job fails
        """
        logger.info(
            f"Polling job {job_id} (timeout: {timeout}s, interval: {poll_interval}s)"
        )
        start_time = time.time()
        last_state = None

        while time.time() - start_time < timeout:
            status = self.get_job_status(job_id)
            state = status.get("state")

            # Log state changes
            if state != last_state:
                logger.info(f"  Job state: {state}")
                last_state = state

            if state == "COMPLETED":
                logger.info("✓ Job completed successfully")
                return status

            elif state == "FAILED":
                details = status.get("details", [])
                error_msg = (
                    details[0]
                    if details
                    else status.get("error_message", "Unknown error")
                )
                logger.error(f"✗ Job failed: {error_msg}")
                raise RuntimeError(f"Job {job_id} failed: {error_msg}")

            elif state in ["PENDING", "RUNNING"]:
                # Still processing, continue polling
                time.sleep(poll_interval)

            else:
                # Unknown state
                logger.warning(f"Unknown job state: {state}")
                time.sleep(poll_interval)

        # Timeout reached
        elapsed = time.time() - start_time
        raise TimeoutError(
            f"Job {job_id} did not complete within {timeout}s (elapsed: {elapsed:.1f}s)"
        )

    def close(self):
        """Close the HTTP session."""
        self.session.close()
        logger.debug("VIPPET client session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
