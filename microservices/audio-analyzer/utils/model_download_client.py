# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Provision snapshots through an already running Model Download REST service.

Used when Audio Analyzer is deployed next to a shared Model Download container
(for example Smart Classroom) instead of its own ephemeral provisioning job.
Both containers must mount the same models storage: Model Download writes to
`MODELS_DIR` (default /opt/models) and Audio Analyzer reads the same files at
`models.asr.models_base_path`.
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from utils.config_loader import config
from utils.provision_models import build_request_entry, prepare_snapshot, provision_models

logger = logging.getLogger(__name__)

SERVICE_URL_ENV = "AUDIO_ANALYZER_MODEL_DOWNLOAD_URL"
TIMEOUT_ENV = "AUDIO_ANALYZER_MODEL_DOWNLOAD_TIMEOUT_SEC"
DEFAULT_TIMEOUT_SEC = 1800.0
POLL_INTERVAL_SEC = 2.0
_REQUEST_TIMEOUT_SEC = 15
_MAX_RESPONSE_BYTES = 64 * 1024
_JOB_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_TERMINAL_STATES = {"completed", "failed", "canceled", "cancelled"}
# Container-to-container call: never route it through a corporate proxy.
_OPENER = build_opener(ProxyHandler({}))


def get_service_url() -> str | None:
    """Return the validated Model Download base URL, or None when not configured."""
    raw = os.environ.get(SERVICE_URL_ENV, "").strip().rstrip("/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            f"{SERVICE_URL_ENV} must be the Model Download base URL "
            "(for example http://model-downloader:8000)"
        )
    return raw


def _timeout_sec() -> float:
    raw = os.environ.get(TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{TIMEOUT_ENV} must be a number of seconds") from exc
    if value <= 0:
        raise RuntimeError(f"{TIMEOUT_ENV} must be positive")
    return value


def _request_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with _OPENER.open(request, timeout=_REQUEST_TIMEOUT_SEC) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        detail = exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"Model Download request failed (HTTP {exc.code}): {detail[:500] or 'no details'}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Model Download service is unreachable at {url}: {exc}") from exc
    if len(body) > _MAX_RESPONSE_BYTES:
        raise RuntimeError("Model Download response exceeds 64 KiB")
    try:
        result = json.loads(body)
    except ValueError as exc:
        raise RuntimeError("Model Download returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Unexpected Model Download response")
    return result


async def _run_download_job(
    base_url: str,
    model: str,
    hub: str,
    download_path: str,
    entry: dict[str, object],
    timeout_sec: float,
) -> None:
    endpoint = f"{base_url}/models/download?{urlencode({'download_path': download_path})}"
    response = await asyncio.to_thread(_request_json, endpoint, {"models": [entry]})
    job_ids = response.get("job_ids")
    if (
        not isinstance(job_ids, list)
        or len(job_ids) != 1
        or not isinstance(job_ids[0], str)
        or not _JOB_ID.fullmatch(job_ids[0])
    ):
        raise RuntimeError(f"Model Download did not return exactly one job for {model}")
    job_id = job_ids[0]
    logger.info("Model Download job %s started for %s (%s)", job_id, model, hub)

    deadline = time.monotonic() + timeout_sec
    while True:
        job = await asyncio.to_thread(_request_json, f"{base_url}/jobs/{job_id}")
        status = str(job.get("status", "")).lower()
        if status == "completed":
            result = job.get("result")
            if (
                not isinstance(result, dict)
                or result.get("model_name") != model
                or result.get("source") != hub
            ):
                raise RuntimeError(f"Model Download job {job_id} completed with an unexpected result for {model}")
            return
        if status in _TERMINAL_STATES:
            raise RuntimeError(
                f"Model Download job for {model} {status}: {job.get('error', 'no details')}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out after {timeout_sec:.0f}s waiting for Model Download to provision {model}"
            )
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def fetch_from_service(
    model: str,
    revision: str | None = None,
    *,
    hub: str = "huggingface",
    download_path: str,
    required_files: list[str],
    files: list[str] | None = None,
    hf_token: str | None = None,
    models_base_path: str | None = None,
) -> str:
    """`fetch` implementation for `provision_models()` backed by the REST API."""
    base_url = get_service_url()
    if base_url is None:
        raise RuntimeError(f"{SERVICE_URL_ENV} is not set")
    models_dir = models_base_path or config.models.asr.models_base_path
    timeout_sec = _timeout_sec()

    async def download(_: Path) -> None:
        entry = build_request_entry(model, revision, hub=hub, files=files, hf_token=hf_token)
        await _run_download_job(base_url, model, hub, download_path, entry, timeout_sec)

    return await prepare_snapshot(
        model, revision, hub=hub, download_path=download_path,
        required_files=required_files, models_dir=models_dir, download=download,
    )


async def provision_from_service() -> None:
    await provision_models(fetch_from_service)
    logger.info("All configured snapshots are ready on the shared models volume")


def provision_from_service_if_configured() -> bool:
    """Provision via the shared service when configured; returns False when not."""
    if get_service_url() is None:
        return False
    asyncio.run(provision_from_service())
    return True
